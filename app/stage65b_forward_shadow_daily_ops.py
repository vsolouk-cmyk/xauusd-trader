#!/usr/bin/env python3
"""
Stage65B Forward-Shadow Daily Operation Wrapper

Purpose:
- Preflight Stage64K macro-regime feature dataset and external spot D1 file.
- Enforce daily-operation freshness/as-of safeguards before Stage65 ledger execution.
- Execute the existing Stage65 signal ledger script without adding any order/broker path.
- Write an operational JSON + Markdown report.

This file intentionally does NOT:
- place orders
- connect to broker/MT5
- tune thresholds
- add historical event filtering
- rescue failed signals
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


DATE_COLUMN_CANDIDATES = (
    "date",
    "feature_date",
    "asof_date",
    "utc_date",
    "time",
    "timestamp",
    "utc_time",
    "datetime",
    "Date",
    "Time",
    "Datetime",
    "Timestamp",
)

OHLC_REQUIRED_ANY_CASE = ("open", "high", "low", "close")


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_date_value(value: str) -> Optional[dt.date]:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    # Common CSV values may include Z suffix, timezone offsets, or plain YYYY-MM-DD.
    cleaned = raw.replace("Z", "+00:00")
    if " " in cleaned and "T" not in cleaned:
        cleaned = cleaned.replace(" ", "T", 1)

    # Try ISO datetime/date first.
    try:
        return dt.datetime.fromisoformat(cleaned).date()
    except Exception:
        pass

    # Try common date-only formats.
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return dt.datetime.strptime(raw[:10], fmt).date()
        except Exception:
            continue
    return None


def read_csv_header_and_dates(path: Path, date_columns: Sequence[str]) -> Tuple[List[str], Optional[str], Optional[dt.date], int, int]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    if path.stat().st_size == 0:
        raise ValueError(f"empty file: {path}")

    total_rows = 0
    parsed_dates = 0
    latest: Optional[dt.date] = None
    chosen_col: Optional[str] = None

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample)
        except Exception:
            dialect = csv.excel
        reader = csv.DictReader(f, dialect=dialect)
        header = list(reader.fieldnames or [])
        if not header:
            raise ValueError(f"missing header: {path}")

        # Preserve config order, then fall back to built-in candidates, then first column.
        candidates: List[str] = []
        for col in list(date_columns) + list(DATE_COLUMN_CANDIDATES) + header[:1]:
            if col and col in header and col not in candidates:
                candidates.append(col)

        if not candidates:
            raise ValueError(f"no date-like column available: {path}")

        candidate_latest: Dict[str, dt.date] = {}
        candidate_counts: Dict[str, int] = {}
        for row in reader:
            total_rows += 1
            for col in candidates:
                parsed = parse_date_value(row.get(col, ""))
                if parsed is None:
                    continue
                candidate_counts[col] = candidate_counts.get(col, 0) + 1
                prev = candidate_latest.get(col)
                if prev is None or parsed > prev:
                    candidate_latest[col] = parsed

    if candidate_latest:
        # Choose the column with the most parsed dates, breaking ties by latest date.
        chosen_col = sorted(
            candidate_latest.keys(),
            key=lambda c: (candidate_counts.get(c, 0), candidate_latest[c]),
            reverse=True,
        )[0]
        latest = candidate_latest[chosen_col]
        parsed_dates = candidate_counts.get(chosen_col, 0)

    if latest is None:
        raise ValueError(f"could not parse any valid dates from: {path}")

    return header, chosen_col, latest, total_rows, parsed_dates


def column_exists_case_insensitive(header: Sequence[str], name: str) -> bool:
    lower = {h.lower() for h in header}
    return name.lower() in lower


def calendar_lag_days(latest: dt.date, now_date: dt.date) -> int:
    return (now_date - latest).days


def classify_file(
    *,
    root: Path,
    relative_path: str,
    label: str,
    max_calendar_lag_days: int,
    date_columns: Sequence[str],
    min_rows: int,
    require_ohlc: bool,
) -> Dict[str, Any]:
    path = (root / relative_path).resolve()
    result: Dict[str, Any] = {
        "label": label,
        "path": relative_path,
        "exists": path.exists(),
        "status": "UNKNOWN",
        "failures": [],
    }

    try:
        header, date_col, latest_date, total_rows, parsed_dates = read_csv_header_and_dates(path, date_columns)
        lag = calendar_lag_days(latest_date, utc_now().date())
        result.update({
            "status": "PASS",
            "date_column": date_col,
            "latest_date": latest_date.isoformat(),
            "calendar_lag_days": lag,
            "row_count": total_rows,
            "parsed_date_rows": parsed_dates,
            "columns": header,
        })
        if total_rows < min_rows:
            result["failures"].append(f"row_count_below_min:{total_rows}<{min_rows}")
        if lag < 0:
            result["failures"].append(f"latest_date_in_future:{latest_date.isoformat()}")
        if lag > max_calendar_lag_days:
            result["failures"].append(f"stale:{lag}>{max_calendar_lag_days}_calendar_days")
        if require_ohlc:
            for col in OHLC_REQUIRED_ANY_CASE:
                if not column_exists_case_insensitive(header, col):
                    result["failures"].append(f"missing_ohlc_column:{col}")
        if result["failures"]:
            result["status"] = "FAIL"
        return result
    except Exception as exc:
        result["status"] = "FAIL"
        result["failures"].append(f"{type(exc).__name__}:{exc}")
        return result


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def ensure_out(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)


def run_stage65(root: Path, config: Dict[str, Any], out_dir: Path) -> Dict[str, Any]:
    stage65_script = root / config["stage65_script"]
    stage65_config = root / config["stage65_config"]
    stage65_out = root / config["stage65_out_dir"]

    if not stage65_script.exists():
        return {
            "attempted": False,
            "returncode": None,
            "status": "FAIL",
            "failure": f"missing_stage65_script:{stage65_script}",
        }
    if not stage65_config.exists():
        return {
            "attempted": False,
            "returncode": None,
            "status": "FAIL",
            "failure": f"missing_stage65_config:{stage65_config}",
        }

    cmd = [
        sys.executable,
        str(stage65_script),
        "--root",
        str(root),
        "--config",
        str(stage65_config),
        "--out",
        str(stage65_out),
    ]

    proc = subprocess.run(
        cmd,
        cwd=str(root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=int(config.get("stage65_timeout_seconds", 300)),
    )

    result: Dict[str, Any] = {
        "attempted": True,
        "cmd": cmd,
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
        "status": "PASS" if proc.returncode == 0 else "FAIL",
    }

    summary_path = root / config.get(
        "stage65_summary_path",
        "reports/stage65_forward_shadow_signal_ledger_fastlane/stage65_forward_shadow_signal_ledger_summary.json",
    )
    if summary_path.exists():
        try:
            result["stage65_summary_path"] = str(summary_path.relative_to(root))
            result["stage65_summary"] = load_json(summary_path)
        except Exception as exc:
            result["stage65_summary_read_error"] = f"{type(exc).__name__}:{exc}"
    else:
        result["stage65_summary_missing"] = str(summary_path.relative_to(root))

    return result


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_markdown(path: Path, summary: Dict[str, Any]) -> None:
    preflight = summary.get("preflight", {})
    stage65 = summary.get("stage65_run", {})
    lines: List[str] = []
    lines.append("# Stage65B Forward-Shadow Daily Operation Report")
    lines.append("")
    lines.append(f"- generated_utc: `{summary.get('generated_utc')}`")
    lines.append(f"- status: `{summary.get('status')}`")
    lines.append(f"- decision: `{summary.get('decision')}`")
    lines.append(f"- root: `{summary.get('root')}`")
    lines.append("")
    lines.append("## Governance")
    for block in summary.get("hard_blocks", []):
        lines.append(f"- `{block}`")
    lines.append("")
    lines.append("## Preflight")
    for key in ("macro_dataset", "external_d1"):
        item = preflight.get(key, {})
        lines.append(f"### {key}")
        lines.append(f"- status: `{item.get('status')}`")
        lines.append(f"- path: `{item.get('path')}`")
        lines.append(f"- latest_date: `{item.get('latest_date')}`")
        lines.append(f"- calendar_lag_days: `{item.get('calendar_lag_days')}`")
        lines.append(f"- row_count: `{item.get('row_count')}`")
        failures = item.get("failures") or []
        if failures:
            lines.append("- failures:")
            for failure in failures:
                lines.append(f"  - `{failure}`")
        else:
            lines.append("- failures: `none`")
        lines.append("")
    lines.append("## Stage65 execution")
    lines.append(f"- attempted: `{stage65.get('attempted')}`")
    lines.append(f"- status: `{stage65.get('status')}`")
    lines.append(f"- returncode: `{stage65.get('returncode')}`")
    if stage65.get("failure"):
        lines.append(f"- failure: `{stage65.get('failure')}`")
    if stage65.get("stage65_summary_path"):
        lines.append(f"- stage65_summary_path: `{stage65.get('stage65_summary_path')}`")
    if stage65.get("stage65_summary"):
        s = stage65.get("stage65_summary") or {}
        lines.append("")
        lines.append("### Stage65 headline")
        for k in (
            "status",
            "decision",
            "latest_feature_date",
            "signal_active",
            "benchmark_active",
            "signal_row_appended",
            "observation_row_appended",
            "observations_matured_this_run",
            "signal_ledger_rows",
            "observation_ledger_rows",
            "forward_governance_ready",
        ):
            if k in s:
                lines.append(f"- {k}: `{s.get(k)}`")
    if stage65.get("stderr_tail"):
        lines.append("")
        lines.append("## stderr tail")
        lines.append("```")
        lines.append(str(stage65.get("stderr_tail"))[-4000:])
        lines.append("```")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Stage65B daily forward-shadow operation wrapper")
    parser.add_argument("--root", default=".", help="repo root")
    parser.add_argument("--config", default="configs/stage65b_forward_shadow_daily_ops.json")
    parser.add_argument("--out", default="reports/stage65b_forward_shadow_daily_ops")
    parser.add_argument("--preflight-only", action="store_true", help="do not run Stage65; only validate inputs")
    parser.add_argument("--allow-stale-run", action="store_true", help="run Stage65 even when freshness preflight fails; still reports FAIL_PRECHECK")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    config_path = (root / args.config).resolve()
    out_dir = (root / args.out).resolve()
    ensure_out(out_dir)

    config = load_json(config_path)
    now = utc_now()

    hard_blocks = [
        "NO_PAPER_ORDER",
        "NO_EA_PROMOTION",
        "NO_PAPER_LIVE",
        "NO_LIVE",
        "NO_BROKER_CONNECTION",
        "NO_ORDER_AUTHORIZATION_FROM_STAGE65",
        "NO_HISTORICAL_EVENT_FILTER_FROM_FORWARD_ONLY_GOVERNANCE",
        "NO_POST_HOC_EVENT_EXCLUSION",
        "NO_REDUCED_SCOPE_RETEST",
        "NO_RESCUE_FILTERING",
        "NO_NEW_INTRADAY_SCAN",
        "NO_THRESHOLD_TUNING",
        "NO_COMMERCIALIZATION_WITHOUT_LATER_FORWARD_AND_BROKER_GOVERNANCE",
    ]

    macro = classify_file(
        root=root,
        relative_path=config["macro_dataset_path"],
        label="Stage64K lag-safe feature dataset",
        max_calendar_lag_days=int(config.get("macro_max_calendar_lag_days", 14)),
        date_columns=config.get("macro_date_columns", []),
        min_rows=int(config.get("macro_min_rows", 1000)),
        require_ohlc=False,
    )
    external = classify_file(
        root=root,
        relative_path=config["external_d1_path"],
        label="External spot D1 OHLC reference",
        max_calendar_lag_days=int(config.get("external_d1_max_calendar_lag_days", 7)),
        date_columns=config.get("external_d1_date_columns", []),
        min_rows=int(config.get("external_d1_min_rows", 1000)),
        require_ohlc=True,
    )

    preflight_ok = macro["status"] == "PASS" and external["status"] == "PASS"

    summary: Dict[str, Any] = {
        "generated_utc": now.isoformat(),
        "root": str(root),
        "config": str(config_path),
        "hard_blocks": hard_blocks,
        "preflight": {
            "macro_dataset": macro,
            "external_d1": external,
            "preflight_ok": preflight_ok,
        },
        "status": "PREFLIGHT_PASS" if preflight_ok else "PREFLIGHT_FAIL",
        "decision": "RUN_STAGE65_ALLOWED_NO_ORDER" if preflight_ok else "STOP_REFRESH_DATA_FIRST_NO_ORDER",
        "stage65_run": {
            "attempted": False,
            "status": "SKIPPED",
            "reason": "preflight_only_or_preflight_failed",
        },
    }

    should_run = (preflight_ok or args.allow_stale_run) and not args.preflight_only
    if should_run:
        stage65_run = run_stage65(root, config, out_dir)
        summary["stage65_run"] = stage65_run
        if stage65_run.get("status") == "PASS" and preflight_ok:
            summary["status"] = "STAGE65B_DAILY_OPERATION_COMPLETE_NO_PROMOTION"
            summary["decision"] = "STAGE65_FORWARD_LEDGER_ACTIVE_CONTINUE_DAILY_NO_ORDER"
        elif stage65_run.get("status") == "PASS":
            summary["status"] = "STAGE65B_RAN_WITH_STALE_PREFLIGHT_NO_PROMOTION"
            summary["decision"] = "DATA_REFRESH_REQUIRED_REVIEW_OUTPUT_NO_ORDER"
        else:
            summary["status"] = "STAGE65B_STAGE65_EXECUTION_FAIL_NO_ORDER"
            summary["decision"] = "FIX_STAGE65_EXECUTION_OR_INPUTS_NO_ORDER"

    write_json(out_dir / "stage65b_forward_shadow_daily_ops_summary.json", summary)
    write_markdown(out_dir / "stage65b_forward_shadow_daily_ops_report.md", summary)

    if summary["status"] in {"STAGE65B_DAILY_OPERATION_COMPLETE_NO_PROMOTION", "PREFLIGHT_PASS"}:
        return 0
    if args.preflight_only and preflight_ok:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
