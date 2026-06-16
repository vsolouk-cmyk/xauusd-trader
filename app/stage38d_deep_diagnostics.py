#!/usr/bin/env python3
"""
Stage38D Deep Diagnostics — read-only.

Purpose
-------
Run a limited robustness diagnostic on Stage38D WATCH/PASS M5/M15 session
baseline rows. This is not a strategy, not an optimizer, and not a promotion
to Stage39/paper/live. It is meant to decide whether the single WATCH row is
worth retaining as a research watchlist candidate or should be archived.

Expected input tables
---------------------
- stage38d_session_baseline_events
- stage38d_session_baseline_summary

Outputs
-------
- stage38d_deep_diag_candidate_summary
- stage38d_deep_diag_split_summary
- stage38d_deep_diag_audit
- JSON/MD report
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

CANDIDATE_SUMMARY_TABLE = "stage38d_deep_diag_candidate_summary"
SPLIT_SUMMARY_TABLE = "stage38d_deep_diag_split_summary"
AUDIT_TABLE = "stage38d_deep_diag_audit"

CORE_DECISIONS = ("PASS_RESEARCH_INTEREST", "WATCH")


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute("select 1 from sqlite_master where type='table' and name=?", (table,)).fetchone() is not None


def table_columns(con: sqlite3.Connection, table: str) -> List[str]:
    return [r[1] for r in con.execute(f"pragma table_info({quote_ident(table)})").fetchall()]


def require_cols(con: sqlite3.Connection, table: str, required: Sequence[str]) -> None:
    cols = set(table_columns(con, table))
    missing = [c for c in required if c not in cols]
    if missing:
        raise RuntimeError(f"Table {table} missing required columns: {missing}. Existing columns: {sorted(cols)}")


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


def safe_mean(vals: Sequence[float]) -> Optional[float]:
    return statistics.mean(vals) if vals else None


def safe_median(vals: Sequence[float]) -> Optional[float]:
    return statistics.median(vals) if vals else None


def t_stat(vals: Sequence[float]) -> Optional[float]:
    if len(vals) < 2:
        return None
    sd = statistics.stdev(vals)
    if sd == 0:
        return None
    return statistics.mean(vals) / (sd / math.sqrt(len(vals)))


def win_rate(vals: Sequence[float]) -> Optional[float]:
    return sum(1 for v in vals if v > 0) / len(vals) if vals else None


def max_drawdown(vals: Sequence[float]) -> float:
    peak = 0.0
    equity = 0.0
    max_dd = 0.0
    for v in vals:
        equity += v
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
    return max_dd


def quantile(vals: Sequence[float], q: float) -> Optional[float]:
    if not vals:
        return None
    xs = sorted(vals)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def year_month(ts: str) -> Tuple[str, str]:
    s = str(ts)
    return s[:4], s[:7]


def load_candidates(con: sqlite3.Connection, summary_table: str, include_kill_top: int = 0) -> List[Dict[str, Any]]:
    require_cols(con, summary_table, [
        "decision", "timeframe", "baseline_family", "baseline_name", "horizon_bars",
        "horizon_minutes", "sample_count", "mean_net_bps"
    ])
    rows = [dict(r) for r in con.execute(f"""
        select *
        from {quote_ident(summary_table)}
        where decision in ({','.join(['?'] * len(CORE_DECISIONS))})
        order by
          case decision when 'PASS_RESEARCH_INTEREST' then 1 when 'WATCH' then 2 else 3 end,
          mean_net_bps desc
    """, CORE_DECISIONS).fetchall()]

    if include_kill_top > 0:
        killed = [dict(r) for r in con.execute(f"""
            select *
            from {quote_ident(summary_table)}
            where decision = 'KILL'
            order by mean_net_bps desc
            limit ?
        """, (include_kill_top,)).fetchall()]
        rows.extend(killed)
    return rows


def load_events_for_candidate(con: sqlite3.Connection, events_table: str, cand: Dict[str, Any]) -> List[Dict[str, Any]]:
    require_cols(con, events_table, [
        "timeframe", "baseline_family", "baseline_name", "horizon_bars",
        "entry_ts_utc", "gross_bps", "cost_bps", "net_bps"
    ])
    rows = [dict(r) for r in con.execute(f"""
        select *
        from {quote_ident(events_table)}
        where timeframe = ?
          and baseline_family = ?
          and baseline_name = ?
          and horizon_bars = ?
        order by entry_ts_utc asc
    """, (cand["timeframe"], cand["baseline_family"], cand["baseline_name"], int(cand["horizon_bars"]))).fetchall()]
    return rows


def calc_basic(events: Sequence[Dict[str, Any]], value_key: str = "net_bps") -> Dict[str, Any]:
    vals = [float(e[value_key]) for e in events if to_float(e.get(value_key)) is not None]
    return {
        "sample_count": len(vals),
        "mean_net_bps": safe_mean(vals),
        "median_net_bps": safe_median(vals),
        "win_rate_net": win_rate(vals),
        "t_stat_mean_net_bps": t_stat(vals),
        "total_net_bps": sum(vals) if vals else 0.0,
        "max_drawdown_bps": max_drawdown(vals),
        "p10_net_bps": quantile(vals, 0.10),
        "p90_net_bps": quantile(vals, 0.90),
    }


def event_net_at_cost(events: Sequence[Dict[str, Any]], multiplier: float) -> List[float]:
    vals: List[float] = []
    for e in events:
        gross = to_float(e.get("gross_bps"))
        cost = to_float(e.get("cost_bps"))
        if gross is None or cost is None:
            net = to_float(e.get("net_bps"))
            if net is not None:
                vals.append(net)
            continue
        vals.append(gross - cost * multiplier)
    return vals


def mean_at_cost(events: Sequence[Dict[str, Any]], multiplier: float) -> Optional[float]:
    return safe_mean(event_net_at_cost(events, multiplier))


def grouped_stats(events: Sequence[Dict[str, Any]], key_fn) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for e in events:
        k = key_fn(e)
        groups[str(k)].append(e)
    out: Dict[str, Dict[str, Any]] = {}
    for k, evs in groups.items():
        st = calc_basic(evs)
        out[k] = st
    return out


def contribution_stats(events: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    by_year: Dict[str, float] = defaultdict(float)
    by_month: Dict[str, float] = defaultdict(float)
    for e in events:
        val = to_float(e.get("net_bps"))
        if val is None:
            continue
        y, m = year_month(e.get("entry_ts_utc", ""))
        by_year[y] += val
        by_month[m] += val

    pos_years = {k: v for k, v in by_year.items() if v > 0}
    neg_years = {k: v for k, v in by_year.items() if v < 0}
    pos_months = {k: v for k, v in by_month.items() if v > 0}
    neg_months = {k: v for k, v in by_month.items() if v < 0}

    def max_share(pos: Dict[str, float]) -> Tuple[Optional[str], Optional[float]]:
        s = sum(pos.values())
        if s <= 0 or not pos:
            return None, None
        k, v = max(pos.items(), key=lambda kv: kv[1])
        return k, v / s

    max_y, max_y_share = max_share(pos_years)
    max_m, max_m_share = max_share(pos_months)

    return {
        "positive_year_count": len(pos_years),
        "negative_year_count": len(neg_years),
        "positive_month_count": len(pos_months),
        "negative_month_count": len(neg_months),
        "max_positive_year": max_y,
        "max_positive_year_share": max_y_share,
        "max_positive_month": max_m,
        "max_positive_month_share": max_m_share,
        "worst_year_total_bps": min(by_year.values()) if by_year else None,
        "best_year_total_bps": max(by_year.values()) if by_year else None,
    }


def split_events(events: Sequence[Dict[str, Any]]) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
    splits: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    evs = list(events)
    n = len(evs)
    mid = n // 2
    for i, e in enumerate(evs):
        y, m = year_month(e.get("entry_ts_utc", ""))
        if y:
            splits[("year", y)].append(e)
        if m:
            splits[("month", m)].append(e)
        if y == "2025":
            splits[("era", "y2025_only")].append(e)
        elif y:
            splits[("era", "exclude_2025")].append(e)
        if y and y < "2025":
            splits[("era", "pre2025_only")].append(e)
        if y == "2026":
            splits[("era", "y2026_only")].append(e)
        splits[("chronological", "first_half" if i < mid else "second_half")].append(e)
        if e.get("direction_label") is not None:
            splits[("direction", str(e.get("direction_label")))].append(e)
        if e.get("cot_state") is not None:
            splits[("cot_state", str(e.get("cot_state")))].append(e)
    return splits


def leave_one_year_out(events: Sequence[Dict[str, Any]]) -> Tuple[Optional[float], Optional[str]]:
    years = sorted({year_month(e.get("entry_ts_utc", ""))[0] for e in events if e.get("entry_ts_utc")})
    if not years:
        return None, None
    worst_mean = None
    worst_year = None
    for y in years:
        evs = [e for e in events if year_month(e.get("entry_ts_utc", ""))[0] != y]
        vals = [float(e["net_bps"]) for e in evs if to_float(e.get("net_bps")) is not None]
        if not vals:
            continue
        m = statistics.mean(vals)
        if worst_mean is None or m < worst_mean:
            worst_mean = m
            worst_year = y
    return worst_mean, worst_year


def decide_candidate(summary: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    notes: List[str] = []

    def lt(key: str, threshold: float, label: str) -> None:
        v = summary.get(key)
        if v is None or v < threshold:
            notes.append(label)

    if summary.get("sample_count", 0) < 350:
        notes.append("LOW_SAMPLE_LT_350")
    lt("mean_net_bps", 2.0, "LOW_MEAN_LT_2BPS")
    if summary.get("median_net_bps") is None or summary.get("median_net_bps") <= 0:
        notes.append("NON_POSITIVE_MEDIAN")
    if summary.get("t_stat_mean_net_bps") is None or summary.get("t_stat_mean_net_bps") < 1.25:
        notes.append("WEAK_T_STAT_LT_1_25")
    lt("exclude_2025_mean_net_bps", 1.0, "WEAK_EXCLUDE_2025_MEAN_LT_1BPS")
    lt("pre2025_mean_net_bps", 0.5, "WEAK_PRE2025_MEAN_LT_0_5BPS")
    lt("first_half_mean_net_bps", 0.5, "WEAK_FIRST_HALF_LT_0_5BPS")
    lt("second_half_mean_net_bps", 0.5, "WEAK_SECOND_HALF_LT_0_5BPS")
    lt("cost_x_1_5_mean_net_bps", 0.5, "WEAK_COST_X1_5_LT_0_5BPS")
    lt("cost_x_2_mean_net_bps", 0.0, "COST_X2_NON_POSITIVE")
    lt("worst_loo_mean_net_bps", 0.0, "LEAVE_ONE_YEAR_OUT_NON_POSITIVE")
    if summary.get("positive_year_count") is not None and summary.get("positive_year_count") < 3:
        notes.append("LOW_POSITIVE_YEAR_COUNT_LT_3")
    if summary.get("negative_year_count") is not None and summary.get("negative_year_count") >= 3:
        notes.append("MANY_NEGATIVE_YEARS_GE_3")
    if summary.get("max_positive_year_share") is not None and summary.get("max_positive_year_share") > 0.55:
        notes.append("YEAR_CONCENTRATED_GT_55PCT")
    if summary.get("max_positive_month_share") is not None and summary.get("max_positive_month_share") > 0.35:
        notes.append("MONTH_CONCENTRATED_GT_35PCT")

    hard_fail = any(n in notes for n in [
        "LOW_MEAN_LT_2BPS", "NON_POSITIVE_MEDIAN", "WEAK_EXCLUDE_2025_MEAN_LT_1BPS",
        "WEAK_PRE2025_MEAN_LT_0_5BPS", "WEAK_FIRST_HALF_LT_0_5BPS",
        "WEAK_SECOND_HALF_LT_0_5BPS", "COST_X2_NON_POSITIVE", "LEAVE_ONE_YEAR_OUT_NON_POSITIVE"
    ])

    if hard_fail:
        return "LOW_CONFIDENCE_RESEARCH_ONLY", ";".join(notes) if notes else None

    if len(notes) <= 2:
        return "PASS_DEEP_DIAGNOSTIC_WATCHLIST", ";".join(notes) if notes else None

    return "WATCH_RESEARCH_ONLY", ";".join(notes) if notes else None


def recreate_tables(con: sqlite3.Connection) -> None:
    con.executescript(f"""
    drop table if exists {quote_ident(CANDIDATE_SUMMARY_TABLE)};
    drop table if exists {quote_ident(SPLIT_SUMMARY_TABLE)};
    drop table if exists {quote_ident(AUDIT_TABLE)};

    create table {quote_ident(CANDIDATE_SUMMARY_TABLE)} (
        summary_id integer primary key autoincrement,
        candidate_id text,
        source_decision text,
        timeframe text,
        baseline_family text,
        baseline_name text,
        horizon_bars integer,
        horizon_minutes integer,
        sample_count integer,
        mean_net_bps real,
        median_net_bps real,
        win_rate_net real,
        t_stat_mean_net_bps real,
        total_net_bps real,
        max_drawdown_bps real,
        p10_net_bps real,
        p90_net_bps real,
        pre2025_mean_net_bps real,
        exclude_2025_mean_net_bps real,
        y2025_mean_net_bps real,
        y2026_mean_net_bps real,
        first_half_mean_net_bps real,
        second_half_mean_net_bps real,
        cost_x_1_5_mean_net_bps real,
        cost_x_2_mean_net_bps real,
        worst_loo_mean_net_bps real,
        worst_loo_excluded_year text,
        positive_year_count integer,
        negative_year_count integer,
        positive_month_count integer,
        negative_month_count integer,
        max_positive_year text,
        max_positive_year_share real,
        max_positive_month text,
        max_positive_month_share real,
        worst_year_total_bps real,
        best_year_total_bps real,
        decision text,
        note text
    );

    create table {quote_ident(SPLIT_SUMMARY_TABLE)} (
        split_id integer primary key autoincrement,
        candidate_id text,
        timeframe text,
        baseline_family text,
        baseline_name text,
        horizon_bars integer,
        split_type text,
        split_value text,
        sample_count integer,
        mean_net_bps real,
        median_net_bps real,
        win_rate_net real,
        t_stat_mean_net_bps real,
        total_net_bps real,
        max_drawdown_bps real,
        note text
    );

    create table {quote_ident(AUDIT_TABLE)} (
        audit_id integer primary key autoincrement,
        created_utc text,
        status text,
        decision text,
        candidates_total integer,
        pass_deep_count integer,
        watch_count integer,
        low_confidence_count integer,
        kill_count integer,
        split_rows_written integer,
        warning_count integer,
        note_count integer,
        json_report text,
        md_report text,
        metadata_json text
    );
    """)


def insert_rows(con: sqlite3.Connection, table: str, rows: Sequence[Dict[str, Any]]) -> None:
    if not rows:
        return
    keys = list(rows[0].keys())
    sql = f"insert into {quote_ident(table)} ({','.join(quote_ident(k) for k in keys)}) values ({','.join(['?'] * len(keys))})"
    con.executemany(sql, [[r.get(k) for k in keys] for r in rows])


def fmt(v: Any, nd: int = 2) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def write_reports(report_dir: Path, payload: Dict[str, Any], candidate_rows: Sequence[Dict[str, Any]], split_rows: Sequence[Dict[str, Any]]) -> Tuple[str, str]:
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "stage38d_deep_diagnostics.json"
    md_path = report_dir / "stage38d_deep_diagnostics.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    lines: List[str] = []
    lines.append("# Stage38D Deep Diagnostics")
    lines.append("")
    lines.append(f"- Status: `{payload['audit']['status']}`")
    lines.append(f"- Decision: `{payload['audit']['decision']}`")
    lines.append(f"- Candidates: `{payload['audit']['candidates_total']}`")
    lines.append("")
    lines.append("## Candidate summary")
    lines.append("")
    lines.append("| decision | candidate | tf | baseline | h | n | mean | median | WR | t | excl 2025 | pre2025 | first | second | cost x2 | worst LOO | note |")
    lines.append("|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for r in candidate_rows:
        lines.append(
            f"| {r['decision']} | {r['candidate_id']} | {r['timeframe']} | {r['baseline_name']} | {r['horizon_bars']} | "
            f"{r['sample_count']} | {fmt(r['mean_net_bps'])} | {fmt(r['median_net_bps'])} | {fmt(r['win_rate_net'],3)} | "
            f"{fmt(r['t_stat_mean_net_bps'])} | {fmt(r['exclude_2025_mean_net_bps'])} | {fmt(r['pre2025_mean_net_bps'])} | "
            f"{fmt(r['first_half_mean_net_bps'])} | {fmt(r['second_half_mean_net_bps'])} | {fmt(r['cost_x_2_mean_net_bps'])} | "
            f"{fmt(r['worst_loo_mean_net_bps'])} | {r.get('note') or ''} |"
        )
    lines.append("")
    lines.append("## Key split rows")
    lines.append("")
    lines.append("| candidate | split | value | n | mean | median | WR | total | note |")
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---|")
    keep_types = {"era", "chronological", "year", "direction", "cot_state"}
    for r in split_rows:
        if r["split_type"] not in keep_types:
            continue
        if r["split_type"] == "month" and r["sample_count"] < 15:
            continue
        lines.append(
            f"| {r['candidate_id']} | {r['split_type']} | {r['split_value']} | {r['sample_count']} | "
            f"{fmt(r['mean_net_bps'])} | {fmt(r['median_net_bps'])} | {fmt(r['win_rate_net'],3)} | {fmt(r['total_net_bps'])} | {r.get('note') or ''} |"
        )
    lines.append("")
    lines.append("## Guardrail")
    lines.append("")
    lines.append("This diagnostic is read-only. It does not authorize Stage39, EA, paper-live, live order, or ML.")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return str(json_path), str(md_path)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Stage38D deep diagnostics")
    ap.add_argument("--db", required=True)
    ap.add_argument("--events-table", default="stage38d_session_baseline_events")
    ap.add_argument("--summary-table", default="stage38d_session_baseline_summary")
    ap.add_argument("--reports-dir", default="data/reports/stage38d_deep_diagnostics")
    ap.add_argument("--include-kill-top", type=int, default=0)
    args = ap.parse_args(argv)

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row

    for t in (args.events_table, args.summary_table):
        if not table_exists(con, t):
            raise RuntimeError(f"Required table not found: {t}")

    candidates = load_candidates(con, args.summary_table, args.include_kill_top)
    candidate_rows: List[Dict[str, Any]] = []
    split_rows: List[Dict[str, Any]] = []
    warnings: List[str] = []
    notes: List[str] = []

    for i, cand in enumerate(candidates, start=1):
        cid = f"D{i}_{cand['timeframe']}_{cand['baseline_name']}_{int(cand['horizon_bars'])}"
        events = load_events_for_candidate(con, args.events_table, cand)
        if not events:
            warnings.append(f"no_events_for_{cid}")
            continue

        basic = calc_basic(events)
        contrib = contribution_stats(events)
        splits = split_events(events)

        def split_mean(stype: str, sval: str) -> Optional[float]:
            evs = splits.get((stype, sval), [])
            vals = [float(e["net_bps"]) for e in evs if to_float(e.get("net_bps")) is not None]
            return safe_mean(vals)

        worst_loo, worst_year = leave_one_year_out(events)
        row: Dict[str, Any] = {
            "candidate_id": cid,
            "source_decision": cand.get("decision"),
            "timeframe": cand["timeframe"],
            "baseline_family": cand["baseline_family"],
            "baseline_name": cand["baseline_name"],
            "horizon_bars": int(cand["horizon_bars"]),
            "horizon_minutes": int(cand.get("horizon_minutes") or 0),
            **basic,
            "pre2025_mean_net_bps": split_mean("era", "pre2025_only"),
            "exclude_2025_mean_net_bps": split_mean("era", "exclude_2025"),
            "y2025_mean_net_bps": split_mean("era", "y2025_only"),
            "y2026_mean_net_bps": split_mean("era", "y2026_only"),
            "first_half_mean_net_bps": split_mean("chronological", "first_half"),
            "second_half_mean_net_bps": split_mean("chronological", "second_half"),
            "cost_x_1_5_mean_net_bps": mean_at_cost(events, 1.5),
            "cost_x_2_mean_net_bps": mean_at_cost(events, 2.0),
            "worst_loo_mean_net_bps": worst_loo,
            "worst_loo_excluded_year": worst_year,
            **contrib,
            "decision": None,
            "note": None,
        }
        decision, note = decide_candidate(row)
        row["decision"] = decision
        row["note"] = note
        candidate_rows.append(row)

        for (stype, sval), evs in sorted(splits.items()):
            st = calc_basic(evs)
            n = st["sample_count"]
            split_note = None
            if n < 30:
                split_note = "LOW_SAMPLE_LT_30"
            split_rows.append({
                "candidate_id": cid,
                "timeframe": cand["timeframe"],
                "baseline_family": cand["baseline_family"],
                "baseline_name": cand["baseline_name"],
                "horizon_bars": int(cand["horizon_bars"]),
                "split_type": stype,
                "split_value": sval,
                "sample_count": n,
                "mean_net_bps": st["mean_net_bps"],
                "median_net_bps": st["median_net_bps"],
                "win_rate_net": st["win_rate_net"],
                "t_stat_mean_net_bps": st["t_stat_mean_net_bps"],
                "total_net_bps": st["total_net_bps"],
                "max_drawdown_bps": st["max_drawdown_bps"],
                "note": split_note,
            })

    pass_deep = sum(1 for r in candidate_rows if r["decision"] == "PASS_DEEP_DIAGNOSTIC_WATCHLIST")
    watch = sum(1 for r in candidate_rows if r["decision"] == "WATCH_RESEARCH_ONLY")
    low_conf = sum(1 for r in candidate_rows if r["decision"] == "LOW_CONFIDENCE_RESEARCH_ONLY")
    kill = sum(1 for r in candidate_rows if r["decision"] == "KILL")

    if pass_deep > 0:
        decision = "PROCEED_TO_CANDIDATE_REVIEW_READ_ONLY_WITH_CAUTION"
    elif watch > 0:
        decision = "WATCH_ONLY_REVIEW_NO_PROMOTION"
    elif low_conf > 0:
        decision = "LOW_CONFIDENCE_ARCHIVE_OR_PIVOT_REVIEW"
    else:
        decision = "NO_CANDIDATE_STOP_OR_PIVOT"

    audit = {
        "created_utc": now_utc(),
        "status": "PASS" if candidate_rows else "FAIL",
        "decision": decision,
        "candidates_total": len(candidate_rows),
        "pass_deep_count": pass_deep,
        "watch_count": watch,
        "low_confidence_count": low_conf,
        "kill_count": kill,
        "split_rows_written": len(split_rows),
        "warning_count": len(warnings),
        "note_count": len(notes),
        "json_report": "",
        "md_report": "",
        "metadata_json": json.dumps({"warnings": warnings, "notes": notes}, ensure_ascii=False),
    }

    payload = {"audit": audit, "candidates": candidate_rows, "splits": split_rows[:500]}
    json_path, md_path = write_reports(Path(args.reports_dir), payload, candidate_rows, split_rows)
    audit["json_report"] = json_path
    audit["md_report"] = md_path
    payload["audit"] = audit
    Path(json_path).write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    recreate_tables(con)
    insert_rows(con, CANDIDATE_SUMMARY_TABLE, candidate_rows)
    insert_rows(con, SPLIT_SUMMARY_TABLE, split_rows)
    con.execute(f"""
        insert into {quote_ident(AUDIT_TABLE)} (
            created_utc, status, decision, candidates_total,
            pass_deep_count, watch_count, low_confidence_count, kill_count,
            split_rows_written, warning_count, note_count,
            json_report, md_report, metadata_json
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        audit["created_utc"], audit["status"], audit["decision"], audit["candidates_total"],
        audit["pass_deep_count"], audit["watch_count"], audit["low_confidence_count"], audit["kill_count"],
        audit["split_rows_written"], audit["warning_count"], audit["note_count"],
        audit["json_report"], audit["md_report"], audit["metadata_json"],
    ))
    con.commit()

    print(json.dumps(audit, indent=2, ensure_ascii=False))
    return 0 if audit["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
