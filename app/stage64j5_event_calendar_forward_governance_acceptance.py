#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional


def utc_now_z() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})


def as_list(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []


def find_source_check(j1: Dict[str, Any], manifest_id: str) -> Optional[Dict[str, Any]]:
    for row in as_list(j1.get("source_checks")):
        if row.get("manifest_id") == manifest_id:
            return row
    return None


def boolish(x: Any) -> bool:
    return bool(x) is True


def build_markdown(summary: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Stage64J5 - Event Calendar Forward-Only Governance Acceptance (No Validation)")
    lines.append("")
    lines.append(f"Generated UTC: `{summary['generated_utc']}`")
    lines.append("")
    lines.append("## Status")
    lines.append("")
    for k in ["status", "decision", "validation_allowed_for_order_or_promotion", "promotion", "paper_order", "paper_live", "live"]:
        lines.append(f"- {k}: `{summary.get(k)}`")
    lines.append("")
    lines.append("## Executive conclusion")
    lines.append("")
    lines.append(summary["executive_conclusion"])
    lines.append("")
    lines.append("## Source readiness")
    lines.append("")
    lines.append("| manifest_id | role | preflight_ok | rows | status | issues |")
    lines.append("|---|---|---:|---:|---|---|")
    for row in summary["source_readiness_table"]:
        lines.append(
            f"| `{row['manifest_id']}` | `{row['role']}` | {row['preflight_ok']} | {row['row_count']} | `{row['status']}` | {row.get('issues','')} |"
        )
    lines.append("")
    lines.append("## Event-calendar governance decision")
    lines.append("")
    ec = summary["event_calendar_governance_decision"]
    for k in ["governance_manifest_found", "forward_only_governance_allowed", "historical_event_feature_allowed", "historical_event_archive_preflight_ok", "accepted_for_stage64k"]:
        lines.append(f"- {k}: `{ec.get(k)}`")
    lines.append("")
    lines.append("Forward-only event governance may only be used for future operational blackout/risk control. It must not be used as a historical validation feature or post-hoc event filter.")
    lines.append("")
    lines.append("## Broker/spot alignment")
    lines.append("")
    lines.append(summary["broker_alignment_statement"])
    lines.append("")
    lines.append("## Hard blocks")
    lines.append("")
    for b in summary["hard_blocks"]:
        lines.append(f"- `{b}`")
    lines.append("")
    lines.append("## Next allowed step")
    lines.append("")
    lines.append(f"`{summary['next_allowed_step']}`")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage64j5_event_calendar_forward_governance_acceptance.json")
    ap.add_argument("--out", default="reports/stage64j5_event_calendar_forward_governance_acceptance")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    config_path = (root / args.config).resolve()
    out_dir = (root / args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = load_json(config_path)

    j1_path = root / cfg["stage64j1_summary"]
    gov_path = root / cfg["stage64j2_event_calendar_governance"]
    j4_path = root / cfg.get("stage64j4_summary", "")

    j1 = load_json(j1_path)
    gov: Dict[str, Any] = {}
    gov_found = gov_path.exists()
    if gov_found:
        gov = load_json(gov_path)

    j4: Dict[str, Any] = {}
    if str(j4_path) and j4_path.exists():
        j4 = load_json(j4_path)

    required_p1 = cfg.get("required_p1_sources", [])
    source_rows: List[Dict[str, Any]] = []
    p1_ok = True
    for mid in required_p1:
        chk = find_source_check(j1, mid) or {}
        ok = boolish(chk.get("preflight_ok"))
        p1_ok = p1_ok and ok
        source_rows.append({
            "manifest_id": mid,
            "role": "core_full_scope_p1_source",
            "preflight_ok": ok,
            "row_count": chk.get("row_count", 0),
            "status": "OK" if ok else "BLOCKED",
            "issues": "; ".join(as_list(chk.get("issues"))),
        })

    event_mid = cfg.get("event_manifest_id", "SRC_MACRO_EVENT_CALENDAR_ARCHIVE")
    event_chk = find_source_check(j1, event_mid) or {}
    event_preflight_ok = boolish(event_chk.get("preflight_ok"))
    source_rows.append({
        "manifest_id": event_mid,
        "role": "event_calendar_historical_archive_or_forward_only_governance",
        "preflight_ok": event_preflight_ok,
        "row_count": event_chk.get("row_count", 0),
        "status": "HISTORICAL_ARCHIVE_OK" if event_preflight_ok else "HISTORICAL_ARCHIVE_BLOCKED_FORWARD_ONLY_GOVERNANCE_CANDIDATE",
        "issues": "; ".join(as_list(event_chk.get("issues"))),
    })

    broker_mid = cfg.get("broker_alignment_manifest_id", "SRC_BROKER_OR_SPOT_GOLD_D1_ALIGNMENT")
    broker_chk = find_source_check(j1, broker_mid) or {}
    broker_ok = boolish(broker_chk.get("preflight_ok"))
    source_rows.append({
        "manifest_id": broker_mid,
        "role": "broker_spot_alignment_before_commercialization",
        "preflight_ok": broker_ok,
        "row_count": broker_chk.get("row_count", 0),
        "status": "OK" if broker_ok else "BLOCKED_BEFORE_COMMERCIALIZATION_NOT_BLOCKING_STAGE64K_RESEARCH_DATASET",
        "issues": "; ".join(as_list(broker_chk.get("issues"))),
    })

    policy = gov.get("policy", {}) if isinstance(gov.get("policy"), dict) else {}
    forward_governance_allowed = gov_found and boolish(policy.get("forward_only_governance_allowed"))
    historical_event_feature_allowed = boolish(policy.get("historical_event_feature_allowed"))
    accepted_for_stage64k = p1_ok and (event_preflight_ok or (forward_governance_allowed and not historical_event_feature_allowed))

    if accepted_for_stage64k:
        decision = "EVENT_CALENDAR_FORWARD_ONLY_GOVERNANCE_ACCEPTED_STAGE64K_ALLOWED_NO_VALIDATION_NO_ORDER"
        executive = (
            "ETF and central-bank full-scope P1 sources passed source preflight. Historical event-calendar archive remains unavailable, "
            "but the previously formalized forward-only governance manifest is valid and is accepted only as future operational governance, "
            "not as a historical validation feature. Stage64K may build a lag-safe full-scope feature dataset using ETF and central-bank sources while excluding historical event-calendar features."
        )
        next_step = "Stage64K_FULL_SCOPE_LAG_SAFE_FEATURE_DATASET_PREFLIGHT_WITH_FORWARD_ONLY_EVENT_GOVERNANCE_NO_VALIDATION"
        status = "EVENT_FORWARD_ONLY_GOVERNANCE_ACCEPTANCE_COMPLETE_NO_PROMOTION"
    else:
        decision = "EVENT_GOVERNANCE_NOT_ACCEPTED_CONTINUE_SOURCE_ACQUISITION_OR_STOP_NO_ORDER"
        executive = (
            "Stage64J5 could not accept event-calendar forward-only governance for the next dataset stage. Continue acquiring a real historical event archive or stop the macro-regime program."
        )
        next_step = "ACQUIRE_EVENT_ARCHIVE_OR_PROGRAM_STOP_NO_ORDER"
        status = "EVENT_FORWARD_ONLY_GOVERNANCE_ACCEPTANCE_BLOCKED_NO_PROMOTION"

    summary: Dict[str, Any] = {
        "stage": "Stage64J5_EVENT_CALENDAR_FORWARD_ONLY_GOVERNANCE_ACCEPTANCE_NO_VALIDATION",
        "status": status,
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
            "stage64j1_summary": str(j1_path),
            "stage64j2_event_calendar_governance": str(gov_path),
            "stage64j4_summary": str(j4_path) if str(j4_path) else "",
        },
        "source_readiness_table": source_rows,
        "p1_full_scope_sources_preflight_ok": p1_ok,
        "event_calendar_governance_decision": {
            "event_manifest_id": event_mid,
            "historical_event_archive_preflight_ok": event_preflight_ok,
            "governance_manifest_found": gov_found,
            "forward_only_governance_allowed": forward_governance_allowed,
            "historical_event_feature_allowed": historical_event_feature_allowed,
            "accepted_for_stage64k": accepted_for_stage64k,
            "blocked_historical_uses": policy.get("blocked_use", "No historical backtest filtering, no post-hoc event exclusion, no validation uplift claim."),
            "allowed_forward_use": policy.get("allowed_use", "Future operational blackout/risk governance only after validation and only if known before event time."),
        },
        "broker_alignment_statement": (
            "Broker/spot D1 alignment remains required before any commercialization or broker XAUUSD validation claim. "
            "It is not accepted as an order/promotion path and does not authorize broker connection. It may remain blocked during Stage64K research dataset preflight."
        ),
        "stage64j4_mapping_reference": {
            "status": j4.get("status", ""),
            "decision": j4.get("decision", ""),
            "mapping_results": j4.get("mapping_results", {}),
        },
        "executive_conclusion": executive,
        "next_allowed_step": next_step,
        "hard_blocks": [
            "NO_PAPER_ORDER",
            "NO_EA_PROMOTION",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_BROKER_CONNECTION",
            "NO_VALIDATION_SCAN_IN_STAGE64J5",
            "NO_HISTORICAL_EVENT_FILTER_FROM_FORWARD_ONLY_GOVERNANCE",
            "NO_POST_HOC_EVENT_EXCLUSION",
            "NO_REDUCED_SCOPE_RETEST",
            "NO_RESCUE_FILTERING",
            "NO_NEW_INTRADAY_SCAN",
            "NO_FULL_SCOPE_VALIDATION_CLAIM_FROM_STAGE64J5",
        ],
        "outputs": {
            "summary_json": str(out_dir / "stage64j5_event_calendar_forward_governance_acceptance_summary.json"),
            "report_md": str(out_dir / "stage64j5_event_calendar_forward_governance_acceptance_report.md"),
            "source_readiness_csv": str(out_dir / "stage64j5_source_readiness.csv"),
        },
    }

    write_json(out_dir / "stage64j5_event_calendar_forward_governance_acceptance_summary.json", summary)
    (out_dir / "stage64j5_event_calendar_forward_governance_acceptance_report.md").write_text(build_markdown(summary), encoding="utf-8")
    write_csv(out_dir / "stage64j5_source_readiness.csv", source_rows, ["manifest_id", "role", "preflight_ok", "row_count", "status", "issues"])

    print(summary["status"])
    print(summary["decision"])
    print("next_allowed_step=", summary["next_allowed_step"])
    return 0 if accepted_for_stage64k else 2


if __name__ == "__main__":
    raise SystemExit(main())
