#!/usr/bin/env python3
"""Stage100 daily unified COT observer combo runner.

Runs local refresh stages and the Stage99 unified+COT observer bridge,
then validates and optionally copies unified_observer_signal.csv to MT5 MQL5/Files.
Observer-only. No order authorization.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_ORDER_SEND_IN_EA",
    "OBSERVER_ONLY_EA",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE100",
    "NO_THRESHOLD_TUNING_FROM_DAILY_UNIFIED_COT_COMBO",
]

EXPECTED_CSV = Path("data/mt5_bridge/unified_observer_signal.csv")


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


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def read_key_value_csv(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        return out
    # Preferred schema: key,value rows, optionally with header.
    start = 1 if len(rows[0]) >= 2 and rows[0][0].strip().lower() == "key" else 0
    for row in rows[start:]:
        if len(row) < 2:
            continue
        key = row[0].strip()
        if key:
            out[key] = row[1].strip()
    return out


def render_command(template: List[str], root: Path) -> List[str]:
    rendered: List[str] = []
    for token in template:
        rendered.append(
            token.replace("{root}", str(root)).replace("{python}", sys.executable)
        )
    return rendered


def run_child_stage(child: Dict[str, Any], root: Path, skip_refresh: bool) -> Dict[str, Any]:
    name = str(child.get("name", "UNKNOWN_STAGE"))
    enabled = bool(child.get("enabled", True))
    refresh_stage = bool(child.get("refresh_stage", False))
    result: Dict[str, Any] = {
        "name": name,
        "enabled": enabled,
        "refresh_stage": refresh_stage,
        "skipped": False,
        "command": [],
        "returncode": None,
        "status": "SKIPPED_DISABLED" if not enabled else "PENDING",
        "stdout_tail": "",
        "stderr_tail": "",
        "missing_script": False,
    }
    if not enabled:
        result["skipped"] = True
        return result
    if skip_refresh and refresh_stage:
        result["skipped"] = True
        result["status"] = "SKIPPED_REFRESH"
        return result
    command = render_command(list(child.get("command", [])), root)
    result["command"] = command
    if not command:
        result["status"] = "FAIL"
        result["stderr_tail"] = "empty child command"
        return result
    # Detect missing python script when command is like python script.py ...
    script_candidates = [Path(p) for p in command[1:2] if p.endswith(".py")]
    if script_candidates and not script_candidates[0].exists():
        result["status"] = "FAIL"
        result["returncode"] = 127
        result["missing_script"] = True
        result["stderr_tail"] = f"missing script: {script_candidates[0]}"
        return result
    proc = subprocess.run(
        command,
        cwd=str(root),
        text=True,
        capture_output=True,
        timeout=int(child.get("timeout_seconds", 600)),
    )
    result["returncode"] = proc.returncode
    result["stdout_tail"] = proc.stdout[-4000:]
    result["stderr_tail"] = proc.stderr[-4000:]
    result["status"] = "PASS" if proc.returncode == 0 else "FAIL"
    return result


def copy_to_mt5(csv_path: Path, mt5_files_dir: Optional[str], copy_enabled: bool) -> Dict[str, Any]:
    res: Dict[str, Any] = {
        "source": str(csv_path),
        "destination": None,
        "copied": False,
        "status": "SKIPPED_COPY_FLAG_FALSE" if not copy_enabled else "PENDING",
        "sha256": sha256_file(csv_path),
        "error": None,
    }
    if not copy_enabled:
        return res
    if not mt5_files_dir:
        res["status"] = "SKIPPED_NO_MT5_FILES_DIR"
        return res
    dst_dir = Path(os.path.expanduser(mt5_files_dir))
    try:
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / csv_path.name
        shutil.copy2(csv_path, dst)
        res["destination"] = str(dst)
        res["copied"] = True
        res["status"] = "COPIED"
        return res
    except Exception as exc:  # pragma: no cover - defensive
        res["status"] = "COPY_FAILED"
        res["error"] = repr(exc)
        return res


def write_report(path: Path, summary: Dict[str, Any]) -> None:
    lines: List[str] = []
    lines.append("# Stage100 Daily Unified COT Observer Combo")
    lines.append("")
    lines.append("## Decision")
    for k in ["status", "decision", "classification", "disposition"]:
        lines.append(f"- {k}: `{summary.get(k)}`")
    lines.append("")
    lines.append("## Child stages")
    for child in summary.get("child_runs", []):
        lines.append(f"- `{child.get('name')}`: status=`{child.get('status')}`, returncode=`{child.get('returncode')}`")
    lines.append("")
    snap = summary.get("csv_snapshot", {})
    lines.append("## Unified observer CSV snapshot")
    for k in ["feature_date", "latest_feature_date_utc", "schema_version", "rule_count", "mode", "any_signal_active", "selected_rule_id", "K06_primary_active", "K06_signal_active", "S83_14_signal_active", "S83_13_signal_active", "C96_07_active", "C96_07_signal_active"]:
        if k in snap:
            lines.append(f"- {k}: `{snap.get(k)}`")
    lines.append("")
    copy = summary.get("csv_copy", {})
    lines.append("## MT5 copy")
    lines.append(f"- `{copy.get('source')}` -> `{copy.get('destination')}`: status=`{copy.get('status')}`, copied=`{copy.get('copied')}`")
    lines.append("")
    lines.append("## Issues")
    issues = summary.get("issues", [])
    if issues:
        for issue in issues:
            lines.append(f"- `{issue}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Hard blocks")
    for hb in HARD_BLOCKS:
        lines.append(f"- `{hb}`")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--skip-refresh", action="store_true")
    p.add_argument("--copy-to-mt5-files", action="store_true")
    args = p.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    config_path = Path(args.config).expanduser().resolve()
    out_dir = Path(args.out).expanduser().resolve()
    cfg = load_json(config_path)

    child_runs = [run_child_stage(child, root, args.skip_refresh) for child in cfg.get("child_stages", [])]
    issues: List[str] = []
    for child in child_runs:
        if child.get("status") == "FAIL":
            issues.append(f"CHILD_STAGE_FAILED:{child.get('name')}")

    csv_path = root / str(cfg.get("unified_observer_csv", EXPECTED_CSV))
    csv_exists = csv_path.exists()
    if not csv_exists:
        issues.append("UNIFIED_OBSERVER_CSV_MISSING")

    snapshot = read_key_value_csv(csv_path)
    snapshot_meta = {
        "path": str(csv_path),
        "exists": csv_exists,
        "sha256": sha256_file(csv_path),
        **snapshot,
    }
    mode = snapshot.get("mode") or snapshot.get("ea_mode")
    if csv_exists and mode != "OBSERVER_ONLY_NO_TRADE":
        issues.append("UNIFIED_CSV_MODE_NOT_OBSERVER_ONLY")
    if csv_exists and snapshot.get("order_authorized", "false").lower() != "false":
        issues.append("UNIFIED_CSV_ORDER_AUTHORIZED_NOT_FALSE")
    if csv_exists and snapshot.get("broker_connection_allowed", "false").lower() != "false":
        issues.append("UNIFIED_CSV_BROKER_CONNECTION_NOT_FALSE")

    # Stage100 expects the Stage99 unified+COT schema and the C96_07 rule keys.
    schema_version = snapshot.get("schema_version", "")
    if csv_exists and schema_version and schema_version != "stage99_unified_observer_cot_v1":
        issues.append("UNIFIED_CSV_SCHEMA_NOT_STAGE99_COT")
    rule_count = snapshot.get("rule_count")
    if csv_exists and rule_count not in {None, "", "6", 6}:
        issues.append("UNIFIED_CSV_RULE_COUNT_NOT_6")
    if csv_exists and "C96_07_active" not in snapshot and "C96_07_signal_active" not in snapshot:
        issues.append("UNIFIED_CSV_C96_07_KEYS_MISSING")

    mt5_files_dir = cfg.get("mt5_files_dir")
    copy_result = copy_to_mt5(csv_path, mt5_files_dir, args.copy_to_mt5_files and csv_exists)
    if copy_result.get("status") == "COPY_FAILED":
        issues.append("MT5_COPY_FAILED")

    ok = not issues
    summary = {
        "stage": "Stage100_DAILY_UNIFIED_COT_OBSERVER_COMBO",
        "root": str(root),
        "config": str(config_path),
        "generated_utc": utc_now(),
        "status": "STAGE100_COMPLETE_NO_PROMOTION" if ok else "STAGE100_COMPLETE_WITH_ISSUES_NO_PROMOTION",
        "decision": "STAGE100_DAILY_UNIFIED_COT_COMBO_COMPLETE_OBSERVER_READY_NO_ORDER" if ok else "STAGE100_DAILY_UNIFIED_COT_COMBO_ISSUES_NO_ORDER",
        "classification": "S100_UNIFIED_COT_OBSERVER_READY" if ok else "S100_UNIFIED_COT_OBSERVER_ISSUES",
        "disposition": "DAILY_UNIFIED_COT_COMBO_OBSERVER_READY_NO_ORDER" if ok else "DAILY_UNIFIED_COT_COMBO_OBSERVER_ISSUES_NO_ORDER",
        "combo_role": "Local daily operator combo for macro/COT refresh and unified+COT observer-only MT5 bridge generation.",
        "skip_refresh": bool(args.skip_refresh),
        "child_runs": child_runs,
        "csv_snapshot": snapshot_meta,
        "csv_copy": copy_result,
        "issues": issues,
        "hard_blocks": HARD_BLOCKS,
        "operator_instructions": [
            "Stage100 cannot authorize orders.",
            "Use --skip-refresh when source files have not changed and only the unified+COT observer CSV must be rebuilt.",
            "Use --copy-to-mt5-files only after confirming the correct MQL5/Files path.",
            "EA files are not daily artifacts; only unified_observer_signal.csv is refreshed daily unless EA logic changes.",
        ],
        "outputs": {
            "summary_json": str(out_dir / "stage100_daily_unified_cot_observer_combo_summary.json"),
            "report_md": str(out_dir / "stage100_daily_unified_cot_observer_combo_report.md"),
            "unified_csv": str(csv_path),
        },
    }
    write_json(out_dir / "stage100_daily_unified_cot_observer_combo_summary.json", summary)
    write_report(out_dir / "stage100_daily_unified_cot_observer_combo_report.md", summary)
    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "decision": summary["decision"],
        "issues": issues,
        "summary_json": summary["outputs"]["summary_json"],
        "report_md": summary["outputs"]["report_md"],
    }, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
