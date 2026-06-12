"""Run the active XAUUSD research-shadow suite in one command.

Order:
1) AMarkets CSV refresh/import cycle when available.
2) Stage18A unified shadow ops cycle.
3) Stage23D canonical DB-first tracker.
4) Stage25D London-range filtered DB-first tracker.
5) Stage27D H1-ATR filtered DB-first tracker.

Research/shadow only. No EA, no paper/live, no order authorization.
"""
from __future__ import annotations

import json
import runpy
import time
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

REPORT_DIR = Path("data/reports/active_shadow_suite")

MODULES = [
    ("csv_import_refresh", "app.stage16e_amarkets_csv_refresh_cycle", "data/reports/stage16e_amarkets_csv_refresh_cycle/stage16e_amarkets_csv_refresh_cycle.md"),
    ("stage18a_unified_shadow_ops_cycle", "app.stage18a_unified_shadow_ops_cycle", "data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.md"),
    ("stage23d_forward_shadow_candidate", "app.stage23d_forward_shadow_candidate", "data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_candidate.md"),
    ("stage25d_db_first_filtered_forward_shadow", "app.stage25d_db_first_filtered_forward_shadow", "data/reports/stage25d_db_first_filtered_forward_shadow/stage25d_db_first_filtered_forward_shadow.md"),
    ("stage27d_db_first_h1_atr_filtered_forward_shadow", "app.stage27d_db_first_h1_atr_filtered_forward_shadow", "data/reports/stage27d_db_first_h1_atr_filtered_forward_shadow/stage27d_db_first_h1_atr_filtered_forward_shadow.md"),
]


def _read_head(path: str, max_chars: int = 6000) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    txt = p.read_text(encoding="utf-8", errors="replace")
    return txt[:max_chars]


def _extract_decision(text: str) -> str:
    keys = ["final_decision:", "## Decision", "Decision"]
    if "final_decision:" in text:
        for line in text.splitlines():
            if "final_decision:" in line:
                return line.split("final_decision:", 1)[-1].strip(" `-")
    if "```text" in text:
        parts = text.split("```text", 1)[-1].split("```", 1)[0].strip()
        if parts:
            return parts.splitlines()[0].strip()
    return "UNKNOWN_DECISION"


def run_module(label: str, module: str, report_path: str) -> Dict[str, Any]:
    started = time.time()
    row: Dict[str, Any] = {"label": label, "module": module, "report_path": report_path, "status": "unknown"}
    try:
        runpy.run_module(module, run_name="__main__")
        row["status"] = "ok"
    except ModuleNotFoundError as exc:
        # Import refresh module names changed during the project; Stage18A still imports once.
        if label == "csv_import_refresh":
            row["status"] = "skipped_missing_module"
            row["error"] = str(exc)
        else:
            row["status"] = "error"
            row["error"] = f"{type(exc).__name__}: {exc}"
    except SystemExit as exc:
        if int(exc.code or 0) == 0:
            row["status"] = "ok"
        else:
            row["status"] = "error"
            row["error"] = f"SystemExit: {exc.code}"
    except Exception as exc:
        row["status"] = "error"
        row["error"] = f"{type(exc).__name__}: {exc}"
    row["runtime_seconds"] = round(time.time() - started, 2)
    text = _read_head(report_path)
    row["decision"] = _extract_decision(text) if text else "REPORT_NOT_FOUND"
    row["report_exists"] = Path(report_path).exists()
    return row


def write_reports(rows: List[Dict[str, Any]], started: float) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    result = {
        "generated_utc": pd.Timestamp.utcnow().isoformat(),
        "decision": "ACTIVE_SHADOW_SUITE_COMPLETED_WITH_ERRORS" if any(r["status"] == "error" for r in rows) else "ACTIVE_SHADOW_SUITE_COMPLETED",
        "scope_guardrails": [
            "Research/shadow only.",
            "No EA change, no automatic trading, no paper/live/order authorization.",
            "CSV import/refresh is attempted first when the import module exists.",
            "Stage18A still remains the active operational shadow runner.",
        ],
        "runtime_seconds": round(time.time() - started, 2),
        "runs": rows,
    }
    (REPORT_DIR / "active_shadow_suite.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    lines: List[str] = []
    lines.append("# Active XAUUSD Research-Shadow Suite\n")
    lines.append(f"Generated UTC: `{result['generated_utc']}`\n")
    lines.append("## Decision\n")
    lines.append("```text")
    lines.append(result["decision"])
    lines.append("```\n")
    lines.append("## Scope guardrails\n")
    for item in result["scope_guardrails"]:
        lines.append(f"- {item}")
    lines.append("\n## Run summary\n")
    cols = ["label", "status", "decision", "runtime_seconds", "report_path"]
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("| " + " | ".join(["---"] * len(cols)) + " |")
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    errors = [r for r in rows if r.get("error")]
    if errors:
        lines.append("\n## Errors / warnings\n")
        for r in errors:
            lines.append(f"- `{r['label']}`: `{r.get('error')}`")
    lines.append("\n## Output files\n")
    lines.append(f"- `{REPORT_DIR / 'active_shadow_suite.json'}`")
    lines.append(f"- `{REPORT_DIR / 'active_shadow_suite.md'}`")
    (REPORT_DIR / "active_shadow_suite.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    started = time.time()
    rows = []
    for label, module, report_path in MODULES:
        rows.append(run_module(label, module, report_path))
    write_reports(rows, started)
    if any(r["status"] == "error" for r in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
