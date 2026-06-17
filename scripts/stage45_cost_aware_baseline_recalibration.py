#!/usr/bin/env python3
"""
Stage45_COST_AWARE_BASELINE_RECALIBRATION_OR_EXTERNAL_CONTEXT_DECISION

This is a decision/recalibration diagnostic, not a trading signal generator.
It reads recent candidate CSV / summary JSON outputs and estimates whether
existing thesis-space failures are primarily cost/slip, stability, event-scarcity,
or missing external-context problems.

It never promotes candidates and never enables EA/paper/live.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


STAGE_DEFAULTS = [
    {
        "stage": "stage41",
        "candidates": "reports/stage41/stage41_parallel_thesis_megascan_v2_candidates.csv",
        "summary": "reports/stage41/stage41_parallel_thesis_megascan_v2_summary.json",
        "residual_cols": ["h1_benchmark_cost_adjusted_residual_bps"],
        "default_cost_gate_bps": 8.0,
        "default_worst_quarter_gate_bps": -10.0,
    },
    {
        "stage": "stage42",
        "candidates": "reports/stage42/stage42_parallel_intraday_execution_megascan_v3_candidates.csv",
        "summary": "reports/stage42/stage42_parallel_intraday_execution_megascan_v3_summary.json",
        "residual_cols": ["intraday_benchmark_cost_adjusted_residual_bps"],
        "default_cost_gate_bps": 15.0,
        "default_worst_quarter_gate_bps": -20.0,
    },
    {
        "stage": "stage43",
        "candidates": "reports/stage43/stage43_parallel_context_regime_megascan_v4_candidates.csv",
        "summary": "reports/stage43/stage43_parallel_context_regime_megascan_v4_summary.json",
        "residual_cols": ["context_benchmark_cost_adjusted_residual_bps"],
        "default_cost_gate_bps": 12.0,
        "default_worst_quarter_gate_bps": -20.0,
    },
]

SCENARIOS = [
    {"name": "observed_costs_current_strict", "cost_saving_bps": 0.0, "cost_gate_bps": 12.0, "residual_gate_bps": 3.0, "train_gate_bps": 0.0, "oos_gate_bps": 0.0, "worst_quarter_gate_bps": -20.0, "boot_p10_gate_bps": -5.0, "min_events": 120.0, "top_year_max_pct": 38.0},
    {"name": "realistic_cost_improvement_plus4", "cost_saving_bps": 4.0, "cost_gate_bps": 12.0, "residual_gate_bps": 3.0, "train_gate_bps": 0.0, "oos_gate_bps": 0.0, "worst_quarter_gate_bps": -20.0, "boot_p10_gate_bps": -5.0, "min_events": 120.0, "top_year_max_pct": 38.0},
    {"name": "aggressive_cost_improvement_plus8", "cost_saving_bps": 8.0, "cost_gate_bps": 12.0, "residual_gate_bps": 3.0, "train_gate_bps": 0.0, "oos_gate_bps": 0.0, "worst_quarter_gate_bps": -20.0, "boot_p10_gate_bps": -5.0, "min_events": 120.0, "top_year_max_pct": 38.0},
    {"name": "very_low_cost_plus16_diagnostic_only", "cost_saving_bps": 16.0, "cost_gate_bps": 12.0, "residual_gate_bps": 3.0, "train_gate_bps": 0.0, "oos_gate_bps": 0.0, "worst_quarter_gate_bps": -20.0, "boot_p10_gate_bps": -5.0, "min_events": 120.0, "top_year_max_pct": 38.0},
    {"name": "minimal_edge_sanity_observed", "cost_saving_bps": 0.0, "cost_gate_bps": 0.0, "residual_gate_bps": 0.0, "train_gate_bps": 0.0, "oos_gate_bps": 0.0, "worst_quarter_gate_bps": -30.0, "boot_p10_gate_bps": -10.0, "min_events": 120.0, "top_year_max_pct": 45.0},
    {"name": "event_scarcity_probe_min40", "cost_saving_bps": 0.0, "cost_gate_bps": 12.0, "residual_gate_bps": 3.0, "train_gate_bps": 0.0, "oos_gate_bps": 0.0, "worst_quarter_gate_bps": -20.0, "boot_p10_gate_bps": -5.0, "min_events": 40.0, "top_year_max_pct": 38.0},
]

NUMERIC_FIELDS = [
    "cost_stressed_mean_bps",
    "train_cost_mean_bps",
    "oos_cost_mean_bps",
    "worst_quarter_slip16_mean_bps",
    "boot_p10_bps",
    "event_clock_n",
    "top_year_event_share_pct",
    "h1_benchmark_cost_adjusted_residual_bps",
    "intraday_benchmark_cost_adjusted_residual_bps",
    "context_benchmark_cost_adjusted_residual_bps",
    "oos_touch_stop_100bps_pct",
    "oos_touch_stop_50bps_pct",
]

PROMOTION_LOCK = {
    "promotion": "NO_GO",
    "EA": "NO_GO",
    "paper_live": "NO_GO",
    "live": "NO_GO",
}


def _safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        if math.isfinite(float(v)):
            return float(v)
        return None
    s = str(v).strip()
    if not s or s.lower() in {"nan", "none", "null", "na", "n/a", ""}:
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    return f if math.isfinite(f) else None


def _q(vals: Sequence[float], p: float) -> Optional[float]:
    xs = sorted(v for v in vals if v is not None and math.isfinite(v))
    if not xs:
        return None
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * p
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    w = pos - lo
    return xs[lo] * (1 - w) + xs[hi] * w


def _numeric_profile(rows: Sequence[Dict[str, Any]], field: str) -> Dict[str, Any]:
    vals = []
    for r in rows:
        f = _safe_float(r.get(field))
        if f is not None:
            vals.append(f)
    if not vals:
        return {"n": 0}
    return {
        "n": len(vals),
        "min": min(vals),
        "p10": _q(vals, 0.10),
        "median": _q(vals, 0.50),
        "p90": _q(vals, 0.90),
        "max": max(vals),
        "mean": mean(vals),
    }


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _read_csv(path: Path, stage_name: str, residual_cols: Sequence[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row = dict(row)
            row["stage"] = stage_name
            # Standardize one residual column for scenario gates.
            residual_value = None
            residual_name = None
            for col in residual_cols:
                residual_value = _safe_float(row.get(col))
                if residual_value is not None:
                    residual_name = col
                    break
            row["stage_residual_bps"] = residual_value
            row["stage_residual_col"] = residual_name
            for field in NUMERIC_FIELDS:
                if field in row:
                    row[field] = _safe_float(row.get(field))
            rows.append(row)
    return rows


def _collect_inputs(root: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    all_rows: List[Dict[str, Any]] = []
    inputs: List[Dict[str, Any]] = []
    missing: List[str] = []
    for item in STAGE_DEFAULTS:
        cpath = root / item["candidates"]
        spath = root / item["summary"]
        record: Dict[str, Any] = {
            "stage": item["stage"],
            "candidates_path": str(cpath),
            "summary_path": str(spath),
            "candidate_csv_exists": cpath.exists(),
            "summary_json_exists": spath.exists(),
        }
        if not cpath.exists():
            missing.append(str(cpath))
        if not spath.exists():
            missing.append(str(spath))
        if cpath.exists():
            rows = _read_csv(cpath, item["stage"], item["residual_cols"])
            record["candidate_rows_csv"] = len(rows)
            all_rows.extend(rows)
        if spath.exists():
            try:
                summary = _read_json(spath)
                record["reported_stage"] = summary.get("stage")
                record["candidate_rows_summary"] = summary.get("candidate_rows")
                record["events_rows_written"] = summary.get("events_rows_written")
                record["strict_watch_count"] = (
                    summary.get("strict_stage41_scan_watch_count")
                    or summary.get("strict_stage42_intraday_scan_watch_count")
                    or summary.get("strict_stage43_context_regime_scan_watch_count")
                    or 0
                )
                record["soft_watch_count"] = (
                    summary.get("soft_stage41_scan_watch_count")
                    or summary.get("soft_stage42_intraday_scan_watch_count")
                    or summary.get("soft_stage43_context_regime_scan_watch_count")
                    or 0
                )
                record["classification_counts"] = summary.get("classification_counts", {})
                for k, v in PROMOTION_LOCK.items():
                    record[k] = summary.get(k, v)
            except Exception as exc:  # keep diagnostic running
                record["summary_read_error"] = repr(exc)
        inputs.append(record)
    return all_rows, inputs, missing


def _split_reasons(value: Any, classification: Any = None) -> List[str]:
    out: List[str] = []
    if classification:
        out.append(str(classification))
    if value:
        for part in str(value).replace(",", ";").split(";"):
            s = part.strip()
            if s:
                out.append(s)
    return out


def _reason_buckets(reason: str) -> List[str]:
    r = reason.lower()
    buckets: List[str] = []
    if "event" in r or "n_too_small" in r or "insufficient" in r:
        buckets.append("event_scarcity")
    if "cost" in r or "mean" in r:
        buckets.append("cost_or_mean_edge")
    if "residual" in r or "benchmark" in r:
        buckets.append("benchmark_residual")
    if "train" in r:
        buckets.append("train_segment")
    if "oos" in r:
        buckets.append("oos_segment")
    if "quarter" in r or "worst_quarter" in r:
        buckets.append("quarter_stability")
    if "boot" in r or "prob" in r:
        buckets.append("bootstrap_stability")
    if "touch" in r or "mae" in r or "stop" in r:
        buckets.append("path_risk")
    if "year" in r or "share" in r or "concentration" in r:
        buckets.append("concentration")
    return buckets or ["other"]


def _scenario_pass(row: Dict[str, Any], scenario: Dict[str, float]) -> Tuple[bool, List[str]]:
    saving = float(scenario["cost_saving_bps"])
    failures: List[str] = []

    event_n = _safe_float(row.get("event_clock_n"))
    cost_mean = _safe_float(row.get("cost_stressed_mean_bps"))
    residual = _safe_float(row.get("stage_residual_bps"))
    train = _safe_float(row.get("train_cost_mean_bps"))
    oos = _safe_float(row.get("oos_cost_mean_bps"))
    worst_q = _safe_float(row.get("worst_quarter_slip16_mean_bps"))
    boot = _safe_float(row.get("boot_p10_bps"))
    top_year = _safe_float(row.get("top_year_event_share_pct"))

    # Treat savings as a sensitivity approximation, not a reconstruction of gross return.
    adj_cost = None if cost_mean is None else cost_mean + saving
    adj_train = None if train is None else train + saving
    adj_oos = None if oos is None else oos + saving
    adj_worst = None if worst_q is None else worst_q + saving
    adj_boot = None if boot is None else boot + saving

    checks = [
        (event_n, ">=", scenario["min_events"], "event_clock_n"),
        (adj_cost, ">", scenario["cost_gate_bps"], "adjusted_cost_mean_bps"),
        (residual, ">", scenario["residual_gate_bps"], "stage_residual_bps"),
        (adj_train, ">", scenario["train_gate_bps"], "adjusted_train_cost_mean_bps"),
        (adj_oos, ">", scenario["oos_gate_bps"], "adjusted_oos_cost_mean_bps"),
        (adj_worst, ">", scenario["worst_quarter_gate_bps"], "adjusted_worst_quarter_slip16_mean_bps"),
        (adj_boot, ">", scenario["boot_p10_gate_bps"], "adjusted_boot_p10_bps"),
    ]
    if top_year is not None:
        checks.append((top_year, "<=", scenario["top_year_max_pct"], "top_year_event_share_pct"))

    for value, op, threshold, name in checks:
        if value is None:
            failures.append(f"{name}_missing")
        elif op == ">" and not (value > threshold):
            failures.append(f"{name}_not_gt_{threshold:g}")
        elif op == ">=" and not (value >= threshold):
            failures.append(f"{name}_not_ge_{threshold:g}")
        elif op == "<=" and not (value <= threshold):
            failures.append(f"{name}_not_le_{threshold:g}")
    return len(failures) == 0, failures


def _scenario_analysis(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for sc in SCENARIOS:
        pass_rows: List[Dict[str, Any]] = []
        blocker_counts: Counter[str] = Counter()
        near_rows: List[Dict[str, Any]] = []
        for row in rows:
            ok, failures = _scenario_pass(row, sc)
            if ok:
                pass_rows.append(row)
            else:
                blocker_counts.update(failures)
                if len(failures) <= 2:
                    near_rows.append({
                        "stage": row.get("stage"),
                        "family": row.get("family"),
                        "candidate": row.get("candidate"),
                        "side": row.get("side"),
                        "event_clock_n": row.get("event_clock_n"),
                        "cost_stressed_mean_bps": row.get("cost_stressed_mean_bps"),
                        "stage_residual_bps": row.get("stage_residual_bps"),
                        "train_cost_mean_bps": row.get("train_cost_mean_bps"),
                        "oos_cost_mean_bps": row.get("oos_cost_mean_bps"),
                        "worst_quarter_slip16_mean_bps": row.get("worst_quarter_slip16_mean_bps"),
                        "boot_p10_bps": row.get("boot_p10_bps"),
                        "remaining_failures": failures,
                    })
        top_pass = sorted(pass_rows, key=lambda r: (_safe_float(r.get("cost_stressed_mean_bps")) or -1e9), reverse=True)[:20]
        results.append({
            "scenario": sc,
            "pass_count": len(pass_rows),
            "pass_by_stage": dict(Counter(str(r.get("stage")) for r in pass_rows)),
            "dominant_blockers": [{"key": k, "n": v} for k, v in blocker_counts.most_common(20)],
            "near_miss_count_failures_le_2": len(near_rows),
            "near_misses_top20": sorted(near_rows, key=lambda r: (_safe_float(r.get("cost_stressed_mean_bps")) or -1e9), reverse=True)[:20],
            "top_pass_rows": [
                {
                    "stage": r.get("stage"),
                    "family": r.get("family"),
                    "candidate": r.get("candidate"),
                    "side": r.get("side"),
                    "event_clock_n": r.get("event_clock_n"),
                    "cost_stressed_mean_bps": r.get("cost_stressed_mean_bps"),
                    "stage_residual_bps": r.get("stage_residual_bps"),
                    "train_cost_mean_bps": r.get("train_cost_mean_bps"),
                    "oos_cost_mean_bps": r.get("oos_cost_mean_bps"),
                    "worst_quarter_slip16_mean_bps": r.get("worst_quarter_slip16_mean_bps"),
                    "boot_p10_bps": r.get("boot_p10_bps"),
                    "failed_reasons": r.get("failed_reasons"),
                }
                for r in top_pass
            ],
        })
    return results


def _cost_needed_profile(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Estimate one-dimensional cost/slip savings needed to satisfy all numeric gates.

    This is intentionally conservative and diagnostic only. It is not an attempt to
    reconstruct gross returns. It asks: if every net path metric improved by X bps,
    what X would be needed for a row to pass robust gates, while keeping residual,
    event count, and concentration fixed?
    """
    needed: List[float] = []
    eligible_rows = 0
    rows_out: List[Dict[str, Any]] = []
    for r in rows:
        event_n = _safe_float(r.get("event_clock_n"))
        residual = _safe_float(r.get("stage_residual_bps"))
        top_year = _safe_float(r.get("top_year_event_share_pct"))
        if event_n is None or event_n < 120:
            continue
        if residual is None or residual <= 3:
            continue
        if top_year is not None and top_year > 38:
            continue
        vals = {
            "cost": _safe_float(r.get("cost_stressed_mean_bps")),
            "train": _safe_float(r.get("train_cost_mean_bps")),
            "oos": _safe_float(r.get("oos_cost_mean_bps")),
            "worst_q": _safe_float(r.get("worst_quarter_slip16_mean_bps")),
            "boot": _safe_float(r.get("boot_p10_bps")),
        }
        if any(v is None for v in vals.values()):
            continue
        required = max(
            0.0,
            12.0 - vals["cost"],
            0.0 - vals["train"],
            0.0 - vals["oos"],
            -20.0 - vals["worst_q"],
            -5.0 - vals["boot"],
        )
        eligible_rows += 1
        needed.append(required)
        rows_out.append({
            "stage": r.get("stage"),
            "family": r.get("family"),
            "candidate": r.get("candidate"),
            "side": r.get("side"),
            "event_clock_n": event_n,
            "stage_residual_bps": residual,
            "cost_stressed_mean_bps": vals["cost"],
            "train_cost_mean_bps": vals["train"],
            "oos_cost_mean_bps": vals["oos"],
            "worst_quarter_slip16_mean_bps": vals["worst_q"],
            "boot_p10_bps": vals["boot"],
            "required_uniform_bps_improvement_to_pass_numeric_gates": required,
        })
    return {
        "eligible_rows_with_event_residual_concentration": eligible_rows,
        "required_uniform_bps_improvement_profile": _numeric_profile([{ "x": x } for x in needed], "x") if needed else {"n": 0},
        "best_rows_by_required_improvement": sorted(rows_out, key=lambda x: x["required_uniform_bps_improvement_to_pass_numeric_gates"])[:25],
    }


def _decision_logic(rows: Sequence[Dict[str, Any]], scenario_results: Sequence[Dict[str, Any]], cost_needed: Dict[str, Any]) -> Dict[str, Any]:
    current_strict = next((x for x in scenario_results if x["scenario"]["name"] == "observed_costs_current_strict"), None)
    realistic_plus4 = next((x for x in scenario_results if x["scenario"]["name"] == "realistic_cost_improvement_plus4"), None)
    aggressive_plus8 = next((x for x in scenario_results if x["scenario"]["name"] == "aggressive_cost_improvement_plus8"), None)
    lowcost_plus16 = next((x for x in scenario_results if x["scenario"]["name"] == "very_low_cost_plus16_diagnostic_only"), None)
    minimal = next((x for x in scenario_results if x["scenario"]["name"] == "minimal_edge_sanity_observed"), None)
    event_probe = next((x for x in scenario_results if x["scenario"]["name"] == "event_scarcity_probe_min40"), None)

    p90_cost = _numeric_profile(rows, "cost_stressed_mean_bps").get("p90")
    median_cost = _numeric_profile(rows, "cost_stressed_mean_bps").get("median")
    worst_q_median = _numeric_profile(rows, "worst_quarter_slip16_mean_bps").get("median")
    boot_median = _numeric_profile(rows, "boot_p10_bps").get("median")

    decision = {
        "archive_stage44_meta_diagnostic": True,
        "do_not_build_stage41b_42b_43b": True,
        "do_not_promote_any_recent_candidate": True,
        "EA": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "recommended_next_stage": None,
        "rationale": [],
        "allowed_next_options": [],
        "not_allowed": [
            "post_hoc_removal_of_weak_hours_months_years_quarters_contexts",
            "candidate_rescue_from_stage41_42_43",
            "EA_paper_live_live_from_archived_rows",
            "ML_before_robust_cost_aware_baseline",
        ],
    }

    if current_strict and current_strict["pass_count"] > 0:
        decision["recommended_next_stage"] = "Stage45B_COST_ASSUMPTION_AUDIT_OF_NEAR_PASS_ROWS"
        decision["rationale"].append("Observed-cost strict recalibration found pass rows, but this is diagnostic only; require independent audit.")
    elif aggressive_plus8 and aggressive_plus8["pass_count"] > 0:
        decision["recommended_next_stage"] = "Stage45C_FEED_AND_TRANSACTION_COST_REALISM_AUDIT"
        decision["rationale"].append("Only aggressive cost improvement creates pass rows; verify broker feed, spread, and slippage realism before more thesis scans.")
    elif lowcost_plus16 and lowcost_plus16["pass_count"] > 0:
        decision["recommended_next_stage"] = "Stage45C_FEED_AND_TRANSACTION_COST_REALISM_AUDIT"
        decision["rationale"].append("Only very-low-cost diagnostic assumptions create pass rows; current broker-cost environment likely overwhelms these edges.")
    elif event_probe and event_probe["pass_count"] > 0:
        decision["recommended_next_stage"] = "Stage45D_RARE_EVENT_SAMPLE_SIZE_DECISION"
        decision["rationale"].append("Lowering min_events reveals rare-event candidates, but promotion is forbidden; decide whether more history/external data is needed.")
    else:
        decision["recommended_next_stage"] = "Stage45B_EXTERNAL_CONTEXT_AND_REFERENCE_FEED_DECISION"
        decision["rationale"].append("No observed-cost or realistic cost-improvement scenario creates robust pass rows; more blind candle-only thesis scans are low value.")

    if minimal and minimal["pass_count"] == 0:
        decision["rationale"].append("Even minimal-edge sanity gates find no robust observed-cost rows.")
    if p90_cost is not None and p90_cost < 12:
        decision["rationale"].append(f"Cost-stressed p90 is only {p90_cost:.2f} bps, below a practical robust edge gate.")
    if median_cost is not None and median_cost < 0:
        decision["rationale"].append(f"Median cost-stressed mean is negative ({median_cost:.2f} bps).")
    if worst_q_median is not None and worst_q_median < -40:
        decision["rationale"].append(f"Worst-quarter median is deeply negative ({worst_q_median:.2f} bps), showing path fragility.")
    if boot_median is not None and boot_median < -5:
        decision["rationale"].append(f"Bootstrap p10 median is below gate ({boot_median:.2f} bps).")

    decision["allowed_next_options"] = [
        "Stage45B external-context decision: DXY/yields/news calendar/CME GC reference before new candle-only scans",
        "Stage45C broker/feed/spread/slippage realism audit using MT5 spread column and optional futures/reference feed",
        "Stage45D rare-event sample-size decision only if event-scarcity scenarios show economically meaningful rows",
        "Stage46 new scan only after Stage45 selects an evidence-based direction",
    ]
    return decision


def _top_rows(rows: Sequence[Dict[str, Any]], field: str, reverse: bool = True, n: int = 25) -> List[Dict[str, Any]]:
    valid = [r for r in rows if _safe_float(r.get(field)) is not None]
    valid.sort(key=lambda r: _safe_float(r.get(field)) or 0.0, reverse=reverse)
    keep = []
    cols = [
        "stage", "classification", "family", "candidate", "side", "event_clock_n", "horizon_h", "horizon_minutes",
        field, "cost_stressed_mean_bps", "stage_residual_bps", "train_cost_mean_bps", "oos_cost_mean_bps",
        "worst_quarter_slip16_mean_bps", "boot_p10_bps", "top_year_event_share_pct", "failed_reasons",
    ]
    for r in valid[:n]:
        keep.append({c: r.get(c) for c in cols if c in r})
    return keep


def _write_csv_long_reasons(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["stage", "family", "candidate", "side", "classification", "reason", "bucket", "event_clock_n", "cost_stressed_mean_bps", "stage_residual_bps"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            reasons = _split_reasons(r.get("failed_reasons"), r.get("classification"))
            for reason in reasons:
                for bucket in _reason_buckets(reason):
                    w.writerow({
                        "stage": r.get("stage"),
                        "family": r.get("family"),
                        "candidate": r.get("candidate"),
                        "side": r.get("side"),
                        "classification": r.get("classification"),
                        "reason": reason,
                        "bucket": bucket,
                        "event_clock_n": r.get("event_clock_n"),
                        "cost_stressed_mean_bps": r.get("cost_stressed_mean_bps"),
                        "stage_residual_bps": r.get("stage_residual_bps"),
                    })


def _md_table(rows: Sequence[Dict[str, Any]], columns: Sequence[str], max_rows: int = 20) -> str:
    if not rows:
        return "\n_None._\n"
    out = []
    out.append("| " + " | ".join(columns) + " |")
    out.append("| " + " | ".join([":--" for _ in columns]) + " |")
    for r in rows[:max_rows]:
        vals = []
        for c in columns:
            v = r.get(c, "")
            if isinstance(v, float):
                vals.append(f"{v:.3f}")
            else:
                s = str(v) if v is not None else ""
                if len(s) > 140:
                    s = s[:137] + "..."
                vals.append(s.replace("|", "/"))
        out.append("| " + " | ".join(vals) + " |")
    return "\n".join(out) + "\n"


def _write_markdown(path: Path, summary: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    diag = summary["diagnostic"]
    decision = summary["decision"]
    lines: List[str] = []
    lines.append("# Stage45_COST_AWARE_BASELINE_RECALIBRATION_OR_EXTERNAL_CONTEXT_DECISION")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    lines.append("promotion = NO_GO")
    lines.append("EA = NO_GO")
    lines.append("paper_live = NO_GO")
    lines.append("live = NO_GO")
    lines.append(f"recommended_next_stage = {decision.get('recommended_next_stage')}")
    lines.append("```")
    lines.append("")
    lines.append("Stage45 is a diagnostic and decision step. It does not create trading signals, does not promote any candidate, and does not authorize operational layers.")
    lines.append("")
    lines.append("## Inputs")
    lines.append("")
    lines.append(_md_table(summary.get("inputs", []), ["stage", "candidate_rows_csv", "events_rows_written", "strict_watch_count", "soft_watch_count", "promotion"], 10))
    lines.append("")
    lines.append("## Aggregate profile")
    lines.append("")
    lines.append("```text")
    lines.append(f"total_candidates_analyzed = {diag.get('total_candidates_analyzed')}")
    lines.append(f"total_strict_watch_count = {diag.get('total_strict_watch_count')}")
    lines.append(f"total_soft_watch_count = {diag.get('total_soft_watch_count')}")
    lines.append("```")
    lines.append("")
    lines.append("## Numeric profile")
    lines.append("")
    numeric_rows = []
    for metric, prof in diag.get("numeric_profile", {}).items():
        row = {"metric": metric}
        row.update(prof)
        numeric_rows.append(row)
    lines.append(_md_table(numeric_rows, ["metric", "n", "min", "p10", "median", "p90", "max", "mean"], 50))
    lines.append("")
    lines.append("## Cost/slip sensitivity scenarios")
    lines.append("")
    scenario_rows = []
    for item in diag.get("scenario_analysis", []):
        sc = item["scenario"]
        scenario_rows.append({
            "scenario": sc["name"],
            "cost_saving_bps": sc["cost_saving_bps"],
            "pass_count": item["pass_count"],
            "near_miss_count_failures_le_2": item["near_miss_count_failures_le_2"],
            "pass_by_stage": item["pass_by_stage"],
        })
    lines.append(_md_table(scenario_rows, ["scenario", "cost_saving_bps", "pass_count", "near_miss_count_failures_le_2", "pass_by_stage"], 20))
    lines.append("")
    lines.append("## Cost improvement needed")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(diag.get("cost_needed_profile", {}), ensure_ascii=False, indent=2)[:4000])
    lines.append("```")
    lines.append("")
    lines.append("## Dominant reasons")
    lines.append("")
    lines.append(_md_table(diag.get("failed_reason_counts", []), ["key", "n"], 30))
    lines.append("")
    lines.append("## Best rows by observed cost-stressed mean")
    lines.append("")
    lines.append(_md_table(diag.get("top_by_cost_mean", []), ["stage", "family", "candidate", "side", "event_clock_n", "cost_stressed_mean_bps", "stage_residual_bps", "train_cost_mean_bps", "oos_cost_mean_bps", "worst_quarter_slip16_mean_bps", "boot_p10_bps", "failed_reasons"], 25))
    lines.append("")
    lines.append("## Recommendation")
    lines.append("")
    lines.append("```text")
    lines.append(f"archive_stage44_meta_diagnostic = {decision.get('archive_stage44_meta_diagnostic')}")
    lines.append(f"do_not_build_stage41b_42b_43b = {decision.get('do_not_build_stage41b_42b_43b')}")
    lines.append(f"do_not_promote_any_recent_candidate = {decision.get('do_not_promote_any_recent_candidate')}")
    lines.append(f"next_stage = {decision.get('recommended_next_stage')}")
    lines.append("```")
    lines.append("")
    lines.append("### Rationale")
    lines.append("")
    for item in decision.get("rationale", []):
        lines.append(f"- {item}")
    lines.append("")
    lines.append("### Allowed next options")
    lines.append("")
    for item in decision.get("allowed_next_options", []):
        lines.append(f"- `{item}`")
    lines.append("")
    lines.append("### Not allowed")
    lines.append("")
    for item in decision.get("not_allowed", []):
        lines.append(f"- `{item}`")
    lines.append("")
    lines.append("## Anti-overfit note")
    lines.append("")
    lines.append("Do not use this diagnostic to rescue Stage41/42/43 rows by post-hoc filtering. Stage45 can only select a direction: external context, feed/cost realism, rare-event sample-size, or a future genuinely new scan.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    outdir = root / args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    rows, inputs, missing = _collect_inputs(root)
    if not rows:
        raise RuntimeError(f"No candidate rows loaded. Missing inputs: {missing}")

    classification_counts = Counter(str(r.get("classification")) for r in rows if r.get("classification"))
    family_counts = Counter(str(r.get("family")) for r in rows if r.get("family"))
    side_counts = Counter(str(r.get("side")) for r in rows if r.get("side"))
    reason_counts: Counter[str] = Counter()
    bucket_counts: Counter[str] = Counter()
    for r in rows:
        for reason in _split_reasons(r.get("failed_reasons"), r.get("classification")):
            reason_counts[reason] += 1
            for b in _reason_buckets(reason):
                bucket_counts[b] += 1

    scenario_results = _scenario_analysis(rows)
    cost_needed = _cost_needed_profile(rows)

    diagnostic = {
        "total_candidates_analyzed": len(rows),
        "total_strict_watch_count": sum(int(_safe_float(i.get("strict_watch_count")) or 0) for i in inputs),
        "total_soft_watch_count": sum(int(_safe_float(i.get("soft_watch_count")) or 0) for i in inputs),
        "classification_counts": [{"key": k, "n": v} for k, v in classification_counts.most_common()],
        "family_counts": [{"key": k, "n": v} for k, v in family_counts.most_common()],
        "side_counts": [{"key": k, "n": v} for k, v in side_counts.most_common()],
        "failed_reason_counts": [{"key": k, "n": v} for k, v in reason_counts.most_common(40)],
        "failed_reason_bucket_counts": [{"key": k, "n": v} for k, v in bucket_counts.most_common(40)],
        "numeric_profile": {field: _numeric_profile(rows, field) for field in NUMERIC_FIELDS + ["stage_residual_bps"]},
        "scenario_analysis": scenario_results,
        "cost_needed_profile": cost_needed,
        "top_by_cost_mean": _top_rows(rows, "cost_stressed_mean_bps", True, 30),
        "top_by_stage_residual": _top_rows(rows, "stage_residual_bps", True, 30),
        "best_worst_quarter_slip16": _top_rows(rows, "worst_quarter_slip16_mean_bps", True, 30),
        "best_boot_p10": _top_rows(rows, "boot_p10_bps", True, 30),
    }
    decision = _decision_logic(rows, scenario_results, cost_needed)

    summary = {
        "stage": "Stage45_COST_AWARE_BASELINE_RECALIBRATION_OR_EXTERNAL_CONTEXT_DECISION",
        "inputs": inputs,
        "missing_inputs": missing,
        "diagnostic": diagnostic,
        "decision": decision,
        **PROMOTION_LOCK,
        "next_allowed_step": decision.get("recommended_next_stage"),
    }

    json_path = outdir / "stage45_cost_aware_baseline_recalibration_summary.json"
    md_path = outdir / "stage45_cost_aware_baseline_recalibration.md"
    csv_path = outdir / "stage45_cost_aware_failure_reasons_long.csv"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(md_path, summary)
    _write_csv_long_reasons(csv_path, rows)

    if args.print_summary:
        compact = {
            "stage": summary["stage"],
            "total_candidates_analyzed": diagnostic["total_candidates_analyzed"],
            "total_strict_watch_count": diagnostic["total_strict_watch_count"],
            "total_soft_watch_count": diagnostic["total_soft_watch_count"],
            "scenario_pass_counts": [
                {"scenario": s["scenario"]["name"], "pass_count": s["pass_count"]}
                for s in scenario_results
            ],
            "recommended_next_stage": decision.get("recommended_next_stage"),
            **PROMOTION_LOCK,
        }
        print(json.dumps(compact, ensure_ascii=False, indent=2))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Stage45 cost-aware baseline recalibration / external-context decision diagnostic")
    p.add_argument("--root", default=".", help="Repo root. Default: current directory")
    p.add_argument("--outdir", default="reports/stage45", help="Output directory relative to root")
    p.add_argument("--print-summary", action="store_true", help="Print compact summary JSON")
    return p


if __name__ == "__main__":
    raise SystemExit(run(build_arg_parser().parse_args()))
