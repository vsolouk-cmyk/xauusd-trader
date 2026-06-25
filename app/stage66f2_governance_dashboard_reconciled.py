#!/usr/bin/env python3
"""
Stage66F2 Governance Dashboard Reconciled.

Purpose:
- Regenerate Stage66 governance from explicit input paths.
- Prefer the reconciled Stage66A v2 concentration audit after Stage66A3 exact-match rule-lock resolution.
- Do not authorize paper orders, broker connections, EA promotion, paper-live, or live trading.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


HARD_BLOCKS = [
    "NO_PAPER_ORDER",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_BROKER_CONNECTION",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE66",
    "NO_THRESHOLD_TUNING",
    "NO_PROMOTION_FROM_DASHBOARD_ONLY",
]


DECISION_MATRIX = {
    "ANY x B_FAIL": "STOP_OR_REDESIGN_H64L_FORWARD_REPLAY_FAILED",
    "ANY x B_KILL": "STOP_FIX_LOOKAHEAD_OR_ROLLING_REPLAY",
    "A_FAIL x ANY": "STOP_OR_REDESIGN_H64L",
    "A_KILL x ANY": "STOP_FIX_RECONSTRUCTION_OR_RULE_LOCK",
    "A_PASS_FAST x B_INSUFFICIENT": "PAPER_SIM_READY_BAND_A_NO_ORDER_B_NEEDS_MORE_ORIGINS",
    "A_PASS_FAST x B_PASS_FAST": "PAPER_SIM_READY_BAND_B_NO_ORDER_PACKAGE2",
    "A_PASS_FAST x B_PASS_LOW_FREQUENCY_ONLY": "PAPER_SIM_READY_BAND_A_NO_ORDER_LOW_FREQUENCY_WARNING",
    "A_PASS_LOW_FREQUENCY_ONLY x B_INSUFFICIENT": "NO_FAST_DEPLOYMENT_THESIS_D_REQUIRED",
    "A_PASS_LOW_FREQUENCY_ONLY x B_PASS_FAST": "PAPER_SIM_READY_BAND_A_NO_ORDER_LOW_FREQUENCY_WARNING",
    "A_PASS_LOW_FREQUENCY_ONLY x B_PASS_LOW_FREQUENCY_ONLY": "NO_FAST_DEPLOYMENT_BACKGROUND_PLUS_THESIS_D_REQUIRED",
    "A_PASS_SMALL_SIZE_ONLY x B_INSUFFICIENT": "PAPER_SIM_DELAY_OR_BAND_A_RESEARCH_ONLY_UNTIL_B_CLARIFIED",
    "A_PASS_SMALL_SIZE_ONLY x B_PASS_FAST": "PAPER_SIM_READY_BAND_A_NO_ORDER_CONCENTRATION_WARNING",
    "A_PASS_SMALL_SIZE_ONLY x B_PASS_LOW_FREQUENCY_ONLY": "PAPER_SIM_READY_BAND_A_NO_ORDER_CONCENTRATION_AND_FREQUENCY_WARNINGS",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path, required: bool) -> Optional[Dict[str, Any]]:
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Required input not found: {path}")
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def classify_integrity(summary: Optional[Dict[str, Any]]) -> str:
    if not summary:
        return "MISSING"
    status = str(summary.get("status", "")).upper()
    decision = str(summary.get("decision", "")).upper()
    if status == "PASS" or decision == "RUN_STAGE66A_B_ALLOWED":
        return "PASS"
    return "FAIL"


def classify_stage66a(summary: Optional[Dict[str, Any]]) -> str:
    if not summary:
        return "A_MISSING"
    status = str(summary.get("status", "")).upper()
    decision = str(summary.get("decision", "")).upper()
    reconstruction = summary.get("reconstruction", {}) or {}
    reconstruction_status = str(reconstruction.get("status", "")).upper()

    if "KILL" in decision or "KILL" in status or reconstruction_status == "FAIL":
        return "A_KILL"
    if "FAIL" in decision or "FAIL" in status:
        return "A_FAIL"
    if decision.startswith("PASS_FAST") or "PASS_FAST" in decision:
        return "A_PASS_FAST"
    if "PASS_LOW_FREQUENCY" in decision:
        return "A_PASS_LOW_FREQUENCY_ONLY"
    if "PASS_SMALL_SIZE" in decision:
        return "A_PASS_SMALL_SIZE_ONLY"
    if "PASS" in decision or "COMPLETE" in status:
        # Conservative fallback: complete without explicit fast pass should not become Band B.
        return "A_PASS_SMALL_SIZE_ONLY"
    return "A_FAIL"


def classify_stage66b(summary: Optional[Dict[str, Any]]) -> str:
    if not summary:
        return "B_MISSING"
    status = str(summary.get("status", "")).upper()
    decision = str(summary.get("decision", "")).upper()
    no_lookahead = summary.get("no_lookahead", {}) or {}
    breach_count = int(no_lookahead.get("breach_count", 0) or 0)

    if breach_count > 0 or "LOOKAHEAD" in decision and "BREACH" in decision:
        return "B_KILL"
    if "KILL" in decision or "KILL" in status:
        return "B_KILL"
    if "FAIL" in decision or "FAIL" in status:
        return "B_FAIL"
    if "PASS_FAST" in decision:
        return "B_PASS_FAST"
    if "LOW_FREQUENCY" in decision:
        return "B_PASS_LOW_FREQUENCY_ONLY"
    if "INSUFFICIENT" in decision:
        return "B_INSUFFICIENT"

    origin_stats = summary.get("origin_stats", {}) or {}
    signal_origin_count = int(origin_stats.get("signal_origin_count", 0) or 0)
    if signal_origin_count < 3:
        return "B_INSUFFICIENT"

    return "B_PASS_LOW_FREQUENCY_ONLY"


def matrix_decision(a_class: str, b_class: str) -> str:
    if b_class == "B_KILL":
        return DECISION_MATRIX["ANY x B_KILL"]
    if b_class == "B_FAIL":
        return DECISION_MATRIX["ANY x B_FAIL"]
    if a_class == "A_KILL":
        return DECISION_MATRIX["A_KILL x ANY"]
    if a_class == "A_FAIL":
        return DECISION_MATRIX["A_FAIL x ANY"]

    key = f"{a_class} x {b_class}"
    return DECISION_MATRIX.get(key, "STOP_UNMAPPED_CLASS_COMBINATION_REVIEW_REQUIRED")


def build_report(summary: Dict[str, Any]) -> str:
    classes = summary["classes"]
    lines = [
        "# Stage66F2 Governance Dashboard Reconciled",
        "",
        "## Decision",
        "",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- integrity_status: `{classes['integrity_status']}`",
        f"- stage66a_class: `{classes['stage66a_class']}`",
        f"- stage66b_class: `{classes['stage66b_class']}`",
        "",
        "## Input paths",
        "",
    ]
    for k, v in summary["input_paths"].items():
        lines.append(f"- {k}: `{v}`")
    lines += [
        "",
        "## Hard blocks",
        "",
    ]
    for block in summary["hard_blocks"]:
        lines.append(f"- `{block}`")
    lines += [
        "",
        "## Interpretation",
        "",
    ]
    if summary["decision"] == "PAPER_SIM_READY_BAND_B_NO_ORDER_PACKAGE2":
        lines.append("Stage66A reconciled and Stage66B replay both passed fast-path evidence checks. This unlocks Stage66C paper-execution simulator design only; it does not authorize any order, broker connection, EA promotion, paper-live, or live trading.")
    elif summary["decision"].startswith("PAPER_SIM_READY"):
        lines.append("The next allowed step is Stage66C paper-execution simulator design with the warning level reflected in the decision label. No order path is authorized.")
    else:
        lines.append("The next step is to fix the track named in the decision before proceeding. No paper simulator, order path, broker connection, or promotion is authorized.")
    lines += [
        "",
        "## Next step",
        "",
        summary["next_step"],
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    config_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    with config_path.open("r", encoding="utf-8") as f:
        cfg = json.load(f)

    def rp(key: str) -> Path:
        val = cfg[key]
        p = Path(val)
        return p if p.is_absolute() else root / p

    integrity_path = rp("integrity_summary_path")
    stage65b_path = rp("stage65b_background_summary_path")
    stage66a_path = rp("stage66a_summary_path")
    stage66b_path = rp("stage66b_summary_path")

    integrity = load_json(integrity_path, required=cfg.get("require_integrity", True))
    stage65b = load_json(stage65b_path, required=False)
    stage66a = load_json(stage66a_path, required=True)
    stage66b = load_json(stage66b_path, required=True)

    integrity_class = classify_integrity(integrity)
    a_class = classify_stage66a(stage66a)
    b_class = classify_stage66b(stage66b)

    if integrity_class != "PASS":
        decision = "STOP_FIX_DATA_INTEGRITY_FIRST"
    else:
        decision = matrix_decision(a_class, b_class)

    status = "STAGE66F2_DASHBOARD_REGENERATED_NO_PROMOTION"
    if decision.startswith("STOP"):
        next_step = "Fix the blocking Stage66 track identified by the decision; do not run Stage66C."
    elif decision == "PAPER_SIM_READY_BAND_B_NO_ORDER_PACKAGE2":
        next_step = "Build and run Stage66C paper-execution simulator using the reconciled H64L v2 rule-lock. No order, broker, EA, paper-live, or live path is authorized."
    else:
        next_step = "Build Stage66C paper-execution simulator only with the warning band shown in the decision. No order path is authorized."

    out_dir = Path(args.out)
    out_dir = out_dir if out_dir.is_absolute() else root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "stage": "Stage66F2_GOVERNANCE_DASHBOARD_RECONCILED",
        "status": status,
        "decision": decision,
        "generated_utc": utc_now(),
        "root": str(root),
        "config": str(config_path),
        "classes": {
            "integrity_status": integrity_class,
            "stage66a_class": a_class,
            "stage66b_class": b_class,
        },
        "input_paths": {
            "integrity_summary_path": str(integrity_path.relative_to(root)) if str(integrity_path).startswith(str(root)) else str(integrity_path),
            "stage65b_background_summary_path": str(stage65b_path.relative_to(root)) if str(stage65b_path).startswith(str(root)) else str(stage65b_path),
            "stage66a_summary_path": str(stage66a_path.relative_to(root)) if str(stage66a_path).startswith(str(root)) else str(stage66a_path),
            "stage66b_summary_path": str(stage66b_path.relative_to(root)) if str(stage66b_path).startswith(str(root)) else str(stage66b_path),
        },
        "inputs_loaded": {
            "integrity": integrity is not None,
            "stage65b_background": stage65b is not None,
            "stage66a": stage66a is not None,
            "stage66b": stage66b is not None,
        },
        "track_decisions": {
            "stage66a": stage66a.get("decision") if isinstance(stage66a, dict) else None,
            "stage66b": stage66b.get("decision") if isinstance(stage66b, dict) else None,
        },
        "stage66a_key_metrics": {
            "active_event_count": (stage66a.get("active_event_stats") or {}).get("active_event_count"),
            "mean_return_bps": (stage66a.get("active_event_stats") or {}).get("mean_return_bps"),
            "positive_event_share": (stage66a.get("active_event_stats") or {}).get("positive_event_share"),
            "episode_count": (stage66a.get("episode_stats") or {}).get("episode_count"),
            "positive_independent_episodes": (stage66a.get("episode_stats") or {}).get("positive_independent_episodes"),
            "max_episode_active_day_share": (stage66a.get("episode_stats") or {}).get("max_episode_active_day_share"),
            "reconstruction_status": (stage66a.get("reconstruction") or {}).get("status"),
            "reconstructed_active_event_count_with_horizon": (stage66a.get("reconstruction") or {}).get("reconstructed_active_event_count_with_horizon"),
            "expected_stage64r_candidate_active_days": (stage66a.get("reconstruction") or {}).get("expected_stage64r_candidate_active_days"),
            "reconstruction_difference_pct": (stage66a.get("reconstruction") or {}).get("difference_pct"),
        },
        "stage66b_key_metrics": {
            "independent_origin_count": (stage66b.get("origin_stats") or {}).get("independent_origin_count"),
            "signal_origin_count": (stage66b.get("origin_stats") or {}).get("signal_origin_count"),
            "positive_signal_origin_share": (stage66b.get("origin_stats") or {}).get("positive_signal_origin_share"),
            "mean_of_signal_origin_means_bps": (stage66b.get("origin_stats") or {}).get("mean_of_signal_origin_means_bps"),
            "no_lookahead_breach_count": (stage66b.get("no_lookahead") or {}).get("breach_count"),
        },
        "decision_matrix_version": "v2_reconciled_input_paths_2026_06_25",
        "decision_matrix": DECISION_MATRIX,
        "hard_blocks": HARD_BLOCKS,
        "next_step": next_step,
        "regeneration_rule": "Run Stage66F2 after Stage66A3 reconciled Stage66A and Stage66B; do not rely on legacy Stage66F if it still points to the old Stage66A output.",
    }

    summary_path = out_dir / "stage66f2_governance_dashboard_reconciled_summary.json"
    report_path = out_dir / "stage66f2_governance_dashboard_reconciled_report.md"

    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    report_path.write_text(build_report(summary), encoding="utf-8")

    print(json.dumps({
        "status": status,
        "decision": decision,
        "summary_path": str(summary_path),
        "report_path": str(report_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
