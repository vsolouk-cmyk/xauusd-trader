#!/usr/bin/env python3
"""
Stage38D M5/M15 Session Baseline Lab — read-only research diagnostic.

Purpose
-------
Run a fixed, non-optimized set of simple M5/M15 session baselines for XAUUSD.
This script does NOT place orders, does NOT produce live alerts, and does NOT
promote any candidate. It writes SQLite diagnostic tables and JSON/MD reports.

Inputs
------
- bars table containing derived M5/M15 bars with columns like:
  source, symbol, timeframe, utc_time, open, high, low, close, spread, volume
- optional COT state table for annotation only.

Outputs
-------
- stage38d_session_baseline_events
- stage38d_session_baseline_summary
- stage38d_session_baseline_audit
- reports/stage38d_m5_m15_session_baseline_lab.{json,md}

Design constraints
------------------
- Baseline-first / data-quality-first.
- No ML.
- No optimization grid beyond fixed, predeclared horizons/rules.
- COT is annotation only, never a trading condition here.
- Skips events whose exit crosses an abnormal gap.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import statistics
import sys
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta, time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

POINT_SIZE = 0.01
DEFAULT_SOURCE = "amarkets_mt5"
DEFAULT_SYMBOL = "XAUUSD"
DEFAULT_TIMEFRAMES = "M5,M15"

EVENTS_TABLE = "stage38d_session_baseline_events"
SUMMARY_TABLE = "stage38d_session_baseline_summary"
AUDIT_TABLE = "stage38d_session_baseline_audit"

TIMESTAMP_CANDIDATES = [
    "utc_time", "ts_utc", "timestamp_utc", "datetime_utc", "bar_ts_utc",
    "time_utc", "open_time_utc", "bar_time_utc", "open_time", "source_time",
    "timestamp", "datetime", "time", "ts",
]

REQUIRED_PRICE_COLS = ["open", "high", "low", "close"]

# Fixed session definitions in UTC. These are research conventions, not broker execution promises.
ASIA_START_HOUR = 23
ASIA_END_HOUR = 7     # Asia range ends before 07:00 UTC.
LONDON_START_HOUR = 7
LONDON_END_HOUR = 12
NY_START_HOUR = 13
NY_END_HOUR = 17

# Fixed horizons by timeframe. Kept deliberately small and session-oriented.
HORIZONS_BY_TF = {
    "M5": [12, 24, 48],    # 1h, 2h, 4h
    "M15": [4, 8, 16],     # 1h, 2h, 4h
}

# Thresholds for summary decisions. These are intentionally conservative.
PASS_MIN_SAMPLE = 350
WATCH_MIN_SAMPLE = 200
PASS_MIN_MEAN_BPS = 4.0
WATCH_MIN_MEAN_BPS = 2.0
PASS_MIN_TSTAT = 1.75
WATCH_MIN_TSTAT = 1.25
MAX_POSITIVE_YEAR_SHARE = 0.55
MIN_POSITIVE_YEARS = 3


@dataclass
class Bar:
    idx: int
    ts: str
    dt: datetime
    source: str
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    spread: Optional[float]
    volume: Optional[float]


@dataclass
class Event:
    event_id: str
    timeframe: str
    baseline_family: str
    baseline_name: str
    trade_date: str
    session_label: str
    entry_ts_utc: str
    exit_ts_utc: str
    horizon_bars: int
    horizon_minutes: int
    direction: int
    direction_label: str
    entry_price: float
    exit_price: float
    gross_bps: float
    cost_bps: float
    net_bps: float
    spread_entry_points: Optional[float]
    spread_exit_points: Optional[float]
    asia_high: Optional[float]
    asia_low: Optional[float]
    asia_range_bps: Optional[float]
    prebreak_range_bps: Optional[float]
    trigger_hour_utc: int
    trigger_minute_utc: int
    cot_state: Optional[str]
    note: Optional[str] = None


def parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # Fallback for common SQLite timestamp format.
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(str(value), fmt).replace(tzinfo=timezone.utc)
                break
            except ValueError:
                dt = None
        if dt is None:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    row = con.execute(
        "select 1 from sqlite_master where type='table' and name=?", (table,)
    ).fetchone()
    return row is not None


def table_columns(con: sqlite3.Connection, table: str) -> List[str]:
    return [r[1] for r in con.execute(f"pragma table_info({quote_ident(table)})").fetchall()]


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def detect_col(cols: Sequence[str], candidates: Sequence[str], table: str, label: str) -> str:
    lower = {c.lower(): c for c in cols}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    raise RuntimeError(f"Cannot detect {label} column in {table}. Tried {candidates}. Existing: {cols}")


def detect_optional_col(cols: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    lower = {c.lower(): c for c in cols}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def tf_minutes(tf: str) -> int:
    t = tf.upper()
    if t.startswith("M"):
        return int(t[1:])
    if t.startswith("H"):
        return int(t[1:]) * 60
    raise ValueError(f"Unsupported timeframe: {tf}")


def normalize_tf(value: str) -> str:
    v = str(value).strip().upper()
    aliases = {"1M": "M1", "1MIN": "M1", "1MINUTE": "M1", "5M": "M5", "15M": "M15", "1H": "H1", "60M": "H1"}
    return aliases.get(v, v)


def load_bars(con: sqlite3.Connection, table: str, source: str, symbol: str, timeframe: str) -> List[Bar]:
    if not table_exists(con, table):
        raise RuntimeError(f"bars table not found: {table}")
    cols = table_columns(con, table)
    ts_col = detect_col(cols, TIMESTAMP_CANDIDATES, table, "timestamp")
    lower_cols = {c.lower(): c for c in cols}
    for req in REQUIRED_PRICE_COLS:
        if req not in lower_cols:
            raise RuntimeError(f"Missing required price column '{req}' in {table}")
    spread_col = detect_optional_col(cols, ["spread", "spread_points", "broker_spread"])
    volume_col = detect_optional_col(cols, ["volume", "tick_volume", "real_volume"])

    # Match timeframe case-insensitively and allow common aliases.
    tf = normalize_tf(timeframe)
    sql = f"""
        select rowid, {quote_ident(ts_col)} as ts,
               {quote_ident(lower_cols['open'])} as open,
               {quote_ident(lower_cols['high'])} as high,
               {quote_ident(lower_cols['low'])} as low,
               {quote_ident(lower_cols['close'])} as close,
               {quote_ident(spread_col) if spread_col else 'null'} as spread,
               {quote_ident(volume_col) if volume_col else 'null'} as volume,
               source, symbol, timeframe
        from {quote_ident(table)}
        where source = ? and symbol = ?
          and upper(timeframe) in (?, ?, ?)
        order by {quote_ident(ts_col)} asc
    """
    tf_alts = sorted({tf, tf.lower(), timeframe})
    # SQLite upper(timeframe) won't equal lowercase, but keeping params simple.
    params = (source, symbol, tf, tf.replace("M", "" ) + "M" if tf.startswith("M") else tf, tf)
    rows = con.execute(sql, params).fetchall()

    bars: List[Bar] = []
    seen_ts = set()
    for i, r in enumerate(rows):
        dt = parse_dt(r[1])
        if dt is None:
            continue
        ts = iso_z(dt)
        if ts in seen_ts:
            continue
        seen_ts.add(ts)
        o, h, l, c = map(to_float, (r[2], r[3], r[4], r[5]))
        if o is None or h is None or l is None or c is None:
            continue
        bars.append(Bar(
            idx=len(bars), ts=ts, dt=dt, source=r[8], symbol=r[9], timeframe=normalize_tf(r[10]),
            open=o, high=h, low=l, close=c, spread=to_float(r[6]), volume=to_float(r[7])
        ))
    return bars


def load_cot_states(con: sqlite3.Connection, table: str) -> Tuple[List[datetime], List[Tuple[str, str]]]:
    if not table or not table_exists(con, table):
        return [], []
    cols = table_columns(con, table)
    ts_col = detect_optional_col(cols, ["bar_ts_utc", "utc_time", "ts_utc", "timestamp_utc", "datetime_utc"])
    state_col = detect_optional_col(cols, ["cot_state", "state", "mm_state"])
    if not ts_col or not state_col:
        return [], []
    rows = con.execute(
        f"select {quote_ident(ts_col)}, {quote_ident(state_col)} from {quote_ident(table)} order by {quote_ident(ts_col)}"
    ).fetchall()
    times: List[datetime] = []
    vals: List[Tuple[str, str]] = []
    for ts, state in rows:
        dt = parse_dt(ts)
        if dt is None or state is None:
            continue
        times.append(dt)
        vals.append((iso_z(dt), str(state)))
    return times, vals


def cot_state_for(dt: datetime, cot_times: List[datetime], cot_vals: List[Tuple[str, str]]) -> Optional[str]:
    if not cot_times:
        return None
    idx = bisect_right(cot_times, dt) - 1
    if idx < 0:
        return None
    return cot_vals[idx][1]


def spread_cost_bps(entry: Bar, exit_bar: Bar, cost_multiplier: float) -> float:
    sp_e = entry.spread if entry.spread is not None else 0.0
    sp_x = exit_bar.spread if exit_bar.spread is not None else sp_e
    # A round-trip using close as a mid proxy is approximated as one average spread.
    avg_spread_price = ((sp_e + sp_x) / 2.0) * POINT_SIZE
    return (avg_spread_price / entry.close) * 10000.0 * cost_multiplier


def range_bps(high: float, low: float, ref: float) -> float:
    if ref <= 0:
        return 0.0
    return ((high - low) / ref) * 10000.0


def max_drawdown(values: Sequence[float]) -> float:
    peak = 0.0
    cum = 0.0
    max_dd = 0.0
    for v in values:
        cum += v
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd
    return max_dd


def t_stat(values: Sequence[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    mean = statistics.mean(values)
    sd = statistics.stdev(values)
    if sd == 0:
        return None
    return mean / (sd / math.sqrt(len(values)))


def safe_median(values: Sequence[float]) -> Optional[float]:
    return statistics.median(values) if values else None


def day_key(dt: datetime) -> str:
    return dt.date().isoformat()


def collect_by_day(bars: List[Bar]) -> Dict[str, List[Bar]]:
    d: Dict[str, List[Bar]] = defaultdict(list)
    for b in bars:
        d[day_key(b.dt)].append(b)
    return d


def bars_between(bars: List[Bar], start_dt: datetime, end_dt: datetime) -> List[Bar]:
    return [b for b in bars if start_dt <= b.dt < end_dt]


def first_breakout(candidates: List[Bar], asia_high: float, asia_low: float, mode: str) -> Optional[Tuple[Bar, int, str]]:
    for b in candidates:
        if mode in ("long", "bidir") and b.close > asia_high:
            return b, 1, "LONG"
        if mode in ("short", "bidir") and b.close < asia_low:
            return b, -1, "SHORT"
    return None


def momentum_event(window: List[Bar], enter_after: Optional[Bar], continuation: bool) -> Optional[Tuple[Bar, int, str, float]]:
    if len(window) < 2 or enter_after is None:
        return None
    first = window[0]
    last = window[-1]
    move = last.close - first.open
    if abs(move) < 1e-12:
        return None
    direction = 1 if move > 0 else -1
    if not continuation:
        direction *= -1
    return enter_after, direction, "LONG" if direction > 0 else "SHORT", range_bps(max(x.high for x in window), min(x.low for x in window), first.open)


def event_from_entry(
    *,
    timeframe: str,
    baseline_family: str,
    baseline_name: str,
    trade_date: str,
    session_label: str,
    entry_bar: Bar,
    exit_bar: Bar,
    horizon_bars: int,
    direction: int,
    direction_label: str,
    asia_high: Optional[float],
    asia_low: Optional[float],
    asia_range: Optional[float],
    prebreak_range: Optional[float],
    cot_state: Optional[str],
    cost_multiplier: float,
) -> Event:
    gross_bps = direction * ((exit_bar.close - entry_bar.close) / entry_bar.close) * 10000.0
    c_bps = spread_cost_bps(entry_bar, exit_bar, cost_multiplier)
    net_bps = gross_bps - c_bps
    eid = f"{timeframe}|{baseline_name}|{horizon_bars}|{trade_date}|{entry_bar.ts}|{direction_label}"
    return Event(
        event_id=eid,
        timeframe=timeframe,
        baseline_family=baseline_family,
        baseline_name=baseline_name,
        trade_date=trade_date,
        session_label=session_label,
        entry_ts_utc=entry_bar.ts,
        exit_ts_utc=exit_bar.ts,
        horizon_bars=horizon_bars,
        horizon_minutes=horizon_bars * tf_minutes(timeframe),
        direction=direction,
        direction_label=direction_label,
        entry_price=entry_bar.close,
        exit_price=exit_bar.close,
        gross_bps=gross_bps,
        cost_bps=c_bps,
        net_bps=net_bps,
        spread_entry_points=entry_bar.spread,
        spread_exit_points=exit_bar.spread,
        asia_high=asia_high,
        asia_low=asia_low,
        asia_range_bps=asia_range,
        prebreak_range_bps=prebreak_range,
        trigger_hour_utc=entry_bar.dt.hour,
        trigger_minute_utc=entry_bar.dt.minute,
        cot_state=cot_state,
    )


def valid_exit(entry: Bar, exit_bar: Bar, horizon_minutes: int, bar_minutes: int) -> bool:
    actual = (exit_bar.dt - entry.dt).total_seconds() / 60.0
    # Prevent weekend/closure jumps from masquerading as short horizon exits.
    return actual <= horizon_minutes + max(30, 3 * bar_minutes)


def generate_events_for_tf(
    bars: List[Bar],
    timeframe: str,
    cot_times: List[datetime],
    cot_vals: List[Tuple[str, str]],
    cost_multiplier: float,
) -> Tuple[List[Event], Dict[str, int]]:
    tfm = tf_minutes(timeframe)
    horizons = HORIZONS_BY_TF.get(timeframe, [max(1, 60 // tfm), max(1, 120 // tfm), max(1, 240 // tfm)])
    events: List[Event] = []
    stats = defaultdict(int)

    if len(bars) < max(horizons) + 100:
        return events, {"not_enough_bars": 1}

    by_dt = {b.dt: b for b in bars}
    # Use index-based exits for speed and validate actual elapsed time to avoid closure gaps.
    idx_map = {b.ts: i for i, b in enumerate(bars)}

    all_dates = sorted({b.dt.date() for b in bars})
    for d in all_dates:
        trade_date = d.isoformat()
        start_asia = datetime.combine(d - timedelta(days=1), time(ASIA_START_HOUR, 0), tzinfo=timezone.utc)
        end_asia = datetime.combine(d, time(ASIA_END_HOUR, 0), tzinfo=timezone.utc)
        london_start = datetime.combine(d, time(LONDON_START_HOUR, 0), tzinfo=timezone.utc)
        london_end = datetime.combine(d, time(LONDON_END_HOUR, 0), tzinfo=timezone.utc)
        ny_start = datetime.combine(d, time(NY_START_HOUR, 0), tzinfo=timezone.utc)
        ny_end = datetime.combine(d, time(NY_END_HOUR, 0), tzinfo=timezone.utc)

        asia = bars_between(bars, start_asia, end_asia)
        if len(asia) < max(4, int((8 * 60 / tfm) * 0.70)):
            stats["skip_asia_incomplete"] += 1
            continue
        asia_high = max(b.high for b in asia)
        asia_low = min(b.low for b in asia)
        asia_ref = asia[-1].close if asia[-1].close > 0 else asia[0].open
        asia_rng = range_bps(asia_high, asia_low, asia_ref)

        # Asia range breakout during London morning, first trigger only.
        london_candidates = bars_between(bars, london_start, london_end)
        for mode, bname in [
            ("bidir", "ASIA_RANGE_BREAKOUT_BIDIR_FIRST"),
            ("long", "ASIA_RANGE_BREAKOUT_LONG_FIRST"),
            ("short", "ASIA_RANGE_BREAKOUT_SHORT_FIRST"),
        ]:
            trig = first_breakout(london_candidates, asia_high, asia_low, mode)
            if trig is None:
                stats[f"no_trigger_{bname}"] += 1
                continue
            entry_bar, direction, label = trig
            eidx = idx_map.get(entry_bar.ts)
            if eidx is None:
                continue
            for h in horizons:
                xidx = eidx + h
                if xidx >= len(bars):
                    stats["skip_no_exit"] += 1
                    continue
                exit_bar = bars[xidx]
                if not valid_exit(entry_bar, exit_bar, h * tfm, tfm):
                    stats["skip_exit_gap"] += 1
                    continue
                events.append(event_from_entry(
                    timeframe=timeframe,
                    baseline_family="ASIA_RANGE",
                    baseline_name=bname,
                    trade_date=trade_date,
                    session_label="LONDON_MORNING",
                    entry_bar=entry_bar,
                    exit_bar=exit_bar,
                    horizon_bars=h,
                    direction=direction,
                    direction_label=label,
                    asia_high=asia_high,
                    asia_low=asia_low,
                    asia_range=asia_rng,
                    prebreak_range=None,
                    cot_state=cot_state_for(entry_bar.dt, cot_times, cot_vals),
                    cost_multiplier=cost_multiplier,
                ))

        # London first-hour momentum continuation/reversal.
        london_first_hour_end = london_start + timedelta(hours=1)
        london_window = bars_between(bars, london_start, london_first_hour_end)
        # Entry is the first bar at or after 08:00.
        london_entry_after = next((b for b in bars if b.dt >= london_first_hour_end), None)
        for continuation, bname in [(True, "LONDON_FIRST_HOUR_CONT"), (False, "LONDON_FIRST_HOUR_REV")]:
            mom = momentum_event(london_window, london_entry_after, continuation)
            if mom is None:
                stats[f"no_trigger_{bname}"] += 1
                continue
            entry_bar, direction, label, pre_rng = mom
            eidx = idx_map.get(entry_bar.ts)
            if eidx is None:
                continue
            for h in horizons:
                xidx = eidx + h
                if xidx >= len(bars):
                    stats["skip_no_exit"] += 1
                    continue
                exit_bar = bars[xidx]
                if not valid_exit(entry_bar, exit_bar, h * tfm, tfm):
                    stats["skip_exit_gap"] += 1
                    continue
                events.append(event_from_entry(
                    timeframe=timeframe,
                    baseline_family="LONDON_OPEN",
                    baseline_name=bname,
                    trade_date=trade_date,
                    session_label="LONDON_FIRST_HOUR",
                    entry_bar=entry_bar,
                    exit_bar=exit_bar,
                    horizon_bars=h,
                    direction=direction,
                    direction_label=label,
                    asia_high=asia_high,
                    asia_low=asia_low,
                    asia_range=asia_rng,
                    prebreak_range=pre_rng,
                    cot_state=cot_state_for(entry_bar.dt, cot_times, cot_vals),
                    cost_multiplier=cost_multiplier,
                ))

        # NY first-hour momentum continuation/reversal.
        ny_first_hour_end = ny_start + timedelta(hours=1)
        ny_window = bars_between(bars, ny_start, ny_first_hour_end)
        ny_entry_after = next((b for b in bars if b.dt >= ny_first_hour_end), None)
        for continuation, bname in [(True, "NY_FIRST_HOUR_CONT"), (False, "NY_FIRST_HOUR_REV")]:
            mom = momentum_event(ny_window, ny_entry_after, continuation)
            if mom is None:
                stats[f"no_trigger_{bname}"] += 1
                continue
            entry_bar, direction, label, pre_rng = mom
            eidx = idx_map.get(entry_bar.ts)
            if eidx is None:
                continue
            for h in horizons:
                xidx = eidx + h
                if xidx >= len(bars):
                    stats["skip_no_exit"] += 1
                    continue
                exit_bar = bars[xidx]
                if not valid_exit(entry_bar, exit_bar, h * tfm, tfm):
                    stats["skip_exit_gap"] += 1
                    continue
                events.append(event_from_entry(
                    timeframe=timeframe,
                    baseline_family="NY_OPEN",
                    baseline_name=bname,
                    trade_date=trade_date,
                    session_label="NY_FIRST_HOUR",
                    entry_bar=entry_bar,
                    exit_bar=exit_bar,
                    horizon_bars=h,
                    direction=direction,
                    direction_label=label,
                    asia_high=asia_high,
                    asia_low=asia_low,
                    asia_range=asia_rng,
                    prebreak_range=pre_rng,
                    cot_state=cot_state_for(entry_bar.dt, cot_times, cot_vals),
                    cost_multiplier=cost_multiplier,
                ))

    return events, dict(stats)


def year_stats(events: Sequence[Event]) -> Tuple[int, int, Optional[float], str, float]:
    by_year: Dict[str, float] = defaultdict(float)
    for e in events:
        by_year[e.entry_ts_utc[:4]] += e.net_bps
    positive = {y: v for y, v in by_year.items() if v > 0}
    negative = {y: v for y, v in by_year.items() if v < 0}
    total_pos = sum(positive.values())
    max_share = None
    max_year = ""
    if total_pos > 0 and positive:
        max_year, max_val = max(positive.items(), key=lambda kv: kv[1])
        max_share = max_val / total_pos if total_pos else None
    worst_year_total = min(by_year.values()) if by_year else 0.0
    return len(positive), len(negative), max_share, max_year, worst_year_total


def decide_summary(sample: int, mean: float, med: float, t: Optional[float], pos_years: int, neg_years: int, max_share: Optional[float]) -> Tuple[str, Optional[str]]:
    notes: List[str] = []
    if sample < WATCH_MIN_SAMPLE:
        notes.append("LOW_SAMPLE_LT_200")
    if mean < WATCH_MIN_MEAN_BPS:
        notes.append("LOW_MEAN_LT_2BPS")
    if t is None or t < WATCH_MIN_TSTAT:
        notes.append("WEAK_T_STAT_LT_1_25")
    if med <= 0:
        notes.append("NON_POSITIVE_MEDIAN")
    if pos_years < MIN_POSITIVE_YEARS:
        notes.append("LOW_POSITIVE_YEAR_COUNT_LT_3")
    if neg_years >= 3:
        notes.append("MANY_NEGATIVE_YEARS_GE_3")
    if max_share is not None and max_share > MAX_POSITIVE_YEAR_SHARE:
        notes.append("YEAR_CONCENTRATED_GT_55PCT")

    pass_cond = (
        sample >= PASS_MIN_SAMPLE and mean >= PASS_MIN_MEAN_BPS and
        t is not None and t >= PASS_MIN_TSTAT and pos_years >= MIN_POSITIVE_YEARS and
        (max_share is None or max_share <= MAX_POSITIVE_YEAR_SHARE)
    )
    watch_cond = (
        sample >= WATCH_MIN_SAMPLE and mean >= WATCH_MIN_MEAN_BPS and
        t is not None and t >= WATCH_MIN_TSTAT and pos_years >= 2
    )
    if pass_cond:
        return "PASS_RESEARCH_INTEREST", ";".join(notes) if notes else None
    if watch_cond:
        return "WATCH", ";".join(notes) if notes else None
    return "KILL", ";".join(notes) if notes else None


def summarize(events: Sequence[Event]) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[str, str, str, int], List[Event]] = defaultdict(list)
    for e in events:
        groups[(e.timeframe, e.baseline_family, e.baseline_name, e.horizon_bars)].append(e)
    out: List[Dict[str, Any]] = []
    for (tf, fam, name, h), evs in sorted(groups.items()):
        vals = [e.net_bps for e in evs]
        gross = [e.gross_bps for e in evs]
        costs = [e.cost_bps for e in evs]
        mean = statistics.mean(vals) if vals else 0.0
        med = safe_median(vals) or 0.0
        win = sum(1 for v in vals if v > 0) / len(vals) if vals else 0.0
        tt = t_stat(vals)
        pos_y, neg_y, max_share, max_year, worst_y_total = year_stats(evs)
        decision, note = decide_summary(len(evs), mean, med, tt, pos_y, neg_y, max_share)
        out.append({
            "timeframe": tf,
            "baseline_family": fam,
            "baseline_name": name,
            "horizon_bars": h,
            "horizon_minutes": h * tf_minutes(tf),
            "sample_count": len(evs),
            "mean_gross_bps": statistics.mean(gross) if gross else 0.0,
            "mean_cost_bps": statistics.mean(costs) if costs else 0.0,
            "mean_net_bps": mean,
            "median_net_bps": med,
            "win_rate_net": win,
            "t_stat_mean_net_bps": tt,
            "total_net_bps": sum(vals),
            "max_drawdown_bps": max_drawdown(vals),
            "positive_year_count": pos_y,
            "negative_year_count": neg_y,
            "max_positive_year_share": max_share,
            "max_positive_year": max_year or None,
            "worst_year_total_bps": worst_y_total,
            "decision": decision,
            "note": note,
        })
    return out


def recreate_tables(con: sqlite3.Connection) -> None:
    con.executescript(f"""
    drop table if exists {EVENTS_TABLE};
    drop table if exists {SUMMARY_TABLE};
    drop table if exists {AUDIT_TABLE};

    create table {EVENTS_TABLE} (
        event_id text primary key,
        timeframe text,
        baseline_family text,
        baseline_name text,
        trade_date text,
        session_label text,
        entry_ts_utc text,
        exit_ts_utc text,
        horizon_bars integer,
        horizon_minutes integer,
        direction integer,
        direction_label text,
        entry_price real,
        exit_price real,
        gross_bps real,
        cost_bps real,
        net_bps real,
        spread_entry_points real,
        spread_exit_points real,
        asia_high real,
        asia_low real,
        asia_range_bps real,
        prebreak_range_bps real,
        trigger_hour_utc integer,
        trigger_minute_utc integer,
        cot_state text,
        note text
    );

    create table {SUMMARY_TABLE} (
        summary_id integer primary key autoincrement,
        timeframe text,
        baseline_family text,
        baseline_name text,
        horizon_bars integer,
        horizon_minutes integer,
        sample_count integer,
        mean_gross_bps real,
        mean_cost_bps real,
        mean_net_bps real,
        median_net_bps real,
        win_rate_net real,
        t_stat_mean_net_bps real,
        total_net_bps real,
        max_drawdown_bps real,
        positive_year_count integer,
        negative_year_count integer,
        max_positive_year_share real,
        max_positive_year text,
        worst_year_total_bps real,
        decision text,
        note text
    );

    create table {AUDIT_TABLE} (
        audit_id integer primary key autoincrement,
        created_utc text,
        status text,
        decision text,
        source text,
        symbol text,
        timeframes text,
        bars_total integer,
        events_written integer,
        summary_rows_written integer,
        pass_count integer,
        watch_count integer,
        kill_count integer,
        warning_count integer,
        note_count integer,
        json_report text,
        md_report text,
        metadata_json text
    );
    """)


def insert_events(con: sqlite3.Connection, events: Sequence[Event]) -> None:
    if not events:
        return
    keys = list(asdict(events[0]).keys())
    placeholders = ",".join(["?"] * len(keys))
    sql = f"insert or replace into {EVENTS_TABLE} ({','.join(keys)}) values ({placeholders})"
    con.executemany(sql, [[asdict(e)[k] for k in keys] for e in events])


def insert_summary(con: sqlite3.Connection, rows: Sequence[Dict[str, Any]]) -> None:
    if not rows:
        return
    keys = list(rows[0].keys())
    placeholders = ",".join(["?"] * len(keys))
    sql = f"insert into {SUMMARY_TABLE} ({','.join(keys)}) values ({placeholders})"
    con.executemany(sql, [[r.get(k) for k in keys] for r in rows])


def write_reports(report_dir: Path, payload: Dict[str, Any], summary_rows: Sequence[Dict[str, Any]]) -> Tuple[str, str]:
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "stage38d_m5_m15_session_baseline_lab.json"
    md_path = report_dir / "stage38d_m5_m15_session_baseline_lab.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    lines = []
    lines.append("# Stage38D M5/M15 Session Baseline Lab")
    lines.append("")
    lines.append(f"- Status: `{payload['audit']['status']}`")
    lines.append(f"- Decision: `{payload['audit']['decision']}`")
    lines.append(f"- Events written: `{payload['audit']['events_written']}`")
    lines.append(f"- Summary rows: `{payload['audit']['summary_rows_written']}`")
    lines.append("")
    lines.append("## Top rows")
    lines.append("")
    lines.append("| decision | tf | family | baseline | horizon | n | mean net bps | median | WR | t | pos years | max pos year share | note |")
    lines.append("|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    sorted_rows = sorted(summary_rows, key=lambda r: (
        {"PASS_RESEARCH_INTEREST": 0, "WATCH": 1, "KILL": 2}.get(r["decision"], 9),
        -(r["mean_net_bps"] or 0),
    ))[:40]
    for r in sorted_rows:
        max_share = "" if r.get("max_positive_year_share") is None else f"{r['max_positive_year_share']:.3f}"
        t = "" if r.get("t_stat_mean_net_bps") is None else f"{r['t_stat_mean_net_bps']:.2f}"
        lines.append(
            f"| {r['decision']} | {r['timeframe']} | {r['baseline_family']} | {r['baseline_name']} | "
            f"{r['horizon_bars']} | {r['sample_count']} | {r['mean_net_bps']:.2f} | "
            f"{r['median_net_bps']:.2f} | {r['win_rate_net']:.3f} | {t} | "
            f"{r['positive_year_count']} | {max_share} | {r.get('note') or ''} |"
        )
    lines.append("")
    lines.append("## Guardrail")
    lines.append("")
    lines.append("This is a read-only baseline diagnostic. It does not authorize Stage39, EA, paper-live, or live trading.")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return str(json_path), str(md_path)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Stage38D M5/M15 session baseline lab")
    ap.add_argument("--db", required=True)
    ap.add_argument("--bars-table", default="bars")
    ap.add_argument("--source", default=DEFAULT_SOURCE)
    ap.add_argument("--symbol", default=DEFAULT_SYMBOL)
    ap.add_argument("--timeframes", default=DEFAULT_TIMEFRAMES)
    ap.add_argument("--cot-state-table", default="cot_gold_t3_feature_states")
    ap.add_argument("--reports-dir", default="data/reports/stage38d_m5_m15_session_baseline_lab")
    ap.add_argument("--cost-multiplier", type=float, default=1.0)
    args = ap.parse_args(argv)

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row

    timeframes = [normalize_tf(x) for x in args.timeframes.split(",") if x.strip()]
    cot_times, cot_vals = load_cot_states(con, args.cot_state_table)

    all_events: List[Event] = []
    tf_meta: Dict[str, Any] = {}
    bars_total = 0
    warnings: List[str] = []
    notes: List[str] = []

    for tf in timeframes:
        bars = load_bars(con, args.bars_table, args.source, args.symbol, tf)
        bars_total += len(bars)
        tf_meta[tf] = {
            "bar_count": len(bars),
            "min_ts": bars[0].ts if bars else None,
            "max_ts": bars[-1].ts if bars else None,
        }
        if not bars:
            warnings.append(f"NO_BARS_{tf}")
            continue
        evs, stats = generate_events_for_tf(bars, tf, cot_times, cot_vals, args.cost_multiplier)
        tf_meta[tf]["events_generated"] = len(evs)
        tf_meta[tf]["generator_stats"] = stats
        all_events.extend(evs)

    # Deduplicate just in case.
    dedup: Dict[str, Event] = {e.event_id: e for e in all_events}
    all_events = list(dedup.values())
    all_events.sort(key=lambda e: (e.timeframe, e.entry_ts_utc, e.baseline_name, e.horizon_bars, e.direction_label))

    summary_rows = summarize(all_events)
    pass_count = sum(1 for r in summary_rows if r["decision"] == "PASS_RESEARCH_INTEREST")
    watch_count = sum(1 for r in summary_rows if r["decision"] == "WATCH")
    kill_count = sum(1 for r in summary_rows if r["decision"] == "KILL")

    if not all_events:
        status = "FAIL"
        decision = "NO_EVENTS_GENERATED"
    elif pass_count > 0:
        status = "PASS"
        decision = "PROCEED_TO_STAGE38D_DEEP_DIAGNOSTICS_READ_ONLY"
    elif watch_count > 0:
        status = "PASS"
        decision = "WATCH_ONLY_REVIEW_BEFORE_DEEP_DIAGNOSTICS"
    else:
        status = "PASS"
        decision = "NO_PROMOTABLE_M5_M15_BASELINE_KILL_OR_PIVOT"

    audit = {
        "created_utc": iso_z(datetime.now(timezone.utc)),
        "status": status,
        "decision": decision,
        "source": args.source,
        "symbol": args.symbol,
        "timeframes": ",".join(timeframes),
        "bars_total": bars_total,
        "events_written": len(all_events),
        "summary_rows_written": len(summary_rows),
        "pass_count": pass_count,
        "watch_count": watch_count,
        "kill_count": kill_count,
        "warning_count": len(warnings),
        "note_count": len(notes) + len([tf for tf in tf_meta if tf_meta[tf].get("generator_stats")]),
    }
    payload = {
        "audit": audit,
        "metadata": {
            "tf_meta": tf_meta,
            "warnings": warnings,
            "notes": notes,
            "cost_multiplier": args.cost_multiplier,
            "point_size": POINT_SIZE,
            "session_utc": {
                "asia": f"{ASIA_START_HOUR}:00 previous day to {ASIA_END_HOUR}:00",
                "london_window": f"{LONDON_START_HOUR}:00 to {LONDON_END_HOUR}:00",
                "ny_window": f"{NY_START_HOUR}:00 to {NY_END_HOUR}:00",
            },
            "guardrail": "read_only_no_stage39_no_ea_no_paper_live_no_live",
        },
        "summary_top": sorted(summary_rows, key=lambda r: (
            {"PASS_RESEARCH_INTEREST": 0, "WATCH": 1, "KILL": 2}.get(r["decision"], 9),
            -(r["mean_net_bps"] or 0),
        ))[:50],
    }
    json_report, md_report = write_reports(Path(args.reports_dir), payload, summary_rows)
    audit["json_report"] = json_report
    audit["md_report"] = md_report

    recreate_tables(con)
    insert_events(con, all_events)
    insert_summary(con, summary_rows)
    con.execute(
        f"""insert into {AUDIT_TABLE}
        (created_utc,status,decision,source,symbol,timeframes,bars_total,events_written,
         summary_rows_written,pass_count,watch_count,kill_count,warning_count,note_count,
         json_report,md_report,metadata_json)
        values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            audit["created_utc"], status, decision, args.source, args.symbol, ",".join(timeframes),
            bars_total, len(all_events), len(summary_rows), pass_count, watch_count, kill_count,
            len(warnings), audit["note_count"], json_report, md_report,
            json.dumps(payload["metadata"], ensure_ascii=False, default=str),
        ),
    )
    con.commit()

    print(json.dumps({
        "status": status,
        "decision": decision,
        "bars_total": bars_total,
        "events_written": len(all_events),
        "summary_rows_written": len(summary_rows),
        "pass_count": pass_count,
        "watch_count": watch_count,
        "kill_count": kill_count,
        "warning_count": len(warnings),
        "note_count": audit["note_count"],
        "json_report": json_report,
        "md_report": md_report,
    }, indent=2, ensure_ascii=False))
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
