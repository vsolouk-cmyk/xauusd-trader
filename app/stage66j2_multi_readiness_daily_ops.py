#!/usr/bin/env python3
"""Stage66J2 Multi-Readiness Daily Ops.

Aggregates the primary H64L v2 readiness path, the selected complementary D3 H60
readiness path, and backup complementary D1/D4 readiness paths. This stage is a
no-order daily operations dashboard only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
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
    "NO_ORDER_AUTHORIZATION_FROM_STAGE66J2",
    "NO_THRESHOLD_TUNING",
    "NO_PROMOTION_FROM_DAILY_OPS_ONLY",
]

WAIT_DECISION = "STAGE66J2_ALL_READINESS_WAIT_SIGNALS_NO_ORDER"
PRIMARY_TICKET_DECISION = "STAGE66J2_PRIMARY_OR_D3_DRY_RUN_TICKET_READY_REVIEW_NO_ORDER"
BACKUP_ACTIVE_DECISION = "STAGE66J2_BACKUP_SIGNAL_ACTIVE_REQUIRES_STAGE66L_NO_ORDER"
MIXED_REVIEW_DECISION = "STAGE66J2_MIXED_ACTIVE_SIGNALS_MANUAL_REVIEW_NO_ORDER"
ISSUE_DECISION = "STAGE66J2_INPUT_OR_CHILD_STAGE_ISSUE_STOP_NO_ORDER"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve(root: Path, p: str) -> Path:
    path = Path(p)
    if path.is_absolute():
        return path
    return root / path


def run_child(root: Path, child: Dict[str, Any]) -> Dict[str, Any]:
    label = child.get("stage_key", child.get("name", "child"))
    enabled = bool(child.get("enabled", True))
    summary_path = resolve(root, child["summary_path"])
    result: Dict[str, Any] = {
        "stage_key": label,
        "enabled": enabled,
        "attempted": False,
        "status": "SKIPPED_DISABLED" if not enabled else "NOT_RUN",
        "summary_path": child.get("summary_path"),
        "summary_found": summary_path.exists(),
        "summary_sha256": sha256_file(summary_path),
    }
    if not enabled:
        return result
    cmd_template = child.get("cmd", [])
    cmd = []
    for part in cmd_template:
        if part == "{python}":
            cmd.append(sys.executable)
        elif part == "{root}":
            cmd.append(str(root))
        else:
            cmd.append(str(resolve(root, part)) if part.startswith("app/") or part.startswith("configs/") or part.startswith("reports/") else str(part))
    result["attempted"] = True
    result["cmd"] = cmd
    try:
        proc = subprocess.run(cmd, cwd=str(root), text=True, capture_output=True, timeout=int(child.get("timeout_seconds", 900)))
        result["returncode"] = proc.returncode
        result["stdout_tail"] = proc.stdout[-2000:]
        result["stderr_tail"] = proc.stderr[-2000:]
        result["status"] = "PASS" if proc.returncode == 0 else "FAIL"
    except Exception as exc:  # pragma: no cover - defensive runtime reporting
        result["status"] = "EXCEPTION"
        result["error"] = repr(exc)
    result["summary_found"] = summary_path.exists()
    result["summary_sha256"] = sha256_file(summary_path)
    return result


def safe_get(d: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def compact_signal(snapshot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(snapshot, dict):
        return {
            "decision": None,
            "classification": None,
            "signal_active": None,
            "feature_date_utc": None,
            "ticket_path": None,
            "rule_failures": [],
        }
    return {
        "decision": snapshot.get("decision"),
        "classification": snapshot.get("classification"),
        "signal_active": bool(snapshot.get("signal_active")) if snapshot.get("signal_active") is not None else None,
        "feature_date_utc": snapshot.get("feature_date_utc"),
        "ticket_path": snapshot.get("ticket_path"),
        "rule_failures": snapshot.get("rule_failures", []),
    }


def backup_compact(item: Dict[str, Any]) -> Dict[str, Any]:
    rule = item.get("rule_lock", {}) or {}
    audit = item.get("audit_gate", {}) or {}
    readiness = item.get("readiness_gate", {}) or {}
    signal = item.get("signal_evaluation", {}) or {}
    metrics = audit.get("metrics_used", {}) or {}
    return {
        "rule_id": rule.get("rule_id"),
        "thesis_id": rule.get("thesis_id"),
        "rule_sha256": rule.get("rule_sha256"),
        "horizon_trading_days": rule.get("horizon_trading_days"),
        "audit_pass": bool(audit.get("all_gates_ok")),
        "signal_active": bool(readiness.get("backup_signal_active")) if readiness.get("backup_signal_active") is not None else bool(signal.get("signal_active")),
        "feature_date_utc": signal.get("feature_date_utc"),
        "rule_failures": signal.get("rule_failures", []),
        "trade_count": metrics.get("trade_count"),
        "mean_net_return_bps": metrics.get("mean_net_return_bps"),
        "win_rate": metrics.get("win_rate"),
        "ticket_generation_allowed_here": bool(readiness.get("ticket_generation_allowed_here", False)),
    }


def append_ledger(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "generated_utc",
        "decision",
        "classification",
        "h64l_signal_active",
        "d3_signal_active",
        "backup_active_count",
        "ready_backup_count",
        "active_backup_rule_ids",
        "h64l_feature_date_utc",
        "d3_feature_date_utc",
        "ticket_paths",
        "issue_count",
    ]
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow({k: row.get(k) for k in fieldnames})


def build_report(summary: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Stage66J2 Multi-Readiness Daily Ops")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append(f"- status: `{summary['status']}`")
    lines.append(f"- decision: `{summary['decision']}`")
    lines.append(f"- classification: `{summary['classification']}`")
    lines.append("")
    lines.append("## Signal snapshot")
    lines.append("")
    for key, label in [("h64l_v2", "H64L v2"), ("d3_h60", "D3 H60")]:
        s = summary["signal_snapshot"].get(key, {})
        lines.append(f"### {label}")
        lines.append("")
        lines.append(f"- decision: `{s.get('decision')}`")
        lines.append(f"- signal_active: `{s.get('signal_active')}`")
        lines.append(f"- feature_date_utc: `{s.get('feature_date_utc')}`")
        lines.append(f"- ticket_path: `{s.get('ticket_path')}`")
        failures = s.get("rule_failures") or []
        if failures:
            lines.append(f"- rule_failures: `{';'.join(str(x) for x in failures)}`")
        lines.append("")
    lines.append("## Backup readiness")
    lines.append("")
    for b in summary.get("backup_readiness", []):
        lines.append(f"### `{b.get('rule_id')}`")
        lines.append("")
        lines.append(f"- audit_pass: `{b.get('audit_pass')}`")
        lines.append(f"- signal_active: `{b.get('signal_active')}`")
        lines.append(f"- feature_date_utc: `{b.get('feature_date_utc')}`")
        lines.append(f"- trade_count: `{b.get('trade_count')}`")
        lines.append(f"- mean_net_return_bps: `{b.get('mean_net_return_bps')}`")
        lines.append(f"- win_rate: `{b.get('win_rate')}`")
        failures = b.get("rule_failures") or []
        if failures:
            lines.append(f"- rule_failures: `{';'.join(str(x) for x in failures)}`")
        lines.append("")
    lines.append("## Issues")
    lines.append("")
    if summary.get("issues"):
        for issue in summary["issues"]:
            lines.append(f"- `{issue}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Hard blocks")
    lines.append("")
    for b in HARD_BLOCKS:
        lines.append(f"- `{b}`")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage66j2_multi_readiness_daily_ops.json")
    ap.add_argument("--out", default="reports/stage66j2_multi_readiness_daily_ops")
    ap.add_argument("--no-run", action="store_true", help="Collect existing child outputs without executing child stages.")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cfg_path = resolve(root, args.config)
    cfg = read_json(cfg_path)
    out_dir = resolve(root, args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    child_results: Dict[str, Any] = {}
    if not args.no_run:
        for child in cfg.get("children", []):
            res = run_child(root, child)
            child_results[res["stage_key"]] = res
    else:
        for child in cfg.get("children", []):
            p = resolve(root, child["summary_path"])
            child_results[child.get("stage_key", child.get("name", "child"))] = {
                "stage_key": child.get("stage_key", child.get("name", "child")),
                "enabled": bool(child.get("enabled", True)),
                "attempted": False,
                "status": "COLLECT_ONLY",
                "summary_path": child.get("summary_path"),
                "summary_found": p.exists(),
                "summary_sha256": sha256_file(p),
            }

    issues: List[str] = []
    for key, res in child_results.items():
        if res.get("enabled") and not res.get("summary_found"):
            issues.append(f"{key}:SUMMARY_NOT_FOUND:{res.get('summary_path')}")
        if res.get("attempted") and res.get("status") != "PASS":
            issues.append(f"{key}:CHILD_RUN_STATUS_{res.get('status')}")

    stage66j_path = resolve(root, cfg["input_paths"]["stage66j_summary_path"])
    stage66k_path = resolve(root, cfg["input_paths"]["stage66k_summary_path"])
    stage66j = read_json(stage66j_path) if stage66j_path.exists() else {}
    stage66k = read_json(stage66k_path) if stage66k_path.exists() else {}
    if not stage66j:
        issues.append("STAGE66J_SUMMARY_MISSING_OR_INVALID")
    if not stage66k:
        issues.append("STAGE66K_SUMMARY_MISSING_OR_INVALID")

    h64l = compact_signal(safe_get(stage66j, ["signal_snapshot", "h64l_v2"], {}))
    d3 = compact_signal(safe_get(stage66j, ["signal_snapshot", "d3_h60"], {}))
    backups = [backup_compact(x) for x in stage66k.get("backup_readiness", [])] if isinstance(stage66k.get("backup_readiness"), list) else []

    active_backups = [b for b in backups if b.get("signal_active")]
    ready_backups = [b for b in backups if b.get("audit_pass")]
    primary_ticket_paths = [p for p in [h64l.get("ticket_path"), d3.get("ticket_path")] if p]

    if issues:
        decision = ISSUE_DECISION
        classification = "J2_STOP_ISSUES"
    elif primary_ticket_paths and active_backups:
        decision = MIXED_REVIEW_DECISION
        classification = "J2_MIXED_ACTIVE_MANUAL_REVIEW"
    elif primary_ticket_paths:
        decision = PRIMARY_TICKET_DECISION
        classification = "J2_PRIMARY_OR_D3_TICKET_READY"
    elif active_backups:
        decision = BACKUP_ACTIVE_DECISION
        classification = "J2_BACKUP_ACTIVE_NEEDS_STAGE66L"
    else:
        decision = WAIT_DECISION
        classification = "J2_WAIT_ALL_INACTIVE"

    generated = utc_now()
    ticket_paths = primary_ticket_paths[:]
    summary: Dict[str, Any] = {
        "stage": "Stage66J2_MULTI_READINESS_DAILY_OPS",
        "status": "STAGE66J2_COMPLETE_NO_PROMOTION" if not issues else "STAGE66J2_STOPPED_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "generated_utc": generated,
        "root": str(root),
        "config": str(cfg_path.relative_to(root)) if cfg_path.is_relative_to(root) else str(cfg_path),
        "run_mode": "collect_only" if args.no_run else "execute_children_then_collect",
        "child_run_results": child_results,
        "input_paths": cfg.get("input_paths", {}),
        "input_hashes": {
            "config_sha256": sha256_file(cfg_path),
            "stage66j_summary_sha256": sha256_file(stage66j_path),
            "stage66k_summary_sha256": sha256_file(stage66k_path),
        },
        "stage_decisions": {
            "stage66j": {
                "decision": stage66j.get("decision"),
                "classification": stage66j.get("classification"),
                "status": stage66j.get("status"),
            },
            "stage66k": {
                "decision": stage66k.get("decision"),
                "classification": stage66k.get("classification"),
                "status": stage66k.get("status"),
            },
        },
        "signal_snapshot": {
            "h64l_v2": h64l,
            "d3_h60": d3,
        },
        "backup_counts": {
            "configured_backup_count": len(backups),
            "ready_backup_count": len(ready_backups),
            "active_backup_count": len(active_backups),
        },
        "backup_readiness": backups,
        "active_backup_rule_ids": [b.get("rule_id") for b in active_backups],
        "ticket_paths": ticket_paths,
        "issues": issues,
        "hard_blocks": HARD_BLOCKS,
        "operator_instructions": [
            "No order may be placed from Stage66J2.",
            "If H64L or D3 dry-run ticket appears, manually review only.",
            "If a backup signal becomes active, build Stage66L no-broker dry-run ticket generator before any review.",
            "Any real paper-order authorization requires a later explicit authorization package and user approval.",
            "Broker, EA, paper-live, and live paths remain blocked.",
        ],
        "next_step": "Continue daily Stage66J2. If a primary/D3 dry-run ticket appears, manually review it; if a backup signal is active, build Stage66L no-broker dry-run ticket generator; otherwise wait for signals or add only explicitly pre-registered new theses.",
        "outputs": {
            "summary_json": str((out_dir / "stage66j2_multi_readiness_daily_ops_summary.json").relative_to(root)) if out_dir.is_relative_to(root) else str(out_dir / "stage66j2_multi_readiness_daily_ops_summary.json"),
            "report_md": str((out_dir / "stage66j2_multi_readiness_daily_ops_report.md").relative_to(root)) if out_dir.is_relative_to(root) else str(out_dir / "stage66j2_multi_readiness_daily_ops_report.md"),
            "ledger_csv": cfg.get("ledger_csv", "data/forward_shadow/stage66j2_multi_readiness_daily_ops_ledger.csv"),
        },
    }

    report = build_report(summary)
    summary_path = out_dir / "stage66j2_multi_readiness_daily_ops_summary.json"
    report_path = out_dir / "stage66j2_multi_readiness_daily_ops_report.md"
    write_json(summary_path, summary)
    report_path.write_text(report, encoding="utf-8")

    ledger_path = resolve(root, cfg.get("ledger_csv", "data/forward_shadow/stage66j2_multi_readiness_daily_ops_ledger.csv"))
    append_ledger(ledger_path, {
        "generated_utc": generated,
        "decision": decision,
        "classification": classification,
        "h64l_signal_active": h64l.get("signal_active"),
        "d3_signal_active": d3.get("signal_active"),
        "backup_active_count": len(active_backups),
        "ready_backup_count": len(ready_backups),
        "active_backup_rule_ids": ";".join(str(x) for x in summary["active_backup_rule_ids"] if x),
        "h64l_feature_date_utc": h64l.get("feature_date_utc"),
        "d3_feature_date_utc": d3.get("feature_date_utc"),
        "ticket_paths": ";".join(str(x) for x in ticket_paths),
        "issue_count": len(issues),
    })

    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "decision": summary["decision"],
        "classification": summary["classification"],
        "backup_active_count": len(active_backups),
        "summary_json": str(summary_path),
        "report_md": str(report_path),
    }, ensure_ascii=False, indent=2))
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
