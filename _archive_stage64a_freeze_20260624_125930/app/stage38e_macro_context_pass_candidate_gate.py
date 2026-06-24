#!/usr/bin/env python3
"""
Stage38E — Macro Context Pass Candidate Gate

Purpose
-------
Restricted read-only event-clock gate after Stage38E macro era recheck.

This script tests only a small set of macro context policies derived from the
corrected era-recheck pass candidates. Skipped events are counted as zero in the
primary event-clock statistics.

This is NOT a strategy, NOT optimization, NOT ML, and NOT a backtest promotion.
No Stage39, no EA, no paper-live, no live order.

Input table
-----------
    stage38e_macro_forward_returns

Output tables
-------------
    stage38e_macro_pass_gate_events
    stage38e_macro_pass_gate_summary
    stage38e_macro_pass_gate_audit
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

RETURNS_TABLE_DEFAULT = "stage38e_macro_forward_returns"
EVENTS_TABLE = "stage38e_macro_pass_gate_events"
SUMMARY_TABLE = "stage38e_macro_pass_gate_summary"
AUDIT_TABLE = "stage38e_macro_pass_gate_audit"
DEFAULT_HORIZONS = [72, 120]


@dataclass(frozen=True)
class Policy:
    name: str
    description: str
    role: str
    predicate: Callable[[Dict[str, Any]], bool]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return None
    try:
        x = float(s)
    except ValueError:
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def mean(xs: Sequence[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def std_sample(xs: Sequence[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def max_drawdown(values: Sequence[float]) -> float:
    peak = 0.0
    equity = 0.0
    mdd = 0.0
    for v in values:
        equity += float(v)
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > mdd:
            mdd = dd
    return mdd


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute("select 1 from sqlite_master where type='table' and name=?", (table,)).fetchone() is not None


def columns(con: sqlite3.Connection, table: str) -> List[str]:
    return [r[1] for r in con.execute(f'pragma table_info("{table}")').fetchall()]


def require_columns(con: sqlite3.Connection, table: str, required: Sequence[str]) -> None:
    cols = set(columns(con, table))
    missing = [c for c in required if c not in cols]
    if missing:
        raise RuntimeError(f"table {table} missing required columns: {missing}; existing={sorted(cols)}")


def drop_output_tables(con: sqlite3.Connection) -> None:
    for t in [EVENTS_TABLE, SUMMARY_TABLE, AUDIT_TABLE]:
        con.execute(f'drop table if exists "{t}"')


def create_output_tables(con: sqlite3.Connection) -> None:
    con.execute(
        f'''
        create table "{EVENTS_TABLE}" (
            row_id integer primary key autoincrement,
            policy_name text not null,
            policy_role text not null,
            policy_description text not null,
            horizon_bars integer not null,
            horizon_hours integer,
            macro_observation_date text not null,
            event_bar_ts_utc text,
            macro_gold_pressure text,
            macro_risk_state text,
            macro_bias text,
            real_yield_5d_bucket text,
            dollar_5d_bucket text,
            vix_5d_bucket text,
            pressure_x_risk text,
            event_year integer,
            event_month text,
            forward_return_bps real,
            selected integer not null,
            event_clock_return_bps real not null,
            ingested_at_utc text not null
        )
        '''
    )
    con.execute(
        f'''
        create table "{SUMMARY_TABLE}" (
            summary_id integer primary key autoincrement,
            horizon_bars integer not null,
            horizon_hours integer,
            policy_name text not null,
            policy_role text not null,
            source_event_count integer not null,
            trade_count integer not null,
            skipped_count integer not null,
            trade_mean_bps real,
            trade_median_bps real,
            trade_win_rate real,
            trade_t_stat real,
            event_clock_mean_bps real,
            event_clock_median_bps real,
            event_clock_win_rate real,
            event_clock_total_bps real,
            uplift_vs_baseline_event_clock_mean_bps real,
            baseline_event_clock_mean_bps real,
            event_clock_max_drawdown_bps real,
            baseline_max_drawdown_bps real,
            dd_delta_vs_baseline_bps real,
            positive_year_count integer,
            negative_year_count integer,
            max_positive_year text,
            max_positive_year_share real,
            positive_month_count integer,
            negative_month_count integer,
            max_positive_month text,
            max_positive_month_share real,
            worst_loo_excluded_year text,
            worst_loo_event_clock_mean_bps real,
            decision text not null,
            note text,
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
            source_return_rows integer not null,
            valid_return_rows integer not null,
            events_written integer not null,
            summary_rows_written integer not null,
            pass_count integer not null,
            watch_count integer not null,
            no_promotion_count integer not null,
            warning_count integer not null,
            note_count integer not null,
            json_report text,
            md_report text,
            ingested_at_utc text not null
        )
        '''
    )


def insert_rows(con: sqlite3.Connection, table: str, rows: Sequence[Dict[str, Any]]) -> None:
    if not rows:
        return
    keys = list(rows[0].keys())
    cols = ", ".join(f'"{k}"' for k in keys)
    qs = ", ".join("?" for _ in keys)
    con.executemany(f'insert into "{table}" ({cols}) values ({qs})', [[r.get(k) for k in keys] for r in rows])


def load_returns(con: sqlite3.Connection, table: str) -> List[Dict[str, Any]]:
    if not table_exists(con, table):
        raise RuntimeError(f"returns table not found: {table}")
    required = [
        "horizon_bars", "forward_return_bps", "macro_observation_date", "event_bar_ts_utc",
        "macro_gold_pressure", "macro_risk_state", "macro_bias", "real_yield_5d_bucket",
        "dollar_5d_bucket", "vix_5d_bucket", "pressure_x_risk", "event_year", "event_month",
    ]
    require_columns(con, table, required)
    optional = ["horizon_hours"]
    cols = required + [c for c in optional if c in columns(con, table)]
    sql = f'select {", ".join(f"\"{c}\"" for c in cols)} from "{table}" where forward_return_bps is not null order by horizon_bars, macro_observation_date'
    rows: List[Dict[str, Any]] = []
    for rec in con.execute(sql):
        d = dict(zip(cols, rec))
        ret = safe_float(d.get("forward_return_bps"))
        if ret is None:
            continue
        d["forward_return_bps"] = ret
        d["horizon_bars"] = int(d["horizon_bars"])
        d["horizon_hours"] = int(d.get("horizon_hours") or d["horizon_bars"])
        try:
            d["event_year"] = int(d.get("event_year") or str(d.get("macro_observation_date"))[:4])
        except Exception:
            d["event_year"] = int(str(d.get("macro_observation_date"))[:4])
        d["event_month"] = str(d.get("event_month") or str(d.get("macro_observation_date"))[:7])[:7]
        rows.append(d)
    return rows


def policies() -> List[Policy]:
    return [
        Policy(
            "BASELINE_ALWAYS_LONG",
            "Reference: all macro events take the long forward return.",
            "baseline",
            lambda r: True,
        ),
        Policy(
            "BLOCK_REAL_YIELD_FLAT_USD_DOWN",
            "Skip long when macro_gold_pressure is REAL_YIELD_FLAT+USD_DOWN.",
            "avoid_long_overlay",
            lambda r: str(r.get("macro_gold_pressure")) != "REAL_YIELD_FLAT+USD_DOWN",
        ),
        Policy(
            "LONG_ONLY_VIX_5D_UP",
            "Long only when VIX 5D bucket is VIX_5D_UP.",
            "supportive_long_context",
            lambda r: str(r.get("vix_5d_bucket")) == "VIX_5D_UP",
        ),
        Policy(
            "LONG_ONLY_REAL_YIELD_DOWN_USD_FLAT",
            "Long only when macro_gold_pressure is REAL_YIELD_DOWN+USD_FLAT.",
            "supportive_long_context",
            lambda r: str(r.get("macro_gold_pressure")) == "REAL_YIELD_DOWN+USD_FLAT",
        ),
        Policy(
            "LONG_ONLY_REAL_5D_DOWN",
            "Long only when real_yield_5d_bucket is REAL_5D_DOWN.",
            "supportive_long_context",
            lambda r: str(r.get("real_yield_5d_bucket")) == "REAL_5D_DOWN",
        ),
        Policy(
            "LONG_PERMITTED_EXCLUDE_HOSTILE_OR_RISK_ELEVATED",
            "Skip long when macro pressure is REAL_YIELD_FLAT+USD_DOWN or risk state is RISK_ELEVATED.",
            "avoid_long_overlay",
            lambda r: str(r.get("macro_gold_pressure")) != "REAL_YIELD_FLAT+USD_DOWN" and str(r.get("macro_risk_state")) != "RISK_ELEVATED",
        ),
    ]


def contribution_stats(rows: Sequence[Dict[str, Any]], value_key: str, group_key: str) -> Dict[str, Any]:
    totals: Dict[str, float] = {}
    for r in rows:
        k = str(r.get(group_key))
        totals[k] = totals.get(k, 0.0) + float(r.get(value_key) or 0.0)
    pos = {k: v for k, v in totals.items() if v > 0}
    neg = {k: v for k, v in totals.items() if v < 0}
    if pos:
        max_k, max_v = max(pos.items(), key=lambda kv: kv[1])
        total_pos = sum(pos.values())
        max_share = max_v / total_pos if total_pos else None
    else:
        max_k, max_share = None, None
    return {
        f"positive_{group_key}_count": len(pos),
        f"negative_{group_key}_count": len(neg),
        f"max_positive_{group_key}": max_k,
        f"max_positive_{group_key}_share": max_share,
    }


def worst_leave_one_year_out(rows: Sequence[Dict[str, Any]], value_key: str) -> Tuple[Optional[str], Optional[float]]:
    years = sorted({int(r["event_year"]) for r in rows})
    if len(years) < 2:
        return None, None
    worst_y: Optional[str] = None
    worst_m: Optional[float] = None
    for y in years:
        vals = [float(r.get(value_key) or 0.0) for r in rows if int(r["event_year"]) != y]
        if not vals:
            continue
        m = mean(vals)
        if m is None:
            continue
        if worst_m is None or m < worst_m:
            worst_m = m
            worst_y = str(y)
    return worst_y, worst_m


def summarize_policy(horizon: int, policy: Policy, rows_h: Sequence[Dict[str, Any]], baseline_mean: float, baseline_dd: float, ingested_at: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    event_rows: List[Dict[str, Any]] = []
    selected_returns: List[float] = []
    event_clock_returns: List[float] = []

    for r in rows_h:
        selected = 1 if policy.predicate(r) else 0
        ret = float(r["forward_return_bps"])
        ec_ret = ret if selected else 0.0
        if selected:
            selected_returns.append(ret)
        event_clock_returns.append(ec_ret)
        event_rows.append({
            "policy_name": policy.name,
            "policy_role": policy.role,
            "policy_description": policy.description,
            "horizon_bars": int(r["horizon_bars"]),
            "horizon_hours": int(r.get("horizon_hours") or r["horizon_bars"]),
            "macro_observation_date": r.get("macro_observation_date"),
            "event_bar_ts_utc": r.get("event_bar_ts_utc"),
            "macro_gold_pressure": r.get("macro_gold_pressure"),
            "macro_risk_state": r.get("macro_risk_state"),
            "macro_bias": r.get("macro_bias"),
            "real_yield_5d_bucket": r.get("real_yield_5d_bucket"),
            "dollar_5d_bucket": r.get("dollar_5d_bucket"),
            "vix_5d_bucket": r.get("vix_5d_bucket"),
            "pressure_x_risk": r.get("pressure_x_risk"),
            "event_year": int(r["event_year"]),
            "event_month": r.get("event_month"),
            "forward_return_bps": ret,
            "selected": selected,
            "event_clock_return_bps": ec_ret,
            "ingested_at_utc": ingested_at,
        })

    n = len(rows_h)
    trade_n = len(selected_returns)
    skipped = n - trade_n
    trade_mean = mean(selected_returns)
    trade_median = median(selected_returns) if selected_returns else None
    trade_win = (sum(1 for x in selected_returns if x > 0) / trade_n) if trade_n else None
    st = std_sample(selected_returns)
    trade_t = None if st is None or st == 0 or trade_n < 2 or trade_mean is None else trade_mean / (st / math.sqrt(trade_n))

    ec_mean = mean(event_clock_returns) or 0.0
    ec_median = median(event_clock_returns) if event_clock_returns else None
    ec_win = sum(1 for x in event_clock_returns if x > 0) / len(event_clock_returns) if event_clock_returns else None
    ec_total = sum(event_clock_returns)
    ec_dd = max_drawdown(event_clock_returns)
    uplift = ec_mean - baseline_mean
    dd_delta = ec_dd - baseline_dd

    y_stats = contribution_stats(event_rows, "event_clock_return_bps", "event_year")
    m_stats = contribution_stats(event_rows, "event_clock_return_bps", "event_month")
    worst_y, worst_loo = worst_leave_one_year_out(event_rows, "event_clock_return_bps")

    notes: List[str] = []
    if trade_n < 60 and policy.name != "BASELINE_ALWAYS_LONG":
        notes.append("LOW_TRADE_SAMPLE_LT_60")
    if abs(uplift) < 5 and policy.name != "BASELINE_ALWAYS_LONG":
        notes.append("LOW_EVENT_CLOCK_UPLIFT_LT_5BPS")
    elif uplift < 8 and policy.name != "BASELINE_ALWAYS_LONG":
        notes.append("MARGINAL_EVENT_CLOCK_UPLIFT_LT_8BPS")
    if dd_delta > 0.0 and policy.name != "BASELINE_ALWAYS_LONG":
        notes.append("NO_DRAWDOWN_IMPROVEMENT")
    if (y_stats.get("positive_event_year_count") or 0) < 3 and policy.name != "BASELINE_ALWAYS_LONG":
        notes.append("LOW_POSITIVE_YEAR_COUNT_LT_3")
    max_y_share = y_stats.get("max_positive_event_year_share")
    if max_y_share is not None and max_y_share > 0.55 and policy.name != "BASELINE_ALWAYS_LONG":
        notes.append("YEAR_CONCENTRATED_GT_55PCT")
    if worst_loo is not None and worst_loo <= 0 and policy.name != "BASELINE_ALWAYS_LONG":
        notes.append("LEAVE_ONE_YEAR_OUT_NON_POSITIVE")

    if policy.name == "BASELINE_ALWAYS_LONG":
        decision = "BASELINE_REFERENCE"
    elif uplift >= 8 and trade_n >= 60 and (y_stats.get("positive_event_year_count") or 0) >= 3 and (max_y_share is None or max_y_share <= 0.55) and (worst_loo is None or worst_loo > 0):
        decision = "PASS_RESTRICTED_MACRO_CONTEXT_GATE"
    elif uplift >= 3 or dd_delta < -100:
        decision = "WATCH_RESTRICTED_MACRO_CONTEXT_GATE"
    else:
        decision = "NO_PROMOTION"

    summary = {
        "horizon_bars": horizon,
        "horizon_hours": horizon,
        "policy_name": policy.name,
        "policy_role": policy.role,
        "source_event_count": n,
        "trade_count": trade_n,
        "skipped_count": skipped,
        "trade_mean_bps": trade_mean,
        "trade_median_bps": trade_median,
        "trade_win_rate": trade_win,
        "trade_t_stat": trade_t,
        "event_clock_mean_bps": ec_mean,
        "event_clock_median_bps": ec_median,
        "event_clock_win_rate": ec_win,
        "event_clock_total_bps": ec_total,
        "uplift_vs_baseline_event_clock_mean_bps": uplift,
        "baseline_event_clock_mean_bps": baseline_mean,
        "event_clock_max_drawdown_bps": ec_dd,
        "baseline_max_drawdown_bps": baseline_dd,
        "dd_delta_vs_baseline_bps": dd_delta,
        "positive_year_count": y_stats.get("positive_event_year_count"),
        "negative_year_count": y_stats.get("negative_event_year_count"),
        "max_positive_year": y_stats.get("max_positive_event_year"),
        "max_positive_year_share": y_stats.get("max_positive_event_year_share"),
        "positive_month_count": m_stats.get("positive_event_month_count"),
        "negative_month_count": m_stats.get("negative_event_month_count"),
        "max_positive_month": m_stats.get("max_positive_event_month"),
        "max_positive_month_share": m_stats.get("max_positive_event_month_share"),
        "worst_loo_excluded_year": worst_y,
        "worst_loo_event_clock_mean_bps": worst_loo,
        "decision": decision,
        "note": ";".join(notes) if notes else None,
        "ingested_at_utc": ingested_at,
    }
    return event_rows, summary


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_md(path: Path, title: str, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {title}", "", "```json", json.dumps(payload, indent=2, sort_keys=True), "```", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Stage38E restricted macro context pass-candidate gate")
    ap.add_argument("--db", default="data/local/xauusd_local_store.sqlite")
    ap.add_argument("--returns-table", default=RETURNS_TABLE_DEFAULT)
    ap.add_argument("--horizons", default=",".join(str(x) for x in DEFAULT_HORIZONS))
    ap.add_argument("--reports-dir", default="data/reports/stage38e_macro_context_pass_candidate_gate")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    horizons = [int(x.strip()) for x in str(args.horizons).split(",") if x.strip()]
    ingested_at = utc_now_iso()
    reports_dir = Path(args.reports_dir)
    json_report = reports_dir / "stage38e_macro_context_pass_candidate_gate.json"
    md_report = reports_dir / "stage38e_macro_context_pass_candidate_gate.md"

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row

    returns = load_returns(con, args.returns_table)
    returns = [r for r in returns if int(r["horizon_bars"]) in set(horizons)]
    policy_list = policies()

    event_rows_all: List[Dict[str, Any]] = []
    summary_rows: List[Dict[str, Any]] = []
    for h in horizons:
        rows_h = [r for r in returns if int(r["horizon_bars"]) == h]
        rows_h.sort(key=lambda r: str(r.get("macro_observation_date")))
        baseline_returns = [float(r["forward_return_bps"]) for r in rows_h]
        baseline_mean = mean(baseline_returns) or 0.0
        baseline_dd = max_drawdown(baseline_returns)
        for p in policy_list:
            ev, sm = summarize_policy(h, p, rows_h, baseline_mean, baseline_dd, ingested_at)
            event_rows_all.extend(ev)
            summary_rows.append(sm)

    pass_count = sum(1 for r in summary_rows if r["decision"] == "PASS_RESTRICTED_MACRO_CONTEXT_GATE")
    watch_count = sum(1 for r in summary_rows if r["decision"] == "WATCH_RESTRICTED_MACRO_CONTEXT_GATE")
    no_promo = sum(1 for r in summary_rows if r["decision"] == "NO_PROMOTION")
    warnings: List[str] = []
    notes: List[str] = []
    if not returns:
        warnings.append("no_valid_returns_loaded")
    if pass_count == 0:
        notes.append("no_restricted_macro_gate_passed")

    if warnings:
        status = "WARN"
        decision = "DO_NOT_USE_MACRO_GATE_REVIEW_WARNINGS"
    elif pass_count > 0:
        status = "PASS"
        decision = "REVIEW_RESTRICTED_MACRO_GATE_PASS_CANDIDATES_READ_ONLY"
    elif watch_count > 0:
        status = "PASS"
        decision = "MACRO_GATE_WATCH_ONLY_NO_BASELINE_PROMOTION"
    else:
        status = "PASS"
        decision = "MACRO_GATE_NO_PROMOTION_CONTEXT_ONLY"

    drop_output_tables(con)
    create_output_tables(con)
    insert_rows(con, EVENTS_TABLE, event_rows_all)
    insert_rows(con, SUMMARY_TABLE, summary_rows)

    audit = {
        "status": status,
        "decision": decision,
        "source_return_rows": len(returns),
        "valid_return_rows": len(returns),
        "events_written": len(event_rows_all),
        "summary_rows_written": len(summary_rows),
        "pass_count": pass_count,
        "watch_count": watch_count,
        "no_promotion_count": no_promo,
        "warning_count": len(warnings),
        "note_count": len(notes),
        "json_report": str(json_report),
        "md_report": str(md_report),
        "ingested_at_utc": ingested_at,
    }
    insert_rows(con, AUDIT_TABLE, [audit])
    con.commit()

    payload = {
        "audit": audit,
        "warnings": warnings,
        "notes": notes,
        "top_summary": sorted(summary_rows, key=lambda r: (r["horizon_bars"], 0 if r["policy_name"] == "BASELINE_ALWAYS_LONG" else 1, -(r.get("uplift_vs_baseline_event_clock_mean_bps") or 0)))[:20],
    }
    write_json(json_report, payload)
    write_md(md_report, "Stage38E Macro Context Pass Candidate Gate", payload)
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
