#!/usr/bin/env python3
"""Stage64N3 - Corrected Survivor Replication and Alignment Decision (No Order).

Decision memo only. Does not run validation, generate signals, connect to broker,
or authorize paper/live execution.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List

STAGE = "Stage64N3_CORRECTED_SURVIVOR_REPLICATION_AND_ALIGNMENT_DECISION_NO_ORDER"
EXPECTED_N1B_DECISION = "A2_PASS_FLAG_RECONCILED_ROBUSTNESS_AUDIT_PASS_STAGE64N3_ALLOWED_NO_ORDER"
DECISION_CONTINUE = "SURVIVOR_HELD_FOR_REPLICATION_AND_ALIGNMENT_AUDIT_DESIGN_NO_ORDER"
DECISION_BLOCKED = "STAGE64N3_INPUTS_BLOCKED_NO_ORDER"

HARD_BLOCKS = [
    "NO_PAPER_ORDER",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_BROKER_CONNECTION",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE64N3",
    "NO_HISTORICAL_EVENT_FILTER_FROM_FORWARD_ONLY_GOVERNANCE",
    "NO_POST_HOC_EVENT_EXCLUSION",
    "NO_REDUCED_SCOPE_RETEST",
    "NO_RESCUE_FILTERING",
    "NO_NEW_INTRADAY_SCAN",
    "NO_PROMOTION_FROM_SINGLE_STAGE64M_PASS",
    "NO_COMMERCIALIZATION_WITHOUT_BROKER_SPOT_ALIGNMENT",
]


def now_utc() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise ValueError(f"JSON root is not object: {path}")
    return obj


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def write_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def rel_or_abs(root: Path, p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else root / path


def build_decision(root: Path, config: Dict[str, Any], out_dir: Path) -> Dict[str, Any]:
    n1b_path = rel_or_abs(root, config.get(
        "stage64n1b_summary",
        "reports/stage64n1b_a2_nonparametric_reconciliation/stage64n1b_a2_nonparametric_reconciliation_summary.json",
    ))
    n1b = load_json(n1b_path)

    target = n1b.get("target_survivor") or {}
    n1b_decision = str(n1b.get("decision", ""))
    n1b_status = str(n1b.get("status", ""))
    reconciled_all = bool(n1b.get("reconciled_all_audits_pass", False))
    validation_run_performed = bool(n1b.get("validation_run_performed", False))
    n1b_hard_blocks = list(n1b.get("hard_blocks") or [])

    input_ok = (
        n1b_decision == EXPECTED_N1B_DECISION
        and reconciled_all
        and not validation_run_performed
        and str(n1b.get("promotion", "NO_GO")) == "NO_GO"
        and str(n1b.get("paper_order", "NO_GO")) == "NO_GO"
        and str(n1b.get("live", "NO_GO")) == "NO_GO"
    )

    replication_requirements = [
        {
            "requirement_id": "R1_IMMUTABLE_REPRODUCTION_PACKAGE",
            "status": "REQUIRED_NEXT",
            "purpose": "Freeze the exact Stage64K dataset, Stage64L rules, Stage64M accounting, and Stage64N1B reconciled audit state into a reproducible replication bundle.",
            "pass_condition": "A separate runner can reproduce the survivor decision from immutable inputs without using reports as source-of-truth.",
            "failure_action": "Do not continue; fix provenance/accounting only, no tuning.",
        },
        {
            "requirement_id": "R2_INDEPENDENT_IMPLEMENTATION_REPLICATION",
            "status": "REQUIRED_NEXT",
            "purpose": "Recompute the H1/h120 survivor from the raw lag-safe dataset with a minimal independent implementation path.",
            "pass_condition": "Active days, excess vs B1, corrected significance, split/year concentration, and robustness checks reproduce within tolerance.",
            "failure_action": "Invalidate or downgrade survivor; no rescue filtering.",
        },
        {
            "requirement_id": "R3_BROKER_SPOT_ALIGNMENT_DESIGN",
            "status": "REQUIRED_BEFORE_BROKER_CLAIM",
            "purpose": "Design the broker/spot D1 alignment audit that must be passed before any broker XAUUSD validation or commercialization claim.",
            "pass_condition": "Alignment data contract and pass/fail gates are predeclared before any broker claim.",
            "failure_action": "Keep survivor research-only; no broker/paper/live path.",
        },
        {
            "requirement_id": "R4_FORWARD_ONLY_EVENT_GOVERNANCE_LEDGER",
            "status": "RETAIN_BLOCKER",
            "purpose": "Keep historical event-calendar features excluded; retain event calendar only as forward blackout/risk governance after later validation.",
            "pass_condition": "No historical event-filter or post-hoc event exclusion is introduced.",
            "failure_action": "Hard governance violation; stop path.",
        },
        {
            "requirement_id": "R5_NO_ORDER_GOVERNANCE",
            "status": "HARD_BLOCK",
            "purpose": "Prevent any paper/live/EA/broker connection from a single Stage64M pass and reconciled N1B audit.",
            "pass_condition": "All downstream stages remain no-order until external replication, broker/spot alignment, and later governance gates pass.",
            "failure_action": "Hard stop governance violation.",
        },
    ]

    if input_ok:
        decision = DECISION_CONTINUE
        status = "REPLICATION_ALIGNMENT_DECISION_COMPLETE_NO_PROMOTION"
        next_allowed = "Stage64N4_REPLICATION_AND_ALIGNMENT_AUDIT_DESIGN_NO_ORDER"
        executive = (
            "The corrected survivor remains research-only after A2 reconciliation. "
            "It may continue only to a replication/alignment audit design stage. "
            "No order, broker connection, paper-live, live, EA promotion, or commercialization claim is authorized."
        )
    else:
        decision = DECISION_BLOCKED
        status = "REPLICATION_ALIGNMENT_DECISION_BLOCKED_NO_PROMOTION"
        next_allowed = "RETURN_TO_STAGE64N1B_OR_STAGE64N2_RECONCILIATION_NO_ORDER"
        executive = (
            "Stage64N3 inputs are not sufficient to hold the survivor for replication/alignment design. "
            "Return to reconciliation/accounting; do not tune, promote, or place orders."
        )

    decision_matrix = [
        {
            "path": "Corrected survivor after N1B",
            "status": "HELD_RESEARCH_ONLY" if input_ok else "BLOCKED_BY_INPUTS",
            "decision": "Continue only to replication/alignment audit design." if input_ok else "Return to reconciliation/accounting.",
            "allowed_next": next_allowed,
        },
        {
            "path": "Broker/spot alignment",
            "status": "REQUIRED_BEFORE_COMMERCIALIZATION",
            "decision": "Broker XAUUSD claims remain blocked until alignment audit is designed and passed.",
            "allowed_next": "Stage64N4 design only; no broker connection.",
        },
        {
            "path": "Event calendar",
            "status": "FORWARD_ONLY_GOVERNANCE",
            "decision": "Historical event-calendar feature/filter remains forbidden.",
            "allowed_next": "Forward-only governance ledger only, after later validation.",
        },
        {
            "path": "Order / EA / paper-live / live",
            "status": "HARD_BLOCKED",
            "decision": "NO_GO",
            "allowed_next": "None",
        },
    ]

    summary = {
        "stage": STAGE,
        "status": status,
        "decision": decision,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_order": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "validation_allowed_for_order_or_promotion": False,
        "validation_run_performed": False,
        "generated_utc": now_utc(),
        "root": str(root),
        "inputs": {
            "config": str(rel_or_abs(root, config.get("_config_path", "configs/stage64n3_corrected_survivor_replication_alignment_decision.json"))),
            "stage64n1b_summary": str(n1b_path),
        },
        "input_checks": {
            "stage64n1b_status": n1b_status,
            "stage64n1b_decision": n1b_decision,
            "expected_stage64n1b_decision": EXPECTED_N1B_DECISION,
            "stage64n1b_decision_ok": n1b_decision == EXPECTED_N1B_DECISION,
            "reconciled_all_audits_pass": reconciled_all,
            "stage64n1b_validation_run_performed": validation_run_performed,
            "n1b_no_promotion_or_order_flags_ok": str(n1b.get("promotion", "NO_GO")) == "NO_GO" and str(n1b.get("paper_order", "NO_GO")) == "NO_GO" and str(n1b.get("live", "NO_GO")) == "NO_GO",
            "input_ok": input_ok,
        },
        "target_survivor": target,
        "reconciled_audit_results": n1b.get("reconciled_audit_results") or [],
        "replication_alignment_requirements": replication_requirements,
        "decision_matrix": decision_matrix,
        "event_calendar_policy": "Historical event-calendar archive is absent and remains excluded from historical validation; forward-only governance may be retained only for future operational blackout/risk control after later validation.",
        "broker_alignment_policy": "Broker/spot D1 alignment remains required before any commercialization or broker XAUUSD validation claim. Stage64N3 does not authorize broker connection.",
        "stage64n1b_hard_blocks_retained": n1b_hard_blocks,
        "executive_conclusion": executive,
        "next_allowed_step": next_allowed,
        "hard_blocks": HARD_BLOCKS,
        "outputs": {
            "summary_json": str(out_dir / "stage64n3_corrected_survivor_replication_alignment_decision_summary.json"),
            "report_md": str(out_dir / "stage64n3_corrected_survivor_replication_alignment_decision_report.md"),
            "replication_requirements_csv": str(out_dir / "stage64n3_replication_alignment_requirements.csv"),
            "decision_matrix_csv": str(out_dir / "stage64n3_decision_matrix.csv"),
        },
    }
    return summary


def write_report(path: Path, summary: Dict[str, Any]) -> None:
    reqs = summary.get("replication_alignment_requirements") or []
    matrix = summary.get("decision_matrix") or []
    checks = summary.get("input_checks") or {}
    target = summary.get("target_survivor") or {}

    lines: List[str] = []
    lines.append("# Stage64N3 - Corrected Survivor Replication and Alignment Decision (No Order)")
    lines.append("")
    lines.append(f"Generated UTC: `{summary.get('generated_utc')}`")
    lines.append("")
    lines.append("## Status")
    lines.append("")
    for k in ["status", "decision", "promotion", "paper_order", "paper_live", "live", "validation_allowed_for_order_or_promotion"]:
        lines.append(f"- {k}: `{summary.get(k)}`")
    lines.append("")
    lines.append("## Executive conclusion")
    lines.append("")
    lines.append(str(summary.get("executive_conclusion", "")))
    lines.append("")
    lines.append("## Input checks")
    lines.append("")
    lines.append("| check | value |")
    lines.append("|---|---:|")
    for k, v in checks.items():
        lines.append(f"| `{k}` | `{v}` |")
    lines.append("")
    lines.append("## Target survivor")
    lines.append("")
    for k, v in target.items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")
    lines.append("## Replication and alignment requirements")
    lines.append("")
    lines.append("| requirement_id | status | purpose | pass_condition | failure_action |")
    lines.append("|---|---|---|---|---|")
    for r in reqs:
        lines.append(
            f"| `{r.get('requirement_id')}` | `{r.get('status')}` | {r.get('purpose')} | {r.get('pass_condition')} | {r.get('failure_action')} |"
        )
    lines.append("")
    lines.append("## Decision matrix")
    lines.append("")
    lines.append("| path | status | decision | allowed_next |")
    lines.append("|---|---|---|---|")
    for r in matrix:
        lines.append(f"| `{r.get('path')}` | `{r.get('status')}` | {r.get('decision')} | {r.get('allowed_next')} |")
    lines.append("")
    lines.append("## Governance")
    lines.append("")
    lines.append(str(summary.get("event_calendar_policy", "")))
    lines.append("")
    lines.append(str(summary.get("broker_alignment_policy", "")))
    lines.append("")
    lines.append("## Hard blocks")
    lines.append("")
    for b in summary.get("hard_blocks") or []:
        lines.append(f"- `{b}`")
    lines.append("")
    lines.append("## Next allowed step")
    lines.append("")
    lines.append(f"`{summary.get('next_allowed_step')}`")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    config_path = Path(args.config).resolve() if Path(args.config).is_absolute() else (root / args.config).resolve()
    config = load_json(config_path)
    config["_config_path"] = str(config_path)
    out_dir = Path(args.out).resolve() if Path(args.out).is_absolute() else (root / args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = build_decision(root, config, out_dir)
    write_json(out_dir / "stage64n3_corrected_survivor_replication_alignment_decision_summary.json", summary)
    write_report(out_dir / "stage64n3_corrected_survivor_replication_alignment_decision_report.md", summary)
    write_csv(
        out_dir / "stage64n3_replication_alignment_requirements.csv",
        summary.get("replication_alignment_requirements") or [],
        ["requirement_id", "status", "purpose", "pass_condition", "failure_action"],
    )
    write_csv(
        out_dir / "stage64n3_decision_matrix.csv",
        summary.get("decision_matrix") or [],
        ["path", "status", "decision", "allowed_next"],
    )
    print(summary["decision"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
