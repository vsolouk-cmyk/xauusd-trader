#!/usr/bin/env python3
"""
Stage44_THESIS_SPACE_FAILURE_META_DIAGNOSTIC

Meta-diagnostic over recent XAUUSD thesis megascan outputs.
This script does not generate trade signals and cannot promote any candidate.
It reads candidate CSV + summary JSON files from prior stages and identifies
why the thesis space is failing: cost/slip, worst-quarter fragility, train/OOS,
bootstrap weakness, event scarcity, benchmark residual, concentration, and path risk.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

STAGE = "Stage44_THESIS_SPACE_FAILURE_META_DIAGNOSTIC"
DEFAULT_STAGE_FILES = {
    "stage41": {
        "summary": "reports/stage41/stage41_parallel_thesis_megascan_v2_summary.json",
        "candidates": "reports/stage41/stage41_parallel_thesis_megascan_v2_candidates.csv",
    },
    "stage42": {
        "summary": "reports/stage42/stage42_parallel_intraday_execution_megascan_v3_summary.json",
        "candidates": "reports/stage42/stage42_parallel_intraday_execution_megascan_v3_candidates.csv",
    },
    "stage43": {
        "summary": "reports/stage43/stage43_parallel_context_regime_megascan_v4_summary.json",
        "candidates": "reports/stage43/stage43_parallel_context_regime_megascan_v4_candidates.csv",
    },
}

PROMOTION_BLOCK = {
    "promotion": "NO_GO",
    "EA": "NO_GO",
    "paper_live": "NO_GO",
    "live": "NO_GO",
}

REASON_BUCKET_PATTERNS: List[Tuple[str, str]] = [
    (r"INSUFFICIENT_EVENTS|insufficient", "event_scarcity"),
    (r"cost_mean|cost_stressed|mean_gt", "cost_or_mean_edge"),
    (r"residual", "benchmark_residual"),
    (r"train", "train_segment"),
    (r"oos", "oos_segment"),
    (r"worst_quarter|positive_quarter|quarter", "quarter_stability"),
    (r"boot_p10|boot_prob|bootstrap", "bootstrap_stability"),
    (r"touch|stop|mae|mfe", "path_risk"),
    (r"top_year|year_share|concentration|LOYO|loyo", "concentration"),
]

RISK_COLUMNS = [
    "cost_stressed_mean_bps",
    "h1_benchmark_cost_adjusted_residual_bps",
    "intraday_benchmark_cost_adjusted_residual_bps",
    "context_benchmark_cost_adjusted_residual_bps",
    "train_cost_mean_bps",
    "oos_cost_mean_bps",
    "worst_quarter_slip16_mean_bps",
    "boot_p10_bps",
    "oos_touch_stop_100bps_pct",
    "oos_touch_stop_50bps_pct",
    "top_year_event_share_pct",
    "event_clock_n",
    "horizon_h",
    "horizon_minutes",
]


@dataclass
class StageInput:
    name: str
    summary_path: Path
    candidates_path: Path
    summary: Dict[str, Any]
    candidates: List[Dict[str, Any]]


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if math.isfinite(float(value)):
            return float(value)
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "na", "n/a"}:
        return None
    try:
        value_f = float(text)
    except ValueError:
        return None
    if not math.isfinite(value_f):
        return None
    return value_f


def _safe_int(value: Any) -> Optional[int]:
    value_f = _safe_float(value)
    if value_f is None:
        return None
    return int(round(value_f))


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _read_csv(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(dict(row))
    return rows


def _split_reasons(text: Any, classification: Any = None) -> List[str]:
    parts: List[str] = []
    for raw in [classification, text]:
        if raw is None:
            continue
        for p in re.split(r"[;|,]+", str(raw)):
            p = p.strip()
            if p:
                parts.append(p)
    return parts


def _bucket_reason(reason: str) -> str:
    for pattern, bucket in REASON_BUCKET_PATTERNS:
        if re.search(pattern, reason, flags=re.IGNORECASE):
            return bucket
    return "other"


def _quantiles(values: Sequence[float]) -> Dict[str, Optional[float]]:
    clean = sorted([v for v in values if v is not None and math.isfinite(v)])
    if not clean:
        return {"n": 0, "min": None, "p10": None, "median": None, "p90": None, "max": None, "mean": None}
    def pct(p: float) -> float:
        if len(clean) == 1:
            return clean[0]
        pos = (len(clean) - 1) * p
        lo = math.floor(pos)
        hi = math.ceil(pos)
        if lo == hi:
            return clean[lo]
        return clean[lo] * (hi - pos) + clean[hi] * (pos - lo)
    return {
        "n": len(clean),
        "min": clean[0],
        "p10": pct(0.10),
        "median": pct(0.50),
        "p90": pct(0.90),
        "max": clean[-1],
        "mean": statistics.fmean(clean),
    }


def _top_counter(counter: Counter, limit: int = 30) -> List[Dict[str, Any]]:
    return [{"key": k, "n": int(v)} for k, v in counter.most_common(limit)]


def _stage_paths_from_args(args: argparse.Namespace) -> Dict[str, Dict[str, Path]]:
    paths: Dict[str, Dict[str, Path]] = {}
    for name, rels in DEFAULT_STAGE_FILES.items():
        paths[name] = {
            "summary": Path(args.repo_root) / rels["summary"],
            "candidates": Path(args.repo_root) / rels["candidates"],
        }
    if args.extra_stage:
        for spec in args.extra_stage:
            # Format: stage_name:summary_path:candidates_path
            parts = spec.split(":", 2)
            if len(parts) != 3:
                raise SystemExit(f"Invalid --extra-stage spec {spec!r}; expected name:summary_path:candidates_path")
            name, summary, candidates = parts
            paths[name] = {"summary": Path(summary), "candidates": Path(candidates)}
    return paths


def _load_inputs(args: argparse.Namespace) -> Tuple[List[StageInput], List[Dict[str, Any]]]:
    loaded: List[StageInput] = []
    missing: List[Dict[str, Any]] = []
    for name, pair in _stage_paths_from_args(args).items():
        summary_path = pair["summary"]
        candidates_path = pair["candidates"]
        if not summary_path.exists() or not candidates_path.exists():
            missing.append({
                "stage": name,
                "summary_exists": summary_path.exists(),
                "candidates_exists": candidates_path.exists(),
                "summary_path": str(summary_path),
                "candidates_path": str(candidates_path),
            })
            continue
        summary = _read_json(summary_path)
        candidates = _read_csv(candidates_path)
        loaded.append(StageInput(name, summary_path, candidates_path, summary, candidates))
    if not loaded:
        raise RuntimeError(
            "No prior stage candidate/summary files were found. Run Stage41/42/43 first, "
            "or pass --extra-stage name:summary.json:candidates.csv."
        )
    return loaded, missing


def _classification_counts(rows: List[Dict[str, Any]]) -> Counter:
    c = Counter()
    for r in rows:
        key = str(r.get("classification", "UNKNOWN") or "UNKNOWN")
        c[key] += 1
    return c


def _family_counts(rows: List[Dict[str, Any]]) -> Counter:
    c = Counter()
    for r in rows:
        key = str(r.get("family", "UNKNOWN") or "UNKNOWN")
        c[key] += 1
    return c


def _side_counts(rows: List[Dict[str, Any]]) -> Counter:
    c = Counter()
    for r in rows:
        key = str(r.get("side", "UNKNOWN") or "UNKNOWN")
        c[key] += 1
    return c


def _reason_counters(rows: List[Dict[str, Any]]) -> Tuple[Counter, Counter]:
    reason_counter = Counter()
    bucket_counter = Counter()
    for r in rows:
        reasons = _split_reasons(r.get("failed_reasons"), r.get("classification"))
        for reason in reasons:
            reason_counter[reason] += 1
            bucket_counter[_bucket_reason(reason)] += 1
    return reason_counter, bucket_counter


def _numeric_profile(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Optional[float]]]:
    profile: Dict[str, Dict[str, Optional[float]]] = {}
    for col in RISK_COLUMNS:
        vals: List[float] = []
        for r in rows:
            val = _safe_float(r.get(col))
            if val is not None:
                vals.append(val)
        if vals:
            profile[col] = _quantiles(vals)
    return profile


def _best_by_metric(rows: List[Dict[str, Any]], metric: str, reverse: bool, limit: int = 15) -> List[Dict[str, Any]]:
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for r in rows:
        val = _safe_float(r.get(metric))
        if val is None:
            continue
        scored.append((val, r))
    scored.sort(key=lambda x: x[0], reverse=reverse)
    out = []
    for val, r in scored[:limit]:
        out.append({
            "stage": r.get("stage"),
            "classification": r.get("classification"),
            "family": r.get("family"),
            "candidate": r.get("candidate"),
            "side": r.get("side"),
            "horizon_h": _safe_float(r.get("horizon_h")),
            "horizon_minutes": _safe_float(r.get("horizon_minutes")),
            "event_clock_n": _safe_int(r.get("event_clock_n")),
            metric: val,
            "cost_stressed_mean_bps": _safe_float(r.get("cost_stressed_mean_bps")),
            "train_cost_mean_bps": _safe_float(r.get("train_cost_mean_bps")),
            "oos_cost_mean_bps": _safe_float(r.get("oos_cost_mean_bps")),
            "worst_quarter_slip16_mean_bps": _safe_float(r.get("worst_quarter_slip16_mean_bps")),
            "boot_p10_bps": _safe_float(r.get("boot_p10_bps")),
            "failed_reasons": r.get("failed_reasons"),
        })
    return out


def _pairwise_stage_summary(inputs: List[StageInput]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for inp in inputs:
        s = inp.summary
        rows.append({
            "stage": inp.name,
            "reported_stage": s.get("stage"),
            "candidate_rows_summary": s.get("candidate_rows"),
            "candidate_rows_csv": len(inp.candidates),
            "events_rows_written": s.get("events_rows_written"),
            "strict_watch_count": (
                s.get("strict_stage41_scan_watch_count")
                or s.get("strict_stage42_intraday_scan_watch_count")
                or s.get("strict_stage43_context_regime_scan_watch_count")
                or s.get("strict_watch_count")
                or 0
            ),
            "soft_watch_count": (
                s.get("soft_stage41_scan_watch_count")
                or s.get("soft_stage42_intraday_scan_watch_count")
                or s.get("soft_stage43_context_regime_scan_watch_count")
                or s.get("soft_watch_count")
                or 0
            ),
            "promotion": s.get("promotion"),
            "EA": s.get("EA"),
            "paper_live": s.get("paper_live"),
            "live": s.get("live"),
            "classification_counts": s.get("classification_counts", {}),
        })
    return rows


def _diagnose_failure_space(all_rows: List[Dict[str, Any]], stage_summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
    reason_counter, bucket_counter = _reason_counters(all_rows)
    class_counter = _classification_counts(all_rows)
    family_counter = _family_counts(all_rows)
    side_counter = _side_counts(all_rows)
    numeric = _numeric_profile(all_rows)

    total_candidates = len(all_rows)
    total_strict = sum(int(s.get("strict_watch_count") or 0) for s in stage_summaries)
    total_soft = sum(int(s.get("soft_watch_count") or 0) for s in stage_summaries)

    blockers = []
    if total_strict == 0 and total_soft == 0:
        blockers.append("no_shortlist_across_recent_scans")
    if bucket_counter.get("cost_or_mean_edge", 0) > 0:
        blockers.append("cost_adjusted_mean_edge_not_sufficient")
    if bucket_counter.get("quarter_stability", 0) > 0:
        blockers.append("worst_quarter_or_quarter_stability_fragility")
    if bucket_counter.get("bootstrap_stability", 0) > 0:
        blockers.append("bootstrap_tail_or_probability_weakness")
    if bucket_counter.get("event_scarcity", 0) > 0:
        blockers.append("event_scarcity_for_context_filtered_theses")
    if bucket_counter.get("benchmark_residual", 0) > 0:
        blockers.append("weak_or_negative_residual_vs_benchmark")
    if bucket_counter.get("oos_segment", 0) > 0 or bucket_counter.get("train_segment", 0) > 0:
        blockers.append("train_oos_instability")
    if bucket_counter.get("path_risk", 0) > 0:
        blockers.append("path_risk_or_stop_touch_fragility")
    if bucket_counter.get("concentration", 0) > 0:
        blockers.append("year_or_event_concentration_risk")

    recommendation = {
        "archive_recent_blind_megascans": total_strict == 0 and total_soft == 0,
        "do_not_build_stage41b_42b_43b": total_strict == 0,
        "do_not_promote_any_recent_candidate": True,
        "next_stage": "Stage45_COST_AWARE_BASELINE_RECALIBRATION_OR_EXTERNAL_CONTEXT_DECISION",
        "rationale": (
            "Recent parallel thesis scans produced no strict or soft shortlist. "
            "The failure pattern should be treated as thesis-space evidence, not as a prompt for post-hoc filtering. "
            "The next efficient step is to recalibrate what edge must beat under realistic cost/spread/slip and decide "
            "whether external macro/news/yields context is required before more thesis scanning."
        ),
        "allowed_next_options": [
            "Stage45A cost/spread/slip sensitivity and threshold recalibration using existing candidate/event outputs",
            "Stage45B external-context decision document: DXY/yields/news calendar/CME GC reference before new scans",
            "Stage45C data-source/feed comparison if broker CFD microstructure appears too noisy for intraday edges",
        ],
        "not_allowed": [
            "Stage41B/Stage42B/Stage43B without strict shortlist",
            "post-hoc removal of weak hours/months/years/quarters/context states",
            "EA/paper-live/live from archived rows",
            "ML model before a robust cost-aware baseline exists",
        ],
    }

    return {
        "total_candidates_analyzed": total_candidates,
        "total_strict_watch_count": total_strict,
        "total_soft_watch_count": total_soft,
        "classification_counts": _top_counter(class_counter, 50),
        "family_counts": _top_counter(family_counter, 80),
        "side_counts": _top_counter(side_counter, 20),
        "failed_reason_counts": _top_counter(reason_counter, 80),
        "failed_reason_bucket_counts": _top_counter(bucket_counter, 30),
        "numeric_profile": numeric,
        "dominant_blockers": blockers,
        "top_by_cost_mean": _best_by_metric(all_rows, "cost_stressed_mean_bps", reverse=True, limit=25),
        "top_by_residual_h1": _best_by_metric(all_rows, "h1_benchmark_cost_adjusted_residual_bps", reverse=True, limit=10),
        "top_by_residual_intraday": _best_by_metric(all_rows, "intraday_benchmark_cost_adjusted_residual_bps", reverse=True, limit=10),
        "top_by_residual_context": _best_by_metric(all_rows, "context_benchmark_cost_adjusted_residual_bps", reverse=True, limit=10),
        "best_worst_quarter_slip16": _best_by_metric(all_rows, "worst_quarter_slip16_mean_bps", reverse=True, limit=20),
        "best_boot_p10": _best_by_metric(all_rows, "boot_p10_bps", reverse=True, limit=20),
        "recommendation": recommendation,
    }


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _flatten_reasons_for_csv(all_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in all_rows:
        reasons = _split_reasons(r.get("failed_reasons"), r.get("classification"))
        if not reasons:
            reasons = ["UNKNOWN"]
        for reason in reasons:
            out.append({
                "stage": r.get("stage"),
                "family": r.get("family"),
                "candidate": r.get("candidate"),
                "side": r.get("side"),
                "classification": r.get("classification"),
                "reason": reason,
                "reason_bucket": _bucket_reason(reason),
                "event_clock_n": r.get("event_clock_n"),
                "cost_stressed_mean_bps": r.get("cost_stressed_mean_bps"),
                "train_cost_mean_bps": r.get("train_cost_mean_bps"),
                "oos_cost_mean_bps": r.get("oos_cost_mean_bps"),
                "worst_quarter_slip16_mean_bps": r.get("worst_quarter_slip16_mean_bps"),
                "boot_p10_bps": r.get("boot_p10_bps"),
            })
    return out


def _format_float(value: Any, digits: int = 3) -> str:
    val = _safe_float(value)
    if val is None:
        return "NA"
    return f"{val:.{digits}f}"


def _md_table(rows: List[Dict[str, Any]], columns: List[str], limit: int = 30) -> str:
    if not rows:
        return "\n_None._\n"
    rows = rows[:limit]
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join([":--" for _ in columns]) + " |"
    lines = [header, sep]
    for r in rows:
        cells = []
        for c in columns:
            v = r.get(c)
            if isinstance(v, float):
                cells.append(_format_float(v))
            else:
                text = str(v) if v is not None else ""
                text = text.replace("|", "/")
                if len(text) > 120:
                    text = text[:117] + "..."
                cells.append(text)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _write_markdown(path: Path, result: Dict[str, Any], stage_summaries: List[Dict[str, Any]], missing: List[Dict[str, Any]]) -> None:
    diag = result["diagnostic"]
    rec = diag["recommendation"]
    lines: List[str] = []
    lines.append(f"# {STAGE}")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    lines.append("promotion = NO_GO")
    lines.append("EA = NO_GO")
    lines.append("paper_live = NO_GO")
    lines.append("live = NO_GO")
    lines.append("```")
    lines.append("")
    lines.append("Stage44 is a meta-diagnostic only. It does not create signals, does not shortlist candidates, and cannot promote any prior row.")
    lines.append("")
    lines.append("## Inputs analyzed")
    lines.append("")
    lines.append(_md_table(stage_summaries, ["stage", "reported_stage", "candidate_rows_csv", "events_rows_written", "strict_watch_count", "soft_watch_count", "promotion"], limit=20))
    if missing:
        lines.append("\n## Missing optional/default inputs")
        lines.append(_md_table(missing, ["stage", "summary_exists", "candidates_exists", "summary_path", "candidates_path"], limit=20))
    lines.append("\n## Aggregate result")
    lines.append("")
    lines.append("```text")
    lines.append(f"total_candidates_analyzed = {diag['total_candidates_analyzed']}")
    lines.append(f"total_strict_watch_count = {diag['total_strict_watch_count']}")
    lines.append(f"total_soft_watch_count = {diag['total_soft_watch_count']}")
    lines.append("```")
    lines.append("")
    lines.append("## Classification counts")
    lines.append("")
    lines.append(_md_table(diag["classification_counts"], ["key", "n"], limit=20))
    lines.append("\n## Failed reason bucket counts")
    lines.append("")
    lines.append(_md_table(diag["failed_reason_bucket_counts"], ["key", "n"], limit=30))
    lines.append("\n## Most frequent raw failed reasons")
    lines.append("")
    lines.append(_md_table(diag["failed_reason_counts"], ["key", "n"], limit=40))
    lines.append("\n## Dominant blockers")
    lines.append("")
    lines.append("```text")
    for b in diag["dominant_blockers"]:
        lines.append(str(b))
    lines.append("```")
    lines.append("\n## Numeric profile")
    lines.append("")
    numeric_rows = []
    for col, stats in diag["numeric_profile"].items():
        numeric_rows.append({
            "metric": col,
            "n": stats.get("n"),
            "min": _format_float(stats.get("min")),
            "p10": _format_float(stats.get("p10")),
            "median": _format_float(stats.get("median")),
            "p90": _format_float(stats.get("p90")),
            "max": _format_float(stats.get("max")),
            "mean": _format_float(stats.get("mean")),
        })
    lines.append(_md_table(numeric_rows, ["metric", "n", "min", "p10", "median", "p90", "max", "mean"], limit=50))
    lines.append("\n## Best rows by cost-stressed mean")
    lines.append("")
    lines.append(_md_table(diag["top_by_cost_mean"], ["stage", "family", "candidate", "side", "event_clock_n", "cost_stressed_mean_bps", "train_cost_mean_bps", "oos_cost_mean_bps", "worst_quarter_slip16_mean_bps", "boot_p10_bps", "failed_reasons"], limit=25))
    lines.append("\n## Best rows by worst-quarter slip16")
    lines.append("")
    lines.append(_md_table(diag["best_worst_quarter_slip16"], ["stage", "family", "candidate", "side", "event_clock_n", "worst_quarter_slip16_mean_bps", "cost_stressed_mean_bps", "failed_reasons"], limit=20))
    lines.append("\n## Recommendation")
    lines.append("")
    lines.append("```text")
    lines.append(f"archive_recent_blind_megascans = {rec['archive_recent_blind_megascans']}")
    lines.append(f"do_not_build_stage41b_42b_43b = {rec['do_not_build_stage41b_42b_43b']}")
    lines.append(f"do_not_promote_any_recent_candidate = {rec['do_not_promote_any_recent_candidate']}")
    lines.append(f"next_stage = {rec['next_stage']}")
    lines.append("```")
    lines.append("")
    lines.append(rec["rationale"])
    lines.append("\n## Allowed next options")
    lines.append("")
    for x in rec["allowed_next_options"]:
        lines.append(f"- `{x}`")
    lines.append("\n## Not allowed")
    lines.append("")
    for x in rec["not_allowed"]:
        lines.append(f"- `{x}`")
    lines.append("\n## Anti-overfit note")
    lines.append("")
    lines.append("Do not rescue Stage41/42/43 rows by post-hoc filtering. Any future scan must be a genuinely new pre-defined thesis or a cost/data-source/external-context decision phase.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    inputs, missing = _load_inputs(args)
    stage_summaries = _pairwise_stage_summary(inputs)
    all_rows: List[Dict[str, Any]] = []
    for inp in inputs:
        for r in inp.candidates:
            rr = dict(r)
            rr["stage"] = inp.name
            all_rows.append(rr)
    diagnostic = _diagnose_failure_space(all_rows, stage_summaries)
    result = {
        "stage": STAGE,
        "inputs": stage_summaries,
        "missing_inputs": missing,
        "diagnostic": diagnostic,
        **PROMOTION_BLOCK,
        "next_allowed_step": diagnostic["recommendation"]["next_stage"],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "stage44_thesis_space_failure_meta_diagnostic_summary.json"
    md_path = out_dir / "stage44_thesis_space_failure_meta_diagnostic.md"
    reasons_path = out_dir / "stage44_thesis_space_failure_reasons_long.csv"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_markdown(md_path, result, stage_summaries, missing)
    _write_csv(reasons_path, _flatten_reasons_for_csv(all_rows))
    if args.print_summary:
        print(json.dumps({
            "stage": STAGE,
            "total_candidates_analyzed": diagnostic["total_candidates_analyzed"],
            "total_strict_watch_count": diagnostic["total_strict_watch_count"],
            "total_soft_watch_count": diagnostic["total_soft_watch_count"],
            "dominant_blockers": diagnostic["dominant_blockers"],
            "next_allowed_step": result["next_allowed_step"],
            **PROMOTION_BLOCK,
        }, indent=2))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=STAGE)
    p.add_argument("--repo-root", default=".", help="Repository root. Default: current directory.")
    p.add_argument("--out-dir", default="reports/stage44", help="Output directory. Default: reports/stage44")
    p.add_argument(
        "--extra-stage",
        action="append",
        default=[],
        help="Optional extra input: name:summary.json:candidates.csv. Can be repeated.",
    )
    p.add_argument("--print-summary", action="store_true", help="Print compact JSON summary to stdout.")
    return p


if __name__ == "__main__":
    raise SystemExit(run(build_arg_parser().parse_args()))
