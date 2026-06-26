#!/usr/bin/env python3
"""
Stage64N2 - Robustness downgrade or reconciliation decision memo (no order).

This script does not run a new validation scan. It reads Stage64N1 robustness-audit
outputs and decides whether the corrected survivor should be downgraded/killed, or
whether the Stage64N1 audit outcome itself is internally inconsistent and must be
reconciled before any downgrade decision.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        with path.open("w", encoding="utf-8", newline="") as f:
            f.write("")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def audit_lookup(audit_results: List[Dict[str, Any]], audit_id: str) -> Dict[str, Any]:
    for row in audit_results:
        if row.get("audit_id") == audit_id:
            return row
    return {"audit_id": audit_id, "pass": False, "headline": "audit row missing"}


def build_report(summary: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Stage64N2 - Robustness Downgrade or Reconciliation Decision (No Order)")
    lines.append("")
    lines.append(f"Generated UTC: `{summary['generated_utc']}`")
    lines.append("")
    lines.append("## Status")
    lines.append("")
    for k in ["status", "decision", "promotion", "paper_order", "paper_live", "live", "validation_allowed_for_order_or_promotion"]:
        lines.append(f"- {k}: `{summary.get(k)}`")
    lines.append("")
    lines.append("## Executive conclusion")
    lines.append("")
    lines.append(summary["executive_conclusion"])
    lines.append("")
    lines.append("## Target survivor")
    lines.append("")
    surv = summary.get("target_survivor", {})
    lines.append(f"- hypothesis_id: `{surv.get('hypothesis_id')}`")
    lines.append(f"- horizon_days: `{surv.get('horizon_days')}`")
    lines.append(f"- primary_benchmark_id: `{surv.get('primary_benchmark_id')}`")
    lines.append("")
    lines.append("## Stage64N1 audit-state review")
    lines.append("")
    lines.append("| audit_id | stage64n1_pass | n2_interpretation |")
    lines.append("|---|---:|---|")
    for row in summary["audit_state_review"]:
        lines.append(f"| `{row['audit_id']}` | `{row['stage64n1_pass']}` | `{row['n2_interpretation']}` |")
    lines.append("")
    lines.append("## A2 consistency review")
    lines.append("")
    a2 = summary["a2_consistency_review"]
    lines.append("| metric | value | threshold | pass |")
    lines.append("|---|---:|---:|---:|")
    for row in a2["metric_checks"]:
        lines.append(f"| `{row['metric']}` | `{row['value']}` | `{row['threshold']}` | `{row['pass']}` |")
    lines.append("")
    lines.append(f"- stage64n1_a2_pass_flag: `{a2['stage64n1_a2_pass_flag']}`")
    lines.append(f"- diagnostics_imply_a2_pass: `{a2['diagnostics_imply_a2_pass']}`")
    lines.append(f"- pass_flag_inconsistent_with_diagnostics: `{a2['pass_flag_inconsistent_with_diagnostics']}`")
    lines.append("")
    lines.append("## Decision matrix")
    lines.append("")
    lines.append("| path | status | decision | allowed_next |")
    lines.append("|---|---|---|---|")
    for row in summary["decision_matrix"]:
        lines.append(f"| `{row['path']}` | `{row['status']}` | {row['decision']} | {row['allowed_next']} |")
    lines.append("")
    lines.append("## Hard blocks")
    lines.append("")
    for block in summary["hard_blocks"]:
        lines.append(f"- `{block}`")
    lines.append("")
    lines.append("## Next allowed step")
    lines.append("")
    lines.append(f"`{summary['next_allowed_step']}`")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    config_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    cfg = read_json(config_path)
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    n1_rel = cfg.get("inputs", {}).get("stage64n1_summary")
    n1_path = root / n1_rel
    n1 = read_json(n1_path)

    thresholds = cfg.get("a2_consistency_thresholds", {})
    audit_results = n1.get("audit_results", [])
    a1 = audit_lookup(audit_results, "A1_REPRODUCE_STAGE64M_ACCOUNTING")
    a2_flag = audit_lookup(audit_results, "A2_NONPARAMETRIC_SIGN_AND_BOOTSTRAP_CHECK")
    a3 = audit_lookup(audit_results, "A3_SOURCE_LAG_STALENESS_SENSITIVITY")
    a4 = audit_lookup(audit_results, "A4_FEATURE_ABLATION_GOVERNANCE")
    a5 = audit_lookup(audit_results, "A5_BROKER_SPOT_ALIGNMENT_BLOCKER_LEDGER")

    a2 = n1.get("a2_nonparametric", {})
    metric_checks: List[Dict[str, Any]] = []

    def check_max(metric: str, threshold_key: str) -> bool:
        value = a2.get(metric)
        threshold = thresholds.get(threshold_key)
        ok = value is not None and threshold is not None and float(value) <= float(threshold)
        metric_checks.append({"metric": metric, "value": value, "threshold": f"<= {threshold}", "pass": ok})
        return ok

    def check_min(metric: str, threshold_key: str) -> bool:
        value = a2.get(metric)
        threshold = thresholds.get(threshold_key)
        ok = value is not None and threshold is not None and float(value) >= float(threshold)
        metric_checks.append({"metric": metric, "value": value, "threshold": f">= {threshold}", "pass": ok})
        return ok

    sign_ok = check_max("sign_test_one_sided_p_gt_benchmark_mean", "sign_test_one_sided_p_max")
    boot_p_ok = check_max("p_boot_excess_le_0", "bootstrap_p_excess_le_0_max")
    q05_ok = check_min("q05_excess_bps", "bootstrap_q05_excess_bps_min")
    iter_ok = check_min("iterations", "bootstrap_iterations_min")
    active_ok = check_min("candidate_active_days", "candidate_active_days_min")

    diagnostics_imply_a2_pass = bool(sign_ok and boot_p_ok and q05_ok and iter_ok and active_ok)
    stage64n1_a2_pass_flag = bool(a2_flag.get("pass"))
    pass_flag_inconsistent = bool((not stage64n1_a2_pass_flag) and diagnostics_imply_a2_pass)

    other_audits_pass = bool(a1.get("pass") and a3.get("pass") and a4.get("pass") and a5.get("pass"))

    target_survivor = n1.get("target_survivor", {})

    if pass_flag_inconsistent and other_audits_pass:
        decision = "DO_NOT_DOWNGRADE_SURVIVOR_A2_PASS_FLAG_RECONCILIATION_REQUIRED_NO_ORDER"
        status = "ROBUSTNESS_DECISION_MEMO_COMPLETE_NO_PROMOTION"
        executive = (
            "Stage64N1 reported A2 as failed, but its own non-parametric diagnostics are positive: "
            "the sign test passes, bootstrap probability of non-positive excess is within threshold, "
            "and the 5th percentile bootstrap excess remains above zero. The survivor must not be downgraded "
            "from this inconsistent pass flag. Reconcile the A2 gate logic first; no tuning or order is authorized."
        )
        next_allowed = "Stage64N1B_A2_NONPARAMETRIC_PASS_FLAG_RECONCILIATION_NO_ORDER"
        survivor_status = "HELD_PENDING_A2_RECONCILIATION"
    elif other_audits_pass and stage64n1_a2_pass_flag:
        decision = "ROBUSTNESS_AUDIT_CONFIRMED_CONTINUE_TO_REPLICATION_ALIGNMENT_DECISION_NO_ORDER"
        status = "ROBUSTNESS_DECISION_MEMO_COMPLETE_NO_PROMOTION"
        executive = (
            "All Stage64N1 audit flags and diagnostics pass. The survivor remains research-only and may continue "
            "to replication/alignment decision work; no order path is authorized."
        )
        next_allowed = "Stage64N2B_REPLICATION_AND_ALIGNMENT_DECISION_NO_ORDER"
        survivor_status = "ROBUSTNESS_CONFIRMED_RESEARCH_ONLY"
    else:
        decision = "DOWNGRADE_OR_KILL_SURVIVOR_ROBUSTNESS_NOT_CONFIRMED_NO_ORDER"
        status = "ROBUSTNESS_DECISION_MEMO_COMPLETE_NO_PROMOTION"
        executive = (
            "Stage64N1 robustness was not confirmed and no internal A2 pass-flag inconsistency was detected. "
            "The survivor should be downgraded or killed; no tuning, rescue filtering, or order path is authorized."
        )
        next_allowed = "Stage64N3_DOWNGRADE_KILL_OR_THESIS_REDESIGN_MEMO_NO_ORDER"
        survivor_status = "DOWNGRADE_OR_KILL_RESEARCH_ONLY"

    audit_state_review = []
    for row in [a1, a2_flag, a3, a4, a5]:
        interp = row.get("headline", "")
        if row.get("audit_id") == "A2_NONPARAMETRIC_SIGN_AND_BOOTSTRAP_CHECK" and pass_flag_inconsistent:
            interp = "Stage64N1 pass flag conflicts with positive A2 diagnostics; reconcile implementation before downgrade."
        audit_state_review.append({
            "audit_id": row.get("audit_id"),
            "stage64n1_pass": bool(row.get("pass")),
            "n2_interpretation": interp,
        })

    decision_matrix = [
        {
            "path": "Corrected survivor",
            "status": survivor_status,
            "decision": "Hold survivor as research-only until the next allowed audit/decision step; no promotion.",
            "allowed_next": next_allowed,
        },
        {
            "path": "A2 non-parametric diagnostics",
            "status": "INCONSISTENT_PASS_FLAG" if pass_flag_inconsistent else ("PASS" if stage64n1_a2_pass_flag else "FAIL"),
            "decision": "Do not retune; use only reconciliation or downgrade logic based on predeclared metrics.",
            "allowed_next": "A2 reconciliation only" if pass_flag_inconsistent else "Follow N2 decision",
        },
        {
            "path": "Order / EA / paper-live / live",
            "status": "HARD_BLOCKED",
            "decision": "NO_GO",
            "allowed_next": "None",
        },
    ]

    summary: Dict[str, Any] = {
        "stage": cfg.get("stage"),
        "status": status,
        "decision": decision,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_order": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "validation_allowed_for_order_or_promotion": False,
        "generated_utc": utc_now(),
        "root": str(root),
        "inputs": {
            "config": str(config_path),
            "stage64n1_summary": str(n1_path),
        },
        "target_survivor": target_survivor,
        "stage64n1_decision": n1.get("decision"),
        "audit_state_review": audit_state_review,
        "a2_consistency_review": {
            "stage64n1_a2_pass_flag": stage64n1_a2_pass_flag,
            "diagnostics_imply_a2_pass": diagnostics_imply_a2_pass,
            "pass_flag_inconsistent_with_diagnostics": pass_flag_inconsistent,
            "thresholds": thresholds,
            "metric_checks": metric_checks,
            "raw_a2_nonparametric": a2,
        },
        "decision_matrix": decision_matrix,
        "executive_conclusion": executive,
        "next_allowed_step": next_allowed,
        "hard_blocks": cfg.get("hard_blocks", []),
        "outputs": {
            "summary_json": str(out_dir / "stage64n2_robustness_downgrade_or_reconciliation_decision_summary.json"),
            "report_md": str(out_dir / "stage64n2_robustness_downgrade_or_reconciliation_decision_report.md"),
            "a2_consistency_checks_csv": str(out_dir / "stage64n2_a2_consistency_checks.csv"),
            "decision_matrix_csv": str(out_dir / "stage64n2_decision_matrix.csv"),
        },
    }

    write_json(out_dir / "stage64n2_robustness_downgrade_or_reconciliation_decision_summary.json", summary)
    (out_dir / "stage64n2_robustness_downgrade_or_reconciliation_decision_report.md").write_text(build_report(summary), encoding="utf-8")
    write_csv(out_dir / "stage64n2_a2_consistency_checks.csv", metric_checks)
    write_csv(out_dir / "stage64n2_decision_matrix.csv", decision_matrix)

    print(json.dumps({
        "status": summary["status"],
        "decision": summary["decision"],
        "next_allowed_step": summary["next_allowed_step"],
        "pass_flag_inconsistent_with_diagnostics": pass_flag_inconsistent,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
