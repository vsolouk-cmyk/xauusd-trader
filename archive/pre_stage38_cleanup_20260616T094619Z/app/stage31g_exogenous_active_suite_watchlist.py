from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

REPORT_DIR = Path("data/reports/stage31g_exogenous_active_suite_watchlist")
STAGE31F_DIR = Path("data/reports/stage31f_exogenous_tracker_cadence_audit")
STAGE31F_SUMMARY = STAGE31F_DIR / "stage31f_cadence_summary.csv"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def run_stage31f_if_requested() -> Dict[str, Any]:
    run_flag = os.getenv("STAGE31G_RUN_STAGE31F", "1").strip().lower()
    if run_flag in {"0", "false", "no", "off"}:
        return {"attempted": False, "returncode": None, "stdout_tail": "", "stderr_tail": ""}

    env = os.environ.copy()
    env.setdefault("STAGE31F_LOOKBACK_HOURS_LIST", "336,720,2160,4320")
    proc = subprocess.run(
        [sys.executable, "-m", "app.stage31f_exogenous_tracker_cadence_audit"],
        text=True,
        capture_output=True,
        env=env,
    )
    return {
        "attempted": True,
        "returncode": int(proc.returncode),
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    }


def load_cadence_summary() -> pd.DataFrame:
    if not STAGE31F_SUMMARY.exists() or STAGE31F_SUMMARY.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(STAGE31F_SUMMARY)
    except Exception:
        return pd.DataFrame()


def as_int(value: Any, default: int = 0) -> int:
    try:
        if pd.isna(value):
            return default
        return int(float(value))
    except Exception:
        return default


def decide(df: pd.DataFrame, stage31f_run: Dict[str, Any]) -> Dict[str, Any]:
    if bool(stage31f_run.get("attempted")) and stage31f_run.get("returncode") not in (0, None):
        return {
            "decision": "STAGE31G_STAGE31F_ERROR_WATCHLIST_REVIEW_ONLY",
            "reason": "Stage31F returned a non-zero code. Existing cadence summary, if any, is not trusted.",
        }
    if df.empty:
        return {
            "decision": "STAGE31G_NO_CADENCE_SUMMARY_RESEARCH_ONLY",
            "reason": "No Stage31F cadence summary was available.",
        }

    work = df.copy()
    if "lookback_hours" in work.columns:
        work["lookback_hours"] = work["lookback_hours"].apply(lambda x: as_int(x, -1))
    else:
        work["lookback_hours"] = -1
    if "recent_signal_rows" not in work.columns:
        work["recent_signal_rows"] = 0
    work["recent_signal_rows"] = work["recent_signal_rows"].apply(as_int)
    if "latest_recent_entry_ts" not in work.columns:
        work["latest_recent_entry_ts"] = ""

    short_recent = int(work.loc[work["lookback_hours"].isin([336, 720]), "recent_signal_rows"].sum())
    mid_recent = int(work.loc[work["lookback_hours"].isin([2160]), "recent_signal_rows"].sum())
    long_recent = int(work.loc[work["lookback_hours"].isin([4320]), "recent_signal_rows"].sum())
    max_recent = int(work["recent_signal_rows"].max()) if len(work) else 0
    active_rows = work[work["recent_signal_rows"] > 0]
    latest = ""
    if not active_rows.empty:
        latest_vals = [str(x) for x in active_rows.get("latest_recent_entry_ts", pd.Series(dtype=str)).tolist() if str(x).strip()]
        latest = max(latest_vals) if latest_vals else ""

    if short_recent > 0:
        decision = "STAGE31G_SHORT_LOOKBACK_EXOGENOUS_WATCHLIST_SIGNAL_REVIEW_ONLY"
        reason = "A signal exists in the short lookback window. This remains observation-only."
    elif mid_recent > 0:
        decision = "STAGE31G_MID_LOOKBACK_EXOGENOUS_WATCHLIST_SIGNAL_REVIEW_ONLY"
        reason = "A signal exists in the 90-day lookback window. This remains observation-only."
    elif long_recent > 0:
        decision = "STAGE31G_LOW_CADENCE_WATCHLIST_REVIEW_ONLY"
        reason = "Only the long lookback window has signals; cadence is too sparse for promotion."
    else:
        decision = "STAGE31G_NO_EXOGENOUS_WATCHLIST_SIGNAL_RESEARCH_ONLY"
        reason = "No monitored lookback window has recent signals."

    return {
        "decision": decision,
        "reason": reason,
        "short_recent_signal_rows": short_recent,
        "mid_recent_signal_rows": mid_recent,
        "long_recent_signal_rows": long_recent,
        "max_recent_signal_rows": max_recent,
        "latest_recent_entry_ts": latest,
    }


def df_to_markdown(df: pd.DataFrame, max_rows: int = 50) -> str:
    if df.empty:
        return "_No rows._"
    show = df.head(max_rows).copy()
    try:
        return show.to_markdown(index=False)
    except Exception:
        cols = list(show.columns)
        lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
        for _, row in show.iterrows():
            lines.append("| " + " | ".join(str(row.get(c, "")) for c in cols) + " |")
        return "\n".join(lines)


def write_outputs(report: Dict[str, Any], cadence_df: pd.DataFrame, stage31f_run: Dict[str, Any]) -> None:
    ensure_dir(REPORT_DIR)
    json_path = REPORT_DIR / "stage31g_exogenous_active_suite_watchlist.json"
    md_path = REPORT_DIR / "stage31g_exogenous_active_suite_watchlist.md"
    csv_path = REPORT_DIR / "stage31g_cadence_summary.csv"

    if not cadence_df.empty:
        cadence_df.to_csv(csv_path, index=False)
    else:
        pd.DataFrame().to_csv(csv_path, index=False)

    payload = {
        "generated_utc": utc_now(),
        "report": report,
        "stage31f_run": stage31f_run,
        "source_paths": {
            "stage31f_summary": str(STAGE31F_SUMMARY),
            "stage31g_report_dir": str(REPORT_DIR),
        },
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    md: List[str] = []
    md.append("# Stage31G Exogenous Active-Suite Watchlist Status")
    md.append("")
    md.append(f"Generated UTC: `{payload['generated_utc']}`")
    md.append("")
    md.append("## Decision")
    md.append("")
    md.append("```text")
    md.append(str(report.get("decision", "UNKNOWN")))
    md.append("```")
    md.append("")
    md.append("## Scope guardrails")
    md.append("")
    md.append("- Research/shadow status only.")
    md.append("- No EA change, no automatic trading, no paper/live/order authorization.")
    md.append("- Consumes Stage31F/Stage31E reports only; no internet fetch is performed.")
    md.append("- A watchlist signal is an observation, not an instruction to trade.")
    md.append("")
    md.append("## Summary")
    md.append("")
    for key in [
        "reason",
        "short_recent_signal_rows",
        "mid_recent_signal_rows",
        "long_recent_signal_rows",
        "max_recent_signal_rows",
        "latest_recent_entry_ts",
    ]:
        if key in report:
            md.append(f"- {key}: `{report[key]}`")
    md.append("")
    md.append("## Stage31F run")
    md.append("")
    md.append("```json")
    md.append(json.dumps(stage31f_run, indent=2, ensure_ascii=False))
    md.append("```")
    md.append("")
    md.append("## Cadence summary")
    md.append("")
    md.append(df_to_markdown(cadence_df))
    md.append("")
    md.append("## Interpretation")
    md.append("")
    md.append("- Low-cadence watchlist status should not change operational behavior.")
    md.append("- Integration into active reporting is for visibility only.")
    md.append("- Promotion would require sustained forward-shadow evidence in short/mid lookbacks.")
    md.append("")
    md.append("## Output files")
    md.append("")
    md.append(f"- `{json_path}`")
    md.append(f"- `{md_path}`")
    md.append(f"- `{csv_path}`")
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")


def main() -> None:
    stage31f_run = run_stage31f_if_requested()
    cadence_df = load_cadence_summary()
    report = decide(cadence_df, stage31f_run)
    write_outputs(report, cadence_df, stage31f_run)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
