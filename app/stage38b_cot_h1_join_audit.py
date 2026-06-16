#!/usr/bin/env python3
"""
Stage38B COT-to-H1 anti-lookahead join audit for XAUUSD/gold.

Purpose
-------
Join weekly CFTC COT gold features to broker H1 bars using ONLY information
that was available at the H1 bar timestamp. This is a data-foundation audit,
not a trading signal, not Stage39, and not paper/live execution.

Anti-lookahead rule
-------------------
For every H1 bar timestamp T, select the latest COT feature row whose:

    available_from_utc <= T

Never join by `as_of_date <= bar_date` alone. COT is observed Tuesday but
published later, normally Friday afternoon US Eastern time; using Tuesday's
as_of_date before publication would leak future information.

Default inputs
--------------
SQLite DB: data/local/xauusd_local_store.sqlite
Bars table: bars
COT features table: cot_gold_features
Symbol/source/timeframe: XAUUSD / amarkets_mt5 / 1h

Default outputs
---------------
SQLite tables:
  - cot_gold_h1_features_joined
  - cot_gold_h1_join_audit

Reports:
  - data/reports/stage38b_cot_h1_join_audit/stage38b_cot_h1_join_audit.json
  - data/reports/stage38b_cot_h1_join_audit/stage38b_cot_h1_join_audit.md
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import os
import sqlite3
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


DEFAULT_DB = "data/local/xauusd_local_store.sqlite"
DEFAULT_REPORTS_DIR = "data/reports/stage38b_cot_h1_join_audit"
DEFAULT_BARS_TABLE = "bars"
DEFAULT_COT_TABLE = "cot_gold_features"
DEFAULT_JOINED_TABLE = "cot_gold_h1_features_joined"
DEFAULT_AUDIT_TABLE = "cot_gold_h1_join_audit"

DEFAULT_SOURCE = "amarkets_mt5"
DEFAULT_SYMBOL = "XAUUSD"
DEFAULT_TIMEFRAME = "1h"

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

PRICE_CANDIDATES = {
    "open": ["open", "o", "open_price"],
    "high": ["high", "h", "high_price"],
    "low": ["low", "l", "low_price"],
    "close": ["close", "c", "close_price"],
    "volume": ["volume", "tick_volume", "real_volume", "vol"],
    "spread": ["spread", "spread_points", "spread_price"],
}

COT_FEATURE_COLUMNS = [
    "as_of_date",
    "available_from_utc",
    "open_interest_all",
    "open_interest_chg_1w",
    "m_money_long_all",
    "m_money_short_all",
    "m_money_net_all",
    "m_money_net_chg_1w",
    "m_money_net_pct_oi",
    "m_money_net_pct_oi_chg_1w",
    "m_money_net_zscore_156w",
    "m_money_gross_long_pct_oi",
    "m_money_gross_short_pct_oi",
    "prod_merc_long_all",
    "prod_merc_short_all",
    "prod_merc_net_all",
    "prod_merc_net_chg_1w",
    "swap_net_all",
    "other_reportables_net_all",
]


@dataclass(frozen=True)
class BarRow:
    bar_ts_raw: str
    bar_ts: datetime
    source: Optional[str]
    symbol: Optional[str]
    timeframe: Optional[str]
    open_price: Optional[float]
    high_price: Optional[float]
    low_price: Optional[float]
    close_price: Optional[float]
    volume: Optional[float]
    spread: Optional[float]


@dataclass(frozen=True)
class CotRow:
    row: Dict[str, Any]
    as_of_date: str
    as_of_dt: datetime
    available_raw: str
    available_dt: datetime


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def normalize_iso_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    return text


def parse_dt(value: Any) -> datetime:
    """Parse common SQLite/ISO timestamps as timezone-aware UTC datetimes."""
    text = normalize_iso_text(value)
    if not text:
        raise ValueError("empty timestamp")

    # Numeric Unix epoch support.
    if text.replace(".", "", 1).isdigit() and len(text) >= 10:
        number = float(text)
        # Treat 13-digit values as milliseconds.
        if number > 10_000_000_000:
            number = number / 1000.0
        return datetime.fromtimestamp(number, tz=timezone.utc).replace(microsecond=0)

    text = text.replace("Z", "+00:00")
    if " " in text and "T" not in text:
        text = text.replace(" ", "T", 1)

    # Date-only fallback: midnight UTC.
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)

    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(microsecond=0)


def iso_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def maybe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if isinstance(value, str) and not value.strip():
            return None
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    except Exception:
        return None


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    row = con.execute(
        "select 1 from sqlite_master where type='table' and name=?", (table,)
    ).fetchone()
    return row is not None


def columns_for_table(con: sqlite3.Connection, table: str) -> List[str]:
    rows = con.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall()
    return [r[1] for r in rows]


def quote_ident(name: str) -> str:
    # Conservative identifier quoting for SQLite table/column names supplied by CLI.
    if not name or "\x00" in name:
        raise ValueError(f"invalid identifier: {name!r}")
    return '"' + name.replace('"', '""') + '"'


def first_present(columns: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    lowered = {c.lower(): c for c in columns}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return None


def require_column(columns: Sequence[str], candidates: Sequence[str], table: str, purpose: str) -> str:
    found = first_present(columns, candidates)
    if found is None:
        raise RuntimeError(
            f"Cannot detect {purpose} column in table {table!r}. "
            f"Tried: {', '.join(candidates)}. Existing columns: {', '.join(columns)}"
        )
    return found


def optional_select_expr(columns: Sequence[str], candidates: Sequence[str], alias: str) -> str:
    found = first_present(columns, candidates)
    if found is None:
        return f"NULL AS {quote_ident(alias)}"
    return f"{quote_ident(found)} AS {quote_ident(alias)}"


def build_bar_where(columns: Sequence[str], source: str, symbol: str, timeframe: str) -> Tuple[str, List[Any], Dict[str, Optional[str]]]:
    filters: List[str] = []
    params: List[Any] = []
    used: Dict[str, Optional[str]] = {"source": None, "symbol": None, "timeframe": None}

    source_col = first_present(columns, ["source", "provider", "feed", "broker"])
    symbol_col = first_present(columns, ["symbol", "instrument", "ticker"])
    timeframe_col = first_present(columns, ["timeframe", "tf", "interval"])

    if source_col:
        filters.append(f"lower({quote_ident(source_col)}) = lower(?)")
        params.append(source)
        used["source"] = source_col
    if symbol_col:
        filters.append(f"upper({quote_ident(symbol_col)}) = upper(?)")
        params.append(symbol)
        used["symbol"] = symbol_col
    if timeframe_col:
        filters.append(f"lower({quote_ident(timeframe_col)}) = lower(?)")
        params.append(timeframe)
        used["timeframe"] = timeframe_col

    where_sql = ""
    if filters:
        where_sql = " WHERE " + " AND ".join(filters)
    return where_sql, params, used


def load_bars(
    con: sqlite3.Connection,
    table: str,
    source: str,
    symbol: str,
    timeframe: str,
) -> Tuple[List[BarRow], Dict[str, Any]]:
    if not table_exists(con, table):
        raise RuntimeError(f"Bars table not found: {table}")

    cols = columns_for_table(con, table)
    ts_col = require_column(cols, TIMESTAMP_CANDIDATES, table, "bar timestamp")
    where_sql, params, filter_cols = build_bar_where(cols, source, symbol, timeframe)

    select_exprs = [
        f"{quote_ident(ts_col)} AS bar_ts_raw",
        optional_select_expr(cols, ["source", "provider", "feed", "broker"], "source"),
        optional_select_expr(cols, ["symbol", "instrument", "ticker"], "symbol"),
        optional_select_expr(cols, ["timeframe", "tf", "interval"], "timeframe"),
        optional_select_expr(cols, PRICE_CANDIDATES["open"], "open_price"),
        optional_select_expr(cols, PRICE_CANDIDATES["high"], "high_price"),
        optional_select_expr(cols, PRICE_CANDIDATES["low"], "low_price"),
        optional_select_expr(cols, PRICE_CANDIDATES["close"], "close_price"),
        optional_select_expr(cols, PRICE_CANDIDATES["volume"], "volume"),
        optional_select_expr(cols, PRICE_CANDIDATES["spread"], "spread"),
    ]
    sql = f"SELECT {', '.join(select_exprs)} FROM {quote_ident(table)}{where_sql} ORDER BY {quote_ident(ts_col)}"

    parse_errors: List[str] = []
    bars: List[BarRow] = []
    for row in con.execute(sql, params).fetchall():
        raw_ts = normalize_iso_text(row[0])
        try:
            bar_dt = parse_dt(raw_ts)
        except Exception as exc:
            if len(parse_errors) < 10:
                parse_errors.append(f"{raw_ts!r}: {exc}")
            continue
        bars.append(
            BarRow(
                bar_ts_raw=raw_ts,
                bar_ts=bar_dt,
                source=normalize_iso_text(row[1]) or None,
                symbol=normalize_iso_text(row[2]) or None,
                timeframe=normalize_iso_text(row[3]) or None,
                open_price=maybe_float(row[4]),
                high_price=maybe_float(row[5]),
                low_price=maybe_float(row[6]),
                close_price=maybe_float(row[7]),
                volume=maybe_float(row[8]),
                spread=maybe_float(row[9]),
            )
        )

    meta = {
        "bars_table": table,
        "timestamp_column": ts_col,
        "filter_columns_used": filter_cols,
        "source_filter_requested": source,
        "symbol_filter_requested": symbol,
        "timeframe_filter_requested": timeframe,
        "parse_error_count": len(parse_errors),
        "parse_error_examples": parse_errors,
    }
    return bars, meta


def load_cot(con: sqlite3.Connection, table: str) -> Tuple[List[CotRow], Dict[str, Any]]:
    if not table_exists(con, table):
        raise RuntimeError(f"COT table not found: {table}")

    cols = columns_for_table(con, table)
    for required in ["as_of_date", "available_from_utc"]:
        if required not in cols:
            raise RuntimeError(f"Required column {required!r} not found in {table!r}")

    selected = [c for c in COT_FEATURE_COLUMNS if c in cols]
    missing = [c for c in COT_FEATURE_COLUMNS if c not in cols]
    sql = f"SELECT {', '.join(quote_ident(c) for c in selected)} FROM {quote_ident(table)} ORDER BY available_from_utc, as_of_date"

    parse_errors: List[str] = []
    cots: List[CotRow] = []
    for raw in con.execute(sql).fetchall():
        d = dict(zip(selected, raw))
        try:
            as_of_dt = parse_dt(d["as_of_date"])
            available_dt = parse_dt(d["available_from_utc"])
        except Exception as exc:
            if len(parse_errors) < 10:
                parse_errors.append(f"as_of={d.get('as_of_date')!r} available={d.get('available_from_utc')!r}: {exc}")
            continue
        cots.append(
            CotRow(
                row=d,
                as_of_date=as_of_dt.date().isoformat(),
                as_of_dt=as_of_dt,
                available_raw=iso_z(available_dt),
                available_dt=available_dt,
            )
        )

    cots.sort(key=lambda x: (x.available_dt, x.as_of_dt))
    meta = {
        "cot_table": table,
        "selected_columns": selected,
        "missing_optional_feature_columns": missing,
        "parse_error_count": len(parse_errors),
        "parse_error_examples": parse_errors,
    }
    return cots, meta


def safe_stat(values: Sequence[float]) -> Dict[str, Optional[float]]:
    xs = [float(x) for x in values if x is not None and not math.isnan(float(x))]
    if not xs:
        return {"min": None, "p25": None, "median": None, "mean": None, "p75": None, "max": None}
    xs_sorted = sorted(xs)

    def percentile(p: float) -> float:
        if len(xs_sorted) == 1:
            return xs_sorted[0]
        k = (len(xs_sorted) - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return xs_sorted[int(k)]
        return xs_sorted[f] * (c - k) + xs_sorted[c] * (k - f)

    return {
        "min": xs_sorted[0],
        "p25": percentile(0.25),
        "median": statistics.median(xs_sorted),
        "mean": statistics.mean(xs_sorted),
        "p75": percentile(0.75),
        "max": xs_sorted[-1],
    }


def create_joined_table(con: sqlite3.Connection, table: str) -> None:
    con.execute(f"DROP TABLE IF EXISTS {quote_ident(table)}")
    con.execute(
        f"""
        CREATE TABLE {quote_ident(table)} (
            bar_ts_utc TEXT PRIMARY KEY,
            source TEXT,
            symbol TEXT,
            timeframe TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            spread REAL,
            cot_as_of_date TEXT,
            cot_available_from_utc TEXT,
            cot_report_lag_days INTEGER,
            cot_available_age_hours REAL,
            open_interest_all REAL,
            open_interest_chg_1w REAL,
            m_money_long_all REAL,
            m_money_short_all REAL,
            m_money_net_all REAL,
            m_money_net_chg_1w REAL,
            m_money_net_pct_oi REAL,
            m_money_net_pct_oi_chg_1w REAL,
            m_money_net_zscore_156w REAL,
            m_money_gross_long_pct_oi REAL,
            m_money_gross_short_pct_oi REAL,
            prod_merc_long_all REAL,
            prod_merc_short_all REAL,
            prod_merc_net_all REAL,
            prod_merc_net_chg_1w REAL,
            swap_net_all REAL,
            other_reportables_net_all REAL,
            join_rule TEXT NOT NULL
        )
        """
    )
    con.execute(f"CREATE INDEX idx_{table}_cot_date ON {quote_ident(table)} (cot_as_of_date)")
    con.execute(f"CREATE INDEX idx_{table}_cot_available ON {quote_ident(table)} (cot_available_from_utc)")


def create_audit_table(con: sqlite3.Connection, table: str) -> None:
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {quote_ident(table)} (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_utc TEXT NOT NULL,
            status TEXT NOT NULL,
            bars_total INTEGER NOT NULL,
            joined_count INTEGER NOT NULL,
            unjoined_count INTEGER NOT NULL,
            warning_count INTEGER NOT NULL,
            note_count INTEGER NOT NULL,
            report_json TEXT NOT NULL
        )
        """
    )


def build_join(
    bars: Sequence[BarRow],
    cots: Sequence[CotRow],
) -> Tuple[List[Tuple[Any, ...]], Dict[str, Any]]:
    available_times = [c.available_dt for c in cots]
    joined_rows: List[Tuple[Any, ...]] = []
    unjoined_before_first = 0
    lookahead_violations = 0
    report_lag_days: List[float] = []
    available_age_hours: List[float] = []
    cot_usage: Dict[str, int] = {}

    for bar in bars:
        idx = bisect.bisect_right(available_times, bar.bar_ts) - 1
        if idx < 0:
            unjoined_before_first += 1
            continue

        cot = cots[idx]
        if cot.available_dt > bar.bar_ts:
            lookahead_violations += 1
            continue

        lag_days = (bar.bar_ts.date() - cot.as_of_dt.date()).days
        age_hours = (bar.bar_ts - cot.available_dt).total_seconds() / 3600.0
        report_lag_days.append(float(lag_days))
        available_age_hours.append(float(age_hours))
        cot_usage[cot.as_of_date] = cot_usage.get(cot.as_of_date, 0) + 1

        row = cot.row
        joined_rows.append(
            (
                iso_z(bar.bar_ts),
                bar.source,
                bar.symbol,
                bar.timeframe,
                bar.open_price,
                bar.high_price,
                bar.low_price,
                bar.close_price,
                bar.volume,
                bar.spread,
                cot.as_of_date,
                cot.available_raw,
                lag_days,
                age_hours,
                maybe_float(row.get("open_interest_all")),
                maybe_float(row.get("open_interest_chg_1w")),
                maybe_float(row.get("m_money_long_all")),
                maybe_float(row.get("m_money_short_all")),
                maybe_float(row.get("m_money_net_all")),
                maybe_float(row.get("m_money_net_chg_1w")),
                maybe_float(row.get("m_money_net_pct_oi")),
                maybe_float(row.get("m_money_net_pct_oi_chg_1w")),
                maybe_float(row.get("m_money_net_zscore_156w")),
                maybe_float(row.get("m_money_gross_long_pct_oi")),
                maybe_float(row.get("m_money_gross_short_pct_oi")),
                maybe_float(row.get("prod_merc_long_all")),
                maybe_float(row.get("prod_merc_short_all")),
                maybe_float(row.get("prod_merc_net_all")),
                maybe_float(row.get("prod_merc_net_chg_1w")),
                maybe_float(row.get("swap_net_all")),
                maybe_float(row.get("other_reportables_net_all")),
                "latest_cot_available_from_utc_lte_bar_ts_utc",
            )
        )

    stats = {
        "bars_total": len(bars),
        "joined_count": len(joined_rows),
        "unjoined_count": len(bars) - len(joined_rows),
        "unjoined_before_first_cot_available_from_utc": unjoined_before_first,
        "lookahead_violation_count": lookahead_violations,
        "report_lag_days_stats": safe_stat(report_lag_days),
        "available_age_hours_stats": safe_stat(available_age_hours),
        "cot_report_count_used": len(cot_usage),
        "top_cot_reports_by_joined_bar_count": sorted(cot_usage.items(), key=lambda x: x[1], reverse=True)[:10],
        "first_joined_bar_ts_utc": joined_rows[0][0] if joined_rows else None,
        "last_joined_bar_ts_utc": joined_rows[-1][0] if joined_rows else None,
        "first_joined_cot_as_of_date": joined_rows[0][10] if joined_rows else None,
        "last_joined_cot_as_of_date": joined_rows[-1][10] if joined_rows else None,
    }
    return joined_rows, stats


def insert_joined_rows(con: sqlite3.Connection, table: str, rows: Sequence[Tuple[Any, ...]]) -> None:
    if not rows:
        return
    placeholders = ",".join(["?"] * 32)
    con.executemany(
        f"""
        INSERT INTO {quote_ident(table)} (
            bar_ts_utc, source, symbol, timeframe,
            open, high, low, close, volume, spread,
            cot_as_of_date, cot_available_from_utc,
            cot_report_lag_days, cot_available_age_hours,
            open_interest_all, open_interest_chg_1w,
            m_money_long_all, m_money_short_all,
            m_money_net_all, m_money_net_chg_1w,
            m_money_net_pct_oi, m_money_net_pct_oi_chg_1w,
            m_money_net_zscore_156w,
            m_money_gross_long_pct_oi, m_money_gross_short_pct_oi,
            prod_merc_long_all, prod_merc_short_all,
            prod_merc_net_all, prod_merc_net_chg_1w,
            swap_net_all, other_reportables_net_all,
            join_rule
        ) VALUES ({placeholders})
        """,
        rows,
    )


def write_reports(report: Dict[str, Any], reports_dir: Path) -> Tuple[Path, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "stage38b_cot_h1_join_audit.json"
    md_path = reports_dir / "stage38b_cot_h1_join_audit.md"

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    stats = report.get("join_stats", {})
    warnings = report.get("warnings", [])
    notes = report.get("notes", [])
    lines = [
        "# Stage38B COT-to-H1 Anti-Lookahead Join Audit",
        "",
        f"Generated UTC: `{report.get('created_utc')}`",
        f"Status: `{report.get('status')}`",
        "",
        "## Join Rule",
        "",
        "```text",
        "For each H1 bar timestamp T, use latest COT row where available_from_utc <= T.",
        "Do not join by as_of_date alone.",
        "```",
        "",
        "## Summary",
        "",
        "```text",
        f"bars_total = {stats.get('bars_total')}",
        f"joined_count = {stats.get('joined_count')}",
        f"unjoined_count = {stats.get('unjoined_count')}",
        f"lookahead_violation_count = {stats.get('lookahead_violation_count')}",
        f"first_joined_bar_ts_utc = {stats.get('first_joined_bar_ts_utc')}",
        f"last_joined_bar_ts_utc = {stats.get('last_joined_bar_ts_utc')}",
        f"first_joined_cot_as_of_date = {stats.get('first_joined_cot_as_of_date')}",
        f"last_joined_cot_as_of_date = {stats.get('last_joined_cot_as_of_date')}",
        "```",
        "",
        "## Report Lag Days",
        "",
        "```json",
        json.dumps(stats.get("report_lag_days_stats"), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Available Age Hours",
        "",
        "```json",
        json.dumps(stats.get("available_age_hours_stats"), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Warnings",
        "",
    ]
    if warnings:
        lines.extend(f"- {w}" for w in warnings)
    else:
        lines.append("None.")
    lines.extend(["", "## Notes", ""])
    if notes:
        lines.extend(f"- {n}" for n in notes)
    else:
        lines.append("None.")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def build_report(
    args: argparse.Namespace,
    bars_meta: Dict[str, Any],
    cot_meta: Dict[str, Any],
    bars: Sequence[BarRow],
    cots: Sequence[CotRow],
    join_stats: Dict[str, Any],
) -> Dict[str, Any]:
    warnings: List[str] = []
    notes: List[str] = []

    if not bars:
        warnings.append("no_h1_bars_found_for_requested_filters")
    if not cots:
        warnings.append("no_cot_feature_rows_found")
    if join_stats.get("lookahead_violation_count", 0) > 0:
        warnings.append("lookahead_violations_detected")
    if join_stats.get("joined_count", 0) == 0:
        warnings.append("zero_joined_rows")
    if bars_meta.get("parse_error_count", 0) > 0:
        warnings.append(f"bar_timestamp_parse_errors:{bars_meta.get('parse_error_count')}")
    if cot_meta.get("parse_error_count", 0) > 0:
        warnings.append(f"cot_timestamp_parse_errors:{cot_meta.get('parse_error_count')}")

    if join_stats.get("unjoined_before_first_cot_available_from_utc", 0) > 0:
        notes.append(
            f"bars_before_first_cot_available_from_utc:{join_stats['unjoined_before_first_cot_available_from_utc']}"
        )
    missing_optional = cot_meta.get("missing_optional_feature_columns") or []
    if missing_optional:
        notes.append("missing_optional_cot_columns:" + ",".join(missing_optional))

    # If filter columns were absent, the script could not enforce requested filters.
    filter_cols = bars_meta.get("filter_columns_used", {})
    absent_filters = [k for k, v in filter_cols.items() if v is None]
    if absent_filters:
        notes.append("bars_table_filter_columns_absent:" + ",".join(absent_filters))

    status = "PASS" if not warnings else "REVIEW"
    if args.fail_on_warning and warnings:
        status = "FAIL"

    return {
        "created_utc": utc_now_iso(),
        "status": status,
        "db": args.db,
        "bars_meta": bars_meta,
        "cot_meta": cot_meta,
        "bars_input_range": {
            "min_bar_ts_utc": iso_z(min(b.bar_ts for b in bars)) if bars else None,
            "max_bar_ts_utc": iso_z(max(b.bar_ts for b in bars)) if bars else None,
            "count": len(bars),
        },
        "cot_input_range": {
            "min_as_of_date": min(c.as_of_date for c in cots) if cots else None,
            "max_as_of_date": max(c.as_of_date for c in cots) if cots else None,
            "min_available_from_utc": iso_z(min(c.available_dt for c in cots)) if cots else None,
            "max_available_from_utc": iso_z(max(c.available_dt for c in cots)) if cots else None,
            "count": len(cots),
        },
        "join_stats": join_stats,
        "output_tables": {
            "joined_table": args.joined_table,
            "audit_table": args.audit_table,
        },
        "reports_dir": args.reports_dir,
        "warnings": warnings,
        "notes": notes,
        "warning_count": len(warnings),
        "note_count": len(notes),
    }


def insert_audit(con: sqlite3.Connection, table: str, report: Dict[str, Any]) -> None:
    create_audit_table(con, table)
    stats = report.get("join_stats", {})
    con.execute(
        f"""
        INSERT INTO {quote_ident(table)} (
            created_utc, status, bars_total, joined_count, unjoined_count,
            warning_count, note_count, report_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            report["created_utc"],
            report["status"],
            int(stats.get("bars_total") or 0),
            int(stats.get("joined_count") or 0),
            int(stats.get("unjoined_count") or 0),
            int(report.get("warning_count") or 0),
            int(report.get("note_count") or 0),
            json.dumps(report, ensure_ascii=False, sort_keys=True),
        ),
    )


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stage38B COT-to-H1 anti-lookahead join audit")
    p.add_argument("--db", default=DEFAULT_DB, help=f"SQLite DB path. Default: {DEFAULT_DB}")
    p.add_argument("--bars-table", default=DEFAULT_BARS_TABLE, help=f"Bars table. Default: {DEFAULT_BARS_TABLE}")
    p.add_argument("--cot-table", default=DEFAULT_COT_TABLE, help=f"COT feature table. Default: {DEFAULT_COT_TABLE}")
    p.add_argument("--joined-table", default=DEFAULT_JOINED_TABLE, help=f"Output joined table. Default: {DEFAULT_JOINED_TABLE}")
    p.add_argument("--audit-table", default=DEFAULT_AUDIT_TABLE, help=f"Audit table. Default: {DEFAULT_AUDIT_TABLE}")
    p.add_argument("--source", default=DEFAULT_SOURCE, help=f"Bars source filter if source column exists. Default: {DEFAULT_SOURCE}")
    p.add_argument("--symbol", default=DEFAULT_SYMBOL, help=f"Bars symbol filter if symbol column exists. Default: {DEFAULT_SYMBOL}")
    p.add_argument("--timeframe", default=DEFAULT_TIMEFRAME, help=f"Bars timeframe filter if timeframe column exists. Default: {DEFAULT_TIMEFRAME}")
    p.add_argument("--reports-dir", default=DEFAULT_REPORTS_DIR, help=f"Reports directory. Default: {DEFAULT_REPORTS_DIR}")
    p.add_argument("--fail-on-warning", action="store_true", help="Return non-zero exit code if warnings are present.")
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    db_path = Path(args.db)
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite DB not found: {db_path}")

    con = sqlite3.connect(str(db_path))
    try:
        con.row_factory = sqlite3.Row
        bars, bars_meta = load_bars(con, args.bars_table, args.source, args.symbol, args.timeframe)
        cots, cot_meta = load_cot(con, args.cot_table)
        joined_rows, join_stats = build_join(bars, cots)

        create_joined_table(con, args.joined_table)
        insert_joined_rows(con, args.joined_table, joined_rows)

        report = build_report(args, bars_meta, cot_meta, bars, cots, join_stats)
        insert_audit(con, args.audit_table, report)
        con.commit()

        json_path, md_path = write_reports(report, Path(args.reports_dir))

        print(json.dumps({
            "status": report["status"],
            "bars_total": join_stats.get("bars_total"),
            "joined_count": join_stats.get("joined_count"),
            "unjoined_count": join_stats.get("unjoined_count"),
            "lookahead_violation_count": join_stats.get("lookahead_violation_count"),
            "first_joined_bar_ts_utc": join_stats.get("first_joined_bar_ts_utc"),
            "last_joined_bar_ts_utc": join_stats.get("last_joined_bar_ts_utc"),
            "warning_count": report["warning_count"],
            "note_count": report["note_count"],
            "json_report": str(json_path),
            "md_report": str(md_path),
            "joined_table": args.joined_table,
            "audit_table": args.audit_table,
        }, ensure_ascii=False, indent=2))

        if args.fail_on_warning and report["warning_count"] > 0:
            return 2
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
