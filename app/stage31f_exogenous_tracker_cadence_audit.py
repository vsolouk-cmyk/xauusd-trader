from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


STAGE31E_REPORT_DIR = Path("data/reports/stage31e_exogenous_forward_shadow_tracker")
OUT_DIR = Path("data/reports/stage31f_exogenous_tracker_cadence_audit")


@dataclass
class LookbackResult:
    lookback_hours: int
    stage31e_returncode: int
    stage31e_decision: str
    recent_signal_rows: int
    recent_signal_gate_count: int
    tracker_results: int
    latest_recent_entry_ts: str
    copied_md: str
    copied_recent_signals_csv: str
    copied_tracker_summary_csv: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_int_from_md(md: str, key: str, default: int = 0) -> int:
    # Matches: - recent_signal_rows: `4`
    pat = rf"{re.escape(key)}:\s*`?(-?\d+)`?"
    m = re.search(pat, md)
    if not m:
        return default
    try:
        return int(m.group(1))
    except Exception:
        return default


def parse_decision_from_md(md: str) -> str:
    m = re.search(r"## Decision\s*```text\s*([A-Z0-9_]+)\s*```", md, re.S)
    if m:
        return m.group(1).strip()
    m = re.search(r"STAGE31E_[A-Z0-9_]+", md)
    return m.group(0) if m else "UNKNOWN"


def latest_ts_from_recent_signals(csv_path: Path) -> str:
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return ""
    latest = ""
    try:
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts = str(row.get("entry_ts_norm", "")).strip()
                if ts and ts > latest:
                    latest = ts
    except Exception:
        return ""
    return latest


def copy_if_exists(src: Path, dst: Path) -> str:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.exists():
        shutil.copy2(src, dst)
        return str(dst)
    return ""


def run_stage31e_for_lookback(hours: int) -> LookbackResult:
    env = os.environ.copy()
    env["STAGE31E_LOOKBACK_HOURS"] = str(hours)

    proc = subprocess.run(
        [sys.executable, "-m", "app.stage31e_exogenous_forward_shadow_tracker"],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    md_path = STAGE31E_REPORT_DIR / "stage31e_exogenous_forward_shadow_tracker.md"
    recent_csv_path = STAGE31E_REPORT_DIR / "stage31e_recent_signals.csv"
    summary_csv_path = STAGE31E_REPORT_DIR / "stage31e_tracker_summary.csv"
    json_path = STAGE31E_REPORT_DIR / "stage31e_exogenous_forward_shadow_tracker.json"

    md = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    decision = parse_decision_from_md(md)
    recent_rows = parse_int_from_md(md, "recent_signal_rows", 0)
    recent_gate_count = parse_int_from_md(md, "recent_signal_gate_count", 0)
    tracker_results = parse_int_from_md(md, "tracker_results", 0)
    latest_ts = latest_ts_from_recent_signals(recent_csv_path)

    prefix = f"stage31e_lookback_{hours}h"
    copied_md = copy_if_exists(md_path, OUT_DIR / f"{prefix}.md")
    copied_recent = copy_if_exists(recent_csv_path, OUT_DIR / f"{prefix}_recent_signals.csv")
    copied_summary = copy_if_exists(summary_csv_path, OUT_DIR / f"{prefix}_tracker_summary.csv")
    copy_if_exists(json_path, OUT_DIR / f"{prefix}.json")

    # Preserve stdout for diagnosis without bloating markdown.
    (OUT_DIR / f"{prefix}_stdout.log").write_text(proc.stdout or "", encoding="utf-8")

    return LookbackResult(
        lookback_hours=hours,
        stage31e_returncode=int(proc.returncode),
        stage31e_decision=decision,
        recent_signal_rows=recent_rows,
        recent_signal_gate_count=recent_gate_count,
        tracker_results=tracker_results,
        latest_recent_entry_ts=latest_ts,
        copied_md=copied_md,
        copied_recent_signals_csv=copied_recent,
        copied_tracker_summary_csv=copied_summary,
    )


def parse_lookbacks() -> List[int]:
    raw = os.getenv("STAGE31F_LOOKBACK_HOURS_LIST", "336,720,2160,4320")
    out: List[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            val = int(token)
        except Exception:
            continue
        if val > 0 and val not in out:
            out.append(val)
    return out or [336, 720, 2160, 4320]


def decide(results: List[LookbackResult]) -> str:
    # No execution implication; this only classifies observation cadence.
    by_hours = {r.lookback_hours: r for r in results}
    if any(r.stage31e_returncode != 0 for r in results):
        return "STAGE31F_STAGE31E_RUN_ERROR_REVIEW_ONLY"
    if by_hours.get(336) and by_hours[336].recent_signal_rows > 0:
        return "STAGE31F_ACTIVE_RECENT_SIGNAL_REVIEW_ONLY"
    if by_hours.get(720) and by_hours[720].recent_signal_rows > 0:
        return "STAGE31F_MONTHLY_CADENCE_SIGNAL_REVIEW_ONLY"
    if by_hours.get(2160) and by_hours[2160].recent_signal_rows > 0:
        return "STAGE31F_QUARTERLY_CADENCE_SIGNAL_REVIEW_ONLY"
    if by_hours.get(4320) and by_hours[4320].recent_signal_rows > 0:
        return "STAGE31F_LOW_CADENCE_WATCHLIST_REVIEW_ONLY"
    if any(r.recent_signal_rows > 0 for r in results):
        return "STAGE31F_SPARSE_SIGNAL_WATCHLIST_REVIEW_ONLY"
    return "STAGE31F_NO_CADENCE_SIGNAL_RESEARCH_ONLY"


def write_csv(results: List[LookbackResult]) -> None:
    path = OUT_DIR / "stage31f_cadence_summary.csv"
    if not results:
        path.write_text("", encoding="utf-8")
        return
    fields = list(asdict(results[0]).keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in results:
            writer.writerow(asdict(r))


def write_markdown(report: Dict[str, Any], results: List[LookbackResult]) -> None:
    lines: List[str] = []
    lines.append("# Stage31F Exogenous Tracker Cadence Audit")
    lines.append("")
    lines.append(f"Generated UTC: `{report['generated_utc']}`")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    lines.append(report["decision"])
    lines.append("```")
    lines.append("")
    lines.append("## Scope guardrails")
    lines.append("")
    lines.append("- Research/shadow cadence audit only.")
    lines.append("- No EA change, no automatic trading, no paper/live/order authorization.")
    lines.append("- Runs Stage31E across multiple lookbacks and summarizes observation cadence.")
    lines.append("- Does not fetch internet data.")
    lines.append("")
    lines.append("## Counts")
    lines.append("")
    lines.append(f"- lookback_count: `{len(results)}`")
    lines.append(f"- any_recent_signal_rows: `{sum(1 for r in results if r.recent_signal_rows > 0)}`")
    lines.append(f"- max_recent_signal_rows: `{max([r.recent_signal_rows for r in results], default=0)}`")
    lines.append("")
    lines.append("## Cadence summary")
    lines.append("")
    lines.append("| lookback_hours | stage31e_decision | recent_signal_rows | recent_signal_gate_count | latest_recent_entry_ts | tracker_results | returncode |")
    lines.append("|---:|:---|---:|---:|:---|---:|---:|")
    for r in results:
        lines.append(
            f"| {r.lookback_hours} | {r.stage31e_decision} | {r.recent_signal_rows} | "
            f"{r.recent_signal_gate_count} | {r.latest_recent_entry_ts} | {r.tracker_results} | {r.stage31e_returncode} |"
        )
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("- Sparse historical/recent matches do not authorize execution.")
    lines.append("- If only long lookbacks produce matches, the candidate should remain in observation/watchlist mode.")
    lines.append("- Active-suite integration, if used, should be status-only and should not change EA, paper/live, or order behavior.")
    lines.append("")
    lines.append("## Output files")
    lines.append("")
    lines.append("- `data/reports/stage31f_exogenous_tracker_cadence_audit/stage31f_exogenous_tracker_cadence_audit.md`")
    lines.append("- `data/reports/stage31f_exogenous_tracker_cadence_audit/stage31f_exogenous_tracker_cadence_audit.json`")
    lines.append("- `data/reports/stage31f_exogenous_tracker_cadence_audit/stage31f_cadence_summary.csv`")
    lines.append("- copied Stage31E lookback artifacts under the same directory")
    lines.append("")

    (OUT_DIR / "stage31f_exogenous_tracker_cadence_audit.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lookbacks = parse_lookbacks()
    results = [run_stage31e_for_lookback(h) for h in lookbacks]
    decision = decide(results)

    report = {
        "generated_utc": utc_now_iso(),
        "decision": decision,
        "lookbacks": lookbacks,
        "results": [asdict(r) for r in results],
        "guardrails": {
            "research_shadow_only": True,
            "no_ea_change": True,
            "no_paper_live_order_authorization": True,
            "no_internet_fetch": True,
        },
    }

    write_csv(results)
    (OUT_DIR / "stage31f_exogenous_tracker_cadence_audit.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    write_markdown(report, results)

    print(json.dumps({"decision": decision, "lookbacks": lookbacks}, ensure_ascii=False))


if __name__ == "__main__":
    main()
