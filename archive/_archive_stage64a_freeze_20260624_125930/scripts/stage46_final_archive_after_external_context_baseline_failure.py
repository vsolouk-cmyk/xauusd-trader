#!/usr/bin/env python3
"""
Stage46_FINAL_ARCHIVE_AFTER_EXTERNAL_CONTEXT_BASELINE_FAILURE

Final archive/report generator after Stage46A external-context baseline scan produced
no strict/soft survivors and Stage46C recommended archive.

This script does not create signals, does not scan candidates, does not rescue archived
Stage41/42/43 rows, and cannot authorize promotion, EA, paper-live, or live trading.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

STAGE = "Stage46_FINAL_ARCHIVE_AFTER_EXTERNAL_CONTEXT_BASELINE_FAILURE"
DEFAULT_STAGE46C_SUMMARY = "reports/stage46c/stage46c_external_context_failure_analysis_or_archive_summary.json"
DEFAULT_STAGE46A_SUMMARY = "reports/stage46a/stage46a_external_context_baseline_scan_implementation_summary.json"
DEFAULT_STAGE46_SUMMARY = "reports/stage46/stage46_external_context_baseline_scan_design_summary.json"
DEFAULT_STAGE45B3_SUMMARY = "reports/stage45b3/stage45b3_external_context_baseline_design_precheck_summary.json"
DEFAULT_OUTDIR = "reports/stage46_final_archive"

NO_GO = "NO_GO"

NOT_ALLOWED = [
    "candidate_rescue_from_stage41_42_43",
    "post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets",
    "EA_paper_live_live_from_archived_rows",
    "ML_before_robust_cost_aware_baseline",
    "continuing_external_context_branch_after_archive_without_new_structural_thesis",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path), "error": "missing"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover
        return {"exists": True, "path": str(path), "error": repr(exc)}


def rel(repo_root: Path, p: Path) -> str:
    try:
        return str(p.resolve().relative_to(repo_root.resolve()))
    except Exception:
        return str(p)


def safe_get(d: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = d
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def profile_stage_reference(repo_root: Path, rel_path: str) -> Dict[str, Any]:
    path = repo_root / rel_path
    payload = read_json(path)
    return {
        "path": rel_path,
        "exists": path.exists(),
        "error": payload.get("error"),
        "stage": payload.get("stage"),
        "status": safe_get(payload, "decision", "status", default=payload.get("status")),
        "next_allowed_step": payload.get("next_allowed_step") or safe_get(payload, "decision", "recommended_next_stage"),
        "promotion": payload.get("promotion") or safe_get(payload, "decision", "promotion"),
        "EA": payload.get("EA") or safe_get(payload, "decision", "EA"),
        "paper_live": payload.get("paper_live") or safe_get(payload, "decision", "paper_live"),
        "live": payload.get("live") or safe_get(payload, "decision", "live"),
        "blockers": safe_get(payload, "decision", "blockers", default=[]),
        "warnings": safe_get(payload, "decision", "warnings", default=[]),
    }


def build_archive_register(stage46c: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for rec in stage46c.get("recommendation_contract", []) or []:
        rows.append({
            "item_type": "recommendation",
            "key": rec.get("recommendation", ""),
            "status": rec.get("status", ""),
            "reason": rec.get("reason", ""),
            "archive_action": "preserve_as_decision_record",
        })
    for bucket in stage46c.get("failure_buckets", []) or []:
        rows.append({
            "item_type": "failure_bucket",
            "key": bucket.get("bucket", ""),
            "status": str(bucket.get("triggered", "")),
            "reason": bucket.get("evidence", ""),
            "archive_action": bucket.get("interpretation", ""),
        })
    return rows


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    cols = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def write_markdown(path: Path, summary: Dict[str, Any]) -> None:
    dec = summary["decision"]
    stage_refs = summary.get("stage_references", {})
    stage46c = summary.get("stage46c_reference", {})
    scan = stage46c.get("scan_recap", {})
    family = stage46c.get("family_summary", []) or []
    buckets = stage46c.get("triggered_failure_buckets", []) or []
    top = (stage46c.get("top_diagnostic_candidates", []) or [])[:10]

    lines: List[str] = []
    lines.append(f"# {STAGE}")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    lines.append(f"promotion = {dec['promotion']}")
    lines.append(f"EA = {dec['EA']}")
    lines.append(f"paper_live = {dec['paper_live']}")
    lines.append(f"live = {dec['live']}")
    lines.append(f"status = {dec['status']}")
    lines.append(f"recommended_next_stage = {dec['recommended_next_stage']}")
    lines.append("```")
    lines.append("")
    lines.append("Stage46 final archive closes the external-context baseline branch after the predefined Stage46A scan produced no strict or soft survivors and Stage46C recommended archive. This step does not create signals, shortlist candidates, or authorize promotion.")
    lines.append("")

    lines.append("## Stage chain references")
    lines.append("")
    lines.append("| stage_file | exists | status | next_allowed_step |")
    lines.append("| :-- | :-- | :-- | :-- |")
    for key, ref in stage_refs.items():
        lines.append(f"| {ref.get('path')} | {ref.get('exists')} | {ref.get('status')} | {ref.get('next_allowed_step')} |")
    lines.append("")

    lines.append("## Stage46A scan recap")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(scan, indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")

    lines.append("## Triggered failure buckets")
    lines.append("")
    for b in buckets:
        lines.append(f"- `{b}`")
    lines.append("")

    lines.append("## Family summary")
    lines.append("")
    lines.append("| family_id | candidates | best_candidate_id | best_mean_net_bps | best_oos_mean_net_bps | best_residual_bps |")
    lines.append("| :-- | --: | :-- | --: | --: | --: |")
    for row in family:
        lines.append(
            f"| {row.get('family_id')} | {row.get('candidate_count')} | {row.get('best_candidate_id')} | "
            f"{float(row.get('best_mean_net_bps', 0)):.3f} | {float(row.get('best_oos_mean_net_bps', 0)):.3f} | {float(row.get('best_residual_vs_benchmark_bps', 0)):.3f} |"
        )
    lines.append("")

    lines.append("## Top diagnostic candidates")
    lines.append("")
    lines.append("| candidate_id | family_id | mean_gross | mean_cost | mean_net | oos_mean | residual |")
    lines.append("| :-- | :-- | --: | --: | --: | --: | --: |")
    for row in top:
        def fnum(k: str) -> float:
            try:
                return float(row.get(k, 0))
            except Exception:
                return 0.0
        lines.append(
            f"| {row.get('candidate_id')} | {row.get('family_id')} | {fnum('mean_gross_bps'):.3f} | {fnum('mean_cost_bps'):.3f} | {fnum('mean_net_bps'):.3f} | {fnum('oos_mean_net_bps'):.3f} | {fnum('residual_vs_benchmark_bps'):.3f} |"
        )
    lines.append("")

    lines.append("## Archive interpretation")
    lines.append("")
    lines.append("The external-context branch was a fresh predefined pass. It did not overcome observed costs, did not produce positive OOS net evidence, did not pass worst-quarter or bootstrap lower-tail checks, and did not produce enough residual edge over benchmark. Therefore there is no Stage46B audit target.")
    lines.append("")
    lines.append("## Not allowed")
    lines.append("")
    for item in dec["not_allowed"]:
        lines.append(f"- `{item}`")
    lines.append("")
    lines.append("## Next valid action")
    lines.append("")
    lines.append("Move to a new session/transfer package or define a genuinely new structural thesis. Do not continue this external-context branch by tuning bad buckets, event windows, archived rows, or post-hoc filters.")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def build_summary(args: argparse.Namespace) -> Dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    outdir = repo_root / args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    stage46c_path = repo_root / args.stage46c_summary
    stage46c = read_json(stage46c_path)

    stage_refs = {
        "stage45b3": profile_stage_reference(repo_root, args.stage45b3_summary),
        "stage46": profile_stage_reference(repo_root, args.stage46_summary),
        "stage46a": profile_stage_reference(repo_root, args.stage46a_summary),
        "stage46c": profile_stage_reference(repo_root, args.stage46c_summary),
    }

    expected_stage46c_status = "EXTERNAL_CONTEXT_BASELINE_FAILURE_ANALYSIS_COMPLETE_ARCHIVE_RECOMMENDED_NO_PROMOTION"
    stage46c_status = safe_get(stage46c, "decision", "status", default=stage46c.get("status"))
    stage46c_ready = stage46c_status == expected_stage46c_status

    blockers: List[str] = []
    warnings: List[str] = []
    if not stage46c_path.exists():
        blockers.append("stage46c_summary_missing")
    if not stage46c_ready:
        blockers.append("stage46c_not_archive_recommended")
    if safe_get(stage46c, "scan_recap", "strict_count", default=None) not in (0, "0"):
        warnings.append("stage46c_strict_count_not_zero_recheck_required")
    if safe_get(stage46c, "scan_recap", "soft_count", default=None) not in (0, "0"):
        warnings.append("stage46c_soft_count_not_zero_recheck_required")

    archive_register = build_archive_register(stage46c)
    archive_register_path = outdir / "stage46_final_archive_register.csv"
    write_csv(archive_register_path, archive_register)

    summary: Dict[str, Any] = {
        "stage": STAGE,
        "settings": {
            "repo_root": str(repo_root),
            "stage46c_summary": args.stage46c_summary,
            "outdir": args.outdir,
        },
        "stage_references": stage_refs,
        "stage46c_reference": {
            "path": args.stage46c_summary,
            "exists": stage46c_path.exists(),
            "error": stage46c.get("error"),
            "status": stage46c_status,
            "next_allowed_step": stage46c.get("next_allowed_step"),
            "scan_recap": stage46c.get("scan_recap", {}),
            "triggered_failure_buckets": stage46c.get("triggered_failure_buckets", []),
            "family_summary": stage46c.get("family_summary", []),
            "top_diagnostic_candidates": stage46c.get("top_diagnostic_candidates", [])[:20],
            "recommendation_contract": stage46c.get("recommendation_contract", []),
        },
        "archive_register_rows": len(archive_register),
        "archive_register_csv": rel(repo_root, archive_register_path),
        "decision": {
            "status": "STAGE46_FINAL_ARCHIVE_COMPLETE_NO_PROMOTION" if not blockers else "STAGE46_FINAL_ARCHIVE_BLOCKED_NO_PROMOTION",
            "promotion": NO_GO,
            "EA": NO_GO,
            "paper_live": NO_GO,
            "live": NO_GO,
            "blockers": blockers,
            "warnings": warnings + ["stage46_external_context_branch_archived_no_survivors"],
            "recommended_next_stage": "NEW_SESSION_OR_NEW_STRUCTURAL_THESIS_DECISION" if not blockers else "Stage46_FINAL_ARCHIVE_RETRY_AFTER_MISSING_INPUTS",
            "rationale": [
                "Stage46A produced no strict or soft survivors and Stage46C recommended archive.",
                "Final archive preserves failure evidence and closes this branch without promotion.",
                "Any future work must start from a genuinely new predefined structural thesis, not from post-hoc rescue.",
            ],
            "not_allowed": NOT_ALLOWED,
        },
        "promotion": NO_GO,
        "EA": NO_GO,
        "paper_live": NO_GO,
        "live": NO_GO,
        "next_allowed_step": "NEW_SESSION_OR_NEW_STRUCTURAL_THESIS_DECISION" if not blockers else "Stage46_FINAL_ARCHIVE_RETRY_AFTER_MISSING_INPUTS",
        "outputs": {
            "summary_json": rel(repo_root, outdir / "stage46_final_archive_after_external_context_baseline_failure_summary.json"),
            "markdown": rel(repo_root, outdir / "stage46_final_archive_after_external_context_baseline_failure.md"),
            "archive_register_csv": rel(repo_root, archive_register_path),
        },
        "generated_utc": utc_now(),
    }

    summary_path = outdir / "stage46_final_archive_after_external_context_baseline_failure_summary.json"
    md_path = outdir / "stage46_final_archive_after_external_context_baseline_failure.md"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(md_path, summary)

    if args.print_summary:
        print(json.dumps({
            "stage": STAGE,
            "status": summary["decision"]["status"],
            "blockers": summary["decision"]["blockers"],
            "warnings": summary["decision"]["warnings"],
            "next_allowed_step": summary["next_allowed_step"],
            "outputs": list(summary["outputs"].values()),
        }, indent=2, ensure_ascii=False))

    return summary


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=STAGE)
    p.add_argument("--repo-root", default=".")
    p.add_argument("--stage46c-summary", default=DEFAULT_STAGE46C_SUMMARY)
    p.add_argument("--stage46a-summary", default=DEFAULT_STAGE46A_SUMMARY)
    p.add_argument("--stage46-summary", default=DEFAULT_STAGE46_SUMMARY)
    p.add_argument("--stage45b3-summary", default=DEFAULT_STAGE45B3_SUMMARY)
    p.add_argument("--outdir", default=DEFAULT_OUTDIR)
    p.add_argument("--print-summary", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    build_summary(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
