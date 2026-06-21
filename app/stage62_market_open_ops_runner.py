#!/usr/bin/env python3
"""
Stage62 market-open operations runner for XAUUSD project.

This script consolidates the manual market-open sequence without creating live/paper-live permission.
By default it is a preflight/dry-run report. Use --execute to run the local Stage52/58B/53/59 scripts.
Use --prepare-demo-signal to also generate a fresh Stage61D3 demo signal file for manual MT5 copy.

It never connects to a broker and never submits orders.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # keep runner non-fragile
        return {"_read_error": str(exc), "_path": str(path)}
    return None


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def load_config(root: Path, config_path: Path) -> Dict[str, Any]:
    cfg = read_json(config_path)
    if not isinstance(cfg, dict):
        raise SystemExit(f"Could not read config: {config_path}")
    return cfg


def resolve(root: Path, p: str) -> Path:
    path = Path(os.path.expanduser(p))
    if path.is_absolute():
        return path
    return root / path


def command_from_step(root: Path, step: Dict[str, Any]) -> List[str]:
    cmd = step.get("cmd")
    if not isinstance(cmd, list) or not cmd:
        raise ValueError(f"Invalid command for step {step.get('id')}")
    return [str(x).replace("{root}", str(root)) for x in cmd]


def check_step(root: Path, step: Dict[str, Any]) -> Dict[str, Any]:
    checks = []
    for key in ("required_paths", "expected_outputs"):
        for item in step.get(key, []) or []:
            path = resolve(root, item)
            checks.append({
                "type": key,
                "path": str(path),
                "exists": path.exists(),
            })
    required_ok = all(c["exists"] for c in checks if c["type"] == "required_paths")
    return {
        "step_id": step.get("id"),
        "label": step.get("label", step.get("id")),
        "required_ok": required_ok,
        "checks": checks,
    }


def run_step(root: Path, step: Dict[str, Any], timeout_sec: int) -> Dict[str, Any]:
    cmd = command_from_step(root, step)
    started = utc_now()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_sec,
        )
        return {
            "step_id": step.get("id"),
            "label": step.get("label", step.get("id")),
            "started_utc": started,
            "finished_utc": utc_now(),
            "cmd": cmd,
            "returncode": proc.returncode,
            "stdout_tail": proc.stdout[-4000:],
            "stderr_tail": proc.stderr[-4000:],
            "ok": proc.returncode == 0,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "step_id": step.get("id"),
            "label": step.get("label", step.get("id")),
            "started_utc": started,
            "finished_utc": utc_now(),
            "cmd": cmd,
            "returncode": None,
            "stdout_tail": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
            "ok": False,
            "error": f"timeout_after_{timeout_sec}_sec",
        }
    except Exception as exc:
        return {
            "step_id": step.get("id"),
            "label": step.get("label", step.get("id")),
            "started_utc": started,
            "finished_utc": utc_now(),
            "cmd": cmd,
            "returncode": None,
            "stdout_tail": "",
            "stderr_tail": "",
            "ok": False,
            "error": str(exc),
        }


def collect_status(root: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    status = {}
    for name, rel in (cfg.get("status_files") or {}).items():
        path = resolve(root, rel)
        status[name] = {
            "path": str(path),
            "exists": path.exists(),
            "json": read_json(path),
        }
    return status


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage62_market_open_ops.json")
    ap.add_argument("--out", default="reports/stage62_market_open_ops")
    ap.add_argument("--execute", action="store_true", help="Run the workflow steps. Default is preflight only.")
    ap.add_argument("--prepare-demo-signal", action="store_true", help="Include Stage61D3 demo signal generation step.")
    ap.add_argument("--continue-on-error", action="store_true")
    ap.add_argument("--timeout-sec", type=int, default=900)
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    out = resolve(root, args.out)
    cfg = load_config(root, resolve(root, args.config))

    base_steps = cfg.get("steps", []) or []
    demo_steps = cfg.get("demo_signal_steps", []) or []
    steps = list(base_steps)
    if args.prepare_demo_signal:
        steps.extend(demo_steps)

    preflight = [check_step(root, step) for step in steps]
    can_execute = all(p["required_ok"] for p in preflight)
    executions = []
    if args.execute:
        if not can_execute:
            executions.append({"ok": False, "error": "preflight_required_paths_failed", "step_id": "PRE_EXECUTION"})
        else:
            for step in steps:
                res = run_step(root, step, args.timeout_sec)
                executions.append(res)
                if not res.get("ok") and not args.continue_on_error:
                    break

    status = collect_status(root, cfg)
    failed_preflight = [p for p in preflight if not p["required_ok"]]
    failed_exec = [e for e in executions if not e.get("ok")]

    if args.execute and not failed_preflight and not failed_exec:
        decision = "MARKET_OPEN_OPS_SEQUENCE_EXECUTED_NO_PROMOTION"
        next_allowed = "REVIEW_STAGE52_STAGE58B_STAGE53_STAGE59_AND_OPTIONAL_STAGE61D_OUTPUTS_NO_PROMOTION"
    elif args.execute:
        decision = "MARKET_OPEN_OPS_EXECUTION_NEEDS_FIX_NO_PROMOTION"
        next_allowed = "FIX_FAILED_STEP_AND_RERUN_NO_PROMOTION"
    else:
        decision = "MARKET_OPEN_OPS_PREFLIGHT_READY_NO_PROMOTION" if not failed_preflight else "MARKET_OPEN_OPS_PREFLIGHT_HAS_MISSING_PATHS_NO_PROMOTION"
        next_allowed = "RUN_WITH_EXECUTE_AFTER_AMARKETS_EXPORTS_UPDATE_NO_PROMOTION"

    summary: Dict[str, Any] = {
        "stage": "Stage62_MARKET_OPEN_OPS_RUNNER_NO_PROMOTION",
        "status": "MARKET_OPEN_OPS_RUNNER_COMPLETE_NO_PROMOTION",
        "promotion": "NO_GO",
        "EA": "DEMO_HARNESS_ONLY_NO_LIVE_EA_PROMOTION",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "broker_connection_in_python": "DISABLED",
        "order_submission_in_python": "DISABLED",
        "decision": decision,
        "next_allowed_step": next_allowed,
        "root": str(root),
        "execute": args.execute,
        "prepare_demo_signal": args.prepare_demo_signal,
        "steps_requested": [s.get("id") for s in steps],
        "preflight": preflight,
        "executions": executions,
        "status_files": status,
        "failed_preflight_count": len(failed_preflight),
        "failed_execution_count": len(failed_exec),
        "generated_utc": utc_now(),
    }

    write_json(out / "stage62_market_open_ops_runner_summary.json", summary)

    check_rows = []
    for p in preflight:
        for c in p["checks"]:
            check_rows.append({
                "step_id": p["step_id"],
                "label": p["label"],
                "type": c["type"],
                "path": c["path"],
                "passed": c["exists"],
            })
    write_csv(out / "stage62_market_open_ops_runner_checks.csv", check_rows, ["step_id", "label", "type", "path", "passed"])

    lines = []
    lines.append("# Stage62 Market-Open Ops Runner")
    lines.append("")
    lines.append(f"- status: `{summary['status']}`")
    lines.append(f"- decision: `{decision}`")
    lines.append(f"- next_allowed_step: `{next_allowed}`")
    lines.append("- promotion: `NO_GO`")
    lines.append("- EA: `DEMO_HARNESS_ONLY_NO_LIVE_EA_PROMOTION`")
    lines.append("- paper_live: `NO_GO`")
    lines.append("- live: `NO_GO`")
    lines.append("")
    lines.append("## Steps")
    for p in preflight:
        lines.append(f"- `{p['step_id']}` required_ok=`{p['required_ok']}`")
    if executions:
        lines.append("")
        lines.append("## Execution")
        for e in executions:
            lines.append(f"- `{e.get('step_id')}` ok=`{e.get('ok')}` returncode=`{e.get('returncode')}`")
    lines.append("")
    lines.append("## Safety")
    lines.append("This runner does not connect Python to a broker and does not submit any order. Stage61 demo order tests remain manual MT5-only and demo-only.")
    (out / "stage62_market_open_ops_runner_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"decision": decision, "out": str(out), "failed_preflight_count": len(failed_preflight), "failed_execution_count": len(failed_exec)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
