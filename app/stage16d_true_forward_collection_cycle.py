#!/usr/bin/env python3
"""
Stage 16D — True-Forward Collection Cycle Runner

Purpose:
- Run an operational research-only cycle for Stage 16C.
- Optionally run a user-supplied data-refresh command first.
- Run Stage 16C collector.
- Produce a cycle report with stale-data guard, collector status, and journal counts.

Why:
- Stage 16C starts the true-forward boundary.
- If local data is older than collector_start_utc, no true-forward signal can be discovered.
- This runner prevents false confidence by explicitly reporting stale-data status.

Hard rules:
- Research shadow collection only.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import json
import shlex
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd


TOOL_VERSION = "v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_STAGE16C_OUT = Path("data/reports/stage16c_true_forward_shadow_collector")
DEFAULT_OUT_DIR = Path("data/reports/stage16d_true_forward_collection_cycle")


def now_utc() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc)).replace(microsecond=0)


def now_iso() -> str:
    return now_utc().isoformat()


def connect(db: Path) -> sqlite3.Connection:
    if not db.exists():
        raise FileNotFoundError(f"DB not found: {db}")
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn


def latest_bar_utc(db: Path) -> Optional[pd.Timestamp]:
    conn = connect(db)
    try:
        row = conn.execute(
            """
            SELECT MAX(utc_time) AS latest
            FROM bars
            WHERE source='amarkets_mt5' AND symbol='XAUUSD'
            """
        ).fetchone()
    finally:
        conn.close()
    if not row or not row["latest"]:
        return None
    return pd.to_datetime(row["latest"], utc=True, errors="coerce")


def read_json(path: Path) -> Dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def run_cmd(cmd: str, cwd: Path, timeout_sec: int) -> Dict:
    if not cmd:
        return {
            "enabled": False,
            "cmd": "",
            "returncode": None,
            "stdout_tail": "",
            "stderr_tail": "",
            "status": "skipped",
        }

    try:
        proc = subprocess.run(
            shlex.split(cmd),
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout_sec,
        )
        return {
            "enabled": True,
            "cmd": cmd,
            "returncode": int(proc.returncode),
            "stdout_tail": proc.stdout[-4000:],
            "stderr_tail": proc.stderr[-4000:],
            "status": "ok" if proc.returncode == 0 else "failed",
        }
    except Exception as e:
        return {
            "enabled": True,
            "cmd": cmd,
            "returncode": None,
            "stdout_tail": "",
            "stderr_tail": str(e)[-4000:],
            "status": "exception",
        }


def run_stage16c(
    cwd: Path,
    collector_out_dir: Path,
    timeout_sec: int,
    scan_days: int,
) -> Dict:
    cmd = [
        sys.executable,
        "-m",
        "app.stage16c_true_forward_shadow_collector",
        "--out-dir",
        str(collector_out_dir),
        "--scan-days",
        str(scan_days),
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout_sec,
        )
        return {
            "cmd": " ".join(cmd),
            "returncode": int(proc.returncode),
            "stdout_tail": proc.stdout[-4000:],
            "stderr_tail": proc.stderr[-4000:],
            "status": "ok" if proc.returncode == 0 else "failed",
        }
    except Exception as e:
        return {
            "cmd": " ".join(cmd),
            "returncode": None,
            "stdout_tail": "",
            "stderr_tail": str(e)[-4000:],
            "status": "exception",
        }


def load_journal(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        x = pd.read_csv(path)
    except Exception:
        return pd.DataFrame()
    for c in ["event_utc", "entry_utc", "exit_target_utc", "detected_utc", "resolved_utc"]:
        if c in x.columns:
            x[c] = pd.to_datetime(x[c], utc=True, errors="coerce")
    return x


def journal_counts(journal: pd.DataFrame) -> Dict:
    if journal.empty:
        return {
            "journal_rows": 0,
            "valid_forward_rows": 0,
            "closed_valid_forward_rows": 0,
            "open_valid_forward_rows": 0,
            "status_counts": {},
        }
    valid = journal[journal.get("forward_valid", False).astype(str).str.lower().isin(["true", "1"])].copy()
    closed = valid[valid["status"].eq("closed_time_exit")].copy() if "status" in valid.columns else pd.DataFrame()
    open_ = valid[valid["status"].isin(["pending_entry", "open_shadow", "open_no_path_yet"])] if "status" in valid.columns else pd.DataFrame()
    return {
        "journal_rows": int(len(journal)),
        "valid_forward_rows": int(len(valid)),
        "closed_valid_forward_rows": int(len(closed)),
        "open_valid_forward_rows": int(len(open_)),
        "status_counts": journal["status"].value_counts().to_dict() if "status" in journal.columns else {},
    }


def decide(pre_latest: Optional[pd.Timestamp], post_latest: Optional[pd.Timestamp], collector_start: Optional[pd.Timestamp], stage16c_result: Dict, counts: Dict) -> Tuple[str, List[str]]:
    reasons: List[str] = []

    if stage16c_result.get("status") != "ok":
        return "CYCLE_FAILED_STAGE16C_ERROR", ["Stage16C collector did not complete successfully."]

    if collector_start is None:
        return "CYCLE_INITIALIZED_COLLECTOR_STATE", ["Collector state was initialized; rerun after data refresh."]

    if post_latest is None:
        return "CYCLE_NO_BAR_DATA", ["No local bar data found."]

    if post_latest <= collector_start:
        reasons.append("Local data is still older than or equal to collector_start_utc; true-forward discovery cannot happen yet.")
        return "CYCLE_WAITING_FOR_POST_START_DATA", reasons

    if counts.get("open_valid_forward_rows", 0) > 0:
        return "CYCLE_TRUE_FORWARD_SIGNAL_OPEN", ["At least one valid true-forward shadow signal is open/pending outcome."]

    if counts.get("closed_valid_forward_rows", 0) > 0:
        return "CYCLE_TRUE_FORWARD_OUTCOMES_AVAILABLE", ["At least one valid true-forward shadow outcome is available."]

    reasons.append("Post-start data exists, but no valid Stage16C signal has appeared yet.")
    return "CYCLE_ACTIVE_NO_FORWARD_SIGNAL_YET", reasons


def run(
    db: Path,
    stage16c_out: Path,
    out_dir: Path,
    refresh_cmd: str,
    timeout_sec: int,
    scan_days: int,
) -> int:
    generated = now_utc()
    cwd = Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)

    pre_latest = latest_bar_utc(db)
    refresh_result = run_cmd(refresh_cmd, cwd=cwd, timeout_sec=timeout_sec) if refresh_cmd else run_cmd("", cwd=cwd, timeout_sec=timeout_sec)
    post_refresh_latest = latest_bar_utc(db)

    stage16c_result = run_stage16c(
        cwd=cwd,
        collector_out_dir=stage16c_out,
        timeout_sec=timeout_sec,
        scan_days=scan_days,
    )

    state = read_json(stage16c_out / "stage16c_collector_state.json")
    report = read_json(stage16c_out / "stage16c_true_forward_shadow_collector.json")
    journal = load_journal(stage16c_out / "stage16c_true_forward_shadow_journal.csv")
    counts = journal_counts(journal)

    collector_start = None
    if state.get("collector_start_utc"):
        collector_start = pd.to_datetime(state["collector_start_utc"], utc=True, errors="coerce")

    post_latest = latest_bar_utc(db)
    final_decision, reasons = decide(pre_latest, post_latest, collector_start, stage16c_result, counts)

    report_json = out_dir / "stage16d_true_forward_collection_cycle.json"
    report_md = out_dir / "stage16d_true_forward_collection_cycle.md"

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated.isoformat(),
        "inputs": {
            "db": str(db),
            "stage16c_out": str(stage16c_out),
            "refresh_cmd": refresh_cmd,
            "timeout_sec": int(timeout_sec),
            "scan_days": int(scan_days),
        },
        "bar_state": {
            "pre_refresh_latest_bar_utc": pre_latest.isoformat() if pre_latest is not None else None,
            "post_refresh_latest_bar_utc": post_refresh_latest.isoformat() if post_refresh_latest is not None else None,
            "post_stage16c_latest_bar_utc": post_latest.isoformat() if post_latest is not None else None,
            "collector_start_utc": collector_start.isoformat() if collector_start is not None else None,
            "data_after_collector_start": bool(post_latest is not None and collector_start is not None and post_latest > collector_start),
        },
        "refresh_result": refresh_result,
        "stage16c_result": stage16c_result,
        "stage16c_report_decision": report.get("final_decision"),
        "journal_counts": counts,
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
    report_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    lines = [
        "# Stage 16D True-Forward Collection Cycle",
        "",
        f"Generated UTC: `{generated.isoformat()}`",
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
        "## Bar/data state",
        f"- pre_refresh_latest_bar_utc: `{pre_latest.isoformat() if pre_latest is not None else None}`",
        f"- post_refresh_latest_bar_utc: `{post_refresh_latest.isoformat() if post_refresh_latest is not None else None}`",
        f"- post_stage16c_latest_bar_utc: `{post_latest.isoformat() if post_latest is not None else None}`",
        f"- collector_start_utc: `{collector_start.isoformat() if collector_start is not None else None}`",
        f"- data_after_collector_start: `{bool(post_latest is not None and collector_start is not None and post_latest > collector_start)}`",
        "",
        "## Refresh result",
        f"- enabled: `{refresh_result.get('enabled')}`",
        f"- status: `{refresh_result.get('status')}`",
        f"- returncode: `{refresh_result.get('returncode')}`",
        f"- cmd: `{refresh_result.get('cmd')}`",
        "",
        "## Stage16C result",
        f"- status: `{stage16c_result.get('status')}`",
        f"- returncode: `{stage16c_result.get('returncode')}`",
        f"- stage16c_report_decision: `{report.get('final_decision')}`",
        "",
        "## Journal counts",
        f"- journal_rows: `{counts['journal_rows']}`",
        f"- valid_forward_rows: `{counts['valid_forward_rows']}`",
        f"- closed_valid_forward_rows: `{counts['closed_valid_forward_rows']}`",
        f"- open_valid_forward_rows: `{counts['open_valid_forward_rows']}`",
        "",
        "## Status counts",
    ]
    if counts.get("status_counts"):
        for k, v in counts["status_counts"].items():
            lines.append(f"- {k}: `{v}`")
    else:
        lines.append("- none")

    if refresh_result.get("stderr_tail"):
        lines += [
            "",
            "## Refresh stderr tail",
            "```text",
            str(refresh_result.get("stderr_tail"))[-2000:],
            "```",
        ]
    if stage16c_result.get("stderr_tail"):
        lines += [
            "",
            "## Stage16C stderr tail",
            "```text",
            str(stage16c_result.get("stderr_tail"))[-2000:],
            "```",
        ]

    lines += [
        "",
        "## Interpretation",
        "- If data_after_collector_start is false, no true-forward signal can be discovered yet.",
        "- If data is fresh but valid_forward_rows is zero, collection is active and waiting.",
        "- Any true-forward signal remains research shadow only.",
        "- No paper/live/order escalation is authorized.",
        "",
        "## Output files",
        f"- json: `{report_json}`",
        f"- md: `{report_md}`",
    ]
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 16D true-forward collection cycle: DONE")
    print(f"final_decision={final_decision}")
    print(f"data_after_collector_start={payload['bar_state']['data_after_collector_start']}")
    print(f"journal_rows={counts['journal_rows']} valid_forward_rows={counts['valid_forward_rows']} closed_valid={counts['closed_valid_forward_rows']}")
    print(f"Report: {report_md}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--stage16c-out", default=str(DEFAULT_STAGE16C_OUT))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--refresh-cmd", default="", help="Optional command, e.g. 'python3 -m app.stage6b_persist_runner'")
    p.add_argument("--timeout-sec", type=int, default=900)
    p.add_argument("--scan-days", type=int, default=10)
    args = p.parse_args()

    return run(
        db=Path(args.db),
        stage16c_out=Path(args.stage16c_out),
        out_dir=Path(args.out_dir),
        refresh_cmd=str(args.refresh_cmd),
        timeout_sec=int(args.timeout_sec),
        scan_days=int(args.scan_days),
    )


if __name__ == "__main__":
    raise SystemExit(main())
