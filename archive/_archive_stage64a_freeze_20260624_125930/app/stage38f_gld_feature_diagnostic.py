#!/usr/bin/env python3
"""
Stage38F SPDR GLD feature diagnostic.

Read-only diagnostic:
- Uses stage38f_spdr_gld_h1_joined created by stage38f_spdr_gld_loader.py.
- Builds one event per GLD observation date using the first H1 bar that can legally see that GLD observation.
- Computes forward XAUUSD returns at fixed H1 horizons.
- Summarizes whether GLD flow/holding context separates forward returns.

No strategy, no optimization, no paper/live.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

FORWARD_TABLE = "stage38f_gld_forward_returns"
SUMMARY_TABLE = "stage38f_gld_feature_context_summary"
AUDIT_TABLE = "stage38f_gld_feature_diagnostic_audit"

TS_CANDIDATES = ["bar_ts_utc", "utc_time", "ts_utc", "timestamp_utc", "datetime_utc", "time_utc", "timestamp", "datetime", "time"]
CLOSE_CANDIDATES = ["close", "bar_close", "close_price", "mid_close", "price_close"]

DEFAULT_HORIZONS = [24, 72, 120]


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def parse_iso_ts(x: Any) -> Optional[datetime]:
    if x is None:
        return None
    s = str(x).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(x), fmt)
        except Exception:
            continue
    return None


def safe_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        if math.isfinite(float(x)):
            return float(x)
        return None
    s = str(x).strip().replace(",", "")
    if s == "" or s.lower() in {"nan", "none", "null", "na", "n/a", "us holiday"}:
        return None
    try:
        v = float(s)
        return v if math.isfinite(v) else None
    except Exception:
        return None


def qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def get_columns(con: sqlite3.Connection, table: str) -> List[str]:
    rows = con.execute(f"pragma table_info({qident(table)})").fetchall()
    return [r[1] for r in rows]


def require_col(cols: Sequence[str], candidates: Sequence[str], table: str, purpose: str) -> str:
    lower = {c.lower(): c for c in cols}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    raise RuntimeError(f"Cannot detect {purpose} column in {table}. Tried {candidates}. Existing columns: {cols}")


def first_existing(cols: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    lower = {c.lower(): c for c in cols}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    return None


def create_tables(con: sqlite3.Connection) -> None:
    for t in [FORWARD_TABLE, SUMMARY_TABLE, AUDIT_TABLE]:
        con.execute(f"drop table if exists {qident(t)}")

    con.execute(
        f"""
        create table {qident(FORWARD_TABLE)} (
            event_id integer,
            horizon_bars integer,
            event_bar_ts_utc text,
            gld_observation_date text,
            gld_available_from_utc text,
            entry_close real,
            exit_bar_ts_utc text,
            exit_close real,
            forward_return_bps real,
            gld_flow_state text,
            gld_flow_1d_bucket text,
            gld_flow_5d_bucket text,
            gld_flow_20d_bucket text,
            gld_holding_z_bucket text,
            gld_flow_state_x_holding_z text,
            tonnes_gold real,
            gld_tonnes_chg_1d real,
            gld_tonnes_chg_5d real,
            gld_tonnes_chg_20d real,
            gld_tonnes_pct_chg_5d real,
            gld_tonnes_pct_chg_20d real,
            gld_holding_zscore_156d real,
            event_year integer,
            event_month text
        )
        """
    )

    con.execute(
        f"""
        create table {qident(SUMMARY_TABLE)} (
            audit_id integer,
            horizon_bars integer,
            group_type text,
            group_value text,
            sample_count integer,
            mean_return_bps real,
            median_return_bps real,
            win_rate_long real,
            t_stat_mean_bps real,
            diff_vs_all_mean_bps real,
            positive_year_count integer,
            negative_year_count integer,
            max_positive_year text,
            max_positive_year_share real,
            positive_month_count integer,
            negative_month_count integer,
            max_positive_month text,
            max_positive_month_share real,
            pre2025_mean_return_bps real,
            exclude_2025_mean_return_bps real,
            y2025_mean_return_bps real,
            y2026_mean_return_bps real,
            first_half_mean_return_bps real,
            second_half_mean_return_bps real,
            worst_loo_mean_return_bps real,
            worst_loo_excluded_year text,
            decision text,
            note text
        )
        """
    )

    con.execute(
        f"""
        create table {qident(AUDIT_TABLE)} (
            audit_id integer primary key autoincrement,
            created_utc text,
            status text,
            decision text,
            joined_rows_loaded integer,
            event_count integer,
            returns_written integer,
            summary_rows_written integer,
            lookahead_violation_count integer,
            pass_count integer,
            watch_count integer,
            no_promotion_count integer,
            warning_count integer,
            note_count integer,
            json_report text,
            md_report text
        )
        """
    )
    con.commit()


def bucket_flow_tonnes(v: Optional[float], horizon: str) -> str:
    if v is None:
        return f"{horizon}_UNKNOWN"
    # Thresholds in tonnes. Deliberately coarse and pre-declared.
    if horizon == "1D":
        if v >= 2.0:
            return "FLOW_1D_STRONG_INFLOW"
        if v > 0.25:
            return "FLOW_1D_INFLOW"
        if v <= -2.0:
            return "FLOW_1D_STRONG_OUTFLOW"
        if v < -0.25:
            return "FLOW_1D_OUTFLOW"
        return "FLOW_1D_FLAT"
    if horizon == "5D":
        if v >= 5.0:
            return "FLOW_5D_STRONG_INFLOW"
        if v > 1.0:
            return "FLOW_5D_INFLOW"
        if v <= -5.0:
            return "FLOW_5D_STRONG_OUTFLOW"
        if v < -1.0:
            return "FLOW_5D_OUTFLOW"
        return "FLOW_5D_FLAT"
    if horizon == "20D":
        if v >= 15.0:
            return "FLOW_20D_STRONG_INFLOW"
        if v > 3.0:
            return "FLOW_20D_INFLOW"
        if v <= -15.0:
            return "FLOW_20D_STRONG_OUTFLOW"
        if v < -3.0:
            return "FLOW_20D_OUTFLOW"
        return "FLOW_20D_FLAT"
    return f"{horizon}_UNKNOWN"


def bucket_z(z: Optional[float]) -> str:
    if z is None:
        return "HOLDING_Z_UNKNOWN"
    if z >= 1.0:
        return "HOLDING_Z_HIGH"
    if z <= -1.0:
        return "HOLDING_Z_LOW"
    return "HOLDING_Z_NEUTRAL"


def mean(xs: Sequence[float]) -> Optional[float]:
    if not xs:
        return None
    return sum(xs) / len(xs)


def std_sample(xs: Sequence[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    m = sum(xs) / n
    v = sum((x - m) ** 2 for x in xs) / (n - 1)
    return math.sqrt(v)


def t_stat(xs: Sequence[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    sd = std_sample(xs)
    if sd is None or sd == 0:
        return None
    return (sum(xs) / n) / (sd / math.sqrt(n))


def group_net_stats(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    vals = [float(r["forward_return_bps"]) for r in rows if r.get("forward_return_bps") is not None]
    if not vals:
        return {}
    total = sum(vals)
    return {
        "count": len(vals),
        "mean": total / len(vals),
        "median": median(vals),
        "win_rate": sum(1 for x in vals if x > 0) / len(vals),
        "t_stat": t_stat(vals),
        "total": total,
    }


def era_metrics(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    vals = [float(r["forward_return_bps"]) for r in rows if r.get("forward_return_bps") is not None]
    if not vals:
        return {}
    years: Dict[str, List[float]] = {}
    months: Dict[str, List[float]] = {}
    for r in rows:
        v = r.get("forward_return_bps")
        if v is None:
            continue
        y = str(r.get("event_year") or "UNKNOWN")
        m = str(r.get("event_month") or "UNKNOWN")
        years.setdefault(y, []).append(float(v))
        months.setdefault(m, []).append(float(v))

    year_totals = {k: sum(vs) for k, vs in years.items()}
    month_totals = {k: sum(vs) for k, vs in months.items()}
    positive_years = {k: v for k, v in year_totals.items() if v > 0}
    negative_years = {k: v for k, v in year_totals.items() if v < 0}
    positive_months = {k: v for k, v in month_totals.items() if v > 0}
    negative_months = {k: v for k, v in month_totals.items() if v < 0}

    pos_year_total = sum(positive_years.values())
    if positive_years and pos_year_total > 0:
        max_y, max_y_val = max(positive_years.items(), key=lambda kv: kv[1])
        max_y_share = max_y_val / pos_year_total
    else:
        max_y, max_y_share = None, None

    pos_month_total = sum(positive_months.values())
    if positive_months and pos_month_total > 0:
        max_m, max_m_val = max(positive_months.items(), key=lambda kv: kv[1])
        max_m_share = max_m_val / pos_month_total
    else:
        max_m, max_m_share = None, None

    pre2025 = [float(r["forward_return_bps"]) for r in rows if str(r.get("event_year")) < "2025" and r.get("forward_return_bps") is not None]
    ex2025 = [float(r["forward_return_bps"]) for r in rows if str(r.get("event_year")) != "2025" and r.get("forward_return_bps") is not None]
    y2025 = [float(r["forward_return_bps"]) for r in rows if str(r.get("event_year")) == "2025" and r.get("forward_return_bps") is not None]
    y2026 = [float(r["forward_return_bps"]) for r in rows if str(r.get("event_year")) == "2026" and r.get("forward_return_bps") is not None]

    sorted_rows = sorted([r for r in rows if r.get("forward_return_bps") is not None], key=lambda r: str(r.get("event_bar_ts_utc") or ""))
    mid = len(sorted_rows) // 2
    first_half = [float(r["forward_return_bps"]) for r in sorted_rows[:mid]]
    second_half = [float(r["forward_return_bps"]) for r in sorted_rows[mid:]]

    loo = []
    for y in sorted(years):
        subset = [float(r["forward_return_bps"]) for r in rows if str(r.get("event_year")) != y and r.get("forward_return_bps") is not None]
        if subset:
            loo.append((y, sum(subset) / len(subset)))
    if loo:
        worst_y, worst_v = min(loo, key=lambda kv: kv[1])
    else:
        worst_y, worst_v = None, None

    return {
        "positive_year_count": len(positive_years),
        "negative_year_count": len(negative_years),
        "max_positive_year": max_y,
        "max_positive_year_share": max_y_share,
        "positive_month_count": len(positive_months),
        "negative_month_count": len(negative_months),
        "max_positive_month": max_m,
        "max_positive_month_share": max_m_share,
        "pre2025_mean": mean(pre2025),
        "exclude_2025_mean": mean(ex2025),
        "y2025_mean": mean(y2025),
        "y2026_mean": mean(y2026),
        "first_half_mean": mean(first_half),
        "second_half_mean": mean(second_half),
        "worst_loo_mean": worst_v,
        "worst_loo_year": worst_y,
    }


def decide_group(group_type: str, group_value: str, stats: Dict[str, Any], era: Dict[str, Any], diff_vs_all: Optional[float]) -> Tuple[str, str]:
    notes: List[str] = []
    n = stats.get("count") or 0
    m = stats.get("mean")
    med = stats.get("median")
    t = stats.get("t_stat")
    py = era.get("positive_year_count") or 0
    ny = era.get("negative_year_count") or 0
    max_y_share = era.get("max_positive_year_share")
    max_m_share = era.get("max_positive_month_share")
    ex25 = era.get("exclude_2025_mean")
    worst_loo = era.get("worst_loo_mean")
    first = era.get("first_half_mean")
    second = era.get("second_half_mean")

    if n < 60:
        notes.append("LOW_SAMPLE_LT_60")
    if m is not None and abs(m) < 5:
        notes.append("LOW_ABS_MEAN_LT_5BPS")
    if diff_vs_all is not None and abs(diff_vs_all) < 8:
        notes.append("LOW_DIFF_VS_ALL_LT_8BPS")
    if t is None or abs(t) < 1.5:
        notes.append("WEAK_T_STAT_LT_1_5")
    if py < 3:
        notes.append("LOW_POSITIVE_YEAR_COUNT_LT_3")
    if ny >= 3:
        notes.append("MANY_NEGATIVE_YEARS_GE_3")
    if max_y_share is not None and max_y_share > 0.55:
        notes.append("YEAR_CONCENTRATED_GT_55PCT")
    if max_m_share is not None and max_m_share > 0.35:
        notes.append("MONTH_CONCENTRATED_GT_35PCT")
    if m is not None and ex25 is not None and ((m > 0 and ex25 <= 0) or (m < 0 and ex25 >= 0)):
        notes.append("EXCLUDE_2025_SIGN_MISMATCH")
    if m is not None and worst_loo is not None and ((m > 0 and worst_loo <= 0) or (m < 0 and worst_loo >= 0)):
        notes.append("LEAVE_ONE_YEAR_OUT_SIGN_MISMATCH")
    if m is not None and first is not None and second is not None:
        if (m > 0 and (first <= 0 or second <= 0)) or (m < 0 and (first >= 0 or second >= 0)):
            notes.append("CHRONO_HALF_SIGN_MISMATCH")
    if med is not None and m is not None and ((m > 0 and med <= 0) or (m < 0 and med >= 0)):
        notes.append("MEDIAN_SIGN_MISMATCH")

    if group_type == "all":
        return "BASELINE_CONTEXT_REFERENCE", ";".join(notes) if notes else None

    strong = (
        n >= 80
        and diff_vs_all is not None
        and abs(diff_vs_all) >= 12
        and t is not None
        and abs(t) >= 1.75
        and py >= 3
        and (max_y_share is None or max_y_share <= 0.55)
        and (worst_loo is None or m is None or not ((m > 0 and worst_loo <= 0) or (m < 0 and worst_loo >= 0)))
    )
    watch = (
        n >= 60
        and diff_vs_all is not None
        and abs(diff_vs_all) >= 8
        and t is not None
        and abs(t) >= 1.25
    )

    if strong:
        return "PASS_GLD_CONTEXT_SEPARATION_WATCH", ";".join(notes) if notes else None
    if watch:
        return "WATCH_GLD_CONTEXT_AFTER_DIAGNOSTIC", ";".join(notes) if notes else None
    return "NO_PROMOTION", ";".join(notes) if notes else None


def load_joined(con: sqlite3.Connection, table: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    cols = get_columns(con, table)
    if not cols:
        raise RuntimeError(f"Table not found or empty schema: {table}")
    ts_col = require_col(cols, TS_CANDIDATES, table, "bar timestamp")
    close_col = require_col(cols, CLOSE_CANDIDATES, table, "close")
    required = ["gld_observation_date", "gld_available_from_utc"]
    missing = [c for c in required if c not in cols]
    if missing:
        raise RuntimeError(f"Missing required GLD join columns in {table}: {missing}. Existing: {cols}")

    optional = [
        "gld_flow_state",
        "tonnes_gold",
        "gld_tonnes_chg_1d",
        "gld_tonnes_chg_5d",
        "gld_tonnes_chg_20d",
        "gld_tonnes_pct_chg_5d",
        "gld_tonnes_pct_chg_20d",
        "gld_holding_zscore_156d",
    ]
    select_cols = [ts_col, close_col, "gld_observation_date", "gld_available_from_utc"] + [c for c in optional if c in cols]
    sql = f"select {', '.join(qident(c) for c in select_cols)} from {qident(table)} order by {qident(ts_col)}"
    out: List[Dict[str, Any]] = []
    for row in con.execute(sql):
        d = dict(zip(select_cols, row))
        ts = parse_iso_ts(d.get(ts_col))
        cl = safe_float(d.get(close_col))
        if ts is None or cl is None:
            continue
        normalized: Dict[str, Any] = {
            "bar_ts_utc": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "close": cl,
            "gld_observation_date": d.get("gld_observation_date"),
            "gld_available_from_utc": d.get("gld_available_from_utc"),
        }
        for c in optional:
            if c in d:
                normalized[c] = d.get(c)
        out.append(normalized)
    return out, {"ts_col": ts_col, "close_col": close_col, "row_count": len(out)}


def build_event_returns(rows: List[Dict[str, Any]], horizons: Sequence[int]) -> Tuple[List[Dict[str, Any]], int]:
    # First legal H1 bar for each GLD observation date.
    first_by_obs: Dict[str, int] = {}
    lookahead = 0
    for i, r in enumerate(rows):
        obs = str(r.get("gld_observation_date") or "")
        if not obs:
            continue
        bt = parse_iso_ts(r.get("bar_ts_utc"))
        av = parse_iso_ts(r.get("gld_available_from_utc"))
        if bt is not None and av is not None and av > bt:
            lookahead += 1
        if obs not in first_by_obs:
            first_by_obs[obs] = i

    out: List[Dict[str, Any]] = []
    event_id = 0
    for obs, idx in sorted(first_by_obs.items(), key=lambda kv: kv[0]):
        event_id += 1
        er = rows[idx]
        entry_close = er["close"]
        event_dt = parse_iso_ts(er["bar_ts_utc"])
        if event_dt is None:
            continue
        event_year = event_dt.year
        event_month = event_dt.strftime("%Y-%m")
        flow_state = str(er.get("gld_flow_state") or "ETF_FLOW_UNKNOWN")
        chg1 = safe_float(er.get("gld_tonnes_chg_1d"))
        chg5 = safe_float(er.get("gld_tonnes_chg_5d"))
        chg20 = safe_float(er.get("gld_tonnes_chg_20d"))
        z = safe_float(er.get("gld_holding_zscore_156d"))
        b1 = bucket_flow_tonnes(chg1, "1D")
        b5 = bucket_flow_tonnes(chg5, "5D")
        b20 = bucket_flow_tonnes(chg20, "20D")
        bz = bucket_z(z)
        for h in horizons:
            exit_idx = idx + int(h)
            if exit_idx >= len(rows):
                continue
            xr = rows[exit_idx]
            exit_close = xr["close"]
            ret = (exit_close / entry_close - 1.0) * 10000.0
            out.append(
                {
                    "event_id": event_id,
                    "horizon_bars": int(h),
                    "event_bar_ts_utc": er["bar_ts_utc"],
                    "gld_observation_date": obs,
                    "gld_available_from_utc": er.get("gld_available_from_utc"),
                    "entry_close": entry_close,
                    "exit_bar_ts_utc": xr["bar_ts_utc"],
                    "exit_close": exit_close,
                    "forward_return_bps": ret,
                    "gld_flow_state": flow_state,
                    "gld_flow_1d_bucket": b1,
                    "gld_flow_5d_bucket": b5,
                    "gld_flow_20d_bucket": b20,
                    "gld_holding_z_bucket": bz,
                    "gld_flow_state_x_holding_z": f"{flow_state}__{bz}",
                    "tonnes_gold": safe_float(er.get("tonnes_gold")),
                    "gld_tonnes_chg_1d": chg1,
                    "gld_tonnes_chg_5d": chg5,
                    "gld_tonnes_chg_20d": chg20,
                    "gld_tonnes_pct_chg_5d": safe_float(er.get("gld_tonnes_pct_chg_5d")),
                    "gld_tonnes_pct_chg_20d": safe_float(er.get("gld_tonnes_pct_chg_20d")),
                    "gld_holding_zscore_156d": z,
                    "event_year": event_year,
                    "event_month": event_month,
                }
            )
    return out, lookahead


def insert_dicts(con: sqlite3.Connection, table: str, rows: Sequence[Dict[str, Any]]) -> None:
    if not rows:
        return
    keys = list(rows[0].keys())
    sql = f"insert into {qident(table)} ({', '.join(qident(k) for k in keys)}) values ({', '.join(['?'] * len(keys))})"
    con.executemany(sql, [[r.get(k) for k in keys] for r in rows])


def summarize(forward_rows: Sequence[Dict[str, Any]], audit_id: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    horizons = sorted({int(r["horizon_bars"]) for r in forward_rows})
    group_specs = [
        ("all", lambda r: "ALL"),
        ("gld_flow_state", lambda r: r.get("gld_flow_state") or "UNKNOWN"),
        ("gld_flow_1d_bucket", lambda r: r.get("gld_flow_1d_bucket") or "UNKNOWN"),
        ("gld_flow_5d_bucket", lambda r: r.get("gld_flow_5d_bucket") or "UNKNOWN"),
        ("gld_flow_20d_bucket", lambda r: r.get("gld_flow_20d_bucket") or "UNKNOWN"),
        ("gld_holding_z_bucket", lambda r: r.get("gld_holding_z_bucket") or "UNKNOWN"),
        ("gld_flow_state_x_holding_z", lambda r: r.get("gld_flow_state_x_holding_z") or "UNKNOWN"),
    ]

    for h in horizons:
        hrows = [r for r in forward_rows if int(r["horizon_bars"]) == h]
        all_stats = group_net_stats(hrows)
        all_mean = all_stats.get("mean")
        for gtype, fn in group_specs:
            groups: Dict[str, List[Dict[str, Any]]] = {}
            for r in hrows:
                groups.setdefault(str(fn(r)), []).append(r)
            for gval, grows in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
                stats = group_net_stats(grows)
                if not stats:
                    continue
                era = era_metrics(grows)
                diff = None if all_mean is None else stats["mean"] - all_mean
                decision, note = decide_group(gtype, gval, stats, era, diff)
                out.append(
                    {
                        "audit_id": audit_id,
                        "horizon_bars": h,
                        "group_type": gtype,
                        "group_value": gval,
                        "sample_count": stats.get("count"),
                        "mean_return_bps": stats.get("mean"),
                        "median_return_bps": stats.get("median"),
                        "win_rate_long": stats.get("win_rate"),
                        "t_stat_mean_bps": stats.get("t_stat"),
                        "diff_vs_all_mean_bps": diff,
                        "positive_year_count": era.get("positive_year_count"),
                        "negative_year_count": era.get("negative_year_count"),
                        "max_positive_year": era.get("max_positive_year"),
                        "max_positive_year_share": era.get("max_positive_year_share"),
                        "positive_month_count": era.get("positive_month_count"),
                        "negative_month_count": era.get("negative_month_count"),
                        "max_positive_month": era.get("max_positive_month"),
                        "max_positive_month_share": era.get("max_positive_month_share"),
                        "pre2025_mean_return_bps": era.get("pre2025_mean"),
                        "exclude_2025_mean_return_bps": era.get("exclude_2025_mean"),
                        "y2025_mean_return_bps": era.get("y2025_mean"),
                        "y2026_mean_return_bps": era.get("y2026_mean"),
                        "first_half_mean_return_bps": era.get("first_half_mean"),
                        "second_half_mean_return_bps": era.get("second_half_mean"),
                        "worst_loo_mean_return_bps": era.get("worst_loo_mean"),
                        "worst_loo_excluded_year": era.get("worst_loo_year"),
                        "decision": decision,
                        "note": note,
                    }
                )
    return out


def write_reports(args: argparse.Namespace, audit: Dict[str, Any], summary: Sequence[Dict[str, Any]]) -> Tuple[str, str]:
    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "stage38f_gld_feature_diagnostic.json"
    md_path = reports_dir / "stage38f_gld_feature_diagnostic.md"

    top = sorted(summary, key=lambda r: (0 if r["decision"] == "PASS_GLD_CONTEXT_SEPARATION_WATCH" else 1 if r["decision"].startswith("WATCH") else 2, -abs(r.get("diff_vs_all_mean_bps") or 0)))[:40]
    payload = {"audit": audit, "top_summary_rows": top}
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    lines = [
        "# Stage38F GLD Feature Diagnostic",
        "",
        "## Audit",
        "",
        "```text",
    ]
    for k, v in audit.items():
        lines.append(f"{k}: {v}")
    lines.extend(["```", "", "## Top rows", "", "|decision|horizon|group_type|group_value|n|mean|diff_vs_all|t|pos_years|neg_years|note|", "|---|---:|---|---|---:|---:|---:|---:|---:|---:|---|"])
    for r in top:
        lines.append(
            f"|{r.get('decision')}|{r.get('horizon_bars')}|{r.get('group_type')}|{r.get('group_value')}|{r.get('sample_count')}|"
            f"{(r.get('mean_return_bps') or 0):.2f}|{(r.get('diff_vs_all_mean_bps') or 0):.2f}|{(r.get('t_stat_mean_bps') or 0):.2f}|"
            f"{r.get('positive_year_count')}|{r.get('negative_year_count')}|{r.get('note') or ''}|"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(json_path), str(md_path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--joined-table", default="stage38f_spdr_gld_h1_joined")
    ap.add_argument("--horizons", default=",".join(str(x) for x in DEFAULT_HORIZONS))
    ap.add_argument("--reports-dir", default="data/reports/stage38f_gld_feature_diagnostic")
    args = ap.parse_args()

    horizons = [int(x.strip()) for x in args.horizons.split(",") if x.strip()]
    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    create_tables(con)

    joined, meta = load_joined(con, args.joined_table)
    forward_rows, lookahead_count = build_event_returns(joined, horizons)
    insert_dicts(con, FORWARD_TABLE, forward_rows)
    con.commit()

    # Reserve audit_id by inserting placeholder.
    cur = con.execute(
        f"insert into {qident(AUDIT_TABLE)} (created_utc, status, decision) values (?, ?, ?)",
        (utc_now_iso(), "RUNNING", "RUNNING"),
    )
    audit_id = int(cur.lastrowid)
    con.commit()

    summary_rows = summarize(forward_rows, audit_id)
    insert_dicts(con, SUMMARY_TABLE, summary_rows)

    pass_count = sum(1 for r in summary_rows if r.get("decision") == "PASS_GLD_CONTEXT_SEPARATION_WATCH")
    watch_count = sum(1 for r in summary_rows if str(r.get("decision") or "").startswith("WATCH"))
    no_promotion_count = sum(1 for r in summary_rows if r.get("decision") == "NO_PROMOTION")
    note_count = sum(1 for r in summary_rows if r.get("note"))
    warning_count = 0
    status = "PASS" if forward_rows and lookahead_count == 0 else "FAIL"
    if pass_count > 0:
        decision = "REVIEW_GLD_CONTEXT_PASS_CANDIDATES_READ_ONLY"
    elif watch_count > 0:
        decision = "GLD_CONTEXT_WATCH_ONLY_NO_PROMOTION"
    else:
        decision = "GLD_CONTEXT_NO_PROMOTION_KEEP_DATA_FOUNDATION"

    audit_payload = {
        "status": status,
        "decision": decision,
        "joined_rows_loaded": meta["row_count"],
        "event_count": len({r["event_id"] for r in forward_rows}),
        "returns_written": len(forward_rows),
        "summary_rows_written": len(summary_rows),
        "lookahead_violation_count": lookahead_count,
        "pass_count": pass_count,
        "watch_count": watch_count,
        "no_promotion_count": no_promotion_count,
        "warning_count": warning_count,
        "note_count": note_count,
    }
    json_report, md_report = write_reports(args, audit_payload, summary_rows)
    audit_payload["json_report"] = json_report
    audit_payload["md_report"] = md_report

    con.execute(
        f"""
        update {qident(AUDIT_TABLE)}
        set status=?, decision=?, joined_rows_loaded=?, event_count=?, returns_written=?,
            summary_rows_written=?, lookahead_violation_count=?, pass_count=?, watch_count=?,
            no_promotion_count=?, warning_count=?, note_count=?, json_report=?, md_report=?
        where audit_id=?
        """,
        (
            status,
            decision,
            audit_payload["joined_rows_loaded"],
            audit_payload["event_count"],
            audit_payload["returns_written"],
            audit_payload["summary_rows_written"],
            lookahead_count,
            pass_count,
            watch_count,
            no_promotion_count,
            warning_count,
            note_count,
            json_report,
            md_report,
            audit_id,
        ),
    )
    con.commit()

    print(json.dumps(audit_payload, indent=2, ensure_ascii=False))
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
