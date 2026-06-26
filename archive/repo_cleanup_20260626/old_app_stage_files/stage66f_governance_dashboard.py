#!/usr/bin/env python3
"""Stage66F idempotent governance dashboard.

Regenerate after every Stage66 A/B/C/D run. No orders. Decision matrix is
pre-registered before seeing Package1 results.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, Optional

from stage66_common_h64l import read_json, write_json, write_report


def load_optional(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return read_json(path)
    except Exception as e:
        return {"status": "READ_ERROR", "error": str(e), "path": str(path)}


def classify_a(decision: Optional[str]) -> str:
    if not decision:
        return "A_MISSING"
    if decision.startswith("KILL") or "RECONSTRUCTION_MISMATCH" in decision:
        return "A_KILL"
    if "PASS_FAST" in decision:
        return "A_PASS_FAST"
    if "PASS_SMALL_SIZE" in decision:
        return "A_PASS_SMALL_SIZE_ONLY"
    if "LOW_FREQUENCY" in decision:
        return "A_PASS_LOW_FREQUENCY_ONLY"
    if decision.startswith("FAIL"):
        return "A_FAIL"
    return "A_OTHER"


def classify_b(decision: Optional[str]) -> str:
    if not decision:
        return "B_MISSING"
    if decision.startswith("KILL") or "LOOKAHEAD" in decision:
        return "B_KILL"
    if "PASS_FAST" in decision:
        return "B_PASS_FAST"
    if "PASS_LOW_FREQUENCY" in decision:
        return "B_PASS_LOW_FREQUENCY_ONLY"
    if "INSUFFICIENT" in decision:
        return "B_INSUFFICIENT"
    if decision.startswith("FAIL"):
        return "B_FAIL"
    return "B_OTHER"


# Pre-registered A x B matrix. This intentionally refuses to promote from one good track alone.
DECISION_MATRIX = {
    ("A_KILL", "ANY"): "STOP_FIX_RECONSTRUCTION_OR_RULE_LOCK",
    ("ANY", "B_KILL"): "STOP_FIX_LOOKAHEAD_OR_ROLLING_REPLAY",
    ("A_PASS_FAST", "B_PASS_FAST"): "PAPER_SIM_READY_BAND_B_NO_ORDER_PACKAGE2",
    ("A_PASS_FAST", "B_PASS_LOW_FREQUENCY_ONLY"): "PAPER_SIM_READY_BAND_A_NO_ORDER_LOW_FREQUENCY_WARNING",
    ("A_PASS_FAST", "B_INSUFFICIENT"): "PAPER_SIM_READY_BAND_A_NO_ORDER_B_NEEDS_MORE_ORIGINS",
    ("A_PASS_SMALL_SIZE_ONLY", "B_PASS_FAST"): "PAPER_SIM_READY_BAND_A_NO_ORDER_CONCENTRATION_WARNING",
    ("A_PASS_SMALL_SIZE_ONLY", "B_PASS_LOW_FREQUENCY_ONLY"): "PAPER_SIM_READY_BAND_A_NO_ORDER_CONCENTRATION_AND_FREQUENCY_WARNINGS",
    ("A_PASS_SMALL_SIZE_ONLY", "B_INSUFFICIENT"): "PAPER_SIM_DELAY_OR_BAND_A_RESEARCH_ONLY_UNTIL_B_CLARIFIED",
    ("A_PASS_LOW_FREQUENCY_ONLY", "B_PASS_FAST"): "PAPER_SIM_READY_BAND_A_NO_ORDER_LOW_FREQUENCY_WARNING",
    ("A_PASS_LOW_FREQUENCY_ONLY", "B_PASS_LOW_FREQUENCY_ONLY"): "NO_FAST_DEPLOYMENT_BACKGROUND_PLUS_THESIS_D_REQUIRED",
    ("A_PASS_LOW_FREQUENCY_ONLY", "B_INSUFFICIENT"): "NO_FAST_DEPLOYMENT_THESIS_D_REQUIRED",
    ("A_FAIL", "ANY"): "STOP_OR_REDESIGN_H64L",
    ("ANY", "B_FAIL"): "STOP_OR_REDESIGN_H64L_FORWARD_REPLAY_FAILED",
}


def matrix_decision(a_class: str, b_class: str) -> str:
    for key in [(a_class, b_class), (a_class, "ANY"), ("ANY", b_class)]:
        if key in DECISION_MATRIX:
            return DECISION_MATRIX[key]
    if a_class == "A_MISSING" or b_class == "B_MISSING":
        return "PACKAGE1_INCOMPLETE_RUN_MISSING_TRACKS"
    return "REVIEW_REQUIRED_UNMAPPED_COMBINATION"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--out", default="reports/stage66f_governance_dashboard")
    args = p.parse_args()
    root = Path(args.root).resolve()
    out_dir = Path(args.out) if Path(args.out).is_absolute() else root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "integrity": load_optional(root / "reports/stage66_data_integrity_crosscheck/stage66_data_integrity_crosscheck_summary.json"),
        "stage66a": load_optional(root / "reports/stage66a_h64l_concentration_audit/stage66a_h64l_concentration_audit_summary.json"),
        "stage66b": load_optional(root / "reports/stage66b_h64l_rolling_origin_replay/stage66b_h64l_rolling_origin_replay_summary.json"),
        "stage65b_background": load_optional(root / "reports/stage65b_forward_shadow_daily_ops/stage65b_forward_shadow_daily_ops_summary.json"),
    }
    a_dec = data["stage66a"].get("decision") if isinstance(data["stage66a"], dict) else None
    b_dec = data["stage66b"].get("decision") if isinstance(data["stage66b"], dict) else None
    a_cls = classify_a(a_dec)
    b_cls = classify_b(b_dec)
    gate2 = matrix_decision(a_cls, b_cls)

    integrity_status = data["integrity"].get("status") if isinstance(data["integrity"], dict) else "MISSING"
    if integrity_status == "FAIL":
        package_decision = "STOP_FIX_DATA_INTEGRITY_FIRST"
    else:
        package_decision = gate2

    summary = {
        "stage": "Stage66F_GOVERNANCE_DASHBOARD",
        "generated_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "root": str(root),
        "status": "STAGE66F_DASHBOARD_REGENERATED_NO_PROMOTION",
        "decision": package_decision,
        "hard_blocks": ["NO_PAPER_ORDER", "NO_EA_PROMOTION", "NO_PAPER_LIVE", "NO_LIVE", "NO_BROKER_CONNECTION", "NO_ORDER_AUTHORIZATION_FROM_STAGE66", "NO_THRESHOLD_TUNING"],
        "regeneration_rule": "Run Stage66F immediately after every Stage66 A/B/C/D execution.",
        "classes": {"stage66a_class": a_cls, "stage66b_class": b_cls, "integrity_status": integrity_status},
        "track_decisions": {"stage66a": a_dec, "stage66b": b_dec},
        "decision_matrix_version": "v1_pre_registered_2026_06_25",
        "decision_matrix": {f"{k[0]} x {k[1]}": v for k, v in DECISION_MATRIX.items()},
        "inputs_loaded": {k: isinstance(v, dict) and v is not None for k, v in data.items()},
        "raw_track_summaries": data,
    }
    write_json(out_dir / "stage66f_governance_dashboard_summary.json", summary)
    sections = [
        ("Decision", f"- status: `{summary['status']}`\n- decision: `{summary['decision']}`"),
        ("Classes", json.dumps(summary["classes"], ensure_ascii=False, indent=2)),
        ("Track decisions", json.dumps(summary["track_decisions"], ensure_ascii=False, indent=2)),
        ("Regeneration rule", summary["regeneration_rule"]),
        ("Decision matrix", json.dumps(summary["decision_matrix"], ensure_ascii=False, indent=2)),
    ]
    write_report(out_dir / "stage66f_governance_dashboard_report.md", "Stage66F Governance Dashboard", sections)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
