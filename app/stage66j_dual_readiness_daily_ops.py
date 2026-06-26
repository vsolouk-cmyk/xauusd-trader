#!/usr/bin/env python3
"""
Stage66J Dual Readiness Daily Ops

Runs/collects no-order readiness checks for:
- Stage65B / H64L background forward-shadow ops
- Stage66H / H64L v2 no-broker dry-run ticket generator
- Stage66I / D3 H60 complementary no-broker dry-run ticket generator

This script never authorizes or places orders. It is an orchestration and summary layer only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE66J",
    "NO_THRESHOLD_TUNING",
    "NO_PROMOTION_FROM_DAILY_OPS_ONLY",
]

NO_ORDER_DECISIONS = {
    "STAGE65_FORWARD_LEDGER_ACTIVE_CONTINUE_DAILY_NO_ORDER",
    "WAIT_FOR_FRESH_H64L_V2_SIGNAL_NO_DRY_RUN_TICKET",
    "DRY_RUN_TICKET_READY_NO_BROKER_NO_ORDER",
    "WAIT_FOR_FRESH_COMPLEMENTARY_D3_H60_SIGNAL_NO_DRY_RUN_TICKET",
    "COMPLEMENTARY_DRY_RUN_TICKET_READY_NO_BROKER_NO_ORDER",
}

H64L_READY_DECISION = "DRY_RUN_TICKET_READY_NO_BROKER_NO_ORDER"
D3_READY_DECISION = "COMPLEMENTARY_DRY_RUN_TICKET_READY_NO_BROKER_NO_ORDER"
H64L_WAIT_DECISION = "WAIT_FOR_FRESH_H64L_V2_SIGNAL_NO_DRY_RUN_TICKET"
D3_WAIT_DECISION = "WAIT_FOR_FRESH_COMPLEMENTARY_D3_H60_SIGNAL_NO_DRY_RUN_TICKET"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def tail_text(text: str, limit: int = 4000) -> str:
    if not text:
        return ""
    return text[-limit:]


def rel(root: Path, p: Path) -> str:
    try:
        return str(p.relative_to(root))
    except Exception:
        return str(p)


@dataclass
class StageSpec:
    stage_key: str
    enabled: bool
    script: Path
    config: Optional[Path]
    out_dir: Path
    summary_path: Path
    args: List[str]


def resolve_stage_specs(root: Path, cfg: Dict[str, Any]) -> List[StageSpec]:
    stages_cfg = cfg.get("stages", {})
    specs: List[StageSpec] = []
    for key in ["stage65b", "stage66h", "stage66i"]:
        sc = stages_cfg.get(key, {})
        enabled = bool(sc.get("enabled", True))
        script = root / sc["script"]
        config_path = root / sc["config"] if sc.get("config") else None
        out_dir = root / sc["out_dir"]
        summary_path = root / sc["summary_path"]
        args = list(sc.get("extra_args", []))
        specs.append(StageSpec(key, enabled, script, config_path, out_dir, summary_path, args))
    return specs


def run_stage(root: Path, python_exe: str, spec: StageSpec, timeout_seconds: int) -> Dict[str, Any]:
    if not spec.enabled:
        return {
            "stage_key": spec.stage_key,
            "enabled": False,
            "attempted": False,
            "status": "SKIPPED_DISABLED",
            "summary_path": rel(root, spec.summary_path),
            "summary_found": spec.summary_path.exists(),
        }

    issues: List[str] = []
    if not spec.script.exists():
        issues.append(f"missing_script:{rel(root, spec.script)}")
    if spec.config is not None and not spec.config.exists():
        issues.append(f"missing_config:{rel(root, spec.config)}")

    if issues:
        return {
            "stage_key": spec.stage_key,
            "enabled": True,
            "attempted": False,
            "status": "BLOCKED_MISSING_INPUTS",
            "issues": issues,
            "summary_path": rel(root, spec.summary_path),
            "summary_found": spec.summary_path.exists(),
        }

    cmd = [python_exe, str(spec.script), "--root", str(root)]
    if spec.config is not None:
        cmd += ["--config", str(spec.config)]
    cmd += ["--out", str(spec.out_dir)]
    cmd += spec.args

    proc = subprocess.run(
        cmd,
        cwd=str(root),
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
    )
    return {
        "stage_key": spec.stage_key,
        "enabled": True,
        "attempted": True,
        "cmd": cmd,
        "returncode": proc.returncode,
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "stdout_tail": tail_text(proc.stdout),
        "stderr_tail": tail_text(proc.stderr),
        "summary_path": rel(root, spec.summary_path),
        "summary_found": spec.summary_path.exists(),
        "summary_sha256": sha256_file(spec.summary_path),
    }


def classify_decisions(stage_summaries: Dict[str, Dict[str, Any]], run_results: Dict[str, Dict[str, Any]]) -> Tuple[str, str, List[str], Dict[str, Any]]:
    issues: List[str] = []
    stage_decisions: Dict[str, Any] = {}

    for key, summary in stage_summaries.items():
        decision = summary.get("decision")
        status = summary.get("status")
        stage_decisions[key] = {
            "decision": decision,
            "status": status,
            "classification": summary.get("classification"),
            "ticket_path": summary.get("ticket_path"),
        }
        if decision not in NO_ORDER_DECISIONS:
            issues.append(f"unexpected_or_missing_decision:{key}:{decision}")

    for key, rr in run_results.items():
        if rr.get("enabled") and rr.get("status") != "PASS":
            issues.append(f"stage_run_not_pass:{key}:{rr.get('status')}")
        if rr.get("enabled") and not rr.get("summary_found"):
            issues.append(f"summary_missing_after_run:{key}")

    h = stage_decisions.get("stage66h", {}).get("decision")
    i = stage_decisions.get("stage66i", {}).get("decision")

    if issues:
        decision = "STAGE66J_STOP_DAILY_OPS_INPUT_OR_STAGE_FAILURE_NO_ORDER"
        classification = "J_STOP"
    elif h == H64L_READY_DECISION and i == D3_READY_DECISION:
        decision = "STAGE66J_MANUAL_REVIEW_REQUIRED_BOTH_DRY_RUN_TICKETS_READY_NO_ORDER"
        classification = "J_BOTH_TICKETS_READY"
    elif h == H64L_READY_DECISION:
        decision = "STAGE66J_MANUAL_REVIEW_REQUIRED_H64L_DRY_RUN_TICKET_READY_NO_ORDER"
        classification = "J_H64L_TICKET_READY"
    elif i == D3_READY_DECISION:
        decision = "STAGE66J_MANUAL_REVIEW_REQUIRED_D3_DRY_RUN_TICKET_READY_NO_ORDER"
        classification = "J_D3_TICKET_READY"
    elif h == H64L_WAIT_DECISION and i == D3_WAIT_DECISION:
        decision = "STAGE66J_DUAL_READINESS_WAIT_SIGNALS_NO_ORDER"
        classification = "J_WAIT_BOTH_INACTIVE"
    else:
        decision = "STAGE66J_DAILY_READINESS_MIXED_WAIT_NO_ORDER"
        classification = "J_MIXED_WAIT"

    return decision, classification, issues, stage_decisions


def extract_signal_snapshot(stage_summaries: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    h = stage_summaries.get("stage66h", {})
    i = stage_summaries.get("stage66i", {})
    if h:
        out["h64l_v2"] = {
            "decision": h.get("decision"),
            "classification": h.get("classification"),
            "signal_active": h.get("signal_evaluation", {}).get("signal_active"),
            "feature_date_utc": h.get("signal_evaluation", {}).get("feature_date_utc"),
            "rule_failures": h.get("signal_evaluation", {}).get("rule_failures", []),
            "ticket_path": h.get("ticket_path"),
        }
    if i:
        out["d3_h60"] = {
            "decision": i.get("decision"),
            "classification": i.get("classification"),
            "signal_active": i.get("signal_evaluation", {}).get("signal_active"),
            "feature_date_utc": i.get("signal_evaluation", {}).get("feature_date_utc"),
            "rule_failures": i.get("signal_evaluation", {}).get("rule_failures", []),
            "ticket_path": i.get("ticket_path"),
        }
    return out


def append_ledger(root: Path, ledger_path: Path, summary: Dict[str, Any]) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "generated_utc": summary.get("generated_utc"),
        "decision": summary.get("decision"),
        "classification": summary.get("classification"),
        "h64l_decision": summary.get("stage_decisions", {}).get("stage66h", {}).get("decision"),
        "d3_decision": summary.get("stage_decisions", {}).get("stage66i", {}).get("decision"),
        "h64l_signal_active": summary.get("signal_snapshot", {}).get("h64l_v2", {}).get("signal_active"),
        "d3_signal_active": summary.get("signal_snapshot", {}).get("d3_h60", {}).get("signal_active"),
        "h64l_ticket_path": summary.get("stage_decisions", {}).get("stage66h", {}).get("ticket_path"),
        "d3_ticket_path": summary.get("stage_decisions", {}).get("stage66i", {}).get("ticket_path"),
        "issues": ";".join(summary.get("issues", [])),
    }
    write_header = not ledger_path.exists()
    with ledger_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def write_report(path: Path, summary: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    h = summary.get("signal_snapshot", {}).get("h64l_v2", {})
    d = summary.get("signal_snapshot", {}).get("d3_h60", {})
    lines = [
        "# Stage66J Dual Readiness Daily Ops", "",
        "## Decision", "",
        f"- status: `{summary.get('status')}`",
        f"- decision: `{summary.get('decision')}`",
        f"- classification: `{summary.get('classification')}`", "",
        "## H64L v2 readiness", "",
        f"- decision: `{h.get('decision')}`",
        f"- signal_active: `{h.get('signal_active')}`",
        f"- feature_date_utc: `{h.get('feature_date_utc')}`",
        f"- ticket_path: `{h.get('ticket_path')}`", "",
        "## D3 H60 complementary readiness", "",
        f"- decision: `{d.get('decision')}`",
        f"- signal_active: `{d.get('signal_active')}`",
        f"- feature_date_utc: `{d.get('feature_date_utc')}`",
        f"- ticket_path: `{d.get('ticket_path')}`", "",
        "## Issues", "", 
    ]
    if summary.get("issues"):
        lines.extend([f"- `{x}`" for x in summary["issues"]])
    else:
        lines.append("- none")
    lines += ["", "## Hard blocks", ""]
    lines.extend([f"- `{x}`" for x in summary.get("hard_blocks", [])])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run Stage66J dual no-order readiness daily ops.")
    parser.add_argument("--root", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--no-run", action="store_true", help="Do not execute child stages; collect existing summaries only.")
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    cfg_path = Path(args.config).expanduser()
    if not cfg_path.is_absolute():
        cfg_path = root / cfg_path
    out_dir = Path(args.out).expanduser()
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = read_json(cfg_path)
    python_exe = cfg.get("python_executable") or sys.executable
    timeout_seconds = int(cfg.get("child_timeout_seconds", 600))
    ledger_path = root / cfg.get("ledger_path", "data/forward_shadow/stage66j_dual_readiness_daily_ops_ledger.csv")

    specs = resolve_stage_specs(root, cfg)
    run_results: Dict[str, Dict[str, Any]] = {}
    if args.no_run:
        for spec in specs:
            run_results[spec.stage_key] = {
                "stage_key": spec.stage_key,
                "enabled": spec.enabled,
                "attempted": False,
                "status": "COLLECT_ONLY_NO_RUN",
                "summary_path": rel(root, spec.summary_path),
                "summary_found": spec.summary_path.exists(),
                "summary_sha256": sha256_file(spec.summary_path),
            }
    else:
        for spec in specs:
            run_results[spec.stage_key] = run_stage(root, python_exe, spec, timeout_seconds)

    stage_summaries: Dict[str, Dict[str, Any]] = {}
    load_issues: List[str] = []
    for spec in specs:
        if not spec.enabled:
            continue
        if spec.summary_path.exists():
            try:
                stage_summaries[spec.stage_key] = read_json(spec.summary_path)
            except Exception as exc:
                load_issues.append(f"summary_read_error:{spec.stage_key}:{exc}")
        else:
            load_issues.append(f"summary_missing:{spec.stage_key}:{rel(root, spec.summary_path)}")

    decision, classification, issues, stage_decisions = classify_decisions(stage_summaries, run_results)
    issues.extend(load_issues)
    if load_issues and decision == "STAGE66J_DUAL_READINESS_WAIT_SIGNALS_NO_ORDER":
        decision = "STAGE66J_STOP_DAILY_OPS_INPUT_OR_STAGE_FAILURE_NO_ORDER"
        classification = "J_STOP"

    summary = {
        "stage": "Stage66J_DUAL_READINESS_DAILY_OPS",
        "status": "STAGE66J_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "generated_utc": utc_now(),
        "root": str(root),
        "config": rel(root, cfg_path),
        "hard_blocks": HARD_BLOCKS,
        "run_mode": "collect_only_no_run" if args.no_run else "execute_children_then_collect",
        "child_run_results": run_results,
        "stage_decisions": stage_decisions,
        "signal_snapshot": extract_signal_snapshot(stage_summaries),
        "issues": issues,
        "outputs": {
            "summary_json": rel(root, out_dir / "stage66j_dual_readiness_daily_ops_summary.json"),
            "report_md": rel(root, out_dir / "stage66j_dual_readiness_daily_ops_report.md"),
            "ledger_csv": rel(root, ledger_path),
        },
        "operator_instructions": [
            "No order may be placed from Stage66J.",
            "If a dry-run ticket appears, manually review it only.",
            "Real paper-order authorization requires a later explicit authorization package and user approval.",
            "Live and broker paths remain blocked.",
        ],
        "next_step": "Continue daily Stage66J. If any dry-run ticket becomes ready, manually review it and build a later explicit authorization package; otherwise keep H64L and D3 readiness running while considering only pre-registered additional theses.",
    }

    append_ledger(root, ledger_path, summary)
    summary_path = out_dir / "stage66j_dual_readiness_daily_ops_summary.json"
    report_path = out_dir / "stage66j_dual_readiness_daily_ops_report.md"
    write_json(summary_path, summary)
    write_report(report_path, summary)

    print(json.dumps({"decision": decision, "classification": classification, "summary_json": str(summary_path), "report_md": str(report_path)}, indent=2))
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
