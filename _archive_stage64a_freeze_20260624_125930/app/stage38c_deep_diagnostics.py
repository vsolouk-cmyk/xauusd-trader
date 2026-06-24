#!/usr/bin/env python3
"""
Stage38C — Simple Baseline Deep Diagnostics for XAUUSD H1 baseline candidates.

Read-only diagnostics only.
No orders, no paper-live, no EA, no Stage39 promotion.

Input tables produced by app/stage38c_simple_baseline_lab.py:
- stage38c_baseline_events
- stage38c_baseline_summary

Purpose:
- Stress-test the Stage38C PASS/WATCH baseline candidates before any further
  research, using year/month concentration, 2025 ablation, chronological split,
  cost sensitivity, and COT annotation diagnostics.

This script intentionally does not create trade signals. It only diagnoses
already-generated read-only baseline events.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median, pstdev
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

DEFAULT_COST_MULTIPLIERS = [0.0, 0.5, 1.0, 1.5, 2.0]
DEFAULT_INCLUDE_DECISIONS = ["PASS_RESEARCH_INTEREST"]


def qident(name: str) -> str:
    if not name or any(ch in name for ch in '"\x00'):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return '"' + name.replace('"', '""') + '"'


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (table,)
    ).fetchone() is not None


def parse_csv_list(s: str) -> List[str]:
    return [p.strip() for p in s.split(",") if p.strip()]


def parse_float_list(s: str) -> List[float]:
    out: List[float] = []
    for part in s.split(","):
        part = part.strip()
        if part:
            out.append(float(part))
    if not out:
        raise argparse.ArgumentTypeError("empty float list")
    return out


def safe_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        f = float(x)
    except Exception:
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def mean(values: Sequence[float]) -> Optional[float]:
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def t_stat(values: Sequence[float]) -> Optional[float]:
    vals = [float(v) for v in values if v is not None]
    n = len(vals)
    if n < 2:
        return None
    sd = pstdev(vals)
    if sd <= 1e-12:
        return None
    return (sum(vals) / n) / (sd / math.sqrt(n))


def win_rate(values: Sequence[float]) -> Optional[float]:
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return None
    return sum(1 for v in vals if v > 0) / len(vals)


def max_drawdown(series: Sequence[float]) -> float:
    peak = 0.0
    cum = 0.0
    max_dd = 0.0
    for x in series:
        cum += float(x)
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd
    return max_dd


def positive_contribution_share(group_sums: Dict[Any, float]) -> Optional[float]:
    positives = [v for v in group_sums.values() if v > 0]
    if not positives:
        return None
    total = sum(positives)
    if total <= 0:
        return None
    return max(positives) / total


def split_stats(events: Sequence[Dict[str, Any]], value_key: str = "net_bps") -> Dict[str, Any]:
    vals = [float(e[value_key]) for e in events if e.get(value_key) is not None]
    years: Dict[int, float] = defaultdict(float)
    months: Dict[str, float] = defaultdict(float)
    for e in events:
        if e.get(value_key) is None:
            continue
        years[int(e["entry_year"])] += float(e[value_key])
        months[str(e["entry_month"])] += float(e[value_key])
    pos_years = sum(1 for v in years.values() if v > 0)
    neg_years = sum(1 for v in years.values() if v < 0)
    return {
        "sample_count": len(vals),
        "mean_bps": mean(vals),
        "median_bps": median(vals) if vals else None,
        "win_rate": win_rate(vals),
        "t_stat": t_stat(vals),
        "total_bps": sum(vals) if vals else None,
        "max_drawdown_bps": max_drawdown(vals),
        "positive_year_count": pos_years,
        "negative_year_count": neg_years,
        "max_positive_year_share": positive_contribution_share(years),
        "max_positive_month_share": positive_contribution_share(months),
        "year_net_bps": {str(k): round(v, 6) for k, v in sorted(years.items())},
        "month_net_bps": {str(k): round(v, 6) for k, v in sorted(months.items())},
    }


def load_candidate_keys(
    con: sqlite3.Connection,
    summary_table: str,
    include_decisions: Sequence[str],
    top_watch: int,
    min_sample: int,
) -> List[Tuple[str, str, int]]:
    if not table_exists(con, summary_table):
        raise RuntimeError(f"Missing summary table: {summary_table}")

    keys: List[Tuple[str, str, int]] = []
    seen = set()

    placeholders = ",".join("?" for _ in include_decisions)
    rows = con.execute(
        f"""
        SELECT baseline_family, baseline_name, horizon_bars, decision, sample_count, mean_net_bps
        FROM {qident(summary_table)}
        WHERE decision IN ({placeholders}) AND sample_count >= ?
        ORDER BY decision, mean_net_bps DESC, sample_count DESC
        """,
        [*include_decisions, min_sample],
    ).fetchall()
    for family, name, horizon, *_ in rows:
        key = (family, name, int(horizon))
        if key not in seen:
            keys.append(key)
            seen.add(key)

    if top_watch > 0:
        watch_rows = con.execute(
            f"""
            SELECT baseline_family, baseline_name, horizon_bars, mean_net_bps, sample_count
            FROM {qident(summary_table)}
            WHERE decision = 'WATCH' AND sample_count >= ?
            ORDER BY mean_net_bps DESC, sample_count DESC
            LIMIT ?
            """,
            (min_sample, top_watch),
        ).fetchall()
        for family, name, horizon, *_ in watch_rows:
            key = (family, name, int(horizon))
            if key not in seen:
                keys.append(key)
                seen.add(key)

    return keys


def load_events_for_key(
    con: sqlite3.Connection,
    events_table: str,
    key: Tuple[str, str, int],
) -> List[Dict[str, Any]]:
    family, name, horizon = key
    rows = con.execute(
        f"""
        SELECT event_id, baseline_family, baseline_name, horizon_bars,
               entry_ts_utc, exit_ts_utc, entry_date_utc, entry_year, entry_month,
               entry_hour_utc, direction, entry_price, exit_price,
               gross_bps, cost_bps, net_bps, signal_detail,
               cot_state, cot_pressure, cot_crowding_score
        FROM {qident(events_table)}
        WHERE baseline_family = ? AND baseline_name = ? AND horizon_bars = ?
        ORDER BY entry_ts_utc, event_id
        """,
        (family, name, horizon),
    ).fetchall()
    cols = [
        "event_id", "baseline_family", "baseline_name", "horizon_bars",
        "entry_ts_utc", "exit_ts_utc", "entry_date_utc", "entry_year", "entry_month",
        "entry_hour_utc", "direction", "entry_price", "exit_price",
        "gross_bps", "cost_bps", "net_bps", "signal_detail",
        "cot_state", "cot_pressure", "cot_crowding_score",
    ]
    out: List[Dict[str, Any]] = []
    for row in rows:
        d = dict(zip(cols, row))
        for k in ["gross_bps", "cost_bps", "net_bps", "cot_crowding_score"]:
            d[k] = safe_float(d.get(k))
        d["entry_year"] = int(d["entry_year"])
        d["horizon_bars"] = int(d["horizon_bars"])
        out.append(d)
    return out


def cost_sensitivity(events: Sequence[Dict[str, Any]], multipliers: Sequence[float]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for m in multipliers:
        vals: List[float] = []
        for e in events:
            gross = e.get("gross_bps")
            cost = e.get("cost_bps")
            if gross is None or cost is None:
                continue
            vals.append(float(gross) - float(cost) * float(m))
        out[f"cost_x_{m:g}"] = {
            "mean_bps": mean(vals),
            "median_bps": median(vals) if vals else None,
            "win_rate": win_rate(vals),
            "t_stat": t_stat(vals),
            "max_drawdown_bps": max_drawdown(vals),
        }
    return out


def leave_one_year_out(events: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    years = sorted({int(e["entry_year"]) for e in events})
    rows = []
    worst_mean = None
    worst_year = None
    for y in years:
        vals = [float(e["net_bps"]) for e in events if int(e["entry_year"]) != y]
        m = mean(vals)
        rows.append({"excluded_year": y, "sample_count": len(vals), "mean_net_bps": m})
        if m is not None and (worst_mean is None or m < worst_mean):
            worst_mean = m
            worst_year = y
    return {"rows": rows, "worst_excluded_year": worst_year, "worst_loo_mean_net_bps": worst_mean}


def cot_breakdown(events: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    by_state: Dict[str, List[float]] = defaultdict(list)
    by_pressure: Dict[str, List[float]] = defaultdict(list)
    for e in events:
        v = e.get("net_bps")
        if v is None:
            continue
        by_state[str(e.get("cot_state") or "UNKNOWN")].append(float(v))
        by_pressure[str(e.get("cot_pressure") or "UNKNOWN")].append(float(v))

    def summarize(d: Dict[str, List[float]]) -> Dict[str, Any]:
        return {
            k: {
                "sample_count": len(vals),
                "mean_net_bps": mean(vals),
                "median_net_bps": median(vals) if vals else None,
                "win_rate_net": win_rate(vals),
            }
            for k, vals in sorted(d.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        }

    return {"cot_state": summarize(by_state), "cot_pressure": summarize(by_pressure)}


def chronological_halves(events: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(events)
    if n == 0:
        return {}
    mid = n // 2
    first = events[:mid]
    second = events[mid:]
    return {
        "first_half": split_stats(first),
        "second_half": split_stats(second),
        "second_minus_first_mean_bps": (
            (split_stats(second).get("mean_bps") or 0.0) - (split_stats(first).get("mean_bps") or 0.0)
            if first and second else None
        ),
    }


def make_decision(metrics: Dict[str, Any], strict: bool = True) -> Tuple[str, str]:
    base = metrics["base"]
    exclude_2025 = metrics["exclude_2025"]
    y2025 = metrics["y2025_only"]
    cost = metrics["cost_sensitivity"]
    chrono = metrics["chronological_halves"]
    loo = metrics["leave_one_year_out"]

    notes: List[str] = []

    sample = base.get("sample_count") or 0
    mean_bps = base.get("mean_bps") or 0.0
    median_bps = base.get("median_bps") or 0.0
    t = base.get("t_stat") or 0.0
    pos_years = base.get("positive_year_count") or 0
    neg_years = base.get("negative_year_count") or 0
    max_year_share = base.get("max_positive_year_share")
    max_month_share = base.get("max_positive_month_share")
    ex2025_mean = exclude_2025.get("mean_bps")
    y2025_mean = y2025.get("mean_bps")
    cost15_mean = (cost.get("cost_x_1.5") or {}).get("mean_bps")
    cost20_mean = (cost.get("cost_x_2") or {}).get("mean_bps")
    first_mean = ((chrono.get("first_half") or {}).get("mean_bps"))
    second_mean = ((chrono.get("second_half") or {}).get("mean_bps"))
    worst_loo = loo.get("worst_loo_mean_net_bps")

    if sample < 200:
        notes.append("LOW_SAMPLE_LT_200")
    if mean_bps < 5.0:
        notes.append("LOW_MEAN_LT_5BPS")
    if median_bps <= 0:
        notes.append("NON_POSITIVE_MEDIAN")
    if t < 1.5:
        notes.append("WEAK_T_STAT_LT_1_5")
    if pos_years < 3:
        notes.append("LOW_POSITIVE_YEAR_COUNT_LT_3")
    if neg_years >= 3:
        notes.append("MANY_NEGATIVE_YEARS_GE_3")
    if max_year_share is not None and max_year_share > 0.55:
        notes.append("YEAR_CONCENTRATED_GT_55PCT")
    if max_month_share is not None and max_month_share > 0.35:
        notes.append("MONTH_CONCENTRATED_GT_35PCT")
    if ex2025_mean is not None and ex2025_mean <= 0:
        notes.append("EXCLUDE_2025_NON_POSITIVE")
    if y2025_mean is not None and y2025_mean > mean_bps * 1.75 and mean_bps > 0:
        notes.append("2025_MEAN_DOMINANT")
    if cost15_mean is not None and cost15_mean <= 0:
        notes.append("FAILS_COST_X_1_5")
    if cost20_mean is not None and cost20_mean <= 0:
        notes.append("FAILS_COST_X_2")
    if first_mean is not None and second_mean is not None and (first_mean <= 0 or second_mean <= 0):
        notes.append("CHRONO_HALF_NON_POSITIVE")
    if worst_loo is not None and worst_loo <= 0:
        notes.append("LEAVE_ONE_YEAR_OUT_NON_POSITIVE")

    # Deliberately conservative because Stage38C is still pre-strategy research.
    severe = {
        "EXCLUDE_2025_NON_POSITIVE",
        "CHRONO_HALF_NON_POSITIVE",
        "LEAVE_ONE_YEAR_OUT_NON_POSITIVE",
        "FAILS_COST_X_1_5",
    }
    severe_hits = severe.intersection(notes)

    if mean_bps <= 0 or sample < 100:
        decision = "KILL_DEEP_DIAGNOSTIC"
    elif severe_hits:
        decision = "LOW_CONFIDENCE_RESEARCH_ONLY"
    elif len(notes) <= 2 and mean_bps >= 5.0 and pos_years >= 3 and (ex2025_mean or 0) > 0:
        decision = "PASS_DEEP_DIAGNOSTIC_WATCHLIST"
    else:
        decision = "WATCH_RESEARCH_ONLY"

    return decision, ";".join(notes) if notes else "OK"


def diagnose_candidate(events: Sequence[Dict[str, Any]], multipliers: Sequence[float]) -> Dict[str, Any]:
    base = split_stats(events)
    ex2025_events = [e for e in events if int(e["entry_year"]) != 2025]
    y2025_events = [e for e in events if int(e["entry_year"]) == 2025]
    pre2025_events = [e for e in events if int(e["entry_year"]) < 2025]
    y2026_events = [e for e in events if int(e["entry_year"]) == 2026]

    metrics: Dict[str, Any] = {
        "base": base,
        "pre2025_only": split_stats(pre2025_events),
        "exclude_2025": split_stats(ex2025_events),
        "y2025_only": split_stats(y2025_events),
        "y2026_only": split_stats(y2026_events),
        "chronological_halves": chronological_halves(events),
        "leave_one_year_out": leave_one_year_out(events),
        "cost_sensitivity": cost_sensitivity(events, multipliers),
        "cot_breakdown": cot_breakdown(events),
    }
    decision, note = make_decision(metrics)
    metrics["decision"] = decision
    metrics["note"] = note
    return metrics


def create_tables(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        DROP TABLE IF EXISTS stage38c_deep_diag_candidate_summary;
        DROP TABLE IF EXISTS stage38c_deep_diag_split_summary;
        DROP TABLE IF EXISTS stage38c_deep_diag_audit;

        CREATE TABLE stage38c_deep_diag_candidate_summary (
            diag_id INTEGER PRIMARY KEY AUTOINCREMENT,
            baseline_family TEXT NOT NULL,
            baseline_name TEXT NOT NULL,
            horizon_bars INTEGER NOT NULL,
            sample_count INTEGER NOT NULL,
            mean_net_bps REAL,
            median_net_bps REAL,
            win_rate_net REAL,
            t_stat_mean_net_bps REAL,
            total_net_bps REAL,
            max_drawdown_bps REAL,
            positive_year_count INTEGER,
            negative_year_count INTEGER,
            max_positive_year_share REAL,
            max_positive_month_share REAL,
            exclude_2025_sample_count INTEGER,
            exclude_2025_mean_net_bps REAL,
            y2025_sample_count INTEGER,
            y2025_mean_net_bps REAL,
            first_half_mean_net_bps REAL,
            second_half_mean_net_bps REAL,
            cost_x_1_5_mean_net_bps REAL,
            cost_x_2_mean_net_bps REAL,
            worst_loo_mean_net_bps REAL,
            worst_loo_excluded_year INTEGER,
            decision TEXT NOT NULL,
            note TEXT,
            metrics_json TEXT NOT NULL
        );

        CREATE TABLE stage38c_deep_diag_split_summary (
            split_id INTEGER PRIMARY KEY AUTOINCREMENT,
            baseline_family TEXT NOT NULL,
            baseline_name TEXT NOT NULL,
            horizon_bars INTEGER NOT NULL,
            split_type TEXT NOT NULL,
            split_value TEXT NOT NULL,
            sample_count INTEGER NOT NULL,
            mean_net_bps REAL,
            median_net_bps REAL,
            win_rate_net REAL,
            t_stat_mean_net_bps REAL,
            total_net_bps REAL,
            max_drawdown_bps REAL,
            positive_year_count INTEGER,
            negative_year_count INTEGER,
            max_positive_year_share REAL,
            max_positive_month_share REAL,
            note TEXT
        );

        CREATE TABLE stage38c_deep_diag_audit (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_utc TEXT NOT NULL,
            status TEXT NOT NULL,
            decision TEXT NOT NULL,
            candidates_total INTEGER NOT NULL,
            pass_deep_count INTEGER NOT NULL,
            watch_count INTEGER NOT NULL,
            low_confidence_count INTEGER NOT NULL,
            kill_count INTEGER NOT NULL,
            warning_count INTEGER NOT NULL,
            note_count INTEGER NOT NULL,
            metadata_json TEXT NOT NULL
        );
        """
    )


def insert_candidate_summary(con: sqlite3.Connection, key: Tuple[str, str, int], metrics: Dict[str, Any]) -> None:
    family, name, horizon = key
    base = metrics["base"]
    ex = metrics["exclude_2025"]
    y2025 = metrics["y2025_only"]
    chrono = metrics["chronological_halves"]
    cost = metrics["cost_sensitivity"]
    loo = metrics["leave_one_year_out"]

    row = (
        family,
        name,
        horizon,
        base.get("sample_count") or 0,
        base.get("mean_bps"),
        base.get("median_bps"),
        base.get("win_rate"),
        base.get("t_stat"),
        base.get("total_bps"),
        base.get("max_drawdown_bps"),
        base.get("positive_year_count"),
        base.get("negative_year_count"),
        base.get("max_positive_year_share"),
        base.get("max_positive_month_share"),
        ex.get("sample_count") or 0,
        ex.get("mean_bps"),
        y2025.get("sample_count") or 0,
        y2025.get("mean_bps"),
        (chrono.get("first_half") or {}).get("mean_bps"),
        (chrono.get("second_half") or {}).get("mean_bps"),
        (cost.get("cost_x_1.5") or {}).get("mean_bps"),
        (cost.get("cost_x_2") or {}).get("mean_bps"),
        loo.get("worst_loo_mean_net_bps"),
        loo.get("worst_excluded_year"),
        metrics.get("decision"),
        metrics.get("note"),
        json.dumps(metrics, sort_keys=True),
    )
    con.execute(
        """
        INSERT INTO stage38c_deep_diag_candidate_summary (
            baseline_family, baseline_name, horizon_bars, sample_count,
            mean_net_bps, median_net_bps, win_rate_net, t_stat_mean_net_bps,
            total_net_bps, max_drawdown_bps, positive_year_count, negative_year_count,
            max_positive_year_share, max_positive_month_share,
            exclude_2025_sample_count, exclude_2025_mean_net_bps,
            y2025_sample_count, y2025_mean_net_bps,
            first_half_mean_net_bps, second_half_mean_net_bps,
            cost_x_1_5_mean_net_bps, cost_x_2_mean_net_bps,
            worst_loo_mean_net_bps, worst_loo_excluded_year,
            decision, note, metrics_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        row,
    )


def insert_split_rows(con: sqlite3.Connection, key: Tuple[str, str, int], events: Sequence[Dict[str, Any]], metrics: Dict[str, Any]) -> None:
    family, name, horizon = key
    rows: List[Tuple[Any, ...]] = []

    split_event_sets = {
        "era": {
            "pre2025_only": [e for e in events if int(e["entry_year"]) < 2025],
            "y2025_only": [e for e in events if int(e["entry_year"]) == 2025],
            "exclude_2025": [e for e in events if int(e["entry_year"]) != 2025],
            "y2026_only": [e for e in events if int(e["entry_year"]) == 2026],
        },
        "chronology": {
            "first_half": events[: len(events) // 2],
            "second_half": events[len(events) // 2 :],
        },
    }

    # Year and COT state split event sets.
    by_year: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_cot: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_pressure: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for e in events:
        by_year[str(e["entry_year"])].append(e)
        by_cot[str(e.get("cot_state") or "UNKNOWN")].append(e)
        by_pressure[str(e.get("cot_pressure") or "UNKNOWN")].append(e)
    split_event_sets["year"] = dict(sorted(by_year.items()))
    split_event_sets["cot_state"] = dict(sorted(by_cot.items()))
    split_event_sets["cot_pressure"] = dict(sorted(by_pressure.items()))

    for split_type, mapping in split_event_sets.items():
        for split_value, evs in mapping.items():
            st = split_stats(evs)
            n = st.get("sample_count") or 0
            note = None
            if n < 30:
                note = "LOW_SPLIT_SAMPLE_LT_30"
            rows.append(
                (
                    family, name, horizon, split_type, split_value, n,
                    st.get("mean_bps"), st.get("median_bps"), st.get("win_rate"),
                    st.get("t_stat"), st.get("total_bps"), st.get("max_drawdown_bps"),
                    st.get("positive_year_count"), st.get("negative_year_count"),
                    st.get("max_positive_year_share"), st.get("max_positive_month_share"),
                    note,
                )
            )

    con.executemany(
        """
        INSERT INTO stage38c_deep_diag_split_summary (
            baseline_family, baseline_name, horizon_bars,
            split_type, split_value, sample_count,
            mean_net_bps, median_net_bps, win_rate_net, t_stat_mean_net_bps,
            total_net_bps, max_drawdown_bps,
            positive_year_count, negative_year_count,
            max_positive_year_share, max_positive_month_share,
            note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def write_reports(reports_dir: Path, audit: Dict[str, Any], candidate_rows: List[Dict[str, Any]]) -> Tuple[str, str]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "stage38c_deep_diagnostics.json"
    md_path = reports_dir / "stage38c_deep_diagnostics.md"

    payload = {"audit": audit, "candidates": candidate_rows}
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    lines = [
        "# Stage38C Simple Baseline Deep Diagnostics",
        "",
        "Read-only diagnostic. No orders, no paper-live, no EA, no Stage39 promotion.",
        "",
        "## Audit",
        "",
        "```json",
        json.dumps(audit, indent=2, sort_keys=True),
        "```",
        "",
        "## Candidate Summary",
        "",
        "| decision | baseline | H | n | mean bps | median bps | t | ex-2025 mean | 2025 mean | cost x1.5 mean | worst LOO mean | note |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in candidate_rows:
        lines.append(
            "| {decision} | {baseline} | {h} | {n} | {mean:.2f} | {median:.2f} | {t:.2f} | {ex:.2f} | {y2025:.2f} | {c15:.2f} | {loo:.2f} | {note} |".format(
                decision=r.get("decision"),
                baseline=f"{r.get('baseline_family')}/{r.get('baseline_name')}",
                h=r.get("horizon_bars"),
                n=r.get("sample_count"),
                mean=r.get("mean_net_bps") or 0.0,
                median=r.get("median_net_bps") or 0.0,
                t=r.get("t_stat_mean_net_bps") or 0.0,
                ex=r.get("exclude_2025_mean_net_bps") or 0.0,
                y2025=r.get("y2025_mean_net_bps") or 0.0,
                c15=r.get("cost_x_1_5_mean_net_bps") or 0.0,
                loo=r.get("worst_loo_mean_net_bps") or 0.0,
                note=r.get("note") or "",
            )
        )
    lines.append("")
    lines.append("## Interpretation Rules")
    lines.append("")
    lines.extend([
        "- `PASS_DEEP_DIAGNOSTIC_WATCHLIST` is not a promotion to trading; it only means the candidate deserves a stricter read-only design.",
        "- `LOW_CONFIDENCE_RESEARCH_ONLY` means the candidate remains research-only and must not proceed to Stage39/paper/live.",
        "- 2025 ablation, chronological halves, and cost x1.5 are treated as mandatory sanity checks.",
    ])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(json_path), str(md_path)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Stage38C simple baseline deep diagnostics")
    ap.add_argument("--db", default="data/local/xauusd_local_store.sqlite")
    ap.add_argument("--events-table", default="stage38c_baseline_events")
    ap.add_argument("--summary-table", default="stage38c_baseline_summary")
    ap.add_argument("--reports-dir", default="data/reports/stage38c_deep_diagnostics")
    ap.add_argument("--include-decisions", default=",".join(DEFAULT_INCLUDE_DECISIONS))
    ap.add_argument("--top-watch", type=int, default=4, help="Also include top N WATCH rows by mean_net_bps")
    ap.add_argument("--min-sample", type=int, default=200)
    ap.add_argument("--cost-multipliers", type=parse_float_list, default=DEFAULT_COST_MULTIPLIERS)
    args = ap.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    con = sqlite3.connect(str(db_path))
    con.row_factory = None

    if not table_exists(con, args.events_table):
        raise SystemExit(f"Missing events table: {args.events_table}")
    if not table_exists(con, args.summary_table):
        raise SystemExit(f"Missing summary table: {args.summary_table}")

    include_decisions = parse_csv_list(args.include_decisions)
    candidate_keys = load_candidate_keys(con, args.summary_table, include_decisions, args.top_watch, args.min_sample)
    warnings: List[str] = []
    notes: List[str] = []
    if not candidate_keys:
        warnings.append("NO_CANDIDATES_SELECTED")

    create_tables(con)

    candidate_rows: List[Dict[str, Any]] = []
    decision_counts = defaultdict(int)

    for key in candidate_keys:
        events = load_events_for_key(con, args.events_table, key)
        if not events:
            warnings.append(f"NO_EVENTS_FOR_{key}")
            continue
        metrics = diagnose_candidate(events, args.cost_multipliers)
        insert_candidate_summary(con, key, metrics)
        insert_split_rows(con, key, events, metrics)

        family, name, horizon = key
        base = metrics["base"]
        row = {
            "baseline_family": family,
            "baseline_name": name,
            "horizon_bars": horizon,
            "sample_count": base.get("sample_count"),
            "mean_net_bps": base.get("mean_bps"),
            "median_net_bps": base.get("median_bps"),
            "win_rate_net": base.get("win_rate"),
            "t_stat_mean_net_bps": base.get("t_stat"),
            "max_drawdown_bps": base.get("max_drawdown_bps"),
            "positive_year_count": base.get("positive_year_count"),
            "negative_year_count": base.get("negative_year_count"),
            "max_positive_year_share": base.get("max_positive_year_share"),
            "max_positive_month_share": base.get("max_positive_month_share"),
            "exclude_2025_mean_net_bps": metrics["exclude_2025"].get("mean_bps"),
            "y2025_mean_net_bps": metrics["y2025_only"].get("mean_bps"),
            "cost_x_1_5_mean_net_bps": (metrics["cost_sensitivity"].get("cost_x_1.5") or {}).get("mean_bps"),
            "cost_x_2_mean_net_bps": (metrics["cost_sensitivity"].get("cost_x_2") or {}).get("mean_bps"),
            "worst_loo_mean_net_bps": metrics["leave_one_year_out"].get("worst_loo_mean_net_bps"),
            "worst_loo_excluded_year": metrics["leave_one_year_out"].get("worst_excluded_year"),
            "decision": metrics.get("decision"),
            "note": metrics.get("note"),
        }
        candidate_rows.append(row)
        decision_counts[row["decision"]] += 1

    pass_count = decision_counts.get("PASS_DEEP_DIAGNOSTIC_WATCHLIST", 0)
    watch_count = decision_counts.get("WATCH_RESEARCH_ONLY", 0)
    low_count = decision_counts.get("LOW_CONFIDENCE_RESEARCH_ONLY", 0)
    kill_count = decision_counts.get("KILL_DEEP_DIAGNOSTIC", 0)

    if pass_count > 0:
        decision = "PROCEED_TO_CANDIDATE_SPEC_REVIEW_READ_ONLY"
    elif watch_count > 0 or low_count > 0:
        decision = "REVIEW_ONLY_NO_PROMOTION"
    else:
        decision = "NO_BASELINE_SURVIVED_DEEP_DIAGNOSTIC"

    audit = {
        "status": "PASS" if not warnings else "PASS_WITH_WARNINGS",
        "decision": decision,
        "candidates_total": len(candidate_rows),
        "pass_deep_count": pass_count,
        "watch_count": watch_count,
        "low_confidence_count": low_count,
        "kill_count": kill_count,
        "warning_count": len(warnings),
        "note_count": len(notes) + sum(1 for r in candidate_rows if r.get("note") and r.get("note") != "OK"),
        "warnings": warnings,
        "notes": notes,
        "events_table": args.events_table,
        "summary_table": args.summary_table,
        "include_decisions": include_decisions,
        "top_watch": args.top_watch,
        "min_sample": args.min_sample,
        "cost_multipliers": args.cost_multipliers,
        "created_utc": utc_now(),
    }

    json_report, md_report = write_reports(Path(args.reports_dir), audit, candidate_rows)
    audit["json_report"] = json_report
    audit["md_report"] = md_report

    con.execute(
        """
        INSERT INTO stage38c_deep_diag_audit (
            created_utc, status, decision, candidates_total,
            pass_deep_count, watch_count, low_confidence_count, kill_count,
            warning_count, note_count, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            audit["created_utc"], audit["status"], audit["decision"], audit["candidates_total"],
            pass_count, watch_count, low_count, kill_count,
            audit["warning_count"], audit["note_count"], json.dumps(audit, sort_keys=True),
        ),
    )
    con.commit()

    print(json.dumps({
        "status": audit["status"],
        "decision": audit["decision"],
        "candidates_total": audit["candidates_total"],
        "pass_deep_count": pass_count,
        "watch_count": watch_count,
        "low_confidence_count": low_count,
        "kill_count": kill_count,
        "warning_count": audit["warning_count"],
        "note_count": audit["note_count"],
        "json_report": json_report,
        "md_report": md_report,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
