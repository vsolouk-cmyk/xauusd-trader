#!/usr/bin/env python3
"""
XAUUSD Stage Pipeline Runner

Runs the allowed research / dry-run validation steps in a reproducible order.

Hard rule:
- This script does NOT authorize demo, paper, or live orders.
- This script does NOT touch MT5 EA files.
- This script does NOT send orders.
- This script only orchestrates existing local validation modules.

Default modes:
- live_only: Stage 5B validator + Stage 5C outcome tracker.
- research: Stage 4G offset2/offset3 + Stage 4H offset2/offset3 + Stage 4I + Stage 4J.
- full: research + live_only.

Expected default inputs:
- ~/Downloads/amarkets_xauusd_1h.csv
- ~/Downloads/amarkets_xauusd_1m.csv
- MT5 Common Files/XAUUSD_DryRun_v1_signals.csv
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence


TOOL_VERSION = "v1"
STRATEGY_ID = "xauusd_long_tp24_sl15_no_london_v1"

DEFAULT_SIGNALS_CSV = Path("~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/XAUUSD_DryRun_v1_signals.csv").expanduser()
DEFAULT_H1_CSV = Path("~/Downloads/amarkets_xauusd_1h.csv").expanduser()
DEFAULT_M1_CSV = Path("~/Downloads/amarkets_xauusd_1m.csv").expanduser()
DEFAULT_OUT_DIR = Path("data/reports/stage_pipeline")


@dataclass
class Step:
    name: str
    command: List[str]
    report_paths: List[str]
    required_inputs: List[str]


@dataclass
class StepResult:
    name: str
    returncode: int
    status: str
    command: str
    stdout_tail: str
    stderr_tail: str
    report_paths: List[str]
    inferred_report_status: str
    started_utc: str
    finished_utc: str


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def tail_text(text: str, max_chars: int = 4000) -> str:
    text = text or ""
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def shell_join(cmd: Sequence[str]) -> str:
    return " ".join(shlex.quote(x) for x in cmd)


def path_exists(path_text: str) -> bool:
    return Path(path_text).expanduser().exists()


def infer_report_status(paths: Sequence[str]) -> str:
    """
    Pulls a coarse status from markdown reports when available.
    This is intentionally conservative and does not override step returncode.
    """
    statuses = []
    for p in paths:
        path = Path(p).expanduser()
        if not path.exists() or path.suffix.lower() != ".md":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        patterns = [
            r"Overall status:\s*\*\*([^*]+)\*\*",
            r"Stage [^\n:]+:\s*([A-Z_]+)",
            r"Top guard:\s*([A-Za-z0-9_]+).*status=([A-Z_]+)",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                statuses.append(" | ".join(g for g in m.groups() if g))
                break
    if not statuses:
        return "UNKNOWN"
    return "; ".join(statuses[:4])


def run_step(step: Step, continue_on_error: bool) -> StepResult:
    started = now_iso()
    missing = [p for p in step.required_inputs if not path_exists(p)]
    if missing:
        finished = now_iso()
        return StepResult(
            name=step.name,
            returncode=98,
            status="SKIPPED_MISSING_INPUT",
            command=shell_join(step.command),
            stdout_tail="",
            stderr_tail="Missing required input(s): " + ", ".join(missing),
            report_paths=step.report_paths,
            inferred_report_status="UNKNOWN",
            started_utc=started,
            finished_utc=finished,
        )

    proc = subprocess.run(
        step.command,
        text=True,
        capture_output=True,
        cwd=Path.cwd(),
    )
    finished = now_iso()
    status = "OK" if proc.returncode == 0 else "ERROR"
    inferred = infer_report_status(step.report_paths)
    result = StepResult(
        name=step.name,
        returncode=proc.returncode,
        status=status,
        command=shell_join(step.command),
        stdout_tail=tail_text(proc.stdout),
        stderr_tail=tail_text(proc.stderr),
        report_paths=step.report_paths,
        inferred_report_status=inferred,
        started_utc=started,
        finished_utc=finished,
    )
    if proc.returncode != 0 and not continue_on_error:
        raise RuntimeError(f"Step failed: {step.name}\n{proc.stderr}\n{proc.stdout}")
    return result


def build_steps(args: argparse.Namespace) -> List[Step]:
    py = sys.executable
    steps: List[Step] = []

    h1 = str(Path(args.h1_csv).expanduser())
    m1 = str(Path(args.m1_csv).expanduser())
    signals = str(Path(args.signals_csv).expanduser())

    if args.mode in {"research", "full"}:
        steps.extend([
            Step(
                name="stage4g_offset2_amarkets_backfill_non_overlap",
                command=[
                    py, "-m", "app.stage4g_amarkets_backfill_validation",
                    "--h1-csv", h1,
                    "--m1-csv", m1,
                    "--server-utc-offset-hours", str(args.server_utc_offset_hours),
                    "--out-dir", "data/reports/stage4g_v2",
                ],
                report_paths=[
                    "data/reports/stage4g_v2/stage4g_v2_amarkets_backfill_validation.md",
                    "data/reports/stage4g_v2/stage4g_v2_non_overlap_trades.csv",
                ],
                required_inputs=[h1, m1],
            ),
            Step(
                name="stage4g_offset3_amarkets_backfill_non_overlap",
                command=[
                    py, "-m", "app.stage4g_amarkets_backfill_validation",
                    "--h1-csv", h1,
                    "--m1-csv", m1,
                    "--server-utc-offset-hours", "3",
                    "--out-dir", "data/reports/stage4g_v2_offset3",
                ],
                report_paths=[
                    "data/reports/stage4g_v2_offset3/stage4g_v2_amarkets_backfill_validation.md",
                    "data/reports/stage4g_v2_offset3/stage4g_v2_non_overlap_trades.csv",
                ],
                required_inputs=[h1, m1],
            ),
            Step(
                name="stage4h_offset2_session_guard_lab",
                command=[
                    py, "-m", "app.stage4h_session_guard_lab",
                    "--trades-csv", "data/reports/stage4g_v2/stage4g_v2_non_overlap_trades.csv",
                    "--out-dir", "data/reports/stage4h_session_guard_lab",
                ],
                report_paths=["data/reports/stage4h_session_guard_lab/stage4h_session_guard_lab.md"],
                required_inputs=["data/reports/stage4g_v2/stage4g_v2_non_overlap_trades.csv"],
            ),
            Step(
                name="stage4h_offset3_session_guard_lab",
                command=[
                    py, "-m", "app.stage4h_session_guard_lab",
                    "--trades-csv", "data/reports/stage4g_v2_offset3/stage4g_v2_non_overlap_trades.csv",
                    "--out-dir", "data/reports/stage4h_session_guard_lab_offset3",
                ],
                report_paths=["data/reports/stage4h_session_guard_lab_offset3/stage4h_session_guard_lab.md"],
                required_inputs=["data/reports/stage4g_v2_offset3/stage4g_v2_non_overlap_trades.csv"],
            ),
            Step(
                name="stage4i_guard_robustness",
                command=[
                    py, "-m", "app.stage4i_guard_robustness",
                    "--offset2-trades", "data/reports/stage4g_v2/stage4g_v2_non_overlap_trades.csv",
                    "--offset3-trades", "data/reports/stage4g_v2_offset3/stage4g_v2_non_overlap_trades.csv",
                    "--out-dir", "data/reports/stage4i_guard_robustness",
                ],
                report_paths=["data/reports/stage4i_guard_robustness/stage4i_guard_robustness.md"],
                required_inputs=[
                    "data/reports/stage4g_v2/stage4g_v2_non_overlap_trades.csv",
                    "data/reports/stage4g_v2_offset3/stage4g_v2_non_overlap_trades.csv",
                ],
            ),
            Step(
                name="stage4j_shock_regime_lab_offset2",
                command=[
                    py, "-m", "app.stage4j_shock_regime_lab",
                    "--trades-csv", "data/reports/stage4g_v2/stage4g_v2_non_overlap_trades.csv",
                    "--out-dir", "data/reports/stage4j_shock_regime_lab",
                    "--shock-start", args.shock_start,
                    "--recent-start", args.recent_start,
                ],
                report_paths=["data/reports/stage4j_shock_regime_lab/stage4j_shock_regime_lab.md"],
                required_inputs=["data/reports/stage4g_v2/stage4g_v2_non_overlap_trades.csv"],
            ),
        ])

    if args.mode in {"live_only", "full"}:
        steps.extend([
            Step(
                name="stage5b_dryrun_signal_csv_validator",
                command=[
                    py, "-m", "app.stage5b_dryrun_log_validator",
                    "--csv", signals,
                    "--print-columns",
                ],
                report_paths=["data/reports/stage5b_dryrun_log_validator.md"],
                required_inputs=[signals],
            ),
            Step(
                name="stage5c_live_outcome_tracker",
                command=[
                    py, "-m", "app.stage5c_live_outcome_tracker",
                    "--signals-csv", signals,
                    "--m1-csv", m1,
                    "--server-utc-offset-hours", str(args.server_utc_offset_hours),
                    "--out-dir", "data/reports/stage5c_live_outcome_tracker",
                ],
                report_paths=["data/reports/stage5c_live_outcome_tracker/stage5c_live_outcome_tracker.md"],
                required_inputs=[signals, m1],
            ),
        ])

    return steps


def write_summary(out_dir: Path, args: argparse.Namespace, results: List[StepResult]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "tool_version": TOOL_VERSION,
        "strategy_id": STRATEGY_ID,
        "generated_utc": now_iso(),
        "mode": args.mode,
        "hard_rule": "Research/dry-run only. No demo, paper, or live authorization.",
        "inputs": {
            "h1_csv": str(Path(args.h1_csv).expanduser()),
            "m1_csv": str(Path(args.m1_csv).expanduser()),
            "signals_csv": str(Path(args.signals_csv).expanduser()),
            "server_utc_offset_hours": args.server_utc_offset_hours,
            "shock_start": args.shock_start,
            "recent_start": args.recent_start,
        },
        "results": [asdict(r) for r in results],
    }
    (out_dir / "stage_pipeline_summary.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines: List[str] = []
    lines.append("# XAUUSD Stage Pipeline Summary")
    lines.append("")
    lines.append(f"Generated UTC: `{payload['generated_utc']}`")
    lines.append(f"Tool version: `{TOOL_VERSION}`")
    lines.append(f"Mode: `{args.mode}`")
    lines.append(f"Strategy ID: `{STRATEGY_ID}`")
    lines.append("")
    lines.append("> Hard rule: this pipeline runs research/dry-run validation only. It does not authorize demo, paper, or live orders.")
    lines.append("")
    lines.append("## Inputs")
    lines.append(f"- h1_csv: `{payload['inputs']['h1_csv']}`")
    lines.append(f"- m1_csv: `{payload['inputs']['m1_csv']}`")
    lines.append(f"- signals_csv: `{payload['inputs']['signals_csv']}`")
    lines.append(f"- server_utc_offset_hours: `{args.server_utc_offset_hours}`")
    lines.append("")
    lines.append("## Step summary")
    lines.append("| # | Step | Status | Return code | Inferred report status | Main reports |")
    lines.append("|---:|---|---|---:|---|---|")
    for i, r in enumerate(results, start=1):
        reports = "<br>".join(f"`{p}`" for p in r.report_paths)
        lines.append(f"| {i} | {r.name} | {r.status} | {r.returncode} | {r.inferred_report_status} | {reports} |")
    lines.append("")
    lines.append("## Decision")
    errors = [r for r in results if r.returncode not in (0,)]
    if errors:
        lines.append("- One or more steps failed or were skipped. Inspect the step reports before making any research decision.")
    else:
        lines.append("- Pipeline completed. Use individual reports for research decisions. No order authorization.")
    lines.append("- Current expected operational decision remains: continue live dry-run, keep EA unchanged unless a validated new locked strategy version is created.")
    (out_dir / "stage_pipeline_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["live_only", "research", "full"], default="full")
    parser.add_argument("--h1-csv", default=str(DEFAULT_H1_CSV))
    parser.add_argument("--m1-csv", default=str(DEFAULT_M1_CSV))
    parser.add_argument("--signals-csv", default=str(DEFAULT_SIGNALS_CSV))
    parser.add_argument("--server-utc-offset-hours", type=float, default=2.0)
    parser.add_argument("--shock-start", default="2026-02-28T00:00:00Z")
    parser.add_argument("--recent-start", default="2026-06-01T00:00:00Z")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--continue-on-error", action="store_true", default=True)
    args = parser.parse_args()

    steps = build_steps(args)
    results: List[StepResult] = []
    print(f"XAUUSD stage pipeline: mode={args.mode} | steps={len(steps)}")
    print("Hard rule: research/dry-run only. No demo/paper/live authorization.")

    for idx, step in enumerate(steps, start=1):
        print(f"\n[{idx}/{len(steps)}] {step.name}")
        print(shell_join(step.command))
        result = run_step(step, continue_on_error=args.continue_on_error)
        results.append(result)
        print(f"status={result.status} returncode={result.returncode} report_status={result.inferred_report_status}")
        if result.stderr_tail.strip():
            print("stderr tail:")
            print(result.stderr_tail[-1000:])

    out_dir = Path(args.out_dir)
    write_summary(out_dir, args, results)
    print(f"\nPipeline summary: {out_dir / 'stage_pipeline_summary.md'}")
    print(f"Pipeline JSON: {out_dir / 'stage_pipeline_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
