#!/usr/bin/env python3
"""
Stage38D M1/M5/M15 Data Availability Audit

Purpose
-------
Read-only audit for XAUUSD intraday bars before any Stage38D session baseline.
This script checks whether M1, M5, and M15 data exist and are clean enough for
session-level research. It does not generate signals, does not backtest, and does
not write orders.

Expected local DB schema, but with defensive column detection:
    bars(source, symbol, timeframe, utc_time, open, high, low, close,
         tick_volume, spread, ...)

Outputs
-------
SQLite tables:
    stage38d_tf_quality_summary
    stage38d_gap_summary
    stage38d_data_availability_audit

Report files:
    stage38d_m5_m15_data_availability_audit.json
    stage38d_m5_m15_data_availability_audit.md
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


TIMESTAMP_CANDIDATES = [
    "utc_time",
    "ts_utc",
    "timestamp_utc",
    "datetime_utc",
    "bar_ts_utc",
    "time_utc",
    "open_time_utc",
    "bar_time_utc",
    "open_time",
    "source_time",
    "timestamp",
    "datetime",
    "time",
    "ts",
]

OHLC_CANDIDATES = {
    "open": ["open", "o", "open_price"],
    "high": ["high", "h", "high_price"],
    "low": ["low", "l", "low_price"],
    "close": ["close", "c", "close_price"],
}

VOLUME_CANDIDATES = ["tick_volume", "volume", "real_volume", "vol"]
SPREAD_CANDIDATES = ["spread", "spread_points", "spread_raw"]

TF_ALIASES = {
    "M1": ["M1", "m1", "1m", "1min", "1min", "1_min", "1-minute", "1minute"],
    "M5": ["M5", "m5", "5m", "5min", "5_min", "5-minute", "5minute"],
    "M15": ["M15", "m15", "15m", "15min", "15_min", "15-minute", "15minute"],
    "H1": ["H1", "h1", "1h", "60m", "60min", "1hour", "1_hour"],
}

EXPECTED_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600}
EXPECTED_BARS_PER_DAY = {"M1": 1440, "M5": 288, "M15": 96, "H1": 24}


@dataclass
class TimeframeQuality:
    timeframe: str
    source_timeframe_values: str
    status: str
    decision: str
    row_count: int
    min_ts_utc: Optional[str]
    max_ts_utc: Optional[str]
    calendar_day_count: int
    active_day_count: int
    active_day_median_rows: Optional[float]
    active_day_min_rows: Optional[int]
    active_day_max_rows: Optional[int]
    duplicate_timestamp_count: int
    parse_error_count: int
    null_ohlc_count: int
    nonpositive_ohlc_count: int
    high_low_violation_count: int
    close_outside_hilo_count: int
    zero_or_null_volume_count: Optional[int]
    null_spread_count: Optional[int]
    negative_spread_count: Optional[int]
    spread_p50: Optional[float]
    spread_p75: Optional[float]
    spread_p90: Optional[float]
    spread_p95: Optional[float]
    spread_p99: Optional[float]
    expected_seconds: int
    gap_count: int
    max_gap_seconds: Optional[int]
    weekend_like_gap_count: int
    large_nonweekend_gap_count: int
    coverage_ratio_vs_h1: Optional[float]
    note: Optional[str]


@dataclass
class GapRecord:
    timeframe: str
    prev_ts_utc: str
    next_ts_utc: str
    delta_seconds: int
    missing_bar_estimate: int
    gap_type: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_ts(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # Defensive handling for epoch seconds or milliseconds.
        v = float(value)
        if v > 10_000_000_000:
            v /= 1000.0
        try:
            return datetime.fromtimestamp(v, tz=timezone.utc).replace(microsecond=0)
        except Exception:
            return None

    s = str(value).strip()
    if not s:
        return None

    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    # SQLite / CSV friendly formats.
    fmts = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).replace(microsecond=0)
        except ValueError:
            pass

    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(microsecond=0)
    except Exception:
        return None


def iso_z(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def percentile(values: Sequence[float], q: float) -> Optional[float]:
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    return xs[lo] * (hi - pos) + xs[hi] * (pos - lo)


def ensure_table_exists(con: sqlite3.Connection, table: str) -> None:
    row = con.execute(
        "select name from sqlite_master where type='table' and name=?", (table,)
    ).fetchone()
    if not row:
        raise RuntimeError(f"Table not found: {table}")


def table_columns(con: sqlite3.Connection, table: str) -> List[str]:
    rows = con.execute(f"pragma table_info({quote_ident(table)})").fetchall()
    return [str(r[1]) for r in rows]


def quote_ident(name: str) -> str:
    if not name or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for ch in name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return f'"{name}"'


def pick_column(columns: Sequence[str], candidates: Sequence[str], required: bool = False, label: str = "column") -> Optional[str]:
    lower_map = {c.lower(): c for c in columns}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    if required:
        raise RuntimeError(f"Cannot detect {label}. Tried {list(candidates)}. Existing columns: {list(columns)}")
    return None


def get_distinct_timeframes(con: sqlite3.Connection, bars_table: str, source_col: str, symbol_col: str, tf_col: str, source: str, symbol: str) -> List[str]:
    sql = f"""
        select distinct {quote_ident(tf_col)}
        from {quote_ident(bars_table)}
        where {quote_ident(source_col)} = ? and {quote_ident(symbol_col)} = ?
        order by {quote_ident(tf_col)}
    """
    return [str(r[0]) for r in con.execute(sql, (source, symbol)).fetchall()]


def matching_tf_values(existing_values: Sequence[str], canonical_tf: str) -> List[str]:
    aliases = {a.lower() for a in TF_ALIASES.get(canonical_tf, [canonical_tf])}
    matched = [v for v in existing_values if str(v).lower() in aliases]
    return matched


def build_where_tf(tf_col: str, values: Sequence[str]) -> Tuple[str, List[Any]]:
    if not values:
        return "1 = 0", []
    placeholders = ",".join("?" for _ in values)
    return f"{quote_ident(tf_col)} in ({placeholders})", list(values)


def classify_gap(prev_dt: datetime, next_dt: datetime, expected_seconds: int) -> Tuple[str, int]:
    delta = int((next_dt - prev_dt).total_seconds())
    missing_est = max(0, int(round(delta / expected_seconds)) - 1)
    if delta <= expected_seconds:
        return "OK", missing_est
    if delta <= expected_seconds * 2:
        return "SMALL_1BAR_GAP", missing_est
    # Weekend-like gap. Friday close to Sunday/Monday open. Keep it as note, not automatic failure.
    if prev_dt.weekday() == 4 and next_dt.weekday() in (6, 0) and delta >= 24 * 3600:
        return "WEEKEND_LIKE", missing_est
    if prev_dt.weekday() == 5 or next_dt.weekday() == 6:
        return "WEEKEND_OR_MARKET_CLOSURE_LIKE", missing_est
    if delta >= 6 * 3600:
        return "LARGE_NONWEEKEND_GAP", missing_est
    return "INTRADAY_GAP", missing_est


def audit_timeframe(
    con: sqlite3.Connection,
    bars_table: str,
    source_col: str,
    symbol_col: str,
    tf_col: str,
    ts_col: str,
    o_col: str,
    h_col: str,
    l_col: str,
    c_col: str,
    vol_col: Optional[str],
    spread_col: Optional[str],
    source: str,
    symbol: str,
    canonical_tf: str,
    tf_values: Sequence[str],
    h1_row_count: Optional[int],
    max_gap_examples: int,
) -> Tuple[TimeframeQuality, List[GapRecord]]:
    expected_seconds = EXPECTED_SECONDS[canonical_tf]
    source_values = ",".join(tf_values)

    if not tf_values:
        q = TimeframeQuality(
            timeframe=canonical_tf,
            source_timeframe_values="",
            status="MISSING",
            decision="MISSING",
            row_count=0,
            min_ts_utc=None,
            max_ts_utc=None,
            calendar_day_count=0,
            active_day_count=0,
            active_day_median_rows=None,
            active_day_min_rows=None,
            active_day_max_rows=None,
            duplicate_timestamp_count=0,
            parse_error_count=0,
            null_ohlc_count=0,
            nonpositive_ohlc_count=0,
            high_low_violation_count=0,
            close_outside_hilo_count=0,
            zero_or_null_volume_count=None,
            null_spread_count=None,
            negative_spread_count=None,
            spread_p50=None,
            spread_p75=None,
            spread_p90=None,
            spread_p95=None,
            spread_p99=None,
            expected_seconds=expected_seconds,
            gap_count=0,
            max_gap_seconds=None,
            weekend_like_gap_count=0,
            large_nonweekend_gap_count=0,
            coverage_ratio_vs_h1=None,
            note="timeframe_not_present_in_bars_table",
        )
        return q, []

    tf_where, tf_params = build_where_tf(tf_col, tf_values)
    select_cols = [ts_col, o_col, h_col, l_col, c_col]
    if vol_col:
        select_cols.append(vol_col)
    if spread_col:
        select_cols.append(spread_col)

    sql = f"""
        select {', '.join(quote_ident(c) for c in select_cols)}
        from {quote_ident(bars_table)}
        where {quote_ident(source_col)} = ?
          and {quote_ident(symbol_col)} = ?
          and {tf_where}
        order by {quote_ident(ts_col)} asc
    """
    params = [source, symbol] + tf_params

    row_count = 0
    parse_error_count = 0
    duplicate_count = 0
    null_ohlc_count = 0
    nonpositive_ohlc_count = 0
    high_low_violation_count = 0
    close_outside_hilo_count = 0
    zero_or_null_volume_count = 0 if vol_col else None
    null_spread_count = 0 if spread_col else None
    negative_spread_count = 0 if spread_col else None
    spreads: List[float] = []
    day_counts: Dict[str, int] = {}
    gap_records: List[GapRecord] = []
    all_gap_count = 0
    weekend_like_gap_count = 0
    large_nonweekend_gap_count = 0
    max_gap_seconds: Optional[int] = None
    min_dt: Optional[datetime] = None
    max_dt: Optional[datetime] = None
    prev_dt: Optional[datetime] = None

    for row in con.execute(sql, params):
        row_count += 1
        idx = 0
        ts_raw = row[idx]
        idx += 1
        o = row[idx]
        idx += 1
        h = row[idx]
        idx += 1
        l = row[idx]
        idx += 1
        c = row[idx]
        idx += 1
        vol = row[idx] if vol_col else None
        if vol_col:
            idx += 1
        spread = row[idx] if spread_col else None

        dt = parse_ts(ts_raw)
        if dt is None:
            parse_error_count += 1
            continue

        min_dt = dt if min_dt is None or dt < min_dt else min_dt
        max_dt = dt if max_dt is None or dt > max_dt else max_dt
        day_key = dt.date().isoformat()
        day_counts[day_key] = day_counts.get(day_key, 0) + 1

        if prev_dt is not None:
            if dt == prev_dt:
                duplicate_count += 1
            elif dt > prev_dt:
                gap_type, missing_est = classify_gap(prev_dt, dt, expected_seconds)
                delta = int((dt - prev_dt).total_seconds())
                if gap_type != "OK":
                    all_gap_count += 1
                    max_gap_seconds = delta if max_gap_seconds is None else max(max_gap_seconds, delta)
                    if gap_type in ("WEEKEND_LIKE", "WEEKEND_OR_MARKET_CLOSURE_LIKE"):
                        weekend_like_gap_count += 1
                    if gap_type == "LARGE_NONWEEKEND_GAP":
                        large_nonweekend_gap_count += 1
                    if len(gap_records) < max_gap_examples:
                        gap_records.append(
                            GapRecord(
                                timeframe=canonical_tf,
                                prev_ts_utc=iso_z(prev_dt) or "",
                                next_ts_utc=iso_z(dt) or "",
                                delta_seconds=delta,
                                missing_bar_estimate=missing_est,
                                gap_type=gap_type,
                            )
                        )
        prev_dt = dt

        ohlc = [o, h, l, c]
        if any(v is None for v in ohlc):
            null_ohlc_count += 1
        else:
            try:
                of, hf, lf, cf = [float(v) for v in ohlc]
                if of <= 0 or hf <= 0 or lf <= 0 or cf <= 0:
                    nonpositive_ohlc_count += 1
                if hf < lf:
                    high_low_violation_count += 1
                if cf > hf or cf < lf:
                    close_outside_hilo_count += 1
            except Exception:
                null_ohlc_count += 1

        if vol_col:
            try:
                if vol is None or float(vol) <= 0:
                    assert zero_or_null_volume_count is not None
                    zero_or_null_volume_count += 1
            except Exception:
                assert zero_or_null_volume_count is not None
                zero_or_null_volume_count += 1

        if spread_col:
            if spread is None or str(spread).strip() == "":
                assert null_spread_count is not None
                null_spread_count += 1
            else:
                try:
                    sf = float(spread)
                    if sf < 0:
                        assert negative_spread_count is not None
                        negative_spread_count += 1
                    else:
                        spreads.append(sf)
                except Exception:
                    assert null_spread_count is not None
                    null_spread_count += 1

    active_counts = list(day_counts.values())
    coverage_ratio_vs_h1 = None
    if canonical_tf != "H1" and h1_row_count and h1_row_count > 0:
        expected_ratio = EXPECTED_SECONDS["H1"] / expected_seconds
        coverage_ratio_vs_h1 = row_count / (h1_row_count * expected_ratio)

    # Decision gates are intentionally conservative, but not overly strict about weekend gaps.
    severe_integrity = (
        parse_error_count > 0
        or null_ohlc_count > 0
        or high_low_violation_count > 0
        or close_outside_hilo_count > 0
        or nonpositive_ohlc_count > 0
    )
    if row_count == 0:
        status = "MISSING"
        decision = "MISSING"
    elif severe_integrity:
        status = "FAIL"
        decision = "NO_GO_BAD_BAR_INTEGRITY"
    elif duplicate_count > max(10, row_count * 0.001):
        status = "WARN"
        decision = "REVIEW_DUPLICATES_BEFORE_USE"
    elif canonical_tf in ("M5", "M15") and row_count < 10_000:
        status = "WARN"
        decision = "LOW_ROW_COUNT_REVIEW"
    elif canonical_tf == "M1" and row_count < 100_000:
        status = "WARN"
        decision = "LOW_M1_ROW_COUNT_REVIEW"
    elif large_nonweekend_gap_count > max(10, row_count * 0.0005):
        status = "WARN"
        decision = "REVIEW_LARGE_NONWEEKEND_GAPS"
    else:
        status = "PASS"
        decision = "USABLE_FOR_STAGE38D_AUDIT"

    notes: List[str] = []
    if weekend_like_gap_count:
        notes.append(f"weekend_or_market_closure_like_gaps={weekend_like_gap_count}")
    if large_nonweekend_gap_count:
        notes.append(f"large_nonweekend_gaps={large_nonweekend_gap_count}")
    if spread_col is None:
        notes.append("spread_column_missing")
    if vol_col is None:
        notes.append("volume_column_missing")
    if coverage_ratio_vs_h1 is not None and coverage_ratio_vs_h1 < 0.90:
        notes.append(f"coverage_ratio_vs_h1_low={coverage_ratio_vs_h1:.4f}")

    q = TimeframeQuality(
        timeframe=canonical_tf,
        source_timeframe_values=source_values,
        status=status,
        decision=decision,
        row_count=row_count,
        min_ts_utc=iso_z(min_dt),
        max_ts_utc=iso_z(max_dt),
        calendar_day_count=len(day_counts),
        active_day_count=len(active_counts),
        active_day_median_rows=float(median(active_counts)) if active_counts else None,
        active_day_min_rows=min(active_counts) if active_counts else None,
        active_day_max_rows=max(active_counts) if active_counts else None,
        duplicate_timestamp_count=duplicate_count,
        parse_error_count=parse_error_count,
        null_ohlc_count=null_ohlc_count,
        nonpositive_ohlc_count=nonpositive_ohlc_count,
        high_low_violation_count=high_low_violation_count,
        close_outside_hilo_count=close_outside_hilo_count,
        zero_or_null_volume_count=zero_or_null_volume_count,
        null_spread_count=null_spread_count,
        negative_spread_count=negative_spread_count,
        spread_p50=percentile(spreads, 0.50),
        spread_p75=percentile(spreads, 0.75),
        spread_p90=percentile(spreads, 0.90),
        spread_p95=percentile(spreads, 0.95),
        spread_p99=percentile(spreads, 0.99),
        expected_seconds=expected_seconds,
        gap_count=all_gap_count,
        max_gap_seconds=max_gap_seconds,
        weekend_like_gap_count=weekend_like_gap_count,
        large_nonweekend_gap_count=large_nonweekend_gap_count,
        coverage_ratio_vs_h1=coverage_ratio_vs_h1,
        note=";".join(notes) if notes else None,
    )
    return q, gap_records


def create_output_tables(con: sqlite3.Connection) -> None:
    con.execute("drop table if exists stage38d_tf_quality_summary")
    con.execute("drop table if exists stage38d_gap_summary")
    con.execute("drop table if exists stage38d_data_availability_audit")

    con.execute(
        """
        create table stage38d_tf_quality_summary (
            timeframe text primary key,
            source_timeframe_values text,
            status text,
            decision text,
            row_count integer,
            min_ts_utc text,
            max_ts_utc text,
            calendar_day_count integer,
            active_day_count integer,
            active_day_median_rows real,
            active_day_min_rows integer,
            active_day_max_rows integer,
            duplicate_timestamp_count integer,
            parse_error_count integer,
            null_ohlc_count integer,
            nonpositive_ohlc_count integer,
            high_low_violation_count integer,
            close_outside_hilo_count integer,
            zero_or_null_volume_count integer,
            null_spread_count integer,
            negative_spread_count integer,
            spread_p50 real,
            spread_p75 real,
            spread_p90 real,
            spread_p95 real,
            spread_p99 real,
            expected_seconds integer,
            gap_count integer,
            max_gap_seconds integer,
            weekend_like_gap_count integer,
            large_nonweekend_gap_count integer,
            coverage_ratio_vs_h1 real,
            note text
        )
        """
    )
    con.execute(
        """
        create table stage38d_gap_summary (
            timeframe text,
            prev_ts_utc text,
            next_ts_utc text,
            delta_seconds integer,
            missing_bar_estimate integer,
            gap_type text
        )
        """
    )
    con.execute(
        """
        create table stage38d_data_availability_audit (
            audit_id integer primary key autoincrement,
            generated_utc text,
            status text,
            decision text,
            source text,
            symbol text,
            bars_table text,
            existing_timeframes text,
            target_timeframes text,
            m1_status text,
            m5_status text,
            m15_status text,
            h1_status text,
            pass_count integer,
            warn_count integer,
            fail_count integer,
            missing_count integer,
            warning_count integer,
            note_count integer,
            json_report text,
            md_report text
        )
        """
    )


def insert_quality(con: sqlite3.Connection, summaries: Sequence[TimeframeQuality]) -> None:
    for q in summaries:
        d = asdict(q)
        keys = list(d.keys())
        sql = f"""
            insert into stage38d_tf_quality_summary ({','.join(keys)})
            values ({','.join('?' for _ in keys)})
        """
        con.execute(sql, [d[k] for k in keys])


def insert_gaps(con: sqlite3.Connection, gaps: Sequence[GapRecord]) -> None:
    con.executemany(
        """
        insert into stage38d_gap_summary
        (timeframe, prev_ts_utc, next_ts_utc, delta_seconds, missing_bar_estimate, gap_type)
        values (?, ?, ?, ?, ?, ?)
        """,
        [
            (g.timeframe, g.prev_ts_utc, g.next_ts_utc, g.delta_seconds, g.missing_bar_estimate, g.gap_type)
            for g in gaps
        ],
    )


def final_decision(summaries: Sequence[TimeframeQuality]) -> Tuple[str, str, int, int, int, int, int, int]:
    by_tf = {q.timeframe: q for q in summaries}
    pass_count = sum(1 for q in summaries if q.status == "PASS")
    warn_count = sum(1 for q in summaries if q.status == "WARN")
    fail_count = sum(1 for q in summaries if q.status == "FAIL")
    missing_count = sum(1 for q in summaries if q.status == "MISSING")
    warning_count = warn_count + fail_count
    note_count = sum(1 for q in summaries if q.note)

    m1 = by_tf.get("M1")
    m5 = by_tf.get("M5")
    m15 = by_tf.get("M15")

    m1_usable = m1 is not None and m1.status in ("PASS", "WARN") and m1.row_count > 100_000
    m5_usable = m5 is not None and m5.status in ("PASS", "WARN") and m5.row_count > 10_000
    m15_usable = m15 is not None and m15.status in ("PASS", "WARN") and m15.row_count > 5_000

    if fail_count > 0:
        status = "FAIL"
        decision = "NO_GO_FIX_BAR_INTEGRITY_FIRST"
    elif m5_usable and m15_usable:
        status = "PASS"
        decision = "PROCEED_TO_STAGE38D_M5_M15_BASELINE_DESIGN"
    elif m1_usable and (not m5_usable or not m15_usable):
        status = "PASS"
        decision = "PROCEED_TO_DERIVE_M5_M15_FROM_M1_THEN_REAUDIT"
    else:
        status = "FAIL"
        decision = "NO_GO_M5_M15_AND_M1_INTRADAY_DATA_INSUFFICIENT"

    return status, decision, pass_count, warn_count, fail_count, missing_count, warning_count, note_count


def write_json_report(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_md_report(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    audit = payload["audit"]
    summaries = payload["timeframe_quality"]
    lines: List[str] = []
    lines.append("# Stage38D M5/M15 Data Availability Audit")
    lines.append("")
    lines.append(f"Generated UTC: `{audit['generated_utc']}`")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append(f"- Status: `{audit['status']}`")
    lines.append(f"- Decision: `{audit['decision']}`")
    lines.append(f"- Source: `{audit['source']}`")
    lines.append(f"- Symbol: `{audit['symbol']}`")
    lines.append(f"- Existing timeframes: `{audit['existing_timeframes']}`")
    lines.append("")
    lines.append("## Timeframe quality")
    lines.append("")
    lines.append("| TF | Status | Decision | Rows | Range UTC | Dup | Parse err | OHLC bad | Gaps | Large nonweekend gaps | Spread p50/p95 | Note |")
    lines.append("|---|---|---|---:|---|---:|---:|---:|---:|---:|---|---|")
    for q in summaries:
        ohlc_bad = q["null_ohlc_count"] + q["nonpositive_ohlc_count"] + q["high_low_violation_count"] + q["close_outside_hilo_count"]
        spread = "n/a"
        if q["spread_p50"] is not None or q["spread_p95"] is not None:
            spread = f"{q['spread_p50']:.2f}/{q['spread_p95']:.2f}"
        rng = f"{q['min_ts_utc']} → {q['max_ts_utc']}" if q["min_ts_utc"] else "n/a"
        lines.append(
            f"| {q['timeframe']} | `{q['status']}` | `{q['decision']}` | {q['row_count']} | {rng} | "
            f"{q['duplicate_timestamp_count']} | {q['parse_error_count']} | {ohlc_bad} | {q['gap_count']} | "
            f"{q['large_nonweekend_gap_count']} | {spread} | {q['note'] or ''} |"
        )
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    if audit["decision"] == "PROCEED_TO_STAGE38D_M5_M15_BASELINE_DESIGN":
        lines.append("M5 and M15 are available enough for the next Stage38D session baseline design.")
    elif audit["decision"] == "PROCEED_TO_DERIVE_M5_M15_FROM_M1_THEN_REAUDIT":
        lines.append("M5/M15 are missing or insufficient, but M1 appears usable. Derive M5/M15 from M1 and re-run this audit before any baseline test.")
    else:
        lines.append("Intraday data is not ready. Fix data integrity or collection before any Stage38D baseline work.")
    lines.append("")
    lines.append("## Hard limits")
    lines.append("")
    lines.append("- No Stage39.")
    lines.append("- No EA.")
    lines.append("- No paper-live.")
    lines.append("- No live order.")
    lines.append("- This is a read-only data audit.")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Stage38D M1/M5/M15 data availability audit")
    ap.add_argument("--db", default="data/local/xauusd_local_store.sqlite")
    ap.add_argument("--bars-table", default="bars")
    ap.add_argument("--source", default="amarkets_mt5")
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--target-timeframes", default="M1,M5,M15,H1", help="Comma-separated canonical TFs")
    ap.add_argument("--reports-dir", default="data/reports/stage38d_m5_m15_data_availability_audit")
    ap.add_argument("--max-gap-examples", type=int, default=200)
    args = ap.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        raise RuntimeError(f"DB not found: {db_path}")

    reports_dir = Path(args.reports_dir)
    json_report = reports_dir / "stage38d_m5_m15_data_availability_audit.json"
    md_report = reports_dir / "stage38d_m5_m15_data_availability_audit.md"

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row

    ensure_table_exists(con, args.bars_table)
    cols = table_columns(con, args.bars_table)
    source_col = pick_column(cols, ["source"], required=True, label="source column")
    symbol_col = pick_column(cols, ["symbol"], required=True, label="symbol column")
    tf_col = pick_column(cols, ["timeframe", "tf", "interval"], required=True, label="timeframe column")
    ts_col = pick_column(cols, TIMESTAMP_CANDIDATES, required=True, label="bar timestamp column")
    o_col = pick_column(cols, OHLC_CANDIDATES["open"], required=True, label="open column")
    h_col = pick_column(cols, OHLC_CANDIDATES["high"], required=True, label="high column")
    l_col = pick_column(cols, OHLC_CANDIDATES["low"], required=True, label="low column")
    c_col = pick_column(cols, OHLC_CANDIDATES["close"], required=True, label="close column")
    vol_col = pick_column(cols, VOLUME_CANDIDATES, required=False, label="volume column")
    spread_col = pick_column(cols, SPREAD_CANDIDATES, required=False, label="spread column")

    existing_tfs = get_distinct_timeframes(con, args.bars_table, source_col, symbol_col, tf_col, args.source, args.symbol)
    targets = [t.strip().upper() for t in args.target_timeframes.split(",") if t.strip()]

    # First get H1 row count for coverage ratios.
    h1_values = matching_tf_values(existing_tfs, "H1")
    h1_count: Optional[int] = None
    if h1_values:
        tf_where, tf_params = build_where_tf(tf_col, h1_values)
        sql = f"""
            select count(*) from {quote_ident(args.bars_table)}
            where {quote_ident(source_col)} = ?
              and {quote_ident(symbol_col)} = ?
              and {tf_where}
        """
        h1_count = int(con.execute(sql, [args.source, args.symbol] + tf_params).fetchone()[0])

    summaries: List[TimeframeQuality] = []
    gap_records: List[GapRecord] = []
    for tf in targets:
        if tf not in EXPECTED_SECONDS:
            raise RuntimeError(f"Unsupported target timeframe: {tf}")
        values = matching_tf_values(existing_tfs, tf)
        q, gaps = audit_timeframe(
            con=con,
            bars_table=args.bars_table,
            source_col=source_col,
            symbol_col=symbol_col,
            tf_col=tf_col,
            ts_col=ts_col,
            o_col=o_col,
            h_col=h_col,
            l_col=l_col,
            c_col=c_col,
            vol_col=vol_col,
            spread_col=spread_col,
            source=args.source,
            symbol=args.symbol,
            canonical_tf=tf,
            tf_values=values,
            h1_row_count=h1_count,
            max_gap_examples=args.max_gap_examples,
        )
        summaries.append(q)
        gap_records.extend(gaps)

    status, decision, pass_count, warn_count, fail_count, missing_count, warning_count, note_count = final_decision(summaries)
    generated_utc = utc_now_iso()

    payload: Dict[str, Any] = {
        "audit": {
            "generated_utc": generated_utc,
            "status": status,
            "decision": decision,
            "source": args.source,
            "symbol": args.symbol,
            "bars_table": args.bars_table,
            "detected_columns": {
                "source": source_col,
                "symbol": symbol_col,
                "timeframe": tf_col,
                "timestamp": ts_col,
                "open": o_col,
                "high": h_col,
                "low": l_col,
                "close": c_col,
                "volume": vol_col,
                "spread": spread_col,
            },
            "existing_timeframes": existing_tfs,
            "target_timeframes": targets,
            "pass_count": pass_count,
            "warn_count": warn_count,
            "fail_count": fail_count,
            "missing_count": missing_count,
            "warning_count": warning_count,
            "note_count": note_count,
            "json_report": str(json_report),
            "md_report": str(md_report),
        },
        "timeframe_quality": [asdict(q) for q in summaries],
        "gap_examples": [asdict(g) for g in gap_records],
    }

    write_json_report(json_report, payload)
    write_md_report(md_report, payload)

    create_output_tables(con)
    insert_quality(con, summaries)
    insert_gaps(con, gap_records)
    con.execute(
        """
        insert into stage38d_data_availability_audit
        (generated_utc, status, decision, source, symbol, bars_table, existing_timeframes,
         target_timeframes, m1_status, m5_status, m15_status, h1_status,
         pass_count, warn_count, fail_count, missing_count, warning_count, note_count,
         json_report, md_report)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            generated_utc,
            status,
            decision,
            args.source,
            args.symbol,
            args.bars_table,
            json.dumps(existing_tfs, ensure_ascii=False),
            json.dumps(targets, ensure_ascii=False),
            next((q.status for q in summaries if q.timeframe == "M1"), None),
            next((q.status for q in summaries if q.timeframe == "M5"), None),
            next((q.status for q in summaries if q.timeframe == "M15"), None),
            next((q.status for q in summaries if q.timeframe == "H1"), None),
            pass_count,
            warn_count,
            fail_count,
            missing_count,
            warning_count,
            note_count,
            str(json_report),
            str(md_report),
        ),
    )
    con.commit()

    result = {
        "status": status,
        "decision": decision,
        "source": args.source,
        "symbol": args.symbol,
        "existing_timeframes": existing_tfs,
        "pass_count": pass_count,
        "warn_count": warn_count,
        "fail_count": fail_count,
        "missing_count": missing_count,
        "warning_count": warning_count,
        "note_count": note_count,
        "json_report": str(json_report),
        "md_report": str(md_report),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
