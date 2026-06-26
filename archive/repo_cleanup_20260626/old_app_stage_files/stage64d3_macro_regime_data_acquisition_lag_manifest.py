#!/usr/bin/env python3
"""Stage64D3 - Macro-regime source acquisition and lag manifest.

This stage is governance / manifest only. It does not download data, mutate trading
state, run validation, generate orders, or authorize promotion.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

STAGE = "Stage64D3_MACRO_REGIME_DATA_ACQUISITION_AND_LAG_MANIFEST_NO_PROMOTION"
STATUS = "DATA_ACQUISITION_LAG_MANIFEST_COMPLETE_NO_PROMOTION"
DECISION = "PREPARE_SOURCE_ACQUISITION_AND_LAG_MANIFEST_VALIDATION_STILL_BLOCKED_NO_ORDER"
NEXT_ALLOWED_STEP = "Stage64D4_SOURCE_FILE_IMPORT_PREFLIGHT_AFTER_FILES_PROVIDED_NO_ORDER"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv(path: Path, rows: Iterable[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def as_list_string(items: Any) -> str:
    if isinstance(items, list):
        return ";".join(str(x) for x in items)
    if items is None:
        return ""
    return str(items)


def load_config(root: Path, config_path: Path) -> Dict[str, Any]:
    config = read_json(config_path)
    if config is None:
        raise SystemExit(f"Could not read config JSON: {config_path}")
    return config


def source_manifest(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    # Keep these rows explicit and predeclared. Do not infer new sources from data after validation.
    return [
        {
            "manifest_id": "SRC_GOLD_D1_OHLC_2011_PRESENT",
            "priority": "P0_CRITICAL",
            "feature_ids": ["gold_d1_trend", "gold_w1_trend", "volatility_regime"],
            "source_family": "gold_ohlcv_reference_or_broker_backfill",
            "target_file": "data/macro_regime/raw/gold_d1_ohlc_2011_present.csv",
            "minimum_start_date": "2011-01-01",
            "minimum_end_policy": "current_or_last_completed_session",
            "required_columns": ["date_utc", "open", "high", "low", "close", "volume", "source", "available_after_utc"],
            "availability_lag_rule_id": "BAR_CLOSE_OR_SESSION_CLOSE_ONLY",
            "acceptance_criteria": "D1 coverage from 2011-01-01 to present; no duplicate date_utc; OHLC numeric; timezone/source documented; W1 derivable from completed D1 bars.",
            "manual_action_required": "Acquire/export long-horizon XAUUSD/gold daily OHLC. If broker history is unavailable before 2022, use one explicitly labeled reference source and keep provenance.",
            "validation_scope_role": "required_for_any_macro_validation",
            "status": "PLANNED_NOT_READY",
        },
        {
            "manifest_id": "SRC_DXY_D1_2011_PRESENT",
            "priority": "P0_CRITICAL",
            "feature_ids": ["dxy_trend_acceleration"],
            "source_family": "external_market_daily",
            "target_file": "data/macro_regime/raw/dxy_daily_2011_present.csv",
            "minimum_start_date": "2011-01-01",
            "minimum_end_policy": "current_or_last_completed_session",
            "required_columns": ["date_utc", "close", "source", "available_after_utc"],
            "availability_lag_rule_id": "SESSION_CLOSE_AVAILABLE_AFTER_UTC_REQUIRED",
            "acceptance_criteria": "Daily DXY history from 2011-01-01; deterministic session-close or explicit available_after_utc; no same-day lookahead for D1 signal construction.",
            "manual_action_required": "Backfill DXY daily history and document whether available_after_utc is exact or deterministic session-close proxy.",
            "validation_scope_role": "required_for_any_macro_validation",
            "status": "PLANNED_NOT_READY",
        },
        {
            "manifest_id": "SRC_REAL_YIELD_OR_PROXY_2011_PRESENT",
            "priority": "P0_CRITICAL",
            "feature_ids": ["real_yield_or_proxy"],
            "source_family": "macro_rate_daily_or_proxy",
            "target_file": "data/macro_regime/raw/real_yield_or_proxy_daily_2011_present.csv",
            "minimum_start_date": "2011-01-01",
            "minimum_end_policy": "current_or_last_available_release",
            "required_columns": ["date_utc", "value", "source", "available_after_utc", "proxy_method"],
            "availability_lag_rule_id": "RELEASE_OR_PROVIDER_AVAILABILITY_TIMESTAMP_REQUIRED",
            "acceptance_criteria": "Real yield or approved proxy coverage from 2011-01-01; proxy method frozen before validation; all components lag-safe.",
            "manual_action_required": "Acquire real yield series or build approved proxy using lag-safe nominal yield and inflation-expectation components.",
            "validation_scope_role": "required_for_any_macro_validation",
            "status": "PLANNED_NOT_READY",
        },
        {
            "manifest_id": "SRC_VIX_OR_VOL_PROXY_2011_PRESENT",
            "priority": "P1_HIGH",
            "feature_ids": ["volatility_regime"],
            "source_family": "external_volatility_or_derived_gold_range",
            "target_file": "data/macro_regime/raw/vix_daily_2011_present.csv",
            "minimum_start_date": "2011-01-01",
            "minimum_end_policy": "current_or_last_completed_session",
            "required_columns": ["date_utc", "close", "source", "available_after_utc"],
            "availability_lag_rule_id": "SESSION_CLOSE_AVAILABLE_AFTER_UTC_REQUIRED",
            "acceptance_criteria": "VIX/proxy history from 2011-01-01 or gold ATR derived from accepted D1 gold OHLC; bins predeclared.",
            "manual_action_required": "Backfill external VIX/proxy or formally derive volatility regime from accepted gold OHLC only.",
            "validation_scope_role": "required_for_full_scope_or_derive_from_gold_ohlc",
            "status": "PLANNED_NOT_READY",
        },
        {
            "manifest_id": "SRC_GOLD_ETF_HOLDINGS_FLOWS",
            "priority": "P1_HIGH",
            "feature_ids": ["etf_flow_divergence"],
            "source_family": "gold_etf_holdings_or_flow",
            "target_file": "data/macro_regime/raw/gold_etf_holdings_or_flows.csv",
            "minimum_start_date": "2011-01-01_preferred_2016_minimum_if_unavailable",
            "minimum_end_policy": "current_or_last_publication",
            "required_columns": ["date_utc", "etf_id", "holdings_tonnes_or_flow", "source", "release_time_utc", "available_after_utc"],
            "availability_lag_rule_id": "NEXT_SESSION_AFTER_PUBLICATION_REQUIRED",
            "acceptance_criteria": "ETF holdings/flows with explicit publication convention; next-session join enforced; if unavailable, formally exclude from reduced-scope validation.",
            "manual_action_required": "Acquire GLD/major gold ETF holdings/flow history with release convention, or document exclusion from first reduced-scope validation.",
            "validation_scope_role": "required_for_full_scope_optional_for_predeclared_reduced_scope",
            "status": "PLANNED_NOT_READY",
        },
        {
            "manifest_id": "SRC_CENTRAL_BANK_GOLD_DEMAND",
            "priority": "P1_HIGH",
            "feature_ids": ["central_bank_demand_regime"],
            "source_family": "official_or_wgc_monthly_quarterly",
            "target_file": "data/macro_regime/raw/central_bank_gold_demand_monthly_quarterly.csv",
            "minimum_start_date": "2011-01-01_preferred",
            "minimum_end_policy": "last_official_release",
            "required_columns": ["period_start", "period_end", "demand_value", "unit", "source", "release_date_utc", "available_after_utc"],
            "availability_lag_rule_id": "OFFICIAL_RELEASE_LAG_REQUIRED_SLOW_PRIOR_ONLY",
            "acceptance_criteria": "Monthly/quarterly demand regime with explicit release lag; used only as slow prior, never as direct timing signal.",
            "manual_action_required": "Acquire official/WGC central-bank demand data or define conservative release-lag manual series; never join as known on period date.",
            "validation_scope_role": "required_for_full_scope_optional_for_predeclared_reduced_scope",
            "status": "PLANNED_NOT_READY",
        },
        {
            "manifest_id": "SRC_MACRO_EVENT_CALENDAR_ARCHIVE",
            "priority": "P2_MEDIUM",
            "feature_ids": ["event_calendar_risk"],
            "source_family": "historical_macro_calendar_or_forward_only",
            "target_file": "data/macro_regime/raw/macro_event_calendar_archive.csv",
            "minimum_start_date": "TBD",
            "minimum_end_policy": "current_or_forward_only",
            "required_columns": ["scheduled_time_utc", "event_type", "importance", "country", "known_before_event", "source", "available_after_utc"],
            "availability_lag_rule_id": "KNOWN_BEFORE_EVENT_ONLY",
            "acceptance_criteria": "Historical scheduled events must be known-before-event; realized surprise excluded from pre-event features. If not available, event filter is forward-only and excluded from historical validation.",
            "manual_action_required": "Acquire historical scheduled macro-event archive or formally restrict event_calendar_risk to forward-only suppression.",
            "validation_scope_role": "optional_forward_risk_filter_unless_historical_archive_ready",
            "status": "PLANNED_NOT_READY",
        },
    ]


def lag_manifest() -> List[Dict[str, Any]]:
    return [
        {
            "lag_rule_id": "BAR_CLOSE_OR_SESSION_CLOSE_ONLY",
            "applies_to": "gold_d1_trend,gold_w1_trend,derived_gold_volatility",
            "required_timestamp_column": "available_after_utc",
            "join_rule": "feature_date can influence only signals with entry_time_utc > available_after_utc",
            "minimum_conservative_lag": "next_completed_bar_or_next_session_if_uncertain",
            "lookahead_risk": "low_if_enforced_mechanically",
            "audit_test": "verify no signal timestamp is <= available_after_utc for joined feature row",
        },
        {
            "lag_rule_id": "SESSION_CLOSE_AVAILABLE_AFTER_UTC_REQUIRED",
            "applies_to": "dxy_trend_acceleration,vix_or_external_volatility",
            "required_timestamp_column": "available_after_utc",
            "join_rule": "external daily close can be used after the relevant market close plus declared safety buffer",
            "minimum_conservative_lag": "next UTC day unless exact provider timestamp proves earlier availability",
            "lookahead_risk": "medium_without_provider_timestamp",
            "audit_test": "session-close proxy must be documented and applied uniformly before feature construction",
        },
        {
            "lag_rule_id": "RELEASE_OR_PROVIDER_AVAILABILITY_TIMESTAMP_REQUIRED",
            "applies_to": "real_yield_or_proxy,macro_rate_components",
            "required_timestamp_column": "available_after_utc",
            "join_rule": "macro/rate observation can be joined only after release/provider availability timestamp",
            "minimum_conservative_lag": "next_session_after_release_if_exact_intraday_timestamp_missing",
            "lookahead_risk": "high_without_release_timestamp",
            "audit_test": "reject rows with missing available_after_utc unless deterministic release convention is approved in config",
        },
        {
            "lag_rule_id": "NEXT_SESSION_AFTER_PUBLICATION_REQUIRED",
            "applies_to": "etf_flow_divergence",
            "required_timestamp_column": "release_time_utc,available_after_utc",
            "join_rule": "ETF flow/holdings updates influence only next-session or later signals unless source timestamp proves intraday availability",
            "minimum_conservative_lag": "next_session_after_publication",
            "lookahead_risk": "high_if_same_date_joined",
            "audit_test": "check available_after_utc is later than release_time_utc and all signal joins are strictly after available_after_utc",
        },
        {
            "lag_rule_id": "OFFICIAL_RELEASE_LAG_REQUIRED_SLOW_PRIOR_ONLY",
            "applies_to": "central_bank_demand_regime",
            "required_timestamp_column": "release_date_utc,available_after_utc",
            "join_rule": "period demand value can affect only dates after official/conservative release availability; never period_start/period_end",
            "minimum_conservative_lag": "next_month_or_next_quarter_after_release_if_exact_timestamp_missing",
            "lookahead_risk": "very_high_if_joined_to_period_date",
            "audit_test": "reject joins where signal date is before release_date_utc or available_after_utc",
        },
        {
            "lag_rule_id": "KNOWN_BEFORE_EVENT_ONLY",
            "applies_to": "event_calendar_risk",
            "required_timestamp_column": "scheduled_time_utc,known_before_event,available_after_utc",
            "join_rule": "scheduled event risk can suppress entries only if event record is known before the event and before the signal",
            "minimum_conservative_lag": "pre-event schedule only; realized surprise excluded",
            "lookahead_risk": "high_if_realized_surprise_or_revised_calendar_used",
            "audit_test": "reject records with known_before_event != true for historical validation",
        },
    ]


def schema_manifest() -> List[Dict[str, Any]]:
    return [
        {
            "target_file": "data/macro_regime/raw/gold_d1_ohlc_2011_present.csv",
            "schema_id": "OHLCV_DAILY_WITH_AVAILABILITY",
            "required_columns": ["date_utc", "open", "high", "low", "close", "volume", "source", "available_after_utc"],
            "date_columns": ["date_utc", "available_after_utc"],
            "numeric_columns": ["open", "high", "low", "close", "volume"],
            "primary_key": ["date_utc", "source"],
        },
        {
            "target_file": "data/macro_regime/raw/dxy_daily_2011_present.csv",
            "schema_id": "DAILY_CLOSE_WITH_AVAILABILITY",
            "required_columns": ["date_utc", "close", "source", "available_after_utc"],
            "date_columns": ["date_utc", "available_after_utc"],
            "numeric_columns": ["close"],
            "primary_key": ["date_utc", "source"],
        },
        {
            "target_file": "data/macro_regime/raw/real_yield_or_proxy_daily_2011_present.csv",
            "schema_id": "MACRO_RATE_VALUE_WITH_PROXY_METHOD",
            "required_columns": ["date_utc", "value", "source", "available_after_utc", "proxy_method"],
            "date_columns": ["date_utc", "available_after_utc"],
            "numeric_columns": ["value"],
            "primary_key": ["date_utc", "source", "proxy_method"],
        },
        {
            "target_file": "data/macro_regime/raw/vix_daily_2011_present.csv",
            "schema_id": "DAILY_CLOSE_WITH_AVAILABILITY",
            "required_columns": ["date_utc", "close", "source", "available_after_utc"],
            "date_columns": ["date_utc", "available_after_utc"],
            "numeric_columns": ["close"],
            "primary_key": ["date_utc", "source"],
        },
        {
            "target_file": "data/macro_regime/raw/gold_etf_holdings_or_flows.csv",
            "schema_id": "ETF_FLOW_HOLDINGS_WITH_RELEASE_LAG",
            "required_columns": ["date_utc", "etf_id", "holdings_tonnes_or_flow", "source", "release_time_utc", "available_after_utc"],
            "date_columns": ["date_utc", "release_time_utc", "available_after_utc"],
            "numeric_columns": ["holdings_tonnes_or_flow"],
            "primary_key": ["date_utc", "etf_id", "source"],
        },
        {
            "target_file": "data/macro_regime/raw/central_bank_gold_demand_monthly_quarterly.csv",
            "schema_id": "CENTRAL_BANK_DEMAND_WITH_RELEASE_LAG",
            "required_columns": ["period_start", "period_end", "demand_value", "unit", "source", "release_date_utc", "available_after_utc"],
            "date_columns": ["period_start", "period_end", "release_date_utc", "available_after_utc"],
            "numeric_columns": ["demand_value"],
            "primary_key": ["period_start", "period_end", "source"],
        },
        {
            "target_file": "data/macro_regime/raw/macro_event_calendar_archive.csv",
            "schema_id": "SCHEDULED_EVENT_KNOWN_BEFORE_EVENT",
            "required_columns": ["scheduled_time_utc", "event_type", "importance", "country", "known_before_event", "source", "available_after_utc"],
            "date_columns": ["scheduled_time_utc", "available_after_utc"],
            "numeric_columns": [],
            "primary_key": ["scheduled_time_utc", "event_type", "country", "source"],
        },
    ]


def write_operator_checklist(path: Path) -> None:
    text = """# Stage64D3 Operator Checklist - Macro-Regime Data Acquisition

This checklist is intentionally acquisition-only. Do not run validation after collecting files until Stage64D4 import preflight and a rerun of Stage64D pass for the selected scope.

## Required sequence

1. Acquire P0 files first: gold D1 OHLC, DXY daily, real-yield/proxy daily.
2. Put files in `data/macro_regime/raw/` using the exact target filenames in the manifest.
3. Preserve provenance columns: `source` and `available_after_utc` are mandatory for all files.
4. For central-bank and ETF data, do not use period date as availability date. Use release/availability date.
5. For event-calendar risk, exclude realized surprise from pre-event features.
6. Run Stage64D4 import preflight only after files exist.
7. Rerun Stage64D after Stage64D4. Validation remains blocked until the selected scope passes coverage and lag checks.

## Forbidden actions

- No historical validation scan.
- No reduced-scope validation unless explicitly predeclared after D4.
- No paper-order, paper-live, live, EA promotion, or broker connection.
- No intraday rescue filtering.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def markdown_table(rows: List[Dict[str, Any]], columns: List[str]) -> str:
    out = []
    out.append("| " + " | ".join(columns) + " |")
    out.append("|" + "|".join(["---" for _ in columns]) + "|")
    for r in rows:
        vals = []
        for c in columns:
            v = r.get(c, "")
            if isinstance(v, list):
                v = ", ".join(str(x) for x in v)
            vals.append(str(v))
        out.append("| " + " | ".join(vals) + " |")
    return "\n".join(out)


def run(root: Path, config_path: Path, out_dir: Path) -> Dict[str, Any]:
    config = load_config(root, config_path)
    generated_utc = utc_now()

    d2_summary_path = root / config.get(
        "stage64d2_summary_path",
        "reports/stage64d2_macro_regime_data_gap_remediation_plan/stage64d2_macro_regime_data_gap_remediation_plan_summary.json",
    )
    d2_summary = read_json(d2_summary_path) or {}

    sources = source_manifest(config)
    lags = lag_manifest()
    schemas = schema_manifest()

    out_dir.mkdir(parents=True, exist_ok=True)

    source_fields = [
        "manifest_id", "priority", "feature_ids", "source_family", "target_file",
        "minimum_start_date", "minimum_end_policy", "required_columns",
        "availability_lag_rule_id", "acceptance_criteria", "manual_action_required",
        "validation_scope_role", "status",
    ]
    write_csv(
        out_dir / "stage64d3_source_acquisition_manifest.csv",
        [{**r, "feature_ids": as_list_string(r["feature_ids"]), "required_columns": as_list_string(r["required_columns"])} for r in sources],
        source_fields,
    )
    write_json(out_dir / "stage64d3_source_acquisition_manifest.json", sources)

    lag_fields = [
        "lag_rule_id", "applies_to", "required_timestamp_column", "join_rule",
        "minimum_conservative_lag", "lookahead_risk", "audit_test",
    ]
    write_csv(out_dir / "stage64d3_lag_manifest.csv", lags, lag_fields)
    write_json(out_dir / "stage64d3_lag_manifest.json", lags)

    schema_fields = ["target_file", "schema_id", "required_columns", "date_columns", "numeric_columns", "primary_key"]
    write_csv(
        out_dir / "stage64d3_expected_file_schema.csv",
        [{**r,
          "required_columns": as_list_string(r["required_columns"]),
          "date_columns": as_list_string(r["date_columns"]),
          "numeric_columns": as_list_string(r["numeric_columns"]),
          "primary_key": as_list_string(r["primary_key"])} for r in schemas],
        schema_fields,
    )
    write_json(out_dir / "stage64d3_expected_file_schema.json", schemas)
    write_operator_checklist(out_dir / "stage64d3_operator_checklist.md")

    p0_count = sum(1 for r in sources if str(r["priority"]).startswith("P0"))
    p1_count = sum(1 for r in sources if str(r["priority"]).startswith("P1"))
    p2_count = sum(1 for r in sources if str(r["priority"]).startswith("P2"))

    summary = {
        "stage": STAGE,
        "status": STATUS,
        "decision": DECISION,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_order": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "mutation_mode": "report_only_no_state_mutation",
        "generated_utc": generated_utc,
        "root": str(root),
        "config": str(config_path),
        "out": str(out_dir),
        "inputs": {
            "stage64d2_summary": str(d2_summary_path),
            "stage64d2_status": d2_summary.get("status"),
            "stage64d2_decision": d2_summary.get("decision"),
        },
        "counts": {
            "source_manifest_rows": len(sources),
            "lag_manifest_rows": len(lags),
            "expected_schema_rows": len(schemas),
            "p0_critical_sources": p0_count,
            "p1_high_sources": p1_count,
            "p2_medium_sources": p2_count,
        },
        "validation_allowed": False,
        "historical_validation_block_reason": "Stage64D2 requires source acquisition and lag manifest completion before any Stage64D rerun or validation consideration.",
        "next_allowed_step": NEXT_ALLOWED_STEP,
        "hard_blocks": [
            "NO_PAPER_ORDER",
            "NO_EA_PROMOTION",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_BROKER_CONNECTION",
            "NO_HISTORICAL_VALIDATION_SCAN",
            "NO_REDUCED_SCOPE_SCAN_WITHOUT_EXPLICIT_PREDECLARATION",
        ],
        "outputs": {
            "summary_json": str(out_dir / "stage64d3_macro_regime_data_acquisition_lag_manifest_summary.json"),
            "report_md": str(out_dir / "stage64d3_macro_regime_data_acquisition_lag_manifest_report.md"),
            "source_manifest_csv": str(out_dir / "stage64d3_source_acquisition_manifest.csv"),
            "source_manifest_json": str(out_dir / "stage64d3_source_acquisition_manifest.json"),
            "lag_manifest_csv": str(out_dir / "stage64d3_lag_manifest.csv"),
            "lag_manifest_json": str(out_dir / "stage64d3_lag_manifest.json"),
            "expected_file_schema_csv": str(out_dir / "stage64d3_expected_file_schema.csv"),
            "expected_file_schema_json": str(out_dir / "stage64d3_expected_file_schema.json"),
            "operator_checklist_md": str(out_dir / "stage64d3_operator_checklist.md"),
        },
    }

    report = f"""# Stage64D3 - Macro-Regime Data Acquisition and Lag Manifest

Generated UTC: `{generated_utc}`

## Status

- status: `{STATUS}`
- decision: `{DECISION}`
- promotion: `NO_GO`
- paper_order: `NO_GO`
- paper_live: `NO_GO`
- live: `NO_GO`
- mutation_mode: `report_only_no_state_mutation`

## Executive conclusion

Stage64D2 confirmed that macro-regime validation is blocked until source coverage and lag-policy gaps are remediated. Stage64D3 therefore creates the acquisition manifest, lag manifest, expected file schemas, and operator checklist required before import preflight. It does not fetch data and does not authorize validation.

## Counts

| metric | value |
|---|---:|
| source_manifest_rows | {len(sources)} |
| lag_manifest_rows | {len(lags)} |
| expected_schema_rows | {len(schemas)} |
| p0_critical_sources | {p0_count} |
| p1_high_sources | {p1_count} |
| p2_medium_sources | {p2_count} |

## Source acquisition manifest

{markdown_table([{**r, "feature_ids": as_list_string(r["feature_ids"]), "required_columns": as_list_string(r["required_columns"])} for r in sources], ["priority", "manifest_id", "feature_ids", "target_file", "availability_lag_rule_id", "status"])}

## Lag manifest

{markdown_table(lags, ["lag_rule_id", "applies_to", "required_timestamp_column", "minimum_conservative_lag", "lookahead_risk"])}

## Expected file schemas

{markdown_table([{**r, "required_columns": as_list_string(r["required_columns"]), "date_columns": as_list_string(r["date_columns"]), "numeric_columns": as_list_string(r["numeric_columns"]), "primary_key": as_list_string(r["primary_key"])} for r in schemas], ["target_file", "schema_id", "required_columns", "primary_key"])}

## Operational decision

No paper-order, paper-live, live, EA promotion, broker connection, historical validation scan, or reduced-scope validation is authorized. The next step is to place acquired source files into the declared paths and run import preflight.

## Next allowed step

`{NEXT_ALLOWED_STEP}`
"""

    write_json(out_dir / "stage64d3_macro_regime_data_acquisition_lag_manifest_summary.json", summary)
    (out_dir / "stage64d3_macro_regime_data_acquisition_lag_manifest_report.md").write_text(report, encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage64D3 macro-regime source acquisition and lag manifest")
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = root / config_path
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir

    summary = run(root, config_path, out_dir)
    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "decision": summary["decision"],
        "validation_allowed": summary["validation_allowed"],
        "next_allowed_step": summary["next_allowed_step"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
