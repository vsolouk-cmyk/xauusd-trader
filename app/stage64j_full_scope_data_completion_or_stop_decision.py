#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import datetime as dt
from pathlib import Path
from typing import Any, Dict, List


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def rel_or_abs(root: Path, p: str) -> Path:
    pp = Path(p)
    return pp if pp.is_absolute() else root / pp


def count_data_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f)
        try:
            next(reader)
        except StopIteration:
            return 0
        return sum(1 for _ in reader)


def first_header(path: Path) -> List[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f)
        try:
            return next(reader)
        except StopIteration:
            return []


def schema_missing(path: Path, required: List[str]) -> List[str]:
    header = set(first_header(path))
    return [c for c in required if c not in header]


def build_source_plan(root: Path, config: Dict[str, Any], stage64i: Dict[str, Any]) -> List[Dict[str, Any]]:
    by_manifest = {}
    for b in stage64i.get("full_scope_state", {}).get("blockers", []):
        by_manifest[b.get("manifest_id")] = b

    plan_rows: List[Dict[str, Any]] = []
    for src in config.get("required_source_completion", []):
        target = rel_or_abs(root, src["target_file"])
        row_count = count_data_rows(target)
        missing_cols = schema_missing(target, src.get("required_columns", []))
        blocker = by_manifest.get(src.get("manifest_id"), {})
        found = target.exists()
        schema_ok = found and not missing_cols
        min_rows = int(src.get("minimum_rows_for_preflight", 1))
        row_count_ok = row_count >= min_rows

        if not found:
            current_state = "MISSING_FILE"
        elif not schema_ok:
            current_state = "SCHEMA_BLOCKED"
        elif not row_count_ok:
            current_state = "DATA_ROWS_BLOCKED"
        else:
            current_state = "POTENTIALLY_READY_FOR_NEXT_PREFLIGHT"

        plan_rows.append({
            "manifest_id": src.get("manifest_id"),
            "priority": src.get("priority"),
            "target_file": src.get("target_file"),
            "found": found,
            "current_row_count": row_count,
            "minimum_rows_for_preflight": min_rows,
            "schema_ok": schema_ok,
            "missing_columns": ";".join(missing_cols),
            "current_state": current_state,
            "lag_policy": src.get("lag_policy"),
            "required_action": src.get("required_action"),
            "notes": src.get("notes", ""),
            "stage64i_issue": blocker.get("issues", ""),
        })
    return plan_rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage64J full-scope data completion or program stop decision memo")
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage64j_full_scope_data_completion_or_stop_decision.json")
    ap.add_argument("--out", default="reports/stage64j_full_scope_data_completion_or_stop_decision")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cfg_path = rel_or_abs(root, args.config)
    out = rel_or_abs(root, args.out)
    out.mkdir(parents=True, exist_ok=True)

    config = read_json(cfg_path)
    stage64i_path = rel_or_abs(root, config["inputs"]["stage64i_summary"])
    stage64i = read_json(stage64i_path)

    reduced_scope_killed = stage64i.get("reduced_scope_decision") == "KILL_REDUCED_SCOPE_P0_PLUS_VIX_AS_PROMOTION_OR_VALIDATION_PATH"
    no_stage64h_survivors = (stage64i.get("stage64h_evidence", {}).get("corrected_survivors") == 0)
    full_scope_blockers = stage64i.get("full_scope_state", {}).get("blockers", [])
    full_scope_blocked = bool(full_scope_blockers)

    source_plan = build_source_plan(root, config, stage64i)
    blocked_sources = [r for r in source_plan if r["current_state"] != "POTENTIALLY_READY_FOR_NEXT_PREFLIGHT"]

    if not reduced_scope_killed or not no_stage64h_survivors:
        decision = "BLOCK_STAGE64J_INPUTS_INCONSISTENT_NO_ORDER"
        status = "DECISION_MEMO_INPUT_BLOCKED_NO_PROMOTION"
        next_allowed_step = "FIX_STAGE64I_OR_STAGE64H_INPUTS_NO_ORDER"
        continuation_allowed = False
    elif full_scope_blocked:
        decision = "CONTINUE_ONLY_WITH_FULL_SCOPE_DATA_COMPLETION_OR_STOP_NO_ORDER"
        status = "FULL_SCOPE_DATA_COMPLETION_OR_STOP_DECISION_COMPLETE_NO_PROMOTION"
        next_allowed_step = "Stage64J1_FULL_SCOPE_P1_P2_SOURCE_ACQUISITION_PREFLIGHT_OR_PROGRAM_STOP_NO_ORDER"
        continuation_allowed = True
    else:
        decision = "FULL_SCOPE_BLOCKERS_NOT_PRESENT_RERUN_STAGE64D_PREFLIGHT_NO_ORDER"
        status = "DECISION_MEMO_COMPLETE_NO_PROMOTION"
        next_allowed_step = "Stage64D_RERUN_FULL_SCOPE_DATA_CONTRACT_AUDIT_NO_ORDER"
        continuation_allowed = True

    decision_matrix = [
        {
            "path": "Reduced-scope P0+VIX",
            "status": "KILLED" if reduced_scope_killed else "NOT_CONFIRMED",
            "evidence": "Stage64H corrected_survivors=0 and no uncorrected watch candidates" if no_stage64h_survivors else "Stage64H survivor evidence not clean",
            "decision": "Reference only; no tuning, no rescue filter, no intraday scan, no promotion",
            "allowed_next": "None except archival/reference use",
        },
        {
            "path": "Full macro-regime thesis",
            "status": "BLOCKED_BY_DATA_COMPLETION" if full_scope_blocked else "DATA_BLOCKERS_NOT_PRESENT",
            "evidence": f"full_scope_blockers={len(full_scope_blockers)}",
            "decision": "Continue only by acquiring ETF, central-bank demand, event calendar, and preserving lag policy",
            "allowed_next": "Stage64J1 source acquisition/preflight or explicit program stop",
        },
        {
            "path": "Broker/spot alignment",
            "status": "REQUIRED_BEFORE_COMMERCIALIZATION",
            "evidence": "Current gold D1 reference is COMEX continuous futures proxy/source warning from prior stages",
            "decision": "No broker XAUUSD claim until broker/spot D1 alignment audit or backfill is available",
            "allowed_next": "Can be prepared after full-scope data completion, before any commercialization claim",
        },
        {
            "path": "Order / EA / paper-live / live",
            "status": "HARD_BLOCKED",
            "evidence": "Reduced scope failed and full scope incomplete",
            "decision": "NO_GO",
            "allowed_next": "None",
        },
    ]

    summary = {
        "stage": "Stage64J_FULL_SCOPE_DATA_COMPLETION_OR_PROGRAM_STOP_DECISION_NO_ORDER",
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
            "config": str(cfg_path),
            "stage64i_summary": str(stage64i_path),
        },
        "stage64i_evidence": {
            "reduced_scope_decision": stage64i.get("reduced_scope_decision"),
            "corrected_survivors": stage64i.get("stage64h_evidence", {}).get("corrected_survivors"),
            "uncorrected_watch_only": stage64i.get("stage64h_evidence", {}).get("uncorrected_watch_only"),
            "negative_excess_vs_benchmark_count": stage64i.get("stage64h_evidence", {}).get("negative_excess_vs_benchmark_count"),
            "full_scope_blocker_count": len(full_scope_blockers),
        },
        "continuation_policy": {
            "data_completion_continuation_allowed": continuation_allowed,
            "reduced_scope_retest_allowed": False,
            "new_intraday_scan_allowed": False,
            "parameter_tweak_or_rescue_filter_allowed": False,
            "program_stop_allowed": True,
            "stage64j1_allowed": continuation_allowed and full_scope_blocked,
        },
        "source_completion_plan": source_plan,
        "blocked_source_count": len(blocked_sources),
        "decision_matrix": decision_matrix,
        "program_stop_triggers": config.get("program_stop_triggers", []),
        "next_allowed_step": next_allowed_step,
        "hard_blocks": [
            "NO_PAPER_ORDER",
            "NO_EA_PROMOTION",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_BROKER_CONNECTION",
            "NO_FULL_SCOPE_VALIDATION_CLAIM",
            "NO_REDUCED_SCOPE_PARAMETER_TWEAKING",
            "NO_RESCUE_FILTERING",
            "NO_NEW_INTRADAY_SCAN",
            "NO_VALIDATION_SCAN_IN_STAGE64J",
        ],
        "outputs": {
            "summary_json": str(out / "stage64j_full_scope_data_completion_or_stop_decision_summary.json"),
            "report_md": str(out / "stage64j_full_scope_data_completion_or_stop_decision_report.md"),
            "source_plan_csv": str(out / "stage64j_source_completion_plan.csv"),
            "decision_matrix_csv": str(out / "stage64j_decision_matrix.csv"),
        },
    }

    write_json(out / "stage64j_full_scope_data_completion_or_stop_decision_summary.json", summary)
    write_csv(out / "stage64j_source_completion_plan.csv", source_plan, [
        "manifest_id", "priority", "target_file", "found", "current_row_count", "minimum_rows_for_preflight",
        "schema_ok", "missing_columns", "current_state", "lag_policy", "required_action", "notes", "stage64i_issue",
    ])
    write_csv(out / "stage64j_decision_matrix.csv", decision_matrix, ["path", "status", "evidence", "decision", "allowed_next"])

    report = out / "stage64j_full_scope_data_completion_or_stop_decision_report.md"
    with report.open("w", encoding="utf-8") as f:
        f.write("# Stage64J - Full-Scope Data Completion or Program Stop Decision (No Order)\n\n")
        f.write(f"Generated UTC: `{summary['generated_utc']}`\n\n")
        f.write("## Status\n\n")
        f.write(f"- status: `{status}`\n")
        f.write(f"- decision: `{decision}`\n")
        f.write("- promotion/paper/live: `NO_GO`\n")
        f.write("- validation_allowed_for_order_or_promotion: `false`\n\n")
        f.write("## Executive conclusion\n\n")
        f.write("Reduced-scope P0+VIX is killed as a promotion or continued-validation path. The only non-stopped continuation is full-scope data completion under lag-safe rules. No tuning, rescue filtering, intraday scanning, order generation, broker connection, EA promotion, paper-live, or live path is authorized.\n\n")
        f.write("## Evidence inherited from Stage64I\n\n")
        ev = summary["stage64i_evidence"]
        for k, v in ev.items():
            f.write(f"- {k}: `{v}`\n")
        f.write("\n## Required source completion plan\n\n")
        f.write("| manifest_id | priority | current_state | rows | min_rows | target_file | lag_policy | required_action |\n")
        f.write("|---|---|---|---:|---:|---|---|---|\n")
        for r in source_plan:
            f.write(f"| `{r['manifest_id']}` | `{r['priority']}` | `{r['current_state']}` | {r['current_row_count']} | {r['minimum_rows_for_preflight']} | `{r['target_file']}` | `{r['lag_policy']}` | {r['required_action']} |\n")
        f.write("\n## Decision matrix\n\n")
        f.write("| path | status | decision | allowed_next |\n")
        f.write("|---|---|---|---|\n")
        for r in decision_matrix:
            f.write(f"| `{r['path']}` | `{r['status']}` | {r['decision']} | {r['allowed_next']} |\n")
        f.write("\n## Program stop triggers\n\n")
        for t in config.get("program_stop_triggers", []):
            f.write(f"- {t}\n")
        f.write("\n## Operational decision\n\n")
        f.write("No validation scan, signal generation, paper-order, paper-live, live, EA promotion, broker connection, or full-scope validation claim is authorized by Stage64J.\n\n")
        f.write("## Next allowed step\n\n")
        f.write(f"`{next_allowed_step}`\n")

    return 0 if continuation_allowed else 2


if __name__ == "__main__":
    raise SystemExit(main())
