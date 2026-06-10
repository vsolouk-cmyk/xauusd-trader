#!/usr/bin/env python3
"""
Stage 6B v2 — Local Persist + Evidence Runner

Runs the daily/local evidence flow in the correct order:

1. Stage data file audit
2. Stage 5B dry-run signal CSV validator
3. Stage 5C live dry-run outcome tracker
4. Stage 6A local SQLite import
5. Stage 6C DB evidence report

Hard rules:
- No demo/paper/live authorization.
- No order sending.
- Does not modify MT5 EA files.
- Updates only the local SQLite evidence store during Stage 6A.
- Stage 6C is read-only and decision-report only.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Sequence


TOOL_VERSION = "v2"
STRATEGY_ID = "xauusd_long_tp24_sl15_no_london_v1"

DEFAULT_H1 = Path("~/Downloads/amarkets_xauusd_1h.csv").expanduser()
DEFAULT_M1 = Path("~/Downloads/amarkets_xauusd_1m.csv").expanduser()
DEFAULT_SIGNALS = Path("~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/XAUUSD_DryRun_v1_signals.csv").expanduser()
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_OUT_DIR = Path("data/reports/stage6b_persist_runner")


@dataclass
class StepResult:
    name: str
    command: str
    returncode: int
    status: str
    stdout_tail: str
    stderr_tail: str
    started_utc: str
    finished_utc: str


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def shell_join(cmd: Sequence[str]) -> str:
    return " ".join(shlex.quote(str(x)) for x in cmd)


def tail(text: str, n: int = 3000) -> str:
    text = text or ""
    return text if len(text) <= n else text[-n:]


def run_step(name: str, cmd: List[str], continue_on_error: bool) -> StepResult:
    started = now_iso()
    proc = subprocess.run(cmd, text=True, capture_output=True, cwd=Path.cwd())
    finished = now_iso()
    result = StepResult(
        name=name,
        command=shell_join(cmd),
        returncode=proc.returncode,
        status="OK" if proc.returncode == 0 else "ERROR",
        stdout_tail=tail(proc.stdout),
        stderr_tail=tail(proc.stderr),
        started_utc=started,
        finished_utc=finished,
    )
    if proc.returncode != 0 and not continue_on_error:
        raise RuntimeError(f"Step failed: {name}\n{proc.stderr}\n{proc.stdout}")
    return result


def write_summary(out_dir: Path, args: argparse.Namespace, results: List[StepResult]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "tool_version": TOOL_VERSION,
        "strategy_id": STRATEGY_ID,
        "generated_utc": now_iso(),
        "hard_rule": "Dry-run/persistence/evidence only. No orders.",
        "inputs": {
            "h1_csv": str(Path(args.h1_csv).expanduser()),
            "m1_csv": str(Path(args.m1_csv).expanduser()),
            "signals_csv": str(Path(args.signals_csv).expanduser()),
            "db": str(Path(args.db)),
            "fetch_twelve": args.fetch_twelve,
            "run_6c": not args.skip_6c,
        },
        "results": [asdict(r) for r in results],
    }
    (out_dir / "stage6b_persist_runner.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Stage 6B Local Persist + Evidence Runner",
        "",
        f"Generated UTC: `{payload['generated_utc']}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: this runner validates dry-run evidence, updates local SQLite, and produces DB evidence reports. It does not authorize demo, paper, or live orders.",
        "",
        "## Inputs",
        f"- h1_csv: `{payload['inputs']['h1_csv']}`",
        f"- m1_csv: `{payload['inputs']['m1_csv']}`",
        f"- signals_csv: `{payload['inputs']['signals_csv']}`",
        f"- db: `{payload['inputs']['db']}`",
        f"- fetch_twelve: `{payload['inputs']['fetch_twelve']}`",
        f"- run_6c: `{payload['inputs']['run_6c']}`",
        "",
        "## Step summary",
        "| # | Step | Status | Return code |",
        "|---:|---|---|---:|",
    ]
    for i, r in enumerate(results, start=1):
        lines.append(f"| {i} | {r.name} | {r.status} | {r.returncode} |")

    lines += [
        "",
        "## Main reports",
        "- `data/reports/stage_data_file_audit/stage_data_file_audit.md`",
        "- `data/reports/stage5b_dryrun_log_validator.md`",
        "- `data/reports/stage5c_live_outcome_tracker/stage5c_live_outcome_tracker.md`",
        "- `data/reports/stage6a_local_store/stage6a_local_store.md`",
        "- `data/reports/stage6c_db_evidence_report/stage6c_db_evidence_report.md`",
        "",
        "## Decision",
    ]
    if any(r.returncode != 0 for r in results):
        lines.append("- One or more steps failed. Inspect the related report before relying on the local store.")
    else:
        lines.append("- Persist + evidence flow completed. Local SQLite evidence store and DB evidence report are updated.")
    lines.append("- This does not authorize orders.")
    (out_dir / "stage6b_persist_runner.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--h1-csv", default=str(DEFAULT_H1))
    p.add_argument("--m1-csv", default=str(DEFAULT_M1))
    p.add_argument("--signals-csv", default=str(DEFAULT_SIGNALS))
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--server-utc-offset-hours", type=float, default=2.0)
    p.add_argument("--fetch-twelve", action="store_true")
    p.add_argument("--twelve-allow-insecure-ssl", action="store_true")
    p.add_argument("--skip-6c", action="store_true")
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--continue-on-error", action="store_true", default=True)
    args = p.parse_args()

    py = sys.executable
    h1 = str(Path(args.h1_csv).expanduser())
    m1 = str(Path(args.m1_csv).expanduser())
    signals = str(Path(args.signals_csv).expanduser())
    db = str(Path(args.db))

    steps = [
        (
            "stage_data_file_audit",
            [py, "-m", "app.stage_data_file_audit", "--h1-csv", h1, "--m1-csv", m1, "--signals-csv", signals, "--server-utc-offset-hours", str(args.server_utc_offset_hours)],
        ),
        (
            "stage5b_dryrun_signal_csv_validator",
            [py, "-m", "app.stage5b_dryrun_log_validator", "--csv", signals, "--print-columns"],
        ),
        (
            "stage5c_live_outcome_tracker",
            [py, "-m", "app.stage5c_live_outcome_tracker", "--signals-csv", signals, "--m1-csv", m1, "--server-utc-offset-hours", str(args.server_utc_offset_hours), "--out-dir", "data/reports/stage5c_live_outcome_tracker"],
        ),
    ]

    stage6a_cmd = [
        py, "-m", "app.stage6a_local_data_store",
        "--db", db,
        "--h1-csv", h1,
        "--m1-csv", m1,
        "--signals-csv", signals,
        "--server-utc-offset-hours", str(args.server_utc_offset_hours),
    ]
    if args.fetch_twelve:
        stage6a_cmd.append("--fetch-twelve")
    if args.twelve_allow_insecure_ssl:
        stage6a_cmd.append("--twelve-allow-insecure-ssl")
    steps.append(("stage6a_local_data_store", stage6a_cmd))

    if not args.skip_6c:
        steps.append((
            "stage6c_db_evidence_report",
            [py, "-m", "app.stage6c_db_evidence_report", "--db", db, "--out-dir", "data/reports/stage6c_db_evidence_report"],
        ))

    print(f"Stage 6B persist + evidence runner: steps={len(steps)}")
    print("Hard rule: dry-run/persistence/evidence only. No demo/paper/live authorization.")

    results = []
    for i, (name, cmd) in enumerate(steps, start=1):
        print(f"\n[{i}/{len(steps)}] {name}")
        print(shell_join(cmd))
        res = run_step(name, cmd, args.continue_on_error)
        results.append(res)
        print(f"status={res.status} returncode={res.returncode}")
        if res.stderr_tail.strip():
            print("stderr tail:")
            print(res.stderr_tail[-1000:])

    out_dir = Path(args.out_dir)
    write_summary(out_dir, args, results)
    print(f"\nSummary: {out_dir / 'stage6b_persist_runner.md'}")
    print("Main evidence report: data/reports/stage6c_db_evidence_report/stage6c_db_evidence_report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
