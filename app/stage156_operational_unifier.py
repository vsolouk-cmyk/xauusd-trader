#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

STAGE = "Stage156_OPERATIONAL_UNIFIER"
STATUS = "STAGE156_COMPLETE_OPERATIONAL_UNIFIER_READY"

DEFAULT_ROOT = "/Users/vahid/Desktop/xauusd-trader"
DEFAULT_MT5_FILES = (
    "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/"
    "drive_c/Program Files/MetaTrader 5/MQL5/Files"
)
DEFAULT_M5 = "/Users/vahid/Downloads/xauusd_fundamental_event_inbox/amarkets_xauusd_5m.csv"
DEFAULT_SCORE_CSV = (
    "/Users/vahid/Desktop/xauusd-trader/reports/"
    "stage150_mtf_separated_validation_discovery/m5/stage150_candidate_scores.csv"
)
DEFAULT_RISK_SUMMARY = (
    "/Users/vahid/Desktop/xauusd-trader/reports/"
    "stage145_clean_ledger_performance_gate/stage145_clean_ledger_performance_gate_summary.json"
)


def utc_now_dt() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def utc_now() -> str:
    return utc_now_dt().isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    s = str(value).strip().replace("Z", "+00:00")
    if not s:
        return None
    for fmt in (
        "%Y.%m.%d %H:%M:%S",
        "%Y.%m.%d %H:%M",
        "%Y.%m.%d",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def clean_col(c: str) -> str:
    return str(c).strip().strip("\ufeff").strip("<>").strip().lower()


def detect_delimiter(line: str) -> str:
    if "\t" in line and line.count("\t") >= line.count(","):
        return "\t"
    if ";" in line and line.count(";") > line.count(","):
        return ";"
    return ","


def latest_bar_time_from_csv(path: Path) -> Tuple[Optional[datetime], Optional[str], int]:
    if not path.exists():
        return None, None, 0
    # Read tail cheaply enough for normal CSV files. The AMarkets file is small enough for this use.
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    data_lines = [ln for ln in lines if ln.strip()]
    if not data_lines:
        return None, None, 0
    last_line = data_lines[-1]
    delim = detect_delimiter(data_lines[0])
    parts = last_line.split(delim)
    dt = None
    if len(parts) >= 2:
        dt = parse_dt(f"{parts[0]} {parts[1]}")
    if dt is None and parts:
        dt = parse_dt(parts[0])
    return dt, last_line, len(data_lines)


def read_kv(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "|" not in line:
            continue
        k, v = line.split("|", 1)
        out[k.strip()] = v.strip()
    return out


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def write_kv(path: Path, kv: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for k, v in kv.items():
            f.write(f"{k}|{'' if v is None else v}\n")
    tmp.replace(path)


def run_cmd(cmd: str, cwd: Path, timeout: int = 600) -> Dict[str, Any]:
    started = utc_now()
    p = subprocess.run(cmd, cwd=str(cwd), shell=True, text=True, capture_output=True, timeout=timeout)
    return {
        "cmd": cmd,
        "started_utc": started,
        "finished_utc": utc_now(),
        "returncode": p.returncode,
        "stdout_tail": p.stdout[-4000:],
        "stderr_tail": p.stderr[-4000:],
    }


def build_router_cmd(args: argparse.Namespace) -> str:
    parts = [
        shlex.quote(sys.executable),
        "app/stage154_active_shortlist_rule_router.py",
        "--root", shlex.quote(str(args.root)),
        "--bars", shlex.quote(str(args.bars_m5)),
        "--score-csv", shlex.quote(str(args.score_csv)),
        "--risk-summary", shlex.quote(str(args.risk_summary)),
        "--tf", shlex.quote(args.tf),
        "--timeframe-minutes", str(args.timeframe_minutes),
        "--max-feature-age-sec", str(args.max_feature_age_sec),
        "--timestamp-shift-hours", str(args.timestamp_shift_hours),
    ]
    if args.write_mt5:
        parts.append("--write-mt5")
    return " ".join(parts)


def infer_status(router_kv: Dict[str, str], stage134_kv: Dict[str, str], source_fresh: bool) -> Tuple[str, str]:
    decision = stage134_kv.get("decision", "")
    if decision == "BLOCKED_SIGNAL_STALE":
        return "BLOCKED_STALE", "Stage134 blocked because feature_date is stale; update source CSV or ensure router scheduler is running."
    if stage134_kv.get("open_positions") not in {"", "0", None}:
        return "POSITION_OPEN", "Stage134 sees an open position; duplicate orders correctly blocked."
    if router_kv.get("any_signal_active") == "true" and stage134_kv.get("signal_fresh") == "true":
        return "SIGNAL_READY_OR_RECENTLY_EXECUTED", "Router has active fresh signal; Stage134 may execute if not already executed and all guards pass."
    if router_kv.get("any_signal_active") == "false" and source_fresh:
        return "NO_ACTIVE_RULE", "Pipeline is fresh but no eligible active risk-guarded rule exists now."
    if not source_fresh:
        return "SOURCE_STALE", "Source M5 CSV is stale after timestamp normalization."
    return "REVIEW", "No immediate failure classification; inspect router/stage134 KVs."


def main() -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--mt5-files", default=DEFAULT_MT5_FILES)
    ap.add_argument("--bars-m5", default=DEFAULT_M5)
    ap.add_argument("--score-csv", default=DEFAULT_SCORE_CSV)
    ap.add_argument("--risk-summary", default=DEFAULT_RISK_SUMMARY)
    ap.add_argument("--tf", default="m5")
    ap.add_argument("--timeframe-minutes", type=int, default=5)
    ap.add_argument("--timestamp-shift-hours", type=float, default=-3.0)
    ap.add_argument("--max-feature-age-sec", type=int, default=7200)
    ap.add_argument("--write-mt5", action="store_true")
    ap.add_argument("--skip-router", action="store_true")
    ap.add_argument("--run-ledger", action="store_true")
    ap.add_argument("--db-update-command", default="", help="Optional shell command run before router, e.g. existing AMarkets DB importer/delta updater.")
    ap.add_argument("--status-wait-sec", type=float, default=2.0)
    args = ap.parse_args()

    root = Path(args.root).expanduser()
    mt5_files = Path(args.mt5_files).expanduser()
    bars_m5 = Path(args.bars_m5).expanduser()
    generated = utc_now()

    raw_dt, last_line, row_count = latest_bar_time_from_csv(bars_m5)
    normalized_dt = raw_dt + timedelta(hours=args.timestamp_shift_hours) if raw_dt else None
    now = utc_now_dt()
    feature_age_sec = int((now - normalized_dt).total_seconds()) if normalized_dt else None
    source_fresh = bool(feature_age_sec is not None and 0 <= feature_age_sec <= args.max_feature_age_sec)

    commands: List[Dict[str, Any]] = []
    if args.db_update_command:
        commands.append(run_cmd(args.db_update_command, cwd=root, timeout=1800))

    router_cmd = build_router_cmd(args)
    if not args.skip_router:
        commands.append(run_cmd(router_cmd, cwd=root, timeout=900))
        if args.status_wait_sec > 0:
            time.sleep(args.status_wait_sec)

    if args.run_ledger:
        commands.append(run_cmd(f"{shlex.quote(sys.executable)} app/stage144_demo_execution_ledger_audit.py", cwd=root, timeout=900))
        commands.append(run_cmd(f"{shlex.quote(sys.executable)} app/stage145_clean_ledger_performance_gate.py", cwd=root, timeout=900))

    router_kv_path = mt5_files / "xauusd_stage155_m5_active_router_rule_state_kv.csv"
    stage134_path = mt5_files / "xauusd_stage134_demo_executor_status_kv.csv"
    router_kv = read_kv(router_kv_path)
    stage134_kv = read_kv(stage134_path)
    classification, reason = infer_status(router_kv, stage134_kv, source_fresh)

    summary = {
        "stage": STAGE,
        "generated_utc": generated,
        "status": STATUS,
        "classification": classification,
        "reason": reason,
        "root": str(root),
        "mt5_files": str(mt5_files),
        "source": {
            "bars_m5": str(bars_m5),
            "exists": bars_m5.exists(),
            "row_count_including_header_if_any": row_count,
            "last_line": last_line,
            "raw_latest_time": raw_dt.isoformat().replace("+00:00", "Z") if raw_dt else "",
            "timestamp_shift_hours": args.timestamp_shift_hours,
            "normalized_latest_time": normalized_dt.isoformat().replace("+00:00", "Z") if normalized_dt else "",
            "feature_age_sec": feature_age_sec,
            "max_feature_age_sec": args.max_feature_age_sec,
            "source_fresh": source_fresh,
        },
        "router": {
            "cmd": router_cmd,
            "kv_path": str(router_kv_path),
            "decision": router_kv.get("decision", ""),
            "any_signal_active": router_kv.get("any_signal_active", ""),
            "selected_rule_id": router_kv.get("selected_rule_id", ""),
            "selected_family_key": router_kv.get("selected_family_key", ""),
            "active_shortlist_count": router_kv.get("active_shortlist_count", ""),
            "eligible_shortlist_count": router_kv.get("eligible_shortlist_count", ""),
            "risk_blocked_family_count": router_kv.get("risk_blocked_family_count", ""),
        },
        "stage134": {
            "kv_path": str(stage134_path),
            "decision": stage134_kv.get("decision", ""),
            "reason": stage134_kv.get("reason", ""),
            "feature_date": stage134_kv.get("feature_date", ""),
            "signal_fresh": stage134_kv.get("signal_fresh", ""),
            "signal_age_sec": stage134_kv.get("signal_age_sec", ""),
            "any_signal_active": stage134_kv.get("any_signal_active", ""),
            "open_positions": stage134_kv.get("open_positions", ""),
            "last_success_signal_key": stage134_kv.get("last_success_signal_key", ""),
            "last_attempt_signal_key": stage134_kv.get("last_attempt_signal_key", ""),
        },
        "commands": commands,
        "next": [
            "If classification is NO_ACTIVE_RULE, keep Stage155 running and do not patch unless inactivity is commercially unacceptable over a defined window.",
            "If classification is SOURCE_STALE or BLOCKED_STALE, update the M5 CSV and run this unifier again.",
            "Use --db-update-command only after identifying the repo's current AMarkets DB updater command.",
        ],
    }

    out_dir = ensure_dir(root / "reports/stage156_operational_unifier")
    write_json(out_dir / "stage156_operational_unifier_summary.json", summary)
    write_kv(root / "data/demo_execution/xauusd_stage156_operational_unifier_status_kv.csv", {
        "stage": STAGE,
        "generated_utc": generated,
        "classification": classification,
        "reason": reason,
        "source_fresh": str(source_fresh).lower(),
        "source_feature_age_sec": feature_age_sec,
        "router_decision": router_kv.get("decision", ""),
        "router_any_signal_active": router_kv.get("any_signal_active", ""),
        "stage134_decision": stage134_kv.get("decision", ""),
        "stage134_signal_fresh": stage134_kv.get("signal_fresh", ""),
        "stage134_open_positions": stage134_kv.get("open_positions", ""),
    })
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
