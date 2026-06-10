#!/usr/bin/env python3
"""
Stage 5A CSV-format patch helper for XAUUSD_DryRun_v1.mq5.

Purpose:
- Fix native MT5 CSV/log encoding/header issues only.
- Do NOT alter trading logic.
- Do NOT add order/trade code.

This v4 version avoids false positives caused by forbidden words inside
comments or strings. It also only blocks newly introduced forbidden tokens.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Tuple

DEFAULT_EA = Path("mql5/Experts/XAUUSD/XAUUSD_DryRun_v1.mq5")
REPORT_JSON = Path("data/reports/stage5a_csv_format_patch_report.json")
REPORT_MD = Path("data/reports/stage5a_csv_format_patch_report.md")

FORBIDDEN_TOKENS = (
    "OrderSend",
    "CTrade",
    ".Buy(",
    ".Sell(",
    "PositionOpen",
    "PositionClose",
    "trade.Buy",
    "trade.Sell",
)

@dataclass
class PatchReport:
    generated_utc: str
    tool_version: str
    ea_source: str
    detected_encoding: str
    apply: bool
    status: str
    changes: List[str]
    warnings: List[str]
    errors: List[str]


def detect_encoding(path: Path) -> Tuple[str, str]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", raw.decode("utf-8-sig", errors="replace")
    return "utf-8", raw.decode("utf-8", errors="replace")


def strip_mql5_comments_and_strings(src: str) -> str:
    """Return code-like text with comments and string literals removed.

    This is intentionally conservative and only used to avoid false-positive
    safety-token scans on comments/strings such as "No CTrade".
    """
    out: List[str] = []
    i = 0
    n = len(src)
    state = "code"
    while i < n:
        ch = src[i]
        nxt = src[i + 1] if i + 1 < n else ""

        if state == "code":
            if ch == "/" and nxt == "/":
                state = "line_comment"
                out.append(" ")
                i += 2
                continue
            if ch == "/" and nxt == "*":
                state = "block_comment"
                out.append(" ")
                i += 2
                continue
            if ch == '"':
                state = "double_string"
                out.append('""')
                i += 1
                continue
            if ch == "'":
                state = "single_string"
                out.append("''")
                i += 1
                continue
            out.append(ch)
            i += 1
            continue

        if state == "line_comment":
            if ch == "\n":
                state = "code"
                out.append("\n")
            else:
                out.append(" ")
            i += 1
            continue

        if state == "block_comment":
            if ch == "*" and nxt == "/":
                state = "code"
                out.append(" ")
                i += 2
            else:
                out.append("\n" if ch == "\n" else " ")
                i += 1
            continue

        if state == "double_string":
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == '"':
                state = "code"
                i += 1
                continue
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue

        if state == "single_string":
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == "'":
                state = "code"
                i += 1
                continue
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue

    return "".join(out)


def forbidden_tokens_in_code(src: str) -> List[str]:
    code = strip_mql5_comments_and_strings(src)
    found: List[str] = []
    for tok in FORBIDDEN_TOKENS:
        if tok in code:
            found.append(tok)
    return found


def add_file_ansi_to_filecommon(src: str) -> Tuple[str, List[str]]:
    changes: List[str] = []

    # Patch line-by-line to keep the transformation explainable and small.
    lines = src.splitlines(keepends=True)
    new_lines: List[str] = []
    for line in lines:
        new_line = line
        # Only patch lines that call FileOpen and contain FILE_COMMON but not FILE_ANSI.
        if "FileOpen" in line and "FILE_COMMON" in line and "FILE_ANSI" not in line:
            new_line = line.replace("FILE_COMMON", "FILE_COMMON|FILE_ANSI")
            if new_line != line:
                changes.append("Added FILE_ANSI to a FILE_COMMON FileOpen(...) call.")
        new_lines.append(new_line)
    return "".join(new_lines), changes


def fix_header_join_bug(src: str) -> Tuple[str, List[str]]:
    changes: List[str] = []
    replacements = [
        ("sma10distance_usd", "sma10\\tdistance_usd"),
        ("sma10\" \"distance_usd", "sma10\\tdistance_usd"),
        ("sma10\"distance_usd", "sma10\\tdistance_usd"),
        ("sma10' 'distance_usd", "sma10\\tdistance_usd"),
        ("sma10'distance_usd", "sma10\\tdistance_usd"),
    ]
    new_src = src
    for old, new in replacements:
        if old in new_src:
            new_src = new_src.replace(old, new)
            changes.append(f"Fixed CSV header join bug: {old} -> {new}.")

    # Also catch adjacent quoted fragments where a tab was omitted, e.g.
    # "sma10" + "distance_usd". This avoids a fragile exact-match dependency.
    pattern = re.compile(r'(sma10\\?t?)\s*"\s*\+\s*"\s*distance_usd')
    if pattern.search(new_src):
        new_src = pattern.sub('sma10\\tdistance_usd', new_src)
        changes.append("Fixed adjacent quoted CSV header fragments for sma10/distance_usd.")

    return new_src, changes


def patch_source(src: str) -> Tuple[str, List[str], List[str]]:
    changes: List[str] = []
    warnings: List[str] = []

    patched, c = add_file_ansi_to_filecommon(src)
    changes.extend(c)

    patched2, c = fix_header_join_bug(patched)
    changes.extend(c)

    # If the exact broken header is not present, record a warning rather than fail.
    if not any("CSV header join" in item or "sma10/distance_usd" in item for item in changes):
        warnings.append("No explicit sma10/distance_usd header-join bug was found. EA may already be fixed or uses a different header construction.")

    if not any("FILE_ANSI" in item for item in changes):
        warnings.append("No FILE_COMMON FileOpen(...) call needed FILE_ANSI, or it was already present.")

    return patched2, changes, warnings


def write_reports(report: PatchReport) -> None:
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False), encoding="utf-8")

    status_icon = "PASS" if report.status == "PASS" else report.status
    lines = [
        "# Stage 5A CSV Format Patch Report",
        "",
        f"Generated UTC: `{report.generated_utc}`",
        f"Tool version: `{report.tool_version}`",
        f"EA source: `{report.ea_source}`",
        f"Detected encoding: `{report.detected_encoding}`",
        f"Apply mode: `{report.apply}`",
        f"Overall status: **{status_icon}**",
        "",
        "> Scope: CSV format only. This tool does not authorize demo, paper, or live orders.",
        "",
        "## Changes",
    ]
    if report.changes:
        lines.extend([f"- {x}" for x in report.changes])
    else:
        lines.append("- No changes required or no patchable pattern found.")
    lines.append("")
    lines.append("## Warnings")
    if report.warnings:
        lines.extend([f"- {x}" for x in report.warnings])
    else:
        lines.append("- None")
    lines.append("")
    lines.append("## Errors")
    if report.errors:
        lines.extend([f"- {x}" for x in report.errors])
    else:
        lines.append("- None")
    lines.append("")
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch Stage 5A EA CSV formatting only.")
    parser.add_argument("--ea", default=str(DEFAULT_EA), help="Path to XAUUSD_DryRun_v1.mq5")
    parser.add_argument("--check", action="store_true", help="Check what would change without writing.")
    parser.add_argument("--apply", action="store_true", help="Apply safe CSV-format patch.")
    args = parser.parse_args()

    if not args.check and not args.apply:
        parser.error("Use --check or --apply")

    ea_path = Path(args.ea)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    errors: List[str] = []
    warnings: List[str] = []
    changes: List[str] = []
    encoding = "unknown"
    status = "FAIL"

    try:
        if not ea_path.exists():
            errors.append(f"EA file not found: {ea_path}")
        else:
            encoding, src = detect_encoding(ea_path)
            before_forbidden = set(forbidden_tokens_in_code(src))
            patched, changes, warnings = patch_source(src)
            after_forbidden = set(forbidden_tokens_in_code(patched))
            newly_introduced = sorted(after_forbidden - before_forbidden)

            if newly_introduced:
                errors.append("Patch would introduce forbidden trade/order token(s): " + ", ".join(newly_introduced))
            elif patched == src:
                status = "PASS"
                warnings.append("No file changes were applied because source already appears patched or patterns were not found.")
            else:
                status = "PASS"
                if args.apply:
                    ea_path.write_text(patched, encoding="utf-8-sig" if encoding == "utf-8-sig" else "utf-8")

            # Existing forbidden tokens in code are not allowed, but comments/strings are ignored.
            # This check remains separate and should agree with Stage 5A.1 audit.
            if before_forbidden:
                errors.append("Forbidden trade/order token(s) already present in executable code before patch: " + ", ".join(sorted(before_forbidden)))
                status = "FAIL"

    except Exception as exc:  # noqa: BLE001 - user-facing CLI
        errors.append(f"Unhandled error: {exc}")

    if errors:
        status = "FAIL"

    report = PatchReport(
        generated_utc=now,
        tool_version="v4",
        ea_source=str(ea_path),
        detected_encoding=encoding,
        apply=bool(args.apply),
        status=status,
        changes=changes,
        warnings=warnings,
        errors=errors,
    )
    write_reports(report)

    print(f"EA source: {ea_path}")
    print(f"Detected encoding: {encoding}")
    if changes:
        print("Patchable CSV-format issues found:")
        for item in changes:
            print(f"  - {item}")
    else:
        print("No patchable CSV-format issues found.")
    if warnings:
        print("Warnings:")
        for item in warnings:
            print(f"  - {item}")
    if errors:
        print("Errors:")
        for item in errors:
            print(f"  - {item}")
    print(f"Stage 5A CSV-format patch helper: {status}")
    print(f"JSON report: {REPORT_JSON}")
    print(f"Markdown report: {REPORT_MD}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
