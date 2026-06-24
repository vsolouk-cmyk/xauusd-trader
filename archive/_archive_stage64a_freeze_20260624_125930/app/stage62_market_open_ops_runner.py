#!/usr/bin/env python3
"""
Stage62 Market-Open Ops Runner - LoaderFix1
Adds mandatory Stage57A context table refresh after AMarkets import and before Stage58B.
No broker connection. No Python order submission.
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
from typing import Any, Dict, List, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_load_error": str(exc), "_path": str(path)}


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def tail_text(text: str, n: int = 4000) -> str:
    if text is None:
        return ""
    return text[-n:]


def run_cmd(root: Path, step_id: str, label: str, cmd: List[str], execute: bool) -> Dict[str, Any]:
    rec: Dict[str, Any] = {
        "step_id": step_id,
        "label": label,
        "cmd": cmd,
        "started_utc": utc_now(),
        "executed": execute,
    }
    if not execute:
        rec.update({"returncode": None, "stdout_tail": "", "stderr_tail": "", "ok": True, "finished_utc": utc_now()})
        return rec
    p = subprocess.run(cmd, cwd=str(root), text=True, capture_output=True)
    rec.update({
        "finished_utc": utc_now(),
        "returncode": p.returncode,
        "stdout_tail": tail_text(p.stdout),
        "stderr_tail": tail_text(p.stderr),
        "ok": p.returncode == 0,
    })
    return rec


def path_check(root: Path, step_id: str, label: str, paths: List[str]) -> Dict[str, Any]:
    checks = []
    ok = True
    for rel in paths:
        p = root / rel
        exists = p.exists()
        checks.append({"path": str(p), "exists": exists})
        ok = ok and exists
    return {"step_id": step_id, "label": label, "required_ok": ok, "checks": checks}


def build_steps(root: Path, out: Path, prepare_demo_signal: bool, skip_context_refresh: bool) -> List[Dict[str, Any]]:
    steps: List[Dict[str, Any]] = []
    py = "python3"
    steps.append({
        "step_id": "S52_IMPORT_AND_RAW_FORWARD",
        "label": "Import latest AMarkets exports and run raw Stage51 forward shadow",
        "required_paths": [
            "app/stage52_import_then_forward_shadow.py",
            "data/broker_normalized/amarkets_multitf.sqlite",
            "reports/stage48f/stage48f_cost_model.json",
            "reports/stage51_volatility_squeeze/stage51_volatility_squeeze_breakout_candidates.csv",
        ],
        "cmd": [py, "app/stage52_import_then_forward_shadow.py", "--root", ".", "--input-dir", "~/Downloads", "--db", "data/broker_normalized/amarkets_multitf.sqlite", "--cost-model", "reports/stage48f/stage48f_cost_model.json", "--candidates", "reports/stage51_volatility_squeeze/stage51_volatility_squeeze_breakout_candidates.csv", "--out", "reports/stage52_forward_shadow"],
    })
    if not skip_context_refresh:
        steps.append({
            "step_id": "S57A_REFRESH_CONTEXT_TABLES",
            "label": "Refresh Stage57A context/regime tables after importer and before context forward",
            "required_paths": [
                "app/stage57a_context_source_precheck.py",
                "data/broker_normalized/amarkets_multitf.sqlite",
                "configs/stage57_context_source_manifest.json",
                "configs/stage57a_context_source_precheck.json",
            ],
            "cmd": [py, "app/stage57a_context_source_precheck.py", "--root", ".", "--db", "data/broker_normalized/amarkets_multitf.sqlite", "--context-manifest", "configs/stage57_context_source_manifest.json", "--config", "configs/stage57a_context_source_precheck.json", "--out", "reports/stage57_context_precheck"],
        })
    steps.append({
        "step_id": "S58B_CONTEXT_FORWARD",
        "label": "Run context-aware Stage51 forward shadow after refreshed context tables",
        "required_paths": [
            "app/stage58b_context_forward_shadow.py",
            "data/broker_normalized/amarkets_multitf.sqlite",
            "reports/stage48f/stage48f_cost_model.json",
            "reports/stage58_context_aware_stage51/stage58a_context_aware_stage51_regime_audit_candidates.csv",
            "reports/stage57_context_precheck/stage57a_m15_context_regime_table.csv",
            "reports/stage57_context_precheck/stage57a_m5_context_regime_table.csv",
        ],
        "cmd": [py, "app/stage58b_context_forward_shadow.py", "--root", ".", "--db", "data/broker_normalized/amarkets_multitf.sqlite", "--cost-model", "reports/stage48f/stage48f_cost_model.json", "--stage58a-candidates", "reports/stage58_context_aware_stage51/stage58a_context_aware_stage51_regime_audit_candidates.csv", "--m15-context", "reports/stage57_context_precheck/stage57a_m15_context_regime_table.csv", "--m5-context", "reports/stage57_context_precheck/stage57a_m5_context_regime_table.csv", "--out", "reports/stage58_context_forward_shadow"],
    })
    steps.append({
        "step_id": "S53_RAW_FORWARD_GATES",
        "label": "Run raw Stage52 forward gates",
        "required_paths": ["app/stage53_forward_shadow_gate_report.py", "configs/stage53_forward_shadow_gates.json"],
        "cmd": [py, "app/stage53_forward_shadow_gate_report.py", "--root", ".", "--state-db", "data/shadow/stage52_forward_shadow.sqlite", "--stage52-summary", "reports/stage52_forward_shadow/stage52_volatility_squeeze_forward_shadow_summary.json", "--runner-summary", "reports/stage52_forward_shadow/stage52_import_then_forward_shadow_summary.json", "--gates", "configs/stage53_forward_shadow_gates.json", "--out", "reports/stage53_forward_shadow_prep"],
    })
    steps.append({
        "step_id": "S59_CONTEXT_FORWARD_GATES",
        "label": "Run Stage58B context forward gates",
        "required_paths": ["app/stage59_context_forward_gate_report.py", "configs/stage59_context_forward_gates.json", "reports/stage58_context_aware_stage51/stage58a_context_aware_stage51_regime_audit_candidates.csv"],
        "cmd": [py, "app/stage59_context_forward_gate_report.py", "--root", ".", "--state-db", "data/shadow/stage58b_context_forward_shadow.sqlite", "--stage58b-summary", "reports/stage58_context_forward_shadow/stage58b_context_forward_shadow_summary.json", "--stage58a-candidates", "reports/stage58_context_aware_stage51/stage58a_context_aware_stage51_regime_audit_candidates.csv", "--gates", "configs/stage59_context_forward_gates.json", "--out", "reports/stage59_context_forward_gates"],
    })
    if prepare_demo_signal:
        steps.append({
            "step_id": "S61D3_PREPARE_TINY_DEMO_SIGNAL",
            "label": "Prepare one fresh EA-compatible tiny demo order signal for manual MT5 demo-only test",
            "required_paths": ["app/stage61d3_ea_compatible_tiny_demo_signal.py", "configs/stage61d3_ea_compatible_tiny_demo_signal.json"],
            "cmd": [py, "app/stage61d3_ea_compatible_tiny_demo_signal.py", "--root", ".", "--config", "configs/stage61d3_ea_compatible_tiny_demo_signal.json", "--out", "reports/stage61_demo_tiny_order"],
        })
    return steps


def status_files(root: Path) -> Dict[str, Any]:
    files = {
        "stage52_runner": "reports/stage52_forward_shadow/stage52_import_then_forward_shadow_summary.json",
        "stage52_forward": "reports/stage52_forward_shadow/stage52_volatility_squeeze_forward_shadow_summary.json",
        "stage57a_context": "reports/stage57_context_precheck/stage57a_context_source_precheck_summary.json",
        "stage58b_forward": "reports/stage58_context_forward_shadow/stage58b_context_forward_shadow_summary.json",
        "stage53_gate": "reports/stage53_forward_shadow_prep/stage53_forward_shadow_gate_summary.json",
        "stage59_gate": "reports/stage59_context_forward_gates/stage59_context_forward_gate_summary.json",
        "stage61d3_tiny_signal": "reports/stage61_demo_tiny_order/stage61d3_ea_compatible_tiny_demo_signal_summary.json",
    }
    out: Dict[str, Any] = {}
    for key, rel in files.items():
        p = root / rel
        out[key] = {"path": str(p), "exists": p.exists(), "json": load_json(p) if p.exists() else None}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage62_market_open_ops.json")
    ap.add_argument("--out", default="reports/stage62_market_open_ops")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--prepare-demo-signal", action="store_true")
    ap.add_argument("--skip-context-refresh", action="store_true")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out = (root / args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    steps = build_steps(root, out, args.prepare_demo_signal, args.skip_context_refresh)
    preflight = [path_check(root, s["step_id"], s["label"], s["required_paths"]) for s in steps]
    failed_preflight = [p for p in preflight if not p["required_ok"]]

    executions: List[Dict[str, Any]] = []
    if args.execute and not failed_preflight:
        for s in steps:
            rec = run_cmd(root, s["step_id"], s["label"], s["cmd"], True)
            executions.append(rec)
            if not rec.get("ok"):
                break
    else:
        for s in steps:
            executions.append(run_cmd(root, s["step_id"], s["label"], s["cmd"], False))

    failed_exec = [e for e in executions if not e.get("ok")]
    sf = status_files(root)

    summary = {
        "stage": "Stage62_MARKET_OPEN_OPS_RUNNER_LOADERFIX1_CONTEXT_REFRESH_NO_PROMOTION",
        "status": "MARKET_OPEN_OPS_RUNNER_COMPLETE_NO_PROMOTION" if not failed_exec and not failed_preflight else "MARKET_OPEN_OPS_RUNNER_HAS_FAILURES_NO_PROMOTION",
        "decision": "MARKET_OPEN_OPS_SEQUENCE_EXECUTED_WITH_CONTEXT_REFRESH_NO_PROMOTION" if args.execute and not failed_exec and not failed_preflight else "MARKET_OPEN_OPS_PREFLIGHT_OR_EXECUTION_REVIEW_NEEDED_NO_PROMOTION",
        "next_allowed_step": "REVIEW_STAGE52_STAGE58B_STAGE53_STAGE59_OUTPUTS_NO_PROMOTION",
        "promotion": "NO_GO",
        "EA": "DEMO_HARNESS_ONLY_NO_LIVE_EA_PROMOTION",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "broker_connection_in_python": "DISABLED",
        "order_submission_in_python": "DISABLED",
        "root": str(root),
        "execute": bool(args.execute),
        "prepare_demo_signal": bool(args.prepare_demo_signal),
        "skip_context_refresh": bool(args.skip_context_refresh),
        "steps_requested": [s["step_id"] for s in steps],
        "preflight": preflight,
        "executions": executions,
        "status_files": sf,
        "failed_preflight_count": len(failed_preflight),
        "failed_execution_count": len(failed_exec),
        "generated_utc": utc_now(),
    }
    write_json(out / "stage62_market_open_ops_runner_summary.json", summary)

    with (out / "stage62_market_open_ops_runner_checks.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["step_id", "check_type", "path", "passed"])
        w.writeheader()
        for p in preflight:
            for c in p["checks"]:
                w.writerow({"step_id": p["step_id"], "check_type": "required_path", "path": c["path"], "passed": c["exists"]})
        for e in executions:
            w.writerow({"step_id": e["step_id"], "check_type": "execution", "path": " ".join(e["cmd"]), "passed": e.get("ok")})

    md = []
    md.append("# Stage62 Market-Open Ops Runner LoaderFix1\n")
    md.append(f"- status: `{summary['status']}`")
    md.append(f"- decision: `{summary['decision']}`")
    md.append("- promotion: `NO_GO`")
    md.append("- EA: `DEMO_HARNESS_ONLY_NO_LIVE_EA_PROMOTION`")
    md.append("- paper_live: `NO_GO`")
    md.append("- live: `NO_GO`\n")
    md.append("## Important fix")
    md.append("Stage57A context/regime tables are now refreshed after AMarkets import and before Stage58B context-forward. This prevents stale context tables from suppressing Stage58B signals after market reopen.\n")
    md.append("## Executions")
    for e in executions:
        md.append(f"- `{e['step_id']}` ok=`{e.get('ok')}` returncode=`{e.get('returncode')}`")
    md.append("\n## Safety")
    md.append("This runner does not connect Python to a broker and does not submit any order. Demo order tests remain manual MT5-only and demo-only.")
    (out / "stage62_market_open_ops_runner_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "decision": summary["decision"],
        "failed_preflight_count": len(failed_preflight),
        "failed_execution_count": len(failed_exec),
        "out": str(out),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
