#!/usr/bin/env python3
"""
Stage38E — Free Macro/Risk Data Availability Audit

Purpose
-------
Download free macro/risk series from FRED's public CSV graph endpoint, normalize
into SQLite, build conservative anti-lookahead daily features, and join them to
XAUUSD H1 bars for availability auditing.

No trading signals. No optimization. No ML. No paper/live execution.

Default free series:
    DGS10     10-Year Treasury Constant Maturity Rate
    DGS2      2-Year Treasury Constant Maturity Rate
    DFII10    10-Year Treasury Inflation-Indexed Security, Constant Maturity
    T10YIE    10-Year Breakeven Inflation Rate
    DTWEXBGS  Nominal Broad U.S. Dollar Index
    VIXCLS    CBOE Volatility Index: VIX

Data source:
    https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES_ID>

Lookahead rule:
    A daily observation dated YYYY-MM-DD is treated as usable only from
    YYYY-MM-DD + 1 calendar day at 00:00:00 UTC.

This is intentionally conservative for read-only research.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

RAW_TABLE = "stage38e_macro_risk_raw_observations"
SERIES_AUDIT_TABLE = "stage38e_macro_risk_series_audit"
DAILY_TABLE = "stage38e_macro_risk_daily_features"
H1_JOIN_TABLE = "stage38e_macro_risk_h1_joined"
AUDIT_TABLE = "stage38e_macro_risk_availability_audit"

DEFAULT_SERIES = ["DGS10", "DGS2", "DFII10", "T10YIE", "DTWEXBGS", "VIXCLS"]
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"

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

OHLC_COLUMNS = ["open", "high", "low", "close", "spread", "tick_volume", "volume"]


@dataclass
class SeriesFetchResult:
    series_id: str
    status: str
    row_count: int
    valid_count: int
    missing_count: int
    min_date: Optional[str]
    max_date: Optional[str]
    url: str
    error: Optional[str] = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso_dt(value: Any) -> Optional[datetime]:
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
        # common DB strings without T
        try:
            dt = datetime.strptime(str(value).strip(), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(microsecond=0)


def dt_to_iso_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s == "." or s.lower() in {"nan", "none", "null"}:
        return None
    try:
        x = float(s)
    except ValueError:
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_md(path: Path, title: str, payload: Dict[str, Any]) -> None:
    ensure_parent(path)
    lines: List[str] = [f"# {title}", "", "```json", json.dumps(payload, indent=2, sort_keys=True), "```", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def get_columns(con: sqlite3.Connection, table: str) -> List[str]:
    return [r[1] for r in con.execute(f'pragma table_info("{table}")').fetchall()]


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    row = con.execute(
        "select 1 from sqlite_master where type='table' and name=?", (table,)
    ).fetchone()
    return row is not None


def require_column(cols: Sequence[str], candidates: Sequence[str], table: str, label: str) -> str:
    lower_map = {c.lower(): c for c in cols}
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    raise RuntimeError(
        f"Cannot detect {label} column in table '{table}'. Tried: {', '.join(candidates)}. "
        f"Existing columns: {', '.join(cols)}"
    )


def normalize_timeframe(tf: str) -> str:
    s = str(tf).strip()
    up = s.upper()
    mapping = {
        "1M": "M1",
        "M1": "M1",
        "1MIN": "M1",
        "1MINUTE": "M1",
        "5M": "M5",
        "M5": "M5",
        "5MIN": "M5",
        "5MINUTE": "M5",
        "15M": "M15",
        "M15": "M15",
        "15MIN": "M15",
        "15MINUTE": "M15",
        "1H": "H1",
        "H1": "H1",
        "60M": "H1",
        "1HR": "H1",
        "1HOUR": "H1",
    }
    return mapping.get(up, up)


def timeframe_aliases(target: str) -> List[str]:
    norm = normalize_timeframe(target)
    if norm == "H1":
        return ["H1", "1h", "1H", "h1", "60m", "60M"]
    if norm == "M1":
        return ["M1", "1m", "1M", "m1"]
    if norm == "M5":
        return ["M5", "5m", "5M", "m5"]
    if norm == "M15":
        return ["M15", "15m", "15M", "m15"]
    return [target]


def fetch_fred_csv(series_id: str, timeout: int, retries: int) -> Tuple[str, Optional[str]]:
    url = FRED_CSV_URL.format(series_id=series_id)
    last_error: Optional[str] = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "xauusd-stage38e-macro-risk-audit/1.0",
                    "Accept": "text/csv,*/*",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read().decode("utf-8", errors="replace")
                return data, None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(min(2 * attempt, 8))
    return "", last_error


def parse_fred_csv(series_id: str, text: str, start_date: Optional[date], end_date: Optional[date]) -> Tuple[List[Dict[str, Any]], int, int]:
    rows: List[Dict[str, Any]] = []
    if not text.strip():
        return rows, 0, 0
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames or []
    if not fieldnames:
        return rows, 0, 0
    date_col = fieldnames[0]
    # FRED graph CSV usually has second column equal to series id.
    value_col = series_id if series_id in fieldnames else fieldnames[-1]
    raw_count = 0
    missing_count = 0
    for r in reader:
        obs_date = parse_date(r.get(date_col))
        if obs_date is None:
            continue
        if start_date and obs_date < start_date:
            continue
        if end_date and obs_date > end_date:
            continue
        raw_count += 1
        val = safe_float(r.get(value_col))
        if val is None:
            missing_count += 1
        rows.append(
            {
                "series_id": series_id,
                "observation_date": obs_date.isoformat(),
                "value": val,
                "is_missing": 1 if val is None else 0,
            }
        )
    return rows, raw_count, missing_count


def create_tables(con: sqlite3.Connection) -> None:
    for t in [RAW_TABLE, SERIES_AUDIT_TABLE, DAILY_TABLE, H1_JOIN_TABLE, AUDIT_TABLE]:
        con.execute(f'drop table if exists "{t}"')

    con.execute(
        f'''
        create table "{RAW_TABLE}" (
            series_id text not null,
            observation_date text not null,
            value real,
            is_missing integer not null default 0,
            ingested_at_utc text not null,
            primary key(series_id, observation_date)
        )
        '''
    )
    con.execute(
        f'''
        create table "{SERIES_AUDIT_TABLE}" (
            series_id text primary key,
            status text not null,
            row_count integer not null,
            valid_count integer not null,
            missing_count integer not null,
            min_date text,
            max_date text,
            url text not null,
            error text,
            ingested_at_utc text not null
        )
        '''
    )
    con.execute(
        f'''
        create table "{DAILY_TABLE}" (
            observation_date text primary key,
            available_from_utc text not null,
            dgs10 real,
            dgs2 real,
            dfii10 real,
            t10yie real,
            dtwexbgs real,
            vixcls real,
            curve_10y2y real,
            nominal_10y_chg_1d real,
            nominal_10y_chg_5d real,
            nominal_10y_chg_20d real,
            real_10y_chg_1d real,
            real_10y_chg_5d real,
            real_10y_chg_20d real,
            dollar_chg_1d real,
            dollar_chg_5d real,
            dollar_chg_20d real,
            vix_chg_1d real,
            vix_chg_5d real,
            vix_chg_20d real,
            macro_gold_pressure text,
            macro_risk_state text,
            available_series_count integer not null,
            missing_series_count integer not null,
            ingested_at_utc text not null
        )
        '''
    )
    con.execute(
        f'''
        create table "{H1_JOIN_TABLE}" (
            bar_ts_utc text primary key,
            source text,
            symbol text,
            timeframe text,
            open real,
            high real,
            low real,
            close real,
            spread real,
            macro_observation_date text,
            macro_available_from_utc text,
            dgs10 real,
            dgs2 real,
            dfii10 real,
            t10yie real,
            dtwexbgs real,
            vixcls real,
            curve_10y2y real,
            nominal_10y_chg_5d real,
            real_10y_chg_5d real,
            dollar_chg_5d real,
            vix_chg_5d real,
            macro_gold_pressure text,
            macro_risk_state text,
            lookahead_violation integer not null default 0,
            ingested_at_utc text not null
        )
        '''
    )
    con.execute(
        f'''
        create table "{AUDIT_TABLE}" (
            audit_id integer primary key autoincrement,
            status text not null,
            decision text not null,
            series_requested integer not null,
            series_pass_count integer not null,
            series_warn_count integer not null,
            series_fail_count integer not null,
            raw_rows_written integer not null,
            daily_feature_rows integer not null,
            h1_bars_total integer not null,
            h1_joined_count integer not null,
            h1_unjoined_count integer not null,
            lookahead_violation_count integer not null,
            min_macro_date text,
            max_macro_date text,
            min_h1_bar_ts_utc text,
            max_h1_bar_ts_utc text,
            warning_count integer not null,
            note_count integer not null,
            json_report text,
            md_report text,
            ingested_at_utc text not null
        )
        '''
    )


def insert_dict_rows(con: sqlite3.Connection, table: str, rows: Sequence[Dict[str, Any]]) -> None:
    if not rows:
        return
    keys = list(rows[0].keys())
    cols = ", ".join(f'"{k}"' for k in keys)
    placeholders = ", ".join("?" for _ in keys)
    sql = f'insert or replace into "{table}" ({cols}) values ({placeholders})'
    con.executemany(sql, [[r.get(k) for k in keys] for r in rows])


def fetch_and_store_series(
    con: sqlite3.Connection,
    series_ids: Sequence[str],
    start_date: Optional[date],
    end_date: Optional[date],
    timeout: int,
    retries: int,
    ingested_at: str,
) -> Tuple[List[SeriesFetchResult], int]:
    all_results: List[SeriesFetchResult] = []
    raw_rows_total = 0
    audit_rows: List[Dict[str, Any]] = []

    for sid in series_ids:
        sid = sid.strip().upper()
        url = FRED_CSV_URL.format(series_id=sid)
        text, error = fetch_fred_csv(sid, timeout=timeout, retries=retries)
        if error:
            result = SeriesFetchResult(sid, "FAIL_FETCH", 0, 0, 0, None, None, url, error)
            all_results.append(result)
            audit_rows.append({**result.__dict__, "ingested_at_utc": ingested_at})
            continue

        rows, row_count, missing_count = parse_fred_csv(sid, text, start_date, end_date)
        valid_count = sum(1 for r in rows if r["is_missing"] == 0)
        dates = [r["observation_date"] for r in rows]
        min_d = min(dates) if dates else None
        max_d = max(dates) if dates else None
        status = "PASS" if valid_count >= 100 else ("WARN_LOW_ROWS" if valid_count > 0 else "FAIL_EMPTY")
        result = SeriesFetchResult(sid, status, row_count, valid_count, missing_count, min_d, max_d, url, None)
        all_results.append(result)
        audit_rows.append({**result.__dict__, "ingested_at_utc": ingested_at})

        for r in rows:
            r["ingested_at_utc"] = ingested_at
        insert_dict_rows(con, RAW_TABLE, rows)
        raw_rows_total += len(rows)

    insert_dict_rows(con, SERIES_AUDIT_TABLE, audit_rows)
    return all_results, raw_rows_total


def build_daily_features(con: sqlite3.Connection, series_ids: Sequence[str], ingested_at: str) -> int:
    raw = con.execute(
        f'select series_id, observation_date, value from "{RAW_TABLE}" order by observation_date, series_id'
    ).fetchall()
    by_date: Dict[str, Dict[str, Optional[float]]] = {}
    for sid, obs_date, val in raw:
        by_date.setdefault(obs_date, {})[str(sid).lower()] = val

    dates = sorted(by_date.keys())
    rows: List[Dict[str, Any]] = []

    # Forward fill market daily series over holidays/weekends only for feature continuity.
    # We keep available_from_utc anchored to each observation date + 1 day; no future fill.
    last_vals: Dict[str, Optional[float]] = {sid.lower(): None for sid in series_ids}
    series_lower = [sid.lower() for sid in series_ids]

    def chg(history: List[Optional[float]], lag: int) -> Optional[float]:
        if len(history) <= lag:
            return None
        cur = history[-1]
        prev = history[-1 - lag]
        if cur is None or prev is None:
            return None
        return cur - prev

    histories: Dict[str, List[Optional[float]]] = {sid: [] for sid in series_lower}

    for obs_date in dates:
        current = by_date.get(obs_date, {})
        for sid in series_lower:
            if sid in current and current[sid] is not None:
                last_vals[sid] = current[sid]
            histories[sid].append(last_vals[sid])

        dgs10 = last_vals.get("dgs10")
        dgs2 = last_vals.get("dgs2")
        dfii10 = last_vals.get("dfii10")
        t10yie = last_vals.get("t10yie")
        dtwexbgs = last_vals.get("dtwexbgs")
        vixcls = last_vals.get("vixcls")

        available_series_count = sum(1 for sid in series_lower if last_vals.get(sid) is not None)
        missing_series_count = len(series_lower) - available_series_count
        curve = None if dgs10 is None or dgs2 is None else dgs10 - dgs2

        real_5d = chg(histories.get("dfii10", []), 5)
        nominal_5d = chg(histories.get("dgs10", []), 5)
        dollar_5d = chg(histories.get("dtwexbgs", []), 5)
        vix_5d = chg(histories.get("vixcls", []), 5)

        # Simple descriptive pressure labels, not trading signals.
        pressure_parts = []
        if real_5d is not None:
            pressure_parts.append("REAL_YIELD_UP" if real_5d > 0.05 else "REAL_YIELD_DOWN" if real_5d < -0.05 else "REAL_YIELD_FLAT")
        if dollar_5d is not None:
            pressure_parts.append("USD_UP" if dollar_5d > 0.5 else "USD_DOWN" if dollar_5d < -0.5 else "USD_FLAT")
        macro_gold_pressure = "+".join(pressure_parts) if pressure_parts else "UNKNOWN"

        if vixcls is None:
            risk_state = "UNKNOWN"
        elif vixcls >= 30:
            risk_state = "RISK_STRESS"
        elif vixcls >= 22:
            risk_state = "RISK_ELEVATED"
        elif vixcls <= 14:
            risk_state = "RISK_CALM"
        else:
            risk_state = "RISK_NORMAL"

        obs_d = parse_date(obs_date)
        assert obs_d is not None
        available_from = datetime.combine(obs_d + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)

        rows.append(
            {
                "observation_date": obs_date,
                "available_from_utc": dt_to_iso_z(available_from),
                "dgs10": dgs10,
                "dgs2": dgs2,
                "dfii10": dfii10,
                "t10yie": t10yie,
                "dtwexbgs": dtwexbgs,
                "vixcls": vixcls,
                "curve_10y2y": curve,
                "nominal_10y_chg_1d": chg(histories.get("dgs10", []), 1),
                "nominal_10y_chg_5d": nominal_5d,
                "nominal_10y_chg_20d": chg(histories.get("dgs10", []), 20),
                "real_10y_chg_1d": chg(histories.get("dfii10", []), 1),
                "real_10y_chg_5d": real_5d,
                "real_10y_chg_20d": chg(histories.get("dfii10", []), 20),
                "dollar_chg_1d": chg(histories.get("dtwexbgs", []), 1),
                "dollar_chg_5d": dollar_5d,
                "dollar_chg_20d": chg(histories.get("dtwexbgs", []), 20),
                "vix_chg_1d": chg(histories.get("vixcls", []), 1),
                "vix_chg_5d": vix_5d,
                "vix_chg_20d": chg(histories.get("vixcls", []), 20),
                "macro_gold_pressure": macro_gold_pressure,
                "macro_risk_state": risk_state,
                "available_series_count": available_series_count,
                "missing_series_count": missing_series_count,
                "ingested_at_utc": ingested_at,
            }
        )

    insert_dict_rows(con, DAILY_TABLE, rows)
    return len(rows)


def load_h1_bars(
    con: sqlite3.Connection,
    bars_table: str,
    source: str,
    symbol: str,
    h1_target: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not table_exists(con, bars_table):
        raise RuntimeError(f"bars table not found: {bars_table}")
    cols = get_columns(con, bars_table)
    ts_col = require_column(cols, TIMESTAMP_CANDIDATES, bars_table, "bar timestamp")
    select_cols = [ts_col]
    for c in ["source", "symbol", "timeframe"]:
        if c in cols:
            select_cols.append(c)
    for c in OHLC_COLUMNS:
        if c in cols and c not in select_cols:
            select_cols.append(c)

    aliases = timeframe_aliases(h1_target)
    where = []
    params: List[Any] = []
    if "source" in cols:
        where.append("source = ?")
        params.append(source)
    if "symbol" in cols:
        where.append("symbol = ?")
        params.append(symbol)
    if "timeframe" in cols:
        where.append("timeframe in ({})".format(",".join("?" for _ in aliases)))
        params.extend(aliases)
    where_sql = " where " + " and ".join(where) if where else ""
    sql = f'select {", ".join(f"\"{c}\"" for c in select_cols)} from "{bars_table}"{where_sql} order by "{ts_col}"'

    rows = []
    parse_errors = 0
    for rec in con.execute(sql, params):
        d = dict(zip(select_cols, rec))
        dt = parse_iso_dt(d.get(ts_col))
        if dt is None:
            parse_errors += 1
            continue
        out = {
            "bar_ts_utc": dt_to_iso_z(dt),
            "source": d.get("source", source),
            "symbol": d.get("symbol", symbol),
            "timeframe": normalize_timeframe(str(d.get("timeframe", h1_target))),
        }
        for c in OHLC_COLUMNS:
            out[c] = safe_float(d.get(c)) if c in d else None
        rows.append(out)
    meta = {"parse_errors": parse_errors, "timestamp_column": ts_col, "h1_aliases": aliases}
    return rows, meta


def join_h1_macro(con: sqlite3.Connection, bars: Sequence[Dict[str, Any]], ingested_at: str) -> Tuple[int, int, int]:
    macro_rows = con.execute(
        f'''
        select observation_date, available_from_utc, dgs10, dgs2, dfii10, t10yie, dtwexbgs, vixcls,
               curve_10y2y, nominal_10y_chg_5d, real_10y_chg_5d, dollar_chg_5d, vix_chg_5d,
               macro_gold_pressure, macro_risk_state
        from "{DAILY_TABLE}"
        where available_series_count > 0
        order by available_from_utc
        '''
    ).fetchall()
    macros = [
        {
            "observation_date": r[0],
            "available_from_utc": r[1],
            "dgs10": r[2],
            "dgs2": r[3],
            "dfii10": r[4],
            "t10yie": r[5],
            "dtwexbgs": r[6],
            "vixcls": r[7],
            "curve_10y2y": r[8],
            "nominal_10y_chg_5d": r[9],
            "real_10y_chg_5d": r[10],
            "dollar_chg_5d": r[11],
            "vix_chg_5d": r[12],
            "macro_gold_pressure": r[13],
            "macro_risk_state": r[14],
        }
        for r in macro_rows
    ]

    rows: List[Dict[str, Any]] = []
    mi = -1
    joined = 0
    lookahead = 0
    for b in bars:
        bar_ts = b["bar_ts_utc"]
        while mi + 1 < len(macros) and macros[mi + 1]["available_from_utc"] <= bar_ts:
            mi += 1
        if mi < 0:
            continue
        m = macros[mi]
        violation = 1 if m["available_from_utc"] > bar_ts else 0
        lookahead += violation
        joined += 1
        rows.append(
            {
                "bar_ts_utc": bar_ts,
                "source": b.get("source"),
                "symbol": b.get("symbol"),
                "timeframe": b.get("timeframe"),
                "open": b.get("open"),
                "high": b.get("high"),
                "low": b.get("low"),
                "close": b.get("close"),
                "spread": b.get("spread"),
                "macro_observation_date": m["observation_date"],
                "macro_available_from_utc": m["available_from_utc"],
                "dgs10": m["dgs10"],
                "dgs2": m["dgs2"],
                "dfii10": m["dfii10"],
                "t10yie": m["t10yie"],
                "dtwexbgs": m["dtwexbgs"],
                "vixcls": m["vixcls"],
                "curve_10y2y": m["curve_10y2y"],
                "nominal_10y_chg_5d": m["nominal_10y_chg_5d"],
                "real_10y_chg_5d": m["real_10y_chg_5d"],
                "dollar_chg_5d": m["dollar_chg_5d"],
                "vix_chg_5d": m["vix_chg_5d"],
                "macro_gold_pressure": m["macro_gold_pressure"],
                "macro_risk_state": m["macro_risk_state"],
                "lookahead_violation": violation,
                "ingested_at_utc": ingested_at,
            }
        )
    insert_dict_rows(con, H1_JOIN_TABLE, rows)
    return joined, len(bars) - joined, lookahead


def summarize_decision(
    series_results: Sequence[SeriesFetchResult],
    daily_rows: int,
    h1_total: int,
    joined_count: int,
    lookahead_count: int,
) -> Tuple[str, str, List[str], List[str]]:
    warnings: List[str] = []
    notes: List[str] = []
    pass_count = sum(1 for r in series_results if r.status == "PASS")
    fail_count = sum(1 for r in series_results if r.status.startswith("FAIL"))
    warn_count = sum(1 for r in series_results if r.status.startswith("WARN"))

    if fail_count:
        warnings.append(f"series_fetch_or_empty_failures={fail_count}")
    if warn_count:
        notes.append(f"series_low_row_warnings={warn_count}")
    if daily_rows <= 0:
        warnings.append("no_daily_feature_rows")
    if h1_total <= 0:
        warnings.append("no_h1_bars_loaded")
    if h1_total > 0 and joined_count / h1_total < 0.95:
        warnings.append(f"low_h1_macro_join_coverage={joined_count}/{h1_total}")
    if lookahead_count:
        warnings.append(f"lookahead_violations={lookahead_count}")

    if pass_count >= 4 and daily_rows > 1000 and h1_total > 0 and joined_count == h1_total and lookahead_count == 0:
        status = "PASS"
        decision = "PROCEED_TO_STAGE38E_MACRO_H1_JOIN_REVIEW"
    elif pass_count >= 4 and daily_rows > 1000 and h1_total > 0 and joined_count / max(h1_total, 1) >= 0.95 and lookahead_count == 0:
        status = "PASS_WITH_NOTES"
        decision = "REVIEW_PARTIAL_MACRO_JOIN_COVERAGE"
    else:
        status = "FAIL" if warnings else "WARN"
        decision = "DO_NOT_PROCEED_REPAIR_MACRO_DATA_FIRST"

    notes.append("daily_observations_available_from_next_calendar_day_0000_utc")
    notes.append("macro_features_are_context_only_not_entry_signals")
    return status, decision, warnings, notes


def run(args: argparse.Namespace) -> Dict[str, Any]:
    series_ids = [s.strip().upper() for s in args.series.split(",") if s.strip()]
    if not series_ids:
        raise RuntimeError("No series requested")
    start_date = parse_date(args.start_date) if args.start_date else None
    end_date = parse_date(args.end_date) if args.end_date else None
    ingested_at = utc_now_iso()

    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_report = reports_dir / "stage38e_macro_risk_data_availability_audit.json"
    md_report = reports_dir / "stage38e_macro_risk_data_availability_audit.md"

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    try:
        create_tables(con)
        series_results, raw_rows_written = fetch_and_store_series(
            con,
            series_ids=series_ids,
            start_date=start_date,
            end_date=end_date,
            timeout=args.timeout,
            retries=args.retries,
            ingested_at=ingested_at,
        )
        daily_rows = build_daily_features(con, series_ids=series_ids, ingested_at=ingested_at)
        bars, bars_meta = load_h1_bars(con, args.bars_table, args.source, args.symbol, args.h1_timeframe)
        joined_count, unjoined_count, lookahead_count = join_h1_macro(con, bars, ingested_at)

        pass_count = sum(1 for r in series_results if r.status == "PASS")
        warn_count = sum(1 for r in series_results if r.status.startswith("WARN"))
        fail_count = sum(1 for r in series_results if r.status.startswith("FAIL"))

        macro_bounds = con.execute(
            f'select min(observation_date), max(observation_date) from "{DAILY_TABLE}"'
        ).fetchone()
        h1_bounds = con.execute(
            f'select min(bar_ts_utc), max(bar_ts_utc) from "{H1_JOIN_TABLE}"'
        ).fetchone()

        status, decision, warnings, notes = summarize_decision(
            series_results, daily_rows, len(bars), joined_count, lookahead_count
        )

        audit_row = {
            "status": status,
            "decision": decision,
            "series_requested": len(series_ids),
            "series_pass_count": pass_count,
            "series_warn_count": warn_count,
            "series_fail_count": fail_count,
            "raw_rows_written": raw_rows_written,
            "daily_feature_rows": daily_rows,
            "h1_bars_total": len(bars),
            "h1_joined_count": joined_count,
            "h1_unjoined_count": unjoined_count,
            "lookahead_violation_count": lookahead_count,
            "min_macro_date": macro_bounds[0] if macro_bounds else None,
            "max_macro_date": macro_bounds[1] if macro_bounds else None,
            "min_h1_bar_ts_utc": h1_bounds[0] if h1_bounds else None,
            "max_h1_bar_ts_utc": h1_bounds[1] if h1_bounds else None,
            "warning_count": len(warnings),
            "note_count": len(notes),
            "json_report": str(json_report),
            "md_report": str(md_report),
            "ingested_at_utc": ingested_at,
        }
        insert_dict_rows(con, AUDIT_TABLE, [audit_row])
        con.commit()

        sample_latest = [
            dict(r)
            for r in con.execute(
                f'''
                select observation_date, available_from_utc, dgs10, dgs2, dfii10, t10yie,
                       dtwexbgs, vixcls, curve_10y2y, real_10y_chg_5d, dollar_chg_5d,
                       macro_gold_pressure, macro_risk_state
                from "{DAILY_TABLE}"
                order by observation_date desc
                limit 5
                '''
            ).fetchall()
        ]

        payload: Dict[str, Any] = {
            "audit": audit_row,
            "warnings": warnings,
            "notes": notes,
            "series": [r.__dict__ for r in series_results],
            "bars_meta": bars_meta,
            "sample_latest_daily_features": sample_latest,
            "tables": {
                "raw": RAW_TABLE,
                "series_audit": SERIES_AUDIT_TABLE,
                "daily_features": DAILY_TABLE,
                "h1_joined": H1_JOIN_TABLE,
                "audit": AUDIT_TABLE,
            },
        }
        write_json(json_report, payload)
        write_md(md_report, "Stage38E Macro/Risk Data Availability Audit", payload)
        return payload
    finally:
        con.close()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Stage38E free FRED macro/risk data availability audit")
    p.add_argument("--db", default="data/local/xauusd_local_store.sqlite")
    p.add_argument("--bars-table", default="bars")
    p.add_argument("--source", default="amarkets_mt5")
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--h1-timeframe", default="H1")
    p.add_argument("--series", default=",".join(DEFAULT_SERIES))
    p.add_argument("--start-date", default="2000-01-01")
    p.add_argument("--end-date", default=None)
    p.add_argument("--reports-dir", default="data/reports/stage38e_macro_risk_data_availability_audit")
    p.add_argument("--timeout", type=int, default=45)
    p.add_argument("--retries", type=int, default=3)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = run(args)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    audit = payload["audit"]
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0 if audit["status"] in {"PASS", "PASS_WITH_NOTES"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
