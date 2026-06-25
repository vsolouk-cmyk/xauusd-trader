#!/usr/bin/env python3
"""Stage66 data integrity crosscheck.

Purpose: cheap, fast guard before Stage66A/B so both tracks do not agree on a
shared hidden data/lag bug. This is not an order or broker path.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List

from stage66_common_h64l import (
    build_external_index,
    first_index_on_or_after,
    load_locked_rule,
    parse_date,
    parse_datetime,
    parse_float,
    read_csv,
    read_json,
    write_json,
    write_report,
)


def latest_date(rows: List[Dict[str, str]], col: str):
    ds = [parse_date(r.get(col)) for r in rows]
    ds = [d for d in ds if d is not None]
    return max(ds) if ds else None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--config", default="configs/stage66_data_integrity_crosscheck.json")
    p.add_argument("--out", default="reports/stage66_data_integrity_crosscheck")
    args = p.parse_args()

    root = Path(args.root).resolve()
    cfg = read_json(root / args.config)
    out_dir = Path(args.out) if Path(args.out).is_absolute() else root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    hard_blocks = [
        "NO_PAPER_ORDER", "NO_EA_PROMOTION", "NO_PAPER_LIVE", "NO_LIVE", "NO_BROKER_CONNECTION",
        "NO_ORDER_AUTHORIZATION_FROM_STAGE66", "NO_THRESHOLD_TUNING"
    ]
    issues: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    macro_path = root / cfg["macro_dataset_path"]
    external_path = root / cfg["external_d1_path"]
    rule_path = root / cfg["locked_rule_path"]

    input_status: Dict[str, Any] = {}
    try:
        rule = load_locked_rule(rule_path)
        input_status["locked_rule_hash_ok"] = True
        input_status["locked_rule_sha256"] = rule.get("rule_sha256")
    except Exception as e:
        issues.append({"scope": "locked_rule", "issue": str(e)})
        rule = None

    if not macro_path.exists():
        issues.append({"scope": "macro_dataset", "issue": "missing", "path": str(macro_path)})
        macro_rows, macro_fields = [], []
    else:
        macro_rows, macro_fields = read_csv(macro_path)

    if not external_path.exists():
        issues.append({"scope": "external_d1", "issue": "missing", "path": str(external_path)})
        external_rows, external_fields = [], []
    else:
        external_rows, external_fields = read_csv(external_path)

    today = dt.datetime.now(dt.timezone.utc).date()
    macro_latest = latest_date(macro_rows, "feature_date_utc") if macro_rows else None
    external_latest = latest_date(external_rows, "date_utc") if external_rows else None
    if macro_latest:
        macro_lag = (today - macro_latest).days
        if macro_lag > int(cfg.get("max_allowed_macro_calendar_lag_days", 5)):
            issues.append({"scope": "macro_dataset", "issue": "stale", "latest_date": macro_latest.isoformat(), "calendar_lag_days": macro_lag})
    else:
        macro_lag = None
        issues.append({"scope": "macro_dataset", "issue": "no_parseable_feature_date"})
    if external_latest:
        external_lag = (today - external_latest).days
        if external_lag > int(cfg.get("max_allowed_external_calendar_lag_days", 3)):
            issues.append({"scope": "external_d1", "issue": "stale", "latest_date": external_latest.isoformat(), "calendar_lag_days": external_lag})
    else:
        external_lag = None
        issues.append({"scope": "external_d1", "issue": "no_parseable_date"})

    # As-of lag hard check on all macro rows.
    lag_breaches: List[Dict[str, Any]] = []
    for i, r in enumerate(macro_rows):
        fd = parse_date(r.get("feature_date_utc"))
        avail = parse_datetime(r.get("sample_available_after_utc"))
        if fd is None or avail is None:
            lag_breaches.append({"row_index": i, "issue": "missing_feature_date_or_available_after"})
            continue
        # available_after may be same day or next day, but must not predate feature date unrealistically.
        if avail.date() < fd:
            lag_breaches.append({"row_index": i, "feature_date_utc": fd.isoformat(), "sample_available_after_utc": avail.isoformat(), "issue": "available_before_feature_date"})
    if lag_breaches:
        issues.append({"scope": "asof_lag", "issue": "breaches", "count": len(lag_breaches), "examples": lag_breaches[:10]})

    # Cross-source gold close sample check: Stage64K gold_close vs external D1 close.
    sample_results: List[Dict[str, Any]] = []
    if macro_rows and external_rows:
        macro_by_date = {parse_date(r.get("feature_date_utc")): r for r in macro_rows if parse_date(r.get("feature_date_utc")) is not None}
        ext_series = build_external_index(external_rows, "date_utc", "close")
        for ds in cfg.get("sample_dates", []):
            d = parse_date(ds)
            if d is None:
                continue
            mr = macro_by_date.get(d)
            ei = first_index_on_or_after(ext_series, d)
            if mr is None or ei is None:
                sample_results.append({"date": ds, "status": "SKIPPED_MISSING_IN_ONE_SOURCE"})
                continue
            g = parse_float(mr.get("gold_close"))
            ec = ext_series[ei][1]
            if g is None or ec is None or ec == 0:
                sample_results.append({"date": ds, "status": "SKIPPED_UNPARSEABLE_CLOSE"})
                continue
            diff_pct = abs(g / ec - 1.0) * 100.0
            status = "PASS"
            if diff_pct > float(cfg.get("gold_close_max_abs_pct_diff_fail", 3.0)):
                status = "FAIL"
                issues.append({"scope": "cross_source_gold_close", "date": ds, "diff_pct": diff_pct, "issue": "exceeds_fail_tolerance"})
            elif diff_pct > float(cfg.get("gold_close_max_abs_pct_diff_warn", 1.0)):
                status = "WARN"
                warnings.append({"scope": "cross_source_gold_close", "date": ds, "diff_pct": diff_pct, "issue": "exceeds_warn_tolerance"})
            sample_results.append({"date": ds, "macro_gold_close": g, "external_close": ec, "abs_diff_pct": diff_pct, "status": status})

    manual_csv = root / cfg.get("optional_manual_independent_points_csv", "")
    manual_points_status = "NOT_SUPPLIED_OPTIONAL"
    if manual_csv.exists():
        manual_rows, manual_fields = read_csv(manual_csv)
        manual_points_status = "SUPPLIED_TEMPLATE_ONLY_OR_MANUAL_POINTS"
        # Template-aware: validate rows that have expected_value filled.
        checked = 0
        for i, r in enumerate(manual_rows):
            expected = parse_float(r.get("expected_value"))
            actual_col = r.get("stage64k_column", "")
            d = parse_date(r.get("date_utc"))
            tolerance_pct = parse_float(r.get("tolerance_pct")) or 1.0
            if expected is None or not actual_col or d is None:
                continue
            mr = {parse_date(x.get("feature_date_utc")): x for x in macro_rows if parse_date(x.get("feature_date_utc")) is not None}.get(d)
            if not mr:
                issues.append({"scope": "manual_independent_point", "row": i, "issue": "date_not_found_in_macro"})
                continue
            actual = parse_float(mr.get(actual_col))
            if actual is None:
                issues.append({"scope": "manual_independent_point", "row": i, "issue": "actual_unparseable", "column": actual_col})
                continue
            checked += 1
            diff_pct = abs(actual / expected - 1.0) * 100.0 if expected != 0 else abs(actual - expected)
            if diff_pct > tolerance_pct:
                issues.append({"scope": "manual_independent_point", "row": i, "issue": "outside_tolerance", "diff_pct": diff_pct})
        if checked == 0:
            manual_points_status = "SUPPLIED_BUT_NO_CHECKABLE_ROWS"
    elif cfg.get("manual_points_required", False):
        issues.append({"scope": "manual_independent_points", "issue": "required_but_missing", "path": str(manual_csv)})

    if issues:
        status = "FAIL"
        decision = "STOP_STAGE66_PACKAGE1_FIX_DATA_FIRST"
    elif warnings:
        status = "PASS_WITH_WARNINGS"
        decision = "RUN_STAGE66A_B_ALLOWED_WARNINGS_VISIBLE"
    else:
        status = "PASS"
        decision = "RUN_STAGE66A_B_ALLOWED"

    summary = {
        "stage": "Stage66_DATA_INTEGRITY_CROSSCHECK",
        "generated_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": status,
        "decision": decision,
        "root": str(root),
        "hard_blocks": hard_blocks,
        "inputs": {
            "macro_dataset_path": cfg["macro_dataset_path"],
            "external_d1_path": cfg["external_d1_path"],
            "locked_rule_path": cfg["locked_rule_path"],
            "macro_rows": len(macro_rows),
            "external_rows": len(external_rows),
            "macro_latest_date": macro_latest.isoformat() if macro_latest else None,
            "external_latest_date": external_latest.isoformat() if external_latest else None,
            "macro_calendar_lag_days": macro_lag,
            "external_calendar_lag_days": external_lag,
            **input_status,
        },
        "sample_cross_source_gold_close": sample_results,
        "manual_points_status": manual_points_status,
        "issues": issues,
        "warnings": warnings,
    }

    write_json(out_dir / "stage66_data_integrity_crosscheck_summary.json", summary)
    sections = [
        ("Decision", f"- status: `{status}`\n- decision: `{decision}`"),
        ("Inputs", json.dumps(summary["inputs"], ensure_ascii=False, indent=2)),
        ("Issues", json.dumps(issues, ensure_ascii=False, indent=2) if issues else "none"),
        ("Warnings", json.dumps(warnings, ensure_ascii=False, indent=2) if warnings else "none"),
        ("Sample cross-source checks", json.dumps(sample_results, ensure_ascii=False, indent=2)),
    ]
    write_report(out_dir / "stage66_data_integrity_crosscheck_report.md", "Stage66 Data Integrity Crosscheck", sections)
    return 0 if status in {"PASS", "PASS_WITH_WARNINGS"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
