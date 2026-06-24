#!/usr/bin/env python3
"""
Stage38E — Macro Context Diagnostic

Purpose
-------
Read-only diagnostic to test whether free macro/risk states separate XAUUSD
forward returns after the Stage38E macro/H1 anti-lookahead join.

This is NOT a strategy, NOT a backtest, NOT optimization, and NOT ML.
No Stage39, no EA, no paper-live, no live order.

Primary methodology
-------------------
Macro/risk observations are daily. Repeating the same macro row on all H1 bars
creates non-independent samples. Therefore the primary sample is event-level:
for each macro_observation_date, select the first H1 bar whose timestamp is >=
macro_available_from_utc. Forward returns are then measured from that bar.

Default horizons:
    24H, 72H, 120H

Output tables
-------------
    stage38e_macro_forward_returns
    stage38e_macro_context_summary
    stage38e_macro_context_audit
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
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

JOINED_TABLE_DEFAULT = "stage38e_macro_risk_h1_joined"
RETURNS_TABLE = "stage38e_macro_forward_returns"
SUMMARY_TABLE = "stage38e_macro_context_summary"
AUDIT_TABLE = "stage38e_macro_context_audit"

DEFAULT_HORIZONS = [24, 72, 120]


@dataclass
class DiagnosticConfig:
    db: str
    joined_table: str
    reports_dir: str
    horizons: List[int]
    min_sample: int


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
        try:
            dt = datetime.strptime(str(value).strip(), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(microsecond=0)


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


def safe_div(a: float, b: float) -> Optional[float]:
    if b == 0:
        return None
    return a / b


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_md(path: Path, title: str, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {title}", "", "```json", json.dumps(payload, indent=2, sort_keys=True), "```", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


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
    for t in [RETURNS_TABLE, SUMMARY_TABLE, AUDIT_TABLE]:
        con.execute(f'drop table if exists "{t}"')


def create_output_tables(con: sqlite3.Connection) -> None:
    con.execute(
        f'''
        create table "{RETURNS_TABLE}" (
            row_id integer primary key autoincrement,
            sample_level text not null,
            macro_observation_date text not null,
            macro_available_from_utc text not null,
            event_bar_ts_utc text not null,
            horizon_bars integer not null,
            horizon_hours integer not null,
            entry_close real not null,
            future_bar_ts_utc text,
            future_close real,
            forward_return_bps real,
            forward_return_pct real,
            macro_gold_pressure text,
            macro_risk_state text,
            macro_bias text,
            real_yield_5d_bucket text,
            dollar_5d_bucket text,
            vix_5d_bucket text,
            pressure_x_risk text,
            dgs10 real,
            dgs2 real,
            dfii10 real,
            t10yie real,
            dtwexbgs real,
            vixcls real,
            curve_10y2y real,
            real_10y_chg_5d real,
            dollar_chg_5d real,
            vix_chg_5d real,
            event_year integer,
            event_month text,
            lookahead_violation integer not null default 0,
            ingested_at_utc text not null
        )
        '''
    )
    con.execute(
        f'''
        create table "{SUMMARY_TABLE}" (
            summary_id integer primary key autoincrement,
            sample_level text not null,
            group_type text not null,
            group_value text not null,
            horizon_bars integer not null,
            horizon_hours integer not null,
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
            joined_rows_loaded integer not null,
            event_count integer not null,
            returns_written integer not null,
            summary_rows_written integer not null,
            lookahead_violation_count integer not null,
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


def bucket_real_yield(x: Optional[float]) -> str:
    if x is None:
        return "REAL_5D_UNKNOWN"
    if x > 0.05:
        return "REAL_5D_UP"
    if x < -0.05:
        return "REAL_5D_DOWN"
    return "REAL_5D_FLAT"


def bucket_dollar(x: Optional[float]) -> str:
    if x is None:
        return "USD_5D_UNKNOWN"
    if x > 0.5:
        return "USD_5D_UP"
    if x < -0.5:
        return "USD_5D_DOWN"
    return "USD_5D_FLAT"


def bucket_vix(x: Optional[float]) -> str:
    if x is None:
        return "VIX_5D_UNKNOWN"
    if x > 3.0:
        return "VIX_5D_UP"
    if x < -3.0:
        return "VIX_5D_DOWN"
    return "VIX_5D_FLAT"


def macro_bias(real_5d: Optional[float], dollar_5d: Optional[float]) -> str:
    real_b = bucket_real_yield(real_5d)
    usd_b = bucket_dollar(dollar_5d)
    if real_b == "REAL_5D_DOWN" and usd_b == "USD_5D_DOWN":
        return "MACRO_SUPPORTIVE_GOLD"
    if real_b == "REAL_5D_UP" and usd_b == "USD_5D_UP":
        return "MACRO_HOSTILE_GOLD"
    if real_b == "REAL_5D_UNKNOWN" or usd_b == "USD_5D_UNKNOWN":
        return "MACRO_UNKNOWN"
    return "MACRO_MIXED"


def load_joined_rows(con: sqlite3.Connection, table: str) -> List[Dict[str, Any]]:
    if not table_exists(con, table):
        raise RuntimeError(f"joined table not found: {table}")
    required = [
        "bar_ts_utc", "close", "macro_observation_date", "macro_available_from_utc",
        "macro_gold_pressure", "macro_risk_state", "real_10y_chg_5d", "dollar_chg_5d", "vix_chg_5d",
    ]
    require_columns(con, table, required)
    optional = ["dgs10", "dgs2", "dfii10", "t10yie", "dtwexbgs", "vixcls", "curve_10y2y"]
    select_cols = required + [c for c in optional if c in columns(con, table)]
    rows: List[Dict[str, Any]] = []
    for rec in con.execute(f'select {", ".join(f"\"{c}\"" for c in select_cols)} from "{table}" order by bar_ts_utc'):
        d = dict(zip(select_cols, rec))
        bar_dt = parse_iso_dt(d.get("bar_ts_utc"))
        avail_dt = parse_iso_dt(d.get("macro_available_from_utc"))
        close = safe_float(d.get("close"))
        if bar_dt is None or avail_dt is None or close is None or close <= 0:
            continue
        for c in ["dgs10", "dgs2", "dfii10", "t10yie", "dtwexbgs", "vixcls", "curve_10y2y", "real_10y_chg_5d", "dollar_chg_5d", "vix_chg_5d"]:
            if c in d:
                d[c] = safe_float(d.get(c))
        d["bar_dt"] = bar_dt
        d["avail_dt"] = avail_dt
        d["close"] = close
        rows.append(d)
    return rows


def select_event_indices(rows: Sequence[Dict[str, Any]]) -> List[int]:
    # First bar for each macro observation date after the macro availability timestamp.
    out: List[int] = []
    seen: set[str] = set()
    for i, r in enumerate(rows):
        obs = str(r["macro_observation_date"])
        if obs in seen:
            continue
        if r["bar_dt"] >= r["avail_dt"]:
            seen.add(obs)
            out.append(i)
    return out


def compute_forward_returns(rows: Sequence[Dict[str, Any]], event_indices: Sequence[int], horizons: Sequence[int], ingested_at: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    n = len(rows)
    for idx in event_indices:
        r = rows[idx]
        event_year = int(str(r["macro_observation_date"])[:4])
        event_month = str(r["macro_observation_date"])[:7]
        real_5d = r.get("real_10y_chg_5d")
        usd_5d = r.get("dollar_chg_5d")
        vix_5d = r.get("vix_chg_5d")
        real_bucket = bucket_real_yield(real_5d)
        usd_bucket = bucket_dollar(usd_5d)
        vix_bucket = bucket_vix(vix_5d)
        bias = macro_bias(real_5d, usd_5d)
        pressure = str(r.get("macro_gold_pressure") or "UNKNOWN")
        risk = str(r.get("macro_risk_state") or "UNKNOWN")
        pressure_x_risk = f"{pressure}__{risk}"
        violation = 1 if r["avail_dt"] > r["bar_dt"] else 0
        for h in horizons:
            fidx = idx + h
            future_ts = None
            future_close = None
            ret_bps = None
            ret_pct = None
            if fidx < n:
                fr = rows[fidx]
                future_ts = fr["bar_ts_utc"]
                future_close = fr["close"]
                ret_pct = (future_close / r["close"] - 1.0) * 100.0
                ret_bps = (future_close / r["close"] - 1.0) * 10000.0
            out.append({
                "sample_level": "event_level",
                "macro_observation_date": r["macro_observation_date"],
                "macro_available_from_utc": r["macro_available_from_utc"],
                "event_bar_ts_utc": r["bar_ts_utc"],
                "horizon_bars": int(h),
                "horizon_hours": int(h),
                "entry_close": r["close"],
                "future_bar_ts_utc": future_ts,
                "future_close": future_close,
                "forward_return_bps": ret_bps,
                "forward_return_pct": ret_pct,
                "macro_gold_pressure": pressure,
                "macro_risk_state": risk,
                "macro_bias": bias,
                "real_yield_5d_bucket": real_bucket,
                "dollar_5d_bucket": usd_bucket,
                "vix_5d_bucket": vix_bucket,
                "pressure_x_risk": pressure_x_risk,
                "dgs10": r.get("dgs10"),
                "dgs2": r.get("dgs2"),
                "dfii10": r.get("dfii10"),
                "t10yie": r.get("t10yie"),
                "dtwexbgs": r.get("dtwexbgs"),
                "vixcls": r.get("vixcls"),
                "curve_10y2y": r.get("curve_10y2y"),
                "real_10y_chg_5d": real_5d,
                "dollar_chg_5d": usd_5d,
                "vix_chg_5d": vix_5d,
                "event_year": event_year,
                "event_month": event_month,
                "lookahead_violation": violation,
                "ingested_at_utc": ingested_at,
            })
    return out


def mean(xs: Sequence[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def std_sample(xs: Sequence[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def contribution_stats(rows: Sequence[Dict[str, Any]], key: str) -> Dict[str, Any]:
    totals: Dict[str, float] = {}
    for r in rows:
        v = r.get("forward_return_bps")
        if v is None:
            continue
        k = str(r.get(key))
        totals[k] = totals.get(k, 0.0) + float(v)
    pos = {k: v for k, v in totals.items() if v > 0}
    neg = {k: v for k, v in totals.items() if v < 0}
    if pos:
        max_k, max_v = max(pos.items(), key=lambda kv: kv[1])
        total_pos = sum(pos.values())
        share = max_v / total_pos if total_pos else None
    else:
        max_k, share = None, None
    return {
        f"positive_{key}_count": len(pos),
        f"negative_{key}_count": len(neg),
        f"max_positive_{key}": max_k,
        f"max_positive_{key}_share": share,
    }


def build_summary(returns: Sequence[Dict[str, Any]], horizons: Sequence[int], min_sample: int, ingested_at: str) -> List[Dict[str, Any]]:
    rows_valid = [r for r in returns if r.get("forward_return_bps") is not None]
    all_mean_by_h: Dict[int, float] = {}
    for h in horizons:
        vals = [float(r["forward_return_bps"]) for r in rows_valid if r["horizon_bars"] == h]
        all_mean_by_h[h] = mean(vals) or 0.0

    group_specs = [
        ("all", lambda r: "ALL"),
        ("macro_gold_pressure", lambda r: r.get("macro_gold_pressure") or "UNKNOWN"),
        ("macro_risk_state", lambda r: r.get("macro_risk_state") or "UNKNOWN"),
        ("macro_bias", lambda r: r.get("macro_bias") or "UNKNOWN"),
        ("real_yield_5d_bucket", lambda r: r.get("real_yield_5d_bucket") or "UNKNOWN"),
        ("dollar_5d_bucket", lambda r: r.get("dollar_5d_bucket") or "UNKNOWN"),
        ("vix_5d_bucket", lambda r: r.get("vix_5d_bucket") or "UNKNOWN"),
        ("pressure_x_risk", lambda r: r.get("pressure_x_risk") or "UNKNOWN"),
    ]

    summaries: List[Dict[str, Any]] = []
    for h in horizons:
        rows_h = [r for r in rows_valid if r["horizon_bars"] == h]
        for gtype, getter in group_specs:
            groups: Dict[str, List[Dict[str, Any]]] = {}
            for r in rows_h:
                groups.setdefault(str(getter(r)), []).append(r)
            for gval, gr in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
                vals = [float(r["forward_return_bps"]) for r in gr]
                if not vals:
                    continue
                n = len(vals)
                m = mean(vals)
                med = median(vals)
                st = std_sample(vals)
                t_stat = None if st is None or st == 0 else m / (st / math.sqrt(n))
                win_rate = sum(1 for x in vals if x > 0) / n
                total = sum(vals)
                year_stats = contribution_stats(gr, "year")
                month_stats = contribution_stats(gr, "month")
                diff = None if m is None else m - all_mean_by_h.get(h, 0.0)
                notes: List[str] = []
                if n < min_sample and gtype != "all":
                    notes.append(f"LOW_SAMPLE_LT_{min_sample}")
                if abs(m or 0.0) < 5 and gtype != "all":
                    notes.append("LOW_ABS_MEAN_LT_5BPS")
                if abs(diff or 0.0) < 5 and gtype != "all":
                    notes.append("LOW_DIFF_VS_ALL_LT_5BPS")
                if year_stats.get("max_positive_year_share") is not None and year_stats["max_positive_year_share"] > 0.55:
                    notes.append("YEAR_CONCENTRATED_GT_55PCT")
                if year_stats.get("positive_year_count", 0) < 3 and gtype != "all":
                    notes.append("LOW_POSITIVE_YEAR_COUNT_LT_3")
                if gtype == "all":
                    decision = "BASELINE_CONTEXT_REFERENCE"
                elif n >= min_sample and abs(diff or 0.0) >= 10 and year_stats.get("positive_year_count", 0) >= 3 and not any("YEAR_CONCENTRATED" in x for x in notes):
                    decision = "PASS_MACRO_CONTEXT_SEPARATION_WATCH"
                elif n >= min_sample and abs(diff or 0.0) >= 5:
                    decision = "WATCH_MACRO_CONTEXT"
                else:
                    decision = "NO_PROMOTION"
                summaries.append({
                    "sample_level": "event_level",
                    "group_type": gtype,
                    "group_value": gval,
                    "horizon_bars": h,
                    "horizon_hours": h,
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
                    "decision": decision,
                    "note": ";".join(notes) if notes else None,
                    "ingested_at_utc": ingested_at,
                })
    return summaries


def audit_decision(joined_rows: int, event_count: int, returns_written: int, summaries: Sequence[Dict[str, Any]], lookahead_count: int) -> Tuple[str, str, List[str], List[str]]:
    warnings: List[str] = []
    notes: List[str] = []
    if joined_rows <= 0:
        warnings.append("no_joined_rows_loaded")
    if event_count < 200:
        warnings.append(f"low_event_count={event_count}")
    if returns_written <= 0:
        warnings.append("no_returns_written")
    if lookahead_count:
        warnings.append(f"lookahead_violations={lookahead_count}")
    pass_rows = [r for r in summaries if r.get("decision") == "PASS_MACRO_CONTEXT_SEPARATION_WATCH"]
    watch_rows = [r for r in summaries if r.get("decision") == "WATCH_MACRO_CONTEXT"]
    if pass_rows:
        notes.append(f"pass_macro_context_rows={len(pass_rows)}")
    if watch_rows:
        notes.append(f"watch_macro_context_rows={len(watch_rows)}")
    if warnings:
        return "FAIL", "DO_NOT_PROCEED_REPAIR_STAGE38E_DIAGNOSTIC", warnings, notes
    if pass_rows:
        return "PASS", "PROCEED_TO_STAGE38E_MACRO_CONTEXT_REVIEW_WITH_CAUTION", warnings, notes
    if watch_rows:
        return "PASS", "REVIEW_WEAK_MACRO_CONTEXT_SEPARATION_BEFORE_ANY_BASELINE", warnings, notes
    return "PASS", "NO_STRONG_MACRO_CONTEXT_SEPARATION_REVIEW_OR_ARCHIVE", warnings, notes


def parse_horizons(s: str) -> List[int]:
    out = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        x = int(part)
        if x <= 0:
            raise argparse.ArgumentTypeError("horizons must be positive integers")
        out.append(x)
    if not out:
        raise argparse.ArgumentTypeError("empty horizons")
    return sorted(set(out))


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Stage38E macro context diagnostic")
    ap.add_argument("--db", default="data/local/xauusd_local_store.sqlite")
    ap.add_argument("--joined-table", default=JOINED_TABLE_DEFAULT)
    ap.add_argument("--reports-dir", default="data/reports/stage38e_macro_context_diagnostic")
    ap.add_argument("--horizons", default="24,72,120", help="comma-separated H1 bar horizons")
    ap.add_argument("--min-sample", type=int, default=60)
    args = ap.parse_args(argv)

    cfg = DiagnosticConfig(
        db=args.db,
        joined_table=args.joined_table,
        reports_dir=args.reports_dir,
        horizons=parse_horizons(args.horizons),
        min_sample=args.min_sample,
    )
    ingested_at = utc_now_iso()
    con = sqlite3.connect(cfg.db)
    con.row_factory = sqlite3.Row

    try:
        joined_rows = load_joined_rows(con, cfg.joined_table)
        event_indices = select_event_indices(joined_rows)
        returns = compute_forward_returns(joined_rows, event_indices, cfg.horizons, ingested_at)
        summaries = build_summary(returns, cfg.horizons, cfg.min_sample, ingested_at)
        lookahead_count = sum(int(r.get("lookahead_violation") or 0) for r in returns)
        status, decision, warnings, notes = audit_decision(len(joined_rows), len(event_indices), len(returns), summaries, lookahead_count)

        drop_output_tables(con)
        create_output_tables(con)
        insert_rows(con, RETURNS_TABLE, returns)
        insert_rows(con, SUMMARY_TABLE, summaries)

        report_dir = Path(cfg.reports_dir)
        json_path = report_dir / "stage38e_macro_context_diagnostic.json"
        md_path = report_dir / "stage38e_macro_context_diagnostic.md"
        payload = {
            "status": status,
            "decision": decision,
            "joined_table": cfg.joined_table,
            "joined_rows_loaded": len(joined_rows),
            "event_count": len(event_indices),
            "horizons": cfg.horizons,
            "returns_written": len(returns),
            "summary_rows_written": len(summaries),
            "lookahead_violation_count": lookahead_count,
            "warning_count": len(warnings),
            "note_count": len(notes),
            "warnings": warnings,
            "notes": notes,
            "returns_table": RETURNS_TABLE,
            "summary_table": SUMMARY_TABLE,
            "audit_table": AUDIT_TABLE,
            "json_report": str(json_path),
            "md_report": str(md_path),
            "ingested_at_utc": ingested_at,
        }
        write_json(json_path, payload)
        write_md(md_path, "Stage38E Macro Context Diagnostic", payload)

        insert_rows(con, AUDIT_TABLE, [{
            "status": status,
            "decision": decision,
            "joined_rows_loaded": len(joined_rows),
            "event_count": len(event_indices),
            "returns_written": len(returns),
            "summary_rows_written": len(summaries),
            "lookahead_violation_count": lookahead_count,
            "warning_count": len(warnings),
            "note_count": len(notes),
            "json_report": str(json_path),
            "md_report": str(md_path),
            "ingested_at_utc": ingested_at,
        }])
        con.commit()
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if status == "PASS" else 2
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
