#!/usr/bin/env python3
"""
Stage38B / T3 COT Research Diagnostic

Purpose
-------
Read-only diagnostic for the Stage38B/T3 COT foundation.

This script measures whether descriptive COT positioning states are associated
with different future XAUUSD H1 close-to-close returns. It is intentionally NOT
an entry/exit strategy, NOT an optimized backtest, NOT ML, NOT paper-live, and
NOT Stage39.

Primary methodological guard
----------------------------
COT is weekly. Repeating the same COT state across every H1 bar creates highly
non-independent samples. Therefore this diagnostic reports two levels:

1) event_level:
   One observation per COT report/state episode: the first H1 bar where a given
   cot_as_of_date becomes available in the anti-lookahead joined table. This is
   the PRIMARY level for decision-making.

2) h1_all:
   Every H1 bar. This is a secondary descriptive panel only.

Default inputs
--------------
    cot_gold_h1_features_joined
    cot_gold_t3_feature_states

Default outputs
---------------
    cot_gold_t3_forward_returns
    cot_gold_t3_research_summary
    cot_gold_t3_research_audit

Reports
-------
    data/reports/stage38b_t3_cot_research_diagnostic/stage38b_t3_cot_research_diagnostic.json
    data/reports/stage38b_t3_cot_research_diagnostic/stage38b_t3_cot_research_diagnostic.md

NO-GO guards remain active:
    Stage39: NO-GO
    EA: NO-GO
    paper-live: NO-GO
    live order: NO-GO
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

UTC = dt.timezone.utc

DEFAULT_HORIZONS = [4, 24, 72, 120, 240]

REQUIRED_JOINED_COLUMNS = ["bar_ts_utc", "close", "cot_as_of_date", "cot_available_from_utc"]
REQUIRED_STATE_COLUMNS = ["bar_ts_utc", "cot_state", "cot_pressure", "cot_available_from_utc"]
OPTIONAL_JOINED_COLUMNS = ["open", "high", "low", "spread", "source", "symbol", "timeframe"]
OPTIONAL_STATE_COLUMNS = [
    "cot_as_of_date",
    "open_interest_all",
    "m_money_net_all",
    "m_money_net_pct_oi",
    "m_money_net_zscore_156w",
    "m_money_net_change_1w",
    "prod_merc_net_all",
    "prod_merc_net_pct_oi",
    "cot_extreme_flag",
    "cot_crowding_score",
]

RETURN_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS {table_name} (
    sample_level TEXT NOT NULL,
    bar_ts_utc TEXT NOT NULL,
    horizon_bars INTEGER NOT NULL,
    future_bar_ts_utc TEXT NOT NULL,
    cot_as_of_date TEXT,
    cot_available_from_utc TEXT NOT NULL,
    cot_state TEXT NOT NULL,
    cot_pressure TEXT,
    cot_extreme_flag INTEGER,
    cot_crowding_score REAL,
    open_interest_all REAL,
    m_money_net_all REAL,
    m_money_net_pct_oi REAL,
    m_money_net_zscore_156w REAL,
    m_money_net_change_1w REAL,
    close_t REAL NOT NULL,
    close_fwd REAL NOT NULL,
    return_price REAL NOT NULL,
    return_pct REAL NOT NULL,
    return_bps REAL NOT NULL,
    atr14_h1 REAL,
    return_atr14_h1 REAL,
    spread_t REAL,
    year INTEGER,
    PRIMARY KEY (sample_level, bar_ts_utc, horizon_bars)
)
"""

SUMMARY_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS {table_name} (
    created_utc TEXT NOT NULL,
    sample_level TEXT NOT NULL,
    group_type TEXT NOT NULL,
    group_value TEXT NOT NULL,
    horizon_bars INTEGER NOT NULL,
    sample_count INTEGER NOT NULL,
    first_bar_ts_utc TEXT,
    last_bar_ts_utc TEXT,
    mean_return_price REAL,
    median_return_price REAL,
    mean_return_pct REAL,
    median_return_pct REAL,
    mean_return_bps REAL,
    median_return_bps REAL,
    stdev_return_bps REAL,
    t_stat_mean_bps REAL,
    win_rate_long REAL,
    win_rate_short REAL,
    p10_return_bps REAL,
    p25_return_bps REAL,
    p75_return_bps REAL,
    p90_return_bps REAL,
    min_return_bps REAL,
    max_return_bps REAL,
    mean_return_atr14_h1 REAL,
    diff_vs_neutral_mean_bps REAL,
    diff_vs_all_mean_bps REAL,
    positive_year_count INTEGER,
    negative_year_count INTEGER,
    max_positive_year_share REAL,
    note TEXT,
    PRIMARY KEY (sample_level, group_type, group_value, horizon_bars)
)
"""

AUDIT_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS {table_name} (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_utc TEXT NOT NULL,
    status TEXT NOT NULL,
    joined_table TEXT NOT NULL,
    state_table TEXT NOT NULL,
    returns_table TEXT NOT NULL,
    summary_table TEXT NOT NULL,
    bars_total INTEGER NOT NULL,
    event_count INTEGER NOT NULL,
    returns_written INTEGER NOT NULL,
    summary_rows_written INTEGER NOT NULL,
    lookahead_violation_count INTEGER NOT NULL,
    warning_count INTEGER NOT NULL,
    note_count INTEGER NOT NULL,
    json_report TEXT NOT NULL,
    md_report TEXT NOT NULL
)
"""


def utc_now_iso() -> str:
    return dt.datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_ts(value: Any) -> Optional[dt.datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    s = s.replace(" ", "T")
    try:
        x = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if x.tzinfo is None:
        x = x.replace(tzinfo=UTC)
    return x.astimezone(UTC)


def iso_z(x: Optional[dt.datetime]) -> Optional[str]:
    if x is None:
        return None
    return x.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def safe_int(value: Any) -> Optional[int]:
    v = safe_float(value)
    if v is None:
        return None
    return int(v)


def quote_ident(name: str) -> str:
    if not name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for c in name):
        raise ValueError(f"Unsafe SQLite identifier: {name!r}")
    return f'"{name}"'


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_columns(con: sqlite3.Connection, table: str) -> List[str]:
    rows = con.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall()
    return [r[1] for r in rows]


def require_columns(existing: Sequence[str], required: Sequence[str], table: str) -> None:
    missing = [c for c in required if c not in existing]
    if missing:
        raise RuntimeError(f"Table {table!r} missing required columns {missing}. Existing columns: {list(existing)}")


def quantile(values: Sequence[float], q: float) -> Optional[float]:
    xs = sorted(v for v in values if v is not None and not math.isnan(v))
    if not xs:
        return None
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    return xs[lo] * (hi - pos) + xs[hi] * (pos - lo)


def stdev(values: Sequence[float]) -> Optional[float]:
    xs = [v for v in values if v is not None and not math.isnan(v)]
    n = len(xs)
    if n < 2:
        return None
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


@dataclass
class Config:
    db: str
    joined_table: str
    state_table: str
    returns_table: str
    summary_table: str
    audit_table: str
    reports_dir: str
    horizons: List[int]
    min_event_samples: int
    write_returns_table: bool
    write_summary_table: bool


def select_expr(alias: str, column: str, output: str, existing: Sequence[str]) -> str:
    if column in existing:
        return f"{alias}.{quote_ident(column)} AS {quote_ident(output)}"
    return f"NULL AS {quote_ident(output)}"


def load_rows(con: sqlite3.Connection, cfg: Config) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    joined_cols = get_columns(con, cfg.joined_table)
    state_cols = get_columns(con, cfg.state_table)
    require_columns(joined_cols, REQUIRED_JOINED_COLUMNS, cfg.joined_table)
    require_columns(state_cols, REQUIRED_STATE_COLUMNS, cfg.state_table)

    parts: List[str] = [
        f"j.{quote_ident('bar_ts_utc')} AS bar_ts_utc",
        f"j.{quote_ident('close')} AS close",
        f"j.{quote_ident('cot_as_of_date')} AS joined_cot_as_of_date",
        f"j.{quote_ident('cot_available_from_utc')} AS joined_cot_available_from_utc",
        f"s.{quote_ident('cot_state')} AS cot_state",
        f"s.{quote_ident('cot_pressure')} AS cot_pressure",
        f"s.{quote_ident('cot_available_from_utc')} AS state_cot_available_from_utc",
    ]

    for c in OPTIONAL_JOINED_COLUMNS:
        if c not in {"close"}:
            parts.append(select_expr("j", c, c, joined_cols))
    for c in OPTIONAL_STATE_COLUMNS:
        if c == "cot_as_of_date":
            parts.append(select_expr("s", c, "state_cot_as_of_date", state_cols))
        else:
            parts.append(select_expr("s", c, c, state_cols))

    sql = f"""
    SELECT {', '.join(parts)}
    FROM {quote_ident(cfg.joined_table)} j
    INNER JOIN {quote_ident(cfg.state_table)} s
      ON j.{quote_ident('bar_ts_utc')} = s.{quote_ident('bar_ts_utc')}
    ORDER BY j.{quote_ident('bar_ts_utc')} ASC
    """
    raw = [dict(r) for r in con.execute(sql).fetchall()]

    rows: List[Dict[str, Any]] = []
    malformed_ts = 0
    for r in raw:
        bt = parse_ts(r.get("bar_ts_utc"))
        ca = parse_ts(r.get("state_cot_available_from_utc") or r.get("joined_cot_available_from_utc"))
        close = safe_float(r.get("close"))
        if bt is None or ca is None or close is None:
            malformed_ts += 1
            continue
        row: Dict[str, Any] = {
            "bar_ts_utc": iso_z(bt),
            "bar_dt": bt,
            "close": close,
            "open": safe_float(r.get("open")),
            "high": safe_float(r.get("high")),
            "low": safe_float(r.get("low")),
            "spread": safe_float(r.get("spread")),
            "source": r.get("source"),
            "symbol": r.get("symbol"),
            "timeframe": r.get("timeframe"),
            "cot_as_of_date": r.get("state_cot_as_of_date") or r.get("joined_cot_as_of_date"),
            "cot_available_from_utc": iso_z(ca),
            "cot_available_dt": ca,
            "cot_state": str(r.get("cot_state") or "COT_STATE_UNKNOWN"),
            "cot_pressure": str(r.get("cot_pressure") or "FLOW_UNKNOWN"),
            "cot_extreme_flag": safe_int(r.get("cot_extreme_flag")),
            "cot_crowding_score": safe_float(r.get("cot_crowding_score")),
            "open_interest_all": safe_float(r.get("open_interest_all")),
            "m_money_net_all": safe_float(r.get("m_money_net_all")),
            "m_money_net_pct_oi": safe_float(r.get("m_money_net_pct_oi")),
            "m_money_net_zscore_156w": safe_float(r.get("m_money_net_zscore_156w")),
            "m_money_net_change_1w": safe_float(r.get("m_money_net_change_1w")),
            "prod_merc_net_all": safe_float(r.get("prod_merc_net_all")),
            "prod_merc_net_pct_oi": safe_float(r.get("prod_merc_net_pct_oi")),
        }
        rows.append(row)

    meta = {
        "joined_columns": joined_cols,
        "state_columns": state_cols,
        "malformed_or_missing_rows_skipped": malformed_ts,
        "input_rows": len(raw),
        "loaded_rows": len(rows),
        "has_ohlc": all(c in joined_cols for c in ["high", "low", "close"]),
        "has_spread": "spread" in joined_cols,
    }
    return rows, meta


def add_atr14(rows: List[Dict[str, Any]]) -> None:
    trs: List[Optional[float]] = []
    prev_close: Optional[float] = None
    for r in rows:
        h = safe_float(r.get("high"))
        l = safe_float(r.get("low"))
        c = safe_float(r.get("close"))
        tr: Optional[float] = None
        if h is not None and l is not None:
            candidates = [h - l]
            if prev_close is not None:
                candidates.append(abs(h - prev_close))
                candidates.append(abs(l - prev_close))
            tr = max(candidates)
        trs.append(tr)
        if c is not None:
            prev_close = c

    for i, r in enumerate(rows):
        window = [x for x in trs[max(0, i - 13) : i + 1] if x is not None]
        r["atr14_h1"] = mean(window) if len(window) >= 14 else None


def detect_event_indices(rows: Sequence[Dict[str, Any]]) -> List[int]:
    """First H1 row for each cot_as_of_date in time order."""
    out: List[int] = []
    seen: set[str] = set()
    for i, r in enumerate(rows):
        key = str(r.get("cot_as_of_date") or "")
        if key and key not in seen:
            seen.add(key)
            out.append(i)
    return out


def build_forward_returns(rows: Sequence[Dict[str, Any]], cfg: Config) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    event_indices = set(detect_event_indices(rows))
    n = len(rows)
    returns: List[Dict[str, Any]] = []
    skipped_by_horizon: Dict[str, int] = {}

    levels = {
        "h1_all": range(n),
        "event_level": sorted(event_indices),
    }

    for level, idx_iter in levels.items():
        for i in idx_iter:
            r = rows[i]
            for h in cfg.horizons:
                j = i + h
                if j >= n:
                    skipped_by_horizon[f"{level}:{h}"] = skipped_by_horizon.get(f"{level}:{h}", 0) + 1
                    continue
                f = rows[j]
                close_t = safe_float(r.get("close"))
                close_f = safe_float(f.get("close"))
                if close_t is None or close_f is None or close_t == 0:
                    skipped_by_horizon[f"{level}:{h}:bad_close"] = skipped_by_horizon.get(f"{level}:{h}:bad_close", 0) + 1
                    continue
                ret_price = close_f - close_t
                ret_pct = ret_price / close_t
                ret_bps = ret_pct * 10000.0
                atr = safe_float(r.get("atr14_h1"))
                ret_atr = (ret_price / atr) if atr and atr > 0 else None
                bt = r["bar_dt"]
                returns.append(
                    {
                        "sample_level": level,
                        "bar_ts_utc": r["bar_ts_utc"],
                        "horizon_bars": h,
                        "future_bar_ts_utc": f["bar_ts_utc"],
                        "cot_as_of_date": r.get("cot_as_of_date"),
                        "cot_available_from_utc": r["cot_available_from_utc"],
                        "cot_state": r.get("cot_state"),
                        "cot_pressure": r.get("cot_pressure"),
                        "cot_extreme_flag": r.get("cot_extreme_flag"),
                        "cot_crowding_score": r.get("cot_crowding_score"),
                        "open_interest_all": r.get("open_interest_all"),
                        "m_money_net_all": r.get("m_money_net_all"),
                        "m_money_net_pct_oi": r.get("m_money_net_pct_oi"),
                        "m_money_net_zscore_156w": r.get("m_money_net_zscore_156w"),
                        "m_money_net_change_1w": r.get("m_money_net_change_1w"),
                        "close_t": close_t,
                        "close_fwd": close_f,
                        "return_price": ret_price,
                        "return_pct": ret_pct,
                        "return_bps": ret_bps,
                        "atr14_h1": atr,
                        "return_atr14_h1": ret_atr,
                        "spread_t": r.get("spread"),
                        "year": bt.year,
                    }
                )

    meta = {"event_count": len(event_indices), "skipped_by_horizon": skipped_by_horizon}
    return returns, meta


def summarize_group(rows: Sequence[Dict[str, Any]], created_utc: str, level: str, group_type: str, group_value: str, horizon: int, all_mean: Optional[float], neutral_mean: Optional[float]) -> Dict[str, Any]:
    bps = [float(r["return_bps"]) for r in rows]
    prices = [float(r["return_price"]) for r in rows]
    pcts = [float(r["return_pct"]) for r in rows]
    atrs = [safe_float(r.get("return_atr14_h1")) for r in rows if safe_float(r.get("return_atr14_h1")) is not None]
    sd = stdev(bps)
    m_bps = mean(bps) if bps else None
    t_stat = (m_bps / (sd / math.sqrt(len(bps)))) if (m_bps is not None and sd and len(bps) > 1) else None

    year_sums: Dict[int, float] = {}
    for r in rows:
        y = int(r.get("year") or 0)
        if y:
            year_sums[y] = year_sums.get(y, 0.0) + float(r["return_bps"])
    positive_years = {y: v for y, v in year_sums.items() if v > 0}
    negative_years = {y: v for y, v in year_sums.items() if v < 0}
    total_positive = sum(positive_years.values())
    max_positive_share = (max(positive_years.values()) / total_positive) if total_positive > 0 else None

    note = None
    if group_type == "cot_state" and level == "event_level" and len(rows) < 10:
        note = "low_event_sample_count"

    return {
        "created_utc": created_utc,
        "sample_level": level,
        "group_type": group_type,
        "group_value": group_value,
        "horizon_bars": horizon,
        "sample_count": len(rows),
        "first_bar_ts_utc": min((str(r["bar_ts_utc"]) for r in rows), default=None),
        "last_bar_ts_utc": max((str(r["bar_ts_utc"]) for r in rows), default=None),
        "mean_return_price": mean(prices) if prices else None,
        "median_return_price": median(prices) if prices else None,
        "mean_return_pct": mean(pcts) if pcts else None,
        "median_return_pct": median(pcts) if pcts else None,
        "mean_return_bps": m_bps,
        "median_return_bps": median(bps) if bps else None,
        "stdev_return_bps": sd,
        "t_stat_mean_bps": t_stat,
        "win_rate_long": (sum(1 for x in bps if x > 0) / len(bps)) if bps else None,
        "win_rate_short": (sum(1 for x in bps if x < 0) / len(bps)) if bps else None,
        "p10_return_bps": quantile(bps, 0.10),
        "p25_return_bps": quantile(bps, 0.25),
        "p75_return_bps": quantile(bps, 0.75),
        "p90_return_bps": quantile(bps, 0.90),
        "min_return_bps": min(bps) if bps else None,
        "max_return_bps": max(bps) if bps else None,
        "mean_return_atr14_h1": mean(atrs) if atrs else None,
        "diff_vs_neutral_mean_bps": (m_bps - neutral_mean) if (m_bps is not None and neutral_mean is not None) else None,
        "diff_vs_all_mean_bps": (m_bps - all_mean) if (m_bps is not None and all_mean is not None) else None,
        "positive_year_count": len(positive_years),
        "negative_year_count": len(negative_years),
        "max_positive_year_share": max_positive_share,
        "note": note,
    }


def build_summaries(returns: Sequence[Dict[str, Any]], created_utc: str) -> List[Dict[str, Any]]:
    summaries: List[Dict[str, Any]] = []
    levels = sorted(set(str(r["sample_level"]) for r in returns))
    horizons = sorted(set(int(r["horizon_bars"]) for r in returns))

    for level in levels:
        for h in horizons:
            subset = [r for r in returns if r["sample_level"] == level and int(r["horizon_bars"]) == h]
            if not subset:
                continue
            all_mean = mean(float(r["return_bps"]) for r in subset)
            neutral_subset = [r for r in subset if r.get("cot_state") == "MM_NEUTRAL"]
            neutral_mean = mean(float(r["return_bps"]) for r in neutral_subset) if neutral_subset else None

            groups: List[Tuple[str, str, List[Dict[str, Any]]]] = [("all", "ALL", subset)]
            for group_type in ["cot_state", "cot_pressure"]:
                values = sorted(set(str(r.get(group_type) or "UNKNOWN") for r in subset))
                for v in values:
                    rows = [r for r in subset if str(r.get(group_type) or "UNKNOWN") == v]
                    groups.append((group_type, v, rows))

            for group_type, group_value, rows in groups:
                summaries.append(summarize_group(rows, created_utc, level, group_type, group_value, h, all_mean, neutral_mean))
    return summaries


def write_returns(con: sqlite3.Connection, table: str, rows: Sequence[Dict[str, Any]]) -> None:
    con.execute(f"DROP TABLE IF EXISTS {quote_ident(table)}")
    con.execute(RETURN_TABLE_SCHEMA.format(table_name=quote_ident(table)))
    cols = [
        "sample_level",
        "bar_ts_utc",
        "horizon_bars",
        "future_bar_ts_utc",
        "cot_as_of_date",
        "cot_available_from_utc",
        "cot_state",
        "cot_pressure",
        "cot_extreme_flag",
        "cot_crowding_score",
        "open_interest_all",
        "m_money_net_all",
        "m_money_net_pct_oi",
        "m_money_net_zscore_156w",
        "m_money_net_change_1w",
        "close_t",
        "close_fwd",
        "return_price",
        "return_pct",
        "return_bps",
        "atr14_h1",
        "return_atr14_h1",
        "spread_t",
        "year",
    ]
    placeholders = ",".join("?" for _ in cols)
    sql = f"INSERT INTO {quote_ident(table)} ({', '.join(quote_ident(c) for c in cols)}) VALUES ({placeholders})"
    con.executemany(sql, [[r.get(c) for c in cols] for r in rows])
    con.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_level_horizon_state ON {quote_ident(table)} (sample_level, horizon_bars, cot_state)")
    con.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_bar_ts ON {quote_ident(table)} (bar_ts_utc)")


def write_summaries(con: sqlite3.Connection, table: str, rows: Sequence[Dict[str, Any]]) -> None:
    con.execute(f"DROP TABLE IF EXISTS {quote_ident(table)}")
    con.execute(SUMMARY_TABLE_SCHEMA.format(table_name=quote_ident(table)))
    cols = [
        "created_utc",
        "sample_level",
        "group_type",
        "group_value",
        "horizon_bars",
        "sample_count",
        "first_bar_ts_utc",
        "last_bar_ts_utc",
        "mean_return_price",
        "median_return_price",
        "mean_return_pct",
        "median_return_pct",
        "mean_return_bps",
        "median_return_bps",
        "stdev_return_bps",
        "t_stat_mean_bps",
        "win_rate_long",
        "win_rate_short",
        "p10_return_bps",
        "p25_return_bps",
        "p75_return_bps",
        "p90_return_bps",
        "min_return_bps",
        "max_return_bps",
        "mean_return_atr14_h1",
        "diff_vs_neutral_mean_bps",
        "diff_vs_all_mean_bps",
        "positive_year_count",
        "negative_year_count",
        "max_positive_year_share",
        "note",
    ]
    placeholders = ",".join("?" for _ in cols)
    sql = f"INSERT INTO {quote_ident(table)} ({', '.join(quote_ident(c) for c in cols)}) VALUES ({placeholders})"
    con.executemany(sql, [[r.get(c) for c in cols] for r in rows])


def write_audit(con: sqlite3.Connection, table: str, report: Dict[str, Any]) -> None:
    con.execute(AUDIT_TABLE_SCHEMA.format(table_name=quote_ident(table)))
    cols = [
        "created_utc",
        "status",
        "joined_table",
        "state_table",
        "returns_table",
        "summary_table",
        "bars_total",
        "event_count",
        "returns_written",
        "summary_rows_written",
        "lookahead_violation_count",
        "warning_count",
        "note_count",
        "json_report",
        "md_report",
    ]
    sql = f"INSERT INTO {quote_ident(table)} ({', '.join(quote_ident(c) for c in cols)}) VALUES ({', '.join('?' for _ in cols)})"
    con.execute(sql, [report.get(c) for c in cols])


def fmt_num(v: Any, digits: int = 4) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def top_summary_rows(summaries: Sequence[Dict[str, Any]], level: str, group_type: str, horizon: int) -> List[Dict[str, Any]]:
    rows = [s for s in summaries if s["sample_level"] == level and s["group_type"] == group_type and int(s["horizon_bars"]) == horizon]
    if group_type == "cot_state":
        order = {
            "MM_EXTREME_LONG": 0,
            "MM_LONG_CROWDED": 1,
            "MM_NEUTRAL": 2,
            "MM_SHORT_CROWDED": 3,
            "MM_EXTREME_SHORT": 4,
        }
        return sorted(rows, key=lambda x: order.get(str(x["group_value"]), 99))
    return sorted(rows, key=lambda x: str(x["group_value"]))


def write_json(path: Path, report: Dict[str, Any]) -> None:
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def write_md(path: Path, report: Dict[str, Any]) -> None:
    lines: List[str] = []
    lines.append("# Stage38B / T3 COT Research Diagnostic")
    lines.append("")
    lines.append(f"Generated UTC: `{report['created_utc']}`")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append(f"Status: `{report['status']}`")
    lines.append(f"Decision: `{report['decision']}`")
    lines.append("")
    lines.append("NO-GO guards remain active:")
    for k, v in report["non_go_guards"].items():
        lines.append(f"- `{k}`: `{v}`")
    lines.append("")
    lines.append("## Methodological Guard")
    lines.append("")
    lines.append("COT is weekly. The primary decision panel is `event_level`, one row per first H1 bar after each COT report becomes available. `h1_all` is secondary and non-independent.")
    lines.append("")
    lines.append("## Coverage")
    lines.append("")
    lines.append(f"- Joined table: `{report['joined_table']}`")
    lines.append(f"- State table: `{report['state_table']}`")
    lines.append(f"- Bars loaded: `{report['bars_total']}`")
    lines.append(f"- Event count: `{report['event_count']}`")
    lines.append(f"- Returns written: `{report['returns_written']}`")
    lines.append(f"- Summary rows written: `{report['summary_rows_written']}`")
    lines.append(f"- First bar: `{report['first_bar_ts_utc']}`")
    lines.append(f"- Last bar: `{report['last_bar_ts_utc']}`")
    lines.append(f"- Lookahead violations: `{report['lookahead_violation_count']}`")
    lines.append("")
    lines.append("## Primary Event-Level State Diagnostics")
    for h in report["horizons"]:
        lines.append("")
        lines.append(f"### Horizon `{h}` H1 bars")
        lines.append("")
        lines.append("| COT state | n | mean bps | median bps | win long | diff vs neutral bps | t-stat | +years | -years | max +year share | note |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
        for r in top_summary_rows(report["summary_preview"], "event_level", "cot_state", h):
            lines.append(
                f"| `{r['group_value']}` | {r['sample_count']} | {fmt_num(r['mean_return_bps'], 2)} | {fmt_num(r['median_return_bps'], 2)} | {fmt_num(r['win_rate_long'], 3)} | {fmt_num(r['diff_vs_neutral_mean_bps'], 2)} | {fmt_num(r['t_stat_mean_bps'], 2)} | {r['positive_year_count']} | {r['negative_year_count']} | {fmt_num(r['max_positive_year_share'], 3)} | `{r.get('note') or ''}` |"
            )
    lines.append("")
    lines.append("## Warnings")
    lines.append("")
    if report["warnings"]:
        for w in report["warnings"]:
            lines.append(f"- `{w}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    if report["notes"]:
        for n in report["notes"]:
            lines.append(f"- `{n}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Next Gate")
    lines.append("")
    lines.append("Do not build a strategy from this output alone. Review event-level separation, sample counts, year contribution, and consistency across horizons first.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_report(cfg: Config, meta: Dict[str, Any], rows: Sequence[Dict[str, Any]], returns: Sequence[Dict[str, Any]], summaries: Sequence[Dict[str, Any]], ret_meta: Dict[str, Any], json_path: Path, md_path: Path) -> Dict[str, Any]:
    warnings: List[str] = []
    notes: List[str] = []

    if meta.get("malformed_or_missing_rows_skipped"):
        warnings.append(f"malformed_or_missing_rows_skipped:{meta['malformed_or_missing_rows_skipped']}")
    if not meta.get("has_ohlc"):
        notes.append("ohlc_not_fully_detected_atr14_return_normalization_may_be_null")
    if not meta.get("has_spread"):
        notes.append("spread_not_detected_spread_context_null")

    lookahead = 0
    for r in rows:
        bt = r.get("bar_dt")
        ca = r.get("cot_available_dt")
        if isinstance(bt, dt.datetime) and isinstance(ca, dt.datetime) and ca > bt:
            lookahead += 1
    if lookahead:
        warnings.append(f"lookahead_violation_count:{lookahead}")

    if ret_meta.get("event_count", 0) < cfg.min_event_samples:
        warnings.append(f"event_count_below_min:{ret_meta.get('event_count', 0)}<{cfg.min_event_samples}")

    if ret_meta.get("skipped_by_horizon"):
        notes.append("skipped_tail_rows_by_horizon:" + json.dumps(ret_meta["skipped_by_horizon"], sort_keys=True))

    first_bar = rows[0]["bar_ts_utc"] if rows else None
    last_bar = rows[-1]["bar_ts_utc"] if rows else None

    status = "PASS" if not warnings and rows and returns else "WARN"
    if lookahead or not rows or not returns:
        status = "FAIL"

    # Keep full summaries in JSON; markdown prints event-level state preview.
    report = {
        "created_utc": utc_now_iso(),
        "status": status,
        "decision": "T3_COT_RESEARCH_DIAGNOSTIC_READY_FOR_REVIEW" if status == "PASS" else "T3_COT_RESEARCH_DIAGNOSTIC_NEEDS_REVIEW",
        "db": cfg.db,
        "joined_table": cfg.joined_table,
        "state_table": cfg.state_table,
        "returns_table": cfg.returns_table,
        "summary_table": cfg.summary_table,
        "audit_table": cfg.audit_table,
        "horizons": cfg.horizons,
        "bars_total": len(rows),
        "event_count": int(ret_meta.get("event_count", 0)),
        "returns_written": len(returns) if cfg.write_returns_table else 0,
        "summary_rows_written": len(summaries) if cfg.write_summary_table else 0,
        "first_bar_ts_utc": first_bar,
        "last_bar_ts_utc": last_bar,
        "lookahead_violation_count": lookahead,
        "metadata": meta,
        "return_metadata": ret_meta,
        "warnings": warnings,
        "notes": notes,
        "warning_count": len(warnings),
        "note_count": len(notes),
        "json_report": str(json_path),
        "md_report": str(md_path),
        "summary_preview": summaries,
        "non_go_guards": {
            "stage39": "NO_GO",
            "ea": "NO_GO",
            "paper_live": "NO_GO",
            "live_order": "NO_GO",
        },
    }
    return report


def parse_horizons(value: str) -> List[int]:
    out: List[int] = []
    for part in value.split(","):
        s = part.strip()
        if not s:
            continue
        h = int(s)
        if h <= 0:
            raise argparse.ArgumentTypeError("horizons must be positive integers")
        out.append(h)
    if not out:
        raise argparse.ArgumentTypeError("at least one horizon is required")
    return sorted(set(out))


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage38B/T3 COT state-only forward return diagnostic")
    parser.add_argument("--db", default="data/local/xauusd_local_store.sqlite")
    parser.add_argument("--joined-table", default="cot_gold_h1_features_joined")
    parser.add_argument("--state-table", default="cot_gold_t3_feature_states")
    parser.add_argument("--returns-table", default="cot_gold_t3_forward_returns")
    parser.add_argument("--summary-table", default="cot_gold_t3_research_summary")
    parser.add_argument("--audit-table", default="cot_gold_t3_research_audit")
    parser.add_argument("--reports-dir", default="data/reports/stage38b_t3_cot_research_diagnostic")
    parser.add_argument("--horizons", type=parse_horizons, default=DEFAULT_HORIZONS, help="Comma-separated H1 horizons, e.g. 4,24,72,120,240")
    parser.add_argument("--min-event-samples", type=int, default=50)
    parser.add_argument("--no-write-returns-table", action="store_true")
    parser.add_argument("--no-write-summary-table", action="store_true")
    args = parser.parse_args()

    cfg = Config(
        db=args.db,
        joined_table=args.joined_table,
        state_table=args.state_table,
        returns_table=args.returns_table,
        summary_table=args.summary_table,
        audit_table=args.audit_table,
        reports_dir=args.reports_dir,
        horizons=args.horizons if isinstance(args.horizons, list) else DEFAULT_HORIZONS,
        min_event_samples=args.min_event_samples,
        write_returns_table=not args.no_write_returns_table,
        write_summary_table=not args.no_write_summary_table,
    )

    reports_dir = ensure_dir(cfg.reports_dir)
    json_path = reports_dir / "stage38b_t3_cot_research_diagnostic.json"
    md_path = reports_dir / "stage38b_t3_cot_research_diagnostic.md"

    con = sqlite3.connect(cfg.db)
    con.row_factory = sqlite3.Row
    try:
        rows, meta = load_rows(con, cfg)
        add_atr14(rows)
        returns, ret_meta = build_forward_returns(rows, cfg)
        created_utc = utc_now_iso()
        summaries = build_summaries(returns, created_utc)

        if cfg.write_returns_table:
            write_returns(con, cfg.returns_table, returns)
        if cfg.write_summary_table:
            write_summaries(con, cfg.summary_table, summaries)

        report = build_report(cfg, meta, rows, returns, summaries, ret_meta, json_path, md_path)
        write_json(json_path, report)
        write_md(md_path, report)
        write_audit(con, cfg.audit_table, report)
        con.commit()
    finally:
        con.close()

    print(json.dumps({
        "status": report["status"],
        "decision": report["decision"],
        "bars_total": report["bars_total"],
        "event_count": report["event_count"],
        "returns_written": report["returns_written"],
        "summary_rows_written": report["summary_rows_written"],
        "lookahead_violation_count": report["lookahead_violation_count"],
        "warning_count": report["warning_count"],
        "note_count": report["note_count"],
        "json_report": report["json_report"],
        "md_report": report["md_report"],
        "returns_table": report["returns_table"],
        "summary_table": report["summary_table"],
        "audit_table": report["audit_table"],
    }, ensure_ascii=False, indent=2))

    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
