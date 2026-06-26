#!/usr/bin/env python3
"""
Stage64N - Full-scope validation decision memo (no order).

Reads the Stage64M full-scope walk-forward validation summary and produces a
research-only decision memo. This stage does not run a validation scan, does not
produce signals, and does not authorize any order path.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List

STAGE = "Stage64N_FULL_SCOPE_VALIDATION_DECISION_MEMO_NO_ORDER"
STATUS = "FULL_SCOPE_VALIDATION_DECISION_MEMO_COMPLETE_NO_PROMOTION"
DECISION_CONTINUE = "CONTINUE_TO_CORRECTED_SURVIVOR_ROBUSTNESS_AUDIT_NO_ORDER"
DECISION_KILL = "KILL_FULL_SCOPE_VALIDATION_NO_CORRECTED_SURVIVOR_NO_ORDER"

HARD_BLOCKS = [
    "NO_PAPER_ORDER",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_BROKER_CONNECTION",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE64N",
    "NO_HISTORICAL_EVENT_FILTER_FROM_FORWARD_ONLY_GOVERNANCE",
    "NO_POST_HOC_EVENT_EXCLUSION",
    "NO_REDUCED_SCOPE_RETEST",
    "NO_RESCUE_FILTERING",
    "NO_NEW_INTRADAY_SCAN",
    "NO_PROMOTION_FROM_SINGLE_STAGE64M_PASS",
]


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def rel(root: Path, p: Path) -> str:
    try:
        return str(p.resolve().relative_to(root.resolve()))
    except Exception:
        return str(p)


def as_list(x: Any) -> List[Dict[str, Any]]:
    return x if isinstance(x, list) else []


def survivor_rows(stage64m: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = as_list(stage64m.get("corrected_survivors"))
    return [r for r in rows if isinstance(r, dict)]


def watch_rows(stage64m: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = as_list(stage64m.get("uncorrected_watch_only"))
    return [r for r in rows if isinstance(r, dict)]


def build_survivor_audit_plan(stage64m: Dict[str, Any]) -> List[Dict[str, Any]]:
    survivors = survivor_rows(stage64m)
    plan: List[Dict[str, Any]] = []

    for s in survivors:
        hid = s.get("hypothesis_id", "")
        horizon = s.get("horizon_days", "")
        plan.extend([
            {
                "audit_id": "A1_REPRODUCE_STAGE64M_ACCOUNTING",
                "hypothesis_id": hid,
                "horizon_days": horizon,
                "purpose": "Recompute active days, benchmark excess, split/year concentration, and corrected p from immutable Stage64K dataset and Stage64L design.",
                "pass_condition": "All Stage64M headline statistics reproduce within tolerance; no forbidden columns or event-calendar filters are detected.",
                "failure_action": "Invalidate survivor and return to decision memo; no tuning allowed.",
            },
            {
                "audit_id": "A2_NONPARAMETRIC_SIGN_AND_BOOTSTRAP_CHECK",
                "hypothesis_id": hid,
                "horizon_days": horizon,
                "purpose": "Check whether corrected edge remains positive under non-parametric / bootstrap-style robustness tests rather than only z-approximation.",
                "pass_condition": "Positive excess remains statistically non-fragile under predeclared resampling diagnostics.",
                "failure_action": "Downgrade to watch or kill; no promotion.",
            },
            {
                "audit_id": "A3_SOURCE_LAG_STALENESS_SENSITIVITY",
                "hypothesis_id": hid,
                "horizon_days": horizon,
                "purpose": "Audit impact of ETF and central-bank as-of lag/staleness on survivor activity and excess return.",
                "pass_condition": "Result is not dominated by stale ETF or stale central-bank observations and survives strict lag caps.",
                "failure_action": "Require source-lag redesign or kill full-scope thesis; no retuned rescue filters.",
            },
            {
                "audit_id": "A4_FEATURE_ABLATION_GOVERNANCE",
                "hypothesis_id": hid,
                "horizon_days": horizon,
                "purpose": "Verify that full-scope incremental sources add genuine information beyond the trend benchmark and reduced-scope macro reference.",
                "pass_condition": "Survivor remains interpretable as full-scope macro edge, not only trend/bull-drift repackaging.",
                "failure_action": "Classify as trend-reference artifact; no promotion.",
            },
            {
                "audit_id": "A5_BROKER_SPOT_ALIGNMENT_BLOCKER_LEDGER",
                "hypothesis_id": hid,
                "horizon_days": horizon,
                "purpose": "Maintain explicit blocker that COMEX/reference gold results cannot become broker XAUUSD claims until broker/spot alignment is complete.",
                "pass_condition": "No commercialization, broker validation, paper order, or live claim is made from Stage64M/Stage64N.",
                "failure_action": "Hard stop governance violation.",
            },
        ])
    return plan


def build_summary(root: Path, config_path: Path, out_dir: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    stage64m_path = root / cfg.get("stage64m_summary", "reports/stage64m_full_scope_walk_forward_validation_run/stage64m_full_scope_walk_forward_validation_run_summary.json")
    stage64m = read_json(stage64m_path)

    counts = stage64m.get("counts", {}) if isinstance(stage64m.get("counts"), dict) else {}
    corrected_survivors = survivor_rows(stage64m)
    uncorrected_watch = watch_rows(stage64m)
    has_corrected = len(corrected_survivors) > 0

    decision = DECISION_CONTINUE if has_corrected else DECISION_KILL
    next_allowed = "Stage64N1_CORRECTED_SURVIVOR_ROBUSTNESS_AUDIT_NO_ORDER" if has_corrected else "STOP_OR_THESIS_LEVEL_REDESIGN_NO_ORDER"

    decision_matrix = [
        {
            "path": "Stage64M corrected survivor",
            "status": "PRESENT" if has_corrected else "ABSENT",
            "decision": "Continue to stricter robustness audit; research-only, no order." if has_corrected else "Kill full-scope validation path; no promotion.",
            "allowed_next": next_allowed,
        },
        {
            "path": "Uncorrected watch candidates",
            "status": "WATCH_ONLY" if uncorrected_watch else "NONE",
            "decision": "Do not promote; may be retained only as diagnostic context for robustness audit." if uncorrected_watch else "No action.",
            "allowed_next": "Diagnostic reference only; no tuning or rescue filtering.",
        },
        {
            "path": "Event calendar",
            "status": "FORWARD_ONLY_GOVERNANCE",
            "decision": "Historical event-calendar features and post-hoc exclusions remain forbidden.",
            "allowed_next": "Future operational blackout governance only after later validation and only if known before event time.",
        },
        {
            "path": "Broker/spot alignment",
            "status": "REQUIRED_BEFORE_COMMERCIALIZATION",
            "decision": "Broker XAUUSD validation/commercialization claim remains blocked.",
            "allowed_next": "Acquire broker/spot D1 alignment before any commercialization or broker claim.",
        },
        {
            "path": "Order / EA / paper-live / live",
            "status": "HARD_BLOCKED",
            "decision": "NO_GO",
            "allowed_next": "None",
        },
    ]

    audit_plan = build_survivor_audit_plan(stage64m)
    summary_path = out_dir / "stage64n_full_scope_validation_decision_memo_summary.json"
    report_path = out_dir / "stage64n_full_scope_validation_decision_memo_report.md"
    decision_csv = out_dir / "stage64n_decision_matrix.csv"
    audit_csv = out_dir / "stage64n_survivor_audit_plan.csv"

    summary: Dict[str, Any] = {
        "stage": STAGE,
        "status": STATUS,
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
            "stage64m_summary": str(stage64m_path),
        },
        "stage64m_counts": counts,
        "corrected_survivor_count": len(corrected_survivors),
        "uncorrected_watch_only_count": len(uncorrected_watch),
        "corrected_survivors": corrected_survivors,
        "uncorrected_watch_only": uncorrected_watch,
        "decision_matrix": decision_matrix,
        "survivor_audit_plan": audit_plan,
        "event_calendar_policy": stage64m.get("event_calendar_policy", "Historical event-calendar features remain forbidden."),
        "broker_alignment_policy": stage64m.get("broker_alignment_policy", "Broker/spot alignment remains required before commercialization."),
        "executive_conclusion": (
            "Stage64M produced one corrected research-only survivor. Stage64N does not authorize promotion or orders; it allows only a stricter corrected-survivor robustness audit."
            if has_corrected else
            "Stage64M produced no corrected survivor. Full-scope validation path is killed unless redesigned at thesis level."
        ),
        "next_allowed_step": next_allowed,
        "hard_blocks": HARD_BLOCKS,
        "outputs": {
            "summary_json": str(summary_path),
            "report_md": str(report_path),
            "decision_matrix_csv": str(decision_csv),
            "survivor_audit_plan_csv": str(audit_csv),
        },
    }

    return summary


def write_report(path: Path, summary: Dict[str, Any]) -> None:
    lines: List[str] = []
    lines.append("# Stage64N - Full-Scope Validation Decision Memo (No Order)")
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
    lines.append(str(summary.get("executive_conclusion", "")))
    lines.append("")
    lines.append("## Stage64M evidence")
    lines.append("")
    counts = summary.get("stage64m_counts", {})
    for k in ["overall_result_rows", "split_result_rows", "candidate_decision_rows", "corrected_survivors", "uncorrected_watch_only"]:
        lines.append(f"- {k}: `{counts.get(k)}`")
    lines.append("")

    lines.append("## Corrected survivors")
    lines.append("")
    survivors = summary.get("corrected_survivors", [])
    if survivors:
        lines.append("| hypothesis_id | horizon | active_days | mean_bps | benchmark_mean_bps | excess_bps | p_corr | pos_splits | max_split_share | max_year_share | decision |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
        for s in survivors:
            lines.append(
                f"| `{s.get('hypothesis_id')}` | {s.get('horizon_days')} | {s.get('candidate_active_days')} | {s.get('candidate_mean_bps')} | {s.get('primary_benchmark_mean_bps')} | {s.get('mean_excess_vs_primary_benchmark_bps')} | {s.get('bonferroni_corrected_p')} | {s.get('positive_excess_splits_vs_primary_benchmark')} | {s.get('max_split_share_of_active_days')} | {s.get('max_year_share_of_active_days')} | `{s.get('decision')}` |"
            )
    else:
        lines.append("No corrected survivors.")
    lines.append("")

    lines.append("## Uncorrected watch only")
    lines.append("")
    watch = summary.get("uncorrected_watch_only", [])
    if watch:
        lines.append("| hypothesis_id | horizon | active_days | excess_bps | p_unc | p_corr | decision |")
        lines.append("|---|---:|---:|---:|---:|---:|---|")
        for s in watch:
            lines.append(
                f"| `{s.get('hypothesis_id')}` | {s.get('horizon_days')} | {s.get('candidate_active_days')} | {s.get('mean_excess_vs_primary_benchmark_bps')} | {s.get('one_sided_p_uncorrected_z_approx')} | {s.get('bonferroni_corrected_p')} | `{s.get('decision')}` |"
            )
    else:
        lines.append("No uncorrected watch candidates.")
    lines.append("")

    lines.append("## Decision matrix")
    lines.append("")
    lines.append("| path | status | decision | allowed_next |")
    lines.append("|---|---|---|---|")
    for row in summary.get("decision_matrix", []):
        lines.append(f"| `{row.get('path')}` | `{row.get('status')}` | {row.get('decision')} | {row.get('allowed_next')} |")
    lines.append("")

    lines.append("## Required survivor robustness audit")
    lines.append("")
    plan = summary.get("survivor_audit_plan", [])
    if plan:
        lines.append("| audit_id | hypothesis_id | horizon | purpose | pass_condition | failure_action |")
        lines.append("|---|---|---:|---|---|---|")
        for row in plan:
            lines.append(f"| `{row.get('audit_id')}` | `{row.get('hypothesis_id')}` | {row.get('horizon_days')} | {row.get('purpose')} | {row.get('pass_condition')} | {row.get('failure_action')} |")
    else:
        lines.append("No audit plan because there is no corrected survivor.")
    lines.append("")

    lines.append("## Event-calendar governance")
    lines.append("")
    lines.append(str(summary.get("event_calendar_policy", "")))
    lines.append("")
    lines.append("## Broker/spot alignment")
    lines.append("")
    lines.append(str(summary.get("broker_alignment_policy", "")))
    lines.append("")

    lines.append("## Hard blocks")
    lines.append("")
    for b in summary.get("hard_blocks", []):
        lines.append(f"- `{b}`")
    lines.append("")
    lines.append("## Next allowed step")
    lines.append("")
    lines.append(f"`{summary.get('next_allowed_step')}`")
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    config_path = Path(args.config).resolve()
    out_dir = Path(args.out).resolve()
    cfg = read_json(config_path)

    summary = build_summary(root, config_path, out_dir, cfg)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_path = out_dir / "stage64n_full_scope_validation_decision_memo_summary.json"
    report_path = out_dir / "stage64n_full_scope_validation_decision_memo_report.md"
    decision_csv = out_dir / "stage64n_decision_matrix.csv"
    audit_csv = out_dir / "stage64n_survivor_audit_plan.csv"

    write_json(summary_path, summary)
    write_report(report_path, summary)
    write_csv(decision_csv, summary.get("decision_matrix", []), ["path", "status", "decision", "allowed_next"])
    write_csv(audit_csv, summary.get("survivor_audit_plan", []), ["audit_id", "hypothesis_id", "horizon_days", "purpose", "pass_condition", "failure_action"])

    print(json.dumps({
        "stage": STAGE,
        "status": summary["status"],
        "decision": summary["decision"],
        "next_allowed_step": summary["next_allowed_step"],
        "summary_json": rel(root, summary_path),
        "report_md": rel(root, report_path),
    }, indent=2))


if __name__ == "__main__":
    main()
