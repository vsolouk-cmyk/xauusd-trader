#!/usr/bin/env python3
"""
Stage38B / T3 COT Feature Audit

Purpose
-------
Read-only audit of the COT-to-H1 joined feature table created by
`app/stage38b_cot_h1_join_audit.py`.

This script does NOT create trade signals, orders, paper-live events, EA output,
or Stage39 artifacts. It only checks whether CFTC COT positioning features are
complete, time-safe, interpretable, and ready for a later T3 research design.

Default input table
-------------------
    cot_gold_h1_features_joined

Default outputs
---------------
    data/reports/stage38b_t3_cot_feature_audit/stage38b_t3_cot_feature_audit.json
    data/reports/stage38b_t3_cot_feature_audit/stage38b_t3_cot_feature_audit.md

Optional SQLite output tables
-----------------------------
    cot_gold_t3_feature_states
    cot_gold_t3_feature_audit

Design principles
-----------------
- Anti-lookahead is re-checked: cot_available_from_utc must be <= bar_ts_utc.
- Only COT fields already joined to H1 are used.
- Feature states are descriptive regime/crowding states, not trade signals.
- Missing optional features are reported, not silently assumed.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import sqlite3
from dataclasses import dataclass, asdict
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

UTC = dt.timezone.utc

REQUIRED_BASE_COLUMNS = [
    "bar_ts_utc",
    "cot_as_of_date",
    "cot_available_from_utc",
]

PRICE_CLOSE_CANDIDATES = ["close", "bar_close", "close_price", "price_close"]
SPREAD_CANDIDATES = ["spread", "spread_points", "broker_spread", "mt5_spread"]

# Feature candidates. The script is intentionally permissive because the exact
# feature set can evolve between Stage38B loader versions.
FEATURE_CANDIDATES = {
    "open_interest_all": ["open_interest_all", "open_interest"],
    "m_money_net_all": ["m_money_net_all", "managed_money_net_all", "mm_net_all"],
    "m_money_net_pct_oi": ["m_money_net_pct_oi", "managed_money_net_pct_oi", "mm_net_pct_oi"],
    "m_money_net_zscore_156w": [
        "m_money_net_zscore_156w",
        "managed_money_net_zscore_156w",
        "mm_net_zscore_156w",
    ],
    "m_money_net_change_1w": [
        "m_money_net_change_1w",
        "m_money_net_chg_1w",
        "change_m_money_net_all",
        "m_money_change_net_all",
    ],
    "prod_merc_net_all": [
        "prod_merc_net_all",
        "producer_merchant_net_all",
        "pm_net_all",
    ],
    "prod_merc_net_pct_oi": [
        "prod_merc_net_pct_oi",
        "producer_merchant_net_pct_oi",
        "pm_net_pct_oi",
    ],
    "swap_net_all": ["swap_net_all", "swap_dealer_net_all", "swap_dealers_net_all"],
    "other_rept_net_all": ["other_rept_net_all", "other_reportable_net_all"],
}

STATE_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS {table_name} (
    bar_ts_utc TEXT PRIMARY KEY,
    cot_as_of_date TEXT NOT NULL,
    cot_available_from_utc TEXT NOT NULL,
    open_interest_all REAL,
    m_money_net_all REAL,
    m_money_net_pct_oi REAL,
    m_money_net_zscore_156w REAL,
    m_money_net_change_1w REAL,
    prod_merc_net_all REAL,
    prod_merc_net_pct_oi REAL,
    cot_state TEXT NOT NULL,
    cot_pressure TEXT NOT NULL,
    cot_extreme_flag INTEGER NOT NULL,
    cot_crowding_score REAL,
    cot_notes TEXT
)
"""

AUDIT_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS {table_name} (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_utc TEXT NOT NULL,
    status TEXT NOT NULL,
    joined_table TEXT NOT NULL,
    state_table TEXT NOT NULL,
    bars_total INTEGER NOT NULL,
    feature_rows_written INTEGER NOT NULL,
    lookahead_violation_count INTEGER NOT NULL,
    duplicate_bar_count INTEGER NOT NULL,
    missing_required_feature_count INTEGER NOT NULL,
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
    # SQLite sometimes stores timestamps as YYYY-mm-dd HH:MM:SS
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


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def quote_ident(name: str) -> str:
    if not name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for c in name):
        raise ValueError(f"Unsafe SQLite identifier: {name!r}")
    return f'"{name}"'


def get_columns(con: sqlite3.Connection, table: str) -> List[str]:
    rows = con.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall()
    return [r[1] for r in rows]


def require_columns(existing: Sequence[str], required: Sequence[str], table: str) -> None:
    missing = [c for c in required if c not in existing]
    if missing:
        raise RuntimeError(
            f"Table {table!r} is missing required columns: {missing}. Existing columns: {list(existing)}"
        )


def pick_column(existing: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    for c in candidates:
        if c in existing:
            return c
    return None


def resolve_feature_columns(existing: Sequence[str]) -> Dict[str, Optional[str]]:
    return {key: pick_column(existing, candidates) for key, candidates in FEATURE_CANDIDATES.items()}


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


def summarize_numeric(values: Sequence[Optional[float]]) -> Dict[str, Any]:
    xs = [v for v in values if v is not None and not math.isnan(v)]
    if not xs:
        return {
            "count": 0,
            "missing": len(values),
            "min": None,
            "p05": None,
            "p25": None,
            "median": None,
            "mean": None,
            "p75": None,
            "p95": None,
            "max": None,
        }
    return {
        "count": len(xs),
        "missing": len(values) - len(xs),
        "min": min(xs),
        "p05": quantile(xs, 0.05),
        "p25": quantile(xs, 0.25),
        "median": median(xs),
        "mean": mean(xs),
        "p75": quantile(xs, 0.75),
        "p95": quantile(xs, 0.95),
        "max": max(xs),
    }


def classify_cot_state(
    z: Optional[float],
    pct_oi: Optional[float],
    change_1w: Optional[float],
) -> Tuple[str, str, int, Optional[float], str]:
    """Return descriptive state, pressure, extreme flag, crowding score, notes."""
    notes: List[str] = []

    score_parts: List[float] = []
    if z is not None:
        score_parts.append(max(-3.0, min(3.0, z)) / 3.0)
    else:
        notes.append("missing_zscore")

    if pct_oi is not None:
        # pct_oi typically ranges inside roughly -0.6..+0.6. Clip for stability.
        score_parts.append(max(-0.60, min(0.60, pct_oi)) / 0.60)
    else:
        notes.append("missing_pct_oi")

    crowding_score = mean(score_parts) if score_parts else None

    # Long/short/crowding states are not directional trade signals.
    if z is not None:
        if z >= 2.0:
            state = "MM_EXTREME_LONG"
            extreme = 1
        elif z >= 1.0:
            state = "MM_LONG_CROWDED"
            extreme = 0
        elif z <= -2.0:
            state = "MM_EXTREME_SHORT"
            extreme = 1
        elif z <= -1.0:
            state = "MM_SHORT_CROWDED"
            extreme = 0
        else:
            state = "MM_NEUTRAL"
            extreme = 0
    elif pct_oi is not None:
        if pct_oi >= 0.45:
            state = "MM_LONG_CROWDED_PCT_ONLY"
            extreme = 0
        elif pct_oi <= -0.25:
            state = "MM_SHORT_CROWDED_PCT_ONLY"
            extreme = 0
        else:
            state = "MM_NEUTRAL_PCT_ONLY"
            extreme = 0
    else:
        state = "COT_STATE_UNKNOWN"
        extreme = 0

    if change_1w is None:
        pressure = "FLOW_UNKNOWN"
        notes.append("missing_change_1w")
    elif change_1w >= 20000:
        pressure = "FAST_MM_LONG_BUILD"
    elif change_1w >= 5000:
        pressure = "MM_LONG_BUILD"
    elif change_1w <= -20000:
        pressure = "FAST_MM_LONG_UNWIND"
    elif change_1w <= -5000:
        pressure = "MM_LONG_UNWIND"
    else:
        pressure = "FLOW_STABLE"

    return state, pressure, extreme, crowding_score, ";".join(notes)


@dataclass
class AuditConfig:
    db: str
    joined_table: str
    state_table: str
    audit_table: str
    reports_dir: str
    write_state_table: bool
    min_bars: int


def load_joined_rows(
    con: sqlite3.Connection,
    table: str,
    cols: Sequence[str],
    feature_cols: Dict[str, Optional[str]],
    close_col: Optional[str],
    spread_col: Optional[str],
) -> List[Dict[str, Any]]:
    selected = list(REQUIRED_BASE_COLUMNS)
    for c in [close_col, spread_col, *feature_cols.values()]:
        if c and c not in selected:
            selected.append(c)

    sql_cols = ", ".join(quote_ident(c) for c in selected)
    rows = con.execute(
        f"SELECT {sql_cols} FROM {quote_ident(table)} ORDER BY {quote_ident('bar_ts_utc')}"
    ).fetchall()
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(zip(selected, r))
        normalized: Dict[str, Any] = {
            "bar_ts_utc": d.get("bar_ts_utc"),
            "cot_as_of_date": d.get("cot_as_of_date"),
            "cot_available_from_utc": d.get("cot_available_from_utc"),
            "close": safe_float(d.get(close_col)) if close_col else None,
            "spread": safe_float(d.get(spread_col)) if spread_col else None,
        }
        for key, col in feature_cols.items():
            normalized[key] = safe_float(d.get(col)) if col else None
        out.append(normalized)
    return out


def compute_state_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    state_rows: List[Dict[str, Any]] = []
    for r in rows:
        state, pressure, extreme, score, notes = classify_cot_state(
            r.get("m_money_net_zscore_156w"),
            r.get("m_money_net_pct_oi"),
            r.get("m_money_net_change_1w"),
        )
        state_rows.append(
            {
                "bar_ts_utc": r.get("bar_ts_utc"),
                "cot_as_of_date": r.get("cot_as_of_date"),
                "cot_available_from_utc": r.get("cot_available_from_utc"),
                "open_interest_all": r.get("open_interest_all"),
                "m_money_net_all": r.get("m_money_net_all"),
                "m_money_net_pct_oi": r.get("m_money_net_pct_oi"),
                "m_money_net_zscore_156w": r.get("m_money_net_zscore_156w"),
                "m_money_net_change_1w": r.get("m_money_net_change_1w"),
                "prod_merc_net_all": r.get("prod_merc_net_all"),
                "prod_merc_net_pct_oi": r.get("prod_merc_net_pct_oi"),
                "cot_state": state,
                "cot_pressure": pressure,
                "cot_extreme_flag": extreme,
                "cot_crowding_score": score,
                "cot_notes": notes,
            }
        )
    return state_rows


def write_state_rows(con: sqlite3.Connection, table: str, rows: Sequence[Dict[str, Any]]) -> None:
    con.execute(f"DROP TABLE IF EXISTS {quote_ident(table)}")
    con.execute(STATE_TABLE_SCHEMA.format(table_name=quote_ident(table)))
    cols = [
        "bar_ts_utc",
        "cot_as_of_date",
        "cot_available_from_utc",
        "open_interest_all",
        "m_money_net_all",
        "m_money_net_pct_oi",
        "m_money_net_zscore_156w",
        "m_money_net_change_1w",
        "prod_merc_net_all",
        "prod_merc_net_pct_oi",
        "cot_state",
        "cot_pressure",
        "cot_extreme_flag",
        "cot_crowding_score",
        "cot_notes",
    ]
    placeholders = ",".join("?" for _ in cols)
    sql = f"INSERT INTO {quote_ident(table)} ({', '.join(quote_ident(c) for c in cols)}) VALUES ({placeholders})"
    con.executemany(sql, [[r.get(c) for c in cols] for r in rows])


def count_by(rows: Sequence[Dict[str, Any]], key: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in rows:
        v = str(r.get(key))
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def audit_rows(
    rows: Sequence[Dict[str, Any]],
    state_rows: Sequence[Dict[str, Any]],
    feature_cols: Dict[str, Optional[str]],
    close_col: Optional[str],
    spread_col: Optional[str],
    cfg: AuditConfig,
) -> Tuple[Dict[str, Any], List[str], List[str]]:
    warnings: List[str] = []
    notes: List[str] = []

    total = len(rows)
    bar_times = [parse_ts(r.get("bar_ts_utc")) for r in rows]
    cot_avail = [parse_ts(r.get("cot_available_from_utc")) for r in rows]

    lookahead = 0
    malformed_ts = 0
    cot_lag_hours: List[float] = []
    for bt, ca in zip(bar_times, cot_avail):
        if bt is None or ca is None:
            malformed_ts += 1
            continue
        if ca > bt:
            lookahead += 1
        else:
            cot_lag_hours.append((bt - ca).total_seconds() / 3600.0)

    if malformed_ts:
        warnings.append(f"malformed_timestamp_count:{malformed_ts}")
    if lookahead:
        warnings.append(f"lookahead_violation_count:{lookahead}")
    if total < cfg.min_bars:
        warnings.append(f"bars_total_below_min:{total}<{cfg.min_bars}")

    duplicate_bar_count = total - len(set(str(r.get("bar_ts_utc")) for r in rows))
    if duplicate_bar_count:
        warnings.append(f"duplicate_bar_ts_utc_count:{duplicate_bar_count}")

    missing_required_features = []
    for key in ["m_money_net_all", "m_money_net_pct_oi", "m_money_net_zscore_156w"]:
        if feature_cols.get(key) is None:
            missing_required_features.append(key)
    if missing_required_features:
        warnings.append("missing_required_feature_columns:" + ",".join(missing_required_features))

    missing_optional = [k for k, c in feature_cols.items() if c is None and k not in missing_required_features]
    if missing_optional:
        notes.append("missing_optional_feature_columns:" + ",".join(missing_optional))

    if close_col is None:
        notes.append("close_column_not_detected_price_return_audit_skipped")
    if spread_col is None:
        notes.append("spread_column_not_detected_spread_context_skipped")

    numeric_summary: Dict[str, Any] = {}
    for key in FEATURE_CANDIDATES:
        numeric_summary[key] = summarize_numeric([r.get(key) for r in rows])

    # Staleness of COT features after publication. Max should be about one week plus weekend/gaps.
    lag_summary = summarize_numeric(cot_lag_hours)
    if lag_summary.get("max") is not None and lag_summary["max"] > 14 * 24:
        notes.append(f"cot_feature_staleness_max_hours:{lag_summary['max']:.2f}")

    latest_rows = rows[-5:]
    latest_state_rows = state_rows[-5:]

    status = "PASS" if not warnings else "WARN"
    if lookahead or missing_required_features or total == 0:
        status = "FAIL"

    report: Dict[str, Any] = {
        "created_utc": utc_now_iso(),
        "status": status,
        "db": cfg.db,
        "joined_table": cfg.joined_table,
        "state_table": cfg.state_table,
        "audit_table": cfg.audit_table,
        "bars_total": total,
        "feature_rows_written": len(state_rows) if cfg.write_state_table else 0,
        "first_bar_ts_utc": rows[0].get("bar_ts_utc") if rows else None,
        "last_bar_ts_utc": rows[-1].get("bar_ts_utc") if rows else None,
        "first_cot_as_of_date": min((str(r.get("cot_as_of_date")) for r in rows), default=None),
        "last_cot_as_of_date": max((str(r.get("cot_as_of_date")) for r in rows), default=None),
        "lookahead_violation_count": lookahead,
        "duplicate_bar_count": duplicate_bar_count,
        "malformed_timestamp_count": malformed_ts,
        "missing_required_feature_count": len(missing_required_features),
        "missing_required_features": missing_required_features,
        "resolved_columns": {
            "close": close_col,
            "spread": spread_col,
            **feature_cols,
        },
        "cot_lag_hours_summary": lag_summary,
        "numeric_feature_summary": numeric_summary,
        "cot_state_counts": count_by(state_rows, "cot_state"),
        "cot_pressure_counts": count_by(state_rows, "cot_pressure"),
        "cot_extreme_count": sum(int(r.get("cot_extreme_flag") or 0) for r in state_rows),
        "latest_5_feature_rows": latest_rows,
        "latest_5_state_rows": latest_state_rows,
        "warning_count": len(warnings),
        "note_count": len(notes),
        "warnings": warnings,
        "notes": notes,
        "decision": (
            "T3_FEATURE_FOUNDATION_READY_FOR_RESEARCH_DESIGN"
            if status == "PASS"
            else "T3_FEATURE_FOUNDATION_NEEDS_REVIEW"
        ),
        "non_go_guards": {
            "stage39": "NO_GO",
            "ea": "NO_GO",
            "paper_live": "NO_GO",
            "live_order": "NO_GO",
        },
    }
    return report, warnings, notes


def write_json_report(path: Path, report: Dict[str, Any]) -> None:
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=False), encoding="utf-8")


def fmt_num(v: Any, digits: int = 6) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def write_md_report(path: Path, report: Dict[str, Any]) -> None:
    lines: List[str] = []
    lines.append("# Stage38B / T3 COT Feature Audit")
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
    lines.append("## Coverage")
    lines.append("")
    lines.append(f"- Joined table: `{report['joined_table']}`")
    lines.append(f"- Bars total: `{report['bars_total']}`")
    lines.append(f"- First bar: `{report['first_bar_ts_utc']}`")
    lines.append(f"- Last bar: `{report['last_bar_ts_utc']}`")
    lines.append(f"- First COT as-of date: `{report['first_cot_as_of_date']}`")
    lines.append(f"- Last COT as-of date: `{report['last_cot_as_of_date']}`")
    lines.append(f"- Lookahead violations: `{report['lookahead_violation_count']}`")
    lines.append(f"- Duplicate bars: `{report['duplicate_bar_count']}`")
    lines.append("")
    lines.append("## Resolved Columns")
    lines.append("")
    for k, v in report["resolved_columns"].items():
        lines.append(f"- `{k}`: `{v}`")
    lines.append("")
    lines.append("## Numeric Feature Summary")
    lines.append("")
    lines.append("| feature | count | missing | min | p25 | median | mean | p75 | max |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for key, s in report["numeric_feature_summary"].items():
        lines.append(
            f"| `{key}` | {s['count']} | {s['missing']} | {fmt_num(s['min'])} | {fmt_num(s['p25'])} | {fmt_num(s['median'])} | {fmt_num(s['mean'])} | {fmt_num(s['p75'])} | {fmt_num(s['max'])} |"
        )
    lines.append("")
    lines.append("## COT State Counts")
    lines.append("")
    for k, v in report["cot_state_counts"].items():
        lines.append(f"- `{k}`: `{v}`")
    lines.append("")
    lines.append("## COT Pressure Counts")
    lines.append("")
    for k, v in report["cot_pressure_counts"].items():
        lines.append(f"- `{k}`: `{v}`")
    lines.append("")
    lines.append("## Latest 5 State Rows")
    lines.append("")
    lines.append("| bar_ts_utc | cot_as_of_date | m_money_net_all | pct_oi | z156 | pressure | state | score |")
    lines.append("|---|---:|---:|---:|---:|---|---|---:|")
    for r in report["latest_5_state_rows"]:
        lines.append(
            f"| `{r.get('bar_ts_utc')}` | `{r.get('cot_as_of_date')}` | {fmt_num(r.get('m_money_net_all'), 2)} | {fmt_num(r.get('m_money_net_pct_oi'), 4)} | {fmt_num(r.get('m_money_net_zscore_156w'), 4)} | `{r.get('cot_pressure')}` | `{r.get('cot_state')}` | {fmt_num(r.get('cot_crowding_score'), 4)} |"
        )
    lines.append("")
    if report["warnings"]:
        lines.append("## Warnings")
        lines.append("")
        for w in report["warnings"]:
            lines.append(f"- `{w}`")
        lines.append("")
    if report["notes"]:
        lines.append("## Notes")
        lines.append("")
        for n in report["notes"]:
            lines.append(f"- `{n}`")
        lines.append("")
    lines.append("## Next Step")
    lines.append("")
    lines.append("If status is PASS, create `docs/STAGE38B_T3_COT_RESEARCH_DESIGN.md` before any T3 backtest.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_audit_row(con: sqlite3.Connection, cfg: AuditConfig, report: Dict[str, Any]) -> None:
    con.execute(AUDIT_TABLE_SCHEMA.format(table_name=quote_ident(cfg.audit_table)))
    cols = [
        "created_utc",
        "status",
        "joined_table",
        "state_table",
        "bars_total",
        "feature_rows_written",
        "lookahead_violation_count",
        "duplicate_bar_count",
        "missing_required_feature_count",
        "warning_count",
        "note_count",
        "json_report",
        "md_report",
    ]
    vals = [
        report["created_utc"],
        report["status"],
        cfg.joined_table,
        cfg.state_table,
        report["bars_total"],
        report["feature_rows_written"],
        report["lookahead_violation_count"],
        report["duplicate_bar_count"],
        report["missing_required_feature_count"],
        report["warning_count"],
        report["note_count"],
        report["json_report"],
        report["md_report"],
    ]
    sql = f"INSERT INTO {quote_ident(cfg.audit_table)} ({', '.join(quote_ident(c) for c in cols)}) VALUES ({', '.join('?' for _ in cols)})"
    con.execute(sql, vals)


def run(cfg: AuditConfig) -> Dict[str, Any]:
    reports_dir = ensure_dir(cfg.reports_dir)
    json_path = reports_dir / "stage38b_t3_cot_feature_audit.json"
    md_path = reports_dir / "stage38b_t3_cot_feature_audit.md"

    con = sqlite3.connect(cfg.db)
    con.row_factory = sqlite3.Row
    try:
        cols = get_columns(con, cfg.joined_table)
        if not cols:
            raise RuntimeError(f"Joined table does not exist or has no columns: {cfg.joined_table}")
        require_columns(cols, REQUIRED_BASE_COLUMNS, cfg.joined_table)

        close_col = pick_column(cols, PRICE_CLOSE_CANDIDATES)
        spread_col = pick_column(cols, SPREAD_CANDIDATES)
        feature_cols = resolve_feature_columns(cols)

        rows = load_joined_rows(con, cfg.joined_table, cols, feature_cols, close_col, spread_col)
        state_rows = compute_state_rows(rows)

        report, _, _ = audit_rows(rows, state_rows, feature_cols, close_col, spread_col, cfg)
        report["json_report"] = str(json_path)
        report["md_report"] = str(md_path)

        if cfg.write_state_table:
            write_state_rows(con, cfg.state_table, state_rows)

        write_json_report(json_path, report)
        write_md_report(md_path, report)
        write_audit_row(con, cfg, report)
        con.commit()
        return report
    finally:
        con.close()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Stage38B T3 COT feature audit for XAUUSD H1 research.")
    p.add_argument("--db", default="data/local/xauusd_local_store.sqlite", help="SQLite database path")
    p.add_argument("--joined-table", default="cot_gold_h1_features_joined", help="Input joined H1+COT table")
    p.add_argument("--state-table", default="cot_gold_t3_feature_states", help="Output descriptive COT state table")
    p.add_argument("--audit-table", default="cot_gold_t3_feature_audit", help="Output audit metadata table")
    p.add_argument("--reports-dir", default="data/reports/stage38b_t3_cot_feature_audit", help="Report directory")
    p.add_argument("--no-state-table", action="store_true", help="Do not write the descriptive COT state table")
    p.add_argument("--min-bars", type=int, default=10000, help="Minimum expected H1 bars")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = AuditConfig(
        db=args.db,
        joined_table=args.joined_table,
        state_table=args.state_table,
        audit_table=args.audit_table,
        reports_dir=args.reports_dir,
        write_state_table=not args.no_state_table,
        min_bars=args.min_bars,
    )
    report = run(cfg)
    print(json.dumps({
        "status": report["status"],
        "decision": report["decision"],
        "bars_total": report["bars_total"],
        "feature_rows_written": report["feature_rows_written"],
        "lookahead_violation_count": report["lookahead_violation_count"],
        "warning_count": report["warning_count"],
        "note_count": report["note_count"],
        "json_report": report["json_report"],
        "md_report": report["md_report"],
        "state_table": report["state_table"],
        "audit_table": report["audit_table"],
    }, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
