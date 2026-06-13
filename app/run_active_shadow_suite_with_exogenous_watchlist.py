from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

REPORT_DIR = Path("data/reports/active_shadow_suite_exogenous_watchlist")
ACTIVE_REPORT = Path("data/reports/active_shadow_suite/active_shadow_suite.md")
WATCHLIST_REPORT = Path("data/reports/stage31g_exogenous_active_suite_watchlist/stage31g_exogenous_active_suite_watchlist.md")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_module(module: str) -> Dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, "-m", module],
        text=True,
        capture_output=True,
    )
    return {
        "module": module,
        "returncode": int(proc.returncode),
        "stdout_tail": proc.stdout[-3000:],
        "stderr_tail": proc.stderr[-3000:],
    }


def extract_decision(path: Path) -> str:
    if not path.exists():
        return "MISSING_REPORT"
    text = path.read_text(encoding="utf-8", errors="replace")
    marker = "```text"
    idx = text.find(marker)
    if idx >= 0:
        end = text.find("```", idx + len(marker))
        if end > idx:
            return text[idx + len(marker):end].strip().splitlines()[0].strip()
    return "UNKNOWN_DECISION"


def write_outputs(runs: List[Dict[str, Any]]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    active_decision = extract_decision(ACTIVE_REPORT)
    watchlist_decision = extract_decision(WATCHLIST_REPORT)
    decision = "ACTIVE_SHADOW_SUITE_WITH_EXOGENOUS_WATCHLIST_COMPLETED"
    if any(r["returncode"] != 0 for r in runs):
        decision = "ACTIVE_SHADOW_SUITE_WITH_EXOGENOUS_WATCHLIST_COMPLETED_WITH_ERRORS"

    payload = {
        "generated_utc": utc_now(),
        "decision": decision,
        "active_suite_decision": active_decision,
        "exogenous_watchlist_decision": watchlist_decision,
        "runs": runs,
        "guardrails": [
            "Research/shadow only",
            "No EA change",
            "No paper/live/order authorization",
            "Exogenous watchlist is status-only",
        ],
    }
    (REPORT_DIR / "active_shadow_suite_exogenous_watchlist.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    md: List[str] = []
    md.append("# Active XAUUSD Research-Shadow Suite + Exogenous Watchlist")
    md.append("")
    md.append(f"Generated UTC: `{payload['generated_utc']}`")
    md.append("")
    md.append("## Decision")
    md.append("")
    md.append("```text")
    md.append(decision)
    md.append("```")
    md.append("")
    md.append("## Guardrails")
    md.append("")
    md.extend(f"- {x}" for x in payload["guardrails"])
    md.append("")
    md.append("## Summary")
    md.append("")
    md.append(f"- active_suite_decision: `{active_decision}`")
    md.append(f"- exogenous_watchlist_decision: `{watchlist_decision}`")
    md.append("")
    md.append("## Run results")
    md.append("")
    md.append("| module | returncode |")
    md.append("|---|---:|")
    for r in runs:
        md.append(f"| {r['module']} | {r['returncode']} |")
    md.append("")
    md.append("## Report paths")
    md.append("")
    md.append(f"- `{ACTIVE_REPORT}`")
    md.append(f"- `{WATCHLIST_REPORT}`")
    md.append(f"- `{REPORT_DIR / 'active_shadow_suite_exogenous_watchlist.md'}`")
    (REPORT_DIR / "active_shadow_suite_exogenous_watchlist.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def main() -> None:
    runs = [
        run_module("app.run_active_shadow_suite"),
        run_module("app.stage31g_exogenous_active_suite_watchlist"),
    ]
    write_outputs(runs)
    print(json.dumps({"runs": runs}, indent=2, ensure_ascii=False))
    if any(r["returncode"] != 0 for r in runs):
        sys.exit(1)


if __name__ == "__main__":
    main()
