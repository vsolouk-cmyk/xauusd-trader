#!/usr/bin/env python3
"""
Stage 17E — PDH Forward Refresh Cycle

Purpose:
- One-command operational research cycle for the Stage17D broker-time forward collector.
- Import the known AMarkets CSV files.
- Run Stage17D broker-time forward shadow collector.
- Summarize whether we have:
    - fresh broker-time data,
    - no signal yet,
    - open valid forward signal,
    - closed forward outcome,
    - late-detected invalid signals.

Default files:
- ~/Downloads/amarkets_xauusd_1h.csv
- ~/Downloads/amarkets_xauusd_1m.csv

Hard rules:
- Research shadow cycle only.
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
DEFAULT_OUT_DIR = Path("data/reports/stage17e_pdh_forward_refresh_cycle")
DEFAULT_STAGE16E_REPORT = Path("data/reports/stage16e_amarkets_csv_refresh_cycle/stage16e_amarkets_csv_refresh_cycle.json")
DEFAULT_STAGE17D_REPORT = Path("data/reports/stage17d_broker_time_forward_shadow_collector/stage17d_broker_time_forward_shadow_collector.json")


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
            "stdout_tail": proc.stdout[-4000:],
            "stderr_tail": proc.stderr[-4000:],
        }
    except Exception as e:
        return {
            "cmd": " ".join(cmd),
            "returncode": None,
            "status": "exception",
            "stdout_tail": "",
            "stderr_tail": str(e)[-4000:],
        }


def run_import(csv_files: List[Path], timeout_sec: int) -> Dict:
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
    return run_cmd(cmd, timeout_sec=timeout_sec)


def run_stage17d(timeout_sec: int, force_reset: bool, scan_bars: int) -> Dict:
    cmd = [
        sys.executable,
        "-m",
        "app.stage17d_broker_time_forward_shadow_collector",
        "--scan-bars",
        str(scan_bars),
    ]
    if force_reset:
        cmd.append("--force-reset")
    return run_cmd(cmd, timeout_sec=timeout_sec)


def decide(import_result: Dict, collector_result: Dict, import_report: Dict, collector_report: Dict) -> Tuple[str, List[str]]:
    reasons: List[str] = []

    if import_result.get("status") != "ok":
        return "REFRESH_CYCLE_IMPORT_FAILED", ["Stage16E CSV import command failed."]

    if collector_result.get("status") != "ok":
        return "REFRESH_CYCLE_COLLECTOR_FAILED", ["Stage17D collector command failed."]

    stage17d_decision = collector_report.get("final_decision")
    counts = collector_report.get("counts", {})
    bar_state = collector_report.get("bar_state", {})

    if stage17d_decision == "BROKER_FORWARD_SIGNAL_OPEN":
        return "REFRESH_CYCLE_FORWARD_SIGNAL_OPEN", ["A valid broker-time forward shadow signal is open/pending outcome."]

    if stage17d_decision in {
        "BROKER_FORWARD_OUTCOMES_AVAILABLE_INSUFFICIENT_SAMPLE",
        "BROKER_FORWARD_SHADOW_POSITIVE_EARLY",
        "BROKER_FORWARD_SHADOW_WEAK_OR_NEGATIVE",
    }:
        return "REFRESH_CYCLE_FORWARD_OUTCOME_AVAILABLE", ["At least one valid broker-time forward outcome is available."]

    if counts.get("late_detected_this_run", 0) > 0 or stage17d_decision == "BROKER_FORWARD_ONLY_LATE_DETECTED_SIGNALS":
        return "REFRESH_CYCLE_LATE_DETECTED_ONLY", ["Signals were found too late; refresh cadence is longer than the strategy horizon."]

    if not bar_state.get("data_after_collector_start", False):
        return "REFRESH_CYCLE_WAITING_FOR_NEW_BROKER_BARS", ["No completed broker-time M15 bar after collector boundary yet."]

    if stage17d_decision == "BROKER_FORWARD_ACTIVE_NO_SIGNAL_YET":
        return "REFRESH_CYCLE_ACTIVE_NO_SIGNAL_YET", ["Fresh broker-time data exists; no valid PDH breakout signal yet."]

    if stage17d_decision == "BROKER_FORWARD_WAITING_FOR_NEW_BAR_DATA":
        return "REFRESH_CYCLE_WAITING_FOR_NEW_BROKER_BARS", ["Collector is waiting for new broker-time bars."]

    reasons.append(f"Stage17D decision: {stage17d_decision}")
    return "REFRESH_CYCLE_REVIEW_STAGE17D", reasons


def run(out_dir: Path, csv_files: List[Path], timeout_sec: int, force_reset: bool, scan_bars: int) -> int:
    generated = now_iso()
    out_dir.mkdir(parents=True, exist_ok=True)

    import_result = run_import(csv_files, timeout_sec=timeout_sec)
    import_report = read_json(DEFAULT_STAGE16E_REPORT)

    collector_result = run_stage17d(timeout_sec=timeout_sec, force_reset=force_reset, scan_bars=scan_bars)
    collector_report = read_json(DEFAULT_STAGE17D_REPORT)

    final_decision, reasons = decide(import_result, collector_result, import_report, collector_report)

    json_path = out_dir / "stage17e_pdh_forward_refresh_cycle.json"
    md_path = out_dir / "stage17e_pdh_forward_refresh_cycle.md"

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "inputs": {
            "csv_files": [str(p.expanduser()) for p in csv_files],
            "timeout_sec": int(timeout_sec),
            "force_reset": bool(force_reset),
            "scan_bars": int(scan_bars),
        },
        "import_result": import_result,
        "import_report_summary": {
            "tool_version": import_report.get("tool_version"),
            "bar_state": import_report.get("bar_state", {}),
            "import_summary": import_report.get("import_summary", {}),
        },
        "collector_result": collector_result,
        "collector_report_summary": {
            "tool_version": collector_report.get("tool_version"),
            "final_decision": collector_report.get("final_decision"),
            "bar_state": collector_report.get("bar_state", {}),
            "counts": collector_report.get("counts", {}),
            "closed_valid_metrics": collector_report.get("closed_valid_metrics", {}),
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

    import_summary = import_report.get("import_summary", {})
    import_bar = import_report.get("bar_state", {})
    cbar = collector_report.get("bar_state", {})
    counts = collector_report.get("counts", {})
    cm = collector_report.get("closed_valid_metrics", {})

    lines = [
        "# Stage 17E PDH Forward Refresh Cycle",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: research shadow cycle only. No EA change, no automatic trading, no paper/live authorization.",
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
        "## Import step",
        f"- status: `{import_result.get('status')}`",
        f"- returncode: `{import_result.get('returncode')}`",
        f"- files_imported: `{import_summary.get('files_imported')}`",
        f"- rows_upserted: `{import_summary.get('rows_upserted')}`",
        f"- before_latest_bar_utc: `{import_bar.get('before_latest_bar_utc')}`",
        f"- after_latest_bar_utc: `{import_bar.get('after_latest_bar_utc')}`",
        f"- latest_changed: `{import_bar.get('latest_changed')}`",
        "",
        "## Stage17D collector step",
        f"- status: `{collector_result.get('status')}`",
        f"- returncode: `{collector_result.get('returncode')}`",
        f"- stage17d_final_decision: `{collector_report.get('final_decision')}`",
        f"- m1_last_broker_time: `{cbar.get('m1_last_broker_time')}`",
        f"- latest_completed_m15_broker_time: `{cbar.get('latest_completed_m15_broker_time')}`",
        f"- collector_start_bar_time: `{cbar.get('collector_start_bar_time')}`",
        f"- data_after_collector_start: `{cbar.get('data_after_collector_start')}`",
        "",
        "## Journal counts",
        f"- scan_candidates: `{counts.get('scan_candidates')}`",
        f"- new_logged_this_run: `{counts.get('new_logged_this_run')}`",
        f"- skipped_before_start: `{counts.get('skipped_before_start')}`",
        f"- late_detected_this_run: `{counts.get('late_detected_this_run')}`",
        f"- resolved_this_run: `{counts.get('resolved_this_run')}`",
        f"- journal_rows: `{counts.get('journal_rows')}`",
        f"- valid_forward_rows: `{counts.get('valid_forward_rows')}`",
        f"- open_valid_rows: `{counts.get('open_valid_rows')}`",
        f"- closed_valid_rows: `{counts.get('closed_valid_rows')}`",
        f"- late_invalid_rows: `{counts.get('late_invalid_rows')}`",
        "",
        "## Closed valid forward metrics",
        f"- events: `{cm.get('events')}`",
        f"- total: `{cm.get('total')}`",
        f"- median: `{cm.get('median')}`",
        f"- pf: `{cm.get('pf')}`",
        f"- dd: `{cm.get('dd')}`",
    ]

    if import_result.get("stderr_tail"):
        lines += ["", "## Import stderr tail", "```text", str(import_result.get("stderr_tail"))[-2000:], "```"]
    if collector_result.get("stderr_tail"):
        lines += ["", "## Collector stderr tail", "```text", str(collector_result.get("stderr_tail"))[-2000:], "```"]

    lines += [
        "",
        "## Interpretation",
        "- This cycle imports the AMarkets CSVs and then runs the Stage17D broker-time collector.",
        "- A 24-hour cadence can still be too slow for an 8-hour horizon; late-detected signals are not forward proof.",
        "- Valid forward evidence requires the signal to be logged before its exit target is known.",
        "- No paper/live/order escalation is authorized.",
        "",
        "## Output files",
        f"- json: `{json_path}`",
        f"- md: `{md_path}`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 17E PDH forward refresh cycle: DONE")
    print(f"final_decision={final_decision}")
    print(f"stage17d_final_decision={collector_report.get('final_decision')}")
    print(f"valid_forward_rows={counts.get('valid_forward_rows')} open_valid={counts.get('open_valid_rows')} closed_valid={counts.get('closed_valid_rows')}")
    print(f"Report: {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--csv-file", action="append", default=[], help="AMarkets CSV file. Can be repeated.")
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--timeout-sec", type=int, default=1200)
    p.add_argument("--scan-bars", type=int, default=5000)
    p.add_argument("--force-reset", action="store_true", help="Pass through to Stage17D; normally do not use after first boundary is set.")
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
        force_reset=bool(args.force_reset),
        scan_bars=int(args.scan_bars),
    )


if __name__ == "__main__":
    raise SystemExit(main())
