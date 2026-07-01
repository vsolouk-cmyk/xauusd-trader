#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

STAGE = "Stage142_DEMO_LOOP_SUPERVISOR"
STATUS = "STAGE142_COMPLETE_DEMO_LOOP_SUPERVISOR_READY"

DEFAULT_BARS = "/Users/vahid/Downloads/xauusd_fundamental_event_inbox/amarkets_xauusd_1h.csv"

SUMMARY_PATHS = {
    "stage134": "reports/stage134_demo_executor_pilot/stage134_demo_executor_pilot_summary.json",
    "stage138": "reports/stage138_broker_technical_demo_discovery/stage138_broker_technical_demo_discovery_summary.json",
    "stage139": "reports/stage139_demo_position_outcome_monitor/stage139_demo_position_outcome_monitor_summary.json",
    "stage140": "reports/stage140_demo_closed_deal_outcome_monitor/stage140_demo_closed_deal_outcome_monitor_summary.json",
    "stage141": "reports/stage141_demo_execution_outcome_ledger/stage141_demo_execution_outcome_ledger_summary.json",
}

RISK_BLOCKS = [
    "NO_ORDER_SEND_IN_STAGE142",
    "NO_POSITION_MODIFICATION_IN_STAGE142",
    "SUPERVISOR_ONLY",
    "STAGE134_EA_IS_ONLY_ORDER_SENDER",
    "DUPLICATE_GUARD_REQUIRED",
    "NEXT_ORDER_ONLY_ON_DISTINCT_SIGNAL_KEY",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_json_safe(path: Path) -> Dict[str, Any]:
    if not path.exists() or path.stat().st_size <= 0:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def write_rows(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    tmp.replace(path)


def append_rows(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    ensure_dir(path.parent)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def build_commands(root: Path, bars: str, run_stage138: bool, run_collectors: bool, run_ledger: bool, write_mt5: bool) -> List[Tuple[str, List[str]]]:
    py = sys.executable or "python3"
    cmds: List[Tuple[str, List[str]]] = []

    if run_stage138:
        cmd = [
            py, "app/stage138_broker_technical_demo_discovery.py",
            "--root", str(root),
            "--bars", bars,
            "--horizon-hours", "24",
            "--min-events", "25",
            "--min-mean-bps", "2.0",
            "--min-hit", "0.51",
        ]
        if write_mt5:
            cmd.append("--write-mt5")
        cmds.append(("stage138_refresh", cmd))

    if run_collectors:
        cmd134 = [py, "app/stage134_demo_executor_pilot_collector.py", "--root", str(root)]
        if write_mt5:
            cmd134.append("--write-mt5-status-kv")
        cmds.append(("stage134_collector", cmd134))

        cmd139 = [py, "app/stage139_demo_position_outcome_collector.py", "--root", str(root)]
        if write_mt5:
            cmd139.append("--write-mt5-status-kv")
        cmds.append(("stage139_position_collector", cmd139))

        cmd140 = [py, "app/stage140_demo_closed_deal_outcome_collector.py", "--root", str(root)]
        if write_mt5:
            cmd140.append("--write-mt5-status-kv")
        cmds.append(("stage140_closed_deal_collector", cmd140))

    if run_ledger:
        cmds.append(("stage141_ledger", [py, "app/stage141_demo_execution_outcome_ledger.py", "--root", str(root)]))

    return cmds


def run_commands(root: Path, cmds: List[Tuple[str, List[str]]], timeout_sec: int, dry_run: bool) -> List[Dict[str, Any]]:
    results = []
    for name, cmd in cmds:
        if dry_run:
            results.append({"name": name, "cmd": cmd, "returncode": 0, "dry_run": True, "stdout_tail": "", "stderr_tail": ""})
            continue
        try:
            p = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, timeout=timeout_sec)
            results.append({
                "name": name,
                "cmd": cmd,
                "returncode": p.returncode,
                "dry_run": False,
                "stdout_tail": (p.stdout or "")[-2000:],
                "stderr_tail": (p.stderr or "")[-2000:],
            })
        except subprocess.TimeoutExpired as e:
            results.append({
                "name": name,
                "cmd": cmd,
                "returncode": 124,
                "dry_run": False,
                "stdout_tail": (e.stdout or "")[-2000:] if isinstance(e.stdout, str) else "",
                "stderr_tail": "TIMEOUT",
            })
    return results


def classify_loop(s134: Dict[str, Any], s138: Dict[str, Any], s139: Dict[str, Any], s140: Dict[str, Any], s141: Dict[str, Any]) -> Dict[str, Any]:
    stage141_decision = str(s141.get("decision", ""))
    stage141_outcome = str(s141.get("outcome_status", ""))
    stage134_decision = str(s134.get("collector_decision", ""))
    stage139_decision = str(s139.get("collector_decision", ""))
    stage140_decision = str(s140.get("collector_decision", ""))
    stage138_rule = str(s138.get("selected_rule_id", ""))

    if "PROFIT_CONFIRMED_CONTINUE_LOOP" in stage141_decision:
        loop_decision = "STAGE142_LOOP_READY_FOR_NEXT_DISTINCT_SIGNAL_AFTER_PROFIT"
        next_action = "KEEP_STAGE138_STAGE134_RUNNING_WAIT_FOR_NEXT_DISTINCT_SIGNAL"
    elif "LOSS_CONFIRMED" in stage141_decision:
        loop_decision = "STAGE142_LOOP_CONTINUE_BUT_REVIEW_RULE_AFTER_LOSS"
        next_action = "CONTINUE_DEMO_LOOP_WITH_RULE_REVIEW_IF_LOSS_CLUSTER"
    elif "DEMO_ORDER_ACCEPTED" in stage134_decision and not stage141_outcome:
        loop_decision = "STAGE142_ORDER_ACCEPTED_OUTCOME_COLLECTION_REQUIRED"
        next_action = "RUN_STAGE139_STAGE140_STAGE141_UNTIL_OUTCOME_LEDGERED"
    elif "OPEN_DEMO_POSITION" in stage139_decision:
        loop_decision = "STAGE142_OPEN_POSITION_MONITORING_REQUIRED"
        next_action = "KEEP_STAGE139_RUNNING_UNTIL_CLOSE"
    elif "CLOSED_DEMO_DEAL" in stage140_decision and not stage141_outcome:
        loop_decision = "STAGE142_CLOSED_DEAL_FOUND_LEDGER_REQUIRED"
        next_action = "RUN_STAGE141_LEDGER"
    elif stage138_rule:
        loop_decision = "STAGE142_RULE_AVAILABLE_WAIT_FOR_STAGE134_NEXT_ACTION"
        next_action = "VERIFY_STAGE134_ARMED_AND_DUPLICATE_GUARD"
    else:
        loop_decision = "STAGE142_NO_ACTIVE_RULE_REFRESH_DISCOVERY"
        next_action = "RUN_STAGE138_REFRESH_OR_BROADER_DISCOVERY"

    return {
        "loop_decision": loop_decision,
        "next_action": next_action,
        "stage138_selected_rule_id": stage138_rule,
        "stage138_bar_max_utc": s138.get("bar_max_utc", ""),
        "stage134_collector_decision": stage134_decision,
        "stage139_collector_decision": stage139_decision,
        "stage140_collector_decision": stage140_decision,
        "stage141_decision": stage141_decision,
        "stage141_outcome_status": stage141_outcome,
        "stage141_signal_key": s141.get("signal_key", ""),
        "stage141_net_profit": s141.get("net_profit", ""),
        "stage141_bps_move": s141.get("bps_move", ""),
        "stage141_ledger_row_count": s141.get("ledger_row_count", ""),
    }


FIELDS = [
    "snapshot_utc",
    "loop_decision",
    "next_action",
    "stage138_selected_rule_id",
    "stage138_bar_max_utc",
    "stage134_collector_decision",
    "stage139_collector_decision",
    "stage140_collector_decision",
    "stage141_decision",
    "stage141_outcome_status",
    "stage141_signal_key",
    "stage141_net_profit",
    "stage141_bps_move",
    "stage141_ledger_row_count",
    "command_failures",
]


def run(root: Path, bars: str, run_stage138: bool, run_collectors: bool, run_ledger: bool, write_mt5: bool, dry_run: bool, timeout_sec: int) -> Dict[str, Any]:
    root = root.expanduser()
    out = ensure_dir(root / "reports/stage142_demo_loop_supervisor")
    data = ensure_dir(root / "data/demo_execution")
    generated = utc_now()

    cmds = build_commands(root, bars, run_stage138, run_collectors, run_ledger, write_mt5)
    command_results = run_commands(root, cmds, timeout_sec, dry_run)
    command_failures = [r for r in command_results if int(r.get("returncode", 0)) != 0]

    s = {k: read_json_safe(root / v) for k, v in SUMMARY_PATHS.items()}
    cls = classify_loop(s["stage134"], s["stage138"], s["stage139"], s["stage140"], s["stage141"])

    row = {
        "snapshot_utc": generated,
        **cls,
        "command_failures": len(command_failures),
    }
    latest_csv = out / "stage142_latest_demo_loop_supervisor_snapshot.csv"
    history_csv = data / "stage142_demo_loop_supervisor_snapshots.csv"
    risk_csv = out / "stage142_risk_manifest.csv"
    write_rows(latest_csv, [row], FIELDS)
    append_rows(history_csv, [row], FIELDS)
    write_rows(risk_csv, [{"risk_block": b, "status": "ACTIVE"} for b in RISK_BLOCKS], ["risk_block", "status"])

    summary = {
        "stage": STAGE,
        "generated_utc": generated,
        "status": STATUS,
        "root": str(root),
        "dry_run": dry_run,
        "commands_run": len(command_results),
        "command_failures": len(command_failures),
        "command_results": command_results,
        **cls,
        "latest_csv": str(latest_csv),
        "history_csv": str(history_csv),
        "risk_manifest_csv": str(risk_csv),
        "summary_json": str(out / "stage142_demo_loop_supervisor_summary.json"),
        "next": [
            "Keep Stage134 EA armed only on demo account.",
            "Keep Stage138 refresh running so Stage134 sees fresh rule-state.",
            "Allow new orders only for distinct signal keys and ledger every closed outcome.",
        ],
    }
    write_json(out / "stage142_demo_loop_supervisor_summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default="/Users/vahid/Desktop/xauusd-trader")
    ap.add_argument("--bars", default=DEFAULT_BARS)
    ap.add_argument("--skip-stage138", action="store_true")
    ap.add_argument("--skip-collectors", action="store_true")
    ap.add_argument("--skip-ledger", action="store_true")
    ap.add_argument("--write-mt5", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--timeout-sec", type=int, default=90)
    args = ap.parse_args()

    run(
        root=Path(args.root),
        bars=args.bars,
        run_stage138=not args.skip_stage138,
        run_collectors=not args.skip_collectors,
        run_ledger=not args.skip_ledger,
        write_mt5=args.write_mt5,
        dry_run=args.dry_run,
        timeout_sec=args.timeout_sec,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
