#!/usr/bin/env python3
"""
Stage64D2 - Macro-Regime Data Gap Remediation Plan

Report-only governance stage. It reads the Stage64D data-contract audit and creates
an actionable remediation plan before any macro-regime historical validation is allowed.
No trading, no order simulation, no database mutation.
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


STAGE = "Stage64D2_MACRO_REGIME_DATA_GAP_REMEDIATION_PLAN_NO_PROMOTION"
STATUS = "DATA_GAP_REMEDIATION_PLAN_COMPLETE_NO_PROMOTION"
DECISION = "REMEDIATE_MACRO_REGIME_DATA_GAPS_BEFORE_ANY_VALIDATION_NO_ORDER"
NEXT_ALLOWED_STEP = "Stage64D3_MACRO_REGIME_DATA_ACQUISITION_AND_LAG_MANIFEST_NO_ORDER"


@dataclass
class RemediationItem:
    priority: str
    feature_id: str
    blocker_type: str
    current_status: str
    required_action: str
    minimum_acceptance_criteria: str
    validation_unlocked_if_done: str
    recommended_source_type: str
    loader_or_policy_requirement: str
    no_order_note: str = "NO_ORDER_NO_PROMOTION"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path, required: bool = True) -> Dict[str, Any]:
    if not path.exists():
        if required:
            raise FileNotFoundError(str(path))
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def first_existing(root: Path, candidates: Iterable[str]) -> Optional[Path]:
    for rel in candidates:
        p = root / rel
        if p.exists():
            return p
    return None


def safe_get(d: Dict[str, Any], keys: Iterable[str], default: Any = None) -> Any:
    cur: Any = d
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def build_remediation_items(summary: Dict[str, Any]) -> List[RemediationItem]:
    fss = summary.get("feature_status_summary", {}) or {}
    missing = set(fss.get("missing_feature_ids", []) or [])
    lag_blocked = set(fss.get("lag_blocked_feature_ids", []) or [])
    coverage_blocked = set(fss.get("coverage_blocked_feature_ids", []) or [])
    blocked = list(fss.get("blocked_feature_ids", []) or [])

    items: List[RemediationItem] = []

    def add(priority: str, feature_id: str, blocker_type: str, current_status: str, action: str,
            criteria: str, unlock: str, source_type: str, loader_req: str) -> None:
        items.append(RemediationItem(
            priority=priority,
            feature_id=feature_id,
            blocker_type=blocker_type,
            current_status=current_status,
            required_action=action,
            minimum_acceptance_criteria=criteria,
            validation_unlocked_if_done=unlock,
            recommended_source_type=source_type,
            loader_or_policy_requirement=loader_req,
        ))

    # Gold price history is foundational. Current broker history starts around 2022; full regime work needs more.
    if "gold_d1_trend" in coverage_blocked or "gold_w1_trend" in coverage_blocked:
        add(
            "P0_CRITICAL",
            "gold_d1_trend/gold_w1_trend",
            "coverage",
            "present_but_short_history",
            "Backfill XAUUSD/gold D1 and W1 historical OHLC to cover at least 2011-present; preserve broker/reference-source provenance.",
            "D1 >= 2011-01-01 to present and W1 >= 2011-01-01 to present; no duplicate timestamps; bar-close only features; source and timezone documented.",
            "Enables regime split coverage for gold trend features but does not unlock full validation alone.",
            "broker_or_reference_ohlcv",
            "D1/W1 aggregation must use completed bars only; if derived from intraday, document cut-off and session close convention.",
        )

    if "dxy_trend_acceleration" in coverage_blocked or "dxy_trend_acceleration" in lag_blocked:
        add(
            "P0_CRITICAL",
            "dxy_trend_acceleration",
            "coverage_and_lag",
            "present_but_short_history_and_lag_unproven",
            "Backfill DXY daily history to 2011-present and add availability/session-close lag policy.",
            "DXY >= 2011-01-01 to present; explicit available_after_utc or deterministic session-close rule; no same-day lookahead in daily signal construction.",
            "Enables USD-pressure branch after lag audit passes.",
            "external_market_daily",
            "Loader must store date/time, value/OHLC, source, available_after_utc or lag_policy_id.",
        )

    if "real_yield_or_proxy" in coverage_blocked or "real_yield_or_proxy" in lag_blocked:
        add(
            "P0_CRITICAL",
            "real_yield_or_proxy",
            "coverage_and_lag",
            "present_but_short_history_and_lag_unproven",
            "Backfill real-yield series or approved proxy to 2011-present; include release/availability lag.",
            "Real yield/proxy >= 2011-01-01; clear selection rule; if proxy uses nominal yield and inflation expectations, each component must be lag-safe.",
            "Enables opportunity-cost pressure branch after lag audit passes.",
            "macro_rate_daily_or_proxy",
            "Loader must avoid interpolating unavailable macro observations into earlier signal dates.",
        )

    if "volatility_regime" in coverage_blocked:
        add(
            "P1_HIGH",
            "volatility_regime",
            "coverage",
            "present_but_short_history",
            "Backfill gold range/ATR and/or VIX proxy coverage to at least 2011-present, aligned to D1/W1 regime windows.",
            "Volatility proxy >= 2011-01-01; deterministic bar-close/session-close lag; regime bins predeclared before validation.",
            "Enables volatility-conditioned validation and risk filters.",
            "derived_gold_ohlc_or_external_volatility",
            "If VIX is used as proxy, document why it is proxy-only and not gold-specific volatility.",
        )

    if "etf_flow_divergence" in missing or "etf_flow_divergence" in lag_blocked:
        add(
            "P1_HIGH",
            "etf_flow_divergence",
            "missing_and_lag",
            "missing",
            "Acquire ETF holdings/flow history for gold ETFs and define next-session availability rule.",
            "ETF holdings/flows >= 2011-01-01 preferred, >= 2016 minimum if source unavailable; timestamp/release convention documented; next-session join enforced.",
            "Enables ETF accumulation/distribution divergence regimes.",
            "ETF_holdings_or_flow_daily_weekly",
            "Loader must store observed_date, published_or_available_after_utc, holdings/flow value, source, and join_lag_days.",
        )

    if "central_bank_demand_regime" in missing or "central_bank_demand_regime" in lag_blocked:
        add(
            "P1_HIGH",
            "central_bank_demand_regime",
            "missing_and_lag",
            "missing",
            "Acquire monthly/quarterly central-bank gold demand regime data with explicit release-lag handling.",
            "Series >= 2011-01-01 preferred; monthly/quarterly release date or conservative lag rule; used only as slow prior, never as entry timing.",
            "Enables central-bank demand prior in macro-regime specification.",
            "official_or_wgc_monthly_quarterly",
            "Loader must store period_start, period_end, release_date/available_after_utc, value/regime_label, source, and lag_policy_id.",
        )

    if "event_calendar_risk" in lag_blocked:
        add(
            "P2_MEDIUM",
            "event_calendar_risk",
            "lag_policy",
            "present_but_not_a_historical_archive",
            "Replace or augment current calendar with a historical event archive or restrict event filter to forward-only risk suppression.",
            "For backtest: event archive with scheduled_time_utc known before event and event_type/importance; for forward-only: explicitly exclude from historical validation.",
            "Enables event-aware validation only if historical known-before-event archive exists.",
            "macro_calendar_historical_or_forward_only",
            "Never use realized surprise or post-event outcome as pre-event feature.",
        )

    # Ensure every blocked feature has an item, even if config evolves.
    existing = {x.feature_id for x in items}
    for feature_id in blocked:
        if feature_id not in existing and not any(feature_id in x.feature_id for x in items):
            add(
                "P3_REVIEW",
                feature_id,
                "unspecified_blocker",
                "blocked",
                "Review Stage64D feature-lag audit and add explicit source/coverage/lag remediation rule.",
                "Feature marked ready by Stage64D rerun with source present, lag policy enforceable, and split coverage acceptable.",
                "May unlock part of validation depending on thesis branch.",
                "to_be_defined",
                "Add loader contract before validation.",
            )

    return items


def build_source_manifest_skeleton(items: List[RemediationItem]) -> List[Dict[str, Any]]:
    manifest: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = item.feature_id
        if key in seen:
            continue
        seen.add(key)
        manifest.append({
            "feature_id": item.feature_id,
            "priority": item.priority,
            "source_type": item.recommended_source_type,
            "source_name": "TBD",
            "file_or_table_target": "TBD",
            "minimum_start_date": "2011-01-01" if item.priority in {"P0_CRITICAL", "P1_HIGH"} else "TBD",
            "required_fields": item.loader_or_policy_requirement,
            "availability_lag_required": "YES" if "lag" in item.blocker_type else "BAR_OR_SESSION_CLOSE_ONLY",
            "manual_acquisition_allowed": "YES",
            "automated_loader_required_before_validation": "YES",
            "status": "PLANNED_NOT_READY",
        })
    return manifest


def build_blocked_validation_plan(summary: Dict[str, Any]) -> Dict[str, Any]:
    counts = summary.get("counts", {}) or {}
    feature_status = summary.get("feature_status_summary", {}) or {}
    return {
        "historical_validation_allowed": False,
        "reason": "Stage64D found data-contract, lag-policy, and coverage blockers.",
        "ready_features": counts.get("ready_features", 0),
        "blocked_features": counts.get("blocked_features"),
        "validation_ready_splits": counts.get("validation_ready_splits", 0),
        "minimum_unlock_condition": [
            "All P0 critical features pass coverage and lag audit.",
            "ETF and central-bank data are either acquired with lag rules or formally excluded from first reduced-scope validation.",
            "At least one pre-2020 split and the 2023_present split have enough features for a predeclared reduced-scope validation.",
            "No validation scan begins until Stage64D is rerun and reports readiness for the selected scope.",
        ],
        "blocked_feature_ids": feature_status.get("blocked_feature_ids", []),
        "missing_feature_ids": feature_status.get("missing_feature_ids", []),
        "lag_blocked_feature_ids": feature_status.get("lag_blocked_feature_ids", []),
        "coverage_blocked_feature_ids": feature_status.get("coverage_blocked_feature_ids", []),
    }


def markdown_report(summary: Dict[str, Any], items: List[RemediationItem], source_manifest: List[Dict[str, Any]], validation_plan: Dict[str, Any], generated_utc: str) -> str:
    counts = summary.get("counts", {}) or {}
    broker = summary.get("broker_audit", {}) or {}

    lines: List[str] = []
    lines.append("# Stage64D2 - Macro-Regime Data Gap Remediation Plan")
    lines.append("")
    lines.append(f"Generated UTC: `{generated_utc}`")
    lines.append("")
    lines.append("## Status")
    lines.append("")
    lines.append(f"- status: `{STATUS}`")
    lines.append(f"- decision: `{DECISION}`")
    lines.append("- promotion: `NO_GO`")
    lines.append("- paper_order: `NO_GO`")
    lines.append("- paper_live: `NO_GO`")
    lines.append("- live: `NO_GO`")
    lines.append("- mutation_mode: `report_only_no_state_mutation`")
    lines.append("")
    lines.append("## Executive conclusion")
    lines.append("")
    lines.append("Stage64D blocked historical validation because none of the 8 macro-regime features were ready. Stage64D2 therefore does not validate a thesis; it defines the minimum remediation actions required before any validation scan can be authorized.")
    lines.append("")
    lines.append("The immediate strategic consequence is that the project should not attempt a reduced intraday rescue or a premature macro scan. The next technical step is source acquisition and lag-manifest construction for the macro-regime feature set.")
    lines.append("")
    lines.append("## Stage64D blockers summarized")
    lines.append("")
    lines.append("| metric | value |")
    lines.append("|---|---:|")
    for k in ["feature_contract_rows", "ready_features", "blocked_features", "missing_features", "lag_blocked_features", "coverage_blocked_features", "validation_splits", "validation_ready_splits"]:
        lines.append(f"| {k} | {counts.get(k, '')} |")
    lines.append("")
    lines.append("## Broker/history baseline")
    lines.append("")
    daily = broker.get("derived_daily_coverage_from_best_intraday", {}) or {}
    lines.append("| item | value |")
    lines.append("|---|---:|")
    lines.append(f"| broker_db_status | {broker.get('status', '')} |")
    lines.append(f"| best_intraday_for_daily | {daily.get('timeframe', '')} |")
    lines.append(f"| first_time_utc | {daily.get('first_time_utc', '')} |")
    lines.append(f"| last_time_utc | {daily.get('last_time_utc', '')} |")
    lines.append(f"| coverage_years | {daily.get('coverage_years', '')} |")
    lines.append("")
    lines.append("## Remediation plan")
    lines.append("")
    lines.append("| priority | feature_id | blocker_type | required_action | minimum_acceptance_criteria |")
    lines.append("|---|---|---|---|---|")
    for item in items:
        lines.append(f"| {item.priority} | `{item.feature_id}` | {item.blocker_type} | {item.required_action} | {item.minimum_acceptance_criteria} |")
    lines.append("")
    lines.append("## Source acquisition manifest skeleton")
    lines.append("")
    lines.append("| feature_id | priority | source_type | minimum_start_date | availability_lag_required | status |")
    lines.append("|---|---|---|---|---|---|")
    for row in source_manifest:
        lines.append(f"| `{row['feature_id']}` | {row['priority']} | {row['source_type']} | {row['minimum_start_date']} | {row['availability_lag_required']} | {row['status']} |")
    lines.append("")
    lines.append("## Validation remains blocked")
    lines.append("")
    lines.append("Historical validation is still blocked. It can only be reconsidered after Stage64D is rerun and the selected feature scope passes coverage and lag checks.")
    lines.append("")
    lines.append("Minimum unlock conditions:")
    lines.append("")
    for cond in validation_plan["minimum_unlock_condition"]:
        lines.append(f"- {cond}")
    lines.append("")
    lines.append("## Operational decision")
    lines.append("")
    lines.append("No paper-order, paper-live, live, EA promotion, or historical validation scan is authorized by this remediation plan.")
    lines.append("")
    lines.append("## Next allowed step")
    lines.append("")
    lines.append(f"`{NEXT_ALLOWED_STEP}`")
    lines.append("")
    return "\n".join(lines)


def run(root: Path, config_path: Path, out_dir: Path) -> Dict[str, Any]:
    config = load_json(config_path, required=False)
    default_summary = "reports/stage64d_macro_regime_data_contract_loader_audit/stage64d_macro_regime_data_contract_loader_audit_summary.json"
    stage64d_summary_path = root / config.get("stage64d_summary", default_summary)

    stage64d_summary = load_json(stage64d_summary_path, required=True)
    generated = utc_now()

    items = build_remediation_items(stage64d_summary)
    item_rows = [asdict(x) for x in items]
    source_manifest = build_source_manifest_skeleton(items)
    validation_plan = build_blocked_validation_plan(stage64d_summary)

    out_dir.mkdir(parents=True, exist_ok=True)
    report_md = out_dir / "stage64d2_macro_regime_data_gap_remediation_plan_report.md"
    summary_json = out_dir / "stage64d2_macro_regime_data_gap_remediation_plan_summary.json"
    remediation_csv = out_dir / "stage64d2_remediation_plan.csv"
    remediation_json = out_dir / "stage64d2_remediation_plan.json"
    source_csv = out_dir / "stage64d2_source_acquisition_manifest_skeleton.csv"
    source_json = out_dir / "stage64d2_source_acquisition_manifest_skeleton.json"
    validation_json = out_dir / "stage64d2_validation_blockers_and_unlock_conditions.json"

    write_csv(remediation_csv, item_rows)
    write_json(remediation_json, item_rows)
    write_csv(source_csv, source_manifest)
    write_json(source_json, source_manifest)
    write_json(validation_json, validation_plan)

    report_text = markdown_report(stage64d_summary, items, source_manifest, validation_plan, generated)
    report_md.write_text(report_text, encoding="utf-8")

    counts = stage64d_summary.get("counts", {}) or {}
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
        "generated_utc": generated,
        "root": str(root),
        "config": str(config_path),
        "out": str(out_dir),
        "inputs": {"stage64d_summary": str(stage64d_summary_path)},
        "stage64d_counts": counts,
        "remediation_counts": {
            "remediation_items": len(items),
            "source_manifest_rows": len(source_manifest),
            "p0_critical_items": sum(1 for x in items if x.priority == "P0_CRITICAL"),
            "p1_high_items": sum(1 for x in items if x.priority == "P1_HIGH"),
            "p2_medium_items": sum(1 for x in items if x.priority == "P2_MEDIUM"),
        },
        "validation_allowed": False,
        "historical_validation_block_reason": "Stage64D found zero ready macro-regime features and unresolved lag/coverage/missing-source blockers.",
        "next_allowed_step": NEXT_ALLOWED_STEP,
        "hard_blocks": [
            "NO_PAPER_ORDER",
            "NO_EA_PROMOTION",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_BROKER_CONNECTION",
            "NO_HISTORICAL_VALIDATION_SCAN",
        ],
        "outputs": {
            "summary_json": str(summary_json.relative_to(root)) if summary_json.is_relative_to(root) else str(summary_json),
            "report_md": str(report_md.relative_to(root)) if report_md.is_relative_to(root) else str(report_md),
            "remediation_plan_csv": str(remediation_csv.relative_to(root)) if remediation_csv.is_relative_to(root) else str(remediation_csv),
            "remediation_plan_json": str(remediation_json.relative_to(root)) if remediation_json.is_relative_to(root) else str(remediation_json),
            "source_manifest_csv": str(source_csv.relative_to(root)) if source_csv.is_relative_to(root) else str(source_csv),
            "source_manifest_json": str(source_json.relative_to(root)) if source_json.is_relative_to(root) else str(source_json),
            "validation_unlock_json": str(validation_json.relative_to(root)) if validation_json.is_relative_to(root) else str(validation_json),
        },
    }
    write_json(summary_json, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage64D2 macro-regime data gap remediation plan")
    parser.add_argument("--root", default=".", help="Repo root")
    parser.add_argument("--config", default="configs/stage64d2_macro_regime_data_gap_remediation_plan.json")
    parser.add_argument("--out", default="reports/stage64d2_macro_regime_data_gap_remediation_plan")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    config_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    summary = run(root=root, config_path=config_path, out_dir=out_dir)
    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "decision": summary["decision"],
        "validation_allowed": summary["validation_allowed"],
        "next_allowed_step": summary["next_allowed_step"],
        "out": summary["out"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
