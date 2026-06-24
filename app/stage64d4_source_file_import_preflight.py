#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from typing import Any, Optional

DEFAULT_TARGETS = [
    {
        "manifest_id": "SRC_GOLD_D1_OHLC_2011_PRESENT",
        "priority": "P0_CRITICAL",
        "target_file": "data/macro_regime/raw/gold_d1_ohlc_2011_present.csv",
        "required_columns": ["date_utc", "open", "high", "low", "close", "volume", "source", "available_after_utc"],
        "time_column": "date_utc",
        "primary_key": ["date_utc", "source"],
        "min_start_date": "2011-01-01",
        "start_grace_days": 7,
        "source_policy": "GOLD_SPOT_OR_REFERENCE_ALLOWED",
    },
    {
        "manifest_id": "SRC_DXY_D1_2011_PRESENT",
        "priority": "P0_CRITICAL",
        "target_file": "data/macro_regime/raw/dxy_daily_2011_present.csv",
        "required_columns": ["date_utc", "close", "source", "available_after_utc"],
        "time_column": "date_utc",
        "primary_key": ["date_utc", "source"],
        "min_start_date": "2011-01-01",
        "start_grace_days": 7,
        "source_policy": "EXACT_DXY_REQUIRED_UNLESS_CONFIG_ACCEPTS_USD_PROXY",
    },
    {
        "manifest_id": "SRC_REAL_YIELD_OR_PROXY_2011_PRESENT",
        "priority": "P0_CRITICAL",
        "target_file": "data/macro_regime/raw/real_yield_or_proxy_daily_2011_present.csv",
        "required_columns": ["date_utc", "value", "source", "available_after_utc", "proxy_method"],
        "time_column": "date_utc",
        "primary_key": ["date_utc", "source", "proxy_method"],
        "min_start_date": "2011-01-01",
        "start_grace_days": 7,
        "source_policy": "REAL_YIELD_OR_APPROVED_PROXY",
    },
    {
        "manifest_id": "SRC_VIX_OR_VOL_PROXY_2011_PRESENT",
        "priority": "P1_HIGH",
        "target_file": "data/macro_regime/raw/vix_daily_2011_present.csv",
        "required_columns": ["date_utc", "close", "source", "available_after_utc"],
        "time_column": "date_utc",
        "primary_key": ["date_utc", "source"],
        "min_start_date": "2011-01-01",
        "start_grace_days": 7,
        "source_policy": "VIX_OR_APPROVED_VOL_PROXY",
    },
    {
        "manifest_id": "SRC_GOLD_ETF_HOLDINGS_FLOWS",
        "priority": "P1_HIGH",
        "target_file": "data/macro_regime/raw/gold_etf_holdings_or_flows.csv",
        "required_columns": ["date_utc", "etf_id", "holdings_tonnes_or_flow", "source", "release_time_utc", "available_after_utc"],
        "time_column": "date_utc",
        "primary_key": ["date_utc", "etf_id", "source"],
        "min_start_date": "2011-01-01",
        "start_grace_days": 7,
        "source_policy": "ETF_FLOW_OR_HOLDINGS_RELEASE_LAG_REQUIRED",
    },
    {
        "manifest_id": "SRC_CENTRAL_BANK_GOLD_DEMAND",
        "priority": "P1_HIGH",
        "target_file": "data/macro_regime/raw/central_bank_gold_demand_monthly_quarterly.csv",
        "required_columns": ["period_start", "period_end", "demand_value", "unit", "source", "release_date_utc", "available_after_utc"],
        "time_column": "period_start",
        "primary_key": ["period_start", "period_end", "source"],
        "min_start_date": "2011-01-01",
        "start_grace_days": 31,
        "source_policy": "CENTRAL_BANK_DEMAND_RELEASE_LAG_REQUIRED_SLOW_PRIOR_ONLY",
    },
    {
        "manifest_id": "SRC_MACRO_EVENT_CALENDAR_ARCHIVE",
        "priority": "P2_MEDIUM",
        "target_file": "data/macro_regime/raw/macro_event_calendar_archive.csv",
        "required_columns": ["scheduled_time_utc", "event_type", "importance", "country", "known_before_event", "source", "available_after_utc"],
        "time_column": "scheduled_time_utc",
        "primary_key": ["scheduled_time_utc", "event_type", "country", "source"],
        "min_start_date": "2011-01-01",
        "start_grace_days": 31,
        "source_policy": "KNOWN_BEFORE_EVENT_ONLY",
    },
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--config", default="configs/stage64d4_source_file_import_preflight.json")
    p.add_argument("--out", default="reports/stage64d4_source_file_import_preflight")
    return p.parse_args()


def load_config(root: Path, config_path: str) -> dict[str, Any]:
    p = root / config_path
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def parse_date_any(v: str) -> Optional[dt.datetime]:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(dt.timezone.utc)
        if "T" in s:
            x = dt.datetime.fromisoformat(s)
            if x.tzinfo is None:
                x = x.replace(tzinfo=dt.timezone.utc)
            return x.astimezone(dt.timezone.utc)
        return dt.datetime.combine(dt.date.fromisoformat(s[:10]), dt.time(0, 0), tzinfo=dt.timezone.utc)
    except Exception:
        return None


def row_key(row: dict[str, str], fields: list[str]) -> tuple[str, ...]:
    return tuple((row.get(f) or "").strip() for f in fields)


def evaluate_source_policy(target: dict[str, Any], rows: list[dict[str, str]], config: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    if not rows:
        return False, [], []
    policy = target.get("source_policy", "")
    sources = sorted({(r.get("source") or "").strip() for r in rows if (r.get("source") or "").strip()})
    source_blob = "|".join(sources).upper()
    warnings: list[str] = []
    issues: list[str] = []

    if policy == "EXACT_DXY_REQUIRED_UNLESS_CONFIG_ACCEPTS_USD_PROXY":
        if "PROXY_NOT_DXY" in source_blob or "DTWEXBGS" in source_blob:
            if config.get("allow_usd_proxy_for_dxy_preflight", False):
                warnings.append("DXY target uses broad USD proxy accepted by config; validation must record reduced-source scope")
                return True, issues, warnings
            issues.append("DXY target uses broad USD proxy, not exact DXY; set allow_usd_proxy_for_dxy_preflight=true only after explicit scope approval")
            return False, issues, warnings
    return True, issues, warnings


def check_file(root: Path, target: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    path = root / target["target_file"]
    required = target["required_columns"]
    result: dict[str, Any] = {
        "manifest_id": target["manifest_id"],
        "priority": target["priority"],
        "target_file": target["target_file"],
        "found": path.exists(),
        "required_columns": required,
        "missing_columns": [],
        "row_count": 0,
        "first_time_utc": None,
        "last_time_utc": None,
        "duplicate_key_count": 0,
        "available_after_missing_count": None,
        "available_after_parse_error_count": None,
        "start_coverage_ok": False,
        "schema_ok": False,
        "source_policy_ok": False,
        "preflight_ok": False,
        "issues": [],
        "warnings": [],
    }
    if not path.exists():
        result["issues"].append("file missing")
        return result

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            columns = reader.fieldnames or []
            missing = [c for c in required if c not in columns]
            result["missing_columns"] = missing
            result["schema_ok"] = not missing
            rows = list(reader)
    except Exception as e:
        result["issues"].append(f"csv read error: {e}")
        return result

    result["row_count"] = len(rows)
    if not rows:
        result["issues"].append("no data rows")

    time_col = target["time_column"]
    times = []
    for r in rows:
        t = parse_date_any(r.get(time_col, ""))
        if t:
            times.append(t)
    if times:
        first = min(times)
        last = max(times)
        result["first_time_utc"] = first.isoformat().replace("+00:00", "Z")
        result["last_time_utc"] = last.isoformat().replace("+00:00", "Z")
        min_start = dt.datetime.combine(dt.date.fromisoformat(target.get("min_start_date", "2011-01-01")), dt.time(0, 0), tzinfo=dt.timezone.utc)
        grace_days = int(target.get("start_grace_days", config.get("default_start_grace_days", 7)))
        if first <= min_start:
            result["start_coverage_ok"] = True
        elif first <= min_start + dt.timedelta(days=grace_days):
            result["start_coverage_ok"] = True
            result["warnings"].append(f"coverage starts after calendar minimum but within grace window: first={first.date()} min={min_start.date()} grace_days={grace_days}")
        else:
            result["issues"].append(f"coverage starts after required minimum plus grace: first={first.date()} min={min_start.date()} grace_days={grace_days}")
    else:
        result["issues"].append("no parseable time column values")

    if rows and target.get("primary_key"):
        seen = set()
        dup = 0
        for r in rows:
            k = row_key(r, target["primary_key"])
            if k in seen:
                dup += 1
            else:
                seen.add(k)
        result["duplicate_key_count"] = dup
        if dup:
            result["issues"].append(f"duplicate primary key rows: {dup}")

    if "available_after_utc" in required:
        missing_av = 0
        parse_err = 0
        for r in rows:
            v = (r.get("available_after_utc") or "").strip()
            if not v:
                missing_av += 1
            elif parse_date_any(v) is None:
                parse_err += 1
        result["available_after_missing_count"] = missing_av
        result["available_after_parse_error_count"] = parse_err
        if missing_av:
            result["issues"].append(f"available_after_utc missing rows: {missing_av}")
        if parse_err:
            result["issues"].append(f"available_after_utc parse error rows: {parse_err}")

    source_policy_ok, source_issues, source_warnings = evaluate_source_policy(target, rows, config)
    result["source_policy_ok"] = source_policy_ok
    result["issues"].extend(source_issues)
    result["warnings"].extend(source_warnings)

    result["preflight_ok"] = bool(
        result["found"]
        and result["schema_ok"]
        and result["row_count"] > 0
        and result["start_coverage_ok"]
        and result["duplicate_key_count"] == 0
        and (result["available_after_missing_count"] in (None, 0))
        and (result["available_after_parse_error_count"] in (None, 0))
        and result["source_policy_ok"]
        and not result["issues"]
    )
    return result


def write_outputs(out_dir: Path, checks: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "stage64d4_source_file_import_preflight_checks.csv"
    fields = [
        "manifest_id", "priority", "target_file", "found", "row_count", "first_time_utc", "last_time_utc",
        "schema_ok", "source_policy_ok", "start_coverage_ok", "duplicate_key_count",
        "available_after_missing_count", "available_after_parse_error_count", "preflight_ok", "issues", "warnings",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for c in checks:
            row = dict(c)
            row["issues"] = "; ".join(c.get("issues") or [])
            row["warnings"] = "; ".join(c.get("warnings") or [])
            w.writerow({k: row.get(k, "") for k in fields})

    with (out_dir / "stage64d4_source_file_import_preflight_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    with (out_dir / "stage64d4_source_file_import_preflight_report.md").open("w", encoding="utf-8") as f:
        f.write("# Stage64D4 Source File Import Preflight - LoaderFix1\n\n")
        f.write(f"Generated UTC: `{summary['generated_utc']}`\n\n")
        f.write(f"Status: `{summary['status']}`\n")
        f.write(f"Decision: `{summary['decision']}`\n\n")
        f.write("No validation or order path is authorized by this preflight.\n\n")
        f.write("## Counts\n\n")
        for k, v in summary["counts"].items():
            f.write(f"- {k}: {v}\n")
        f.write("\n## Failed or missing files\n\n")
        failed = [c for c in checks if not c.get("preflight_ok")]
        if failed:
            for c in failed:
                issue_text = "; ".join(c.get("issues") or []) or "failed without issue text"
                f.write(f"- `{c['target_file']}`: {issue_text}\n")
        else:
            f.write("- none\n")
        f.write("\n## Warnings\n\n")
        warned = [c for c in checks if c.get("warnings")]
        if warned:
            for c in warned:
                f.write(f"- `{c['target_file']}`: {'; '.join(c.get('warnings') or [])}\n")
        else:
            f.write("- none\n")
        f.write("\n## Next\n\n")
        if summary["p0_ready_for_stage64d_rerun"]:
            f.write("P0 raw files passed preflight. Rerun Stage64D to reassess data-contract readiness. Validation remains blocked until Stage64D explicitly unlocks the selected scope.\n")
        else:
            f.write("P0 raw files did not pass preflight. Fix P0 raw files before rerunning Stage64D. Validation remains blocked.\n")


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    config = load_config(root, args.config)
    targets = config.get("targets") or DEFAULT_TARGETS
    out_dir = root / args.out

    checks = [check_file(root, target, config) for target in targets]
    p0 = [c for c in checks if c.get("priority") == "P0_CRITICAL"]
    p0_ok = sum(1 for c in p0 if c.get("preflight_ok"))
    ok = sum(1 for c in checks if c.get("preflight_ok"))
    found = sum(1 for c in checks if c.get("found"))

    p0_ready = p0_ok == len(p0) and len(p0) > 0
    all_ready = ok == len(checks) and len(checks) > 0
    decision = "P0_RAW_FILES_PASS_PREFLIGHT_RERUN_STAGE64D_NO_ORDER" if p0_ready else "BLOCK_STAGE64D_RERUN_UNTIL_P0_RAW_FILES_PASS_PREFLIGHT_NO_ORDER"

    summary = {
        "stage": "Stage64D4_SOURCE_FILE_IMPORT_PREFLIGHT_NO_PROMOTION_LOADERFIX1",
        "status": "SOURCE_FILE_IMPORT_PREFLIGHT_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_order": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "validation_allowed": False,
        "generated_utc": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "root": str(root),
        "counts": {
            "targets": len(checks),
            "found": found,
            "preflight_ok": ok,
            "p0_required": len(p0),
            "p0_preflight_ok": p0_ok,
        },
        "p0_ready_for_stage64d_rerun": p0_ready,
        "all_raw_files_preflight_ok": all_ready,
        "hard_blocks": [
            "NO_PAPER_ORDER",
            "NO_EA_PROMOTION",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_HISTORICAL_VALIDATION_SCAN",
        ],
        "outputs": {
            "checks_csv": str(out_dir / "stage64d4_source_file_import_preflight_checks.csv"),
            "summary_json": str(out_dir / "stage64d4_source_file_import_preflight_summary.json"),
            "report_md": str(out_dir / "stage64d4_source_file_import_preflight_report.md"),
        },
        "checks": checks,
    }
    write_outputs(out_dir, checks, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
