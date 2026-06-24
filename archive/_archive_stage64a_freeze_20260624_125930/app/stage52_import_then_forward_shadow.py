#!/usr/bin/env python3
"""
Stage52 helper runner: run AMarkets fast persistent importer, then Stage52 true forward shadow.

This script does not implement trading logic. It orchestrates two existing scripts so the
persistent broker DB is updated before forward-shadow scans it.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_cmd(cmd: List[str], cwd: Path) -> Dict[str, Any]:
    started = utc_now_iso()
    proc = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)
    ended = utc_now_iso()
    return {
        "cmd": cmd,
        "cwd": str(cwd),
        "started_utc": started,
        "ended_utc": ended,
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-5000:],
        "stderr_tail": proc.stderr[-5000:],
        "ok": proc.returncode == 0,
    }


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"missing": True, "path": str(path)}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"read_error": repr(exc), "path": str(path)}


def write_report(path: Path, summary: Dict[str, Any]) -> None:
    importer = summary.get("importer_summary", {})
    forward = summary.get("forward_summary", {})
    lines = []
    lines.append("# Stage52 Import Then True Forward Shadow Runner")
    lines.append("")
    lines.append(f"- status: `{summary.get('status')}`")
    lines.append(f"- next_allowed_step: `{summary.get('next_allowed_step')}`")
    lines.append("- promotion: `NO_GO`")
    lines.append("- EA: `NO_GO`")
    lines.append("- paper_live: `NO_GO`")
    lines.append("- live: `NO_GO`")
    lines.append("")
    lines.append("## Importer")
    lines.append("")
    lines.append(f"- importer_status: `{importer.get('status')}`")
    lines.append(f"- changed_timeframes: `{importer.get('changed_timeframes')}`")
    lines.append(f"- skipped_timeframes: `{importer.get('skipped_timeframes')}`")
    lines.append(f"- missing_timeframes: `{importer.get('missing_timeframes')}`")
    rows = []
    for item in importer.get("imports", []) or []:
        rows.append(f"- {item.get('timeframe')}: status=`{item.get('status')}` mode=`{item.get('mode')}` rows_in_db=`{item.get('rows_in_db')}` raw_read=`{item.get('raw_rows_read_this_run')}`")
    if rows:
        lines.extend(rows)
    lines.append("")
    lines.append("## Forward-shadow")
    lines.append("")
    lines.append(f"- forward_status: `{forward.get('status')}`")
    lines.append(f"- mode: `{forward.get('mode')}`")
    lines.append(f"- previous_watermark_utc: `{forward.get('previous_watermark_utc')}`")
    lines.append(f"- latest_m15_time_utc: `{forward.get('latest_m15_time_utc')}`")
    lines.append(f"- new_watermark_utc: `{forward.get('new_watermark_utc')}`")
    lines.append(f"- generated_signals_this_run: `{forward.get('generated_signals_this_run')}`")
    lines.append(f"- inserted_new_signals: `{forward.get('inserted_new_signals')}`")
    lines.append(f"- newly_evaluated_signals: `{forward.get('newly_evaluated_signals')}`")
    state = forward.get("state", {}) or {}
    lines.append(f"- total_signals: `{state.get('total_signals')}`")
    lines.append(f"- pending_signals: `{state.get('pending_signals')}`")
    lines.append(f"- evaluated_signals: `{state.get('evaluated_signals')}`")
    lines.append(f"- true_forward_signals: `{state.get('true_forward_signals')}`")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("This runner exists only to avoid order-of-operations mistakes: AMarkets files are imported into the persistent broker DB first, then the Stage52 true-forward scan reads that updated DB. It does not authorize promotion, EA, paper-live, or live trading.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Stage49 fast importer, then Stage52 true forward shadow.")
    parser.add_argument("--root", default=".", help="Repo root")
    parser.add_argument("--input-dir", default="~/Downloads", help="AMarkets export directory")
    parser.add_argument("--db", default="data/broker_normalized/amarkets_multitf.sqlite")
    parser.add_argument("--cost-model", default="reports/stage48f/stage48f_cost_model.json")
    parser.add_argument("--candidates", default="reports/stage51_volatility_squeeze/stage51_volatility_squeeze_breakout_candidates.csv")
    parser.add_argument("--server-utc-offset-hours", type=float, default=3.0)
    parser.add_argument("--point-size", type=float, default=0.01)
    parser.add_argument("--out", default="reports/stage52_forward_shadow")
    parser.add_argument("--export-csv", default="never", choices=["never", "changed", "all"], help="Pass-through to fast importer")
    parser.add_argument("--reset-forward-state", action="store_true", help="One-time reset/init watermark. Do not use routinely.")
    parser.add_argument("--allow-historical-backfill", action="store_true", help="Pass-through diagnostic-only historical backfill flag if supported")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    out = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    importer_script = root / "app" / "stage49_amarkets_multitf_importer_fast.py"
    forward_script = root / "app" / "stage52_volatility_squeeze_forward_shadow.py"
    missing = [str(p) for p in [importer_script, forward_script] if not p.exists()]
    if missing:
        summary = {
            "stage": "Stage52_IMPORT_THEN_FORWARD_SHADOW_RUNNER",
            "status": "RUNNER_MISSING_DEPENDENCIES_NO_PROMOTION",
            "missing": missing,
            "promotion": "NO_GO", "EA": "NO_GO", "paper_live": "NO_GO", "live": "NO_GO",
            "generated_utc": utc_now_iso(),
        }
        (out / "stage52_import_then_forward_shadow_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        write_report(out / "stage52_import_then_forward_shadow_report.md", summary)
        print(json.dumps(summary, indent=2))
        return 2

    importer_cmd = [
        sys.executable, str(importer_script),
        "--root", str(root),
        "--input-dir", str(Path(args.input_dir).expanduser()),
        "--server-utc-offset-hours", str(args.server_utc_offset_hours),
        "--point-size", str(args.point_size),
        "--out", str(out),
    ]
    if args.export_csv != "never":
        importer_cmd += ["--export-csv", args.export_csv]

    importer_run = run_cmd(importer_cmd, root)

    forward_cmd = [
        sys.executable, str(forward_script),
        "--root", str(root),
        "--db", args.db,
        "--cost-model", args.cost_model,
        "--candidates", args.candidates,
        "--out", str(out),
    ]
    if args.reset_forward_state:
        forward_cmd.append("--reset-forward-state")
    if args.allow_historical_backfill:
        forward_cmd.append("--allow-historical-backfill")

    forward_run: Dict[str, Any]
    if importer_run["ok"]:
        forward_run = run_cmd(forward_cmd, root)
    else:
        forward_run = {"skipped": True, "reason": "importer_failed"}

    importer_summary = read_json(out / "stage49_fast_import_summary.json")
    forward_summary = read_json(out / "stage52_volatility_squeeze_forward_shadow_summary.json")

    ok = importer_run.get("ok") and forward_run.get("ok")
    summary: Dict[str, Any] = {
        "stage": "Stage52_IMPORT_THEN_TRUE_FORWARD_SHADOW_RUNNER",
        "patch": "Stage52_LOADERFIX2_COMBINED_IMPORT_AND_FORWARD_RUNNER",
        "status": "RUNNER_COMPLETE_NO_PROMOTION" if ok else "RUNNER_FAILED_NO_PROMOTION",
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "next_allowed_step": "CONTINUE_TRUE_FORWARD_SHADOW_UNTIL_MIN_EVIDENCE_NO_PROMOTION" if ok else "FIX_RUNNER_OR_INPUTS_NO_PROMOTION",
        "root": str(root),
        "input_dir": str(Path(args.input_dir).expanduser()),
        "db": args.db,
        "cost_model": args.cost_model,
        "candidates": args.candidates,
        "reset_forward_state": args.reset_forward_state,
        "importer_run": importer_run,
        "forward_run": forward_run,
        "importer_summary": importer_summary,
        "forward_summary": forward_summary,
        "generated_utc": utc_now_iso(),
    }

    (out / "stage52_import_then_forward_shadow_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(out / "stage52_import_then_forward_shadow_report.md", summary)
    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "importer_status": importer_summary.get("status"),
        "forward_status": forward_summary.get("status"),
        "inserted_new_signals": forward_summary.get("inserted_new_signals"),
        "newly_evaluated_signals": forward_summary.get("newly_evaluated_signals"),
        "out": str(out),
    }, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
