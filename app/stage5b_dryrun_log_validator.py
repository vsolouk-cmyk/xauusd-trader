"""Stage 5B dry-run log validator for XAUUSD MT5 EA logs.

Standard-library only. Validates dry-run/log-only CSV evidence; it does not
approve demo, paper, or live orders.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

TOOL_VERSION = "v4"
DEFAULT_LOG_NAME = "XAUUSD_DryRun_v1_signals.csv"
DEFAULT_STRATEGY_ID = "xauusd_long_tp24_sl15_no_london_v1"
REPORT_DIR = Path("data/reports")
JSON_REPORT = REPORT_DIR / "stage5b_dryrun_log_validator.json"
MD_REPORT = REPORT_DIR / "stage5b_dryrun_log_validator.md"

# EA-native columns from XAUUSD_DryRun_v1.mq5 after Stage 5A CSV header fix.
EA_NATIVE_SIGNAL_ONLY_COLUMNS = {
    "logged_at_gmt",
    "symbol",
    "chart_symbol",
    "strategy_id",
    "signal_closed_h1_time_server",
    "signal_closed_h1_time_gmt_now",
    "session_utc",
    "close_h1",
    "sma10",
    "distance_usd",
    "direction",
    "planned_entry_model",
    "tp_usd",
    "sl_usd",
    "time_exit_h1_bars",
    "dry_run_only",
}

CANONICAL_ALIASES = {
    "timestamp_utc": [
        "timestamp_utc",
        "logged_at_utc",
        "logged_at_gmt",
        "time_utc",
        "time_gmt",
        "created_at_utc",
    ],
    "closed_h1_time_utc": [
        "closed_h1_time_utc",
        "signal_closed_h1_time_utc",
        "signal_closed_h1_time_gmt",
        "signal_closed_h1_time_gmt_now",
        "signal_closed_h1_time_server",
    ],
    "symbol": ["symbol", "broker_symbol", "resolved_symbol"],
    "strategy_id": ["strategy_id", "strategy", "strategy_name"],
    # Important: do NOT include dry_run_only. It is a safety flag, not a signal flag.
    "signal": ["signal", "is_signal", "signal_state", "signal_status", "event_signal"],
    "reason": ["reason", "status", "event_type", "message", "log_reason"],
    "session_name": ["session_name", "session", "session_utc", "utc_session"],
    "session_allowed": ["session_allowed", "allowed_session", "is_session_allowed"],
    "distance_usd": ["distance_usd", "sma_distance_usd", "distance", "dist_usd"],
    "close": ["close", "close_h1", "h1_close"],
    "sma10": ["sma10", "sma_10", "sma10_h1", "h1_sma10"],
    "take_profit_usd": ["take_profit_usd", "tp_usd", "tp", "take_profit"],
    "stop_loss_usd": ["stop_loss_usd", "sl_usd", "sl", "stop_loss"],
    "direction": ["direction", "side", "trade_direction"],
    "dry_run_only": ["dry_run_only", "dry_run", "log_only"],
    "time_exit_h1_bars": ["time_exit_h1_bars", "time_exit_bars", "max_hold_h1_bars"],
}

@dataclass
class Check:
    status: str
    name: str
    detail: str


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean_header_cell(value: str) -> str:
    value = value.replace("\ufeff", "")
    value = value.replace("�", "")
    value = value.strip().strip('"').strip("'")
    return value


def _normalize_col(value: str) -> str:
    value = _clean_header_cell(value)
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value


def _decode_bytes(raw: bytes) -> Tuple[str, str]:
    for enc in ("utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "cp1252", "latin-1"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8-replace"


def _detect_delimiter(text: str) -> Tuple[str, str]:
    sample = "\n".join(text.splitlines()[:5])
    candidates = [("\t", "TAB"), (",", "COMMA"), (";", "SEMICOLON"), ("|", "PIPE")]
    counts = [(sample.count(d), d, name) for d, name in candidates]
    counts.sort(reverse=True, key=lambda x: x[0])
    if counts and counts[0][0] > 0:
        return counts[0][1], counts[0][2]
    try:
        dialect = csv.Sniffer().sniff(sample)
        name = {"\t": "TAB", ",": "COMMA", ";": "SEMICOLON", "|": "PIPE"}.get(dialect.delimiter, dialect.delimiter)
        return dialect.delimiter, name
    except Exception:
        return ",", "COMMA_FALLBACK"


def _fix_known_header(header: List[str]) -> Tuple[List[str], List[str]]:
    notes: List[str] = []
    out: List[str] = []
    for cell in header:
        raw = _clean_header_cell(cell)
        norm = _normalize_col(raw)
        if norm == "sma10distance_usd":
            out.extend(["sma10", "distance_usd"])
            notes.append("Split broken header cell sma10distance_usd into sma10 + distance_usd.")
        else:
            out.append(raw)
    return out, notes


def _read_csv(path: Path) -> Tuple[List[str], List[Dict[str, str]], str, str, str, List[str]]:
    raw = path.read_bytes()
    text, encoding = _decode_bytes(raw)
    delimiter, delimiter_name = _detect_delimiter(text)
    # Drop fully blank lines but preserve row content.
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return [], [], encoding, delimiter_name, delimiter, []
    reader = csv.reader(lines, delimiter=delimiter)
    raw_rows = list(reader)
    if not raw_rows:
        return [], [], encoding, delimiter_name, delimiter, []
    header, notes = _fix_known_header(raw_rows[0])
    norm_header = [_normalize_col(h) for h in header]
    rows: List[Dict[str, str]] = []
    for raw_row in raw_rows[1:]:
        # If the old broken header had one fewer delimiter than the row, align conservatively.
        row = list(raw_row)
        if len(row) < len(norm_header):
            row += [""] * (len(norm_header) - len(row))
        if len(row) > len(norm_header):
            row = row[: len(norm_header)]
        mapped = {norm_header[i]: (row[i].strip() if i < len(row) else "") for i in range(len(norm_header))}
        if any(v != "" for v in mapped.values()):
            rows.append(mapped)
    return norm_header, rows, encoding, delimiter_name, delimiter, notes


def _find_col(columns: Sequence[str], aliases: Sequence[str]) -> Optional[str]:
    colset = set(columns)
    for alias in aliases:
        norm = _normalize_col(alias)
        if norm in colset:
            return norm
    return None


def _resolve_columns(columns: Sequence[str]) -> Dict[str, Optional[str]]:
    return {key: _find_col(columns, aliases) for key, aliases in CANONICAL_ALIASES.items()}


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.replace(",", ".")
    try:
        x = float(s)
        if math.isfinite(x):
            return x
    except ValueError:
        return None
    return None


def _truthy(value: Any) -> Optional[bool]:
    s = str(value).strip().lower()
    if s in {"1", "true", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _is_london_session(value: str) -> bool:
    s = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    return s in {"london", "ldn"} or s.startswith("london_")


def _search_for_log(root: Path, name: str = DEFAULT_LOG_NAME) -> Optional[Path]:
    if not root.exists():
        return None
    matches = []
    try:
        for p in root.rglob(name):
            if p.is_file():
                matches.append(p)
    except (PermissionError, OSError):
        pass
    if not matches:
        return None
    matches.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return matches[0]


def _write_reports(report: Dict[str, Any]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines: List[str] = []
    lines.append("# Stage 5B Dry-run Log Validator")
    lines.append("")
    lines.append(f"Generated UTC: `{report['generated_utc']}`")
    lines.append(f"Tool version: `{report['tool_version']}`")
    lines.append(f"Strict mode: `{report['strict_mode']}`")
    lines.append(f"Overall status: **{report['overall_status']}**")
    lines.append("")
    lines.append("> Hard rule: this validates dry-run logs only. It does not authorize demo, paper, or live orders.")
    lines.append("")
    lines.append("## Stats")
    lines.append("")
    for key, value in report["stats"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    lines.append("## Detected columns")
    lines.append("")
    for col in report["columns"]:
        lines.append(f"- `{col}`")
    lines.append("")
    lines.append("## Resolved columns")
    lines.append("")
    for key, value in report["resolved_columns"].items():
        if value:
            lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("## Checks")
    lines.append("")
    lines.append("| Status | Check | Detail |")
    lines.append("|---|---|---|")
    for chk in report["checks"]:
        detail = str(chk["detail"]).replace("|", "\\|")
        lines.append(f"| {chk['status']} | {chk['name']} | {detail} |")
    lines.append("")
    lines.append(f"Decision: **{report['decision']}**")
    lines.append("")
    MD_REPORT.write_text("\n".join(lines), encoding="utf-8")


def validate(csv_path: Path, strict: bool = False, expected_strategy_id: str = DEFAULT_STRATEGY_ID) -> Dict[str, Any]:
    checks: List[Check] = []
    if not csv_path.exists():
        checks.append(Check("FAIL", "CSV file", f"File not found: {csv_path}"))
        report = _build_report(csv_path, [], {}, [], checks, strict, {}, None, None)
        _write_reports(report)
        return report

    size = csv_path.stat().st_size
    if size == 0:
        checks.append(Check("WARN", "CSV file", "File exists but is empty. This can be normal before first market tick/log row."))
        report = _build_report(csv_path, [], {}, [], checks, strict, {"file_size_bytes": size}, None, None)
        _write_reports(report)
        return report

    columns, rows, encoding, delimiter_name, delimiter, header_notes = _read_csv(csv_path)
    resolved = _resolve_columns(columns)
    colset = set(columns)
    native_signal_only_schema = EA_NATIVE_SIGNAL_ONLY_COLUMNS.issubset(colset)

    checks.append(Check("PASS" if columns else "FAIL", "CSV header", f"Detected {len(columns)} column(s)."))
    checks.append(Check("PASS", "CSV delimiter", f"Detected delimiter: {delimiter_name}."))
    checks.append(Check("PASS" if rows else "WARN", "CSV rows", f"Detected {len(rows)} data row(s)."))
    if encoding.lower() not in {"utf-8-sig", "utf-8"}:
        checks.append(Check("WARN", "CSV encoding", f"Decoded as {encoding}. UTF-8/ANSI output is preferred."))
    else:
        checks.append(Check("PASS", "CSV encoding", f"Decoded as {encoding}."))
    for note in header_notes:
        checks.append(Check("WARN", "Known header repair", note))

    if native_signal_only_schema:
        checks.append(Check("PASS", "EA-native signal-only schema", "Detected Stage 5A EA signal-log schema. Rows are treated as dry-run signal records."))
    else:
        missing_native = sorted(EA_NATIVE_SIGNAL_ONLY_COLUMNS - colset)
        checks.append(Check("WARN", "EA-native signal-only schema", f"Not fully detected. Missing: {', '.join(missing_native[:12])}{'...' if len(missing_native) > 12 else ''}"))

    # Mapping checks.
    if resolved.get("timestamp_utc") or resolved.get("closed_h1_time_utc"):
        checks.append(Check("PASS", "Usable time column", f"timestamp={resolved.get('timestamp_utc')}, closed_h1={resolved.get('closed_h1_time_utc')}"))
    elif rows:
        checks.append(Check("FAIL", "Usable time column", "Rows exist but no timestamp/H1-time column could be mapped."))
    else:
        checks.append(Check("WARN", "Usable time column", "No rows yet; cannot validate timestamps."))

    if resolved.get("signal"):
        checks.append(Check("PASS", "Signal/event column", f"Mapped explicit signal column: {resolved['signal']}"))
    elif native_signal_only_schema:
        checks.append(Check("PASS" if not strict else "WARN", "Signal/event column", "No explicit signal column, but EA-native schema is signal-only; each data row is treated as a dry-run signal."))
    else:
        checks.append(Check("WARN", "Signal/event column", "No explicit signal column. This is acceptable only for signal-only CSV schemas."))

    if resolved.get("reason"):
        checks.append(Check("PASS", "Reason/status column", f"Mapped reason/status column: {resolved['reason']}"))
    elif native_signal_only_schema:
        checks.append(Check("WARN", "Reason/status column", "No reason/status column in current EA-native schema. Acceptable for signal-only logs, but less informative."))
    else:
        checks.append(Check("WARN", "Reason/status column", "No reason/status column found."))

    # Validate rows.
    signal_rows = 0
    blocked_rows = 0
    no_signal_rows = 0

    if rows:
        if native_signal_only_schema and not resolved.get("signal"):
            signal_rows = len(rows)
        else:
            sig_col = resolved.get("signal")
            reason_col = resolved.get("reason")
            for row in rows:
                sig = str(row.get(sig_col or "", "")).strip().lower()
                reason = str(row.get(reason_col or "", "")).strip().lower()
                combined = f"{sig} {reason}"
                if any(x in combined for x in ["signal", "long", "buy", "entry"]):
                    signal_rows += 1
                if "blocked" in combined or "skip" in combined or "london" in combined:
                    blocked_rows += 1
                if "no_signal" in combined or "no signal" in combined:
                    no_signal_rows += 1

        # Dry-run-only safety flag.
        dry_col = resolved.get("dry_run_only")
        if dry_col:
            values = [_truthy(row.get(dry_col, "")) for row in rows]
            bad = [v for v in values if v is not True]
            if bad:
                checks.append(Check("FAIL", "Dry-run-only flag", f"{len(bad)} row(s) are not explicitly dry_run_only=true."))
            else:
                checks.append(Check("PASS", "Dry-run-only flag", "All rows have dry_run_only=true."))
        else:
            checks.append(Check("WARN", "Dry-run-only flag", "Column unavailable; cannot verify dry_run_only flag."))

        # Strategy ID.
        sid_col = resolved.get("strategy_id")
        if sid_col:
            mismatches = [row.get(sid_col, "") for row in rows if row.get(sid_col, "") != expected_strategy_id]
            if mismatches:
                checks.append(Check("FAIL", "Strategy ID consistency", f"{len(mismatches)} row(s) do not match {expected_strategy_id}."))
            else:
                checks.append(Check("PASS", "Strategy ID consistency", f"All rows match {expected_strategy_id}."))
        else:
            checks.append(Check("WARN", "Strategy ID consistency", "Strategy column unavailable; cannot verify strategy ID."))

        # Direction.
        direction_col = resolved.get("direction")
        if direction_col:
            bad_dir = [row.get(direction_col, "") for row in rows if str(row.get(direction_col, "")).strip().lower() not in {"long", "buy"}]
            if bad_dir:
                checks.append(Check("FAIL", "Long-only direction", f"{len(bad_dir)} row(s) are not long/buy."))
            else:
                checks.append(Check("PASS", "Long-only direction", "All rows are long/buy."))
        else:
            checks.append(Check("WARN", "Long-only direction", "Direction column unavailable."))

        # TP/SL/time exit.
        for label, colkey, expected in [
            ("TP USD", "take_profit_usd", 24.0),
            ("SL USD", "stop_loss_usd", 15.0),
            ("Time exit H1 bars", "time_exit_h1_bars", 12.0),
        ]:
            col = resolved.get(colkey)
            if not col:
                checks.append(Check("WARN", label, f"Column {colkey} unavailable."))
                continue
            bad = []
            for row in rows:
                val = _to_float(row.get(col))
                if val is None or abs(val - expected) > 1e-9:
                    bad.append(row.get(col, ""))
            if bad:
                checks.append(Check("FAIL", label, f"{len(bad)} row(s) do not match expected {expected}."))
            else:
                checks.append(Check("PASS", label, f"All rows match expected {expected}."))

        # Distance arithmetic.
        c_col, s_col, d_col = resolved.get("close"), resolved.get("sma10"), resolved.get("distance_usd")
        if c_col and s_col and d_col:
            bad = 0
            checked = 0
            for row in rows:
                close = _to_float(row.get(c_col))
                sma = _to_float(row.get(s_col))
                dist = _to_float(row.get(d_col))
                if close is None or sma is None or dist is None:
                    continue
                checked += 1
                if abs((close - sma) - dist) > 0.05:
                    bad += 1
            if checked == 0:
                checks.append(Check("WARN", "Distance arithmetic", "Columns exist but no numeric rows could be checked."))
            elif bad:
                checks.append(Check("FAIL", "Distance arithmetic", f"{bad}/{checked} row(s) failed close - sma10 ≈ distance_usd."))
            else:
                checks.append(Check("PASS", "Distance arithmetic", f"Checked {checked} row(s): close - sma10 ≈ distance_usd."))
        else:
            checks.append(Check("WARN", "Distance arithmetic", "close/sma10/distance columns unavailable; cannot verify signal arithmetic."))

        # No-London filter: signal rows must not be London.
        sess_col = resolved.get("session_name")
        if sess_col:
            london_rows = [row for row in rows if _is_london_session(row.get(sess_col, ""))]
            if london_rows:
                checks.append(Check("FAIL", "No-London filter", f"{len(london_rows)} signal row(s) are in blocked London session."))
            else:
                checks.append(Check("PASS", "No-London filter", "No signal rows are marked as London session."))
        else:
            checks.append(Check("WARN", "No-London filter", "Session column unavailable; cannot verify London blocking from CSV alone."))
    else:
        checks.append(Check("WARN", "Evidence readiness", "No data rows yet. Header/schema can be checked, but dry-run evidence starts after first logged row."))

    extra_stats = {
        "file_size_bytes": size,
        "encoding": encoding,
        "detected_delimiter": delimiter_name,
        "rows": len(rows),
        "signals": signal_rows,
        "blocked_skipped_rows": blocked_rows,
        "no_signal_rows": no_signal_rows,
        "native_signal_only_schema": native_signal_only_schema,
    }
    report = _build_report(csv_path, columns, resolved, rows, checks, strict, extra_stats, encoding, delimiter_name)
    _write_reports(report)
    return report


def _build_report(
    csv_path: Path,
    columns: List[str],
    resolved: Dict[str, Optional[str]],
    rows: List[Dict[str, str]],
    checks: List[Check],
    strict: bool,
    extra_stats: Dict[str, Any],
    encoding: Optional[str],
    delimiter_name: Optional[str],
) -> Dict[str, Any]:
    statuses = [c.status for c in checks]
    if "FAIL" in statuses:
        overall = "FAIL"
        decision = "Do not rely on this dry-run log until FAIL items are fixed."
    elif "WARN" in statuses:
        # In non-strict mode, WARN is acceptable when only informational limitations remain.
        overall = "WARN" if strict else "PASS_WITH_WARNINGS"
        decision = "Usable for Stage 5B dry-run monitoring with warnings; not authorization for demo/paper/live orders."
    else:
        overall = "PASS"
        decision = "Dry-run log passed Stage 5B validation; still not authorization for demo/paper/live orders."

    stats = {
        "CSV path": str(csv_path),
        **extra_stats,
    }
    return {
        "generated_utc": _now_utc(),
        "tool_version": TOOL_VERSION,
        "strict_mode": strict,
        "overall_status": overall,
        "decision": decision,
        "stats": stats,
        "columns": columns,
        "resolved_columns": {k: v for k, v in resolved.items() if v},
        "checks": [asdict(c) for c in checks],
        "sample_rows": rows[:5],
        "report_paths": {
            "json": str(JSON_REPORT),
            "markdown": str(MD_REPORT),
        },
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate XAUUSD Stage 5B MT5 dry-run CSV logs.")
    parser.add_argument("--csv", dest="csv_path", help="Path to XAUUSD_DryRun_v1_signals.csv")
    parser.add_argument("--search-root", help="Search root for XAUUSD_DryRun_v1_signals.csv")
    parser.add_argument("--strict", action="store_true", help="Treat non-critical warnings as non-pass status.")
    parser.add_argument("--expected-strategy-id", default=DEFAULT_STRATEGY_ID)
    parser.add_argument("--print-columns", action="store_true")
    args = parser.parse_args(argv)

    csv_path: Optional[Path] = Path(args.csv_path).expanduser() if args.csv_path else None
    if csv_path is None and args.search_root:
        csv_path = _search_for_log(Path(args.search_root).expanduser())
    if csv_path is None:
        print("Stage 5B dry-run log validator: FAIL")
        print("No CSV path provided and no log found with --search-root.")
        return 2

    report = validate(csv_path, strict=args.strict, expected_strategy_id=args.expected_strategy_id)
    print(f"Stage 5B dry-run log validator: {report['overall_status']}")
    print(f"CSV: {csv_path}")
    print(f"JSON report: {JSON_REPORT}")
    print(f"Markdown report: {MD_REPORT}")
    if args.print_columns:
        print("Detected columns:")
        for c in report.get("columns", []):
            print(f"  - {c}")
        print("Resolved columns:")
        for k, v in report.get("resolved_columns", {}).items():
            print(f"  - {k}: {v}")
    return 1 if report["overall_status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
