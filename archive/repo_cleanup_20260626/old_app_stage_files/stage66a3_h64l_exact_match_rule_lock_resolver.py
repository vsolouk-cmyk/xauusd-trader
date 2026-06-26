#!/usr/bin/env python3
"""Stage66A3 exact-match H64L rule-lock resolver.

Purpose:
- Resolve Stage66A2's MULTIPLE_RECONCILIATION_MATCHES case without threshold tuning.
- Promote only a single exact reconstruction match (active_event_count_with_horizon == expected).
- Write a proposed H64L v2 rule lock and a Stage66A reconciled config.
- No broker connection, no order path, no promotion.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List


def canonical_sha256(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_report(path: Path, summary: Dict[str, Any]) -> None:
    lines = [
        "# Stage66A3 H64L Exact-Match Rule-Lock Resolver",
        "",
        "## Decision",
        "",
        f"- status: `{summary.get('status')}`",
        f"- decision: `{summary.get('decision')}`",
        f"- selected_variant_id: `{summary.get('selected_variant_id')}`",
        f"- exact_match_count: `{summary.get('exact_match_count')}`",
        f"- tolerance_match_count: `{summary.get('tolerance_match_count')}`",
        "",
        "## Rationale",
        "",
        "Stage66A2 returned multiple tolerance-level reconciliation matches, but only one variant exactly reproduced the Stage64R active-event count.",
        "This resolver does not tune thresholds. It applies the pre-declared stricter tie-break: exact active-event reconstruction beats tolerance-only near matches.",
        "",
        "## Selected rule additions",
        "",
    ]
    for c in summary.get("selected_extra_conditions", []):
        lines.append(f"- `{c.get('field')} {c.get('operator')} {c.get('threshold')}` — {c.get('meaning')}")
    lines.extend([
        "",
        "## Output artifacts",
        "",
    ])
    for k, v in summary.get("output_artifacts", {}).items():
        lines.append(f"- `{k}`: `{v}`")
    lines.extend([
        "",
        "## Hard blocks",
        "",
    ])
    for b in summary.get("hard_blocks", []):
        lines.append(f"- `{b}`")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage66a3_h64l_exact_match_rule_lock_resolver.json")
    ap.add_argument("--out", default="reports/stage66a3_h64l_exact_match_rule_lock_resolver")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cfg_path = (root / args.config).resolve()
    out_dir = (root / args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = read_json(cfg_path)

    summary_path = root / cfg["stage66a2_summary_path"]
    matrix_path = root / cfg["stage66a2_variant_matrix_path"]
    base_rule_path = root / cfg["base_locked_rule_path"]
    existing_a_config_path = root / cfg["existing_stage66a_config_path"]

    a2_summary = read_json(summary_path)
    matrix = read_json(matrix_path)
    base_rule = read_json(base_rule_path)
    existing_a_config = read_json(existing_a_config_path)

    expected_count = int(cfg["expected_stage64r_candidate_active_days"])
    selected_variant_id = cfg.get("selected_variant_id")
    strict_exact_required = bool(cfg.get("strict_exact_match_required", True))
    allow_multiple_tolerance_matches = bool(cfg.get("allow_multiple_tolerance_matches", True))

    hard_blocks = [
        "NO_PAPER_ORDER",
        "NO_EA_PROMOTION",
        "NO_PAPER_LIVE",
        "NO_LIVE",
        "NO_BROKER_CONNECTION",
        "NO_THRESHOLD_TUNING",
        "NO_RESCUE_FILTERING",
        "NO_PROMOTION_FROM_RECONCILIATION_ONLY",
    ]

    tolerance_matches = [v for v in matrix if v.get("within_tolerance") is True]
    exact_matches = [v for v in matrix if int(v.get("active_event_count_with_horizon", -999999)) == expected_count]

    decision = None
    status = None
    selected = None
    issues: List[str] = []

    if a2_summary.get("decision") not in {
        "MULTIPLE_RECONCILIATION_MATCHES_REQUIRE_MANUAL_RULE_LOCK_REVIEW",
        "UNIQUE_RECONCILIATION_MATCH_WRITE_PROPOSED_RULE_LOCK_V2_NO_PROMOTION",
    }:
        issues.append(f"Unexpected Stage66A2 decision: {a2_summary.get('decision')}")

    if strict_exact_required and len(exact_matches) != 1:
        issues.append(f"Expected exactly one exact reconstruction match; found {len(exact_matches)}")

    if not allow_multiple_tolerance_matches and len(tolerance_matches) > 1:
        issues.append(f"Multiple tolerance matches are not allowed by config; found {len(tolerance_matches)}")

    if selected_variant_id:
        selected_candidates = [v for v in exact_matches if v.get("variant_id") == selected_variant_id]
        if len(selected_candidates) != 1:
            issues.append(f"Configured selected_variant_id is not the unique exact match: {selected_variant_id}")
        else:
            selected = selected_candidates[0]
    elif len(exact_matches) == 1:
        selected = exact_matches[0]

    if selected is not None:
        if float(selected.get("difference_pct_vs_expected", 999.0)) != 0.0:
            issues.append("Selected variant is not a zero-difference exact match.")
        if int(selected.get("active_event_count_with_horizon")) != expected_count:
            issues.append("Selected variant active_event_count_with_horizon does not equal expected count.")

    if issues:
        status = "STAGE66A3_STOP_NO_RULE_WRITTEN"
        decision = "STOP_RULE_LOCK_REVIEW_REQUIRES_STAGE64R_SOURCE_AUDIT"
    else:
        status = "STAGE66A3_COMPLETE_RULE_LOCK_V2_WRITTEN_NO_PROMOTION"
        decision = "EXACT_RECONCILIATION_MATCH_WRITE_RULE_LOCK_V2_NO_PROMOTION"

    output_artifacts: Dict[str, str] = {}

    if selected is not None and not issues:
        payload = copy.deepcopy(base_rule["rule_lock_payload"])
        existing_conditions = payload.get("conditions", [])
        existing_keys = {(c.get("field"), c.get("operator"), float(c.get("threshold", 0))) for c in existing_conditions}
        added = []
        for c in selected.get("extra_conditions", []):
            key = (c.get("field"), c.get("operator"), float(c.get("threshold", 0)))
            if key not in existing_keys:
                existing_conditions.append(c)
                added.append(c)
        payload["conditions"] = existing_conditions
        payload["version"] = cfg.get("output_rule_version", "v2_stage66a3_exact_reconciled")
        payload["description"] = (
            "Locked H64L rule reconciled by Stage66A3 exact-match resolver. "
            "Adds only the unique zero-difference Stage66A2 conditions required to reproduce Stage64R active count. "
            "No threshold tuning; no order authorization."
        )
        payload["locked_from"] = {
            "stage": "Stage66A2/Stage66A3 reconstruction reconciliation",
            "base_rule_path": cfg["base_locked_rule_path"],
            "base_rule_sha256": base_rule.get("rule_sha256"),
            "stage66a2_decision": a2_summary.get("decision"),
            "selected_variant_id": selected.get("variant_id"),
            "selected_variant_rule_sha256": selected.get("rule_sha256"),
            "expected_stage64r_candidate_active_days": expected_count,
            "selected_active_event_count_with_horizon": selected.get("active_event_count_with_horizon"),
            "difference_pct_vs_expected": selected.get("difference_pct_vs_expected"),
            "tie_break_policy": "unique exact active-event-count match beats tolerance-only near matches",
        }
        payload["hard_blocks"] = sorted(set(payload.get("hard_blocks", []) + hard_blocks))
        new_rule = {
            "rule_lock_payload": payload,
            "rule_sha256": canonical_sha256(payload),
        }
        out_rule_path = root / cfg["output_locked_rule_path"]
        write_json(out_rule_path, new_rule)
        output_artifacts["locked_rule_v2"] = str(out_rule_path.relative_to(root))

        reconciled_cfg = copy.deepcopy(existing_a_config)
        reconciled_cfg["locked_rule_path"] = cfg["output_locked_rule_path"]
        reconciled_cfg["stage"] = "Stage66A_H64L_CONCENTRATION_AUDIT_RECONCILED_V2"
        reconciled_cfg["reconciliation_source"] = {
            "stage": "Stage66A3",
            "selected_variant_id": selected.get("variant_id"),
            "selected_rule_sha256": selected.get("rule_sha256"),
            "rule_lock_v2_sha256": new_rule["rule_sha256"],
            "tie_break_policy": "unique exact active-event-count match beats tolerance-only near matches",
        }
        out_a_config_path = root / cfg["output_stage66a_config_path"]
        write_json(out_a_config_path, reconciled_cfg)
        output_artifacts["stage66a_reconciled_config"] = str(out_a_config_path.relative_to(root))

    run_summary = {
        "stage": "Stage66A3_H64L_EXACT_MATCH_RULE_LOCK_RESOLVER",
        "status": status,
        "decision": decision,
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "root": str(root),
        "expected_stage64r_candidate_active_days": expected_count,
        "a2_decision": a2_summary.get("decision"),
        "tolerance_match_count": len(tolerance_matches),
        "exact_match_count": len(exact_matches),
        "selected_variant_id": selected.get("variant_id") if selected else None,
        "selected_extra_conditions": selected.get("extra_conditions", []) if selected else [],
        "selected_active_event_count_with_horizon": selected.get("active_event_count_with_horizon") if selected else None,
        "selected_difference_pct_vs_expected": selected.get("difference_pct_vs_expected") if selected else None,
        "selected_mean_return_bps": selected.get("mean_return_bps") if selected else None,
        "selected_positive_event_share": selected.get("positive_event_share") if selected else None,
        "selected_max_year_share": selected.get("max_year_share") if selected else None,
        "selected_rule_sha256": selected.get("rule_sha256") if selected else None,
        "near_tolerance_matches": [
            {
                "variant_id": v.get("variant_id"),
                "active_event_count_with_horizon": v.get("active_event_count_with_horizon"),
                "difference_pct_vs_expected": v.get("difference_pct_vs_expected"),
                "condition_count": v.get("condition_count"),
            }
            for v in tolerance_matches
            if selected is None or v.get("variant_id") != selected.get("variant_id")
        ],
        "issues": issues,
        "output_artifacts": output_artifacts,
        "hard_blocks": hard_blocks,
        "next_step": (
            "Rerun Stage66A with the reconciled v2 config, then rerun Stage66F. "
            "Do not run Stage66C until Stage66F maps the new A/B combination to a paper-simulation-ready decision."
            if not issues
            else "Inspect Stage64R source artifacts before changing any rule lock."
        ),
    }
    write_json(out_dir / "stage66a3_h64l_exact_match_rule_lock_resolver_summary.json", run_summary)
    write_report(out_dir / "stage66a3_h64l_exact_match_rule_lock_resolver_report.md", run_summary)
    print(json.dumps({"decision": decision, "status": status, "selected_variant_id": run_summary["selected_variant_id"]}, ensure_ascii=False))
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
