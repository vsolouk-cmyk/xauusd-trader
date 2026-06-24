#!/usr/bin/env python3
"""
Stage38B / T3 COT Interaction Diagnostic

Purpose
-------
Read-only diagnostic for testing whether CFTC COT positioning adds useful
regime information when combined with structural XAUUSD context.

This script is intentionally NOT a trading strategy, NOT an optimized backtest,
NOT ML, NOT paper-live, NOT EA output, and NOT Stage39.

What it tests
-------------
The previous Stage38B raw COT diagnostic showed that COT state alone is not a
promotable standalone signal. This script therefore tests interactions:

- COT state × T1-like structural expansion state
- COT state × D1 trend bucket
- COT state × H4 trend bucket
- COT state × H1 ATR/price bucket
- COT state × macro long-gold bucket, if a compatible macro table exists

Primary methodological guard
----------------------------
COT is weekly. The PRIMARY panel is event_level: one observation per first H1
bar after a COT report becomes available. The h1_all panel is descriptive only,
because repeated H1 rows within the same COT week are not independent.

Default inputs
--------------
    cot_gold_h1_features_joined
    cot_gold_t3_feature_states
    macro_daily_regime, if present

Default outputs
---------------
    cot_gold_t3_interaction_context
    cot_gold_t3_interaction_forward_returns
    cot_gold_t3_interaction_summary
    cot_gold_t3_interaction_audit

Reports
-------
    data/reports/stage38b_t3_cot_interaction_diagnostic/stage38b_t3_cot_interaction_diagnostic.json
    data/reports/stage38b_t3_cot_interaction_diagnostic/stage38b_t3_cot_interaction_diagnostic.md

NO-GO guards remain active:
    Stage39: NO-GO
    EA: NO-GO
    paper-live: NO-GO
    live order: NO-GO
"""

from __future__ import annotations

import argparse
import bisect
import datetime as dt
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

UTC = dt.timezone.utc

DEFAULT_HORIZONS = [120, 240]

REQUIRED_JOINED_COLUMNS = ["bar_ts_utc", "close", "cot_as_of_date", "cot_available_from_utc"]
REQUIRED_STATE_COLUMNS = ["bar_ts_utc", "cot_state", "cot_available_from_utc"]

MACRO_DATE_CANDIDATES = [
    "date",
    "regime_date",
    "macro_date",
    "utc_date",
    "day",
    "as_of_date",
]
MACRO_SCORE_CANDIDATES = [
    "macro_score_long_gold",
    "long_gold_score",
    "score_long_gold",
    "macro_long_gold_score",
    "gold_macro_score",
    "macro_score",
    "score",
]

CONTEXT_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS {table_name} (
    bar_ts_utc TEXT PRIMARY KEY,
    cot_as_of_date TEXT,
    cot_available_from_utc TEXT NOT NULL,
    cot_state TEXT NOT NULL,
    cot_pressure TEXT,
    close REAL NOT NULL,
    d1_completed_date TEXT,
    d1_close REAL,
    d1_sma50 REAL,
    d1_trend_pct REAL,
    d1_trend_bucket TEXT NOT NULL,
    h4_completed_bucket_utc TEXT,
    h4_close REAL,
    h4_sma50 REAL,
    h4_trend_pct REAL,
    h4_trend_bucket TEXT NOT NULL,
    atr14_h1 REAL,
    atr_pct_price REAL,
    atr_bucket TEXT NOT NULL,
    t1_locked_structural_state TEXT NOT NULL,
    macro_date TEXT,
    macro_score_long_gold REAL,
    macro_bucket TEXT NOT NULL,
    m_money_net_all REAL,
    m_money_net_pct_oi REAL,
    m_money_net_zscore_156w REAL,
    cot_crowding_score REAL
)
"""

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
    d1_trend_bucket TEXT NOT NULL,
    h4_trend_bucket TEXT NOT NULL,
    atr_bucket TEXT NOT NULL,
    t1_locked_structural_state TEXT NOT NULL,
    macro_bucket TEXT NOT NULL,
    close_t REAL NOT NULL,
    close_fwd REAL NOT NULL,
    return_price REAL NOT NULL,
    return_pct REAL NOT NULL,
    return_bps REAL NOT NULL,
    return_atr14_h1 REAL,
    year INTEGER NOT NULL,
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
    mean_return_bps REAL,
    median_return_bps REAL,
    stdev_return_bps REAL,
    t_stat_mean_bps REAL,
    win_rate_long REAL,
    p10_return_bps REAL,
    p25_return_bps REAL,
    p75_return_bps REAL,
    p90_return_bps REAL,
    min_return_bps REAL,
    max_return_bps REAL,
    mean_return_atr14_h1 REAL,
    diff_vs_all_mean_bps REAL,
    diff_vs_cot_state_mean_bps REAL,
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
    macro_table TEXT,
    context_table TEXT NOT NULL,
    returns_table TEXT NOT NULL,
    summary_table TEXT NOT NULL,
    bars_total INTEGER NOT NULL,
    event_count INTEGER NOT NULL,
    context_rows_written INTEGER NOT NULL,
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


def parse_date(value: Any) -> Optional[dt.date]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if "T" in s:
        s = s.split("T", 1)[0]
    if " " in s:
        s = s.split(" ", 1)[0]
    try:
        return dt.date.fromisoformat(s[:10])
    except ValueError:
        return None


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


def quote_ident(name: str) -> str:
    if not name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for c in name):
        raise ValueError(f"Unsafe SQLite identifier: {name!r}")
    return f'"{name}"'


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_tables(con: sqlite3.Connection) -> List[str]:
    return [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]


def get_columns(con: sqlite3.Connection, table: str) -> List[str]:
    return [r[1] for r in con.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall()]


def require_columns(existing: Sequence[str], required: Sequence[str], table: str) -> None:
    missing = [c for c in required if c not in existing]
    if missing:
        raise RuntimeError(f"Table {table!r} missing required columns {missing}. Existing columns: {list(existing)}")


def pick_column(existing: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    for c in candidates:
        if c in existing:
            return c
    return None


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
    if len(xs) < 2:
        return None
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


@dataclass
class Config:
    db: str
    joined_table: str
    state_table: str
    macro_table: str
    context_table: str
    returns_table: str
    summary_table: str
    audit_table: str
    reports_dir: str
    horizons: List[int]
    min_event_samples: int


def select_optional(alias: str, col: str, out: str, existing: Sequence[str]) -> str:
    if col in existing:
        return f"{alias}.{quote_ident(col)} AS {quote_ident(out)}"
    return f"NULL AS {quote_ident(out)}"


def load_core_rows(con: sqlite3.Connection, cfg: Config) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    joined_cols = get_columns(con, cfg.joined_table)
    state_cols = get_columns(con, cfg.state_table)
    require_columns(joined_cols, REQUIRED_JOINED_COLUMNS, cfg.joined_table)
    require_columns(state_cols, REQUIRED_STATE_COLUMNS, cfg.state_table)

    joined_optional = [
        "open", "high", "low", "spread", "source", "symbol", "timeframe",
        "m_money_net_all", "m_money_net_pct_oi", "m_money_net_zscore_156w",
    ]
    state_optional = [
        "cot_pressure", "cot_as_of_date", "m_money_net_all", "m_money_net_pct_oi",
        "m_money_net_zscore_156w", "cot_crowding_score",
    ]

    parts = [
        "j.bar_ts_utc AS bar_ts_utc",
        "j.close AS close",
        "j.cot_as_of_date AS joined_cot_as_of_date",
        "j.cot_available_from_utc AS joined_cot_available_from_utc",
        "s.cot_state AS cot_state",
        "s.cot_available_from_utc AS state_cot_available_from_utc",
    ]
    for c in joined_optional:
        parts.append(select_optional("j", c, f"j_{c}", joined_cols))
    for c in state_optional:
        if c == "cot_as_of_date":
            parts.append(select_optional("s", c, "s_cot_as_of_date", state_cols))
        else:
            parts.append(select_optional("s", c, f"s_{c}", state_cols))

    sql = f"""
    SELECT {', '.join(parts)}
    FROM {quote_ident(cfg.joined_table)} j
    INNER JOIN {quote_ident(cfg.state_table)} s
      ON j.{quote_ident('bar_ts_utc')} = s.{quote_ident('bar_ts_utc')}
    ORDER BY j.{quote_ident('bar_ts_utc')} ASC
    """
    raw = [dict(r) for r in con.execute(sql).fetchall()]
    rows: List[Dict[str, Any]] = []
    skipped = 0
    for r in raw:
        bt = parse_ts(r.get("bar_ts_utc"))
        cot_av = parse_ts(r.get("state_cot_available_from_utc") or r.get("joined_cot_available_from_utc"))
        close = safe_float(r.get("close"))
        if bt is None or cot_av is None or close is None:
            skipped += 1
            continue
        row = {
            "bar_ts_utc": iso_z(bt),
            "bar_dt": bt,
            "close": close,
            "open": safe_float(r.get("j_open")),
            "high": safe_float(r.get("j_high")),
            "low": safe_float(r.get("j_low")),
            "spread": safe_float(r.get("j_spread")),
            "source": r.get("j_source"),
            "symbol": r.get("j_symbol"),
            "timeframe": r.get("j_timeframe"),
            "cot_as_of_date": r.get("s_cot_as_of_date") or r.get("joined_cot_as_of_date"),
            "cot_available_from_utc": iso_z(cot_av),
            "cot_available_dt": cot_av,
            "cot_state": str(r.get("cot_state") or "COT_STATE_UNKNOWN"),
            "cot_pressure": str(r.get("s_cot_pressure") or "FLOW_UNKNOWN"),
            "m_money_net_all": safe_float(r.get("s_m_money_net_all") if r.get("s_m_money_net_all") is not None else r.get("j_m_money_net_all")),
            "m_money_net_pct_oi": safe_float(r.get("s_m_money_net_pct_oi") if r.get("s_m_money_net_pct_oi") is not None else r.get("j_m_money_net_pct_oi")),
            "m_money_net_zscore_156w": safe_float(r.get("s_m_money_net_zscore_156w") if r.get("s_m_money_net_zscore_156w") is not None else r.get("j_m_money_net_zscore_156w")),
            "cot_crowding_score": safe_float(r.get("s_cot_crowding_score")),
        }
        rows.append(row)

    meta = {
        "joined_columns": joined_cols,
        "state_columns": state_cols,
        "input_rows": len(raw),
        "loaded_rows": len(rows),
        "skipped_bad_core_rows": skipped,
        "has_ohlc": all(c in joined_cols for c in ["high", "low", "close"]),
        "has_spread": "spread" in joined_cols,
    }
    return rows, meta


def floor_h4(x: dt.datetime) -> dt.datetime:
    x = x.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    return x.replace(hour=(x.hour // 4) * 4)


def add_atr14_prior(rows: List[Dict[str, Any]]) -> None:
    trs: List[Optional[float]] = []
    prev_close: Optional[float] = None
    for r in rows:
        high = safe_float(r.get("high"))
        low = safe_float(r.get("low"))
        close = safe_float(r.get("close"))
        tr: Optional[float] = None
        if high is not None and low is not None:
            vals = [high - low]
            if prev_close is not None:
                vals.append(abs(high - prev_close))
                vals.append(abs(low - prev_close))
            tr = max(vals)
        trs.append(tr)
        if close is not None:
            prev_close = close

    for i, r in enumerate(rows):
        prev_trs = [x for x in trs[max(0, i - 14): i] if x is not None]
        atr = mean(prev_trs) if len(prev_trs) >= 14 else None
        close = safe_float(r.get("close"))
        r["atr14_h1"] = atr
        r["atr_pct_price"] = (atr / close) if (atr is not None and close and close > 0) else None


def add_completed_h4_context(rows: List[Dict[str, Any]]) -> None:
    # Build completed H4 closes by bucket, using the last H1 close inside each bucket.
    by_bucket: Dict[dt.datetime, float] = {}
    for r in rows:
        bt = r["bar_dt"]
        b = floor_h4(bt)
        by_bucket[b] = float(r["close"])
    buckets = sorted(by_bucket)
    closes = [by_bucket[b] for b in buckets]
    bucket_to_idx = {b: i for i, b in enumerate(buckets)}

    for r in rows:
        current_bucket = floor_h4(r["bar_dt"])
        idx = bisect.bisect_left(buckets, current_bucket) - 1
        if idx < 0:
            r["h4_completed_bucket_utc"] = None
            r["h4_close"] = None
            r["h4_sma50"] = None
            r["h4_trend_pct"] = None
            continue
        h4_close = closes[idx]
        if idx >= 49:
            sma50 = mean(closes[idx - 49: idx + 1])
        else:
            sma50 = None
        r["h4_completed_bucket_utc"] = iso_z(buckets[idx])
        r["h4_close"] = h4_close
        r["h4_sma50"] = sma50
        r["h4_trend_pct"] = ((h4_close - sma50) / sma50) if (sma50 and sma50 != 0) else None


def add_completed_d1_context(rows: List[Dict[str, Any]]) -> None:
    by_date: Dict[dt.date, float] = {}
    for r in rows:
        by_date[r["bar_dt"].date()] = float(r["close"])
    days = sorted(by_date)
    closes = [by_date[d] for d in days]

    for r in rows:
        current_day = r["bar_dt"].date()
        idx = bisect.bisect_left(days, current_day) - 1
        if idx < 0:
            r["d1_completed_date"] = None
            r["d1_close"] = None
            r["d1_sma50"] = None
            r["d1_trend_pct"] = None
            continue
        d1_close = closes[idx]
        if idx >= 49:
            sma50 = mean(closes[idx - 49: idx + 1])
        else:
            sma50 = None
        r["d1_completed_date"] = days[idx].isoformat()
        r["d1_close"] = d1_close
        r["d1_sma50"] = sma50
        r["d1_trend_pct"] = ((d1_close - sma50) / sma50) if (sma50 and sma50 != 0) else None


def bucket_d1(v: Optional[float]) -> str:
    if v is None:
        return "D1_UNKNOWN"
    if v >= 0.05:
        return "D1_STRONG_UP"
    if v >= 0.02:
        return "D1_UP"
    if v <= -0.05:
        return "D1_STRONG_DOWN"
    if v <= -0.02:
        return "D1_DOWN"
    return "D1_NEUTRAL"


def bucket_h4(v: Optional[float]) -> str:
    if v is None:
        return "H4_UNKNOWN"
    if v >= 0.02:
        return "H4_STRONG_UP"
    if v >= 0.005:
        return "H4_UP"
    if v <= -0.02:
        return "H4_STRONG_DOWN"
    if v <= -0.005:
        return "H4_DOWN"
    return "H4_NEUTRAL"


def bucket_atr(v: Optional[float]) -> str:
    if v is None:
        return "ATR_UNKNOWN"
    if v >= 0.003:
        return "ATR_EXPANSION"
    if v >= 0.002:
        return "ATR_NORMAL"
    return "ATR_LOW"


def t1_structural_state(d1: Optional[float], h4: Optional[float], atr: Optional[float]) -> str:
    if d1 is None or h4 is None or atr is None:
        return "T1_STRUCT_UNKNOWN"
    if d1 >= 0.05 and h4 >= 0.02 and atr >= 0.003:
        return "T1_STRUCT_ON"
    return "T1_STRUCT_OFF"


def load_macro(con: sqlite3.Connection, table: str) -> Tuple[List[Tuple[dt.date, float]], Dict[str, Any]]:
    tables = get_tables(con)
    if table not in tables:
        return [], {"macro_available": False, "reason": f"table_not_found:{table}"}
    cols = get_columns(con, table)
    date_col = pick_column(cols, MACRO_DATE_CANDIDATES)
    score_col = pick_column(cols, MACRO_SCORE_CANDIDATES)
    if not date_col or not score_col:
        return [], {
            "macro_available": False,
            "reason": "date_or_score_column_not_detected",
            "columns": cols,
            "date_col": date_col,
            "score_col": score_col,
        }
    sql = f"SELECT {quote_ident(date_col)} AS d, {quote_ident(score_col)} AS s FROM {quote_ident(table)} ORDER BY {quote_ident(date_col)} ASC"
    out: List[Tuple[dt.date, float]] = []
    for r in con.execute(sql).fetchall():
        d = parse_date(r[0])
        s = safe_float(r[1])
        if d is not None and s is not None:
            out.append((d, s))
    return out, {"macro_available": bool(out), "table": table, "date_col": date_col, "score_col": score_col, "row_count": len(out)}


def add_macro_context(rows: List[Dict[str, Any]], macro_rows: Sequence[Tuple[dt.date, float]]) -> Dict[str, Any]:
    if not macro_rows:
        for r in rows:
            r["macro_date"] = None
            r["macro_score_long_gold"] = None
            r["macro_bucket"] = "MACRO_UNKNOWN"
        return {"macro_context_rows": 0, "macro_bucket_mode": "unavailable"}

    m_dates = [d for d, _ in macro_rows]
    m_scores = [s for _, s in macro_rows]
    q33 = quantile(m_scores, 0.3333)
    q66 = quantile(m_scores, 0.6667)
    use_sign = (q33 is None or q66 is None or abs(q66 - q33) < 1e-12)

    assigned = 0
    for r in rows:
        bd = r["bar_dt"].date()
        idx = bisect.bisect_right(m_dates, bd) - 1
        if idx < 0:
            r["macro_date"] = None
            r["macro_score_long_gold"] = None
            r["macro_bucket"] = "MACRO_UNKNOWN"
            continue
        d, s = macro_rows[idx]
        r["macro_date"] = d.isoformat()
        r["macro_score_long_gold"] = s
        assigned += 1
        if use_sign:
            if s > 0:
                r["macro_bucket"] = "MACRO_BULLISH"
            elif s < 0:
                r["macro_bucket"] = "MACRO_BEARISH"
            else:
                r["macro_bucket"] = "MACRO_NEUTRAL"
        else:
            if s >= q66:  # type: ignore[operator]
                r["macro_bucket"] = "MACRO_HIGH"
            elif s <= q33:  # type: ignore[operator]
                r["macro_bucket"] = "MACRO_LOW"
            else:
                r["macro_bucket"] = "MACRO_MID"
    return {"macro_context_rows": assigned, "macro_bucket_mode": "sign" if use_sign else "tertile", "q33": q33, "q66": q66}


def add_context(rows: List[Dict[str, Any]], macro_rows: Sequence[Tuple[dt.date, float]]) -> Dict[str, Any]:
    add_atr14_prior(rows)
    add_completed_h4_context(rows)
    add_completed_d1_context(rows)
    macro_meta = add_macro_context(rows, macro_rows)
    for r in rows:
        r["d1_trend_bucket"] = bucket_d1(safe_float(r.get("d1_trend_pct")))
        r["h4_trend_bucket"] = bucket_h4(safe_float(r.get("h4_trend_pct")))
        r["atr_bucket"] = bucket_atr(safe_float(r.get("atr_pct_price")))
        r["t1_locked_structural_state"] = t1_structural_state(
            safe_float(r.get("d1_trend_pct")),
            safe_float(r.get("h4_trend_pct")),
            safe_float(r.get("atr_pct_price")),
        )
    counts: Dict[str, Dict[str, int]] = {}
    for key in ["d1_trend_bucket", "h4_trend_bucket", "atr_bucket", "t1_locked_structural_state", "macro_bucket"]:
        d: Dict[str, int] = {}
        for r in rows:
            v = str(r.get(key) or "UNKNOWN")
            d[v] = d.get(v, 0) + 1
        counts[key] = d
    return {"bucket_counts": counts, **macro_meta}


def detect_event_indices(rows: Sequence[Dict[str, Any]]) -> List[int]:
    seen: set[str] = set()
    out: List[int] = []
    for i, r in enumerate(rows):
        k = str(r.get("cot_as_of_date") or "")
        if k and k not in seen:
            seen.add(k)
            out.append(i)
    return out


def build_forward_returns(rows: Sequence[Dict[str, Any]], horizons: Sequence[int]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    n = len(rows)
    event_indices = set(detect_event_indices(rows))
    ret_rows: List[Dict[str, Any]] = []
    skipped: Dict[str, int] = {}
    levels = {"h1_all": range(n), "event_level": sorted(event_indices)}
    for level, idx_iter in levels.items():
        for i in idx_iter:
            r = rows[i]
            for h in horizons:
                j = i + h
                if j >= n:
                    skipped[f"{level}:{h}:end_of_data"] = skipped.get(f"{level}:{h}:end_of_data", 0) + 1
                    continue
                f = rows[j]
                c0 = safe_float(r.get("close"))
                c1 = safe_float(f.get("close"))
                if c0 is None or c1 is None or c0 == 0:
                    skipped[f"{level}:{h}:bad_close"] = skipped.get(f"{level}:{h}:bad_close", 0) + 1
                    continue
                ret_price = c1 - c0
                ret_pct = ret_price / c0
                atr = safe_float(r.get("atr14_h1"))
                ret_rows.append({
                    "sample_level": level,
                    "bar_ts_utc": r["bar_ts_utc"],
                    "horizon_bars": h,
                    "future_bar_ts_utc": f["bar_ts_utc"],
                    "cot_as_of_date": r.get("cot_as_of_date"),
                    "cot_available_from_utc": r["cot_available_from_utc"],
                    "cot_state": r.get("cot_state") or "COT_STATE_UNKNOWN",
                    "cot_pressure": r.get("cot_pressure") or "FLOW_UNKNOWN",
                    "d1_trend_bucket": r.get("d1_trend_bucket") or "D1_UNKNOWN",
                    "h4_trend_bucket": r.get("h4_trend_bucket") or "H4_UNKNOWN",
                    "atr_bucket": r.get("atr_bucket") or "ATR_UNKNOWN",
                    "t1_locked_structural_state": r.get("t1_locked_structural_state") or "T1_STRUCT_UNKNOWN",
                    "macro_bucket": r.get("macro_bucket") or "MACRO_UNKNOWN",
                    "close_t": c0,
                    "close_fwd": c1,
                    "return_price": ret_price,
                    "return_pct": ret_pct,
                    "return_bps": ret_pct * 10000.0,
                    "return_atr14_h1": (ret_price / atr) if atr and atr > 0 else None,
                    "year": r["bar_dt"].year,
                })
    return ret_rows, {"event_count": len(event_indices), "skipped_by_horizon": skipped}


def interaction_key(r: Dict[str, Any], group_type: str) -> str:
    cot = str(r.get("cot_state") or "COT_STATE_UNKNOWN")
    if group_type == "all":
        return "ALL"
    if group_type == "cot_state":
        return cot
    if group_type == "t1_locked_structural_state":
        return str(r.get("t1_locked_structural_state") or "T1_STRUCT_UNKNOWN")
    if group_type == "d1_trend_bucket":
        return str(r.get("d1_trend_bucket") or "D1_UNKNOWN")
    if group_type == "h4_trend_bucket":
        return str(r.get("h4_trend_bucket") or "H4_UNKNOWN")
    if group_type == "atr_bucket":
        return str(r.get("atr_bucket") or "ATR_UNKNOWN")
    if group_type == "macro_bucket":
        return str(r.get("macro_bucket") or "MACRO_UNKNOWN")
    if group_type == "cot_state_x_t1_structural":
        return f"{cot}__{r.get('t1_locked_structural_state') or 'T1_STRUCT_UNKNOWN'}"
    if group_type == "cot_state_x_d1_bucket":
        return f"{cot}__{r.get('d1_trend_bucket') or 'D1_UNKNOWN'}"
    if group_type == "cot_state_x_h4_bucket":
        return f"{cot}__{r.get('h4_trend_bucket') or 'H4_UNKNOWN'}"
    if group_type == "cot_state_x_atr_bucket":
        return f"{cot}__{r.get('atr_bucket') or 'ATR_UNKNOWN'}"
    if group_type == "cot_state_x_macro_bucket":
        return f"{cot}__{r.get('macro_bucket') or 'MACRO_UNKNOWN'}"
    raise ValueError(f"Unsupported group_type: {group_type}")


def parent_cot_state(group_value: str) -> Optional[str]:
    if "__" in group_value:
        return group_value.split("__", 1)[0]
    if group_value.startswith("MM_"):
        return group_value
    return None


def summarize_group(
    rows: Sequence[Dict[str, Any]],
    created_utc: str,
    level: str,
    group_type: str,
    group_value: str,
    horizon: int,
    all_mean: Optional[float],
    cot_state_means: Dict[str, float],
    min_event_samples: int,
) -> Dict[str, Any]:
    vals = [float(r["return_bps"]) for r in rows]
    n = len(vals)
    m = mean(vals) if vals else None
    med = median(vals) if vals else None
    sd = stdev(vals)
    tstat = (m / (sd / math.sqrt(n))) if (m is not None and sd and n > 1) else None
    years: Dict[int, float] = {}
    for r in rows:
        y = int(r["year"])
        years[y] = years.get(y, 0.0) + float(r["return_bps"])
    positive_years = {y: v for y, v in years.items() if v > 0}
    negative_years = {y: v for y, v in years.items() if v < 0}
    pos_total = sum(positive_years.values())
    max_pos_share = (max(positive_years.values()) / pos_total) if pos_total > 0 and positive_years else None
    atr_vals = [float(r["return_atr14_h1"]) for r in rows if r.get("return_atr14_h1") is not None]
    note: Optional[str] = None
    if level == "event_level" and group_type.startswith("cot_state_x") and n < min_event_samples:
        note = f"LOW_EVENT_SAMPLE_LT_{min_event_samples}"
    if max_pos_share is not None and max_pos_share >= 0.80:
        note = f"{note};YEAR_CONCENTRATED" if note else "YEAR_CONCENTRATED"
    p_cot = parent_cot_state(group_value)
    cot_mean = cot_state_means.get(p_cot) if p_cot else None
    return {
        "created_utc": created_utc,
        "sample_level": level,
        "group_type": group_type,
        "group_value": group_value,
        "horizon_bars": horizon,
        "sample_count": n,
        "first_bar_ts_utc": min((str(r["bar_ts_utc"]) for r in rows), default=None),
        "last_bar_ts_utc": max((str(r["bar_ts_utc"]) for r in rows), default=None),
        "mean_return_bps": m,
        "median_return_bps": med,
        "stdev_return_bps": sd,
        "t_stat_mean_bps": tstat,
        "win_rate_long": (sum(1 for v in vals if v > 0) / n) if n else None,
        "p10_return_bps": quantile(vals, 0.10),
        "p25_return_bps": quantile(vals, 0.25),
        "p75_return_bps": quantile(vals, 0.75),
        "p90_return_bps": quantile(vals, 0.90),
        "min_return_bps": min(vals) if vals else None,
        "max_return_bps": max(vals) if vals else None,
        "mean_return_atr14_h1": mean(atr_vals) if atr_vals else None,
        "diff_vs_all_mean_bps": (m - all_mean) if (m is not None and all_mean is not None) else None,
        "diff_vs_cot_state_mean_bps": (m - cot_mean) if (m is not None and cot_mean is not None) else None,
        "positive_year_count": len(positive_years),
        "negative_year_count": len(negative_years),
        "max_positive_year_share": max_pos_share,
        "note": note,
    }


def build_summaries(returns: Sequence[Dict[str, Any]], created_utc: str, min_event_samples: int, include_macro: bool) -> List[Dict[str, Any]]:
    summaries: List[Dict[str, Any]] = []
    levels = sorted(set(str(r["sample_level"]) for r in returns))
    horizons = sorted(set(int(r["horizon_bars"]) for r in returns))
    base_group_types = [
        "all",
        "cot_state",
        "t1_locked_structural_state",
        "d1_trend_bucket",
        "h4_trend_bucket",
        "atr_bucket",
        "cot_state_x_t1_structural",
        "cot_state_x_d1_bucket",
        "cot_state_x_h4_bucket",
        "cot_state_x_atr_bucket",
    ]
    if include_macro:
        base_group_types.extend(["macro_bucket", "cot_state_x_macro_bucket"])

    for level in levels:
        for h in horizons:
            subset = [r for r in returns if r["sample_level"] == level and int(r["horizon_bars"]) == h]
            if not subset:
                continue
            all_mean = mean(float(r["return_bps"]) for r in subset)
            cot_state_means: Dict[str, float] = {}
            for cot in sorted(set(str(r.get("cot_state") or "UNKNOWN") for r in subset)):
                cot_rows = [r for r in subset if str(r.get("cot_state") or "UNKNOWN") == cot]
                cot_state_means[cot] = mean(float(r["return_bps"]) for r in cot_rows)

            for group_type in base_group_types:
                grouped: Dict[str, List[Dict[str, Any]]] = {}
                for r in subset:
                    key = interaction_key(r, group_type)
                    grouped.setdefault(key, []).append(r)
                for key in sorted(grouped):
                    summaries.append(
                        summarize_group(grouped[key], created_utc, level, group_type, key, h, all_mean, cot_state_means, min_event_samples)
                    )
    return summaries


def write_context(con: sqlite3.Connection, table: str, rows: Sequence[Dict[str, Any]]) -> None:
    con.execute(f"DROP TABLE IF EXISTS {quote_ident(table)}")
    con.execute(CONTEXT_TABLE_SCHEMA.format(table_name=quote_ident(table)))
    cols = [
        "bar_ts_utc", "cot_as_of_date", "cot_available_from_utc", "cot_state", "cot_pressure", "close",
        "d1_completed_date", "d1_close", "d1_sma50", "d1_trend_pct", "d1_trend_bucket",
        "h4_completed_bucket_utc", "h4_close", "h4_sma50", "h4_trend_pct", "h4_trend_bucket",
        "atr14_h1", "atr_pct_price", "atr_bucket", "t1_locked_structural_state",
        "macro_date", "macro_score_long_gold", "macro_bucket",
        "m_money_net_all", "m_money_net_pct_oi", "m_money_net_zscore_156w", "cot_crowding_score",
    ]
    sql = f"INSERT INTO {quote_ident(table)} ({', '.join(quote_ident(c) for c in cols)}) VALUES ({', '.join('?' for _ in cols)})"
    con.executemany(sql, [[r.get(c) for c in cols] for r in rows])
    con.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_cot_state ON {quote_ident(table)} (cot_state)")
    con.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_t1 ON {quote_ident(table)} (t1_locked_structural_state)")


def write_returns(con: sqlite3.Connection, table: str, rows: Sequence[Dict[str, Any]]) -> None:
    con.execute(f"DROP TABLE IF EXISTS {quote_ident(table)}")
    con.execute(RETURN_TABLE_SCHEMA.format(table_name=quote_ident(table)))
    cols = [
        "sample_level", "bar_ts_utc", "horizon_bars", "future_bar_ts_utc",
        "cot_as_of_date", "cot_available_from_utc", "cot_state", "cot_pressure",
        "d1_trend_bucket", "h4_trend_bucket", "atr_bucket", "t1_locked_structural_state", "macro_bucket",
        "close_t", "close_fwd", "return_price", "return_pct", "return_bps", "return_atr14_h1", "year",
    ]
    sql = f"INSERT INTO {quote_ident(table)} ({', '.join(quote_ident(c) for c in cols)}) VALUES ({', '.join('?' for _ in cols)})"
    con.executemany(sql, [[r.get(c) for c in cols] for r in rows])
    con.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_level_h_group ON {quote_ident(table)} (sample_level, horizon_bars, cot_state)")


def write_summaries(con: sqlite3.Connection, table: str, rows: Sequence[Dict[str, Any]]) -> None:
    con.execute(f"DROP TABLE IF EXISTS {quote_ident(table)}")
    con.execute(SUMMARY_TABLE_SCHEMA.format(table_name=quote_ident(table)))
    cols = [
        "created_utc", "sample_level", "group_type", "group_value", "horizon_bars", "sample_count",
        "first_bar_ts_utc", "last_bar_ts_utc", "mean_return_bps", "median_return_bps",
        "stdev_return_bps", "t_stat_mean_bps", "win_rate_long", "p10_return_bps", "p25_return_bps",
        "p75_return_bps", "p90_return_bps", "min_return_bps", "max_return_bps", "mean_return_atr14_h1",
        "diff_vs_all_mean_bps", "diff_vs_cot_state_mean_bps", "positive_year_count", "negative_year_count",
        "max_positive_year_share", "note",
    ]
    sql = f"INSERT INTO {quote_ident(table)} ({', '.join(quote_ident(c) for c in cols)}) VALUES ({', '.join('?' for _ in cols)})"
    con.executemany(sql, [[r.get(c) for c in cols] for r in rows])


def write_audit(con: sqlite3.Connection, table: str, report: Dict[str, Any]) -> None:
    con.execute(AUDIT_TABLE_SCHEMA.format(table_name=quote_ident(table)))
    cols = [
        "created_utc", "status", "joined_table", "state_table", "macro_table", "context_table",
        "returns_table", "summary_table", "bars_total", "event_count", "context_rows_written",
        "returns_written", "summary_rows_written", "lookahead_violation_count", "warning_count", "note_count",
        "json_report", "md_report",
    ]
    sql = f"INSERT INTO {quote_ident(table)} ({', '.join(quote_ident(c) for c in cols)}) VALUES ({', '.join('?' for _ in cols)})"
    con.execute(sql, [report.get(c) for c in cols])


def fmt(v: Any, digits: int = 2) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def preview_summaries(summaries: Sequence[Dict[str, Any]], limit_per_group: int = 20) -> List[Dict[str, Any]]:
    keep_types = [
        "cot_state_x_t1_structural",
        "cot_state_x_d1_bucket",
        "cot_state_x_h4_bucket",
        "cot_state_x_atr_bucket",
        "cot_state_x_macro_bucket",
    ]
    out: List[Dict[str, Any]] = []
    for h in sorted(set(int(s["horizon_bars"]) for s in summaries)):
        for gt in keep_types:
            rows = [s for s in summaries if s["sample_level"] == "event_level" and s["group_type"] == gt and int(s["horizon_bars"]) == h]
            rows = sorted(rows, key=lambda x: (-(x.get("sample_count") or 0), str(x.get("group_value"))))[:limit_per_group]
            out.extend(rows)
    return out


def write_json(path: Path, report: Dict[str, Any]) -> None:
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def write_md(path: Path, report: Dict[str, Any]) -> None:
    lines: List[str] = []
    lines.append("# Stage38B / T3 COT Interaction Diagnostic")
    lines.append("")
    lines.append(f"Generated UTC: `{report['created_utc']}`")
    lines.append("")
    lines.append("## Decision Gate")
    lines.append("")
    lines.append(f"Status: `{report['status']}`")
    lines.append(f"Decision: `{report['decision']}`")
    lines.append("")
    lines.append("NO-GO guards remain active:")
    for k, v in report["non_go_guards"].items():
        lines.append(f"- `{k}`: `{v}`")
    lines.append("")
    lines.append("## Method")
    lines.append("")
    lines.append("This is a read-only interaction diagnostic. It checks whether COT state separates future H1 returns better when combined with completed D1 trend, completed H4 trend, prior H1 ATR/price, and macro context if available. It is not a strategy or backtest.")
    lines.append("")
    lines.append("Primary decision panel: `event_level`, one row per first H1 bar after each COT report becomes available.")
    lines.append("")
    lines.append("## Coverage")
    lines.append("")
    for k in ["bars_total", "event_count", "context_rows_written", "returns_written", "summary_rows_written", "lookahead_violation_count"]:
        lines.append(f"- {k}: `{report[k]}`")
    lines.append(f"- first_bar_ts_utc: `{report['first_bar_ts_utc']}`")
    lines.append(f"- last_bar_ts_utc: `{report['last_bar_ts_utc']}`")
    lines.append("")
    lines.append("## Context Bucket Counts")
    lines.append("")
    for key, values in report["context_meta"].get("bucket_counts", {}).items():
        lines.append(f"### `{key}`")
        for v, n in sorted(values.items(), key=lambda x: (-x[1], x[0])):
            lines.append(f"- `{v}`: `{n}`")
        lines.append("")
    lines.append("## Primary Event-Level Interaction Preview")
    lines.append("")
    lines.append("Rows below are sorted by interaction family and sample size. Use them for review, not promotion.")
    for h in report["horizons"]:
        lines.append("")
        lines.append(f"### Horizon `{h}` H1 bars")
        for gt in ["cot_state_x_t1_structural", "cot_state_x_d1_bucket", "cot_state_x_h4_bucket", "cot_state_x_atr_bucket", "cot_state_x_macro_bucket"]:
            rows = [r for r in report["summary_preview"] if r["sample_level"] == "event_level" and r["group_type"] == gt and int(r["horizon_bars"]) == h]
            if not rows:
                continue
            lines.append("")
            lines.append(f"#### `{gt}`")
            lines.append("")
            lines.append("| group | n | mean bps | median bps | win long | diff vs COT state | +years | -years | max +year share | note |")
            lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
            for r in rows:
                lines.append(
                    f"| `{r['group_value']}` | {r['sample_count']} | {fmt(r['mean_return_bps'], 2)} | {fmt(r['median_return_bps'], 2)} | {fmt(r['win_rate_long'], 3)} | {fmt(r['diff_vs_cot_state_mean_bps'], 2)} | {r['positive_year_count']} | {r['negative_year_count']} | {fmt(r['max_positive_year_share'], 3)} | `{r.get('note') or ''}` |"
                )
    lines.append("")
    lines.append("## Warnings")
    if report["warnings"]:
        for w in report["warnings"]:
            lines.append(f"- `{w}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Notes")
    if report["notes"]:
        for n in report["notes"]:
            lines.append(f"- `{n}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Next Gate")
    lines.append("")
    lines.append("If interaction separation is weak or year-concentrated, T3 must remain a secondary filter or be downgraded. If interaction separation is robust, the next step is a design review before any baseline/backtest construction.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_report(
    cfg: Config,
    rows: Sequence[Dict[str, Any]],
    base_meta: Dict[str, Any],
    macro_meta: Dict[str, Any],
    context_meta: Dict[str, Any],
    ret_meta: Dict[str, Any],
    returns: Sequence[Dict[str, Any]],
    summaries: Sequence[Dict[str, Any]],
    json_path: Path,
    md_path: Path,
) -> Dict[str, Any]:
    warnings: List[str] = []
    notes: List[str] = []
    if base_meta.get("skipped_bad_core_rows"):
        warnings.append(f"skipped_bad_core_rows:{base_meta['skipped_bad_core_rows']}")
    if not base_meta.get("has_ohlc"):
        warnings.append("ohlc_not_fully_available_structural_context_degraded")
    if not macro_meta.get("macro_available"):
        notes.append(f"macro_context_unavailable:{macro_meta.get('reason')}")
    if context_meta.get("bucket_counts", {}).get("t1_locked_structural_state", {}).get("T1_STRUCT_UNKNOWN", 0) > 0:
        notes.append(f"t1_structural_unknown_rows:{context_meta['bucket_counts']['t1_locked_structural_state'].get('T1_STRUCT_UNKNOWN', 0)}")

    lookahead = 0
    for r in rows:
        bt = r.get("bar_dt")
        ca = r.get("cot_available_dt")
        if isinstance(bt, dt.datetime) and isinstance(ca, dt.datetime) and ca > bt:
            lookahead += 1
    if lookahead:
        warnings.append(f"lookahead_violations:{lookahead}")

    status = "PASS" if rows and returns and summaries and lookahead == 0 and not any(w.startswith("lookahead") for w in warnings) else "REVIEW"
    decision = "INTERACTION_REVIEW_REQUIRED_BEFORE_BACKTEST"

    preview = preview_summaries(summaries)
    first_ts = rows[0]["bar_ts_utc"] if rows else None
    last_ts = rows[-1]["bar_ts_utc"] if rows else None
    report = {
        "created_utc": utc_now_iso(),
        "status": status,
        "decision": decision,
        "joined_table": cfg.joined_table,
        "state_table": cfg.state_table,
        "macro_table": cfg.macro_table if macro_meta.get("macro_available") else None,
        "context_table": cfg.context_table,
        "returns_table": cfg.returns_table,
        "summary_table": cfg.summary_table,
        "bars_total": len(rows),
        "event_count": ret_meta.get("event_count", 0),
        "context_rows_written": len(rows),
        "returns_written": len(returns),
        "summary_rows_written": len(summaries),
        "lookahead_violation_count": lookahead,
        "warning_count": len(warnings),
        "note_count": len(notes),
        "warnings": warnings,
        "notes": notes,
        "base_meta": base_meta,
        "macro_meta": macro_meta,
        "context_meta": context_meta,
        "return_meta": ret_meta,
        "horizons": cfg.horizons,
        "first_bar_ts_utc": first_ts,
        "last_bar_ts_utc": last_ts,
        "json_report": str(json_path),
        "md_report": str(md_path),
        "summary_preview": preview,
        "non_go_guards": {
            "Stage39": "NO_GO",
            "EA": "NO_GO",
            "paper_live": "NO_GO",
            "live_order": "NO_GO",
        },
    }
    return report


def parse_horizons(s: str) -> List[int]:
    out: List[int] = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        v = int(part)
        if v <= 0:
            raise ValueError("Horizon values must be positive")
        out.append(v)
    if not out:
        raise ValueError("At least one horizon is required")
    return sorted(set(out))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stage38B / T3 COT interaction diagnostic. Read-only; no strategy/orders.")
    p.add_argument("--db", default="data/local/xauusd_local_store.sqlite")
    p.add_argument("--joined-table", default="cot_gold_h1_features_joined")
    p.add_argument("--state-table", default="cot_gold_t3_feature_states")
    p.add_argument("--macro-table", default="macro_daily_regime")
    p.add_argument("--context-table", default="cot_gold_t3_interaction_context")
    p.add_argument("--returns-table", default="cot_gold_t3_interaction_forward_returns")
    p.add_argument("--summary-table", default="cot_gold_t3_interaction_summary")
    p.add_argument("--audit-table", default="cot_gold_t3_interaction_audit")
    p.add_argument("--reports-dir", default="data/reports/stage38b_t3_cot_interaction_diagnostic")
    p.add_argument("--horizons", default=",".join(str(x) for x in DEFAULT_HORIZONS))
    p.add_argument("--min-event-samples", type=int, default=8)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    cfg = Config(
        db=args.db,
        joined_table=args.joined_table,
        state_table=args.state_table,
        macro_table=args.macro_table,
        context_table=args.context_table,
        returns_table=args.returns_table,
        summary_table=args.summary_table,
        audit_table=args.audit_table,
        reports_dir=args.reports_dir,
        horizons=parse_horizons(args.horizons),
        min_event_samples=args.min_event_samples,
    )

    reports_dir = ensure_dir(cfg.reports_dir)
    json_path = reports_dir / "stage38b_t3_cot_interaction_diagnostic.json"
    md_path = reports_dir / "stage38b_t3_cot_interaction_diagnostic.md"

    con = sqlite3.connect(cfg.db)
    con.row_factory = sqlite3.Row
    try:
        rows, base_meta = load_core_rows(con, cfg)
        macro_rows, macro_meta = load_macro(con, cfg.macro_table)
        context_meta = add_context(rows, macro_rows)
        returns, ret_meta = build_forward_returns(rows, cfg.horizons)
        created_utc = utc_now_iso()
        include_macro = bool(macro_meta.get("macro_available"))
        summaries = build_summaries(returns, created_utc, cfg.min_event_samples, include_macro=include_macro)

        with con:
            write_context(con, cfg.context_table, rows)
            write_returns(con, cfg.returns_table, returns)
            write_summaries(con, cfg.summary_table, summaries)

        report = build_report(cfg, rows, base_meta, macro_meta, context_meta, ret_meta, returns, summaries, json_path, md_path)
        write_json(json_path, report)
        write_md(md_path, report)

        with con:
            write_audit(con, cfg.audit_table, report)

        print(json.dumps({
            "status": report["status"],
            "decision": report["decision"],
            "bars_total": report["bars_total"],
            "event_count": report["event_count"],
            "context_rows_written": report["context_rows_written"],
            "returns_written": report["returns_written"],
            "summary_rows_written": report["summary_rows_written"],
            "lookahead_violation_count": report["lookahead_violation_count"],
            "warning_count": report["warning_count"],
            "note_count": report["note_count"],
            "json_report": report["json_report"],
            "md_report": report["md_report"],
            "context_table": cfg.context_table,
            "returns_table": cfg.returns_table,
            "summary_table": cfg.summary_table,
            "audit_table": cfg.audit_table,
        }, ensure_ascii=False, indent=2))
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
