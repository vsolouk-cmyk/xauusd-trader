#!/usr/bin/env python3
"""
Stage38C Asia Range Targeted Filter Diagnostic

Purpose
-------
Read-only diagnostic for the restricted Stage38C lead candidate:

    C1_ASIA_RANGE_BREAKOUT_24H

This script does NOT create a trading strategy, does NOT optimize freely, and
does NOT create any paper/live execution path. It evaluates a small set of
pre-declared diagnostic cuts around the Asia range breakout candidate:

    - direction: LONG vs SHORT
    - COT annotation / extreme positioning
    - Asia session range size
    - pre-entry H1 ATR / price volatility
    - breakout hour / timing
    - breakout extension beyond the Asia range

The main decision layer is event-clock policy evaluation:
skipped events are counted as zero-return events, so filters cannot look good
only because weak windows were removed from the denominator.

Expected input tables
---------------------
- stage38c_candidate_spec_events
- bars

Expected output tables
----------------------
- stage38c_asia_targeted_filter_events
- stage38c_asia_targeted_filter_summary
- stage38c_asia_targeted_filter_audit

Default candidate:
- C1_ASIA_RANGE_BREAKOUT_24H

Default bar source/symbol/timeframe:
- amarkets_mt5 / XAUUSD / 1h

Status
------
Read-only research diagnostic. Stage39, EA, paper-live, and live order remain NO-GO.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


TIMESTAMP_CANDIDATES = [
    "entry_ts_utc",
    "event_ts_utc",
    "signal_ts_utc",
    "bar_ts_utc",
    "ts_utc",
    "timestamp_utc",
    "datetime_utc",
    "utc_time",
    "time_utc",
    "open_time_utc",
    "open_time",
    "timestamp",
    "datetime",
    "time",
    "ts",
]

NET_BPS_CANDIDATES = [
    "net_bps",
    "return_net_bps",
    "event_net_bps",
    "net_return_bps",
    "r_net_bps",
]

GROSS_BPS_CANDIDATES = [
    "gross_bps",
    "return_gross_bps",
    "raw_bps",
    "event_gross_bps",
    "gross_return_bps",
]

COST_BPS_CANDIDATES = [
    "cost_bps",
    "total_cost_bps",
    "stress_cost_bps",
    "spread_cost_bps",
    "execution_cost_bps",
]

DIRECTION_CANDIDATES = [
    "direction_label",
    "direction",
    "side",
    "signal_side",
    "trade_side",
]

CANDIDATE_ID_CANDIDATES = [
    "candidate_id",
    "candidate",
    "strategy_id",
]

BASELINE_NAME_CANDIDATES = [
    "baseline_name",
    "name",
]

HORIZON_CANDIDATES = [
    "horizon_bars",
    "horizon",
]

COT_STATE_CANDIDATES = [
    "cot_state",
    "mm_state",
    "managed_money_state",
]

PRICE_CANDIDATES = [
    "entry_price",
    "event_price",
    "signal_price",
    "close",
    "price",
]

BAR_TS_CANDIDATES = [
    "utc_time",
    "ts_utc",
    "timestamp_utc",
    "datetime_utc",
    "bar_ts_utc",
    "time_utc",
    "open_time_utc",
    "open_time",
    "timestamp",
    "datetime",
    "time",
    "ts",
]

BAR_OPEN_CANDIDATES = ["open", "o"]
BAR_HIGH_CANDIDATES = ["high", "h"]
BAR_LOW_CANDIDATES = ["low", "l"]
BAR_CLOSE_CANDIDATES = ["close", "c"]


EXTREME_COT_STATES = {"MM_EXTREME_LONG", "MM_EXTREME_SHORT"}


@dataclass
class EventRow:
    source_rowid: int
    candidate_id: str
    baseline_name: str
    horizon_bars: int
    ts_utc: str
    dt_utc: dt.datetime
    year: int
    month: str
    direction_label: str
    cot_state: str
    net_bps: float
    gross_bps: Optional[float]
    cost_bps: Optional[float]
    entry_price: Optional[float]

    # Derived market-context fields
    asia_date: str = ""
    asia_range_bps: Optional[float] = None
    asia_high: Optional[float] = None
    asia_low: Optional[float] = None
    asia_mid: Optional[float] = None
    pre_entry_atr_bps: Optional[float] = None
    breakout_hour_utc: Optional[int] = None
    breakout_extension_bps: Optional[float] = None
    range_bucket: str = "RANGE_UNKNOWN"
    atr_bucket: str = "ATR_UNKNOWN"
    breakout_hour_bucket: str = "HOUR_UNKNOWN"
    breakout_extension_bucket: str = "EXT_UNKNOWN"


@dataclass
class BarRow:
    ts_utc: str
    dt_utc: dt.datetime
    open: float
    high: float
    low: float
    close: float


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_ts(value: Any) -> str:
    if value is None:
        raise ValueError("timestamp is None")
    s = str(value).strip()
    if not s:
        raise ValueError("timestamp is empty")
    s = s.replace(" ", "T")
    if s.endswith("+00:00"):
        s = s[:-6] + "Z"
    if s.endswith("z"):
        s = s[:-1] + "Z"
    if not s.endswith("Z"):
        s = s + "Z"
    return s


def parse_ts(value: Any) -> dt.datetime:
    s = normalize_ts(value)
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(dt.timezone.utc).replace(tzinfo=None)


def table_columns(con: sqlite3.Connection, table: str) -> List[str]:
    try:
        rows = con.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall()
    except sqlite3.OperationalError as exc:
        raise RuntimeError(f"Cannot inspect table {table!r}: {exc}") from exc
    if not rows:
        raise RuntimeError(f"Table {table!r} does not exist or has no columns.")
    return [str(r[1]) for r in rows]


def quote_ident(name: str) -> str:
    if not name or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for ch in name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return '"' + name + '"'


def detect_column(cols: Sequence[str], candidates: Sequence[str], required: bool = True, label: str = "column") -> Optional[str]:
    lower_map = {c.lower(): c for c in cols}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    if required:
        raise RuntimeError(
            f"Cannot detect {label}. Tried: {', '.join(candidates)}. Existing columns: {', '.join(cols)}"
        )
    return None


def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def mean(xs: Sequence[float]) -> Optional[float]:
    if not xs:
        return None
    return sum(xs) / len(xs)


def stdev_sample(xs: Sequence[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return math.sqrt(var)


def t_stat_mean(xs: Sequence[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    sd = stdev_sample(xs)
    if sd is None or sd == 0:
        return None
    return (sum(xs) / n) / (sd / math.sqrt(n))


def quantile(xs: Sequence[float], q: float) -> Optional[float]:
    vals = sorted(x for x in xs if x is not None and not math.isnan(x))
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    pos = (len(vals) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return vals[lo]
    w = pos - lo
    return vals[lo] * (1 - w) + vals[hi] * w


def max_drawdown(series: Sequence[float]) -> float:
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for x in series:
        cum += x
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd
    return max_dd


def max_positive_year_share(year_sums: Dict[int, float]) -> Optional[float]:
    positives = [v for v in year_sums.values() if v > 0]
    total_pos = sum(positives)
    if total_pos <= 0:
        return None
    return max(positives) / total_pos


def select_all(con: sqlite3.Connection, table: str) -> List[sqlite3.Row]:
    return con.execute(f"SELECT rowid AS _rowid_, * FROM {quote_ident(table)}").fetchall()


def load_candidate_events(
    con: sqlite3.Connection,
    table: str,
    candidate_id: str,
    horizon_bars: Optional[int],
) -> Tuple[List[EventRow], Dict[str, Any]]:
    cols = table_columns(con, table)
    ts_col = detect_column(cols, TIMESTAMP_CANDIDATES, label="event timestamp column")
    net_col = detect_column(cols, NET_BPS_CANDIDATES, label="net bps column")
    direction_col = detect_column(cols, DIRECTION_CANDIDATES, label="direction column")
    candidate_col = detect_column(cols, CANDIDATE_ID_CANDIDATES, label="candidate id column")
    baseline_col = detect_column(cols, BASELINE_NAME_CANDIDATES, required=False, label="baseline name column")
    horizon_col = detect_column(cols, HORIZON_CANDIDATES, required=False, label="horizon bars column")
    cot_col = detect_column(cols, COT_STATE_CANDIDATES, required=False, label="COT state column")
    gross_col = detect_column(cols, GROSS_BPS_CANDIDATES, required=False, label="gross bps column")
    cost_col = detect_column(cols, COST_BPS_CANDIDATES, required=False, label="cost bps column")
    price_col = detect_column(cols, PRICE_CANDIDATES, required=False, label="entry price column")

    query = f"SELECT rowid AS _rowid_, * FROM {quote_ident(table)} WHERE {quote_ident(candidate_col)} = ?"
    params: List[Any] = [candidate_id]
    if horizon_bars is not None and horizon_col:
        query += f" AND CAST({quote_ident(horizon_col)} AS INTEGER) = ?"
        params.append(int(horizon_bars))
    rows = con.execute(query, params).fetchall()

    events: List[EventRow] = []
    dropped = 0
    for r in rows:
        try:
            ts = normalize_ts(r[ts_col])
            dtu = parse_ts(ts)
            net = safe_float(r[net_col])
            if net is None:
                dropped += 1
                continue
            direction = str(r[direction_col] or "").strip().upper()
            if direction in {"BUY", "BULL", "LONG_ENTRY"}:
                direction = "LONG"
            elif direction in {"SELL", "BEAR", "SHORT_ENTRY"}:
                direction = "SHORT"
            elif direction not in {"LONG", "SHORT"}:
                direction = direction or "UNKNOWN"
            cot_state = str(r[cot_col]).strip() if cot_col and r[cot_col] is not None else "COT_UNKNOWN"
            baseline_name = str(r[baseline_col]).strip() if baseline_col and r[baseline_col] is not None else "UNKNOWN"
            hb = safe_int(r[horizon_col], default=horizon_bars or 0) if horizon_col else (horizon_bars or 0)
            events.append(
                EventRow(
                    source_rowid=int(r["_rowid_"]),
                    candidate_id=str(r[candidate_col]),
                    baseline_name=baseline_name,
                    horizon_bars=hb,
                    ts_utc=ts,
                    dt_utc=dtu,
                    year=dtu.year,
                    month=f"{dtu.year:04d}-{dtu.month:02d}",
                    direction_label=direction,
                    cot_state=cot_state,
                    net_bps=float(net),
                    gross_bps=safe_float(r[gross_col]) if gross_col else None,
                    cost_bps=safe_float(r[cost_col]) if cost_col else None,
                    entry_price=safe_float(r[price_col]) if price_col else None,
                )
            )
        except Exception:
            dropped += 1

    events.sort(key=lambda e: e.dt_utc)
    meta = {
        "source_table": table,
        "candidate_id": candidate_id,
        "horizon_filter": horizon_bars,
        "detected_columns": {
            "timestamp": ts_col,
            "net_bps": net_col,
            "direction": direction_col,
            "candidate_id": candidate_col,
            "baseline_name": baseline_col,
            "horizon_bars": horizon_col,
            "cot_state": cot_col,
            "gross_bps": gross_col,
            "cost_bps": cost_col,
            "entry_price": price_col,
        },
        "raw_rows": len(rows),
        "loaded_events": len(events),
        "dropped_rows": dropped,
    }
    if not events:
        raise RuntimeError(f"No usable events loaded for candidate_id={candidate_id!r}. Meta: {meta}")
    return events, meta


def load_bars(
    con: sqlite3.Connection,
    table: str,
    source: str,
    symbol: str,
    timeframe: str,
) -> Tuple[List[BarRow], Dict[str, Any]]:
    cols = table_columns(con, table)
    ts_col = detect_column(cols, BAR_TS_CANDIDATES, label="bar timestamp column")
    open_col = detect_column(cols, BAR_OPEN_CANDIDATES, label="bar open column")
    high_col = detect_column(cols, BAR_HIGH_CANDIDATES, label="bar high column")
    low_col = detect_column(cols, BAR_LOW_CANDIDATES, label="bar low column")
    close_col = detect_column(cols, BAR_CLOSE_CANDIDATES, label="bar close column")

    lower_cols = {c.lower(): c for c in cols}
    source_col = lower_cols.get("source")
    symbol_col = lower_cols.get("symbol")
    timeframe_col = lower_cols.get("timeframe")

    where_parts = []
    params: List[Any] = []
    if source_col:
        where_parts.append(f"{quote_ident(source_col)} = ?")
        params.append(source)
    if symbol_col:
        where_parts.append(f"{quote_ident(symbol_col)} = ?")
        params.append(symbol)
    if timeframe_col:
        where_parts.append(f"{quote_ident(timeframe_col)} = ?")
        params.append(timeframe)

    where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
    query = (
        f"SELECT {quote_ident(ts_col)} AS ts, {quote_ident(open_col)} AS o, "
        f"{quote_ident(high_col)} AS h, {quote_ident(low_col)} AS l, {quote_ident(close_col)} AS c "
        f"FROM {quote_ident(table)}{where_sql}"
    )
    rows = con.execute(query, params).fetchall()

    bars: List[BarRow] = []
    dropped = 0
    for r in rows:
        try:
            ts = normalize_ts(r["ts"])
            dtu = parse_ts(ts)
            o = safe_float(r["o"])
            h = safe_float(r["h"])
            l = safe_float(r["l"])
            c = safe_float(r["c"])
            if o is None or h is None or l is None or c is None:
                dropped += 1
                continue
            bars.append(BarRow(ts, dtu, o, h, l, c))
        except Exception:
            dropped += 1

    bars.sort(key=lambda b: b.dt_utc)
    meta = {
        "bars_table": table,
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "detected_columns": {
            "timestamp": ts_col,
            "open": open_col,
            "high": high_col,
            "low": low_col,
            "close": close_col,
            "source": source_col,
            "symbol": symbol_col,
            "timeframe": timeframe_col,
        },
        "raw_rows": len(rows),
        "loaded_bars": len(bars),
        "dropped_rows": dropped,
    }
    if not bars:
        raise RuntimeError(f"No usable bars loaded. Meta: {meta}")
    return bars, meta


def true_range(current: BarRow, prev_close: Optional[float]) -> float:
    if prev_close is None:
        return current.high - current.low
    return max(current.high - current.low, abs(current.high - prev_close), abs(current.low - prev_close))


def enrich_events_with_bar_context(
    events: List[EventRow],
    bars: List[BarRow],
    asia_start_hour: int,
    asia_end_hour: int,
    atr_lookback_bars: int,
) -> Dict[str, Any]:
    bars_by_ts = {b.ts_utc: b for b in bars}
    bars_by_date: Dict[str, List[BarRow]] = {}
    for b in bars:
        bars_by_date.setdefault(b.dt_utc.date().isoformat(), []).append(b)

    # For fast "last bar <= event" lookup, use simple pointer because data is small enough.
    bar_dts = [b.dt_utc for b in bars]

    def last_bar_index_before_or_at(t: dt.datetime) -> Optional[int]:
        # binary search without importing bisect? use bisect for clarity
        import bisect

        idx = bisect.bisect_right(bar_dts, t) - 1
        return idx if idx >= 0 else None

    missing_context = 0
    for ev in events:
        ev.breakout_hour_utc = ev.dt_utc.hour
        ev.breakout_hour_bucket = hour_bucket(ev.dt_utc.hour)
        ev.asia_date = ev.dt_utc.date().isoformat()

        day_bars = bars_by_date.get(ev.asia_date, [])
        asia_bars = [b for b in day_bars if asia_start_hour <= b.dt_utc.hour < asia_end_hour]
        if not asia_bars:
            # Fallback for broker/session shifts: if entry happened shortly after midnight,
            # try previous UTC date.
            prev_date = (ev.dt_utc.date() - dt.timedelta(days=1)).isoformat()
            prev_bars = bars_by_date.get(prev_date, [])
            asia_bars = [b for b in prev_bars if asia_start_hour <= b.dt_utc.hour < asia_end_hour]
            if asia_bars:
                ev.asia_date = prev_date

        if asia_bars:
            ev.asia_high = max(b.high for b in asia_bars)
            ev.asia_low = min(b.low for b in asia_bars)
            ev.asia_mid = (ev.asia_high + ev.asia_low) / 2.0
            if ev.asia_mid and ev.asia_mid > 0:
                ev.asia_range_bps = (ev.asia_high - ev.asia_low) / ev.asia_mid * 10000.0
        else:
            missing_context += 1

        idx = last_bar_index_before_or_at(ev.dt_utc)
        if idx is not None:
            entry_bar = bars[idx]
            entry_price = ev.entry_price if ev.entry_price is not None else entry_bar.close
            if ev.asia_high is not None and ev.asia_low is not None and ev.asia_mid and ev.asia_mid > 0:
                if ev.direction_label == "LONG":
                    ev.breakout_extension_bps = (entry_price - ev.asia_high) / ev.asia_mid * 10000.0
                elif ev.direction_label == "SHORT":
                    ev.breakout_extension_bps = (ev.asia_low - entry_price) / ev.asia_mid * 10000.0

            # Use completed bars strictly before event timestamp for ATR.
            end_idx = idx
            while end_idx >= 0 and bars[end_idx].dt_utc >= ev.dt_utc:
                end_idx -= 1
            start_idx = max(1, end_idx - atr_lookback_bars + 1)
            trs: List[float] = []
            for j in range(start_idx, end_idx + 1):
                prev_close = bars[j - 1].close if j > 0 else None
                trs.append(true_range(bars[j], prev_close))
            if trs and entry_bar.close > 0:
                ev.pre_entry_atr_bps = (sum(trs) / len(trs)) / entry_bar.close * 10000.0
        else:
            missing_context += 1

    # Diagnostic buckets are sample-tercile buckets. They are NOT production thresholds.
    range_vals = [e.asia_range_bps for e in events if e.asia_range_bps is not None]
    atr_vals = [e.pre_entry_atr_bps for e in events if e.pre_entry_atr_bps is not None]
    ext_vals = [e.breakout_extension_bps for e in events if e.breakout_extension_bps is not None]

    r33, r67 = quantile(range_vals, 0.33), quantile(range_vals, 0.67)
    a33, a67 = quantile(atr_vals, 0.33), quantile(atr_vals, 0.67)
    e33, e67 = quantile([x for x in ext_vals if x >= 0], 0.33), quantile([x for x in ext_vals if x >= 0], 0.67)

    for ev in events:
        ev.range_bucket = bucket_tercile(ev.asia_range_bps, r33, r67, "RANGE_LOW", "RANGE_NORMAL", "RANGE_WIDE", "RANGE_UNKNOWN")
        ev.atr_bucket = bucket_tercile(ev.pre_entry_atr_bps, a33, a67, "ATR_LOW", "ATR_NORMAL", "ATR_EXPANSION", "ATR_UNKNOWN")
        ev.breakout_extension_bucket = extension_bucket(ev.breakout_extension_bps, e33, e67)

    return {
        "asia_start_hour": asia_start_hour,
        "asia_end_hour": asia_end_hour,
        "atr_lookback_bars": atr_lookback_bars,
        "missing_context_count": missing_context,
        "range_bucket_thresholds_bps": {"p33": r33, "p67": r67},
        "atr_bucket_thresholds_bps": {"p33": a33, "p67": a67},
        "breakout_extension_thresholds_bps_non_negative": {"p33": e33, "p67": e67},
        "note": "Buckets are full-sample diagnostic terciles, not production thresholds.",
    }


def bucket_tercile(value: Optional[float], p33: Optional[float], p67: Optional[float], low_label: str, mid_label: str, high_label: str, unknown: str) -> str:
    if value is None or p33 is None or p67 is None:
        return unknown
    if value <= p33:
        return low_label
    if value <= p67:
        return mid_label
    return high_label


def hour_bucket(hour: int) -> str:
    if hour <= 6:
        return f"H{hour:02d}_EARLY_OR_ASIA"
    if hour in {7, 8, 9, 10, 11, 12, 13, 14}:
        return f"H{hour:02d}"
    return "H15_PLUS_OR_OTHER"


def extension_bucket(value: Optional[float], p33: Optional[float], p67: Optional[float]) -> str:
    if value is None:
        return "EXT_UNKNOWN"
    if value < 0:
        return "EXT_NEGATIVE_OR_NOT_CONFIRMED"
    if p33 is None or p67 is None:
        return "EXT_NON_NEGATIVE"
    if value <= p33:
        return "EXT_WEAK"
    if value <= p67:
        return "EXT_NORMAL"
    return "EXT_STRONG"


def policy_allow(policy_name: str, e: EventRow) -> bool:
    if policy_name == "BASELINE_ALL":
        return True
    if policy_name == "LONG_ONLY":
        return e.direction_label == "LONG"
    if policy_name == "SHORT_ONLY_DIAGNOSTIC":
        return e.direction_label == "SHORT"
    if policy_name == "LONG_ONLY_EXCLUDE_COT_EXTREMES":
        return e.direction_label == "LONG" and e.cot_state not in EXTREME_COT_STATES
    if policy_name == "LONG_ONLY_COT_NEUTRAL_OR_LONG_CROWDED":
        return e.direction_label == "LONG" and e.cot_state in {"MM_NEUTRAL", "MM_LONG_CROWDED"}
    if policy_name == "LONG_ONLY_ATR_NORMAL_OR_EXPANSION":
        return e.direction_label == "LONG" and e.atr_bucket in {"ATR_NORMAL", "ATR_EXPANSION"}
    if policy_name == "LONG_ONLY_RANGE_NORMAL_OR_WIDE":
        return e.direction_label == "LONG" and e.range_bucket in {"RANGE_NORMAL", "RANGE_WIDE"}
    return False


def summarize_policy(policy_name: str, events: List[EventRow], baseline_event_clock_mean: float, baseline_dd: float) -> Dict[str, Any]:
    event_series = [e.net_bps if policy_allow(policy_name, e) else 0.0 for e in events]
    selected = [e for e in events if policy_allow(policy_name, e)]
    selected_vals = [e.net_bps for e in selected]
    source_n = len(events)
    trade_n = len(selected)
    skipped = source_n - trade_n

    year_sums: Dict[int, float] = {}
    for e, x in zip(events, event_series):
        year_sums[e.year] = year_sums.get(e.year, 0.0) + x

    event_clock_mean = mean(event_series) or 0.0
    dd = max_drawdown(event_series)
    positive_year_count = sum(1 for v in year_sums.values() if v > 0)
    negative_year_count = sum(1 for v in year_sums.values() if v < 0)
    max_pos_share = max_positive_year_share(year_sums)

    loo_means = []
    years = sorted(set(e.year for e in events))
    for y in years:
        vals = [x for e, x in zip(events, event_series) if e.year != y]
        if vals:
            loo_means.append((y, mean(vals) or 0.0))
    worst_loo_year, worst_loo_mean = (None, None)
    if loo_means:
        worst_loo_year, worst_loo_mean = min(loo_means, key=lambda t: t[1])

    notes: List[str] = []
    if trade_n < 50 and policy_name != "BASELINE_ALL":
        notes.append("LOW_TRADE_SAMPLE_LT_50")
    if max_pos_share is not None and max_pos_share > 0.55:
        notes.append("YEAR_CONCENTRATED_GT_55PCT")
    if worst_loo_mean is not None and worst_loo_mean <= 0:
        notes.append("LEAVE_ONE_YEAR_OUT_NON_POSITIVE")
    if event_clock_mean - baseline_event_clock_mean < 5 and policy_name != "BASELINE_ALL":
        notes.append("LOW_EVENT_CLOCK_UPLIFT_LT_5BPS")
    if dd >= baseline_dd and policy_name != "BASELINE_ALL":
        notes.append("NO_DRAWDOWN_IMPROVEMENT")

    if policy_name == "BASELINE_ALL":
        decision = "BASELINE_REFERENCE"
    elif policy_name == "SHORT_ONLY_DIAGNOSTIC":
        decision = "DIAGNOSTIC_ONLY"
    elif (
        trade_n >= 250
        and event_clock_mean - baseline_event_clock_mean >= 5.0
        and dd < baseline_dd
        and worst_loo_mean is not None
        and worst_loo_mean > 0
    ):
        decision = "PASS_RESTRICTED_FILTER_CANDIDATE"
    elif trade_n >= 100 and event_clock_mean > baseline_event_clock_mean and (worst_loo_mean is None or worst_loo_mean > 0):
        decision = "WATCH_MARGINAL_FILTER"
    else:
        decision = "NO_PROMOTION"

    return {
        "summary_type": "policy_event_clock",
        "group_type": "policy",
        "group_value": policy_name,
        "source_event_count": source_n,
        "trade_count": trade_n,
        "skipped_count": skipped,
        "mean_net_bps": mean(selected_vals),
        "median_net_bps": median(selected_vals) if selected_vals else None,
        "win_rate_net": sum(1 for x in selected_vals if x > 0) / trade_n if trade_n else None,
        "t_stat_mean_net_bps": t_stat_mean(selected_vals),
        "event_clock_mean_bps": event_clock_mean,
        "event_clock_total_bps": sum(event_series),
        "uplift_vs_baseline_event_clock_mean_bps": event_clock_mean - baseline_event_clock_mean,
        "event_clock_max_drawdown_bps": dd,
        "dd_delta_vs_baseline_bps": dd - baseline_dd,
        "positive_year_count": positive_year_count,
        "negative_year_count": negative_year_count,
        "max_positive_year_share": max_pos_share,
        "worst_loo_excluded_year": worst_loo_year,
        "worst_loo_event_clock_mean_bps": worst_loo_mean,
        "decision": decision,
        "note": ";".join(notes) if notes else None,
    }


def summarize_split(summary_type: str, group_type: str, group_value: str, selected: List[EventRow]) -> Dict[str, Any]:
    vals = [e.net_bps for e in selected]
    year_sums: Dict[int, float] = {}
    for e in selected:
        year_sums[e.year] = year_sums.get(e.year, 0.0) + e.net_bps

    notes: List[str] = []
    if len(selected) < 30:
        notes.append("LOW_SAMPLE_LT_30")
    mps = max_positive_year_share(year_sums)
    if mps is not None and mps > 0.55:
        notes.append("YEAR_CONCENTRATED_GT_55PCT")

    return {
        "summary_type": summary_type,
        "group_type": group_type,
        "group_value": group_value,
        "source_event_count": len(selected),
        "trade_count": len(selected),
        "skipped_count": 0,
        "mean_net_bps": mean(vals),
        "median_net_bps": median(vals) if vals else None,
        "win_rate_net": sum(1 for x in vals if x > 0) / len(vals) if vals else None,
        "t_stat_mean_net_bps": t_stat_mean(vals),
        "event_clock_mean_bps": None,
        "event_clock_total_bps": None,
        "uplift_vs_baseline_event_clock_mean_bps": None,
        "event_clock_max_drawdown_bps": None,
        "dd_delta_vs_baseline_bps": None,
        "positive_year_count": sum(1 for v in year_sums.values() if v > 0),
        "negative_year_count": sum(1 for v in year_sums.values() if v < 0),
        "max_positive_year_share": mps,
        "worst_loo_excluded_year": None,
        "worst_loo_event_clock_mean_bps": None,
        "decision": "SPLIT_DIAGNOSTIC",
        "note": ";".join(notes) if notes else None,
    }


def build_summaries(events: List[EventRow]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    baseline_series = [e.net_bps for e in events]
    baseline_event_clock_mean = mean(baseline_series) or 0.0
    baseline_dd = max_drawdown(baseline_series)

    summaries: List[Dict[str, Any]] = []
    policies = [
        "BASELINE_ALL",
        "LONG_ONLY",
        "SHORT_ONLY_DIAGNOSTIC",
        "LONG_ONLY_EXCLUDE_COT_EXTREMES",
        "LONG_ONLY_COT_NEUTRAL_OR_LONG_CROWDED",
        "LONG_ONLY_ATR_NORMAL_OR_EXPANSION",
        "LONG_ONLY_RANGE_NORMAL_OR_WIDE",
    ]
    for p in policies:
        summaries.append(summarize_policy(p, events, baseline_event_clock_mean, baseline_dd))

    split_specs = [
        ("direction", lambda e: e.direction_label),
        ("cot_state", lambda e: e.cot_state),
        ("direction_x_cot_state", lambda e: f"{e.direction_label}__{e.cot_state}"),
        ("range_bucket", lambda e: e.range_bucket),
        ("long_x_range_bucket", lambda e: f"LONG__{e.range_bucket}" if e.direction_label == "LONG" else None),
        ("atr_bucket", lambda e: e.atr_bucket),
        ("long_x_atr_bucket", lambda e: f"LONG__{e.atr_bucket}" if e.direction_label == "LONG" else None),
        ("breakout_hour_bucket", lambda e: e.breakout_hour_bucket),
        ("long_x_breakout_hour_bucket", lambda e: f"LONG__{e.breakout_hour_bucket}" if e.direction_label == "LONG" else None),
        ("breakout_extension_bucket", lambda e: e.breakout_extension_bucket),
        ("long_x_breakout_extension_bucket", lambda e: f"LONG__{e.breakout_extension_bucket}" if e.direction_label == "LONG" else None),
        ("year", lambda e: str(e.year)),
    ]

    for group_type, key_fn in split_specs:
        groups: Dict[str, List[EventRow]] = {}
        for e in events:
            key = key_fn(e)
            if key is None:
                continue
            groups.setdefault(key, []).append(e)
        for key, group_events in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            summaries.append(summarize_split("split_trade_only", group_type, key, group_events))

    policy_rows = [s for s in summaries if s["summary_type"] == "policy_event_clock"]
    pass_count = sum(1 for s in policy_rows if s["decision"] == "PASS_RESTRICTED_FILTER_CANDIDATE")
    watch_count = sum(1 for s in policy_rows if s["decision"] == "WATCH_MARGINAL_FILTER")

    if pass_count:
        decision = "PROCEED_TO_RESTRICTED_FILTER_RETEST_READ_ONLY"
    elif watch_count:
        decision = "REVIEW_MARGINAL_FILTERS_BEFORE_ANY_RETEST"
    else:
        decision = "NO_FILTER_PROMOTION_KEEP_ASIA_RANGE_RESEARCH_ONLY"

    meta = {
        "baseline_event_clock_mean_bps": baseline_event_clock_mean,
        "baseline_event_clock_max_drawdown_bps": baseline_dd,
        "policy_pass_count": pass_count,
        "policy_watch_count": watch_count,
        "decision": decision,
    }
    return summaries, meta


def recreate_output_tables(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        DROP TABLE IF EXISTS stage38c_asia_targeted_filter_events;
        DROP TABLE IF EXISTS stage38c_asia_targeted_filter_summary;
        DROP TABLE IF EXISTS stage38c_asia_targeted_filter_audit;

        CREATE TABLE stage38c_asia_targeted_filter_events (
            source_rowid INTEGER,
            candidate_id TEXT,
            baseline_name TEXT,
            horizon_bars INTEGER,
            event_ts_utc TEXT,
            event_year INTEGER,
            event_month TEXT,
            direction_label TEXT,
            cot_state TEXT,
            net_bps REAL,
            gross_bps REAL,
            cost_bps REAL,
            entry_price REAL,
            asia_date TEXT,
            asia_range_bps REAL,
            asia_high REAL,
            asia_low REAL,
            asia_mid REAL,
            pre_entry_atr_bps REAL,
            breakout_hour_utc INTEGER,
            breakout_extension_bps REAL,
            range_bucket TEXT,
            atr_bucket TEXT,
            breakout_hour_bucket TEXT,
            breakout_extension_bucket TEXT,
            policy_baseline_all INTEGER,
            policy_long_only INTEGER,
            policy_short_only_diagnostic INTEGER,
            policy_long_only_exclude_cot_extremes INTEGER,
            policy_long_only_cot_neutral_or_long_crowded INTEGER,
            policy_long_only_atr_normal_or_expansion INTEGER,
            policy_long_only_range_normal_or_wide INTEGER
        );

        CREATE TABLE stage38c_asia_targeted_filter_summary (
            summary_type TEXT,
            group_type TEXT,
            group_value TEXT,
            source_event_count INTEGER,
            trade_count INTEGER,
            skipped_count INTEGER,
            mean_net_bps REAL,
            median_net_bps REAL,
            win_rate_net REAL,
            t_stat_mean_net_bps REAL,
            event_clock_mean_bps REAL,
            event_clock_total_bps REAL,
            uplift_vs_baseline_event_clock_mean_bps REAL,
            event_clock_max_drawdown_bps REAL,
            dd_delta_vs_baseline_bps REAL,
            positive_year_count INTEGER,
            negative_year_count INTEGER,
            max_positive_year_share REAL,
            worst_loo_excluded_year INTEGER,
            worst_loo_event_clock_mean_bps REAL,
            decision TEXT,
            note TEXT
        );

        CREATE TABLE stage38c_asia_targeted_filter_audit (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            generated_utc TEXT,
            status TEXT,
            decision TEXT,
            candidate_id TEXT,
            events_loaded INTEGER,
            events_written INTEGER,
            summary_rows_written INTEGER,
            policy_pass_count INTEGER,
            policy_watch_count INTEGER,
            warning_count INTEGER,
            note_count INTEGER,
            metadata_json TEXT
        );
        """
    )


def insert_events(con: sqlite3.Connection, events: List[EventRow]) -> None:
    rows = []
    for e in events:
        rows.append(
            (
                e.source_rowid,
                e.candidate_id,
                e.baseline_name,
                e.horizon_bars,
                e.ts_utc,
                e.year,
                e.month,
                e.direction_label,
                e.cot_state,
                e.net_bps,
                e.gross_bps,
                e.cost_bps,
                e.entry_price,
                e.asia_date,
                e.asia_range_bps,
                e.asia_high,
                e.asia_low,
                e.asia_mid,
                e.pre_entry_atr_bps,
                e.breakout_hour_utc,
                e.breakout_extension_bps,
                e.range_bucket,
                e.atr_bucket,
                e.breakout_hour_bucket,
                e.breakout_extension_bucket,
                int(policy_allow("BASELINE_ALL", e)),
                int(policy_allow("LONG_ONLY", e)),
                int(policy_allow("SHORT_ONLY_DIAGNOSTIC", e)),
                int(policy_allow("LONG_ONLY_EXCLUDE_COT_EXTREMES", e)),
                int(policy_allow("LONG_ONLY_COT_NEUTRAL_OR_LONG_CROWDED", e)),
                int(policy_allow("LONG_ONLY_ATR_NORMAL_OR_EXPANSION", e)),
                int(policy_allow("LONG_ONLY_RANGE_NORMAL_OR_WIDE", e)),
            )
        )
    con.executemany(
        """
        INSERT INTO stage38c_asia_targeted_filter_events VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?
        )
        """,
        rows,
    )


def insert_summaries(con: sqlite3.Connection, summaries: List[Dict[str, Any]]) -> None:
    cols = [
        "summary_type",
        "group_type",
        "group_value",
        "source_event_count",
        "trade_count",
        "skipped_count",
        "mean_net_bps",
        "median_net_bps",
        "win_rate_net",
        "t_stat_mean_net_bps",
        "event_clock_mean_bps",
        "event_clock_total_bps",
        "uplift_vs_baseline_event_clock_mean_bps",
        "event_clock_max_drawdown_bps",
        "dd_delta_vs_baseline_bps",
        "positive_year_count",
        "negative_year_count",
        "max_positive_year_share",
        "worst_loo_excluded_year",
        "worst_loo_event_clock_mean_bps",
        "decision",
        "note",
    ]
    rows = [tuple(s.get(c) for c in cols) for s in summaries]
    con.executemany(
        f"""
        INSERT INTO stage38c_asia_targeted_filter_summary
        ({", ".join(cols)})
        VALUES ({", ".join(["?"] * len(cols))})
        """,
        rows,
    )


def write_reports(
    reports_dir: Path,
    audit: Dict[str, Any],
    summaries: List[Dict[str, Any]],
    metadata: Dict[str, Any],
) -> Tuple[str, str]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "stage38c_asia_range_targeted_filter_diagnostic.json"
    md_path = reports_dir / "stage38c_asia_range_targeted_filter_diagnostic.md"

    payload = {
        "audit": audit,
        "metadata": metadata,
        "summaries": summaries,
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def fmt(x: Any, nd: int = 2) -> str:
        if x is None:
            return ""
        if isinstance(x, float):
            return f"{x:.{nd}f}"
        return str(x)

    policy_rows = [s for s in summaries if s["summary_type"] == "policy_event_clock"]
    direction_rows = [s for s in summaries if s["group_type"] == "direction"]
    cot_rows = [s for s in summaries if s["group_type"] == "cot_state"]
    long_cot_rows = [s for s in summaries if s["group_type"] == "direction_x_cot_state" and str(s["group_value"]).startswith("LONG__")]
    long_range_rows = [s for s in summaries if s["group_type"] == "long_x_range_bucket"]
    long_atr_rows = [s for s in summaries if s["group_type"] == "long_x_atr_bucket"]
    long_hour_rows = [s for s in summaries if s["group_type"] == "long_x_breakout_hour_bucket"]
    long_ext_rows = [s for s in summaries if s["group_type"] == "long_x_breakout_extension_bucket"]

    lines: List[str] = []
    lines.append("# Stage38C Asia Range Targeted Filter Diagnostic")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append(f"- Status: `{audit['status']}`")
    lines.append(f"- Decision: `{audit['decision']}`")
    lines.append(f"- Candidate: `{audit['candidate_id']}`")
    lines.append(f"- Events: `{audit['events_written']}`")
    lines.append("")
    lines.append("## Policy event-clock summary")
    lines.append("")
    lines.append("| Policy | Trades | Skipped | Trade mean bps | Event-clock mean bps | Uplift bps | Max DD bps | Decision | Note |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|---|")
    for s in policy_rows:
        lines.append(
            f"| {s['group_value']} | {s['trade_count']} | {s['skipped_count']} | "
            f"{fmt(s['mean_net_bps'])} | {fmt(s['event_clock_mean_bps'])} | "
            f"{fmt(s['uplift_vs_baseline_event_clock_mean_bps'])} | {fmt(s['event_clock_max_drawdown_bps'])} | "
            f"{s['decision']} | {s.get('note') or ''} |"
        )

    def section(title: str, rows: List[Dict[str, Any]], limit: int = 20) -> None:
        lines.append("")
        lines.append(f"## {title}")
        lines.append("")
        lines.append("| Group | N | Mean bps | Median bps | WR | t-stat | Pos years | Neg years | Max pos year share | Note |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
        for s in rows[:limit]:
            lines.append(
                f"| {s['group_value']} | {s['trade_count']} | {fmt(s['mean_net_bps'])} | "
                f"{fmt(s['median_net_bps'])} | {fmt(s['win_rate_net'], 3)} | "
                f"{fmt(s['t_stat_mean_net_bps'])} | {s['positive_year_count']} | {s['negative_year_count']} | "
                f"{fmt(s['max_positive_year_share'], 3)} | {s.get('note') or ''} |"
            )

    section("Direction split", direction_rows)
    section("COT split", cot_rows)
    section("LONG × COT split", long_cot_rows)
    section("LONG × Asia range bucket", long_range_rows)
    section("LONG × ATR bucket", long_atr_rows)
    section("LONG × breakout hour bucket", long_hour_rows)
    section("LONG × breakout extension bucket", long_ext_rows)

    lines.append("")
    lines.append("## Method notes")
    lines.append("")
    lines.append("- This is read-only research diagnostics, not a trading strategy.")
    lines.append("- Policy rows use event-clock accounting: skipped events are counted as zero-return events.")
    lines.append("- Range/ATR/extension buckets are full-sample diagnostic terciles and must not be treated as production thresholds.")
    lines.append("- Stage39, EA, paper-live and live order remain NO-GO.")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(json_path), str(md_path)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Stage38C Asia Range targeted filter diagnostic, read-only.")
    parser.add_argument("--db", default="data/local/xauusd_local_store.sqlite")
    parser.add_argument("--candidate-events-table", default="stage38c_candidate_spec_events")
    parser.add_argument("--bars-table", default="bars")
    parser.add_argument("--candidate-id", default="C1_ASIA_RANGE_BREAKOUT_24H")
    parser.add_argument("--horizon-bars", type=int, default=24)
    parser.add_argument("--source", default="amarkets_mt5")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--asia-start-hour", type=int, default=0)
    parser.add_argument("--asia-end-hour", type=int, default=6)
    parser.add_argument("--atr-lookback-bars", type=int, default=14)
    parser.add_argument("--reports-dir", default="data/reports/stage38c_asia_range_targeted_filter_diagnostic")
    args = parser.parse_args(argv)

    warnings: List[str] = []
    notes: List[str] = []

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row

    events, events_meta = load_candidate_events(
        con,
        args.candidate_events_table,
        args.candidate_id,
        args.horizon_bars,
    )
    bars, bars_meta = load_bars(con, args.bars_table, args.source, args.symbol, args.timeframe)
    context_meta = enrich_events_with_bar_context(
        events,
        bars,
        args.asia_start_hour,
        args.asia_end_hour,
        args.atr_lookback_bars,
    )
    if context_meta["missing_context_count"] > 0:
        notes.append(f"missing_or_partial_bar_context:{context_meta['missing_context_count']}")

    summaries, decision_meta = build_summaries(events)

    policy_pass_count = int(decision_meta["policy_pass_count"])
    policy_watch_count = int(decision_meta["policy_watch_count"])
    decision = str(decision_meta["decision"])

    status = "PASS"
    if not events:
        status = "FAIL"
        warnings.append("NO_EVENTS")

    recreate_output_tables(con)
    insert_events(con, events)
    insert_summaries(con, summaries)

    metadata = {
        "script": "stage38c_asia_range_targeted_filter_diagnostic.py",
        "read_only_research_stage": True,
        "no_stage39": True,
        "no_ea": True,
        "no_paper_live": True,
        "no_live_order": True,
        "args": vars(args),
        "events_meta": events_meta,
        "bars_meta": bars_meta,
        "context_meta": context_meta,
        "decision_meta": decision_meta,
    }

    audit = {
        "generated_utc": utc_now_iso(),
        "status": status,
        "decision": decision,
        "candidate_id": args.candidate_id,
        "events_loaded": events_meta["loaded_events"],
        "events_written": len(events),
        "summary_rows_written": len(summaries),
        "policy_pass_count": policy_pass_count,
        "policy_watch_count": policy_watch_count,
        "warning_count": len(warnings),
        "note_count": len(notes),
        "warnings": warnings,
        "notes": notes,
    }

    json_report, md_report = write_reports(Path(args.reports_dir), audit, summaries, metadata)
    audit["json_report"] = json_report
    audit["md_report"] = md_report

    con.execute(
        """
        INSERT INTO stage38c_asia_targeted_filter_audit (
            generated_utc, status, decision, candidate_id,
            events_loaded, events_written, summary_rows_written,
            policy_pass_count, policy_watch_count,
            warning_count, note_count, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            audit["generated_utc"],
            audit["status"],
            audit["decision"],
            audit["candidate_id"],
            audit["events_loaded"],
            audit["events_written"],
            audit["summary_rows_written"],
            audit["policy_pass_count"],
            audit["policy_watch_count"],
            audit["warning_count"],
            audit["note_count"],
            json.dumps(metadata, ensure_ascii=False),
        ),
    )
    con.commit()

    print(json.dumps(audit, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
