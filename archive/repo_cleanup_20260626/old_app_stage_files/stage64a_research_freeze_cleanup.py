#!/usr/bin/env python3
"""
Stage64A Research Freeze + Cleanup + Active/Archive Map + Experiment Ledger Skeleton.

This stage is intentionally non-mutating with respect to prior research state DBs, shadow
signals, MT5 files, and execution harness artifacts. It writes a freeze memo, an
active/archive/reference-only map, and an experiment ledger skeleton for later multiple-
testing accounting.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

UTC = dt.timezone.utc

DEFAULT_MAP_ROWS: List[Dict[str, Any]] = [
    {
        "stage_id": "Stage64",
        "component": "Daily/Weekly Macro-Regime Gold System",
        "role": "ACTIVE_PRIMARY",
        "decision": "NEW_MAIN_PROGRAM",
        "allowed_actions": "thesis_specification, data_contract, historical_regime_validation",
        "forbidden_actions": "paper_order, paper_live, live, intraday_candidate_rescue",
        "reason": "Strategic pivot from candidate-first intraday scans to thesis-first gold trading system program.",
        "owner_next_step": "Stage64C macro-regime thesis specification",
    },
    {
        "stage_id": "Stage64A",
        "component": "Research freeze, cleanup map, experiment ledger skeleton",
        "role": "ACTIVE_GOVERNANCE",
        "decision": "EXECUTE_NOW",
        "allowed_actions": "write_freeze_memo, write_active_archive_map, write_experiment_ledger_skeleton",
        "forbidden_actions": "state_mutation, signal_generation, order_generation",
        "reason": "Reset governance before starting new thesis-first research program.",
        "owner_next_step": "Commit Stage64A artifacts and use as control point.",
    },
    {
        "stage_id": "Stage64B",
        "component": "Stage58B corrected statistical audit",
        "role": "ACTIVE_SECONDARY_AUDIT",
        "decision": "PLANNED_NO_PROMOTION",
        "allowed_actions": "variant_count_extraction, multiple_testing_penalty_estimate, corrected_audit",
        "forbidden_actions": "promotion, rescue_filtering, paper_order",
        "reason": "Stage58B remains only passive telemetry / corrected statistical audit, not main commercialization path.",
        "owner_next_step": "Run corrected audit after Stage64A is committed.",
    },
    {
        "stage_id": "Stage58B",
        "component": "Context-aware Stage51 true-forward shadow",
        "role": "PASSIVE_TELEMETRY_REFERENCE",
        "decision": "NO_PROMOTION_PASSIVE_ONLY",
        "allowed_actions": "independent_forward_telemetry, corrected_statistical_audit",
        "forbidden_actions": "old_gate_promotion, paper_order, paper_live, live, parameter_rescue",
        "reason": "Current quality is low-frequency and under-sampled; old gates are no longer sufficient for promotion.",
        "owner_next_step": "Feed Stage64B audit only; do not block Stage64C.",
    },
    {
        "stage_id": "Stage52",
        "component": "Raw volatility squeeze true-forward shadow",
        "role": "REFERENCE_CONTROL_ONLY",
        "decision": "FAILED_FORWARD_REFERENCE",
        "allowed_actions": "control_stream, regression_reference",
        "forbidden_actions": "promotion, paper_order, paper_live, live",
        "reason": "Forward quality deteriorated materially; raw path failed as a candidate promotion route.",
        "owner_next_step": "Keep only as benchmark/control against context filters.",
    },
    {
        "stage_id": "Stage61",
        "component": "Demo execution harness",
        "role": "EXECUTION_PLUMBING_REFERENCE",
        "decision": "REFERENCE_ONLY",
        "allowed_actions": "compile_reference, schema_reference, demo_plumbing_evidence",
        "forbidden_actions": "edge_claim, paper_live, live",
        "reason": "Demo execution proves parser/gate/order plumbing only, not trading edge.",
        "owner_next_step": "Keep AllowTrading false unless a future approved execution test explicitly requires otherwise.",
    },
    {
        "stage_id": "Stage62",
        "component": "Market-open ops runner",
        "role": "OPERATIONAL_SUPPORT_REFERENCE",
        "decision": "SUPPORT_ONLY",
        "allowed_actions": "data_import, context_refresh, report_generation",
        "forbidden_actions": "promotion_decision_without_stage64_governance, order_generation",
        "reason": "Useful orchestration layer but not a thesis or edge source.",
        "owner_next_step": "Run only if needed for passive telemetry or Stage64B audit inputs.",
    },
    {
        "stage_id": "Stage47",
        "component": "Liquidity sweep reversal",
        "role": "ARCHIVE_REFERENCE",
        "decision": "ARCHIVE_NO_RESCUE",
        "allowed_actions": "read_only_reference",
        "forbidden_actions": "new_filter_rescue, promotion",
        "reason": "Failed after loader fixes and broker/cost-aware review.",
        "owner_next_step": "No action.",
    },
    {
        "stage_id": "Stage49",
        "component": "Multi-timeframe trend persistence",
        "role": "ARCHIVE_REFERENCE",
        "decision": "ARCHIVE_NO_RESCUE",
        "allowed_actions": "read_only_reference",
        "forbidden_actions": "promotion, parameter_rescue",
        "reason": "Initial diagnostic did not survive hard audit.",
        "owner_next_step": "No action.",
    },
    {
        "stage_id": "Stage50",
        "component": "Session open range breakout",
        "role": "ARCHIVE_REFERENCE",
        "decision": "ARCHIVE_NO_RESCUE",
        "allowed_actions": "read_only_reference",
        "forbidden_actions": "promotion, parameter_rescue",
        "reason": "Hard audit pass count was zero.",
        "owner_next_step": "No action.",
    },
    {
        "stage_id": "Stage60",
        "component": "Context-aware parallel family scan",
        "role": "ARCHIVE_REFERENCE",
        "decision": "ARCHIVE_NO_RESCUE",
        "allowed_actions": "read_only_reference, multiple_testing_count_reference",
        "forbidden_actions": "promotion, cherry_pick_rescue",
        "reason": "Large candidate universe with no hard-audit survivors.",
        "owner_next_step": "Use in Stage64B multiple-testing penalty accounting.",
    },
    {
        "stage_id": "Stage38_to_Stage63",
        "component": "Prior intraday candidate-first research program",
        "role": "FROZEN_ARCHIVE_NAMESPACE",
        "decision": "FREEZE_NO_NEW_INTRADAY_SCAN",
        "allowed_actions": "audit_reference, ledger_counting, lessons_learned",
        "forbidden_actions": "new_intraday_megascan, old_gate_promotion, rescue_filtering",
        "reason": "Program-level pivot to macro-regime gold thesis.",
        "owner_next_step": "Keep artifacts available for review; do not expand this branch.",
    },
]

DEFAULT_LEDGER_ROWS: List[Dict[str, Any]] = [
    {
        "stage_id": "Stage38",
        "thesis_family": "COT/macro/GLD/composite overlays and early structural filters",
        "candidate_count": "multiple families; exact count to be extracted from reports",
        "variant_count": "unknown_exact",
        "selection_rule": "historical overlay and baseline diagnostics",
        "testing_multiple_penalty_group": "prior_intraday_macro_overlay",
        "decision": "ARCHIVE_REFERENCE",
        "decision_reason": "No stable promotion path; 2025 concentration and low-confidence effects.",
        "count_confidence": "LOW_NEEDS_EXTRACTION",
        "source_artifacts": "reports/stage38*",
        "next_audit_action": "Optional count extraction only",
    },
    {
        "stage_id": "Stage46",
        "thesis_family": "External context baseline failure branch",
        "candidate_count": "132",
        "variant_count": "132_or_more",
        "selection_rule": "strict/soft survivor gates",
        "testing_multiple_penalty_group": "prior_external_context",
        "decision": "ARCHIVE_REFERENCE",
        "decision_reason": "strict=0, soft=0; no promotion.",
        "count_confidence": "MEDIUM_FROM_PRIOR_SUMMARY",
        "source_artifacts": "reports/stage46*",
        "next_audit_action": "Confirm exact rows in Stage64B if needed",
    },
    {
        "stage_id": "Stage47",
        "thesis_family": "Liquidity sweep reversal",
        "candidate_count": "27",
        "variant_count": "27",
        "selection_rule": "loader-fixed broker-aware retest",
        "testing_multiple_penalty_group": "prior_intraday_reversal",
        "decision": "ARCHIVE_REFERENCE",
        "decision_reason": "No strict/soft survivors after corrected data handling.",
        "count_confidence": "MEDIUM_FROM_PRIOR_SUMMARY",
        "source_artifacts": "reports/stage47*",
        "next_audit_action": "Confirm final candidate CSV count",
    },
    {
        "stage_id": "Stage48_cost_aware",
        "thesis_family": "Broker/cost-aware liquidity sweep diagnostic",
        "candidate_count": "27",
        "variant_count": "27",
        "selection_rule": "stress/extreme cost-aware diagnostics",
        "testing_multiple_penalty_group": "prior_intraday_reversal_cost_aware",
        "decision": "ARCHIVE_REFERENCE",
        "decision_reason": "Cost-aware run produced no promotion-quality survivor.",
        "count_confidence": "MEDIUM_FROM_PRIOR_SUMMARY",
        "source_artifacts": "reports/stage48*",
        "next_audit_action": "Keep cost model as infrastructure reference",
    },
    {
        "stage_id": "Stage49",
        "thesis_family": "Multi-timeframe trend persistence",
        "candidate_count": "24 initial diagnostic survivors; hard-audit pass=0",
        "variant_count": "unknown_full_scan",
        "selection_rule": "hard audit after initial survivor screen",
        "testing_multiple_penalty_group": "prior_intraday_trend_persistence",
        "decision": "ARCHIVE_REFERENCE",
        "decision_reason": "Hard audit eliminated the branch.",
        "count_confidence": "MEDIUM_PARTIAL",
        "source_artifacts": "reports/stage49*",
        "next_audit_action": "Extract full variant count only if used for penalty accounting",
    },
    {
        "stage_id": "Stage50",
        "thesis_family": "Session open range breakout",
        "candidate_count": "96",
        "variant_count": "96",
        "selection_rule": "session/open-range hard audit",
        "testing_multiple_penalty_group": "prior_session_breakout",
        "decision": "ARCHIVE_REFERENCE",
        "decision_reason": "Hard-audit pass count=0.",
        "count_confidence": "MEDIUM_FROM_PRIOR_SUMMARY",
        "source_artifacts": "reports/stage50*",
        "next_audit_action": "Confirm exact candidate CSV count",
    },
    {
        "stage_id": "Stage51",
        "thesis_family": "Volatility squeeze breakout",
        "candidate_count": "12 hard-audit pass candidates",
        "variant_count": "full scan count unknown; selected=12",
        "selection_rule": "hard audit, then forward shadow",
        "testing_multiple_penalty_group": "prior_volatility_squeeze",
        "decision": "SOURCE_REFERENCE_ONLY",
        "decision_reason": "Raw forward branch later failed; context branch remains passive watch.",
        "count_confidence": "MEDIUM_SELECTED_ONLY",
        "source_artifacts": "reports/stage51*",
        "next_audit_action": "Extract full scan variant count for Stage64B",
    },
    {
        "stage_id": "Stage52",
        "thesis_family": "Raw volatility squeeze true-forward shadow",
        "candidate_count": "12",
        "variant_count": "12 selected from Stage51",
        "selection_rule": "true-forward shadow gates",
        "testing_multiple_penalty_group": "prior_volatility_squeeze_forward",
        "decision": "FAILED_FORWARD_REFERENCE_ONLY",
        "decision_reason": "Latest known forward evidence deteriorated; all raw candidates negative in latest audit snapshot.",
        "count_confidence": "HIGH_SELECTED_COUNT",
        "source_artifacts": "reports/stage52_forward_shadow, reports/stage53_forward_shadow_prep",
        "next_audit_action": "Reference/control only; no promotion accounting beyond failed branch",
    },
    {
        "stage_id": "Stage58A",
        "thesis_family": "Context-aware Stage51 regime audit",
        "candidate_count": "100 pass rows in candidate file; selected to Stage58B=4",
        "variant_count": "100_or_more",
        "selection_rule": "context/regime filter audit",
        "testing_multiple_penalty_group": "prior_context_filtering",
        "decision": "AUDIT_SOURCE_REFERENCE",
        "decision_reason": "Selected candidates feed Stage58B passive telemetry; not promotion by itself.",
        "count_confidence": "MEDIUM_FROM_STAGE59_META",
        "source_artifacts": "reports/stage58_context_aware_stage51*",
        "next_audit_action": "Stage64B must count full candidate universe conservatively",
    },
    {
        "stage_id": "Stage58B",
        "thesis_family": "Context-aware Stage51 true-forward shadow",
        "candidate_count": "4",
        "variant_count": "selected=4; parent universe>=100",
        "selection_rule": "passive forward telemetry; old promotion gates deprecated",
        "testing_multiple_penalty_group": "prior_context_forward_shadow",
        "decision": "PASSIVE_TELEMETRY_AND_CORRECTED_AUDIT_ONLY",
        "decision_reason": "Positive but low-frequency/under-sampled; no longer main commercialization path.",
        "count_confidence": "HIGH_SELECTED_COUNT_LOW_PARENT_COUNT",
        "source_artifacts": "reports/stage58_context_forward_shadow, reports/stage59_context_forward_gates",
        "next_audit_action": "Stage64B corrected statistical audit with multiple-testing penalty",
    },
    {
        "stage_id": "Stage60",
        "thesis_family": "Context-aware parallel family scan",
        "candidate_count": "1539",
        "variant_count": "1539",
        "selection_rule": "parallel scan and hard audit",
        "testing_multiple_penalty_group": "prior_context_megascan",
        "decision": "ARCHIVE_REFERENCE",
        "decision_reason": "No hard-audit pass candidates despite large search space.",
        "count_confidence": "HIGH_FROM_PRIOR_SUMMARY",
        "source_artifacts": "reports/stage60_context_aware_family_scan*",
        "next_audit_action": "Include in multiple-testing penalty denominator",
    },
    {
        "stage_id": "Stage61",
        "thesis_family": "Demo execution harness / order plumbing",
        "candidate_count": "not_applicable",
        "variant_count": "not_applicable",
        "selection_rule": "demo-only order path test",
        "testing_multiple_penalty_group": "execution_plumbing_not_edge",
        "decision": "REFERENCE_ONLY",
        "decision_reason": "Proves plumbing only, not edge.",
        "count_confidence": "HIGH_NA",
        "source_artifacts": "mql5/Experts, reports/stage61*",
        "next_audit_action": "No trading inference allowed",
    },
    {
        "stage_id": "Stage64C",
        "thesis_family": "Daily/Weekly Macro-Regime Gold Thesis",
        "candidate_count": "0_not_started",
        "variant_count": "0_not_started",
        "selection_rule": "thesis-first design before scan",
        "testing_multiple_penalty_group": "new_macro_regime_program",
        "decision": "NEW_ACTIVE_PROGRAM",
        "decision_reason": "Strategic pivot from intraday candidate-first research to macro-regime thesis-first program.",
        "count_confidence": "HIGH_NOT_STARTED",
        "source_artifacts": "to_be_created_in_stage64C",
        "next_audit_action": "Define data contract, lag policy, regime labels, validation framework",
    },
]


def utc_now() -> str:
    return dt.datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def format_table(rows: List[Dict[str, Any]], fields: List[str]) -> str:
    out = []
    out.append("| " + " | ".join(fields) + " |")
    out.append("|" + "|".join(["---"] * len(fields)) + "|")
    for row in rows:
        out.append("| " + " | ".join(str(row.get(field, "")).replace("|", "/") for field in fields) + " |")
    return "\n".join(out)


def build_freeze_memo(generated_utc: str, map_rows: List[Dict[str, Any]], ledger_rows: List[Dict[str, Any]]) -> str:
    active_rows = [r for r in map_rows if "ACTIVE" in str(r.get("role", ""))]
    passive_rows = [r for r in map_rows if "PASSIVE" in str(r.get("role", "")) or "REFERENCE" in str(r.get("role", ""))]
    return f"""# Stage64A Research Freeze + Cleanup Memo

Generated UTC: `{generated_utc}`

## Decision

Stage64A freezes the previous intraday candidate-first research program and establishes the operational map for the new thesis-first Gold / XAUUSD program.

Primary decision:

`RESEARCH_FREEZE_ACTIVE_ARCHIVE_MAP_AND_EXPERIMENT_LEDGER_SKELETON_COMPLETE_NO_PROMOTION`

## Non-negotiable freeze rules

- No new intraday candidate scans are authorized from Stage38-Stage63 branches.
- No rescue filtering, context tweaking, or parameter tweaking is authorized for failed branches.
- Stage52 raw volatility squeeze is failed forward reference/control only.
- Stage58B context-aware path is passive telemetry / corrected statistical audit only.
- Stage61 demo execution is plumbing reference only and does not prove edge.
- No paper-order, paper-live, or live trading is authorized.
- Stage64C Daily/Weekly Macro-Regime Gold Thesis is the new active research path.

## Active components

{format_table(active_rows, ["stage_id", "component", "role", "decision", "owner_next_step"])}

## Passive/archive/reference components

{format_table(passive_rows, ["stage_id", "component", "role", "decision", "reason"])}

## Multiple-testing accounting intent

The experiment ledger created by this stage is a skeleton for later conservative multiple-testing accounting. Counts marked as unknown or partial must be corrected in Stage64B before any statistical claim is made about Stage58B or related context-aware candidates.

Key penalty groups that must not be ignored:

- prior_intraday_macro_overlay
- prior_external_context
- prior_intraday_reversal
- prior_intraday_trend_persistence
- prior_session_breakout
- prior_volatility_squeeze
- prior_context_filtering
- prior_context_megascan

## Status

`NO_PROMOTION_NO_ORDER_NON_MUTATING_GOVERNANCE_STAGE_COMPLETE`
"""


def build_report(generated_utc: str, summary: Dict[str, Any]) -> str:
    return f"""# Stage64A Research Freeze + Cleanup Report

Generated UTC: `{generated_utc}`

## Status

- stage: `Stage64A_RESEARCH_FREEZE_CLEANUP_LEDGER_NO_PROMOTION`
- status: `{summary['status']}`
- promotion: `NO_GO`
- paper_order: `NO_GO`
- paper_live: `NO_GO`
- live: `NO_GO`
- mutation_mode: `{summary['mutation_mode']}`

## What this stage produced

1. Research freeze memo.
2. Active / archive / reference-only map.
3. Experiment ledger skeleton for candidate/variant/thesis-family accounting.
4. Multiple-testing penalty group placeholders.

## Strategic effect

The prior candidate-first intraday program is frozen. Stage52 raw is no longer a promotion path. Stage58B is not promoted; it remains only passive telemetry and a corrected statistical-audit target. The active research route is Stage64C: Daily/Weekly Macro-Regime Gold Thesis.

## Output files

- `{summary['outputs']['freeze_memo']}`
- `{summary['outputs']['active_archive_map_csv']}`
- `{summary['outputs']['active_archive_map_json']}`
- `{summary['outputs']['experiment_ledger_csv']}`
- `{summary['outputs']['experiment_ledger_json']}`
- `{summary['outputs']['summary_json']}`

## Control statement

This stage does not move, delete, or rewrite prior research artifacts. Cleanup is implemented as governance classification and ledger initialization. Physical archiving can be done later only after the map is reviewed and committed.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage64A research freeze and cleanup map generator")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--config", default="configs/stage64a_research_freeze_cleanup.json")
    parser.add_argument("--out", default="reports/stage64a_research_freeze_cleanup")
    args = parser.parse_args()

    repo_root = Path(args.root).resolve()
    config_path = (repo_root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    out_dir = (repo_root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    config = read_json(config_path)

    mutation_mode = str(config.get("mutation_mode", "report_only_no_state_mutation"))
    if mutation_mode != "report_only_no_state_mutation":
        raise SystemExit("Stage64A refuses to run with any mutation mode other than report_only_no_state_mutation")

    generated_utc = utc_now()
    map_rows = config.get("active_archive_map", DEFAULT_MAP_ROWS)
    ledger_rows = config.get("experiment_ledger_skeleton", DEFAULT_LEDGER_ROWS)

    out_dir.mkdir(parents=True, exist_ok=True)

    map_fields = ["stage_id", "component", "role", "decision", "allowed_actions", "forbidden_actions", "reason", "owner_next_step"]
    ledger_fields = [
        "stage_id", "thesis_family", "candidate_count", "variant_count", "selection_rule",
        "testing_multiple_penalty_group", "decision", "decision_reason", "count_confidence",
        "source_artifacts", "next_audit_action"
    ]

    active_archive_map_csv = out_dir / "stage64a_active_archive_reference_map.csv"
    active_archive_map_json = out_dir / "stage64a_active_archive_reference_map.json"
    ledger_csv = out_dir / "stage64a_experiment_ledger_skeleton.csv"
    ledger_json = out_dir / "stage64a_experiment_ledger_skeleton.json"
    freeze_memo = out_dir / "stage64a_research_freeze_memo.md"
    report_md = out_dir / "stage64a_research_freeze_cleanup_report.md"
    summary_json = out_dir / "stage64a_research_freeze_cleanup_summary.json"

    write_csv(active_archive_map_csv, map_rows, map_fields)
    write_json(active_archive_map_json, {"generated_utc": generated_utc, "rows": map_rows})
    write_csv(ledger_csv, ledger_rows, ledger_fields)
    write_json(ledger_json, {"generated_utc": generated_utc, "rows": ledger_rows})
    freeze_memo.write_text(build_freeze_memo(generated_utc, map_rows, ledger_rows), encoding="utf-8")

    summary = {
        "stage": "Stage64A_RESEARCH_FREEZE_CLEANUP_LEDGER_NO_PROMOTION",
        "status": "RESEARCH_FREEZE_CLEANUP_MAP_LEDGER_COMPLETE_NO_PROMOTION",
        "decision": "FREEZE_PRIOR_INTRADAY_PROGRAM_STAGE58B_PASSIVE_STAGE64C_ACTIVE",
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_order": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "mutation_mode": mutation_mode,
        "root": str(repo_root),
        "config": str(config_path),
        "out": str(out_dir),
        "counts": {
            "active_archive_map_rows": len(map_rows),
            "experiment_ledger_rows": len(ledger_rows),
            "active_roles": sum(1 for r in map_rows if "ACTIVE" in str(r.get("role", ""))),
            "archive_or_reference_roles": sum(1 for r in map_rows if "ARCHIVE" in str(r.get("role", "")) or "REFERENCE" in str(r.get("role", ""))),
        },
        "frozen_rules": [
            "NO_NEW_INTRADAY_SCAN",
            "NO_RESCUE_FILTERING",
            "NO_OLD_GATE_PROMOTION",
            "NO_PAPER_ORDER",
            "NO_PAPER_LIVE",
            "NO_LIVE",
        ],
        "outputs": {
            "freeze_memo": str(freeze_memo.relative_to(repo_root) if freeze_memo.is_relative_to(repo_root) else freeze_memo),
            "active_archive_map_csv": str(active_archive_map_csv.relative_to(repo_root) if active_archive_map_csv.is_relative_to(repo_root) else active_archive_map_csv),
            "active_archive_map_json": str(active_archive_map_json.relative_to(repo_root) if active_archive_map_json.is_relative_to(repo_root) else active_archive_map_json),
            "experiment_ledger_csv": str(ledger_csv.relative_to(repo_root) if ledger_csv.is_relative_to(repo_root) else ledger_csv),
            "experiment_ledger_json": str(ledger_json.relative_to(repo_root) if ledger_json.is_relative_to(repo_root) else ledger_json),
            "report_md": str(report_md.relative_to(repo_root) if report_md.is_relative_to(repo_root) else report_md),
            "summary_json": str(summary_json.relative_to(repo_root) if summary_json.is_relative_to(repo_root) else summary_json),
        },
        "next_allowed_step": "RUN_STAGE64B_CORRECTED_STATISTICAL_AUDIT_AND_STAGE64C_MACRO_REGIME_THESIS_SPEC_NO_PROMOTION",
        "generated_utc": generated_utc,
    }
    report_md.write_text(build_report(generated_utc, summary), encoding="utf-8")
    write_json(summary_json, summary)

    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "decision": summary["decision"],
        "outputs": summary["outputs"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
