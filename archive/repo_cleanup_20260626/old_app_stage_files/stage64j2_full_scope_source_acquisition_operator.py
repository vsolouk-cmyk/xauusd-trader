#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List


def utc_now_z() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path, required: bool = False) -> Dict[str, Any]:
    if not path.exists():
        if required:
            raise FileNotFoundError(str(path))
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def create_template(path: Path, columns: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        write_csv(path, [], columns)


def count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        return sum(1 for _ in reader)


def csv_columns(path: Path) -> List[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or [])


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage64J2 full-scope source acquisition operator plan; no validation.")
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage64j2_full_scope_source_acquisition_operator.json")
    ap.add_argument("--out", default="reports/stage64j2_full_scope_source_acquisition_operator")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    config_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = load_json(config_path, required=True)
    j1_summary = load_json(root / cfg.get("stage64j1_summary_path", ""), required=False)
    source_targets: List[Dict[str, Any]] = cfg.get("source_targets", [])

    plan_rows: List[Dict[str, Any]] = []
    for t in source_targets:
        target_file = root / t["target_file"]
        template_file = root / t["template_file"]
        create_template(template_file, t["required_columns"])
        found = target_file.exists()
        rows = count_csv_rows(target_file) if found else 0
        cols = csv_columns(target_file) if found else []
        missing_cols = [c for c in t["required_columns"] if c not in cols] if found else t["required_columns"]
        row_count_ok = rows >= int(t.get("minimum_rows_for_preflight", 0))
        schema_ok = found and not missing_cols
        current_state = "READY_CANDIDATE_FOR_J1_PREFLIGHT" if schema_ok and row_count_ok else ("MISSING_FILE" if not found else "DATA_OR_SCHEMA_INCOMPLETE")
        plan_rows.append({
            "manifest_id": t["manifest_id"],
            "priority": t.get("priority", ""),
            "target_file": t["target_file"],
            "template_file": t["template_file"],
            "found": found,
            "current_rows": rows,
            "minimum_rows_for_preflight": t.get("minimum_rows_for_preflight", ""),
            "schema_ok": schema_ok,
            "missing_columns": ";".join(missing_cols),
            "row_count_ok": row_count_ok,
            "current_state": current_state,
            "lag_policy": t.get("lag_policy", ""),
            "accepted_source_families": "; ".join(t.get("accepted_source_families", [])),
            "required_action": t.get("required_action", ""),
        })

    event_governance = None
    if cfg.get("formalize_event_calendar_forward_only_governance"):
        policy = cfg.get("event_calendar_forward_only_policy", {})
        event_governance = {
            "stage": cfg.get("stage"),
            "generated_utc": utc_now_z(),
            "policy": policy,
            "operational_effect": "Historical event-calendar validation feature remains blocked unless real archive is acquired. Forward-only governance may be used only for future blackout/risk control after any later validation stage.",
            "hard_blocks": [
                "NO_HISTORICAL_EVENT_FILTER_BACKTEST_WITH_FORWARD_ONLY_GOVERNANCE",
                "NO_POST_HOC_EVENT_EXCLUSION",
                "NO_ORDER_AUTHORIZATION",
                "NO_REDUCED_SCOPE_RESCUE"
            ]
        }
        write_json(root / "data/macro_regime/manifests/stage64j2_event_calendar_forward_only_governance.json", event_governance)

    ready_candidates = sum(1 for r in plan_rows if r["current_state"] == "READY_CANDIDATE_FOR_J1_PREFLIGHT")
    missing_or_incomplete = len(plan_rows) - ready_candidates

    decision = "SOURCE_ACQUISITION_OPERATOR_PLAN_COMPLETE_CONTINUE_ACQUISITION_OR_PROGRAM_STOP_NO_ORDER"
    next_allowed_step = "ACQUIRE_SOURCE_FILES_AND_RERUN_STAGE64J1_OR_PROGRAM_STOP_NO_ORDER"

    summary = {
        "stage": cfg.get("stage"),
        "status": "SOURCE_ACQUISITION_OPERATOR_PLAN_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_order": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "validation_allowed_for_order_or_promotion": False,
        "generated_utc": utc_now_z(),
        "root": str(root),
        "inputs": {
            "config": str(config_path),
            "stage64j1_summary": str(root / cfg.get("stage64j1_summary_path", "")),
        },
        "stage64j1_state": {
            "decision": j1_summary.get("decision"),
            "blocked_source_count": j1_summary.get("counts", {}).get("blocked_source_count"),
            "next_allowed_step": j1_summary.get("next_allowed_step"),
        },
        "counts": {
            "source_targets": len(source_targets),
            "ready_candidates_for_j1_preflight": ready_candidates,
            "missing_or_incomplete_targets": missing_or_incomplete,
            "templates_created_or_present": len(source_targets),
            "event_calendar_forward_only_governance_formalized": bool(event_governance),
        },
        "source_plan": plan_rows,
        "event_calendar_forward_only_governance": event_governance,
        "hard_blocks": cfg.get("hard_blocks", []),
        "next_allowed_step": next_allowed_step,
        "outputs": {
            "summary_json": str(out_dir / "stage64j2_full_scope_source_acquisition_operator_summary.json"),
            "report_md": str(out_dir / "stage64j2_full_scope_source_acquisition_operator_report.md"),
            "source_plan_csv": str(out_dir / "stage64j2_source_acquisition_plan.csv"),
            "source_plan_json": str(out_dir / "stage64j2_source_acquisition_plan.json"),
            "event_calendar_governance_json": str(root / "data/macro_regime/manifests/stage64j2_event_calendar_forward_only_governance.json") if event_governance else "",
        }
    }

    write_json(out_dir / "stage64j2_full_scope_source_acquisition_operator_summary.json", summary)
    write_json(out_dir / "stage64j2_source_acquisition_plan.json", plan_rows)
    write_csv(out_dir / "stage64j2_source_acquisition_plan.csv", plan_rows, [
        "manifest_id", "priority", "target_file", "template_file", "found", "current_rows",
        "minimum_rows_for_preflight", "schema_ok", "missing_columns", "row_count_ok", "current_state",
        "lag_policy", "accepted_source_families", "required_action"
    ])

    md = []
    md.append("# Stage64J2 - Full-Scope Source Acquisition Operator Plan (No Validation)\n")
    md.append(f"Generated UTC: `{summary['generated_utc']}`\n")
    md.append("## Status\n")
    md.append("- status: `SOURCE_ACQUISITION_OPERATOR_PLAN_COMPLETE_NO_PROMOTION`")
    md.append(f"- decision: `{decision}`")
    md.append("- validation_allowed_for_order_or_promotion: `false`")
    md.append("- promotion/paper/live: `NO_GO`\n")
    md.append("## Executive conclusion\n")
    md.append("Stage64J2 does not acquire data and does not run validation. It creates source templates, formalizes the optional forward-only event-calendar governance path, and gives the operator a strict source-acquisition checklist. Continue only by acquiring the missing full-scope sources under lag policy or stop the program.\n")
    md.append("## Current source acquisition plan\n")
    md.append("| manifest_id | state | rows | min_rows | target_file | lag_policy | required_action |")
    md.append("|---|---|---:|---:|---|---|---|")
    for r in plan_rows:
        md.append(f"| `{r['manifest_id']}` | `{r['current_state']}` | {r['current_rows']} | {r['minimum_rows_for_preflight']} | `{r['target_file']}` | `{r['lag_policy']}` | {r['required_action']} |")
    md.append("\n## Templates\n")
    for r in plan_rows:
        md.append(f"- `{r['template_file']}`")
    if event_governance:
        md.append("\n## Event-calendar governance\n")
        md.append("Historical event-calendar filtering remains blocked unless a real historical archive is acquired. A forward-only governance manifest was written for future blackout/risk control only; it cannot be used to improve historical validation results.\n")
    md.append("## Hard blocks\n")
    for b in cfg.get("hard_blocks", []):
        md.append(f"- `{b}`")
    md.append("\n## Next allowed step\n")
    md.append(f"`{next_allowed_step}`\n")
    (out_dir / "stage64j2_full_scope_source_acquisition_operator_report.md").write_text("\n".join(md), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
