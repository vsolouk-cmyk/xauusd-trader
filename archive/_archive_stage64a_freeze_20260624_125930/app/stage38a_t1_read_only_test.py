#!/usr/bin/env python3
"""
Stage38A T1 Read-only Test

Project: XAUUSD / Gold Trading System
Purpose: Read-only evaluation of T1_REGIME_FILTERED_STRUCTURE_CONTINUATION.

This script is intentionally read-only with respect to project data stores.
It reads:
  - data/local/xauusd_local_store.sqlite::bars
  - data/local/xauusd_local_store.sqlite::macro_daily_regime

It writes only report files under:
  - data/reports/stage38a_t1_read_only_test/

It does NOT:
  - create orders
  - write dryrun/live/paper tables
  - touch EA/MQL files
  - touch scheduler/workflow files
  - connect to broker APIs
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sqlite3
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


STAGE = "Stage38A"
SCRIPT_NAME = "stage38a_t1_read_only_test.py"
DEFAULT_DB = "data/local/xauusd_local_store.sqlite"
DEFAULT_OUT_DIR = "data/reports/stage38a_t1_read_only_test"

SOURCE = "amarkets_mt5"
SYMBOL = "XAUUSD"
TIMEFRAME = "1h"

# Extracted from AMarkets/MT5 screenshot, Stage38A spec extraction.
DIGITS = 2
POINT = 0.01
CONTRACT_SIZE = 100

# Stage38A execution cost model v0.
SPREAD_COSTS = {
    "raw": 0.0,
    "base_p50": 37.0,
    "normal_p75": 43.0,
    "stress_p90": 49.0,
    "high_p95": 51.0,
    "tail_p99": 70.0,
}

# Convert spread points to price distance using POINT=0.01.
SPREAD_PRICE_COSTS = {k: v * POINT for k, v in SPREAD_COSTS.items()}

# Macro and structure constants.
MAX_MACRO_FFILL_DAYS = 5
ATR_PERIOD = 14
D1_MA_PERIOD = 50
H4_MA_PERIOD = 50
H4_MIN_H1_COUNT = 3
D1_MIN_H1_COUNT = 18
ROLLING_48H_LOOKBACK = 48

# Setup constants.
MIN_SWEEP_ATR = 0.10
MAX_SIGNAL_RANGE_ATR = 2.0
RETEST_TOLERANCE_ATR = 0.15
RETEST_MAX_BARS = 3
STOP_BUFFER_ATR = 0.10
MIN_STOP_ATR = 0.50
MAX_STOP_ATR = 2.50
TIME_STOP_H1_BARS = 5

# Data coverage gate.
MIN_REQUIRED_ROWS = 20_000
MIN_REQUIRED_START = date(2022, 6, 1)
MIN_REQUIRED_END = date(2026, 6, 1)

ENTRY_VARIANTS = [
    "V1_CLOSE_ACCEPTANCE",
    "V2_RETEST_CONFIRMATION",
    "V3_STRICT_NEXT_BAR_HOLD",
]
LEVEL_VARIANTS = [
    "previous_day_high",
    "rolling_48h_high",
]
TARGET_VARIANTS = [
    ("TP_1R", 1.0),
    ("TP_1_5R", 1.5),
]
TIME_VARIANT = "TIME_5H"


@dataclass
class Bar:
    idx: int
    utc_time: datetime
    open: float
    high: float
    low: float
    close: float
    spread: Optional[float] = None
    atr_h1_14: Optional[float] = None
    previous_day_high: Optional[float] = None
    rolling_48h_high: Optional[float] = None
    d1_close: Optional[float] = None
    d1_ma50: Optional[float] = None
    h4_close: Optional[float] = None
    h4_ma50: Optional[float] = None
    macro_regime: Optional[str] = None
    macro_score_long_gold: Optional[float] = None
    d_real_yield_20d: Optional[float] = None
    d_usd_20d_pct: Optional[float] = None
    regime_reason: Optional[str] = None


@dataclass
class MacroRow:
    obs_date: date
    macro_regime: str
    macro_score_long_gold: Optional[float]
    d_real_yield_20d: Optional[float]
    d_usd_20d_pct: Optional[float]
    rate_pressure_score: Optional[float]
    usd_pressure_score: Optional[float]
    regime_reason: str


@dataclass
class D1Row:
    d: date
    open: float
    high: float
    low: float
    close: float
    h1_count: int
    ma50: Optional[float]


@dataclass
class H4Row:
    start: datetime
    end: datetime
    open: float
    high: float
    low: float
    close: float
    h1_count: int
    ma50: Optional[float]


@dataclass
class PlannedEntry:
    entry_variant: str
    entry_idx: int
    stop_anchor_low: float
    signal_idx: int
    confirm_idx: int
    note: str


def parse_dt(value: str) -> datetime:
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_date(value: str) -> date:
    return date.fromisoformat(value[:10])


def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def ensure_read_only_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def connect_read_only(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute(
        "select name from sqlite_master where type='table' and name=?;",
        (table,),
    )
    return cur.fetchone() is not None


def get_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    return [row[1] for row in conn.execute(f"pragma table_info({table});").fetchall()]


def require_columns(columns: Iterable[str], required: Iterable[str], table: str) -> None:
    cols = set(columns)
    missing = [c for c in required if c not in cols]
    if missing:
        raise RuntimeError(f"Missing required columns in {table}: {missing}")


def load_h1_bars(conn: sqlite3.Connection) -> List[Bar]:
    if not table_exists(conn, "bars"):
        raise RuntimeError("Required table not found: bars")
    cols = get_columns(conn, "bars")
    require_columns(
        cols,
        ["utc_time", "open", "high", "low", "close", "source", "symbol", "timeframe"],
        "bars",
    )

    spread_select = "spread" if "spread" in cols else "null as spread"

    sql = f"""
    select
        utc_time,
        open,
        high,
        low,
        close,
        {spread_select}
    from bars
    where source = ?
      and symbol = ?
      and timeframe = ?
    order by utc_time;
    """
    rows = conn.execute(sql, (SOURCE, SYMBOL, TIMEFRAME)).fetchall()

    # Deduplicate by timestamp, keeping the last row encountered.
    by_time: Dict[datetime, Tuple[float, float, float, float, Optional[float]]] = {}
    for row in rows:
        dt = parse_dt(row[0])
        by_time[dt] = (
            float(row[1]),
            float(row[2]),
            float(row[3]),
            float(row[4]),
            safe_float(row[5]),
        )

    bars: List[Bar] = []
    for idx, dt in enumerate(sorted(by_time.keys())):
        o, h, l, c, s = by_time[dt]
        bars.append(Bar(idx=idx, utc_time=dt, open=o, high=h, low=l, close=c, spread=s))
    return bars


def load_macro_rows(conn: sqlite3.Connection) -> List[MacroRow]:
    if not table_exists(conn, "macro_daily_regime"):
        raise RuntimeError("Required table not found: macro_daily_regime")
    cols = get_columns(conn, "macro_daily_regime")
    require_columns(
        cols,
        [
            "obs_date",
            "macro_regime",
            "macro_score_long_gold",
            "d_real_yield_20d",
            "d_usd_20d_pct",
            "rate_pressure_score",
            "usd_pressure_score",
            "regime_reason",
        ],
        "macro_daily_regime",
    )

    sql = """
    select
        obs_date,
        macro_regime,
        macro_score_long_gold,
        d_real_yield_20d,
        d_usd_20d_pct,
        rate_pressure_score,
        usd_pressure_score,
        regime_reason
    from macro_daily_regime
    order by obs_date;
    """
    out: List[MacroRow] = []
    for row in conn.execute(sql).fetchall():
        out.append(
            MacroRow(
                obs_date=parse_date(row[0]),
                macro_regime=str(row[1] or ""),
                macro_score_long_gold=safe_float(row[2]),
                d_real_yield_20d=safe_float(row[3]),
                d_usd_20d_pct=safe_float(row[4]),
                rate_pressure_score=safe_float(row[5]),
                usd_pressure_score=safe_float(row[6]),
                regime_reason=str(row[7] or ""),
            )
        )
    return out


def validate_inputs(bars: List[Bar], macro_rows: List[MacroRow]) -> Dict[str, Any]:
    if len(bars) < MIN_REQUIRED_ROWS:
        raise RuntimeError(f"DATA_COVERAGE_FAIL: H1 rows {len(bars)} < {MIN_REQUIRED_ROWS}")
    min_d = bars[0].utc_time.date()
    max_d = bars[-1].utc_time.date()
    if min_d > MIN_REQUIRED_START:
        raise RuntimeError(f"DATA_COVERAGE_FAIL: min date {min_d} > {MIN_REQUIRED_START}")
    if max_d < MIN_REQUIRED_END:
        raise RuntimeError(f"DATA_COVERAGE_FAIL: max date {max_d} < {MIN_REQUIRED_END}")
    if not macro_rows:
        raise RuntimeError("MACRO_REGIME_FAIL: no macro_daily_regime rows")

    macro_labels = sorted({m.macro_regime for m in macro_rows})
    if not any(label in macro_labels for label in ("supportive", "neutral", "hostile", "mixed")):
        raise RuntimeError(f"MACRO_REGIME_FAIL: unexpected macro labels {macro_labels}")

    duplicates = 0
    gaps_gt_3h = 0
    previous: Optional[datetime] = None
    for b in bars:
        if previous is not None:
            if b.utc_time == previous:
                duplicates += 1
            if b.utc_time - previous > timedelta(hours=3):
                gaps_gt_3h += 1
        previous = b.utc_time

    return {
        "h1_rows": len(bars),
        "h1_min_utc": bars[0].utc_time.isoformat(),
        "h1_max_utc": bars[-1].utc_time.isoformat(),
        "macro_rows": len(macro_rows),
        "macro_min_date": min(m.obs_date for m in macro_rows).isoformat(),
        "macro_max_date": max(m.obs_date for m in macro_rows).isoformat(),
        "macro_labels": macro_labels,
        "duplicate_timestamps_after_dedupe": duplicates,
        "h1_gaps_gt_3h": gaps_gt_3h,
    }


def compute_atr(bars: List[Bar]) -> None:
    true_ranges: List[Optional[float]] = []
    prev_close: Optional[float] = None
    for b in bars:
        if prev_close is None:
            tr = b.high - b.low
        else:
            tr = max(
                b.high - b.low,
                abs(b.high - prev_close),
                abs(b.low - prev_close),
            )
        true_ranges.append(tr)
        prev_close = b.close

    for i, b in enumerate(bars):
        if i + 1 < ATR_PERIOD:
            continue
        window = true_ranges[i - ATR_PERIOD + 1 : i + 1]
        if any(v is None for v in window):
            continue
        b.atr_h1_14 = sum(v for v in window if v is not None) / ATR_PERIOD


def derive_d1(bars: List[Bar]) -> Dict[date, D1Row]:
    groups: Dict[date, List[Bar]] = defaultdict(list)
    for b in bars:
        groups[b.utc_time.date()].append(b)

    rows: List[D1Row] = []
    for d in sorted(groups):
        g = groups[d]
        if len(g) < D1_MIN_H1_COUNT:
            continue
        rows.append(
            D1Row(
                d=d,
                open=g[0].open,
                high=max(x.high for x in g),
                low=min(x.low for x in g),
                close=g[-1].close,
                h1_count=len(g),
                ma50=None,
            )
        )

    closes: List[float] = []
    for row in rows:
        closes.append(row.close)
        if len(closes) >= D1_MA_PERIOD:
            row.ma50 = sum(closes[-D1_MA_PERIOD:]) / D1_MA_PERIOD
    return {row.d: row for row in rows}


def h4_floor(dt: datetime) -> datetime:
    h = (dt.hour // 4) * 4
    return dt.replace(hour=h, minute=0, second=0, microsecond=0)


def derive_h4(bars: List[Bar]) -> List[H4Row]:
    groups: Dict[datetime, List[Bar]] = defaultdict(list)
    for b in bars:
        groups[h4_floor(b.utc_time)].append(b)

    rows: List[H4Row] = []
    closes: List[float] = []
    for start in sorted(groups):
        g = groups[start]
        if len(g) < H4_MIN_H1_COUNT:
            continue
        row = H4Row(
            start=start,
            end=start + timedelta(hours=4),
            open=g[0].open,
            high=max(x.high for x in g),
            low=min(x.low for x in g),
            close=g[-1].close,
            h1_count=len(g),
            ma50=None,
        )
        closes.append(row.close)
        if len(closes) >= H4_MA_PERIOD:
            row.ma50 = sum(closes[-H4_MA_PERIOD:]) / H4_MA_PERIOD
        rows.append(row)
    return rows


def attach_derived_fields(bars: List[Bar], d1: Dict[date, D1Row], h4_rows: List[H4Row]) -> None:
    valid_dates = sorted(d1.keys())

    # D1 previous completed day and previous day high.
    for b in bars:
        pos = bisect_right(valid_dates, b.utc_time.date()) - 1
        # Use strictly previous date for daily structure and previous_day_high.
        while pos >= 0 and valid_dates[pos] >= b.utc_time.date():
            pos -= 1
        if pos >= 0:
            drow = d1[valid_dates[pos]]
            b.previous_day_high = drow.high
            b.d1_close = drow.close
            b.d1_ma50 = drow.ma50

    # rolling 48h high, excluding current bar.
    highs: List[float] = []
    for i, b in enumerate(bars):
        if i >= ROLLING_48H_LOOKBACK:
            b.rolling_48h_high = max(highs[i - ROLLING_48H_LOOKBACK : i])
        highs.append(b.high)

    # H4 latest completed bar. Use signal close time = H1 open + 1 hour.
    h4_ends = [row.end for row in h4_rows]
    for b in bars:
        signal_close_time = b.utc_time + timedelta(hours=1)
        pos = bisect_right(h4_ends, signal_close_time) - 1
        if pos >= 0:
            hrow = h4_rows[pos]
            b.h4_close = hrow.close
            b.h4_ma50 = hrow.ma50


def attach_macro(bars: List[Bar], macro_rows: List[MacroRow]) -> None:
    macro_dates = [m.obs_date for m in macro_rows]
    for b in bars:
        d = b.utc_time.date()
        pos = bisect_right(macro_dates, d) - 1
        if pos < 0:
            continue
        m = macro_rows[pos]
        if (d - m.obs_date).days > MAX_MACRO_FFILL_DAYS:
            continue
        b.macro_regime = m.macro_regime
        b.macro_score_long_gold = m.macro_score_long_gold
        b.d_real_yield_20d = m.d_real_yield_20d
        b.d_usd_20d_pct = m.d_usd_20d_pct
        b.regime_reason = m.regime_reason


def is_macro_permitted(b: Bar) -> Tuple[bool, str]:
    regime = (b.macro_regime or "").lower()
    if regime == "supportive":
        return True, "supportive"
    if regime == "neutral":
        score_ok = b.macro_score_long_gold is not None and b.macro_score_long_gold >= 0
        real_ok = b.d_real_yield_20d is not None and b.d_real_yield_20d <= 0
        usd_ok = b.d_usd_20d_pct is not None and b.d_usd_20d_pct <= 0
        if score_ok and (real_ok or usd_ok):
            return True, "neutral_non_hostile"
    return False, regime or "missing_macro"


def is_structure_permitted(b: Bar) -> bool:
    if b.d1_close is None or b.d1_ma50 is None:
        return False
    if b.h4_close is None or b.h4_ma50 is None:
        return False
    return b.d1_close > b.d1_ma50 and b.h4_close > b.h4_ma50


def is_blocked_entry_window(dt: datetime) -> bool:
    # Python: Monday=0 ... Sunday=6
    weekday = dt.weekday()
    hour = dt.hour
    is_sunday_block = weekday == 6 and hour in (22, 23)
    is_monday_block = weekday == 0 and hour in (0, 1)
    return is_sunday_block or is_monday_block


def has_large_gap_in_window(bars: List[Bar], start_idx: int, end_idx: int) -> bool:
    for i in range(start_idx + 1, end_idx + 1):
        if bars[i].utc_time - bars[i - 1].utc_time > timedelta(hours=3):
            return True
    return False


def get_level(b: Bar, level_variant: str) -> Optional[float]:
    if level_variant == "previous_day_high":
        return b.previous_day_high
    if level_variant == "rolling_48h_high":
        return b.rolling_48h_high
    raise ValueError(f"Unknown level_variant: {level_variant}")


def signal_close_position_ratio(b: Bar) -> Optional[float]:
    rng = b.high - b.low
    if rng <= 0:
        return None
    return (b.close - b.low) / rng


def plan_entry(
    bars: List[Bar],
    i: int,
    entry_variant: str,
    level: float,
    atr: float,
) -> Optional[PlannedEntry]:
    b0 = bars[i]

    if entry_variant == "V1_CLOSE_ACCEPTANCE":
        ratio = signal_close_position_ratio(b0)
        if ratio is None or b0.close <= level or ratio < 0.50:
            return None
        entry_idx = i + 1
        if entry_idx >= len(bars):
            return None
        return PlannedEntry(
            entry_variant=entry_variant,
            entry_idx=entry_idx,
            stop_anchor_low=b0.low,
            signal_idx=i,
            confirm_idx=i,
            note="close_acceptance",
        )

    if entry_variant == "V2_RETEST_CONFIRMATION":
        if b0.close <= level:
            return None
        for j in range(i + 1, min(i + 1 + RETEST_MAX_BARS, len(bars) - 1) + 1):
            bj = bars[j]
            if bj.low <= level + RETEST_TOLERANCE_ATR * atr and bj.close > level:
                entry_idx = j + 1
                if entry_idx >= len(bars):
                    return None
                return PlannedEntry(
                    entry_variant=entry_variant,
                    entry_idx=entry_idx,
                    stop_anchor_low=bj.low,
                    signal_idx=i,
                    confirm_idx=j,
                    note=f"retest_confirmed_at_{bj.utc_time.isoformat()}",
                )
        return None

    if entry_variant == "V3_STRICT_NEXT_BAR_HOLD":
        if i + 2 >= len(bars):
            return None
        b1 = bars[i + 1]
        if b0.close <= level:
            return None
        if b1.close < level:
            return None
        return PlannedEntry(
            entry_variant=entry_variant,
            entry_idx=i + 2,
            stop_anchor_low=min(b0.low, b1.low),
            signal_idx=i,
            confirm_idx=i + 1,
            note="strict_next_bar_hold",
        )

    raise ValueError(f"Unknown entry_variant: {entry_variant}")


def simulate_exit(
    bars: List[Bar],
    entry_idx: int,
    entry_price: float,
    stop_price: float,
    target_price: float,
) -> Tuple[str, int, float, float]:
    """
    Conservative H1 sequencing:
    If both stop and target are touched in the same H1 bar, count stop first.
    Returns: exit_reason, exit_idx, exit_price, gross_R_directional_price_diff
    """
    stop_distance = entry_price - stop_price
    max_exit_idx = entry_idx + TIME_STOP_H1_BARS - 1
    if max_exit_idx >= len(bars):
        raise RuntimeError("Not enough bars for time stop simulation")

    for j in range(entry_idx, max_exit_idx + 1):
        bj = bars[j]
        stop_touched = bj.low <= stop_price
        target_touched = bj.high >= target_price
        if stop_touched:
            return "SL", j, stop_price, stop_price - entry_price
        if target_touched:
            return "TP", j, target_price, target_price - entry_price

    bj = bars[max_exit_idx]
    return "TIME", max_exit_idx, bj.close, bj.close - entry_price


def profit_factor(values: List[float]) -> float:
    wins = sum(v for v in values if v > 0)
    losses = -sum(v for v in values if v < 0)
    if losses == 0:
        if wins > 0:
            return float("inf")
        return 0.0
    return wins / losses


def max_drawdown(values: List[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for v in values:
        equity += v
        peak = max(peak, equity)
        dd = peak - equity
        max_dd = max(max_dd, dd)
    return max_dd


def percentile(values: List[float], p: float) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    rank = (len(s) - 1) * p
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return s[int(rank)]
    frac = rank - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def clean_number(v: Any) -> Any:
    if isinstance(v, float):
        if math.isinf(v):
            return "inf"
        if math.isnan(v):
            return ""
        return round(v, 8)
    return v


def variant_id(entry_variant: str, level_variant: str, target_name: str) -> str:
    return f"{entry_variant}__{level_variant}__{target_name}__{TIME_VARIANT}"


def generate_trades(bars: List[Bar]) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, int]]]:
    trades: List[Dict[str, Any]] = []
    skip_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for i, b in enumerate(bars):
        atr = b.atr_h1_14
        if atr is None or atr <= 0:
            continue

        for level_variant in LEVEL_VARIANTS:
            level = get_level(b, level_variant)
            if level is None:
                continue

            if b.high <= level:
                continue

            sweep_distance = b.high - level
            if sweep_distance < MIN_SWEEP_ATR * atr:
                continue

            signal_range = b.high - b.low
            signal_range_atr_ratio = signal_range / atr if atr > 0 else None
            if signal_range_atr_ratio is None or signal_range_atr_ratio > MAX_SIGNAL_RANGE_ATR:
                for entry_variant in ENTRY_VARIANTS:
                    for target_name, _ in TARGET_VARIANTS:
                        skip_counts[variant_id(entry_variant, level_variant, target_name)]["large_signal_skipped"] += 1
                continue

            macro_ok, macro_bucket = is_macro_permitted(b)
            if not macro_ok:
                for entry_variant in ENTRY_VARIANTS:
                    for target_name, _ in TARGET_VARIANTS:
                        skip_counts[variant_id(entry_variant, level_variant, target_name)]["macro_skipped"] += 1
                continue

            if not is_structure_permitted(b):
                for entry_variant in ENTRY_VARIANTS:
                    for target_name, _ in TARGET_VARIANTS:
                        skip_counts[variant_id(entry_variant, level_variant, target_name)]["structure_skipped"] += 1
                continue

            for entry_variant in ENTRY_VARIANTS:
                planned = plan_entry(bars, i, entry_variant, level, atr)
                if planned is None:
                    for target_name, _ in TARGET_VARIANTS:
                        skip_counts[variant_id(entry_variant, level_variant, target_name)]["entry_condition_skipped"] += 1
                    continue

                entry_idx = planned.entry_idx
                entry_bar = bars[entry_idx]
                if is_blocked_entry_window(entry_bar.utc_time):
                    for target_name, _ in TARGET_VARIANTS:
                        skip_counts[variant_id(entry_variant, level_variant, target_name)]["blocked_window_skipped"] += 1
                    continue

                max_exit_idx = entry_idx + TIME_STOP_H1_BARS - 1
                if max_exit_idx >= len(bars):
                    for target_name, _ in TARGET_VARIANTS:
                        skip_counts[variant_id(entry_variant, level_variant, target_name)]["not_enough_future_bars_skipped"] += 1
                    continue

                if has_large_gap_in_window(bars, entry_idx, max_exit_idx):
                    for target_name, _ in TARGET_VARIANTS:
                        skip_counts[variant_id(entry_variant, level_variant, target_name)]["weekend_or_large_gap_skipped"] += 1
                    continue

                entry_price = entry_bar.open
                stop_price = planned.stop_anchor_low - STOP_BUFFER_ATR * atr
                stop_distance = entry_price - stop_price

                stop_distance_atr_ratio = stop_distance / atr if atr > 0 else None
                if (
                    stop_distance <= 0
                    or stop_distance_atr_ratio is None
                    or stop_distance_atr_ratio < MIN_STOP_ATR
                    or stop_distance_atr_ratio > MAX_STOP_ATR
                ):
                    for target_name, _ in TARGET_VARIANTS:
                        skip_counts[variant_id(entry_variant, level_variant, target_name)]["invalid_stop_skipped"] += 1
                    continue

                for target_name, target_r in TARGET_VARIANTS:
                    vid = variant_id(entry_variant, level_variant, target_name)
                    target_price = entry_price + target_r * stop_distance
                    try:
                        exit_reason, exit_idx, exit_price_raw, gross_price_diff = simulate_exit(
                            bars=bars,
                            entry_idx=entry_idx,
                            entry_price=entry_price,
                            stop_price=stop_price,
                            target_price=target_price,
                        )
                    except RuntimeError:
                        skip_counts[vid]["not_enough_future_bars_skipped"] += 1
                        continue

                    gross_r = gross_price_diff / stop_distance
                    cost_r_values = {}
                    for cost_name, spread_price in SPREAD_PRICE_COSTS.items():
                        # Conservative one-full-spread-equivalent penalty against bid-chart gross result.
                        cost_r = spread_price / stop_distance if stop_distance > 0 else 0.0
                        cost_r_values[cost_name] = gross_r - cost_r

                    trade_id = f"{vid}__{b.utc_time.strftime('%Y%m%dT%H%M%SZ')}__{len(trades)+1:06d}"
                    trades.append(
                        {
                            "trade_id": trade_id,
                            "variant_id": vid,
                            "entry_variant": entry_variant,
                            "level_variant": level_variant,
                            "target_variant": target_name,
                            "time_variant": TIME_VARIANT,
                            "signal_utc": b.utc_time.isoformat(),
                            "entry_utc": entry_bar.utc_time.isoformat(),
                            "exit_utc": bars[exit_idx].utc_time.isoformat(),
                            "source": SOURCE,
                            "symbol": SYMBOL,
                            "timeframe": TIMEFRAME,
                            "macro_regime": b.macro_regime or "",
                            "macro_bucket": macro_bucket,
                            "macro_score_long_gold": b.macro_score_long_gold,
                            "d_real_yield_20d": b.d_real_yield_20d,
                            "d_usd_20d_pct": b.d_usd_20d_pct,
                            "d1_close": b.d1_close,
                            "d1_ma50": b.d1_ma50,
                            "h4_close": b.h4_close,
                            "h4_ma50": b.h4_ma50,
                            "atr_h1_14": atr,
                            "reference_level": level,
                            "sweep_distance": sweep_distance,
                            "entry_price": entry_price,
                            "stop_price": stop_price,
                            "target_price": target_price,
                            "stop_distance": stop_distance,
                            "exit_reason": exit_reason,
                            "exit_price_raw": exit_price_raw,
                            "r_gross": gross_r,
                            "r_base_p50": cost_r_values["base_p50"],
                            "r_normal_p75": cost_r_values["normal_p75"],
                            "r_stress_p90": cost_r_values["stress_p90"],
                            "r_high_p95": cost_r_values["high_p95"],
                            "r_tail_p99": cost_r_values["tail_p99"],
                            "blocked_window_flag": False,
                            "event_guard_flag": "limited",
                            "signal_range_atr_ratio": signal_range_atr_ratio,
                            "stop_distance_atr_ratio": stop_distance_atr_ratio,
                            "confirm_utc": bars[planned.confirm_idx].utc_time.isoformat(),
                            "notes": planned.note,
                        }
                    )

    return trades, skip_counts


def summarize_variant(trades: List[Dict[str, Any]], skip_counts: Dict[str, Dict[str, int]]) -> List[Dict[str, Any]]:
    by_variant: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for t in trades:
        by_variant[t["variant_id"]].append(t)

    all_variant_ids = [
        variant_id(entry, level, target)
        for level in LEVEL_VARIANTS
        for entry in ENTRY_VARIANTS
        for target, _ in TARGET_VARIANTS
    ]

    rows: List[Dict[str, Any]] = []
    for vid in all_variant_ids:
        ts = by_variant.get(vid, [])
        if ts:
            first = ts[0]
            entry_variant = first["entry_variant"]
            level_variant = first["level_variant"]
            target_variant = first["target_variant"]
            time_variant = first["time_variant"]
        else:
            parts = vid.split("__")
            entry_variant = parts[0]
            level_variant = parts[1]
            target_variant = parts[2]
            time_variant = TIME_VARIANT

        r_gross = [float(t["r_gross"]) for t in ts]
        r_base = [float(t["r_base_p50"]) for t in ts]
        r_p90 = [float(t["r_stress_p90"]) for t in ts]
        r_p95 = [float(t["r_high_p95"]) for t in ts]
        r_p99 = [float(t["r_tail_p99"]) for t in ts]

        gross_pf = profit_factor(r_gross) if r_gross else 0.0
        base_pf = profit_factor(r_base) if r_base else 0.0
        p90_pf = profit_factor(r_p90) if r_p90 else 0.0
        p95_pf = profit_factor(r_p95) if r_p95 else 0.0
        p99_pf = profit_factor(r_p99) if r_p99 else 0.0

        cost_sensitivity = None
        if gross_pf not in (0.0, float("inf")) and isinstance(gross_pf, float):
            cost_sensitivity = p90_pf / gross_pf if math.isfinite(gross_pf) else None

        macro_counts = defaultdict(int)
        for t in ts:
            macro_counts[t.get("macro_bucket") or t.get("macro_regime") or "unknown"] += 1

        permitted_count = macro_counts["supportive"] + macro_counts["neutral_non_hostile"]
        permitted_share = permitted_count / len(ts) if ts else 0.0

        avg_p90 = sum(r_p90) / len(r_p90) if r_p90 else 0.0
        avg_gross = sum(r_gross) / len(r_gross) if r_gross else 0.0
        win_rate_gross = sum(1 for v in r_gross if v > 0) / len(r_gross) if r_gross else 0.0
        win_rate_p90 = sum(1 for v in r_p90 if v > 0) / len(r_p90) if r_p90 else 0.0

        decision = "KILL"
        status = "FAIL"
        if (
            len(ts) >= 50
            and p90_pf >= 1.10
            and avg_p90 > 0
            and (cost_sensitivity is not None and cost_sensitivity >= 0.70)
            and permitted_share >= 0.90
        ):
            decision = "PASS_RESEARCH_INTEREST"
            status = "PASS"
        elif len(ts) >= 25 and p90_pf >= 1.00 and avg_p90 > 0:
            decision = "WATCHLIST"
            status = "WATCH"

        sc = skip_counts.get(vid, {})
        rows.append(
            {
                "variant_id": vid,
                "entry_variant": entry_variant,
                "level_variant": level_variant,
                "target_variant": target_variant,
                "time_variant": time_variant,
                "trade_count": len(ts),
                "gross_pf": gross_pf,
                "base_p50_pf": base_pf,
                "stress_p90_pf": p90_pf,
                "high_p95_pf": p95_pf,
                "tail_p99_pf": p99_pf,
                "avg_R_gross": avg_gross,
                "avg_R_p90": avg_p90,
                "win_rate_gross": win_rate_gross,
                "win_rate_p90": win_rate_p90,
                "max_drawdown_R_p90": max_drawdown(r_p90) if r_p90 else 0.0,
                "median_R_p90": percentile(r_p90, 0.50),
                "p10_R_p90": percentile(r_p90, 0.10),
                "p90_R_p90": percentile(r_p90, 0.90),
                "cost_sensitivity_ratio": cost_sensitivity,
                "supportive_trades": macro_counts["supportive"],
                "neutral_non_hostile_trades": macro_counts["neutral_non_hostile"],
                "hostile_trades": macro_counts["hostile"],
                "mixed_trades": macro_counts["mixed"],
                "missing_macro_trades": macro_counts["missing_macro"],
                "blocked_window_skipped": sc.get("blocked_window_skipped", 0),
                "event_guard_skipped": sc.get("event_guard_skipped", 0),
                "invalid_stop_skipped": sc.get("invalid_stop_skipped", 0),
                "large_signal_skipped": sc.get("large_signal_skipped", 0),
                "macro_skipped": sc.get("macro_skipped", 0),
                "structure_skipped": sc.get("structure_skipped", 0),
                "entry_condition_skipped": sc.get("entry_condition_skipped", 0),
                "weekend_or_large_gap_skipped": sc.get("weekend_or_large_gap_skipped", 0),
                "status": status,
                "decision": decision,
            }
        )

    rows.sort(
        key=lambda r: (
            0 if r["decision"] == "PASS_RESEARCH_INTEREST" else 1 if r["decision"] == "WATCHLIST" else 2,
            -(r["stress_p90_pf"] if isinstance(r["stress_p90_pf"], float) and math.isfinite(r["stress_p90_pf"]) else 9999.0),
        )
    )
    return rows


def split_metrics(trades: List[Dict[str, Any]], key: str, value_field: str = "r_stress_p90") -> List[Dict[str, Any]]:
    groups: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    for t in trades:
        groups[(t["variant_id"], str(t.get(key, "")))].append(float(t[value_field]))
    rows = []
    for (vid, group_value), vals in sorted(groups.items()):
        rows.append(
            {
                "variant_id": vid,
                key: group_value,
                "trade_count": len(vals),
                "pf": profit_factor(vals),
                "avg_R": sum(vals) / len(vals) if vals else 0.0,
                "win_rate": sum(1 for v in vals if v > 0) / len(vals) if vals else 0.0,
                "max_drawdown_R": max_drawdown(vals),
            }
        )
    return rows


def monthly_metrics(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    for t in trades:
        month = t["entry_utc"][:7]
        groups[(t["variant_id"], month)].append(float(t["r_stress_p90"]))
    rows = []
    for (vid, month), vals in sorted(groups.items()):
        rows.append(
            {
                "variant_id": vid,
                "yyyy_mm": month,
                "trade_count": len(vals),
                "pf_p90": profit_factor(vals),
                "avg_R_p90": sum(vals) / len(vals) if vals else 0.0,
                "win_rate_p90": sum(1 for v in vals if v > 0) / len(vals) if vals else 0.0,
            }
        )
    return rows


def yearly_metrics(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    for t in trades:
        year = t["entry_utc"][:4]
        groups[(t["variant_id"], year)].append(float(t["r_stress_p90"]))
    rows = []
    for (vid, year), vals in sorted(groups.items()):
        rows.append(
            {
                "variant_id": vid,
                "yyyy": year,
                "trade_count": len(vals),
                "pf_p90": profit_factor(vals),
                "avg_R_p90": sum(vals) / len(vals) if vals else 0.0,
                "win_rate_p90": sum(1 for v in vals if v > 0) / len(vals) if vals else 0.0,
            }
        )
    return rows


def diagnostics_rows(variant_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for r in variant_rows:
        reasons = []
        if r["trade_count"] < 50:
            reasons.append("low_trade_count")
        if isinstance(r["stress_p90_pf"], float) and r["stress_p90_pf"] < 1.10:
            reasons.append("p90_pf_below_research_threshold")
        if isinstance(r["avg_R_p90"], float) and r["avg_R_p90"] <= 0:
            reasons.append("avg_R_p90_non_positive")
        csr = r.get("cost_sensitivity_ratio")
        if csr is None or (isinstance(csr, float) and csr < 0.70):
            reasons.append("cost_sensitive_or_unresolved")
        if r["decision"] == "PASS_RESEARCH_INTEREST":
            reasons.append("research_interest_only_not_stage39")
        rows.append(
            {
                "variant_id": r["variant_id"],
                "decision": r["decision"],
                "diagnostic_flags": ";".join(reasons),
                "stage39_status": "NO_GO",
                "execution_authorization": "NO_EA_NO_PAPER_NO_LIVE_NO_ORDER",
            }
        )
    return rows


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as f:
        if not fieldnames:
            f.write("")
            return
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: clean_number(row.get(k, "")) for k in fieldnames})


def write_json(path: Path, data: Dict[str, Any]) -> None:
    def default(obj: Any) -> Any:
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, float):
            if math.isinf(obj):
                return "inf"
            if math.isnan(obj):
                return None
        return str(obj)

    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=default), encoding="utf-8")


def markdown_report(
    summary: Dict[str, Any],
    validation: Dict[str, Any],
    variant_rows: List[Dict[str, Any]],
) -> str:
    best = variant_rows[0] if variant_rows else None
    pass_count = sum(1 for r in variant_rows if r["decision"] == "PASS_RESEARCH_INTEREST")
    watch_count = sum(1 for r in variant_rows if r["decision"] == "WATCHLIST")
    kill_count = sum(1 for r in variant_rows if r["decision"] == "KILL")

    lines = []
    lines.append("# Stage38A T1 Read-only Test Report")
    lines.append("")
    lines.append("چپ‌چین ادامه می‌دهم.")
    lines.append("")
    lines.append("## Executive Decision")
    lines.append("")
    lines.append("```text")
    lines.append("T1_READ_ONLY_TEST = COMPLETED")
    lines.append(f"PASS_RESEARCH_INTEREST_COUNT = {pass_count}")
    lines.append(f"WATCHLIST_COUNT = {watch_count}")
    lines.append(f"KILL_COUNT = {kill_count}")
    lines.append("STAGE39 = NO_GO")
    lines.append("EA_PAPER_LIVE_ORDER = NO_GO")
    lines.append("```")
    lines.append("")
    lines.append("## Data Coverage")
    lines.append("")
    lines.append("```text")
    for k in ["h1_rows", "h1_min_utc", "h1_max_utc", "macro_rows", "macro_min_date", "macro_max_date", "h1_gaps_gt_3h"]:
        lines.append(f"{k} = {validation.get(k)}")
    lines.append("```")
    lines.append("")
    lines.append("## Cost Model")
    lines.append("")
    lines.append("```text")
    lines.append("POINT = 0.01")
    lines.append("COST_UNIT = price_distance derived from spread_points")
    for k, v in SPREAD_COSTS.items():
        lines.append(f"{k}: {v} points -> {SPREAD_PRICE_COSTS[k]:.4f} price units")
    lines.append("```")
    lines.append("")
    lines.append("## Best Variant by Decision/P90 PF")
    lines.append("")
    if best:
        lines.append("```text")
        for k in [
            "variant_id",
            "trade_count",
            "gross_pf",
            "base_p50_pf",
            "stress_p90_pf",
            "avg_R_p90",
            "win_rate_p90",
            "max_drawdown_R_p90",
            "cost_sensitivity_ratio",
            "decision",
        ]:
            lines.append(f"{k} = {clean_number(best.get(k))}")
        lines.append("```")
    else:
        lines.append("No trades generated.")
    lines.append("")
    lines.append("## Variant Metrics")
    lines.append("")
    lines.append("| variant_id | trades | p90_pf | avg_R_p90 | win_rate_p90 | decision |")
    lines.append("|---|---:|---:|---:|---:|---|")
    for r in variant_rows:
        lines.append(
            f"| {r['variant_id']} | {r['trade_count']} | {clean_number(r['stress_p90_pf'])} | "
            f"{clean_number(r['avg_R_p90'])} | {clean_number(r['win_rate_p90'])} | {r['decision']} |"
        )
    lines.append("")
    lines.append("## Required Warning")
    lines.append("")
    lines.append("```text")
    lines.append("This is read-only research output.")
    lines.append("It does not authorize Stage39.")
    lines.append("It does not authorize EA, paper-live, live execution, or orders.")
    lines.append("```")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage38A T1 read-only test")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to local SQLite store")
    parser.add_argument("--out", default=DEFAULT_OUT_DIR, help="Output report directory")
    args = parser.parse_args()

    repo = Path.cwd()
    db_path = Path(args.db)
    out_dir = Path(args.out)
    ensure_read_only_output_dir(out_dir)

    generated_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    if not db_path.exists():
        raise RuntimeError(f"Input DB not found: {db_path}")

    with connect_read_only(db_path) as conn:
        bars = load_h1_bars(conn)
        macro_rows = load_macro_rows(conn)

    validation = validate_inputs(bars, macro_rows)
    compute_atr(bars)
    d1 = derive_d1(bars)
    h4_rows = derive_h4(bars)
    attach_derived_fields(bars, d1, h4_rows)
    attach_macro(bars, macro_rows)

    trades, skip_counts = generate_trades(bars)
    variant_rows = summarize_variant(trades, skip_counts)
    regime_rows = split_metrics(trades, "macro_bucket")
    cost_rows = []
    for r in variant_rows:
        cost_rows.append(
            {
                "variant_id": r["variant_id"],
                "gross_pf": r["gross_pf"],
                "base_p50_pf": r["base_p50_pf"],
                "stress_p90_pf": r["stress_p90_pf"],
                "high_p95_pf": r["high_p95_pf"],
                "tail_p99_pf": r["tail_p99_pf"],
                "cost_sensitivity_ratio": r["cost_sensitivity_ratio"],
            }
        )
    diag_rows = diagnostics_rows(variant_rows)
    monthly_rows = monthly_metrics(trades)
    yearly_rows = yearly_metrics(trades)

    pass_count = sum(1 for r in variant_rows if r["decision"] == "PASS_RESEARCH_INTEREST")
    watch_count = sum(1 for r in variant_rows if r["decision"] == "WATCHLIST")
    kill_count = sum(1 for r in variant_rows if r["decision"] == "KILL")
    best = variant_rows[0] if variant_rows else None

    summary = {
        "stage": STAGE,
        "script": SCRIPT_NAME,
        "generated_utc": generated_utc,
        "execution_authorization": "NO_EA_NO_PAPER_NO_LIVE_NO_ORDER",
        "stage39_status": "NO_GO",
        "input_db": str(db_path),
        "price_source": SOURCE,
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "variant_count": len(variant_rows),
        "trade_count_total": len(trades),
        "pass_research_interest_count": pass_count,
        "watchlist_count": watch_count,
        "kill_count": kill_count,
        "best_variant_by_stress_p90": best["variant_id"] if best else None,
        "cost_unit": "price_distance_derived_from_spread_points",
        "point": POINT,
        "digits": DIGITS,
        "contract_size": CONTRACT_SIZE,
        "usd_pnl_conversion_resolved": False,
        "decision": "RESEARCH_ONLY_NO_STAGE39",
        "report_dir": str(out_dir),
    }

    write_json(out_dir / "stage38a_t1_summary.json", summary)

    trade_fields = [
        "trade_id",
        "variant_id",
        "entry_variant",
        "level_variant",
        "target_variant",
        "time_variant",
        "signal_utc",
        "entry_utc",
        "exit_utc",
        "source",
        "symbol",
        "timeframe",
        "macro_regime",
        "macro_bucket",
        "macro_score_long_gold",
        "d_real_yield_20d",
        "d_usd_20d_pct",
        "d1_close",
        "d1_ma50",
        "h4_close",
        "h4_ma50",
        "atr_h1_14",
        "reference_level",
        "sweep_distance",
        "entry_price",
        "stop_price",
        "target_price",
        "stop_distance",
        "exit_reason",
        "exit_price_raw",
        "r_gross",
        "r_base_p50",
        "r_normal_p75",
        "r_stress_p90",
        "r_high_p95",
        "r_tail_p99",
        "blocked_window_flag",
        "event_guard_flag",
        "signal_range_atr_ratio",
        "stop_distance_atr_ratio",
        "confirm_utc",
        "notes",
    ]
    write_csv(out_dir / "stage38a_t1_trade_ledger.csv", trades, trade_fields)

    variant_fields = [
        "variant_id",
        "entry_variant",
        "level_variant",
        "target_variant",
        "time_variant",
        "trade_count",
        "gross_pf",
        "base_p50_pf",
        "stress_p90_pf",
        "high_p95_pf",
        "tail_p99_pf",
        "avg_R_gross",
        "avg_R_p90",
        "win_rate_gross",
        "win_rate_p90",
        "max_drawdown_R_p90",
        "median_R_p90",
        "p10_R_p90",
        "p90_R_p90",
        "cost_sensitivity_ratio",
        "supportive_trades",
        "neutral_non_hostile_trades",
        "hostile_trades",
        "mixed_trades",
        "missing_macro_trades",
        "blocked_window_skipped",
        "event_guard_skipped",
        "invalid_stop_skipped",
        "large_signal_skipped",
        "macro_skipped",
        "structure_skipped",
        "entry_condition_skipped",
        "weekend_or_large_gap_skipped",
        "status",
        "decision",
    ]
    write_csv(out_dir / "stage38a_t1_variant_metrics.csv", variant_rows, variant_fields)
    write_csv(out_dir / "stage38a_t1_regime_split.csv", regime_rows)
    write_csv(out_dir / "stage38a_t1_cost_sensitivity.csv", cost_rows)
    write_csv(out_dir / "stage38a_t1_diagnostics.csv", diag_rows)
    write_csv(out_dir / "stage38a_t1_monthly_metrics.csv", monthly_rows)
    write_csv(out_dir / "stage38a_t1_yearly_metrics.csv", yearly_rows)

    md = markdown_report(summary, validation, variant_rows)
    (out_dir / "stage38a_t1_read_only_test.md").write_text(md, encoding="utf-8")

    print("STAGE38A_T1_READ_ONLY_TEST_DONE")
    print(f"REPORT_DIR={out_dir}")
    print(f"TRADE_COUNT={len(trades)}")
    print(f"PASS_RESEARCH_INTEREST_COUNT={pass_count}")
    print(f"WATCHLIST_COUNT={watch_count}")
    print(f"KILL_COUNT={kill_count}")
    print("STAGE39=NO_GO")
    print("EA_PAPER_LIVE_ORDER=NO_GO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
