#!/usr/bin/env python3
"""
Stage64N1B - A2 non-parametric pass-flag reconciliation.

This script does not run a new validation scan and does not generate signals or orders.
It reconciles the Stage64N1 A2 pass flag against the Stage64N2 consistency review.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing JSON input: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=False)
        f.write("\n")


def write_csv(path: Path, rows: Iterable[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)


def as_float(value: Any, default: float = math.nan) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def audit_pass_map(stage64n1: Dict[str, Any]) -> Dict[str, bool]:
    out: Dict[str, bool] = {}
    for row in stage64n1.get("audit_results", []) or []:
        if isinstance(row, dict) and row.get("audit_id"):
            out[str(row["audit_id"])] = as_bool(row.get("pass"))
    return out


def target_matches(actual: Dict[str, Any], expected: Dict[str, Any]) -> bool:
    if not expected:
        return True
    return (
        str(actual.get("hypothesis_id")) == str(expected.get("hypothesis_id"))
        and as_int(actual.get("horizon_days")) == as_int(expected.get("horizon_days"))
        and str(actual.get("primary_benchmark_id")) == str(expected.get("primary_benchmark_id"))
    )


def get_a2_metrics(stage64n1: Dict[str, Any], stage64n2: Dict[str, Any]) -> Dict[str, Any]:
    review = stage64n2.get("a2_consistency_review", {}) or {}
    raw = review.get("raw_a2_nonparametric") or stage64n1.get("a2_nonparametric") or {}
    if not isinstance(raw, dict):
        raw = {}
    return raw


def reconcile_a2(metrics: Dict[str, Any], thresholds: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], bool]:
    checks: List[Dict[str, Any]] = []

    def add(metric: str, value: Any, threshold_text: str, passed: bool) -> None:
        checks.append({
            "metric": metric,
            "value": value,
            "threshold": threshold_text,
            "pass": bool(passed),
        })

    sign_p = as_float(metrics.get("sign_test_one_sided_p_gt_benchmark_mean"))
    sign_max = as_float(thresholds.get("sign_test_one_sided_p_gt_benchmark_mean_max", 0.05))
    add("sign_test_one_sided_p_gt_benchmark_mean", sign_p, f"<= {sign_max}", math.isfinite(sign_p) and sign_p <= sign_max)

    boot_p = as_float(metrics.get("p_boot_excess_le_0"))
    boot_max = as_float(thresholds.get("p_boot_excess_le_0_max", 0.05))
    add("p_boot_excess_le_0", boot_p, f"<= {boot_max}", math.isfinite(boot_p) and boot_p <= boot_max)

    q05 = as_float(metrics.get("q05_excess_bps"))
    q05_min = as_float(thresholds.get("q05_excess_bps_min", 0.0))
    add("q05_excess_bps", q05, f">= {q05_min}", math.isfinite(q05) and q05 >= q05_min)

    iterations = as_int(metrics.get("iterations"))
    iterations_min = as_int(thresholds.get("iterations_min", 1000))
    add("iterations", iterations, f">= {iterations_min}", iterations >= iterations_min)

    active_days = as_int(metrics.get("candidate_active_days"))
    active_min = as_int(thresholds.get("candidate_active_days_min", 120))
    add("candidate_active_days", active_days, f">= {active_min}", active_days >= active_min)

    return checks, all(row["pass"] for row in checks)


def render_report(summary: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Stage64N1B - A2 Non-Parametric Pass-Flag Reconciliation (No Order)")
    lines.append("")
    lines.append(f"Generated UTC: `{summary['generated_utc']}`")
    lines.append("")
    lines.append("## Status")
    lines.append("")
    for key in ["status", "decision", "promotion", "paper_order", "paper_live", "live", "validation_allowed_for_order_or_promotion"]:
        lines.append(f"- {key}: `{summary.get(key)}`")
    lines.append("")
    lines.append("## Executive conclusion")
    lines.append("")
    lines.append(summary["executive_conclusion"])
    lines.append("")
    lines.append("## Target survivor")
    lines.append("")
    target = summary.get("target_survivor", {})
    for key in ["hypothesis_id", "horizon_days", "primary_benchmark_id"]:
        lines.append(f"- {key}: `{target.get(key)}`")
    lines.append("")
    lines.append("## A2 reconciliation checks")
    lines.append("")
    lines.append("| metric | value | threshold | pass |")
    lines.append("|---|---:|---:|---:|")
    for row in summary.get("a2_reconciliation_checks", []):
        lines.append(f"| `{row['metric']}` | `{row['value']}` | `{row['threshold']}` | `{row['pass']}` |")
    lines.append("")
    lines.append("## Audit-state reconciliation")
    lines.append("")
    lines.append("| audit_id | stage64n1_pass | reconciled_pass | note |")
    lines.append("|---|---:|---:|---|")
    for row in summary.get("reconciled_audit_results", []):
        lines.append(f"| `{row['audit_id']}` | `{row['stage64n1_pass']}` | `{row['reconciled_pass']}` | {row['note']} |")
    lines.append("")
    lines.append("## Decision matrix")
    lines.append("")
    lines.append("| path | status | decision | allowed_next |")
    lines.append("|---|---|---|---|")
    for row in summary.get("decision_matrix", []):
        lines.append(f"| `{row['path']}` | `{row['status']}` | {row['decision']} | {row['allowed_next']} |")
    lines.append("")
    lines.append("## Hard blocks")
    lines.append("")
    for block in summary.get("hard_blocks", []):
        lines.append(f"- `{block}`")
    lines.append("")
    lines.append("## Next allowed step")
    lines.append("")
    lines.append(f"`{summary.get('next_allowed_step')}`")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage64N1B A2 pass-flag reconciliation")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--config", required=True, help="Config JSON path")
    parser.add_argument("--out", required=True, help="Output directory")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = root / config_path
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    config = load_json(config_path)
    inputs = config.get("inputs", {}) or {}
    n1_path = root / str(inputs.get("stage64n1_summary", ""))
    n2_path = root / str(inputs.get("stage64n2_summary", ""))
    stage64n1 = load_json(n1_path)
    stage64n2 = load_json(n2_path)

    expected_n2_decision = str(config.get("required_stage64n2_decision", ""))
    n2_decision_ok = not expected_n2_decision or stage64n2.get("decision") == expected_n2_decision

    expected_target = config.get("expected_target_survivor", {}) or {}
    target = stage64n2.get("target_survivor") or stage64n1.get("target_survivor") or {}
    target_ok = target_matches(target, expected_target)

    audit_map = audit_pass_map(stage64n1)
    metrics = get_a2_metrics(stage64n1, stage64n2)
    checks, diagnostics_imply_a2_pass = reconcile_a2(metrics, config.get("thresholds", {}) or {})

    n1_a2_flag = audit_map.get("A2_NONPARAMETRIC_SIGN_AND_BOOTSTRAP_CHECK", False)
    pass_flag_inconsistent = bool(diagnostics_imply_a2_pass and not n1_a2_flag)

    other_audits = [
        "A1_REPRODUCE_STAGE64M_ACCOUNTING",
        "A3_SOURCE_LAG_STALENESS_SENSITIVITY",
        "A4_FEATURE_ABLATION_GOVERNANCE",
        "A5_BROKER_SPOT_ALIGNMENT_BLOCKER_LEDGER",
    ]
    other_audits_pass = all(audit_map.get(x, False) for x in other_audits)

    reconciled_a2_pass = bool(n2_decision_ok and target_ok and diagnostics_imply_a2_pass)
    reconciled_all_audits_pass = bool(other_audits_pass and reconciled_a2_pass)

    reconciled_rows: List[Dict[str, Any]] = []
    for audit_id in ["A1_REPRODUCE_STAGE64M_ACCOUNTING", "A2_NONPARAMETRIC_SIGN_AND_BOOTSTRAP_CHECK", "A3_SOURCE_LAG_STALENESS_SENSITIVITY", "A4_FEATURE_ABLATION_GOVERNANCE", "A5_BROKER_SPOT_ALIGNMENT_BLOCKER_LEDGER"]:
        stage64n1_pass = audit_map.get(audit_id, False)
        if audit_id == "A2_NONPARAMETRIC_SIGN_AND_BOOTSTRAP_CHECK":
            reconciled_pass = reconciled_a2_pass
            note = "A2 pass flag reconciled from predeclared non-parametric metrics; no tuning or new validation scan."
        else:
            reconciled_pass = stage64n1_pass
            note = "Stage64N1 audit result retained."
        reconciled_rows.append({
            "audit_id": audit_id,
            "stage64n1_pass": stage64n1_pass,
            "reconciled_pass": bool(reconciled_pass),
            "note": note,
        })

    if reconciled_all_audits_pass:
        decision = "A2_PASS_FLAG_RECONCILED_ROBUSTNESS_AUDIT_PASS_STAGE64N3_ALLOWED_NO_ORDER"
        status = "A2_PASS_FLAG_RECONCILIATION_COMPLETE_NO_PROMOTION"
        next_allowed = str(config.get("next_allowed_if_reconciled"))
        conclusion = (
            "Stage64N1 marked A2 as failed, but Stage64N2 and the underlying non-parametric metrics show that A2 passes the "
            "predeclared sign/bootstrap thresholds. A2 is reconciled as pass for research-only audit accounting. This does not "
            "authorize promotion or orders; the survivor may continue only to the next no-order replication/alignment decision step."
        )
        survivor_status = "HELD_RESEARCH_ONLY_AFTER_A2_RECONCILIATION"
    else:
        decision = "A2_RECONCILIATION_NOT_RESOLVED_DOWNGRADE_OR_KILL_DECISION_REQUIRED_NO_ORDER"
        status = "A2_PASS_FLAG_RECONCILIATION_INCOMPLETE_NO_PROMOTION"
        next_allowed = str(config.get("next_allowed_if_not_reconciled"))
        conclusion = (
            "A2 reconciliation did not clear all required checks or another robustness audit is not passing. The survivor remains "
            "research-only and must move to downgrade/kill decision; no tuning or orders are authorized."
        )
        survivor_status = "HELD_OR_DOWNGRADE_PENDING"

    decision_matrix = [
        {
            "path": "Corrected survivor",
            "status": survivor_status,
            "decision": "Continue only through no-order governance/audit path; no promotion.",
            "allowed_next": next_allowed,
        },
        {
            "path": "A2 non-parametric pass flag",
            "status": "RECONCILED_PASS" if reconciled_a2_pass else "NOT_RECONCILED",
            "decision": "Use predeclared metrics only; no retuning, no replacement metric, no new scan.",
            "allowed_next": "No-order decision path only",
        },
        {
            "path": "Order / EA / paper-live / live",
            "status": "HARD_BLOCKED",
            "decision": "NO_GO",
            "allowed_next": "None",
        },
    ]

    summary = {
        "stage": config.get("stage", "Stage64N1B_A2_NONPARAMETRIC_PASS_FLAG_RECONCILIATION_NO_ORDER"),
        "status": status,
        "decision": decision,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_order": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "validation_allowed_for_order_or_promotion": False,
        "validation_run_performed": False,
        "generated_utc": utc_now(),
        "root": str(root),
        "inputs": {
            "config": str(config_path),
            "stage64n1_summary": str(n1_path),
            "stage64n2_summary": str(n2_path),
        },
        "target_survivor": target,
        "input_decisions": {
            "stage64n1_decision": stage64n1.get("decision"),
            "stage64n2_decision": stage64n2.get("decision"),
            "required_stage64n2_decision": expected_n2_decision,
            "stage64n2_decision_ok": n2_decision_ok,
            "target_ok": target_ok,
        },
        "a2_reconciliation": {
            "stage64n1_a2_pass_flag": n1_a2_flag,
            "diagnostics_imply_a2_pass": diagnostics_imply_a2_pass,
            "pass_flag_inconsistent_with_diagnostics": pass_flag_inconsistent,
            "reconciled_a2_pass": reconciled_a2_pass,
            "raw_metrics": metrics,
        },
        "a2_reconciliation_checks": checks,
        "other_audits_pass": other_audits_pass,
        "reconciled_all_audits_pass": reconciled_all_audits_pass,
        "reconciled_audit_results": reconciled_rows,
        "decision_matrix": decision_matrix,
        "executive_conclusion": conclusion,
        "next_allowed_step": next_allowed,
        "hard_blocks": config.get("hard_blocks", []),
        "outputs": {
            "summary_json": str(out_dir / "stage64n1b_a2_nonparametric_reconciliation_summary.json"),
            "report_md": str(out_dir / "stage64n1b_a2_nonparametric_reconciliation_report.md"),
            "a2_reconciliation_checks_csv": str(out_dir / "stage64n1b_a2_reconciliation_checks.csv"),
            "reconciled_audit_results_csv": str(out_dir / "stage64n1b_reconciled_audit_results.csv"),
        },
    }

    write_json(out_dir / "stage64n1b_a2_nonparametric_reconciliation_summary.json", summary)
    (out_dir / "stage64n1b_a2_nonparametric_reconciliation_report.md").write_text(render_report(summary), encoding="utf-8")
    write_csv(out_dir / "stage64n1b_a2_reconciliation_checks.csv", checks, ["metric", "value", "threshold", "pass"])
    write_csv(out_dir / "stage64n1b_reconciled_audit_results.csv", reconciled_rows, ["audit_id", "stage64n1_pass", "reconciled_pass", "note"])

    print(json.dumps({
        "status": status,
        "decision": decision,
        "next_allowed_step": next_allowed,
        "summary": str(out_dir / "stage64n1b_a2_nonparametric_reconciliation_summary.json"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
