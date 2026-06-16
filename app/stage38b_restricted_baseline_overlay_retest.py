#!/usr/bin/env python3
"""
Stage38B / Restricted Baseline Overlay Retest

Purpose
-------
Read-only retest after the T3 COT overlay gate.

This is NOT Stage39, NOT an EA, NOT paper-live, NOT live-order execution,
NOT ML, and NOT an optimized trading strategy.

It compares pre-declared event-level COT baseline/overlay policies:

1. BASELINE_ALWAYS_LONG
   Long at each weekly COT event window.

2. OVERLAY_LONG_PERMITTED_ONLY
   Long only when the COT overlay gate says LONG_PERMITTED.
   Blocked windows are treated as skipped windows with zero event-clock return.

3. OVERLAY_AVOID_LONG_HOSTILE_ONLY
   Skip only AVOID_LONG_HOSTILE windows.

4. OVERLAY_LOW_CONVICTION_BLOCK_ONLY
   Skip only LOW_CONVICTION_BLOCK windows.

5. DIAG_SQUEEZE_LONG_ONLY
   Diagnostic only. Long only in SQUEEZE_DO_NOT_SHORT windows.
   This is explicitly not promotable by itself because sample size is expected to be low.

Primary comparison
------------------
Event-clock metrics are primary. Skipped windows receive zero return so that the
comparison is against the same weekly COT opportunity clock. Trade-only metrics
are secondary.

Inputs
------
Default input table:
    cot_gold_t3_overlay_gate_events

Expected outputs
----------------
    cot_gold_t3_restricted_overlay_retest_events
    cot_gold_t3_restricted_overlay_retest_summary
    cot_gold_t3_restricted_overlay_retest_audit

Reports
-------
    data/reports/stage38b_restricted_baseline_overlay_retest/stage38b_restricted_baseline_overlay_retest.json
    data/reports/stage38b_restricted_baseline_overlay_retest/stage38b_restricted_baseline_overlay_retest.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sqlite3
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, List, Optional, Sequence, Tuple

UTC = dt.timezone.utc
DEFAULT_HORIZONS = [120, 240]

REQUIRED_SOURCE_COLUMNS = [
    "sample_level",
    "bar_ts_utc",
    "horizon_bars",
    "future_bar_ts_utc",
    "cot_available_from_utc",
    "cot_state",
    "atr_bucket",
    "close_t",
    "return_bps",
    "stress_p90_cost_bps",
    "return_bps_after_stress_cost",
    "year",
    "avoid_long_hostile",
    "squeeze_do_not_short",
    "low_conviction_block",
    "overlay_category",
    "long_overlay_policy",
    "short_overlay_policy",
]

POLICIES = [
    "BASELINE_ALWAYS_LONG",
    "OVERLAY_LONG_PERMITTED_ONLY",
    "OVERLAY_AVOID_LONG_HOSTILE_ONLY",
    "OVERLAY_LOW_CONVICTION_BLOCK_ONLY",
    "DIAG_SQUEEZE_LONG_ONLY",
]

EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS {table_name} (
    policy_name TEXT NOT NULL,
    horizon_bars INTEGER NOT NULL,
    bar_ts_utc TEXT NOT NULL,
    future_bar_ts_utc TEXT NOT NULL,
    cot_as_of_date TEXT,
    cot_available_from_utc TEXT NOT NULL,
    cot_state TEXT NOT NULL,
    atr_bucket TEXT NOT NULL,
    overlay_category TEXT NOT NULL,
    long_overlay_policy TEXT NOT NULL,
    short_overlay_policy TEXT NOT NULL,
    avoid_long_hostile INTEGER NOT NULL,
    squeeze_do_not_short INTEGER NOT NULL,
    low_conviction_block INTEGER NOT NULL,
    close_t REAL NOT NULL,
    source_return_bps REAL NOT NULL,
    source_stress_p90_cost_bps REAL,
    source_return_bps_after_stress_cost REAL NOT NULL,
    policy_traded INTEGER NOT NULL,
    policy_skipped INTEGER NOT NULL,
    policy_return_bps_event_clock REAL NOT NULL,
    policy_return_bps_trade_only REAL,
    year INTEGER NOT NULL,
    PRIMARY KEY (policy_name, horizon_bars, bar_ts_utc)
)
"""

SUMMARY_SCHEMA = """
CREATE TABLE IF NOT EXISTS {table_name} (
    created_utc TEXT NOT NULL,
    policy_name TEXT NOT NULL,
    horizon_bars INTEGER NOT NULL,
    source_event_count INTEGER NOT NULL,
    trade_count INTEGER NOT NULL,
    skipped_count INTEGER NOT NULL,
    coverage_pct REAL,
    first_bar_ts_utc TEXT,
    last_bar_ts_utc TEXT,
    trade_mean_bps REAL,
    trade_median_bps REAL,
    trade_win_rate REAL,
    trade_total_bps REAL,
    event_clock_mean_bps REAL,
    event_clock_median_bps REAL,
    event_clock_win_rate REAL,
    event_clock_total_bps REAL,
    event_clock_max_drawdown_bps REAL,
    event_clock_sharpe_proxy REAL,
    skipped_mean_source_bps REAL,
    skipped_median_source_bps REAL,
    baseline_event_clock_mean_bps REAL,
    uplift_vs_baseline_event_clock_mean_bps REAL,
    uplift_vs_baseline_event_clock_total_bps REAL,
    baseline_max_drawdown_bps REAL,
    dd_delta_vs_baseline_bps REAL,
    positive_year_count INTEGER,
    negative_year_count INTEGER,
    max_positive_year_share REAL,
    decision TEXT NOT NULL,
    note TEXT,
    PRIMARY KEY (policy_name, horizon_bars)
)
"""

AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS {table_name} (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_utc TEXT NOT NULL,
    status TEXT NOT NULL,
    decision TEXT NOT NULL,
    source_table TEXT NOT NULL,
    events_table TEXT NOT NULL,
    summary_table TEXT NOT NULL,
    source_event_rows INTEGER NOT NULL,
    events_written INTEGER NOT NULL,
    summary_rows_written INTEGER NOT NULL,
    horizon_list TEXT NOT NULL,
    min_trade_samples INTEGER NOT NULL,
    warning_count INTEGER NOT NULL,
    note_count INTEGER NOT NULL,
    json_report TEXT NOT NULL,
    md_report TEXT NOT NULL
)
"""


def utc_now_iso() -> str:
    return dt.datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def quote_ident(name: str) -> str:
    if not name or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for ch in name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return '"' + name + '"'


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "select 1 from sqlite_master where type='table' and name=? limit 1",
        (table,),
    ).fetchone() is not None


def table_columns(con: sqlite3.Connection, table: str) -> List[str]:
    if not table_exists(con, table):
        raise RuntimeError(f"Missing table: {table}")
    return [r[1] for r in con.execute(f"pragma table_info({quote_ident(table)})").fetchall()]


def require_columns(con: sqlite3.Connection, table: str, required: Sequence[str]) -> None:
    cols = set(table_columns(con, table))
    missing = [c for c in required if c not in cols]
    if missing:
        raise RuntimeError(f"Table {table!r} missing required columns: {missing}. Existing: {sorted(cols)}")


def parse_horizons(raw: str) -> List[int]:
    vals: List[int] = []
    for part in raw.split(','):
        part = part.strip()
        if part:
            vals.append(int(part))
    if not vals:
        raise ValueError("At least one horizon is required")
    return sorted(set(vals))


def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        x = float(value)
    except Exception:
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def percentile(values: Sequence[float], q: float) -> Optional[float]:
    vals = sorted(v for v in values if v is not None and not math.isnan(v))
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    pos = (len(vals) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return vals[int(pos)]
    return vals[lo] * (hi - pos) + vals[hi] * (pos - lo)


def stdev_sample(values: Sequence[float]) -> Optional[float]:
    vals = [v for v in values if v is not None and not math.isnan(v)]
    if len(vals) < 2:
        return None
    m = mean(vals)
    return math.sqrt(sum((x - m) ** 2 for x in vals) / (len(vals) - 1))


def max_drawdown(values: Sequence[float]) -> float:
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for v in values:
        cumulative += float(v or 0.0)
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd
    return max_dd


def positive_year_share(rows: Sequence[Dict[str, Any]], value_key: str) -> Tuple[int, int, Optional[float]]:
    by_year: Dict[int, float] = {}
    for r in rows:
        y = int(r["year"])
        by_year[y] = by_year.get(y, 0.0) + float(r.get(value_key) or 0.0)
    pos_vals = [v for v in by_year.values() if v > 0]
    neg_vals = [v for v in by_year.values() if v < 0]
    if not pos_vals:
        return 0, len(neg_vals), None
    total_pos = sum(pos_vals)
    share = max(pos_vals) / total_pos if total_pos > 0 else None
    return len(pos_vals), len(neg_vals), share


def load_source_rows(con: sqlite3.Connection, source_table: str, horizons: Sequence[int]) -> List[Dict[str, Any]]:
    require_columns(con, source_table, REQUIRED_SOURCE_COLUMNS)
    cols = table_columns(con, source_table)
    optional = ["cot_as_of_date"]
    select_cols = list(REQUIRED_SOURCE_COLUMNS)
    for c in optional:
        if c in cols and c not in select_cols:
            select_cols.append(c)
    horizon_ph = ",".join("?" for _ in horizons)
    sql = f"""
        select {', '.join(quote_ident(c) for c in select_cols)}
        from {quote_ident(source_table)}
        where sample_level = 'event_level'
          and horizon_bars in ({horizon_ph})
        order by horizon_bars, bar_ts_utc
    """
    con.row_factory = sqlite3.Row
    rows = con.execute(sql, tuple(horizons)).fetchall()
    out: List[Dict[str, Any]] = []
    for row in rows:
        d = dict(row)
        ret = safe_float(d.get("return_bps_after_stress_cost"))
        close_t = safe_float(d.get("close_t"))
        src_ret = safe_float(d.get("return_bps"))
        if ret is None or close_t is None or src_ret is None:
            continue
        d["return_bps_after_stress_cost"] = ret
        d["return_bps"] = src_ret
        d["close_t"] = close_t
        d["stress_p90_cost_bps"] = safe_float(d.get("stress_p90_cost_bps"))
        d["avoid_long_hostile"] = int(d.get("avoid_long_hostile") or 0)
        d["squeeze_do_not_short"] = int(d.get("squeeze_do_not_short") or 0)
        d["low_conviction_block"] = int(d.get("low_conviction_block") or 0)
        d["year"] = int(d.get("year"))
        out.append(d)
    return out


def should_trade(policy: str, row: Dict[str, Any]) -> bool:
    if policy == "BASELINE_ALWAYS_LONG":
        return True
    if policy == "OVERLAY_LONG_PERMITTED_ONLY":
        return str(row.get("long_overlay_policy")) == "LONG_PERMITTED"
    if policy == "OVERLAY_AVOID_LONG_HOSTILE_ONLY":
        return int(row.get("avoid_long_hostile") or 0) == 0
    if policy == "OVERLAY_LOW_CONVICTION_BLOCK_ONLY":
        return int(row.get("low_conviction_block") or 0) == 0
    if policy == "DIAG_SQUEEZE_LONG_ONLY":
        return int(row.get("squeeze_do_not_short") or 0) == 1
    raise ValueError(f"Unknown policy: {policy}")


def build_policy_events(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        for policy in POLICIES:
            traded = should_trade(policy, row)
            ret_after_cost = float(row["return_bps_after_stress_cost"])
            out.append(
                {
                    "policy_name": policy,
                    "horizon_bars": int(row["horizon_bars"]),
                    "bar_ts_utc": row["bar_ts_utc"],
                    "future_bar_ts_utc": row["future_bar_ts_utc"],
                    "cot_as_of_date": row.get("cot_as_of_date"),
                    "cot_available_from_utc": row["cot_available_from_utc"],
                    "cot_state": row["cot_state"],
                    "atr_bucket": row["atr_bucket"],
                    "overlay_category": row["overlay_category"],
                    "long_overlay_policy": row["long_overlay_policy"],
                    "short_overlay_policy": row["short_overlay_policy"],
                    "avoid_long_hostile": int(row.get("avoid_long_hostile") or 0),
                    "squeeze_do_not_short": int(row.get("squeeze_do_not_short") or 0),
                    "low_conviction_block": int(row.get("low_conviction_block") or 0),
                    "close_t": float(row["close_t"]),
                    "source_return_bps": float(row["return_bps"]),
                    "source_stress_p90_cost_bps": row.get("stress_p90_cost_bps"),
                    "source_return_bps_after_stress_cost": ret_after_cost,
                    "policy_traded": 1 if traded else 0,
                    "policy_skipped": 0 if traded else 1,
                    "policy_return_bps_event_clock": ret_after_cost if traded else 0.0,
                    "policy_return_bps_trade_only": ret_after_cost if traded else None,
                    "year": int(row["year"]),
                }
            )
    return out


def recreate_table(con: sqlite3.Connection, table: str, schema: str) -> None:
    con.execute(f"DROP TABLE IF EXISTS {quote_ident(table)}")
    con.execute(schema.format(table_name=quote_ident(table)))


def write_events(con: sqlite3.Connection, table: str, rows: Sequence[Dict[str, Any]]) -> int:
    fields = [
        "policy_name",
        "horizon_bars",
        "bar_ts_utc",
        "future_bar_ts_utc",
        "cot_as_of_date",
        "cot_available_from_utc",
        "cot_state",
        "atr_bucket",
        "overlay_category",
        "long_overlay_policy",
        "short_overlay_policy",
        "avoid_long_hostile",
        "squeeze_do_not_short",
        "low_conviction_block",
        "close_t",
        "source_return_bps",
        "source_stress_p90_cost_bps",
        "source_return_bps_after_stress_cost",
        "policy_traded",
        "policy_skipped",
        "policy_return_bps_event_clock",
        "policy_return_bps_trade_only",
        "year",
    ]
    ph = ",".join("?" for _ in fields)
    sql = f"INSERT INTO {quote_ident(table)} ({', '.join(quote_ident(f) for f in fields)}) VALUES ({ph})"
    con.executemany(sql, [tuple(r.get(f) for f in fields) for r in rows])
    return len(rows)


def summarize_policy(rows: Sequence[Dict[str, Any]], policy: str, horizon: int, baseline: Optional[Dict[str, Any]], min_trade_samples: int) -> Dict[str, Any]:
    subset = [r for r in rows if r["policy_name"] == policy and int(r["horizon_bars"]) == horizon]
    subset = sorted(subset, key=lambda r: r["bar_ts_utc"])
    source_count = len(subset)
    traded = [r for r in subset if int(r["policy_traded"]) == 1]
    skipped = [r for r in subset if int(r["policy_skipped"]) == 1]

    trade_vals = [float(r["policy_return_bps_trade_only"]) for r in traded if r.get("policy_return_bps_trade_only") is not None]
    clock_vals = [float(r["policy_return_bps_event_clock"]) for r in subset]
    skipped_vals = [float(r["source_return_bps_after_stress_cost"]) for r in skipped]

    trade_count = len(traded)
    skipped_count = len(skipped)
    coverage = trade_count / source_count if source_count else None

    trade_mean = mean(trade_vals) if trade_vals else None
    trade_med = median(trade_vals) if trade_vals else None
    trade_win = sum(1 for v in trade_vals if v > 0) / len(trade_vals) if trade_vals else None
    trade_total = sum(trade_vals) if trade_vals else 0.0

    clock_mean = mean(clock_vals) if clock_vals else None
    clock_med = median(clock_vals) if clock_vals else None
    clock_win = sum(1 for v in clock_vals if v > 0) / len(clock_vals) if clock_vals else None
    clock_total = sum(clock_vals) if clock_vals else 0.0
    clock_dd = max_drawdown(clock_vals)
    sd = stdev_sample(clock_vals)
    sharpe_proxy = (clock_mean / sd * math.sqrt(len(clock_vals))) if (clock_mean is not None and sd and sd > 0) else None

    skipped_mean = mean(skipped_vals) if skipped_vals else None
    skipped_med = median(skipped_vals) if skipped_vals else None

    py, ny, max_share = positive_year_share(subset, "policy_return_bps_event_clock")

    baseline_mean = baseline.get("event_clock_mean_bps") if baseline else clock_mean
    baseline_total = baseline.get("event_clock_total_bps") if baseline else clock_total
    baseline_dd = baseline.get("event_clock_max_drawdown_bps") if baseline else clock_dd

    uplift_mean = (clock_mean - baseline_mean) if (clock_mean is not None and baseline_mean is not None) else None
    uplift_total = (clock_total - baseline_total) if (clock_total is not None and baseline_total is not None) else None
    dd_delta = (clock_dd - baseline_dd) if (clock_dd is not None and baseline_dd is not None) else None

    notes: List[str] = []
    decision = "BASELINE_REFERENCE" if policy == "BASELINE_ALWAYS_LONG" else "NO_GO"

    if trade_count < min_trade_samples:
        notes.append(f"LOW_TRADE_SAMPLE_LT_{min_trade_samples}")
    if max_share is not None and max_share >= 0.70:
        notes.append("YEAR_CONCENTRATED")

    if policy == "BASELINE_ALWAYS_LONG":
        decision = "BASELINE_REFERENCE"
    elif policy == "OVERLAY_LONG_PERMITTED_ONLY":
        # Conservative: event-clock uplift must survive skipped-window zero returns.
        if (
            trade_count >= min_trade_samples
            and uplift_mean is not None
            and uplift_mean >= 5.0
            and dd_delta is not None
            and dd_delta <= 0.0
            and (max_share is None or max_share < 0.70)
        ):
            decision = "PASS_RESTRICTED_OVERLAY"
        elif trade_count >= min_trade_samples and uplift_mean is not None and uplift_mean > 0:
            decision = "WATCH_MARGINAL_OVERLAY"
        else:
            decision = "NO_GO"
    elif policy in ("OVERLAY_AVOID_LONG_HOSTILE_ONLY", "OVERLAY_LOW_CONVICTION_BLOCK_ONLY"):
        if trade_count >= min_trade_samples and uplift_mean is not None and uplift_mean > 0:
            decision = "WATCH_COMPONENT_OVERLAY"
        else:
            decision = "NO_GO"
    elif policy == "DIAG_SQUEEZE_LONG_ONLY":
        # Diagnostic only, never promotable here.
        if trade_count >= min_trade_samples and trade_mean is not None and trade_mean > 0:
            decision = "DIAGNOSTIC_ONLY_NOT_PROMOTABLE"
        else:
            decision = "DIAGNOSTIC_LOW_SAMPLE"

    return {
        "created_utc": utc_now_iso(),
        "policy_name": policy,
        "horizon_bars": horizon,
        "source_event_count": source_count,
        "trade_count": trade_count,
        "skipped_count": skipped_count,
        "coverage_pct": coverage,
        "first_bar_ts_utc": subset[0]["bar_ts_utc"] if subset else None,
        "last_bar_ts_utc": subset[-1]["bar_ts_utc"] if subset else None,
        "trade_mean_bps": trade_mean,
        "trade_median_bps": trade_med,
        "trade_win_rate": trade_win,
        "trade_total_bps": trade_total,
        "event_clock_mean_bps": clock_mean,
        "event_clock_median_bps": clock_med,
        "event_clock_win_rate": clock_win,
        "event_clock_total_bps": clock_total,
        "event_clock_max_drawdown_bps": clock_dd,
        "event_clock_sharpe_proxy": sharpe_proxy,
        "skipped_mean_source_bps": skipped_mean,
        "skipped_median_source_bps": skipped_med,
        "baseline_event_clock_mean_bps": baseline_mean,
        "uplift_vs_baseline_event_clock_mean_bps": uplift_mean,
        "uplift_vs_baseline_event_clock_total_bps": uplift_total,
        "baseline_max_drawdown_bps": baseline_dd,
        "dd_delta_vs_baseline_bps": dd_delta,
        "positive_year_count": py,
        "negative_year_count": ny,
        "max_positive_year_share": max_share,
        "decision": decision,
        "note": ";".join(notes) if notes else None,
    }


def build_summary(policy_events: Sequence[Dict[str, Any]], horizons: Sequence[int], min_trade_samples: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for horizon in horizons:
        base = summarize_policy(policy_events, "BASELINE_ALWAYS_LONG", horizon, None, min_trade_samples)
        out.append(base)
        for policy in POLICIES:
            if policy == "BASELINE_ALWAYS_LONG":
                continue
            out.append(summarize_policy(policy_events, policy, horizon, base, min_trade_samples))
    return out


def write_summary(con: sqlite3.Connection, table: str, rows: Sequence[Dict[str, Any]]) -> int:
    fields = [
        "created_utc",
        "policy_name",
        "horizon_bars",
        "source_event_count",
        "trade_count",
        "skipped_count",
        "coverage_pct",
        "first_bar_ts_utc",
        "last_bar_ts_utc",
        "trade_mean_bps",
        "trade_median_bps",
        "trade_win_rate",
        "trade_total_bps",
        "event_clock_mean_bps",
        "event_clock_median_bps",
        "event_clock_win_rate",
        "event_clock_total_bps",
        "event_clock_max_drawdown_bps",
        "event_clock_sharpe_proxy",
        "skipped_mean_source_bps",
        "skipped_median_source_bps",
        "baseline_event_clock_mean_bps",
        "uplift_vs_baseline_event_clock_mean_bps",
        "uplift_vs_baseline_event_clock_total_bps",
        "baseline_max_drawdown_bps",
        "dd_delta_vs_baseline_bps",
        "positive_year_count",
        "negative_year_count",
        "max_positive_year_share",
        "decision",
        "note",
    ]
    ph = ",".join("?" for _ in fields)
    sql = f"INSERT INTO {quote_ident(table)} ({', '.join(quote_ident(f) for f in fields)}) VALUES ({ph})"
    con.executemany(sql, [tuple(r.get(f) for f in fields) for r in rows])
    return len(rows)


def decide_overall(summary: Sequence[Dict[str, Any]]) -> str:
    pass_any = any(r["decision"] == "PASS_RESTRICTED_OVERLAY" for r in summary)
    watch_any = any(str(r["decision"]).startswith("WATCH") for r in summary)
    # Require both 120H and 240H to be at least watch for primary overlay.
    primary = [r for r in summary if r["policy_name"] == "OVERLAY_LONG_PERMITTED_ONLY"]
    primary_watch_both = len(primary) >= 2 and all(r["decision"] in ("PASS_RESTRICTED_OVERLAY", "WATCH_MARGINAL_OVERLAY") for r in primary)
    if pass_any and primary_watch_both:
        return "PROCEED_TO_BASELINE_OVERLAY_DESIGN_WITH_CAUTION"
    if watch_any and primary_watch_both:
        return "MARGINAL_OVERLAY_VALUE_REVIEW_BEFORE_ANY_BACKTEST"
    if watch_any:
        return "COMPONENT_ONLY_WATCH_NO_STRATEGY"
    return "KILL_OR_DOWNGRADE_T3_OVERLAY"


def write_audit(
    con: sqlite3.Connection,
    table: str,
    created_utc: str,
    status: str,
    decision: str,
    args: argparse.Namespace,
    source_rows: int,
    events_written: int,
    summary_written: int,
    warnings: Sequence[str],
    notes: Sequence[str],
    json_report: Path,
    md_report: Path,
) -> None:
    sql = f"""
        INSERT INTO {quote_ident(table)} (
            created_utc, status, decision, source_table, events_table, summary_table,
            source_event_rows, events_written, summary_rows_written, horizon_list,
            min_trade_samples, warning_count, note_count, json_report, md_report
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    con.execute(
        sql,
        (
            created_utc,
            status,
            decision,
            args.source_table,
            args.events_table,
            args.summary_table,
            source_rows,
            events_written,
            summary_written,
            args.horizons,
            args.min_trade_samples,
            len(warnings),
            len(notes),
            str(json_report),
            str(md_report),
        ),
    )


def round_or_none(x: Any, ndigits: int = 4) -> Any:
    if isinstance(x, float):
        return round(x, ndigits)
    return x


def write_reports(
    reports_dir: Path,
    created_utc: str,
    status: str,
    decision: str,
    args: argparse.Namespace,
    source_rows: Sequence[Dict[str, Any]],
    summary_rows: Sequence[Dict[str, Any]],
    warnings: Sequence[str],
    notes: Sequence[str],
) -> Tuple[Path, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "stage38b_restricted_baseline_overlay_retest.json"
    md_path = reports_dir / "stage38b_restricted_baseline_overlay_retest.md"

    payload = {
        "created_utc": created_utc,
        "status": status,
        "decision": decision,
        "source_table": args.source_table,
        "events_table": args.events_table,
        "summary_table": args.summary_table,
        "source_event_rows": len(source_rows),
        "summary_rows_written": len(summary_rows),
        "horizons": parse_horizons(args.horizons),
        "min_trade_samples": args.min_trade_samples,
        "warnings": list(warnings),
        "notes": list(notes),
        "summary": [
            {k: round_or_none(v) for k, v in r.items() if k != "created_utc"}
            for r in summary_rows
        ],
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    lines: List[str] = []
    lines.append("# Stage38B Restricted Baseline Overlay Retest")
    lines.append("")
    lines.append(f"**Created UTC:** {created_utc}")
    lines.append(f"**Status:** `{status}`")
    lines.append(f"**Decision:** `{decision}`")
    lines.append("")
    lines.append("This is a read-only event-level retest. It is not Stage39, not EA, not paper-live, not live execution, and not ML.")
    lines.append("")
    lines.append("## Inputs")
    lines.append("")
    lines.append(f"- Source table: `{args.source_table}`")
    lines.append(f"- Source event rows: `{len(source_rows)}`")
    lines.append(f"- Horizons: `{args.horizons}`")
    lines.append(f"- Minimum trade samples: `{args.min_trade_samples}`")
    lines.append("")
    if warnings:
        lines.append("## Warnings")
        lines.append("")
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")
    if notes:
        lines.append("## Notes")
        lines.append("")
        for n in notes:
            lines.append(f"- {n}")
        lines.append("")

    lines.append("## Summary")
    lines.append("")
    headers = [
        "horizon",
        "policy",
        "events",
        "trades",
        "skips",
        "trade_mean_bps",
        "clock_mean_bps",
        "uplift_clock_bps",
        "max_dd_bps",
        "dd_delta_bps",
        "decision",
        "note",
    ]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for r in sorted(summary_rows, key=lambda x: (x["horizon_bars"], POLICIES.index(x["policy_name"]))):
        vals = [
            r["horizon_bars"],
            r["policy_name"],
            r["source_event_count"],
            r["trade_count"],
            r["skipped_count"],
            None if r["trade_mean_bps"] is None else round(r["trade_mean_bps"], 2),
            None if r["event_clock_mean_bps"] is None else round(r["event_clock_mean_bps"], 2),
            None if r["uplift_vs_baseline_event_clock_mean_bps"] is None else round(r["uplift_vs_baseline_event_clock_mean_bps"], 2),
            None if r["event_clock_max_drawdown_bps"] is None else round(r["event_clock_max_drawdown_bps"], 2),
            None if r["dd_delta_vs_baseline_bps"] is None else round(r["dd_delta_vs_baseline_bps"], 2),
            r["decision"],
            r["note"],
        ]
        lines.append("| " + " | ".join("" if v is None else str(v) for v in vals) + " |")

    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("Primary judgment should be based on event-clock uplift, because skipped windows must remain on the same COT weekly opportunity clock. Trade-only averages are secondary.")
    lines.append("")
    lines.append("A marginal improvement does not justify strategy promotion. It only justifies writing a restricted design document or killing/downgrading T3 if the improvement is too small or year-concentrated.")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Stage38B restricted baseline overlay retest")
    ap.add_argument("--db", default="data/local/xauusd_local_store.sqlite")
    ap.add_argument("--source-table", default="cot_gold_t3_overlay_gate_events")
    ap.add_argument("--events-table", default="cot_gold_t3_restricted_overlay_retest_events")
    ap.add_argument("--summary-table", default="cot_gold_t3_restricted_overlay_retest_summary")
    ap.add_argument("--audit-table", default="cot_gold_t3_restricted_overlay_retest_audit")
    ap.add_argument("--reports-dir", default="data/reports/stage38b_restricted_baseline_overlay_retest")
    ap.add_argument("--horizons", default="120,240")
    ap.add_argument("--min-trade-samples", type=int, default=20)
    args = ap.parse_args(argv)

    created = utc_now_iso()
    horizons = parse_horizons(args.horizons)
    warnings: List[str] = []
    notes: List[str] = []

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    con = sqlite3.connect(str(db_path))
    try:
        source_rows = load_source_rows(con, args.source_table, horizons)
        if not source_rows:
            raise RuntimeError("No source event rows loaded")

        policy_events = build_policy_events(source_rows)
        summary_rows = build_summary(policy_events, horizons, args.min_trade_samples)
        decision = decide_overall(summary_rows)
        status = "PASS" if summary_rows else "FAIL"

        # Notes and warnings based on results.
        primary = [r for r in summary_rows if r["policy_name"] == "OVERLAY_LONG_PERMITTED_ONLY"]
        if any(r["decision"] == "WATCH_MARGINAL_OVERLAY" for r in primary):
            notes.append("Primary overlay has positive but marginal event-clock uplift; review before any further backtest.")
        if any(r.get("note") and "YEAR_CONCENTRATED" in str(r.get("note")) for r in summary_rows):
            notes.append("Some policy results are year-concentrated.")
        if any(r["policy_name"] == "DIAG_SQUEEZE_LONG_ONLY" and r["trade_count"] < args.min_trade_samples for r in summary_rows):
            notes.append("SQUEEZE_LONG_ONLY is diagnostic only and low-sample; it must not be promoted as a standalone setup.")

        reports_dir = Path(args.reports_dir)
        json_report, md_report = write_reports(
            reports_dir,
            created,
            status,
            decision,
            args,
            source_rows,
            summary_rows,
            warnings,
            notes,
        )

        recreate_table(con, args.events_table, EVENTS_SCHEMA)
        events_written = write_events(con, args.events_table, policy_events)
        recreate_table(con, args.summary_table, SUMMARY_SCHEMA)
        summary_written = write_summary(con, args.summary_table, summary_rows)
        recreate_table(con, args.audit_table, AUDIT_SCHEMA)
        write_audit(
            con,
            args.audit_table,
            created,
            status,
            decision,
            args,
            len(source_rows),
            events_written,
            summary_written,
            warnings,
            notes,
            json_report,
            md_report,
        )
        con.commit()

        print(json.dumps(
            {
                "status": status,
                "decision": decision,
                "source_event_rows": len(source_rows),
                "events_written": events_written,
                "summary_rows_written": summary_written,
                "warning_count": len(warnings),
                "note_count": len(notes),
                "json_report": str(json_report),
                "md_report": str(md_report),
                "events_table": args.events_table,
                "summary_table": args.summary_table,
                "audit_table": args.audit_table,
            },
            indent=2,
        ))
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
