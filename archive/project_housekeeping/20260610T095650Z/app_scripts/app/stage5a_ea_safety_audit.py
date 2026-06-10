"""
Stage 5A.1 — MT5 dry-run EA safety audit.

Purpose:
- Confirm the Stage 5A EA remains dry-run/log-only.
- Detect accidental order-placement or position-management code.
- Produce a compact JSON + Markdown report under data/reports/.

Usage:
  python3 -m app.stage5a_ea_safety_audit
  python3 -m app.stage5a_ea_safety_audit --ea mql5/Experts/XAUUSD/XAUUSD_DryRun_v1.mq5

No external dependencies.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

DEFAULT_EA_PATH = Path("mql5/Experts/XAUUSD/XAUUSD_DryRun_v1.mq5")
DEFAULT_REPORT_DIR = Path("data/reports")


@dataclass
class AuditItem:
    name: str
    status: str  # PASS / WARN / FAIL
    detail: str


FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    ("OrderSend", r"\bOrderSend\s*\("),
    ("CTrade include", r"#\s*include\s*<\s*Trade/Trade\.mqh\s*>"),
    ("CTrade object", r"\bCTrade\b"),
    ("Buy call", r"(?:\.|\b)Buy\s*\("),
    ("Sell call", r"(?:\.|\b)Sell\s*\("),
    ("PositionOpen", r"\bPositionOpen\s*\("),
    ("PositionClose", r"\bPositionClose\s*\("),
    ("OrderSendAsync", r"\bOrderSendAsync\s*\("),
    ("trade request action", r"\bMqlTradeRequest\b"),
    ("TRADE_ACTION_DEAL", r"\bTRADE_ACTION_DEAL\b"),
    ("TRADE_ACTION_PENDING", r"\bTRADE_ACTION_PENDING\b"),
]

REQUIRED_OR_EXPECTED_PATTERNS: list[tuple[str, str, str]] = [
    ("Uses FILE_COMMON for MT5 common CSV logging", r"\bFILE_COMMON\b", "FAIL"),
    ("Reads H1 data internally", r"\bPERIOD_H1\b", "FAIL"),
    ("Supports AUTO/chart-symbol behavior", r"\bInpSymbol\b|\b_Symbol\b", "WARN"),
    ("Contains strategy/dry-run wording", r"Dry[- ]?run|DRY[- ]?RUN|dry[- ]?run", "WARN"),
    ("Contains CSV logging logic", r"FileOpen\s*\(|\.csv\b", "WARN"),
]

SESSION_HINTS: list[tuple[str, str]] = [
    ("London blocked start hour 07 UTC", r"\b7\b|07:00|07"),
    ("London blocked end hour 13 UTC", r"\b13\b|13:00"),
]


def strip_comments(source: str) -> str:
    """Remove MQL/C-like comments before scanning for executable patterns."""
    no_block = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    no_line = re.sub(r"//.*", "", no_block)
    return no_line


def scan_forbidden(code: str) -> list[AuditItem]:
    items: list[AuditItem] = []
    for name, pattern in FORBIDDEN_PATTERNS:
        matches = list(re.finditer(pattern, code, flags=re.IGNORECASE))
        if matches:
            items.append(
                AuditItem(
                    name=f"Forbidden code check: {name}",
                    status="FAIL",
                    detail=f"Found {len(matches)} executable-looking occurrence(s).",
                )
            )
        else:
            items.append(
                AuditItem(
                    name=f"Forbidden code check: {name}",
                    status="PASS",
                    detail="No executable occurrence found.",
                )
            )
    return items


def scan_expected(code: str) -> list[AuditItem]:
    items: list[AuditItem] = []
    for name, pattern, missing_status in REQUIRED_OR_EXPECTED_PATTERNS:
        if re.search(pattern, code, flags=re.IGNORECASE):
            items.append(AuditItem(name=name, status="PASS", detail="Expected pattern found."))
        else:
            items.append(
                AuditItem(
                    name=name,
                    status=missing_status,
                    detail="Expected pattern not found; inspect EA manually.",
                )
            )
    for name, pattern in SESSION_HINTS:
        if re.search(pattern, code, flags=re.IGNORECASE):
            items.append(AuditItem(name=name, status="PASS", detail="Session boundary hint found."))
        else:
            items.append(
                AuditItem(
                    name=name,
                    status="WARN",
                    detail="Could not confirm this boundary by static scan; inspect session filter manually.",
                )
            )
    return items


def summarize(items: Iterable[AuditItem]) -> str:
    statuses = [item.status for item in items]
    if "FAIL" in statuses:
        return "FAIL"
    if "WARN" in statuses:
        return "WARN"
    return "PASS"


def write_reports(ea_path: Path, items: list[AuditItem], report_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    overall = summarize(items)

    payload = {
        "generated_at_utc": now,
        "stage": "5A.1",
        "tool": "stage5a_ea_safety_audit",
        "ea_path": str(ea_path),
        "overall_status": overall,
        "items": [asdict(item) for item in items],
        "hard_rule": "Stage 5A EA must remain dry-run/log-only and must not place or manage orders.",
    }

    json_path = report_dir / "stage5a1_ea_safety_audit.json"
    md_path = report_dir / "stage5a1_ea_safety_audit.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Stage 5A.1 EA Safety Audit",
        "",
        f"Generated UTC: `{now}`",
        f"EA path: `{ea_path}`",
        f"Overall status: **{overall}**",
        "",
        "> Hard rule: Stage 5A is dry-run/log-only. Any executable order-placement code is a blocker.",
        "",
        "| Status | Check | Detail |",
        "|---|---|---|",
    ]
    for item in items:
        lines.append(f"| {item.status} | {item.name} | {item.detail} |")
    lines.append("")
    if overall == "FAIL":
        lines.append("Decision: **Do not run this EA in MT5 until FAIL items are fixed and re-audited.**")
    elif overall == "WARN":
        lines.append("Decision: **Order-safety passed, but WARN items need manual review before relying on the dry-run log.**")
    else:
        lines.append("Decision: **Static audit passed for dry-run safety. Continue dry-run observation only.**")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 5A.1 MT5 dry-run EA safety audit")
    parser.add_argument("--ea", default=str(DEFAULT_EA_PATH), help="Path to the MQL5 EA file inside the repo")
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR), help="Output report directory")
    args = parser.parse_args()

    ea_path = Path(args.ea).expanduser()
    report_dir = Path(args.report_dir).expanduser()

    if not ea_path.exists():
        print(f"FAIL: EA file not found: {ea_path}")
        return 1

    source = ea_path.read_text(encoding="utf-8", errors="replace")
    executable_scan_text = strip_comments(source)

    items: list[AuditItem] = []
    items.extend(scan_forbidden(executable_scan_text))
    items.extend(scan_expected(executable_scan_text))

    json_path, md_path = write_reports(ea_path, items, report_dir)
    overall = summarize(items)

    print(f"Stage 5A.1 EA safety audit: {overall}")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {md_path}")
    return 1 if overall == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
