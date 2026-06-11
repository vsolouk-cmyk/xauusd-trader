#!/usr/bin/env python3
"""
Stage 18A v2 — Unified Shadow Ops Cycle

Purpose:
- One-command manual workflow for current research-shadow operations.
- Import AMarkets CSVs once.
- Run active forward/shadow collectors:
    A) Stage16C macro pressure/reversal sweep-reclaim candidate
    B) Stage17D broker-time PDH breakout continuation candidate
    C) Stage18E broker-time shortlist candidates from Stage18D
- Preserve separate reports for each candidate family.
- Produce one consolidated dashboard report.

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


TOOL_VERSION = "v2_with_stage18e"
DEFAULT_OUT_DIR = Path("data/reports/stage18a_unified_shadow_ops_cycle")

STAGE16E_JSON = Path("data/reports/stage16e_amarkets_csv_refresh_cycle/stage16e_amarkets_csv_refresh_cycle.json")
STAGE16C_JSON = Path("data/reports/stage16c_true_forward_shadow_collector/stage16c_true_forward_shadow_collector.json")
STAGE17D_JSON = Path("data/reports/stage17d_broker_time_forward_shadow_collector/stage17d_broker_time_forward_shadow_collector.json")
STAGE18E_JSON = Path("data/reports/stage18e_shortlist_forward_shadow_collector/stage18e_shortlist_forward_shadow_collector.json")


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
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout_sec)
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
    cmd = [sys.executable, "-m", "app.stage16e_amarkets_csv_refresh_cycle", "--filename-contains", "", "--no-cycle"]
    for p in csv_files:
        cmd.extend(["--csv-file", str(p.expanduser())])
    return run_cmd(cmd, timeout_sec)


def run_stage16c(timeout_sec: int, scan_days: int) -> Dict:
    return run_cmd([sys.executable, "-m", "app.stage16c_true_forward_shadow_collector", "--scan-days", str(scan_days)], timeout_sec)


def run_stage17d(timeout_sec: int, scan_bars: int) -> Dict:
    return run_cmd([sys.executable, "-m", "app.stage17d_broker_time_forward_shadow_collector", "--scan-bars", str(scan_bars)], timeout_sec)


def run_stage18e(timeout_sec: int, scan_bars: int) -> Dict:
    return run_cmd([sys.executable, "-m", "app.stage18e_shortlist_forward_shadow_collector", "--scan-bars", str(scan_bars)], timeout_sec)


def extract_counts(report: Dict) -> Dict:
    return report.get("counts", {}) if isinstance(report, dict) else {}


def any_open_or_closed(report: Dict, mode: str) -> Tuple[int, int, int]:
    counts = extract_counts(report)
    if mode == "stage18e":
        csum = report.get("candidate_summary", [])
        open_rows = sum(int(r.get("open_valid_rows", 0) or 0) for r in csum)
        closed_rows = sum(int(r.get("closed_valid_rows", 0) or 0) for r in csum)
        late_rows = sum(int(r.get("late_invalid_rows", 0) or 0) for r in csum) + int(counts.get("late_detected_this_run", 0) or 0)
        return open_rows, closed_rows, late_rows

    open_rows = int(counts.get("open_valid_forward_rows", 0) or counts.get("open_valid_rows", 0) or 0)
    closed_rows = int(counts.get("closed_valid_forward_rows", 0) or counts.get("closed_valid_rows", 0) or 0)
    late_rows = int(counts.get("late_detected_this_run", 0) or counts.get("late_invalid_rows", 0) or counts.get("late_or_invalid_rows", 0) or 0)
    return open_rows, closed_rows, late_rows


def decide(import_result: Dict, command_results: Dict[str, Dict], reports: Dict[str, Dict]) -> Tuple[str, List[str]]:
    if import_result.get("status") != "ok":
        return "UNIFIED_CYCLE_IMPORT_FAILED", ["CSV import failed; collectors were not reliable."]

    failed = [k for k, v in command_results.items() if v.get("status") not in {"ok", "skipped"}]
    if len(failed) == len(command_results):
        return "UNIFIED_CYCLE_ALL_COLLECTORS_FAILED", ["All collectors failed."]

    open_total = 0
    closed_total = 0
    late_total = 0
    for key, rep in reports.items():
        mode = "stage18e" if key == "stage18e" else "normal"
        o, c, l = any_open_or_closed(rep, mode)
        open_total += o
        closed_total += c
        late_total += l

    if open_total > 0:
        return "UNIFIED_FORWARD_SIGNAL_OPEN", [f"At least one active candidate has open valid forward-shadow signal(s): open_total={open_total}."]
    if closed_total > 0:
        return "UNIFIED_FORWARD_OUTCOME_AVAILABLE", [f"At least one active candidate has closed valid forward outcome(s): closed_total={closed_total}."]
    if late_total > 0:
        return "UNIFIED_LATE_DETECTED_REVIEW_CADENCE", [f"Late/invalid detected signals exist: late_total={late_total}. Refresh cadence may be too slow."]

    reasons = []
    for key, rep in reports.items():
        reasons.append(f"{key} decision: {rep.get('final_decision')}")
    return "UNIFIED_ACTIVE_NO_SIGNAL_YET", reasons


def run(out_dir: Path, csv_files: List[Path], timeout_sec: int, scan_days16: int, scan_bars17: int, scan_bars18: int, skip_stage16: bool, skip_stage17: bool, skip_stage18: bool) -> int:
    generated = now_iso()
    out_dir.mkdir(parents=True, exist_ok=True)

    import_result = import_csvs(csv_files, timeout_sec)
    import_report = read_json(STAGE16E_JSON)

    command_results: Dict[str, Dict] = {}
    reports: Dict[str, Dict] = {}

    if skip_stage16:
        command_results["stage16c"] = {"status": "skipped", "returncode": None, "cmd": "skipped"}
    else:
        command_results["stage16c"] = run_stage16c(timeout_sec, scan_days16)
    reports["stage16c"] = read_json(STAGE16C_JSON)

    if skip_stage17:
        command_results["stage17d"] = {"status": "skipped", "returncode": None, "cmd": "skipped"}
    else:
        command_results["stage17d"] = run_stage17d(timeout_sec, scan_bars17)
    reports["stage17d"] = read_json(STAGE17D_JSON)

    if skip_stage18:
        command_results["stage18e"] = {"status": "skipped", "returncode": None, "cmd": "skipped"}
    else:
        command_results["stage18e"] = run_stage18e(timeout_sec, scan_bars18)
    reports["stage18e"] = read_json(STAGE18E_JSON)

    final_decision, reasons = decide(import_result, command_results, reports)

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
            "scan_bars18": int(scan_bars18),
            "skip_stage16": bool(skip_stage16),
            "skip_stage17": bool(skip_stage17),
            "skip_stage18": bool(skip_stage18),
        },
        "import_step": {
            "command": import_result,
            "report_summary": {
                "bar_state": import_report.get("bar_state", {}),
                "import_summary": import_report.get("import_summary", {}),
            },
        },
        "collector_commands": command_results,
        "collector_reports": reports,
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
    s16 = reports.get("stage16c", {})
    s17 = reports.get("stage17d", {})
    s18 = reports.get("stage18e", {})

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
        f"- command_status: `{command_results.get('stage16c', {}).get('status')}`",
        f"- final_decision: `{s16.get('final_decision')}`",
        f"- counts: `{extract_counts(s16)}`",
        "",
        "## Candidate B — Stage17D PDH breakout continuation",
        f"- command_status: `{command_results.get('stage17d', {}).get('status')}`",
        f"- final_decision: `{s17.get('final_decision')}`",
        f"- bar_state: `{s17.get('bar_state', {})}`",
        f"- counts: `{extract_counts(s17)}`",
        "",
        "## Candidate C/D — Stage18E shortlist collector",
        f"- command_status: `{command_results.get('stage18e', {}).get('status')}`",
        f"- final_decision: `{s18.get('final_decision')}`",
        f"- bar_state: `{s18.get('bar_state', {})}`",
        f"- counts: `{extract_counts(s18)}`",
        "",
        "### Stage18E candidate summary",
        "| Candidate | Variant | Family | Horizon min | Journal | Valid | Open | Closed | Late | Closed total | Closed PF |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in s18.get("candidate_summary", []):
        lines.append(
            f"| `{r.get('candidate_id')}` | `{r.get('variant')}` | `{r.get('family')}` | {r.get('horizon_minutes')} | {r.get('journal_rows')} | {r.get('valid_forward_rows')} | {r.get('open_valid_rows')} | {r.get('closed_valid_rows')} | {r.get('late_invalid_rows')} | {r.get('closed_total')} | {r.get('closed_pf')} |"
        )
    if not s18.get("candidate_summary"):
        lines.append("| none | none | none | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |")

    for key, result in command_results.items():
        if result.get("stderr_tail"):
            lines += ["", f"## {key} stderr tail", "```text", str(result.get("stderr_tail"))[-2000:], "```"]

    lines += [
        "",
        "## Interpretation",
        "- Stage18A v2 is now the preferred manual loop: import once, then run Stage16C, Stage17D, and Stage18E.",
        "- Stage18E adds only the Stage18D de-duplicated shortlist, not all Stage18C promotions.",
        "- Signals remain research-shadow observations only.",
        "- No paper/live/order escalation is authorized.",
        "",
        "## Output files",
        f"- json: `{json_path}`",
        f"- md: `{md_path}`",
        "- Stage16C report: `data/reports/stage16c_true_forward_shadow_collector/stage16c_true_forward_shadow_collector.md`",
        "- Stage17D report: `data/reports/stage17d_broker_time_forward_shadow_collector/stage17d_broker_time_forward_shadow_collector.md`",
        "- Stage18E report: `data/reports/stage18e_shortlist_forward_shadow_collector/stage18e_shortlist_forward_shadow_collector.md`",
        "- Import report: `data/reports/stage16e_amarkets_csv_refresh_cycle/stage16e_amarkets_csv_refresh_cycle.md`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 18A unified shadow ops cycle v2: DONE")
    print(f"final_decision={final_decision}")
    print(f"stage16c={s16.get('final_decision')}")
    print(f"stage17d={s17.get('final_decision')}")
    print(f"stage18e={s18.get('final_decision')}")
    print(f"Report: {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--csv-file", action="append", default=[], help="AMarkets CSV file. Can be repeated.")
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--timeout-sec", type=int, default=1200)
    p.add_argument("--scan-days16", type=int, default=10)
    p.add_argument("--scan-bars17", type=int, default=5000)
    p.add_argument("--scan-bars18", type=int, default=5000)
    p.add_argument("--skip-stage16", action="store_true")
    p.add_argument("--skip-stage17", action="store_true")
    p.add_argument("--skip-stage18", action="store_true")
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
        scan_bars18=int(args.scan_bars18),
        skip_stage16=bool(args.skip_stage16),
        skip_stage17=bool(args.skip_stage17),
        skip_stage18=bool(args.skip_stage18),
    )


if __name__ == "__main__":
    raise SystemExit(main())
