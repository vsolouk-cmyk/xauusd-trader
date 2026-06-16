#!/usr/bin/env python3
"""
Stage38C — Candidate Specification Review for XAUUSD simple baselines.

Read-only research only.
No orders, no EA, no paper-live, no Stage39 promotion.

Inputs expected from prior Stage38C steps:
- stage38c_baseline_events
- stage38c_deep_diag_candidate_summary

Outputs:
- stage38c_candidate_spec_events
- stage38c_candidate_spec_summary
- stage38c_candidate_spec_audit
- JSON/MD report

Purpose:
- Lock candidate identifiers after deep diagnostics.
- Preserve only restricted read-only candidates.
- Prevent weak baselines from silently becoming strategy/backtest candidates.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median, pstdev
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class CandidateSpec:
    candidate_id: str
    role: str
    baseline_family: str
    baseline_name: str
    horizon_bars: int


DEFAULT_CANDIDATES = [
    CandidateSpec(
        candidate_id="C1_ASIA_RANGE_BREAKOUT_24H",
        role="LEAD_RESTRICTED_RESEARCH_CANDIDATE",
        baseline_family="ASIA_RANGE",
        baseline_name="ASIA_RANGE_BREAKOUT",
        horizon_bars=24,
    ),
    CandidateSpec(
        candidate_id="C2_ATR_EXP_CONT_T1P5_24H",
        role="SECONDARY_DIAGNOSTIC_COMPARATOR",
        baseline_family="ATR_EXPANSION",
        baseline_name="ATR_EXP_CONT_T1P5",
        horizon_bars=24,
    ),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def qident(name: str) -> str:
    if not name or any(ch in name for ch in '"\x00'):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return '"' + name.replace('"', '""') + '"'


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone() is not None


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


def max_drawdown(values: Sequence[float]) -> float:
    peak = 0.0
    equity = 0.0
    max_dd = 0.0
    for v in values:
        equity += float(v)
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return max_dd


def positive_contribution_share(group_sums: Dict[Any, float]) -> Optional[float]:
    positives = [v for v in group_sums.values() if v > 0]
    if not positives:
        return None
    total = sum(positives)
    if total <= 0:
        return None
    return max(positives) / total


def parse_signal_detail(detail: Optional[str]) -> Dict[str, Optional[float]]:
    out: Dict[str, Optional[float]] = {
        "asia_high": None,
        "asia_low": None,
        "breakout_close": None,
        "asia_range_price": None,
        "asia_range_bps": None,
    }
    if not detail:
        return out
    for key, out_key in [
        ("asia_high", "asia_high"),
        ("asia_low", "asia_low"),
        ("close", "breakout_close"),
    ]:
        m = re.search(rf"(?:^|;){re.escape(key)}=([-+]?\d+(?:\.\d+)?)", detail)
        if m:
            out[out_key] = safe_float(m.group(1))
    if out["asia_high"] is not None and out["asia_low"] is not None:
        rng = float(out["asia_high"]) - float(out["asia_low"])
        out["asia_range_price"] = rng
        close = out["breakout_close"]
        if close and close > 0:
            out["asia_range_bps"] = rng / close * 10000.0
    return out


def load_events(con: sqlite3.Connection, events_table: str, spec: CandidateSpec) -> List[Dict[str, Any]]:
    if not table_exists(con, events_table):
        raise RuntimeError(f"Missing events table: {events_table}")

    rows = con.execute(
        f"""
        SELECT event_id, baseline_family, baseline_name, horizon_bars,
               entry_ts_utc, exit_ts_utc, entry_date_utc, entry_year, entry_month,
               entry_hour_utc, direction, entry_price, exit_price,
               gross_price, net_price, gross_bps, cost_bps, net_bps,
               signal_detail, cot_state, cot_pressure, cot_crowding_score
        FROM {qident(events_table)}
        WHERE baseline_family = ? AND baseline_name = ? AND horizon_bars = ?
        ORDER BY entry_ts_utc, event_id
        """,
        (spec.baseline_family, spec.baseline_name, spec.horizon_bars),
    ).fetchall()

    cols = [
        "source_event_id", "baseline_family", "baseline_name", "horizon_bars",
        "entry_ts_utc", "exit_ts_utc", "entry_date_utc", "entry_year", "entry_month",
        "entry_hour_utc", "direction", "entry_price", "exit_price",
        "gross_price", "net_price", "gross_bps", "cost_bps", "net_bps",
        "signal_detail", "cot_state", "cot_pressure", "cot_crowding_score",
    ]
    out: List[Dict[str, Any]] = []
    for row in rows:
        d = dict(zip(cols, row))
        for key in ["entry_price", "exit_price", "gross_price", "net_price", "gross_bps", "cost_bps", "net_bps", "cot_crowding_score"]:
            d[key] = safe_float(d.get(key))
        d["entry_year"] = int(d["entry_year"])
        d["horizon_bars"] = int(d["horizon_bars"])
        d["entry_hour_utc"] = int(d["entry_hour_utc"])
        d["direction"] = int(d["direction"])
        d.update(parse_signal_detail(d.get("signal_detail")))
        out.append(d)
    return out


def basic_stats(events: Sequence[Dict[str, Any]], value_key: str = "net_bps") -> Dict[str, Any]:
    vals = [float(e[value_key]) for e in events if e.get(value_key) is not None]
    years: Dict[int, float] = defaultdict(float)
    months: Dict[str, float] = defaultdict(float)
    directions: Dict[int, List[float]] = defaultdict(list)
    cot_states: Dict[str, List[float]] = defaultdict(list)

    for e in events:
        v = e.get(value_key)
        if v is None:
            continue
        vf = float(v)
        years[int(e["entry_year"])] += vf
        months[str(e["entry_month"])] += vf
        directions[int(e["direction"])].append(vf)
        cot_states[str(e.get("cot_state") or "UNKNOWN")].append(vf)

    direction_stats = {
        ("LONG" if k > 0 else "SHORT" if k < 0 else "FLAT"): {
            "sample_count": len(vs),
            "mean_net_bps": mean(vs),
            "median_net_bps": median(vs) if vs else None,
            "win_rate_net": win_rate(vs),
            "total_net_bps": sum(vs) if vs else None,
        }
        for k, vs in sorted(directions.items())
    }
    cot_state_stats = {
        k: {
            "sample_count": len(vs),
            "mean_net_bps": mean(vs),
            "median_net_bps": median(vs) if vs else None,
            "win_rate_net": win_rate(vs),
            "total_net_bps": sum(vs) if vs else None,
        }
        for k, vs in sorted(cot_states.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    }

    return {
        "sample_count": len(vals),
        "mean_net_bps": mean(vals),
        "median_net_bps": median(vals) if vals else None,
        "win_rate_net": win_rate(vals),
        "t_stat_mean_net_bps": t_stat(vals),
        "total_net_bps": sum(vals) if vals else None,
        "max_drawdown_bps": max_drawdown(vals),
        "positive_year_count": sum(1 for v in years.values() if v > 0),
        "negative_year_count": sum(1 for v in years.values() if v < 0),
        "max_positive_year_share": positive_contribution_share(years),
        "max_positive_month_share": positive_contribution_share(months),
        "year_net_bps": {str(k): round(v, 6) for k, v in sorted(years.items())},
        "month_net_bps": {str(k): round(v, 6) for k, v in sorted(months.items())},
        "direction_stats": direction_stats,
        "cot_state_stats": cot_state_stats,
    }


def cost_stats(events: Sequence[Dict[str, Any]], multiplier: float) -> Dict[str, Any]:
    vals: List[float] = []
    for e in events:
        gross = e.get("gross_bps")
        cost = e.get("cost_bps")
        if gross is None or cost is None:
            continue
        vals.append(float(gross) - float(cost) * multiplier)
    return {
        "mean_net_bps": mean(vals),
        "median_net_bps": median(vals) if vals else None,
        "win_rate_net": win_rate(vals),
        "t_stat_mean_net_bps": t_stat(vals),
        "max_drawdown_bps": max_drawdown(vals),
    }


def chronological_halves(events: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if not events:
        return {"first_half": {}, "second_half": {}}
    mid = len(events) // 2
    return {
        "first_half": basic_stats(events[:mid]),
        "second_half": basic_stats(events[mid:]),
    }


def leave_one_year_out(events: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    years = sorted({int(e["entry_year"]) for e in events})
    rows = []
    worst_year = None
    worst_mean = None
    for y in years:
        subset = [e for e in events if int(e["entry_year"]) != y]
        stats = basic_stats(subset)
        m = stats.get("mean_net_bps")
        rows.append({"excluded_year": y, "sample_count": len(subset), "mean_net_bps": m})
        if m is not None and (worst_mean is None or m < worst_mean):
            worst_mean = m
            worst_year = y
    return {"rows": rows, "worst_excluded_year": worst_year, "worst_loo_mean_net_bps": worst_mean}


def range_bucket_stats(events: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    vals = [e.get("asia_range_bps") for e in events if e.get("asia_range_bps") is not None]
    if len(vals) < 20:
        return {}
    sorted_vals = sorted(float(v) for v in vals)
    q1 = sorted_vals[int(0.33 * (len(sorted_vals) - 1))]
    q2 = sorted_vals[int(0.66 * (len(sorted_vals) - 1))]

    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for e in events:
        v = e.get("asia_range_bps")
        if v is None:
            buckets["UNKNOWN"].append(e)
        elif float(v) <= q1:
            buckets["ASIA_RANGE_LOW"] .append(e)
        elif float(v) <= q2:
            buckets["ASIA_RANGE_NORMAL"].append(e)
        else:
            buckets["ASIA_RANGE_WIDE"].append(e)
    return {
        "q33_asia_range_bps": q1,
        "q66_asia_range_bps": q2,
        "bucket_stats": {k: basic_stats(vs) for k, vs in sorted(buckets.items())},
    }


def build_metrics(events: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    full = basic_stats(events)
    pre2025 = basic_stats([e for e in events if int(e["entry_year"]) < 2025])
    exclude2025 = basic_stats([e for e in events if int(e["entry_year"]) != 2025])
    y2025 = basic_stats([e for e in events if int(e["entry_year"]) == 2025])
    y2026 = basic_stats([e for e in events if int(e["entry_year"]) == 2026])
    return {
        "full": full,
        "pre2025": pre2025,
        "exclude2025": exclude2025,
        "y2025": y2025,
        "y2026": y2026,
        "cost_x_1_5": cost_stats(events, 1.5),
        "cost_x_2": cost_stats(events, 2.0),
        "chronological_halves": chronological_halves(events),
        "leave_one_year_out": leave_one_year_out(events),
        "asia_range_buckets": range_bucket_stats(events),
    }


def decide(spec: CandidateSpec, metrics: Dict[str, Any]) -> Tuple[str, str]:
    full = metrics["full"]
    pre2025 = metrics["pre2025"]
    exclude2025 = metrics["exclude2025"]
    y2025 = metrics["y2025"]
    y2026 = metrics["y2026"]
    cost15 = metrics["cost_x_1_5"]
    cost20 = metrics["cost_x_2"]
    halves = metrics["chronological_halves"]
    loo = metrics["leave_one_year_out"]

    notes: List[str] = []
    n = full.get("sample_count") or 0
    mean_full = full.get("mean_net_bps") or 0.0
    median_full = full.get("median_net_bps") or 0.0
    t = full.get("t_stat_mean_net_bps") or 0.0
    pre_mean = pre2025.get("mean_net_bps")
    ex_mean = exclude2025.get("mean_net_bps")
    y25_mean = y2025.get("mean_net_bps")
    y26_mean = y2026.get("mean_net_bps")
    cost15_mean = cost15.get("mean_net_bps")
    cost20_mean = cost20.get("mean_net_bps")
    first_mean = (halves.get("first_half") or {}).get("mean_net_bps")
    second_mean = (halves.get("second_half") or {}).get("mean_net_bps")
    worst_loo = loo.get("worst_loo_mean_net_bps")

    if n < 500:
        notes.append("LOW_SAMPLE_LT_500")
    if mean_full < 5.0:
        notes.append("LOW_MEAN_LT_5BPS")
    if median_full <= 0:
        notes.append("NON_POSITIVE_MEDIAN")
    if t < 1.5:
        notes.append("WEAK_T_STAT_LT_1_5")
    if pre_mean is not None and pre_mean < 3.0:
        notes.append("WEAK_PRE2025_MEAN_LT_3BPS")
    if ex_mean is not None and ex_mean <= 0:
        notes.append("EXCLUDE_2025_NON_POSITIVE")
    if y25_mean is not None and y25_mean > mean_full * 1.75 and mean_full > 0:
        notes.append("2025_MEAN_DOMINANT")
    if y26_mean is not None and y26_mean > mean_full * 2.5 and mean_full > 0:
        notes.append("2026_MEAN_DOMINANT")
    if cost15_mean is not None and cost15_mean <= 0:
        notes.append("FAILS_COST_X_1_5")
    if cost20_mean is not None and cost20_mean <= 0:
        notes.append("FAILS_COST_X_2")
    if first_mean is not None and first_mean < 3.0:
        notes.append("WEAK_FIRST_HALF_LT_3BPS")
    if second_mean is not None and second_mean <= 0:
        notes.append("SECOND_HALF_NON_POSITIVE")
    if worst_loo is not None and worst_loo <= 0:
        notes.append("LEAVE_ONE_YEAR_OUT_NON_POSITIVE")

    severe = {
        "EXCLUDE_2025_NON_POSITIVE",
        "FAILS_COST_X_1_5",
        "LEAVE_ONE_YEAR_OUT_NON_POSITIVE",
        "SECOND_HALF_NON_POSITIVE",
    }

    if mean_full <= 0 or severe.intersection(notes):
        decision = "KILL_CANDIDATE_SPEC"
    elif spec.candidate_id.startswith("C1_") and mean_full >= 5 and (ex_mean or 0) > 0 and (cost20_mean or 0) > 0:
        decision = "RESTRICTED_RESEARCH_CANDIDATE_SPEC"
    elif spec.candidate_id.startswith("C2_"):
        decision = "SECONDARY_LOW_CONFIDENCE_COMPARATOR_ONLY"
    else:
        decision = "WATCH_RESEARCH_ONLY"

    return decision, ";".join(notes) if notes else "OK"


def create_tables(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        DROP TABLE IF EXISTS stage38c_candidate_spec_events;
        DROP TABLE IF EXISTS stage38c_candidate_spec_summary;
        DROP TABLE IF EXISTS stage38c_candidate_spec_audit;

        CREATE TABLE stage38c_candidate_spec_events (
            spec_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id TEXT NOT NULL,
            candidate_role TEXT NOT NULL,
            source_event_id INTEGER NOT NULL,
            baseline_family TEXT NOT NULL,
            baseline_name TEXT NOT NULL,
            horizon_bars INTEGER NOT NULL,
            entry_ts_utc TEXT NOT NULL,
            exit_ts_utc TEXT NOT NULL,
            entry_date_utc TEXT NOT NULL,
            entry_year INTEGER NOT NULL,
            entry_month TEXT NOT NULL,
            entry_hour_utc INTEGER NOT NULL,
            direction INTEGER NOT NULL,
            direction_label TEXT NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL NOT NULL,
            gross_bps REAL NOT NULL,
            cost_bps REAL NOT NULL,
            net_bps REAL NOT NULL,
            asia_high REAL,
            asia_low REAL,
            asia_range_price REAL,
            asia_range_bps REAL,
            signal_detail TEXT,
            cot_state TEXT,
            cot_pressure TEXT,
            cot_crowding_score REAL
        );

        CREATE TABLE stage38c_candidate_spec_summary (
            summary_id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id TEXT NOT NULL,
            candidate_role TEXT NOT NULL,
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
            pre2025_mean_net_bps REAL,
            exclude_2025_mean_net_bps REAL,
            y2025_mean_net_bps REAL,
            y2026_mean_net_bps REAL,
            cost_x_1_5_mean_net_bps REAL,
            cost_x_2_mean_net_bps REAL,
            first_half_mean_net_bps REAL,
            second_half_mean_net_bps REAL,
            worst_loo_mean_net_bps REAL,
            worst_loo_excluded_year INTEGER,
            decision TEXT NOT NULL,
            note TEXT,
            metrics_json TEXT NOT NULL
        );

        CREATE TABLE stage38c_candidate_spec_audit (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_utc TEXT NOT NULL,
            status TEXT NOT NULL,
            decision TEXT NOT NULL,
            candidates_total INTEGER NOT NULL,
            events_written INTEGER NOT NULL,
            restricted_candidate_count INTEGER NOT NULL,
            secondary_count INTEGER NOT NULL,
            killed_count INTEGER NOT NULL,
            warning_count INTEGER NOT NULL,
            note_count INTEGER NOT NULL,
            json_report TEXT NOT NULL,
            md_report TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        );
        """
    )


def insert_events(con: sqlite3.Connection, spec: CandidateSpec, events: Sequence[Dict[str, Any]]) -> int:
    rows = []
    for e in events:
        direction = int(e["direction"])
        direction_label = "LONG" if direction > 0 else "SHORT" if direction < 0 else "FLAT"
        rows.append((
            spec.candidate_id,
            spec.role,
            e["source_event_id"],
            e["baseline_family"],
            e["baseline_name"],
            e["horizon_bars"],
            e["entry_ts_utc"],
            e["exit_ts_utc"],
            e["entry_date_utc"],
            e["entry_year"],
            e["entry_month"],
            e["entry_hour_utc"],
            direction,
            direction_label,
            e["entry_price"],
            e["exit_price"],
            e["gross_bps"],
            e["cost_bps"],
            e["net_bps"],
            e.get("asia_high"),
            e.get("asia_low"),
            e.get("asia_range_price"),
            e.get("asia_range_bps"),
            e.get("signal_detail"),
            e.get("cot_state"),
            e.get("cot_pressure"),
            e.get("cot_crowding_score"),
        ))
    con.executemany(
        """
        INSERT INTO stage38c_candidate_spec_events (
            candidate_id, candidate_role, source_event_id,
            baseline_family, baseline_name, horizon_bars,
            entry_ts_utc, exit_ts_utc, entry_date_utc, entry_year, entry_month,
            entry_hour_utc, direction, direction_label, entry_price, exit_price,
            gross_bps, cost_bps, net_bps,
            asia_high, asia_low, asia_range_price, asia_range_bps,
            signal_detail, cot_state, cot_pressure, cot_crowding_score
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        rows,
    )
    return len(rows)


def insert_summary(con: sqlite3.Connection, spec: CandidateSpec, metrics: Dict[str, Any], decision: str, note: str) -> None:
    full = metrics["full"]
    halves = metrics["chronological_halves"]
    loo = metrics["leave_one_year_out"]
    con.execute(
        """
        INSERT INTO stage38c_candidate_spec_summary (
            candidate_id, candidate_role, baseline_family, baseline_name, horizon_bars,
            sample_count, mean_net_bps, median_net_bps, win_rate_net,
            t_stat_mean_net_bps, total_net_bps, max_drawdown_bps,
            positive_year_count, negative_year_count, max_positive_year_share,
            max_positive_month_share, pre2025_mean_net_bps,
            exclude_2025_mean_net_bps, y2025_mean_net_bps, y2026_mean_net_bps,
            cost_x_1_5_mean_net_bps, cost_x_2_mean_net_bps,
            first_half_mean_net_bps, second_half_mean_net_bps,
            worst_loo_mean_net_bps, worst_loo_excluded_year,
            decision, note, metrics_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            spec.candidate_id,
            spec.role,
            spec.baseline_family,
            spec.baseline_name,
            spec.horizon_bars,
            full.get("sample_count") or 0,
            full.get("mean_net_bps"),
            full.get("median_net_bps"),
            full.get("win_rate_net"),
            full.get("t_stat_mean_net_bps"),
            full.get("total_net_bps"),
            full.get("max_drawdown_bps"),
            full.get("positive_year_count"),
            full.get("negative_year_count"),
            full.get("max_positive_year_share"),
            full.get("max_positive_month_share"),
            metrics["pre2025"].get("mean_net_bps"),
            metrics["exclude2025"].get("mean_net_bps"),
            metrics["y2025"].get("mean_net_bps"),
            metrics["y2026"].get("mean_net_bps"),
            metrics["cost_x_1_5"].get("mean_net_bps"),
            metrics["cost_x_2"].get("mean_net_bps"),
            (halves.get("first_half") or {}).get("mean_net_bps"),
            (halves.get("second_half") or {}).get("mean_net_bps"),
            loo.get("worst_loo_mean_net_bps"),
            loo.get("worst_excluded_year"),
            decision,
            note,
            json.dumps(metrics, ensure_ascii=False, sort_keys=True),
        ),
    )


def write_reports(
    reports_dir: Path,
    audit: Dict[str, Any],
    summaries: Sequence[Dict[str, Any]],
) -> Tuple[Path, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "stage38c_candidate_spec_review.json"
    md_path = reports_dir / "stage38c_candidate_spec_review.md"

    payload = {"audit": audit, "summaries": list(summaries)}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    lines: List[str] = []
    lines.append("# Stage38C Candidate Spec Review")
    lines.append("")
    lines.append(f"Generated UTC: `{audit['created_utc']}`")
    lines.append("")
    lines.append("## Audit")
    lines.append("")
    lines.append("```text")
    for k in ["status", "decision", "candidates_total", "events_written", "restricted_candidate_count", "secondary_count", "killed_count", "warning_count", "note_count"]:
        lines.append(f"{k} = {audit.get(k)}")
    lines.append("```")
    lines.append("")
    lines.append("## Candidate summaries")
    lines.append("")
    for s in summaries:
        lines.append(f"### {s['candidate_id']}")
        lines.append("")
        lines.append("```text")
        for k in [
            "candidate_role", "baseline_family", "baseline_name", "horizon_bars",
            "sample_count", "mean_net_bps", "median_net_bps", "win_rate_net",
            "t_stat_mean_net_bps", "pre2025_mean_net_bps", "exclude_2025_mean_net_bps",
            "y2025_mean_net_bps", "y2026_mean_net_bps", "cost_x_2_mean_net_bps",
            "first_half_mean_net_bps", "second_half_mean_net_bps", "worst_loo_mean_net_bps",
            "decision", "note",
        ]:
            lines.append(f"{k} = {s.get(k)}")
        lines.append("```")
        lines.append("")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stage38C candidate spec review")
    p.add_argument("--db", default="data/local/xauusd_local_store.sqlite")
    p.add_argument("--events-table", default="stage38c_baseline_events")
    p.add_argument("--deep-summary-table", default="stage38c_deep_diag_candidate_summary")
    p.add_argument("--reports-dir", default="data/reports/stage38c_candidate_spec_review")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db)
    if not db_path.exists():
        raise RuntimeError(f"DB not found: {db_path}")

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row

    warnings: List[str] = []
    notes: List[str] = []

    if not table_exists(con, args.events_table):
        raise RuntimeError(f"Missing required events table: {args.events_table}")
    if not table_exists(con, args.deep_summary_table):
        notes.append(f"deep_summary_table_missing_or_not_used:{args.deep_summary_table}")

    create_tables(con)

    summaries_for_report: List[Dict[str, Any]] = []
    events_written = 0
    restricted_count = 0
    secondary_count = 0
    killed_count = 0

    for spec in DEFAULT_CANDIDATES:
        events = load_events(con, args.events_table, spec)
        if not events:
            warnings.append(f"missing_events_for:{spec.candidate_id}")
            continue
        events_written += insert_events(con, spec, events)
        metrics = build_metrics(events)
        decision, note = decide(spec, metrics)
        insert_summary(con, spec, metrics, decision, note)

        if decision == "RESTRICTED_RESEARCH_CANDIDATE_SPEC":
            restricted_count += 1
        elif decision == "SECONDARY_LOW_CONFIDENCE_COMPARATOR_ONLY":
            secondary_count += 1
        elif decision == "KILL_CANDIDATE_SPEC":
            killed_count += 1
        else:
            notes.append(f"watch_or_other_decision:{spec.candidate_id}:{decision}")

        row = con.execute(
            """
            SELECT candidate_id, candidate_role, baseline_family, baseline_name, horizon_bars,
                   sample_count, mean_net_bps, median_net_bps, win_rate_net,
                   t_stat_mean_net_bps, pre2025_mean_net_bps, exclude_2025_mean_net_bps,
                   y2025_mean_net_bps, y2026_mean_net_bps, cost_x_2_mean_net_bps,
                   first_half_mean_net_bps, second_half_mean_net_bps,
                   worst_loo_mean_net_bps, decision, note
            FROM stage38c_candidate_spec_summary
            WHERE candidate_id = ?
            """,
            (spec.candidate_id,),
        ).fetchone()
        summaries_for_report.append(dict(row))

    if restricted_count >= 1:
        top_decision = "PROCEED_TO_ASIA_RANGE_TARGETED_FILTER_DIAGNOSTIC_READ_ONLY"
    elif killed_count == len(DEFAULT_CANDIDATES):
        top_decision = "STOP_STAGE38C_NO_CANDIDATE"
    else:
        top_decision = "WATCH_ONLY_NO_PROMOTION"

    status = "PASS" if not warnings and summaries_for_report else "PASS_WITH_WARNINGS" if summaries_for_report else "FAIL"
    created = utc_now()
    audit = {
        "created_utc": created,
        "status": status,
        "decision": top_decision,
        "candidates_total": len(summaries_for_report),
        "events_written": events_written,
        "restricted_candidate_count": restricted_count,
        "secondary_count": secondary_count,
        "killed_count": killed_count,
        "warning_count": len(warnings),
        "note_count": len(notes),
        "warnings": warnings,
        "notes": notes,
        "trading_status": "NO_GO_STAGE39_EA_PAPER_LIVE_LIVE",
    }

    json_path, md_path = write_reports(Path(args.reports_dir), audit, summaries_for_report)
    audit["json_report"] = str(json_path)
    audit["md_report"] = str(md_path)

    con.execute(
        """
        INSERT INTO stage38c_candidate_spec_audit (
            created_utc, status, decision, candidates_total, events_written,
            restricted_candidate_count, secondary_count, killed_count,
            warning_count, note_count, json_report, md_report, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            audit["created_utc"],
            audit["status"],
            audit["decision"],
            audit["candidates_total"],
            audit["events_written"],
            audit["restricted_candidate_count"],
            audit["secondary_count"],
            audit["killed_count"],
            audit["warning_count"],
            audit["note_count"],
            audit["json_report"],
            audit["md_report"],
            json.dumps(audit, ensure_ascii=False, sort_keys=True),
        ),
    )
    con.commit()

    print(json.dumps({
        "status": audit["status"],
        "decision": audit["decision"],
        "candidates_total": audit["candidates_total"],
        "events_written": audit["events_written"],
        "restricted_candidate_count": audit["restricted_candidate_count"],
        "secondary_count": audit["secondary_count"],
        "killed_count": audit["killed_count"],
        "warning_count": audit["warning_count"],
        "note_count": audit["note_count"],
        "json_report": audit["json_report"],
        "md_report": audit["md_report"],
    }, ensure_ascii=False, indent=2))

    return 0 if status in {"PASS", "PASS_WITH_WARNINGS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
