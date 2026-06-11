#!/usr/bin/env python3
"""
Stage 18A — Unified Shadow Ops Cycle

Purpose:
- One-command manual workflow for current research-shadow operations.
- Import AMarkets CSVs once.
- Run both active forward/shadow collectors:
    A) Stage16C macro pressure/reversal sweep-reclaim candidate
    B) Stage17D broker-time PDH breakout continuation candidate
- Preserve separate reports for each candidate.
- Produce one consolidated dashboard report.

Active candidates:
1) Stage16C:
   prev_day_low_sweep_rejection + sweep_depth_ge_q50 + reclaim_lt_q50 + real_yield_10y_chg5_up
   LONG research shadow

2) Stage17D:
   pdh_breakout_continuation_long_h32_cool4
   LONG research shadow, broker bar time

Hard rules:
- Research shadow operations only.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


TOOL_VERSION = "v1"
DEFAULT_OUT_DIR = Path("data/reports/stage18a_unified_shadow_ops_cycle")

STAGE16E_JSON = Path("data/reports/stage16e_amarkets_csv_refresh_cycle/stage16e_amarkets_csv_refresh_cycle.json")
STAGE16C_JSON = Path("data/reports/stage16c_true_forward_shadow_collector/stage16c_true_forward_shadow_collector.json")
STAGE17D_JSON = Path("data/reports/stage17d_broker_time_forward_shadow_collector/stage17d_broker_time_forward_shadow_collector.json")


def now_utc() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc)).replace(microsecond=0)


def now_iso() -> str:
    return now_utc().isoformat()


def read_json(path: Path) -> Dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def run_cmd(cmd: List[str], timeout_sec: int) -> Dict:
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
        )
        return {
            "cmd": " ".join(cmd),
            "returncode": int(proc.returncode),
            "status": "ok" if proc.returncode == 0 else "failed",
            "stdout_tail": proc.stdout[-5000:],
            "stderr_tail": proc.stderr[-5000:],
        }
    except Exception as e:
        return {
            "cmd": " ".join(cmd),
            "returncode": None,
            "status": "exception",
            "stdout_tail": "",
            "stderr_tail": str(e)[-5000:],
        }


def import_csvs(csv_files: List[Path], timeout_sec: int) -> Dict:
    cmd = [
        sys.executable,
        "-m",
        "app.stage16e_amarkets_csv_refresh_cycle",
        "--filename-contains",
        "",
        "--no-cycle",
    ]
    for p in csv_files:
        cmd.extend(["--csv-file", str(p.expanduser())])
    return run_cmd(cmd, timeout_sec)


def run_stage16c(timeout_sec: int, scan_days: int) -> Dict:
    cmd = [
        sys.executable,
        "-m",
        "app.stage16c_true_forward_shadow_collector",
        "--scan-days",
        str(scan_days),
    ]
    return run_cmd(cmd, timeout_sec)


def run_stage17d(timeout_sec: int, scan_bars: int) -> Dict:
    cmd = [
        sys.executable,
        "-m",
        "app.stage17d_broker_time_forward_shadow_collector",
        "--scan-bars",
        str(scan_bars),
    ]
    return run_cmd(cmd, timeout_sec)


def stage16_status(report: Dict) -> Dict:
    return {
        "final_decision": report.get("final_decision"),
        "bar_state": {
            "latest_m15_bar_utc": report.get("source", {}).get("m15_latest_bar") or report.get("bar_state", {}).get("latest_completed_m15_broker_time"),
            "collector_start_utc": report.get("collector_start_utc"),
        },
        "counts": report.get("counts", {}),
        "closed_metrics": report.get("closed_valid_forward_metrics", {}),
    }


def stage17_status(report: Dict) -> Dict:
    return {
        "final_decision": report.get("final_decision"),
        "bar_state": report.get("bar_state", {}),
        "counts": report.get("counts", {}),
        "closed_metrics": report.get("closed_valid_metrics", {}),
    }


def decide(import_result: Dict, s16_result: Dict, s17_result: Dict, s16_report: Dict, s17_report: Dict) -> Tuple[str, List[str]]:
    reasons: List[str] = []

    if import_result.get("status") != "ok":
        return "UNIFIED_CYCLE_IMPORT_FAILED", ["CSV import failed; collectors were not reliable."]

    if s16_result.get("status") != "ok" and s17_result.get("status") != "ok":
        return "UNIFIED_CYCLE_BOTH_COLLECTORS_FAILED", ["Both collectors failed."]

    s16d = s16_report.get("final_decision")
    s17d = s17_report.get("final_decision")
    s16c = s16_report.get("counts", {})
    s17c = s17_report.get("counts", {})

    open16 = int(s16c.get("open_valid_forward_rows", 0) or s16c.get("open_valid_rows", 0) or 0)
    closed16 = int(s16c.get("closed_valid_forward_rows", 0) or s16c.get("closed_valid_rows", 0) or 0)
    open17 = int(s17c.get("open_valid_rows", 0) or 0)
    closed17 = int(s17c.get("closed_valid_rows", 0) or 0)
    late17 = int(s17c.get("late_detected_this_run", 0) or 0) + int(s17c.get("late_invalid_rows", 0) or 0)

    if open16 or open17:
        return "UNIFIED_FORWARD_SIGNAL_OPEN", ["At least one active candidate has a valid open forward-shadow signal."]

    if closed16 or closed17:
        return "UNIFIED_FORWARD_OUTCOME_AVAILABLE", ["At least one active candidate has a closed valid forward-shadow outcome."]

    if late17:
        return "UNIFIED_LATE_DETECTED_REVIEW_CADENCE", ["Stage17D found late-detected signals; refresh cadence may be too slow."]

    # Normal active/no-signal state.
    reasons.append(f"Stage16C decision: {s16d}")
    reasons.append(f"Stage17D decision: {s17d}")
    return "UNIFIED_ACTIVE_NO_SIGNAL_YET", reasons


def run(out_dir: Path, csv_files: List[Path], timeout_sec: int, scan_days16: int, scan_bars17: int, skip_stage16: bool, skip_stage17: bool) -> int:
    generated = now_iso()
    out_dir.mkdir(parents=True, exist_ok=True)

    import_result = import_csvs(csv_files, timeout_sec)
    import_report = read_json(STAGE16E_JSON)

    if skip_stage16:
        s16_result = {"status": "skipped", "returncode": None, "cmd": "skipped"}
        s16_report = read_json(STAGE16C_JSON)
    else:
        s16_result = run_stage16c(timeout_sec, scan_days16)
        s16_report = read_json(STAGE16C_JSON)

    if skip_stage17:
        s17_result = {"status": "skipped", "returncode": None, "cmd": "skipped"}
        s17_report = read_json(STAGE17D_JSON)
    else:
        s17_result = run_stage17d(timeout_sec, scan_bars17)
        s17_report = read_json(STAGE17D_JSON)

    final_decision, reasons = decide(import_result, s16_result, s17_result, s16_report, s17_report)

    json_path = out_dir / "stage18a_unified_shadow_ops_cycle.json"
    md_path = out_dir / "stage18a_unified_shadow_ops_cycle.md"

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "inputs": {
            "csv_files": [str(p.expanduser()) for p in csv_files],
            "timeout_sec": int(timeout_sec),
            "scan_days16": int(scan_days16),
            "scan_bars17": int(scan_bars17),
            "skip_stage16": bool(skip_stage16),
            "skip_stage17": bool(skip_stage17),
        },
        "import_step": {
            "command": import_result,
            "report_summary": {
                "bar_state": import_report.get("bar_state", {}),
                "import_summary": import_report.get("import_summary", {}),
            },
        },
        "stage16c": {
            "command": s16_result,
            "summary": stage16_status(s16_report),
        },
        "stage17d": {
            "command": s17_result,
            "summary": stage17_status(s17_report),
        },
        "final_decision": final_decision,
        "reasons": reasons,
        "authorization_flags": {
            "trade_authorization": False,
            "ea_change_authorization": False,
            "paper_order_authorization": False,
            "live_order_authorization": False,
            "automatic_trading": False,
        },
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    imp = import_report.get("import_summary", {})
    ibar = import_report.get("bar_state", {})
    s16 = stage16_status(s16_report)
    s17 = stage17_status(s17_report)
    s16_counts = s16.get("counts", {})
    s17_counts = s17.get("counts", {})
    s16_m = s16.get("closed_metrics", {})
    s17_m = s17.get("closed_metrics", {})
    s17_bar = s17.get("bar_state", {})

    lines = [
        "# Stage 18A Unified Shadow Ops Cycle",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: unified research-shadow operations only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Final decision",
        f"- final_decision: `{final_decision}`",
        "",
        "## Reasons",
    ]
    for r in reasons:
        lines.append(f"- {r}")

    lines += [
        "",
        "## Import once",
        f"- import_status: `{import_result.get('status')}`",
        f"- files_imported: `{imp.get('files_imported')}`",
        f"- rows_upserted: `{imp.get('rows_upserted')}`",
        f"- before_latest_bar_utc: `{ibar.get('before_latest_bar_utc')}`",
        f"- after_latest_bar_utc: `{ibar.get('after_latest_bar_utc')}`",
        f"- latest_changed: `{ibar.get('latest_changed')}`",
        "",
        "## Candidate A — Stage16C macro pressure/reversal sweep",
        f"- command_status: `{s16_result.get('status')}`",
        f"- final_decision: `{s16.get('final_decision')}`",
        f"- journal_rows: `{s16_counts.get('journal_rows')}`",
        f"- valid_forward_rows: `{s16_counts.get('valid_forward_rows')}`",
        f"- open_valid_forward_rows: `{s16_counts.get('open_valid_forward_rows') or s16_counts.get('open_valid_rows')}`",
        f"- closed_valid_forward_rows: `{s16_counts.get('closed_valid_forward_rows') or s16_counts.get('closed_valid_rows')}`",
        f"- closed_events: `{s16_m.get('events')}`",
        f"- closed_total: `{s16_m.get('total')}`",
        f"- closed_pf: `{s16_m.get('pf')}`",
        "",
        "## Candidate B — Stage17D PDH breakout continuation",
        f"- command_status: `{s17_result.get('status')}`",
        f"- final_decision: `{s17.get('final_decision')}`",
        f"- m1_last_broker_time: `{s17_bar.get('m1_last_broker_time')}`",
        f"- latest_completed_m15_broker_time: `{s17_bar.get('latest_completed_m15_broker_time')}`",
        f"- collector_start_bar_time: `{s17_bar.get('collector_start_bar_time')}`",
        f"- data_after_collector_start: `{s17_bar.get('data_after_collector_start')}`",
        f"- scan_candidates: `{s17_counts.get('scan_candidates')}`",
        f"- new_logged_this_run: `{s17_counts.get('new_logged_this_run')}`",
        f"- late_detected_this_run: `{s17_counts.get('late_detected_this_run')}`",
        f"- journal_rows: `{s17_counts.get('journal_rows')}`",
        f"- valid_forward_rows: `{s17_counts.get('valid_forward_rows')}`",
        f"- open_valid_rows: `{s17_counts.get('open_valid_rows')}`",
        f"- closed_valid_rows: `{s17_counts.get('closed_valid_rows')}`",
        f"- closed_events: `{s17_m.get('events')}`",
        f"- closed_total: `{s17_m.get('total')}`",
        f"- closed_pf: `{s17_m.get('pf')}`",
    ]

    if import_result.get("stderr_tail"):
        lines += ["", "## Import stderr tail", "```text", str(import_result.get("stderr_tail"))[-2000:], "```"]
    if s16_result.get("stderr_tail"):
        lines += ["", "## Stage16C stderr tail", "```text", str(s16_result.get("stderr_tail"))[-2000:], "```"]
    if s17_result.get("stderr_tail"):
        lines += ["", "## Stage17D stderr tail", "```text", str(s17_result.get("stderr_tail"))[-2000:], "```"]

    lines += [
        "",
        "## Interpretation",
        "- This runner is the preferred manual loop: import once, then produce separate candidate reports and one consolidated dashboard.",
        "- Stage16C and Stage17D remain independent candidates; one signal does not validate the other.",
        "- If V2/EA logs a signal, compare its timestamp and condition against the Stage16C/Stage17D journals, but do not treat it as an order signal.",
        "- Continue Stage17/Stage18 behavior discovery in parallel; successful candidates should join this unified cycle later.",
        "- No paper/live/order escalation is authorized.",
        "",
        "## Output files",
        f"- json: `{json_path}`",
        f"- md: `{md_path}`",
        "- Stage16C report: `data/reports/stage16c_true_forward_shadow_collector/stage16c_true_forward_shadow_collector.md`",
        "- Stage17D report: `data/reports/stage17d_broker_time_forward_shadow_collector/stage17d_broker_time_forward_shadow_collector.md`",
        "- Import report: `data/reports/stage16e_amarkets_csv_refresh_cycle/stage16e_amarkets_csv_refresh_cycle.md`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 18A unified shadow ops cycle: DONE")
    print(f"final_decision={final_decision}")
    print(f"stage16c={s16.get('final_decision')}")
    print(f"stage17d={s17.get('final_decision')}")
    print(f"Report: {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--csv-file", action="append", default=[], help="AMarkets CSV file. Can be repeated.")
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--timeout-sec", type=int, default=1200)
    p.add_argument("--scan-days16", type=int, default=10)
    p.add_argument("--scan-bars17", type=int, default=5000)
    p.add_argument("--skip-stage16", action="store_true")
    p.add_argument("--skip-stage17", action="store_true")
    args = p.parse_args()

    csv_files = [Path(x).expanduser() for x in args.csv_file]
    if not csv_files:
        csv_files = [
            Path("~/Downloads/amarkets_xauusd_1h.csv").expanduser(),
            Path("~/Downloads/amarkets_xauusd_1m.csv").expanduser(),
        ]

    return run(
        out_dir=Path(args.out_dir),
        csv_files=csv_files,
        timeout_sec=int(args.timeout_sec),
        scan_days16=int(args.scan_days16),
        scan_bars17=int(args.scan_bars17),
        skip_stage16=bool(args.skip_stage16),
        skip_stage17=bool(args.skip_stage17),
    )


if __name__ == "__main__":
    raise SystemExit(main())
