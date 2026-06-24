#!/usr/bin/env python3
"""Stage46C external-context failure analysis / archive decision.

This script is intentionally diagnostic-only. It reads the predefined fresh
Stage46A scan outputs and explains why the external-context baseline branch did
or did not produce a survivor. It does not create signals, shortlist candidates,
rescue archived rows, or authorize promotion.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Tuple

STAGE = "Stage46C_EXTERNAL_CONTEXT_FAILURE_ANALYSIS_OR_ARCHIVE"
DEFAULT_STAGE46A_SUMMARY = "reports/stage46a/stage46a_external_context_baseline_scan_implementation_summary.json"
DEFAULT_OUTDIR = "reports/stage46c"

NO_GO = {
    "promotion": "NO_GO",
    "EA": "NO_GO",
    "paper_live": "NO_GO",
    "live": "NO_GO",
}

NOT_ALLOWED = [
    "candidate_rescue_from_stage41_42_43",
    "post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets",
    "EA_paper_live_live_from_archived_rows",
    "ML_before_robust_cost_aware_baseline",
    "continuing_external_context_scan_without_failure_analysis_decision",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not path.exists():
        return None, "missing"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:  # pragma: no cover - defensive
        return None, repr(exc)


def as_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        if math.isfinite(float(v)):
            return float(v)
        return None
    s = str(v).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return None
    try:
        out = float(s)
    except Exception:
        return None
    if not math.isfinite(out):
        return None
    return out


def as_int(v: Any) -> Optional[int]:
    f = as_float(v)
    if f is None:
        return None
    return int(f)


def pct(v: Optional[float]) -> str:
    if v is None:
        return ""
    return f"{100.0 * v:.3f}%"


def profile(values: Iterable[Any]) -> Dict[str, Any]:
    vals = sorted([x for x in (as_float(v) for v in values) if x is not None])
    if not vals:
        return {"n": 0}
    def q(p: float) -> float:
        if len(vals) == 1:
            return vals[0]
        pos = (len(vals) - 1) * p
        lo = int(math.floor(pos))
        hi = int(math.ceil(pos))
        if lo == hi:
            return vals[lo]
        return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)
    return {
        "n": len(vals),
        "min": vals[0],
        "p10": q(0.10),
        "p25": q(0.25),
        "median": q(0.50),
        "p75": q(0.75),
        "p90": q(0.90),
        "p95": q(0.95),
        "p99": q(0.99),
        "max": vals[-1],
        "mean": sum(vals) / len(vals),
    }


def read_candidate_csv(repo_root: Path, summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    output_path = (summary.get("outputs") or {}).get("candidate_metrics_csv")
    if not output_path:
        return []
    p = Path(output_path)
    if not p.is_absolute():
        p = repo_root / p
    if not p.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with p.open("r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                rows.append(dict(row))
    except Exception:
        return []
    return rows


def candidate_rows_from_summary_or_csv(repo_root: Path, summary: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str]:
    rows = read_candidate_csv(repo_root, summary)
    if rows:
        return rows, "candidate_metrics_csv"
    top = summary.get("top_candidates") or []
    if isinstance(top, list):
        return [r for r in top if isinstance(r, dict)], "summary_top_candidates_only"
    return [], "none"


def count_where(rows: List[Dict[str, Any]], key: str, predicate) -> int:
    n = 0
    for row in rows:
        v = as_float(row.get(key))
        if v is not None and predicate(v):
            n += 1
    return n


def best_row(rows: List[Dict[str, Any]], metric: str) -> Optional[Dict[str, Any]]:
    best: Optional[Dict[str, Any]] = None
    best_val: Optional[float] = None
    for row in rows:
        v = as_float(row.get(metric))
        if v is None:
            continue
        if best_val is None or v > best_val:
            best = row
            best_val = v
    return best


def compact_row(row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not row:
        return {}
    keys = [
        "candidate_id", "family_id", "direction", "hold_bars", "news_mode", "params_json",
        "event_count", "mean_gross_bps", "mean_cost_bps", "mean_net_bps", "oos_mean_net_bps",
        "worst_quarter_mean_net_bps", "benchmark_mean_net_bps", "residual_vs_benchmark_bps",
        "bootstrap_mean_p05_bps", "classification",
    ]
    return {k: row.get(k) for k in keys if k in row}


def make_failure_buckets(summary: Dict[str, Any], rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    scan = summary.get("scan_summary") or {}
    candidate_rows = as_int(scan.get("candidate_rows")) or len(rows)
    strict_count = as_int(scan.get("strict_count")) or 0
    soft_count = as_int(scan.get("soft_count")) or 0

    rows_for_metrics = rows
    best_net = best_row(rows_for_metrics, "mean_net_bps")
    best_gross = best_row(rows_for_metrics, "mean_gross_bps")
    best_resid = best_row(rows_for_metrics, "residual_vs_benchmark_bps")
    best_oos = best_row(rows_for_metrics, "oos_mean_net_bps")
    best_boot = best_row(rows_for_metrics, "bootstrap_mean_p05_bps")
    best_worst_q = best_row(rows_for_metrics, "worst_quarter_mean_net_bps")

    pos_net = count_where(rows_for_metrics, "mean_net_bps", lambda x: x > 0)
    pos_oos = count_where(rows_for_metrics, "oos_mean_net_bps", lambda x: x > 0)
    pos_boot = count_where(rows_for_metrics, "bootstrap_mean_p05_bps", lambda x: x > 0)
    pos_worst_q = count_where(rows_for_metrics, "worst_quarter_mean_net_bps", lambda x: x > 0)
    pos_resid_1 = count_where(rows_for_metrics, "residual_vs_benchmark_bps", lambda x: x >= 1.0)

    gross_prof = profile([r.get("mean_gross_bps") for r in rows_for_metrics])
    cost_prof = profile([r.get("mean_cost_bps") for r in rows_for_metrics])
    net_prof = profile([r.get("mean_net_bps") for r in rows_for_metrics])
    resid_prof = profile([r.get("residual_vs_benchmark_bps") for r in rows_for_metrics])

    median_gross = gross_prof.get("median") if gross_prof.get("n") else None
    median_cost = cost_prof.get("median") if cost_prof.get("n") else None
    gross_cost_gap = None
    if isinstance(median_gross, (int, float)) and isinstance(median_cost, (int, float)):
        gross_cost_gap = median_gross - median_cost

    buckets = [
        {
            "bucket": "no_survivors",
            "triggered": strict_count == 0 and soft_count == 0,
            "evidence": f"strict_count={strict_count}; soft_count={soft_count}; candidate_rows={candidate_rows}",
            "interpretation": "No Stage46B audit is justified because there are no strict or soft survivors.",
        },
        {
            "bucket": "no_positive_net_edge",
            "triggered": pos_net == 0,
            "evidence": f"positive_mean_net_candidates={pos_net}; best_mean_net={as_float((best_net or {}).get('mean_net_bps'))}",
            "interpretation": "The external-context rules do not overcome observed transaction costs.",
        },
        {
            "bucket": "cost_overwhelms_gross_edge",
            "triggered": bool(gross_cost_gap is not None and gross_cost_gap < 0),
            "evidence": f"median_mean_gross={median_gross}; median_mean_cost={median_cost}; median_gross_minus_cost={gross_cost_gap}",
            "interpretation": "The raw directional context is too weak relative to cost assumptions.",
        },
        {
            "bucket": "oos_negative",
            "triggered": pos_oos == 0,
            "evidence": f"positive_oos_candidates={pos_oos}; best_oos_mean_net={as_float((best_oos or {}).get('oos_mean_net_bps'))}",
            "interpretation": "No candidate shows positive out-of-sample net performance.",
        },
        {
            "bucket": "quarter_stability_negative",
            "triggered": pos_worst_q == 0,
            "evidence": f"positive_worst_quarter_candidates={pos_worst_q}; best_worst_quarter={as_float((best_worst_q or {}).get('worst_quarter_mean_net_bps'))}",
            "interpretation": "Quarter-level stability remains negative even for the best candidates.",
        },
        {
            "bucket": "bootstrap_floor_negative",
            "triggered": pos_boot == 0,
            "evidence": f"positive_bootstrap_p05_candidates={pos_boot}; best_bootstrap_p05={as_float((best_boot or {}).get('bootstrap_mean_p05_bps'))}",
            "interpretation": "Bootstrap lower-tail evidence does not support promotion.",
        },
        {
            "bucket": "benchmark_residual_too_small",
            "triggered": pos_resid_1 == 0,
            "evidence": f"residual_ge_1bps_candidates={pos_resid_1}; best_residual={as_float((best_resid or {}).get('residual_vs_benchmark_bps'))}",
            "interpretation": "Residual edge versus simple benchmark is too small to justify continuing this scan branch.",
        },
    ]

    return buckets


def family_summary(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        family = str(row.get("family_id") or "UNKNOWN")
        groups.setdefault(family, []).append(row)
    out = []
    for family, rs in sorted(groups.items()):
        b = best_row(rs, "mean_net_bps")
        out.append({
            "family_id": family,
            "candidate_count": len(rs),
            "best_candidate_id": (b or {}).get("candidate_id"),
            "best_mean_net_bps": as_float((b or {}).get("mean_net_bps")),
            "best_oos_mean_net_bps": as_float((b or {}).get("oos_mean_net_bps")),
            "best_residual_vs_benchmark_bps": as_float((b or {}).get("residual_vs_benchmark_bps")),
            "best_bootstrap_mean_p05_bps": as_float((b or {}).get("bootstrap_mean_p05_bps")),
            "best_worst_quarter_mean_net_bps": as_float((b or {}).get("worst_quarter_mean_net_bps")),
            "positive_mean_net_count": count_where(rs, "mean_net_bps", lambda x: x > 0),
            "positive_oos_count": count_where(rs, "oos_mean_net_bps", lambda x: x > 0),
        })
    return out


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: List[str] = []
    for row in rows:
        for k in row.keys():
            if k not in keys:
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def md_table(rows: List[Dict[str, Any]], columns: List[str]) -> str:
    if not rows:
        return ""
    lines = []
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("| " + " | ".join([":--" for _ in columns]) + " |")
    for row in rows:
        vals = []
        for col in columns:
            v = row.get(col, "")
            if isinstance(v, float):
                vals.append(f"{v:.3f}")
            else:
                vals.append(str(v).replace("\n", " "))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def build_markdown(summary: Dict[str, Any], buckets: List[Dict[str, Any]], families: List[Dict[str, Any]], top: List[Dict[str, Any]]) -> str:
    decision = summary["decision"]
    lines = [
        f"# {STAGE}",
        "",
        "## Decision",
        "",
        "```text",
        f"promotion = {decision['promotion']}",
        f"EA = {decision['EA']}",
        f"paper_live = {decision['paper_live']}",
        f"live = {decision['live']}",
        f"status = {decision['status']}",
        f"recommended_next_stage = {decision['recommended_next_stage']}",
        "```",
        "",
        "Stage46C is failure analysis only. It does not create signals, rescue archived candidates, or authorize promotion.",
        "",
        "## Failure buckets",
        "",
        md_table(buckets, ["bucket", "triggered", "evidence", "interpretation"]),
        "",
        "## Family summary",
        "",
        md_table(families, ["family_id", "candidate_count", "best_candidate_id", "best_mean_net_bps", "best_oos_mean_net_bps", "best_residual_vs_benchmark_bps", "best_bootstrap_mean_p05_bps"]),
        "",
        "## Top diagnostic rows",
        "",
        md_table(top, ["candidate_id", "family_id", "direction", "hold_bars", "mean_gross_bps", "mean_cost_bps", "mean_net_bps", "oos_mean_net_bps", "residual_vs_benchmark_bps", "classification"]),
        "",
        "## Interpretation",
        "",
        "The external-context branch was implemented as a fresh predefined scan. It did not produce a strict or soft survivor. The dominant interpretation is that the available context variables may slightly rank or tag regimes, but they do not create enough net edge after observed costs and stability checks.",
        "",
        "## Not allowed",
        "",
    ]
    for item in NOT_ALLOWED:
        lines.append(f"- `{item}`")
    lines.extend([
        "",
        "## Anti-overfit note",
        "",
        "Do not tune event windows, bad hours, bad months, spread buckets, or archived candidate rows after seeing Stage46A failure. The valid next action is final archive/transfer or a genuinely new thesis decision outside this branch.",
        "",
    ])
    return "\n".join(lines)


def build_summary(args: argparse.Namespace) -> Dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    outdir = repo_root / args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    stage46a_path = repo_root / args.stage46a_summary
    stage46a, stage46a_error = read_json(stage46a_path)
    if stage46a is None:
        stage46a = {}

    rows, row_source = candidate_rows_from_summary_or_csv(repo_root, stage46a)
    scan = stage46a.get("scan_summary") or {}
    candidate_rows = as_int(scan.get("candidate_rows")) or len(rows)
    strict_count = as_int(scan.get("strict_count")) or 0
    soft_count = as_int(scan.get("soft_count")) or 0

    buckets = make_failure_buckets(stage46a, rows)
    families = family_summary(rows)
    top_sorted = sorted(rows, key=lambda r: as_float(r.get("mean_net_bps")) if as_float(r.get("mean_net_bps")) is not None else -1e18, reverse=True)[:20]
    top_compact = [compact_row(r) for r in top_sorted]

    critical_bucket_names = [b["bucket"] for b in buckets if b.get("triggered")]

    if stage46a_error:
        status = "STAGE46C_BLOCKED_MISSING_STAGE46A_SUMMARY_NO_PROMOTION"
        recommended = "Stage46A_EXTERNAL_CONTEXT_BASELINE_SCAN_IMPLEMENTATION"
        blockers = ["stage46a_summary_missing_or_unreadable"]
    elif strict_count > 0 or soft_count > 0:
        status = "STAGE46C_FOUND_SURVIVORS_ROUTE_TO_AUDIT_NO_PROMOTION"
        recommended = "Stage46B_EXTERNAL_CONTEXT_CANDIDATE_AUDIT"
        blockers = []
    else:
        status = "EXTERNAL_CONTEXT_BASELINE_FAILURE_ANALYSIS_COMPLETE_ARCHIVE_RECOMMENDED_NO_PROMOTION"
        recommended = "Stage46_FINAL_ARCHIVE_AFTER_EXTERNAL_CONTEXT_BASELINE_FAILURE"
        blockers = []

    recommendation_contract = [
        {
            "recommendation": "do_not_promote_stage46a",
            "status": "required",
            "reason": "strict_count=0 and soft_count=0; all tested candidates remain research-only failures",
        },
        {
            "recommendation": "do_not_rescue_stage41_42_43",
            "status": "required",
            "reason": "Stage46A was a fresh pass; archived candidate rescue remains prohibited",
        },
        {
            "recommendation": "archive_stage46_branch_if_no_new_thesis",
            "status": "recommended",
            "reason": "external context design did not overcome observed costs or stability constraints",
        },
        {
            "recommendation": "new_thesis_only_if_structurally_distinct",
            "status": "optional_future_research",
            "reason": "Any next scan must be based on a predefined structurally new thesis, not post-hoc filters",
        },
    ]

    summary: Dict[str, Any] = {
        "stage": STAGE,
        "settings": {
            "repo_root": str(repo_root),
            "stage46a_summary": args.stage46a_summary,
            "outdir": args.outdir,
            "candidate_row_source": row_source,
        },
        "stage46a_reference": {
            "path": str(stage46a_path),
            "exists": stage46a_path.exists(),
            "error": stage46a_error,
            "status": (stage46a.get("decision") or {}).get("status") or stage46a.get("status"),
            "next_allowed_step": stage46a.get("next_allowed_step"),
            "recommended_next_stage": (stage46a.get("decision") or {}).get("recommended_next_stage"),
        },
        "scan_recap": {
            "candidate_rows": candidate_rows,
            "strict_count": strict_count,
            "soft_count": soft_count,
            "classification_counts": scan.get("classification_counts") or {},
            "event_sample_rows_written": scan.get("event_sample_rows_written"),
        },
        "candidate_metric_profiles": {
            "mean_gross_bps": profile([r.get("mean_gross_bps") for r in rows]),
            "mean_cost_bps": profile([r.get("mean_cost_bps") for r in rows]),
            "mean_net_bps": profile([r.get("mean_net_bps") for r in rows]),
            "oos_mean_net_bps": profile([r.get("oos_mean_net_bps") for r in rows]),
            "worst_quarter_mean_net_bps": profile([r.get("worst_quarter_mean_net_bps") for r in rows]),
            "residual_vs_benchmark_bps": profile([r.get("residual_vs_benchmark_bps") for r in rows]),
            "bootstrap_mean_p05_bps": profile([r.get("bootstrap_mean_p05_bps") for r in rows]),
        },
        "failure_buckets": buckets,
        "triggered_failure_buckets": critical_bucket_names,
        "family_summary": families,
        "top_diagnostic_candidates": top_compact,
        "recommendation_contract": recommendation_contract,
        "decision": {
            "status": status,
            **NO_GO,
            "blockers": blockers,
            "warnings": ["stage46a_no_survivors_confirmed", "archive_recommended_unless_new_structural_thesis_is_defined"],
            "recommended_next_stage": recommended,
            "rationale": [
                "Stage46C analyzes the fresh external-context baseline failure without creating new signals.",
                "No strict or soft Stage46A survivor exists, so Stage46B audit is not justified.",
                "The valid path is final archive/transfer unless a genuinely new predefined thesis is selected.",
            ],
            "not_allowed": NOT_ALLOWED,
        },
        **NO_GO,
        "next_allowed_step": recommended,
        "outputs": {
            "summary_json": str(outdir / "stage46c_external_context_failure_analysis_or_archive_summary.json"),
            "markdown": str(outdir / "stage46c_external_context_failure_analysis_or_archive.md"),
            "failure_bucket_matrix_csv": str(outdir / "stage46c_failure_bucket_matrix.csv"),
            "family_failure_summary_csv": str(outdir / "stage46c_family_failure_summary.csv"),
            "top_candidate_diagnostic_csv": str(outdir / "stage46c_top_candidate_diagnostic.csv"),
            "recommendation_contract_csv": str(outdir / "stage46c_recommendation_contract.csv"),
        },
        "generated_utc": utc_now(),
    }

    write_csv(outdir / "stage46c_failure_bucket_matrix.csv", buckets)
    write_csv(outdir / "stage46c_family_failure_summary.csv", families)
    write_csv(outdir / "stage46c_top_candidate_diagnostic.csv", top_compact)
    write_csv(outdir / "stage46c_recommendation_contract.csv", recommendation_contract)

    (outdir / "stage46c_external_context_failure_analysis_or_archive_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (outdir / "stage46c_external_context_failure_analysis_or_archive.md").write_text(
        build_markdown(summary, buckets, families, top_compact), encoding="utf-8"
    )

    if args.print_summary:
        print(json.dumps({
            "stage": STAGE,
            "status": status,
            "candidate_rows": candidate_rows,
            "strict_count": strict_count,
            "soft_count": soft_count,
            "triggered_failure_buckets": critical_bucket_names,
            "recommended_next_stage": recommended,
            "promotion": "NO_GO",
            "EA": "NO_GO",
            "paper_live": "NO_GO",
            "live": "NO_GO",
        }, indent=2, ensure_ascii=False))

    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Stage46C external-context failure analysis / archive decision")
    ap.add_argument("--repo-root", default=".", help="Repository root")
    ap.add_argument("--stage46a-summary", default=DEFAULT_STAGE46A_SUMMARY, help="Stage46A summary JSON path relative to repo root")
    ap.add_argument("--outdir", default=DEFAULT_OUTDIR, help="Output directory relative to repo root")
    ap.add_argument("--print-summary", action="store_true", help="Print compact summary JSON")
    args = ap.parse_args(argv)
    build_summary(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
