#!/usr/bin/env python3
"""
Stage38E — Macro Context Era Recheck

Purpose
-------
Read-only correction/extension after the first Stage38E macro context diagnostic.
The first diagnostic correctly produced event-level forward returns, but its
summary concentration fields can be misleading if yearly/monthly contribution is
computed from non-existent keys instead of event_year/event_month.

This script does NOT recompute market data, does NOT create a strategy, does NOT
optimize, and does NOT place orders. It reads stage38e_macro_forward_returns and
rebuilds the macro-context summary with explicit event_year / event_month era
statistics.

No Stage39, no EA, no paper-live, no live order.

Output tables
-------------
    stage38e_macro_context_era_summary
    stage38e_macro_context_era_audit
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

RETURNS_TABLE_DEFAULT = "stage38e_macro_forward_returns"
SUMMARY_TABLE = "stage38e_macro_context_era_summary"
AUDIT_TABLE = "stage38e_macro_context_era_audit"
DEFAULT_HORIZONS = [24, 72, 120]
DEFAULT_MIN_SAMPLE = 60


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_year(value: Any, fallback: Any = None) -> Optional[int]:
    for v in (value, fallback):
        if v is None:
            continue
        s = str(v).strip()
        if not s:
            continue
        try:
            return int(s[:4])
        except Exception:
            continue
    return None


def parse_month(value: Any, fallback: Any = None) -> Optional[str]:
    for v in (value, fallback):
        if v is None:
            continue
        s = str(v).strip()
        if len(s) >= 7:
            return s[:7]
    return None


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
    for t in [SUMMARY_TABLE, AUDIT_TABLE]:
        con.execute(f'drop table if exists "{t}"')


def create_output_tables(con: sqlite3.Connection) -> None:
    con.execute(
        f'''
        create table "{SUMMARY_TABLE}" (
            summary_id integer primary key autoincrement,
            group_type text not null,
            group_value text not null,
            horizon_bars integer not null,
            horizon_hours integer,
            sample_count integer not null,
            mean_return_bps real,
            median_return_bps real,
            win_rate_long real,
            std_return_bps real,
            t_stat_mean_bps real,
            diff_vs_all_mean_bps real,
            total_return_bps real,
            positive_year_count integer,
            negative_year_count integer,
            max_positive_year text,
            max_positive_year_share real,
            positive_month_count integer,
            negative_month_count integer,
            max_positive_month text,
            max_positive_month_share real,
            pre2025_sample_count integer,
            pre2025_mean_return_bps real,
            exclude_2025_sample_count integer,
            exclude_2025_mean_return_bps real,
            y2025_sample_count integer,
            y2025_mean_return_bps real,
            y2026_sample_count integer,
            y2026_mean_return_bps real,
            first_half_sample_count integer,
            first_half_mean_return_bps real,
            second_half_sample_count integer,
            second_half_mean_return_bps real,
            worst_loo_excluded_year text,
            worst_loo_mean_return_bps real,
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
        "horizon_bars", "forward_return_bps", "macro_observation_date",
        "event_bar_ts_utc", "macro_gold_pressure", "macro_risk_state",
        "macro_bias", "real_yield_5d_bucket", "dollar_5d_bucket",
    ]
    require_columns(con, table, required)
    optional = ["horizon_hours", "event_year", "event_month", "vix_5d_bucket", "pressure_x_risk"]
    cols = required + [c for c in optional if c in columns(con, table)]
    sql = f'select {", ".join(f"\"{c}\"" for c in cols)} from "{table}" where forward_return_bps is not null'
    out: List[Dict[str, Any]] = []
    for rec in con.execute(sql):
        d = dict(zip(cols, rec))
        ret = safe_float(d.get("forward_return_bps"))
        if ret is None:
            continue
        d["forward_return_bps"] = ret
        d["horizon_bars"] = int(d["horizon_bars"])
        d["horizon_hours"] = int(d.get("horizon_hours") or d["horizon_bars"])
        y = parse_year(d.get("event_year"), d.get("macro_observation_date"))
        m = parse_month(d.get("event_month"), d.get("macro_observation_date"))
        if y is None or m is None:
            continue
        d["event_year"] = y
        d["event_month"] = m
        out.append(d)
    return out


def contribution_stats(rows: Sequence[Dict[str, Any]], key: str) -> Dict[str, Any]:
    totals: Dict[str, float] = {}
    for r in rows:
        v = safe_float(r.get("forward_return_bps"))
        if v is None:
            continue
        k = str(r.get(key) or "UNKNOWN")
        totals[k] = totals.get(k, 0.0) + float(v)
    pos = {k: v for k, v in totals.items() if v > 0}
    neg = {k: v for k, v in totals.items() if v < 0}
    if pos:
        max_k, max_v = max(pos.items(), key=lambda kv: kv[1])
        total_pos = sum(pos.values())
        share = max_v / total_pos if total_pos else None
    else:
        max_k, share = None, None
    label = "year" if key == "event_year" else "month"
    return {
        f"positive_{label}_count": len(pos),
        f"negative_{label}_count": len(neg),
        f"max_positive_{label}": max_k,
        f"max_positive_{label}_share": share,
    }


def subset_mean(rows: Sequence[Dict[str, Any]], pred) -> Tuple[int, Optional[float]]:
    vals = [float(r["forward_return_bps"]) for r in rows if pred(r)]
    return len(vals), mean(vals)


def chronological_halves(rows: Sequence[Dict[str, Any]]) -> Tuple[int, Optional[float], int, Optional[float]]:
    rs = sorted(rows, key=lambda r: str(r.get("event_bar_ts_utc") or r.get("macro_observation_date") or ""))
    if not rs:
        return 0, None, 0, None
    mid = len(rs) // 2
    first = rs[:mid]
    second = rs[mid:]
    return len(first), mean([float(r["forward_return_bps"]) for r in first]), len(second), mean([float(r["forward_return_bps"]) for r in second])


def worst_leave_one_year_out(rows: Sequence[Dict[str, Any]]) -> Tuple[Optional[str], Optional[float]]:
    years = sorted({int(r["event_year"]) for r in rows if r.get("event_year") is not None})
    if len(years) < 2:
        return None, None
    worst_year: Optional[str] = None
    worst_mean: Optional[float] = None
    for y in years:
        vals = [float(r["forward_return_bps"]) for r in rows if int(r["event_year"]) != y]
        if not vals:
            continue
        m = mean(vals)
        if worst_mean is None or (m is not None and m < worst_mean):
            worst_mean = m
            worst_year = str(y)
    return worst_year, worst_mean


def summarize_group(rows: Sequence[Dict[str, Any]], group_type: str, group_value: str, horizon: int, all_mean: float, min_sample: int, ingested_at: str) -> Dict[str, Any]:
    vals = [float(r["forward_return_bps"]) for r in rows]
    n = len(vals)
    m = mean(vals)
    med = median(vals) if vals else None
    st = std_sample(vals)
    t_stat = None if st is None or st == 0 or m is None else m / (st / math.sqrt(n))
    win_rate = sum(1 for x in vals if x > 0) / n if n else None
    total = sum(vals)
    diff = None if m is None else m - all_mean
    year_stats = contribution_stats(rows, "event_year")
    month_stats = contribution_stats(rows, "event_month")
    pre_n, pre_m = subset_mean(rows, lambda r: int(r["event_year"]) < 2025)
    ex25_n, ex25_m = subset_mean(rows, lambda r: int(r["event_year"]) != 2025)
    y25_n, y25_m = subset_mean(rows, lambda r: int(r["event_year"]) == 2025)
    y26_n, y26_m = subset_mean(rows, lambda r: int(r["event_year"]) == 2026)
    fh_n, fh_m, sh_n, sh_m = chronological_halves(rows)
    loo_y, loo_m = worst_leave_one_year_out(rows)

    notes: List[str] = []
    if n < min_sample and group_type != "all":
        notes.append(f"LOW_SAMPLE_LT_{min_sample}")
    if abs(m or 0.0) < 5 and group_type != "all":
        notes.append("LOW_ABS_MEAN_LT_5BPS")
    if abs(diff or 0.0) < 5 and group_type != "all":
        notes.append("LOW_DIFF_VS_ALL_LT_5BPS")
    if year_stats.get("max_positive_year_share") is not None and year_stats["max_positive_year_share"] > 0.55:
        notes.append("YEAR_CONCENTRATED_GT_55PCT")
    if month_stats.get("max_positive_month_share") is not None and month_stats["max_positive_month_share"] > 0.35:
        notes.append("MONTH_CONCENTRATED_GT_35PCT")
    if year_stats.get("positive_year_count", 0) < 3 and group_type != "all":
        notes.append("LOW_POSITIVE_YEAR_COUNT_LT_3")
    if m is not None and m > 0 and ex25_m is not None and ex25_m <= 0 and group_type != "all":
        notes.append("EXCLUDE_2025_NON_POSITIVE")
    if m is not None and m > 0 and pre_m is not None and pre_m < 5 and group_type != "all":
        notes.append("WEAK_PRE2025_LT_5BPS")
    if m is not None and m > 0 and loo_m is not None and loo_m <= 0 and group_type != "all":
        notes.append("LEAVE_ONE_YEAR_OUT_NON_POSITIVE")
    if fh_m is not None and sh_m is not None and ((fh_m <= 0 < sh_m) or (sh_m <= 0 < fh_m)) and group_type != "all":
        notes.append("CHRONO_HALF_SIGN_MISMATCH")

    if group_type == "all":
        decision = "BASELINE_CONTEXT_REFERENCE"
    elif (
        n >= min_sample
        and abs(diff or 0.0) >= 10
        and year_stats.get("positive_year_count", 0) >= 3
        and not any(x.startswith("YEAR_CONCENTRATED") or x.startswith("MONTH_CONCENTRATED") for x in notes)
        and not any(x in {"EXCLUDE_2025_NON_POSITIVE", "LEAVE_ONE_YEAR_OUT_NON_POSITIVE", "CHRONO_HALF_SIGN_MISMATCH"} for x in notes)
    ):
        decision = "PASS_MACRO_CONTEXT_SEPARATION_WATCH"
    elif n >= min_sample and abs(diff or 0.0) >= 5:
        decision = "WATCH_MACRO_CONTEXT_AFTER_ERA_RECHECK"
    else:
        decision = "NO_PROMOTION"

    return {
        "group_type": group_type,
        "group_value": group_value,
        "horizon_bars": horizon,
        "horizon_hours": horizon,
        "sample_count": n,
        "mean_return_bps": m,
        "median_return_bps": med,
        "win_rate_long": win_rate,
        "std_return_bps": st,
        "t_stat_mean_bps": t_stat,
        "diff_vs_all_mean_bps": diff,
        "total_return_bps": total,
        "positive_year_count": year_stats.get("positive_year_count"),
        "negative_year_count": year_stats.get("negative_year_count"),
        "max_positive_year": year_stats.get("max_positive_year"),
        "max_positive_year_share": year_stats.get("max_positive_year_share"),
        "positive_month_count": month_stats.get("positive_month_count"),
        "negative_month_count": month_stats.get("negative_month_count"),
        "max_positive_month": month_stats.get("max_positive_month"),
        "max_positive_month_share": month_stats.get("max_positive_month_share"),
        "pre2025_sample_count": pre_n,
        "pre2025_mean_return_bps": pre_m,
        "exclude_2025_sample_count": ex25_n,
        "exclude_2025_mean_return_bps": ex25_m,
        "y2025_sample_count": y25_n,
        "y2025_mean_return_bps": y25_m,
        "y2026_sample_count": y26_n,
        "y2026_mean_return_bps": y26_m,
        "first_half_sample_count": fh_n,
        "first_half_mean_return_bps": fh_m,
        "second_half_sample_count": sh_n,
        "second_half_mean_return_bps": sh_m,
        "worst_loo_excluded_year": loo_y,
        "worst_loo_mean_return_bps": loo_m,
        "decision": decision,
        "note": ";".join(notes) if notes else None,
        "ingested_at_utc": ingested_at,
    }


def build_summary(returns: Sequence[Dict[str, Any]], horizons: Sequence[int], min_sample: int, ingested_at: str) -> List[Dict[str, Any]]:
    group_specs = [
        ("all", lambda r: "ALL"),
        ("macro_bias", lambda r: r.get("macro_bias") or "UNKNOWN"),
        ("macro_gold_pressure", lambda r: r.get("macro_gold_pressure") or "UNKNOWN"),
        ("macro_risk_state", lambda r: r.get("macro_risk_state") or "UNKNOWN"),
        ("real_yield_5d_bucket", lambda r: r.get("real_yield_5d_bucket") or "UNKNOWN"),
        ("dollar_5d_bucket", lambda r: r.get("dollar_5d_bucket") or "UNKNOWN"),
        ("vix_5d_bucket", lambda r: r.get("vix_5d_bucket") or "UNKNOWN"),
        ("pressure_x_risk", lambda r: r.get("pressure_x_risk") or "UNKNOWN"),
    ]
    out: List[Dict[str, Any]] = []
    for h in horizons:
        rows_h = [r for r in returns if int(r["horizon_bars"]) == h]
        if not rows_h:
            continue
        all_mean = mean([float(r["forward_return_bps"]) for r in rows_h]) or 0.0
        for gtype, getter in group_specs:
            groups: Dict[str, List[Dict[str, Any]]] = {}
            for r in rows_h:
                groups.setdefault(str(getter(r)), []).append(r)
            for gval, gr in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
                out.append(summarize_group(gr, gtype, gval, h, all_mean, min_sample, ingested_at))
    return out


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_md(path: Path, title: str, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {title}", "", "```json", json.dumps(payload, indent=2, sort_keys=True), "```", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage38E macro context era/year recheck")
    ap.add_argument("--db", default="data/local/xauusd_local_store.sqlite")
    ap.add_argument("--returns-table", default=RETURNS_TABLE_DEFAULT)
    ap.add_argument("--reports-dir", default="data/reports/stage38e_macro_context_era_recheck")
    ap.add_argument("--horizons", default=",".join(str(x) for x in DEFAULT_HORIZONS))
    ap.add_argument("--min-sample", type=int, default=DEFAULT_MIN_SAMPLE)
    args = ap.parse_args()

    horizons = [int(x.strip()) for x in str(args.horizons).split(",") if x.strip()]
    ingested_at = utc_now_iso()
    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row

    source_rows = con.execute(f'select count(*) from "{args.returns_table}"').fetchone()[0] if table_exists(con, args.returns_table) else 0
    returns = load_returns(con, args.returns_table)
    summary = build_summary(returns, horizons, args.min_sample, ingested_at)

    pass_count = sum(1 for r in summary if r["decision"] == "PASS_MACRO_CONTEXT_SEPARATION_WATCH")
    watch_count = sum(1 for r in summary if r["decision"] == "WATCH_MACRO_CONTEXT_AFTER_ERA_RECHECK")
    no_count = sum(1 for r in summary if r["decision"] in {"NO_PROMOTION", "BASELINE_CONTEXT_REFERENCE"})
    warnings: List[str] = []
    notes: List[str] = []
    if not returns:
        warnings.append("no_valid_macro_forward_returns")
    if pass_count == 0:
        notes.append("no_macro_context_pass_after_corrected_year_recheck")
    if watch_count > 0:
        notes.append(f"watch_context_count={watch_count}")

    if warnings:
        status = "FAIL"
        decision = "FIX_INPUT_RETURNS_BEFORE_REVIEW"
    elif pass_count > 0:
        status = "PASS"
        decision = "REVIEW_MACRO_CONTEXT_PASS_CANDIDATES_READ_ONLY"
    elif watch_count > 0:
        status = "PASS"
        decision = "WEAK_MACRO_CONTEXT_WATCH_ONLY_NO_BASELINE_PROMOTION"
    else:
        status = "PASS"
        decision = "MACRO_CONTEXT_FOUNDATION_ONLY_NO_PROMOTION"

    reports_dir = Path(args.reports_dir)
    json_path = reports_dir / "stage38e_macro_context_era_recheck.json"
    md_path = reports_dir / "stage38e_macro_context_era_recheck.md"
    payload = {
        "status": status,
        "decision": decision,
        "source_return_rows": source_rows,
        "valid_return_rows": len(returns),
        "summary_rows_written": len(summary),
        "pass_count": pass_count,
        "watch_count": watch_count,
        "no_promotion_count": no_count,
        "warning_count": len(warnings),
        "note_count": len(notes),
        "warnings": warnings,
        "notes": notes,
        "summary_table": SUMMARY_TABLE,
        "audit_table": AUDIT_TABLE,
        "ingested_at_utc": ingested_at,
    }

    drop_output_tables(con)
    create_output_tables(con)
    insert_rows(con, SUMMARY_TABLE, summary)
    insert_rows(con, AUDIT_TABLE, [{
        "status": status,
        "decision": decision,
        "source_return_rows": source_rows,
        "valid_return_rows": len(returns),
        "summary_rows_written": len(summary),
        "pass_count": pass_count,
        "watch_count": watch_count,
        "no_promotion_count": no_count,
        "warning_count": len(warnings),
        "note_count": len(notes),
        "json_report": str(json_path),
        "md_report": str(md_path),
        "ingested_at_utc": ingested_at,
    }])
    con.commit()

    write_json(json_path, payload)
    write_md(md_path, "Stage38E Macro Context Era Recheck", payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
