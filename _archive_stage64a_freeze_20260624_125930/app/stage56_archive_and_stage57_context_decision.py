#!/usr/bin/env python3
"""
Stage56 archive + Stage57 context expansion decision helper.

This script is intentionally non-trading and non-promotional. It reads the
Stage56 megascan summary plus optional Stage55/Stage54 summaries and creates a
plain decision report documenting whether the price-action alternative megascan
should be archived and whether context-aware research should be prepared.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

NO_GO = {
    "promotion": "NO_GO",
    "EA": "NO_GO",
    "paper_live": "NO_GO",
    "live": "NO_GO",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path, required: bool = False) -> Optional[Dict[str, Any]]:
    if not path.exists():
        if required:
            raise FileNotFoundError(f"required JSON not found: {path}")
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def read_csv_count(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"found": False, "rows": 0, "columns": [], "sample": []}
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = []
        count = 0
        for row in reader:
            count += 1
            if len(rows) < 5:
                rows.append(dict(row))
        return {"found": True, "rows": count, "columns": reader.fieldnames or [], "sample": rows}


def summarize_family_status(stage56: Dict[str, Any]) -> List[Dict[str, Any]]:
    fam = stage56.get("family_summary", {}) or {}
    out: List[Dict[str, Any]] = []
    for name, payload in fam.items():
        out.append(
            {
                "family": name,
                "candidate_count": payload.get("candidate_count", 0),
                "trade_count": payload.get("trade_count", 0),
                "hard_audit_pass_count": payload.get("hard_audit_pass_count", 0),
                "error": payload.get("error"),
                "decision": "ARCHIVE_NO_PASS" if (payload.get("hard_audit_pass_count", 0) or 0) == 0 else "KEEP_FOR_REVIEW",
            }
        )
    return out


def context_source_inventory(root: Path, manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    sources = manifest.get("context_sources", []) if isinstance(manifest, dict) else []
    out = []
    for src in sources:
        item = dict(src)
        paths = src.get("candidate_paths", []) or []
        found_paths = []
        for p in paths:
            pp = Path(os.path.expanduser(str(p)))
            if not pp.is_absolute():
                pp = root / pp
            if pp.exists():
                found_paths.append(str(pp))
        item["found_paths"] = found_paths
        item["available_now"] = bool(found_paths) or bool(src.get("derived_from_existing_broker_db", False))
        out.append(item)
    return out


def write_markdown(path: Path, summary: Dict[str, Any]) -> None:
    lines: List[str] = []
    lines.append("# Stage56 Archive and Stage57 Context Expansion Decision")
    lines.append("")
    for key in ["status", "decision", "next_allowed_step", "promotion", "EA", "paper_live", "live"]:
        lines.append(f"- {key}: `{summary.get(key)}`")
    lines.append("")
    lines.append("## Stage56 outcome")
    s56 = summary.get("stage56", {})
    lines.append(f"- total_candidates: `{s56.get('total_candidates')}`")
    lines.append(f"- total_trade_rows: `{s56.get('total_trade_rows')}`")
    lines.append(f"- hard_audit_pass_count: `{s56.get('hard_audit_pass_count')}`")
    lines.append("")
    lines.append("## Family archive decisions")
    for item in summary.get("family_archive", []):
        lines.append(
            f"- `{item.get('family')}`: candidates=`{item.get('candidate_count')}`, "
            f"trades=`{item.get('trade_count')}`, pass=`{item.get('hard_audit_pass_count')}`, "
            f"decision=`{item.get('decision')}`"
        )
    lines.append("")
    lines.append("## Context expansion inventory")
    for item in summary.get("context_inventory", []):
        lines.append(
            f"- `{item.get('id')}` priority=`{item.get('priority')}` available_now=`{item.get('available_now')}` "
            f"status=`{item.get('status')}`"
        )
    lines.append("")
    lines.append("## Interpretation")
    lines.append(
        "The Stage56 parallel alternative price-action megascan produced no hard-audit survivors. "
        "The correct response is to archive these three alternative families rather than rescue/tune them. "
        "Stage51/52 should continue as a passive true-forward evidence collector, but the next active research branch should expand context rather than repeat price-action-only scans."
    )
    lines.append("")
    lines.append("No promotion, EA, paper-live, live trading, or order submission is authorized.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    fieldnames = ["family", "candidate_count", "trade_count", "hard_audit_pass_count", "decision", "error"]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fieldnames})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--stage56-summary", default="reports/stage56_parallel_alt_megascan/stage56_parallel_alt_megascan_summary.json")
    ap.add_argument("--stage56-candidates", default="reports/stage56_parallel_alt_megascan/stage56_parallel_alt_megascan_candidates.csv")
    ap.add_argument("--stage55-summary", default="reports/stage55_frequency_and_alternatives/stage55_forward_frequency_and_alternative_path_summary.json")
    ap.add_argument("--stage54-summary", default="reports/stage54_ops_readiness/stage54_ops_readiness_summary.json")
    ap.add_argument("--context-manifest", default="configs/stage57_context_source_manifest.json")
    ap.add_argument("--out", default="reports/stage57_context_expansion")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    out = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    stage56 = load_json(root / args.stage56_summary, required=True)
    stage55 = load_json(root / args.stage55_summary, required=False)
    stage54 = load_json(root / args.stage54_summary, required=False)
    manifest = load_json(root / args.context_manifest, required=False) or {}
    cand_meta = read_csv_count(root / args.stage56_candidates)

    hard_pass = int(stage56.get("hard_audit_pass_count") or 0)
    stage56_decision = stage56.get("decision")
    no_pass = hard_pass == 0 and str(stage56_decision or "").endswith("NO_PASS_NO_PROMOTION")

    decision = (
        "ARCHIVE_STAGE56_PRICE_ACTION_ALTS_AND_PREPARE_STAGE57_CONTEXT_EXPANSION_NO_PROMOTION"
        if no_pass
        else "REVIEW_STAGE56_SURVIVORS_NO_PROMOTION"
    )
    next_step = (
        "STAGE57_CONTEXT_SOURCE_PRECHECK_NO_PROMOTION_AND_CONTINUE_STAGE52_FORWARD_SHADOW"
        if no_pass
        else "DESIGN_FORWARD_SHADOW_FOR_STAGE56_SURVIVORS_NO_PROMOTION"
    )

    family_archive = summarize_family_status(stage56)
    context_inventory = context_source_inventory(root, manifest)

    summary: Dict[str, Any] = {
        "stage": "Stage56_ARCHIVE_STAGE57_CONTEXT_DECISION_NO_PROMOTION",
        "status": "ARCHIVE_AND_CONTEXT_DECISION_COMPLETE_NO_PROMOTION",
        **NO_GO,
        "decision": decision,
        "next_allowed_step": next_step,
        "root": str(root),
        "stage56_summary_path": str(root / args.stage56_summary),
        "stage56_candidates_path": str(root / args.stage56_candidates),
        "stage56_candidates_meta": cand_meta,
        "stage56": {
            "status": stage56.get("status"),
            "decision": stage56.get("decision"),
            "total_candidates": stage56.get("total_candidates"),
            "total_trade_rows": stage56.get("total_trade_rows"),
            "hard_audit_pass_count": stage56.get("hard_audit_pass_count"),
            "family_summary": stage56.get("family_summary"),
        },
        "stage55_decision": (stage55 or {}).get("decision"),
        "stage54_decision": (stage54 or {}).get("decision"),
        "family_archive": family_archive,
        "context_inventory": context_inventory,
        "generated_utc": utc_now(),
    }

    summary_path = out / "stage56_archive_stage57_context_decision_summary.json"
    report_path = out / "stage56_archive_stage57_context_decision_report.md"
    archive_csv_path = out / "stage56_family_archive_decisions.csv"

    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_markdown(report_path, summary)
    write_csv(archive_csv_path, family_archive)

    print(json.dumps({"stage": summary["stage"], "status": summary["status"], "decision": decision, "out": str(out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
