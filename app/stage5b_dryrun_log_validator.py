"""
Stage 5B — MT5 dry-run CSV log validator.

Purpose:
- Find/read the MT5 Common Files CSV produced by XAUUSD_DryRun_v1.
- Validate headers, parse rows, detect obvious schema/time/session/signal problems.
- Produce JSON + Markdown reports under data/reports/.

Usage examples:
  python3 -m app.stage5b_dryrun_log_validator --csv samples/stage5b_mt5_dryrun_sample.csv
  python3 -m app.stage5b_dryrun_log_validator --search-root "$HOME/Library/Application Support"
  python3 -m app.stage5b_dryrun_log_validator --search-root "$HOME/.wine"

No external dependencies.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DEFAULT_LOG_NAME = "XAUUSD_DryRun_v1_signals.csv"
DEFAULT_REPORT_DIR = Path("data/reports")
DEFAULT_STRATEGY_JSON = Path("configs/locked_strategy_v1.json")

RECOMMENDED_COLUMNS = [
    "timestamp_utc",
    "symbol",
    "strategy_id",
    "ea_version",
    "chart_timeframe",
    "signal_timeframe",
    "closed_h1_time_utc",
    "close",
    "sma10",
    "distance_usd",
    "session_name",
    "session_allowed",
    "signal",
    "reason",
]

COLUMN_ALIASES = {
    "timestamp_utc": {"timestamp_utc", "time_utc", "timestamp", "logged_at_utc", "logged_time_utc", "server_time_utc"},
    "closed_h1_time_utc": {"closed_h1_time_utc", "h1_time_utc", "bar_time_utc", "signal_bar_time_utc", "closed_bar_time_utc"},
    "symbol": {"symbol", "resolved_symbol", "mt5_symbol"},
    "strategy_id": {"strategy_id", "strategy", "strategy_name"},
    "signal": {"signal", "is_signal", "dry_run_signal", "has_signal"},
    "reason": {"reason", "message", "status", "event"},
    "session_name": {"session_name", "session", "market_session"},
    "session_allowed": {"session_allowed", "allowed_session", "is_session_allowed"},
    "distance_usd": {"distance_usd", "distance", "close_minus_sma", "close_minus_sma10"},
    "close": {"close", "h1_close", "closed_h1_close"},
    "sma10": {"sma10", "sma_10", "sma"},
}

TRUE_VALUES = {"1", "true", "yes", "y", "signal", "logged"}
FALSE_VALUES = {"0", "false", "no", "n", "none", ""}


@dataclass
class ValidationItem:
    name: str
    status: str  # PASS / WARN / FAIL
    detail: str


def normalize_col(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def resolve_columns(fieldnames: list[str]) -> dict[str, str]:
    normalized = {normalize_col(col): col for col in fieldnames}
    resolved: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if normalize_col(alias) in normalized:
                resolved[canonical] = normalized[normalize_col(alias)]
                break
    return resolved


def parse_bool(value: Any) -> bool | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    return None


def parse_dt(value: str) -> datetime | None:
    text = str(value).strip()
    if not text:
        return None
    candidates = [
        text,
        text.replace("Z", "+00:00"),
        text.replace("/", "-"),
    ]
    formats = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y.%m.%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    ]
    for candidate in candidates:
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass
        for fmt in formats:
            try:
                dt = datetime.strptime(candidate, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except ValueError:
                continue
    return None


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def find_log_file(search_roots: Iterable[Path], filename: str = DEFAULT_LOG_NAME, max_files: int = 250_000) -> Path | None:
    checked = 0
    skip_dirs = {"node_modules", ".git", "__pycache__", "Caches", "Cache", "Trash"}
    for root in search_roots:
        root = root.expanduser()
        if not root.exists():
            continue
        if root.is_file() and root.name == filename:
            return root
        for current_root, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
            checked += len(files)
            if filename in files:
                return Path(current_root) / filename
            if checked >= max_files:
                return None
    return None


def load_strategy(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def validate(csv_path: Path, strategy: dict[str, Any]) -> tuple[list[ValidationItem], list[dict[str, str]], dict[str, Any]]:
    items: list[ValidationItem] = []
    if not csv_path.exists():
        return [ValidationItem("CSV exists", "FAIL", f"File not found: {csv_path}")], [], {}

    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            rows = [dict(row) for row in reader]
    except Exception as exc:  # noqa: BLE001 - diagnostic tool
        return [ValidationItem("CSV readable", "FAIL", f"Could not read CSV: {exc}")], [], {}

    if not fieldnames:
        items.append(ValidationItem("CSV header", "FAIL", "CSV has no header row."))
        return items, rows, {}
    items.append(ValidationItem("CSV header", "PASS", f"Detected {len(fieldnames)} column(s)."))

    if not rows:
        items.append(ValidationItem("CSV rows", "WARN", "CSV has a header but no data rows yet."))
    else:
        items.append(ValidationItem("CSV rows", "PASS", f"Detected {len(rows)} data row(s)."))

    normalized_present = {normalize_col(c) for c in fieldnames}
    missing_recommended = [c for c in RECOMMENDED_COLUMNS if normalize_col(c) not in normalized_present]
    if missing_recommended:
        items.append(
            ValidationItem(
                "Recommended schema",
                "WARN",
                "Missing recommended column(s): " + ", ".join(missing_recommended),
            )
        )
    else:
        items.append(ValidationItem("Recommended schema", "PASS", "All recommended columns are present."))

    resolved = resolve_columns(fieldnames)
    for critical in ["timestamp_utc", "symbol", "signal", "reason"]:
        if critical in resolved:
            items.append(ValidationItem(f"Column mapping: {critical}", "PASS", f"Mapped to `{resolved[critical]}`."))
        else:
            severity = "WARN" if critical in {"signal", "reason"} else "FAIL"
            items.append(ValidationItem(f"Column mapping: {critical}", severity, "No suitable column found."))

    strategy_id_expected = strategy.get("strategy_id")
    if strategy_id_expected and "strategy_id" in resolved and rows:
        bad = [r for r in rows if str(r.get(resolved["strategy_id"], "")).strip() not in {"", strategy_id_expected}]
        if bad:
            items.append(ValidationItem("Strategy ID consistency", "FAIL", f"{len(bad)} row(s) do not match {strategy_id_expected}."))
        else:
            items.append(ValidationItem("Strategy ID consistency", "PASS", f"Rows match {strategy_id_expected} or are blank."))
    elif strategy_id_expected:
        items.append(ValidationItem("Strategy ID consistency", "WARN", "Strategy column unavailable; cannot verify strategy ID."))

    if "timestamp_utc" in resolved and rows:
        bad_times = []
        parsed_times = []
        for idx, row in enumerate(rows, start=2):
            dt = parse_dt(row.get(resolved["timestamp_utc"], ""))
            if dt is None:
                bad_times.append(idx)
            else:
                parsed_times.append(dt)
        if bad_times:
            items.append(ValidationItem("Timestamp parse", "FAIL", f"Unparseable timestamp at CSV line(s): {bad_times[:10]}."))
        else:
            items.append(ValidationItem("Timestamp parse", "PASS", "All timestamps parsed as UTC-compatible values."))
        if parsed_times and parsed_times != sorted(parsed_times):
            items.append(ValidationItem("Timestamp order", "WARN", "Rows are not sorted by timestamp."))
        elif parsed_times:
            items.append(ValidationItem("Timestamp order", "PASS", "Rows are sorted by timestamp."))

    if "closed_h1_time_utc" in resolved and rows:
        bad_h1 = []
        for idx, row in enumerate(rows, start=2):
            dt = parse_dt(row.get(resolved["closed_h1_time_utc"], ""))
            if dt is None or dt.minute != 0:
                bad_h1.append(idx)
        if bad_h1:
            items.append(ValidationItem("Closed H1 time alignment", "WARN", f"Non-H1-aligned or unparseable row(s): {bad_h1[:10]}."))
        else:
            items.append(ValidationItem("Closed H1 time alignment", "PASS", "Closed H1 times align to minute 00."))

    if {"close", "sma10", "distance_usd"}.issubset(resolved) and rows:
        bad_distance = []
        for idx, row in enumerate(rows, start=2):
            close = parse_float(row.get(resolved["close"]))
            sma = parse_float(row.get(resolved["sma10"]))
            dist = parse_float(row.get(resolved["distance_usd"]))
            if close is None or sma is None or dist is None:
                bad_distance.append(idx)
                continue
            if abs((close - sma) - dist) > 0.05:
                bad_distance.append(idx)
        if bad_distance:
            items.append(ValidationItem("Distance arithmetic", "WARN", f"close - sma10 differs from distance_usd at row(s): {bad_distance[:10]}."))
        else:
            items.append(ValidationItem("Distance arithmetic", "PASS", "distance_usd matches close - sma10 within tolerance."))

    if "session_name" in resolved and "session_allowed" in resolved and rows:
        london_allowed = []
        for idx, row in enumerate(rows, start=2):
            session = str(row.get(resolved["session_name"], "")).strip().lower()
            allowed = parse_bool(row.get(resolved["session_allowed"]))
            if session == "london" and allowed is True:
                london_allowed.append(idx)
        if london_allowed:
            items.append(ValidationItem("No-London filter", "FAIL", f"London marked allowed at row(s): {london_allowed[:10]}."))
        else:
            items.append(ValidationItem("No-London filter", "PASS", "No row marks London as allowed."))
    else:
        items.append(ValidationItem("No-London filter", "WARN", "Session columns unavailable; cannot verify London blocking."))

    signal_count = 0
    blocked_count = 0
    no_signal_count = 0
    if rows:
        for row in rows:
            reason_text = " ".join(str(v) for v in row.values()).lower()
            if "signal" in resolved:
                signal_val = parse_bool(row.get(resolved["signal"]))
                if signal_val is True:
                    signal_count += 1
            elif "dry-run signal" in reason_text or "dry run signal" in reason_text:
                signal_count += 1
            if "blocked" in reason_text or "london" in reason_text and "skip" in reason_text:
                blocked_count += 1
            if "no signal" in reason_text:
                no_signal_count += 1

    stats = {
        "csv_path": str(csv_path),
        "row_count": len(rows),
        "columns": fieldnames,
        "resolved_columns": resolved,
        "signal_count": signal_count,
        "blocked_or_skip_count": blocked_count,
        "no_signal_count": no_signal_count,
    }
    return items, rows, stats


def summarize(items: Iterable[ValidationItem]) -> str:
    statuses = [item.status for item in items]
    if "FAIL" in statuses:
        return "FAIL"
    if "WARN" in statuses:
        return "WARN"
    return "PASS"


def write_reports(items: list[ValidationItem], stats: dict[str, Any], report_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    overall = summarize(items)
    payload = {
        "generated_at_utc": now,
        "stage": "5B",
        "tool": "stage5b_dryrun_log_validator",
        "overall_status": overall,
        "stats": stats,
        "items": [asdict(item) for item in items],
        "hard_rule": "This validates dry-run logs only. It does not authorize demo, paper, or live orders.",
    }
    json_path = report_dir / "stage5b_dryrun_log_validator.json"
    md_path = report_dir / "stage5b_dryrun_log_validator.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Stage 5B Dry-run Log Validator",
        "",
        f"Generated UTC: `{now}`",
        f"Overall status: **{overall}**",
        "",
        "> Hard rule: this validates dry-run logs only. It does not authorize demo, paper, or live orders.",
        "",
        "## Stats",
        "",
        f"- CSV path: `{stats.get('csv_path', 'n/a')}`",
        f"- Rows: `{stats.get('row_count', 0)}`",
        f"- Signals: `{stats.get('signal_count', 0)}`",
        f"- Blocked/skipped rows: `{stats.get('blocked_or_skip_count', 0)}`",
        f"- No-signal rows: `{stats.get('no_signal_count', 0)}`",
        "",
        "## Checks",
        "",
        "| Status | Check | Detail |",
        "|---|---|---|",
    ]
    for item in items:
        lines.append(f"| {item.status} | {item.name} | {item.detail} |")
    lines.append("")
    if overall == "FAIL":
        lines.append("Decision: **Do not rely on this dry-run log until FAIL items are fixed.**")
    elif overall == "WARN":
        lines.append("Decision: **Log is usable for inspection, but WARN items must be reviewed before evidence collection.**")
    else:
        lines.append("Decision: **Log schema and basic consistency checks passed. Continue dry-run evidence collection only.**")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 5B MT5 dry-run CSV log validator")
    parser.add_argument("--csv", dest="csv_path", help="Explicit path to XAUUSD_DryRun_v1_signals.csv")
    parser.add_argument("--search-root", action="append", default=[], help="Directory to search if --csv is not provided")
    parser.add_argument("--log-name", default=DEFAULT_LOG_NAME, help="CSV filename to search for")
    parser.add_argument("--strategy-json", default=str(DEFAULT_STRATEGY_JSON), help="Locked strategy JSON spec")
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR), help="Output report directory")
    args = parser.parse_args()

    report_dir = Path(args.report_dir).expanduser()
    strategy = load_strategy(Path(args.strategy_json).expanduser())

    if args.csv_path:
        csv_path = Path(args.csv_path).expanduser()
    else:
        roots = [Path(p).expanduser() for p in args.search_root]
        if not roots:
            roots = [
                Path.home() / "Library" / "Application Support",
                Path.home() / ".wine",
                Path.home() / "Downloads",
            ]
        found = find_log_file(roots, args.log_name)
        if found is None:
            print("FAIL: CSV log not found. Pass --csv explicitly after locating MT5 Common Files.")
            print("Tried roots:")
            for root in roots:
                print(f"  - {root}")
            return 1
        csv_path = found

    items, _rows, stats = validate(csv_path, strategy)
    json_path, md_path = write_reports(items, stats, report_dir)
    overall = summarize(items)

    print(f"Stage 5B dry-run log validator: {overall}")
    print(f"CSV: {csv_path}")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {md_path}")
    return 1 if overall == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
