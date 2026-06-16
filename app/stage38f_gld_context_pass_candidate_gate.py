#!/usr/bin/env python3
"""
Stage38F GLD Context Pass Candidate Gate

Purpose:
    Event-clock validation for GLD/SPDR ETF context candidates.

This is NOT a strategy, NOT a backtest promotion, and NOT a paper/live tool.

It compares restricted GLD context policies against an always-long
event-clock reference. Skipped events are counted as 0 bps, so a selective
policy must beat the reference after opportunity-cost accounting.

Expected input table:
    stage38f_gld_forward_returns

The script is intentionally schema-tolerant and detects the likely return,
timestamp/date, horizon, and GLD feature columns.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple


EVENT_TABLE = "stage38f_gld_pass_gate_events"
SUMMARY_TABLE = "stage38f_gld_pass_gate_summary"
AUDIT_TABLE = "stage38f_gld_pass_gate_audit"

RETURN_COL_CANDIDATES = [
    "return_bps",
    "forward_return_bps",
    "future_return_bps",
    "future_ret_bps",
    "fwd_return_bps",
    "ret_bps",
    "return_bps_long",
    "long_return_bps",
]

TS_COL_CANDIDATES = [
    "event_ts_utc",
    "bar_ts_utc",
    "entry_ts_utc",
    "anchor_ts_utc",
    "first_h1_ts_utc",
    "ts_utc",
    "timestamp_utc",
    "utc_time",
]

DATE_COL_CANDIDATES = [
    "gld_observation_date",
    "observation_date",
    "event_date",
    "date",
    "as_of_date",
]

HORIZON_COL_CANDIDATES = [
    "horizon_bars",
    "horizon",
]


@dataclass
class Event:
    event_key: str
    event_ts: str
    event_date: str
    horizon_bars: int
    ret_bps: float
    gld_flow_state: Optional[str]
    gld_flow_1d_bucket: Optional[str]
    gld_flow_5d_bucket: Optional[str]
    gld_flow_20d_bucket: Optional[str]
    gld_holding_z_bucket: Optional[str]


@dataclass
class Policy:
    name: str
    role: str
    description: str
    predicate: Callable[[Event], bool]


def connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def table_columns(con: sqlite3.Connection, table: str) -> List[str]:
    rows = con.execute(f'pragma table_info("{table}")').fetchall()
    if not rows:
        raise RuntimeError(f"table not found or has no columns: {table}")
    return [r["name"] for r in rows]


def pick_col(cols: Sequence[str], candidates: Sequence[str], label: str, required: bool = True) -> Optional[str]:
    lower_map = {c.lower(): c for c in cols}
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    if required:
        raise RuntimeError(f"cannot detect {label}. Tried {list(candidates)}. Existing columns: {list(cols)}")
    return None


def safe_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        if math.isnan(float(x)):
            return None
        return float(x)
    s = str(x).strip()
    if not s or s.lower() in {"nan", "none", "null", "na", "n/a"}:
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def safe_int(x: Any) -> Optional[int]:
    if x is None:
        return None
    try:
        return int(float(str(x).strip()))
    except Exception:
        return None


def year_from_date_or_ts(s: str) -> Optional[int]:
    if not s or len(str(s)) < 4:
        return None
    try:
        return int(str(s)[:4])
    except Exception:
        return None


def month_from_date_or_ts(s: str) -> Optional[str]:
    s = str(s)
    if len(s) >= 7:
        return s[:7]
    return None


def mean(xs: Sequence[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def median(xs: Sequence[float]) -> Optional[float]:
    return statistics.median(xs) if xs else None


def sample_std(xs: Sequence[float]) -> Optional[float]:
    if len(xs) < 2:
        return None
    return statistics.stdev(xs)


def t_stat(xs: Sequence[float]) -> Optional[float]:
    if len(xs) < 2:
        return None
    sd = sample_std(xs)
    if not sd:
        return None
    return (sum(xs) / len(xs)) / (sd / math.sqrt(len(xs)))


def win_rate(xs: Sequence[float]) -> Optional[float]:
    return sum(1 for x in xs if x > 0) / len(xs) if xs else None


def max_drawdown_bps(xs: Sequence[float]) -> float:
    peak = 0.0
    equity = 0.0
    max_dd = 0.0
    for x in xs:
        equity += x
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
    return max_dd


def aggregate_by_year(events: Sequence[Tuple[Event, float]]) -> Tuple[int, int, Optional[int], Optional[float]]:
    sums: Dict[int, float] = {}
    for ev, val in events:
        y = year_from_date_or_ts(ev.event_date or ev.event_ts)
        if y is None:
            continue
        sums[y] = sums.get(y, 0.0) + val
    pos = {y: v for y, v in sums.items() if v > 0}
    neg = {y: v for y, v in sums.items() if v < 0}
    if not pos:
        return len(pos), len(neg), None, None
    total_pos = sum(pos.values())
    max_y, max_val = max(pos.items(), key=lambda kv: kv[1])
    share = max_val / total_pos if total_pos else None
    return len(pos), len(neg), max_y, share


def aggregate_by_month(events: Sequence[Tuple[Event, float]]) -> Tuple[int, int, Optional[str], Optional[float]]:
    sums: Dict[str, float] = {}
    for ev, val in events:
        m = month_from_date_or_ts(ev.event_date or ev.event_ts)
        if m is None:
            continue
        sums[m] = sums.get(m, 0.0) + val
    pos = {m: v for m, v in sums.items() if v > 0}
    neg = {m: v for m, v in sums.items() if v < 0}
    if not pos:
        return len(pos), len(neg), None, None
    total_pos = sum(pos.values())
    max_m, max_val = max(pos.items(), key=lambda kv: kv[1])
    share = max_val / total_pos if total_pos else None
    return len(pos), len(neg), max_m, share


def worst_leave_one_year_out_mean(events: Sequence[Tuple[Event, float]]) -> Tuple[Optional[float], Optional[int]]:
    years = sorted({year_from_date_or_ts(ev.event_date or ev.event_ts) for ev, _ in events})
    years = [y for y in years if y is not None]
    if len(years) < 2:
        return None, None
    worst_mean: Optional[float] = None
    worst_year: Optional[int] = None
    for y in years:
        vals = [v for ev, v in events if year_from_date_or_ts(ev.event_date or ev.event_ts) != y]
        if not vals:
            continue
        m = sum(vals) / len(vals)
        if worst_mean is None or m < worst_mean:
            worst_mean = m
            worst_year = y
    return worst_mean, worst_year


def load_events(con: sqlite3.Connection, table: str) -> Tuple[List[Event], Dict[str, str]]:
    cols = table_columns(con, table)
    ret_col = pick_col(cols, RETURN_COL_CANDIDATES, "return bps")
    horizon_col = pick_col(cols, HORIZON_COL_CANDIDATES, "horizon bars")
    ts_col = pick_col(cols, TS_COL_CANDIDATES, "event timestamp", required=False)
    date_col = pick_col(cols, DATE_COL_CANDIDATES, "event date", required=False)

    if not ts_col and not date_col:
        raise RuntimeError(f"cannot detect timestamp/date column. Existing columns: {cols}")

    lower_map = {c.lower(): c for c in cols}
    feature_cols = {
        "gld_flow_state": lower_map.get("gld_flow_state"),
        "gld_flow_1d_bucket": lower_map.get("gld_flow_1d_bucket"),
        "gld_flow_5d_bucket": lower_map.get("gld_flow_5d_bucket"),
        "gld_flow_20d_bucket": lower_map.get("gld_flow_20d_bucket"),
        "gld_holding_z_bucket": lower_map.get("gld_holding_z_bucket"),
    }

    select_cols = [ret_col, horizon_col]
    if ts_col:
        select_cols.append(ts_col)
    if date_col and date_col not in select_cols:
        select_cols.append(date_col)
    for c in feature_cols.values():
        if c and c not in select_cols:
            select_cols.append(c)

    sql = f'select {", ".join([f"{c!r}".replace(chr(39), chr(34)) for c in select_cols])} from "{table}" order by "{date_col or ts_col}", "{horizon_col}"'
    rows = con.execute(sql).fetchall()

    events: List[Event] = []
    for i, r in enumerate(rows):
        ret = safe_float(r[ret_col])
        h = safe_int(r[horizon_col])
        if ret is None or h is None:
            continue

        ts = str(r[ts_col]) if ts_col and r[ts_col] is not None else ""
        dt = str(r[date_col]) if date_col and r[date_col] is not None else ""
        if not dt and ts:
            dt = ts[:10]
        if not ts and dt:
            ts = dt + "T00:00:00Z"

        def get_feat(name: str) -> Optional[str]:
            c = feature_cols.get(name)
            if c and r[c] is not None:
                return str(r[c])
            return None

        events.append(Event(
            event_key=f"{dt}|{ts}|{h}|{i}",
            event_ts=ts,
            event_date=dt,
            horizon_bars=h,
            ret_bps=ret,
            gld_flow_state=get_feat("gld_flow_state"),
            gld_flow_1d_bucket=get_feat("gld_flow_1d_bucket"),
            gld_flow_5d_bucket=get_feat("gld_flow_5d_bucket"),
            gld_flow_20d_bucket=get_feat("gld_flow_20d_bucket"),
            gld_holding_z_bucket=get_feat("gld_holding_z_bucket"),
        ))

    meta = {
        "return_col": ret_col,
        "horizon_col": horizon_col,
        "ts_col": ts_col or "",
        "date_col": date_col or "",
        **{f"feature_col_{k}": v or "" for k, v in feature_cols.items()},
    }
    return events, meta


def build_policies() -> List[Policy]:
    return [
        Policy("BASELINE_ALWAYS_LONG", "baseline", "All events participate.", lambda e: True),
        Policy("LONG_ONLY_ETF_STRONG_OUTFLOW", "supportive_or_exhaustion_context", "Only GLD strong outflow context.", lambda e: e.gld_flow_state == "ETF_STRONG_OUTFLOW"),
        Policy("LONG_ONLY_ETF_STRONG_INFLOW", "supportive_flow_context", "Only GLD strong inflow context.", lambda e: e.gld_flow_state == "ETF_STRONG_INFLOW"),
        Policy("LONG_ONLY_FLOW_5D_INFLOW", "supportive_flow_context", "Only 5-day GLD inflow context.", lambda e: e.gld_flow_5d_bucket == "FLOW_5D_INFLOW"),
        Policy("LONG_ONLY_FLOW_20D_STRONG_OUTFLOW", "exhaustion_context", "Only 20-day strong GLD outflow context.", lambda e: e.gld_flow_20d_bucket == "FLOW_20D_STRONG_OUTFLOW"),
        Policy("LONG_ONLY_FLOW_20D_STRONG_INFLOW", "supportive_flow_context", "Only 20-day strong GLD inflow context.", lambda e: e.gld_flow_20d_bucket == "FLOW_20D_STRONG_INFLOW"),
        Policy("LONG_ONLY_FLOW_1D_FLAT", "diagnostic_context", "Only one-day flat flow context.", lambda e: e.gld_flow_1d_bucket == "FLOW_1D_FLAT"),
        Policy("BLOCK_FLOW_20D_OUTFLOW", "avoid_long_overlay", "Block hostile 20-day GLD outflow context.", lambda e: e.gld_flow_20d_bucket != "FLOW_20D_OUTFLOW"),
        Policy("BLOCK_ETF_OUTFLOW", "avoid_long_overlay", "Block GLD outflow state.", lambda e: e.gld_flow_state != "ETF_OUTFLOW"),
        Policy(
            "LONG_PERMITTED_EXCLUDE_ETF_OUTFLOW_OR_FLOW20_OUTFLOW",
            "avoid_long_overlay",
            "Permit long except GLD outflow state or 20-day outflow bucket.",
            lambda e: (e.gld_flow_state != "ETF_OUTFLOW" and e.gld_flow_20d_bucket != "FLOW_20D_OUTFLOW"),
        ),
    ]


def create_tables(con: sqlite3.Connection) -> None:
    for t in [EVENT_TABLE, SUMMARY_TABLE, AUDIT_TABLE]:
        con.execute(f'drop table if exists "{t}"')

    con.execute(f"""
        create table "{EVENT_TABLE}" (
            event_key text,
            event_ts_utc text,
            event_date text,
            horizon_bars integer,
            policy_name text,
            policy_role text,
            trade_flag integer,
            event_clock_return_bps real,
            raw_return_bps real,
            gld_flow_state text,
            gld_flow_1d_bucket text,
            gld_flow_5d_bucket text,
            gld_flow_20d_bucket text,
            gld_holding_z_bucket text
        )
    """)

    con.execute(f"""
        create table "{SUMMARY_TABLE}" (
            horizon_bars integer,
            policy_name text,
            policy_role text,
            policy_description text,
            source_event_count integer,
            trade_count integer,
            skipped_count integer,
            trade_mean_bps real,
            trade_median_bps real,
            trade_win_rate real,
            trade_t_stat real,
            event_clock_mean_bps real,
            event_clock_median_bps real,
            event_clock_win_rate real,
            event_clock_t_stat real,
            uplift_vs_baseline_event_clock_mean_bps real,
            event_clock_max_drawdown_bps real,
            dd_delta_vs_baseline_bps real,
            positive_year_count integer,
            negative_year_count integer,
            max_positive_year integer,
            max_positive_year_share real,
            positive_month_count integer,
            negative_month_count integer,
            max_positive_month text,
            max_positive_month_share real,
            worst_loo_event_clock_mean_bps real,
            worst_loo_excluded_year integer,
            decision text,
            note text
        )
    """)

    con.execute(f"""
        create table "{AUDIT_TABLE}" (
            audit_id integer primary key autoincrement,
            status text,
            decision text,
            source_return_rows integer,
            valid_return_rows integer,
            events_written integer,
            summary_rows_written integer,
            pass_count integer,
            watch_count integer,
            no_promotion_count integer,
            warning_count integer,
            note_count integer,
            metadata_json text
        )
    """)
    con.commit()


def summarize_policy(
    events: List[Event],
    policy: Policy,
    baseline_mean: float,
    baseline_dd: float,
) -> Tuple[Dict[str, Any], List[Tuple[Event, float]]]:
    source_count = len(events)
    selected_vals = [e.ret_bps for e in events if policy.predicate(e)]
    event_clock_pairs = [(e, e.ret_bps if policy.predicate(e) else 0.0) for e in events]
    event_vals = [v for _, v in event_clock_pairs]

    trade_count = len(selected_vals)
    skipped_count = source_count - trade_count

    ev_mean = mean(event_vals) or 0.0
    uplift = ev_mean - baseline_mean
    dd = max_drawdown_bps(event_vals)
    dd_delta = dd - baseline_dd

    pyc, nyc, max_y, max_y_share = aggregate_by_year(event_clock_pairs)
    pmc, nmc, max_m, max_m_share = aggregate_by_month(event_clock_pairs)
    worst_loo, worst_year = worst_leave_one_year_out_mean(event_clock_pairs)

    notes: List[str] = []
    if trade_count < 60:
        notes.append("LOW_TRADE_SAMPLE_LT_60")
    if uplift < 8.0 and policy.name != "BASELINE_ALWAYS_LONG":
        if uplift < 5.0:
            notes.append("LOW_EVENT_CLOCK_UPLIFT_LT_5BPS")
        else:
            notes.append("MARGINAL_EVENT_CLOCK_UPLIFT_LT_8BPS")
    if pyc < 4 and policy.name != "BASELINE_ALWAYS_LONG":
        notes.append("LOW_POSITIVE_YEAR_COUNT_LT_4")
    if max_y_share is not None and max_y_share > 0.55:
        notes.append("YEAR_CONCENTRATED_GT_55PCT")
    if worst_loo is not None and worst_loo <= 0 and policy.name != "BASELINE_ALWAYS_LONG":
        notes.append("WORST_LOO_NON_POSITIVE")
    if dd_delta >= 0 and policy.name != "BASELINE_ALWAYS_LONG":
        notes.append("NO_DRAWDOWN_IMPROVEMENT")

    if policy.name == "BASELINE_ALWAYS_LONG":
        decision = "BASELINE_REFERENCE"
    elif (
        uplift >= 8.0
        and trade_count >= 60
        and pyc >= 4
        and (max_y_share is None or max_y_share <= 0.55)
        and (worst_loo is None or worst_loo > 0)
    ):
        decision = "PASS_RESTRICTED_GLD_CONTEXT_GATE"
    elif uplift > 0 or (trade_count >= 60 and (worst_loo is not None and worst_loo > 0)):
        decision = "WATCH_RESTRICTED_GLD_CONTEXT_GATE"
    else:
        decision = "NO_PROMOTION"

    row = {
        "horizon_bars": events[0].horizon_bars if events else None,
        "policy_name": policy.name,
        "policy_role": policy.role,
        "policy_description": policy.description,
        "source_event_count": source_count,
        "trade_count": trade_count,
        "skipped_count": skipped_count,
        "trade_mean_bps": mean(selected_vals),
        "trade_median_bps": median(selected_vals),
        "trade_win_rate": win_rate(selected_vals),
        "trade_t_stat": t_stat(selected_vals),
        "event_clock_mean_bps": ev_mean,
        "event_clock_median_bps": median(event_vals),
        "event_clock_win_rate": win_rate(event_vals),
        "event_clock_t_stat": t_stat(event_vals),
        "uplift_vs_baseline_event_clock_mean_bps": uplift,
        "event_clock_max_drawdown_bps": dd,
        "dd_delta_vs_baseline_bps": dd_delta,
        "positive_year_count": pyc,
        "negative_year_count": nyc,
        "max_positive_year": max_y,
        "max_positive_year_share": max_y_share,
        "positive_month_count": pmc,
        "negative_month_count": nmc,
        "max_positive_month": max_m,
        "max_positive_month_share": max_m_share,
        "worst_loo_event_clock_mean_bps": worst_loo,
        "worst_loo_excluded_year": worst_year,
        "decision": decision,
        "note": ";".join(notes) if notes else None,
    }
    return row, event_clock_pairs


def insert_dict_rows(con: sqlite3.Connection, table: str, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    keys = list(rows[0].keys())
    sql = f'insert into "{table}" ({",".join(keys)}) values ({",".join(["?"] * len(keys))})'
    con.executemany(sql, [[r.get(k) for k in keys] for r in rows])


def write_reports(reports_dir: Path, audit: Dict[str, Any], summaries: List[Dict[str, Any]], meta: Dict[str, Any]) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    payload = {"audit": audit, "metadata": meta, "summary": summaries}
    (reports_dir / "stage38f_gld_context_pass_candidate_gate.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    lines: List[str] = []
    lines.append("# Stage38F GLD Context Pass Candidate Gate\n")
    lines.append("## Audit\n")
    for k, v in audit.items():
        lines.append(f"- **{k}:** {v}")
    lines.append("\n## Summary\n")
    lines.append("| horizon | policy | role | source | trades | skipped | trade mean bps | event-clock mean bps | uplift bps | dd delta bps | decision | note |")
    lines.append("|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|")
    for r in summaries:
        lines.append(
            f"| {r['horizon_bars']} | {r['policy_name']} | {r['policy_role']} | {r['source_event_count']} | {r['trade_count']} | {r['skipped_count']} | "
            f"{(r['trade_mean_bps'] if r['trade_mean_bps'] is not None else float('nan')):.2f} | "
            f"{(r['event_clock_mean_bps'] if r['event_clock_mean_bps'] is not None else float('nan')):.2f} | "
            f"{(r['uplift_vs_baseline_event_clock_mean_bps'] if r['uplift_vs_baseline_event_clock_mean_bps'] is not None else float('nan')):.2f} | "
            f"{(r['dd_delta_vs_baseline_bps'] if r['dd_delta_vs_baseline_bps'] is not None else float('nan')):.2f} | "
            f"{r['decision']} | {r['note'] or ''} |"
        )
    (reports_dir / "stage38f_gld_context_pass_candidate_gate.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/local/xauusd_local_store.sqlite")
    ap.add_argument("--returns-table", default="stage38f_gld_forward_returns")
    ap.add_argument("--reports-dir", default="data/reports/stage38f_gld_context_pass_candidate_gate")
    args = ap.parse_args()

    con = connect(args.db)
    events, meta = load_events(con, args.returns_table)
    source_return_rows = con.execute(f'select count(*) from "{args.returns_table}"').fetchone()[0]
    valid_return_rows = len(events)

    if not events:
        raise RuntimeError("no valid return events detected")

    create_tables(con)

    policies = build_policies()
    horizons = sorted({e.horizon_bars for e in events})

    summary_rows: List[Dict[str, Any]] = []
    event_rows: List[Dict[str, Any]] = []

    for h in horizons:
        h_events = sorted([e for e in events if e.horizon_bars == h], key=lambda e: (e.event_date, e.event_ts, e.event_key))
        if not h_events:
            continue

        baseline_vals = [e.ret_bps for e in h_events]
        baseline_mean = mean(baseline_vals) or 0.0
        baseline_dd = max_drawdown_bps(baseline_vals)

        for policy in policies:
            row, event_clock = summarize_policy(h_events, policy, baseline_mean, baseline_dd)
            summary_rows.append(row)

            for ev, ev_ret in event_clock:
                trade_flag = 1 if policy.predicate(ev) else 0
                event_rows.append({
                    "event_key": ev.event_key,
                    "event_ts_utc": ev.event_ts,
                    "event_date": ev.event_date,
                    "horizon_bars": ev.horizon_bars,
                    "policy_name": policy.name,
                    "policy_role": policy.role,
                    "trade_flag": trade_flag,
                    "event_clock_return_bps": ev_ret,
                    "raw_return_bps": ev.ret_bps,
                    "gld_flow_state": ev.gld_flow_state,
                    "gld_flow_1d_bucket": ev.gld_flow_1d_bucket,
                    "gld_flow_5d_bucket": ev.gld_flow_5d_bucket,
                    "gld_flow_20d_bucket": ev.gld_flow_20d_bucket,
                    "gld_holding_z_bucket": ev.gld_holding_z_bucket,
                })

    insert_dict_rows(con, SUMMARY_TABLE, summary_rows)
    insert_dict_rows(con, EVENT_TABLE, event_rows)

    pass_count = sum(1 for r in summary_rows if r["decision"] == "PASS_RESTRICTED_GLD_CONTEXT_GATE")
    watch_count = sum(1 for r in summary_rows if r["decision"] == "WATCH_RESTRICTED_GLD_CONTEXT_GATE")
    no_promotion_count = sum(1 for r in summary_rows if r["decision"] == "NO_PROMOTION")

    if pass_count > 0:
        decision = "REVIEW_GLD_GATE_PASS_CANDIDATES_READ_ONLY"
    elif watch_count > 0:
        decision = "GLD_GATE_WATCH_ONLY_NO_BASELINE_PROMOTION"
    else:
        decision = "GLD_GATE_NO_PROMOTION_KEEP_DATA_ONLY"

    audit = {
        "status": "PASS",
        "decision": decision,
        "source_return_rows": source_return_rows,
        "valid_return_rows": valid_return_rows,
        "events_written": len(event_rows),
        "summary_rows_written": len(summary_rows),
        "pass_count": pass_count,
        "watch_count": watch_count,
        "no_promotion_count": no_promotion_count,
        "warning_count": 0,
        "note_count": 1,
        "metadata_json": json.dumps(meta, ensure_ascii=False, sort_keys=True),
    }

    con.execute(
        f"""
        insert into "{AUDIT_TABLE}" (
            status, decision, source_return_rows, valid_return_rows,
            events_written, summary_rows_written,
            pass_count, watch_count, no_promotion_count,
            warning_count, note_count, metadata_json
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            audit["status"], audit["decision"], audit["source_return_rows"], audit["valid_return_rows"],
            audit["events_written"], audit["summary_rows_written"],
            audit["pass_count"], audit["watch_count"], audit["no_promotion_count"],
            audit["warning_count"], audit["note_count"], audit["metadata_json"],
        ),
    )

    con.commit()
    write_reports(Path(args.reports_dir), audit, summary_rows, meta)

    print(json.dumps({
        "status": audit["status"],
        "decision": audit["decision"],
        "source_return_rows": source_return_rows,
        "valid_return_rows": valid_return_rows,
        "events_written": len(event_rows),
        "summary_rows_written": len(summary_rows),
        "pass_count": pass_count,
        "watch_count": watch_count,
        "no_promotion_count": no_promotion_count,
        "reports_dir": args.reports_dir,
    }, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
