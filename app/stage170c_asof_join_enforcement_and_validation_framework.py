#!/usr/bin/env python3
"""
Stage170C — As-Of Join Enforcement and Validation Framework

Read-only governance/enforcement stage for the XAUUSD project.
It does not create trading candidates, does not write MT5 execution signals,
and does not authorize demo/live orders.

Purpose:
- Convert Stage170B's data as-of contract into machine-readable enforcement checks.
- Build a purged/embargoed walk-forward plan from broker bar timestamps.
- Produce templates/reports for path-aware labeling and multiple-testing controls.
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

STAGE = "Stage170C_ASOF_JOIN_ENFORCEMENT_AND_VALIDATION_FRAMEWORK"
REPORT_DIR = "stage170c_asof_join_enforcement_and_validation_framework"
ORDER_ROUTING_ALLOWED = False
DEMO_RELEASE_ALLOWED = False


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sniff_separator(path: Path) -> str:
    with path.open("r", encoding="utf-8-sig", errors="replace") as f:
        head = f.readline()
    candidates = {"tab": "\t", "comma": ",", "semicolon": ";", "pipe": "|"}
    counts = {name: head.count(sep) for name, sep in candidates.items()}
    best_name = max(counts, key=counts.get)
    return candidates[best_name] if counts[best_name] > 0 else ","


def sep_name(sep: str) -> str:
    return "tab" if sep == "\t" else sep


def read_json(path: Optional[Path]) -> Dict[str, Any]:
    if path is None:
        return {}
    path = path.expanduser()
    if not path.exists():
        return {"missing": True, "path": str(path)}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"read_error": f"{type(exc).__name__}: {exc}", "path": str(path)}


def inspect_csv(path: Optional[Path], max_rows: int = 5) -> Dict[str, Any]:
    if path is None:
        return {"provided": False, "exists": False}
    path = path.expanduser()
    meta: Dict[str, Any] = {"provided": True, "path": str(path), "exists": path.exists()}
    if not path.exists():
        return meta
    try:
        sep = sniff_separator(path)
        df = pd.read_csv(path, sep=sep, nrows=max_rows)
        meta.update({
            "separator": sep_name(sep),
            "sample_rows_read": int(len(df)),
            "columns": list(map(str, df.columns)),
            "size_bytes": int(path.stat().st_size),
        })
    except Exception as exc:  # noqa: BLE001
        meta.update({"read_error": f"{type(exc).__name__}: {exc}"})
    return meta


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: List[str] = []
    for row in rows:
        for key in row.keys():
            if key not in keys:
                keys.append(key)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def default_contract_rows() -> List[Dict[str, Any]]:
    """Fallback contract when Stage170B CSV is missing; mirrors Stage170B design."""
    return [
        {"source_id":"AMARKETS_M5_BROKER_BARS","source_group":"technical_broker_bars","observed_time_field":"<DATE>+<TIME>","available_time_field":"bar_close_time_utc","historical_asof_status":"MEDIUM_HIGH","intraday_join_policy":"completed_bar_only_next_bar_execution","embargo_policy":"no_same_bar_execution","blocking_issue":"must enforce completed-bar convention","required_test":"bar_timestamp_parse_and_next_bar_join_test","owner_action":"codify execution timestamp convention"},
        {"source_id":"AMARKETS_HTF_BROKER_BARS","source_group":"technical_broker_bars","observed_time_field":"derived_from_m1_or_native","available_time_field":"htf_bar_close_time_utc","historical_asof_status":"MEDIUM_HIGH","intraday_join_policy":"completed_htf_bar_only","embargo_policy":"exclude_current_incomplete_htf_bar","blocking_issue":"HTF incomplete bar can leak","required_test":"htf_asof_join_test","owner_action":"use shared HTF asof helper"},
        {"source_id":"FRED_MACRO_DAILY_PANEL","source_group":"macro","observed_time_field":"observation_date","available_time_field":"MISSING_OR_ASSUMED","historical_asof_status":"LOW","intraday_join_policy":"embargo_same_day_until_release_time_or_next_day","embargo_policy":"no same-day daily macro without release timestamp","blocking_issue":"latest revised values can leak into history","required_test":"fred_vintage_or_release_lag_test","owner_action":"add vintage/release map"},
        {"source_id":"CFTC_COT_WEEKLY","source_group":"positioning","observed_time_field":"report_date_tuesday","available_time_field":"friday_publication_time_utc_required","historical_asof_status":"MEDIUM_LOW","intraday_join_policy":"join only after publication timestamp","embargo_policy":"embargo Tuesday-Friday observation gap","blocking_issue":"Tuesday values leak if joined before Friday publication","required_test":"cot_publication_lag_test","owner_action":"add available_time_utc"},
        {"source_id":"ETF_GLD_WGC_CENTRAL_BANK_GOLD","source_group":"flows","observed_time_field":"flow_date_or_month","available_time_field":"publication_time_utc_required","historical_asof_status":"LOW_TO_MEDIUM","intraday_join_policy":"available_time asof only","embargo_policy":"frequency-specific publication lag","blocking_issue":"calendar date is not availability date","required_test":"flow_publication_lag_test","owner_action":"populate source-specific available_time_utc"},
        {"source_id":"SCHEDULED_MACRO_EVENT_CALENDAR","source_group":"calendar","observed_time_field":"scheduled_release_time_utc","available_time_field":"schedule_known_time_or_release_time","historical_asof_status":"MEDIUM_FOR_SCHEDULE_LOW_FOR_ACTUAL_SURPRISE","intraday_join_policy":"schedule known before event; actual after release","embargo_policy":"split schedule and released surprise features","blocking_issue":"actual values can leak if timestamp absent","required_test":"schedule_vs_actual_split_test","owner_action":"separate schedule-only and release-value features"},
        {"source_id":"GDELT_NEWS_PANEL_STAGE166F","source_group":"news_event_guard","observed_time_field":"time_bucket_utc","available_time_field":"fetch_time_or_bucket_end_required","historical_asof_status":"MEDIUM_AS_GUARD_LOW_AS_ALPHA","intraday_join_policy":"guard only unless hand labels pass event study","embargo_policy":"do not use as direct alpha without event-study","blocking_issue":"article-count intensity is not causal directional label","required_test":"event_study_and_label_quality_test","owner_action":"keep as guard"},
        {"source_id":"MANUAL_CURRENT_EVENTS","source_group":"manual_events","observed_time_field":"event_time_utc","available_time_field":"created_at_utc_required","historical_asof_status":"LOW_FOR_BACKTEST_UNLESS_VERSIONED","intraday_join_policy":"manual current only unless versioned","embargo_policy":"versioned created_at before use","blocking_issue":"manual backfill can create hindsight bias","required_test":"manual_event_created_at_test","owner_action":"add created_at/source_quality/versioning"},
    ]


def load_contract(path: Optional[Path]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if path is None:
        return default_contract_rows(), {"source": "default_embedded_stage170b_contract", "exists": False}
    path = path.expanduser()
    meta = inspect_csv(path, max_rows=5)
    if not path.exists():
        return default_contract_rows(), {**meta, "source": "default_embedded_stage170b_contract"}
    try:
        sep = sniff_separator(path)
        df = pd.read_csv(path, sep=sep)
        rows = df.fillna("").to_dict(orient="records")
        return rows, {**meta, "source": str(path), "row_count": int(len(rows))}
    except Exception as exc:  # noqa: BLE001
        return default_contract_rows(), {**meta, "source": "default_embedded_stage170b_contract", "load_error": f"{type(exc).__name__}: {exc}"}


def norm_text(value: Any) -> str:
    return str(value or "").strip().upper()


def enforce_contract(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    report: List[Dict[str, Any]] = []
    for row in rows:
        source_id = str(row.get("source_id", "UNKNOWN"))
        status = norm_text(row.get("historical_asof_status"))
        available = norm_text(row.get("available_time_field"))
        observed = norm_text(row.get("observed_time_field"))
        embargo = norm_text(row.get("embargo_policy"))
        issue = str(row.get("blocking_issue", ""))
        required_test = str(row.get("required_test", ""))

        missing_available = (not available) or ("MISSING" in available) or ("REQUIRED" in available and "TIME" in available)
        low_status = "LOW" in status
        medium_low_status = "MEDIUM_LOW" in status or "LOW_TO_MEDIUM" in status
        ambiguous_alpha_news = "GDELT" in source_id and "LOW_AS_ALPHA" in status
        missing_observed = not observed
        missing_embargo = not embargo

        blocking_for_discovery = bool(missing_available or missing_observed or low_status or medium_low_status or ambiguous_alpha_news)
        blocking_for_promotion = bool(blocking_for_discovery or missing_embargo)
        pass_for_guard_only = bool("GDELT" in source_id or "MANUAL" in source_id)

        report.append({
            "source_id": source_id,
            "historical_asof_status": row.get("historical_asof_status", ""),
            "available_time_field": row.get("available_time_field", ""),
            "observed_time_field": row.get("observed_time_field", ""),
            "embargo_policy": row.get("embargo_policy", ""),
            "required_test": required_test,
            "blocking_issue": issue,
            "missing_available_time_policy": missing_available,
            "missing_observed_time_policy": missing_observed,
            "missing_embargo_policy": missing_embargo,
            "low_or_medium_low_asof_confidence": bool(low_status or medium_low_status),
            "ambiguous_alpha_semantics": ambiguous_alpha_news,
            "pass_for_guard_only": pass_for_guard_only,
            "pass_for_new_discovery": not blocking_for_discovery,
            "pass_for_commercial_promotion": not blocking_for_promotion,
            "enforcement_action": "BLOCK_NEW_DISCOVERY_UNTIL_SOURCE_POLICY_FIXED" if blocking_for_discovery else "ALLOW_READONLY_RESEARCH_WITH_CONTRACT",
        })
    return report


def load_bar_times(path: Path) -> Dict[str, Any]:
    path = path.expanduser()
    meta = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        meta["error"] = "missing bars file"
        return meta
    try:
        sep = sniff_separator(path)
        df_head = pd.read_csv(path, sep=sep, nrows=5)
        cols = list(map(str, df_head.columns))
        meta.update({"separator": sep_name(sep), "columns": cols})
        if "<DATE>" in cols and "<TIME>" in cols:
            df = pd.read_csv(path, sep=sep, usecols=["<DATE>", "<TIME>"])
            times = pd.to_datetime(df["<DATE>"].astype(str) + " " + df["<TIME>"].astype(str), utc=True, errors="coerce")
        elif "time_utc" in cols:
            df = pd.read_csv(path, sep=sep, usecols=["time_utc"])
            times = pd.to_datetime(df["time_utc"], utc=True, errors="coerce")
        elif "timestamp" in cols:
            df = pd.read_csv(path, sep=sep, usecols=["timestamp"])
            times = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        else:
            meta["error"] = f"cannot identify timestamp columns: {cols}"
            return meta
        times = pd.Series(times).dropna().sort_values().reset_index(drop=True)
        if times.empty:
            meta["error"] = "no parseable timestamps"
            return meta
        meta.update({
            "row_count": int(len(times)),
            "min_time_utc": str(times.iloc[0]),
            "max_time_utc": str(times.iloc[-1]),
        })
        return {"meta": meta, "times": times}
    except Exception as exc:  # noqa: BLE001
        meta["error"] = f"{type(exc).__name__}: {exc}"
        return meta


def build_walk_forward(times: pd.Series, n_folds: int = 6, embargo_hours: int = 24) -> List[Dict[str, Any]]:
    if len(times) < 500:
        return []
    start = pd.Timestamp(times.iloc[0]).to_pydatetime()
    end = pd.Timestamp(times.iloc[-1]).to_pydatetime()
    total_seconds = (end - start).total_seconds()
    if total_seconds <= 0:
        return []
    rows: List[Dict[str, Any]] = []
    # Expanding train, rolling selection+validation. Keep final 20% untouched by convention.
    for i in range(n_folds):
        train_end_frac = 0.45 + i * 0.06
        sel_end_frac = train_end_frac + 0.05
        val_end_frac = sel_end_frac + 0.05
        if val_end_frac >= 0.80:
            val_end_frac = 0.80
        train_start = start
        train_end = start + timedelta(seconds=total_seconds * train_end_frac)
        selection_start = train_end + timedelta(hours=embargo_hours)
        selection_end = start + timedelta(seconds=total_seconds * sel_end_frac)
        validation_start = selection_end + timedelta(hours=embargo_hours)
        validation_end = start + timedelta(seconds=total_seconds * val_end_frac)
        if validation_start >= validation_end:
            continue
        rows.append({
            "fold_id": f"WF{i+1:02d}",
            "train_start_utc": train_start.isoformat(),
            "train_end_utc": train_end.isoformat(),
            "selection_start_utc": selection_start.isoformat(),
            "selection_end_utc": selection_end.isoformat(),
            "validation_start_utc": validation_start.isoformat(),
            "validation_end_utc": validation_end.isoformat(),
            "embargo_hours": embargo_hours,
            "final_locked_holdout_rule": "do_not_use_newest_20pct_for_selection_or_model_choice",
            "pass_fail_rule": "candidate_family_must_pass_majority_folds_and_final_locked_holdout_after_costs",
        })
    return rows


def build_multiple_testing_template() -> List[Dict[str, Any]]:
    return [
        {"control_layer":"family_lineage_registry","purpose":"track how many deterministic variants were searched per thesis family","required_columns":"family_id,rule_id,stage,parameters,train_window,selection_window","promotion_gate":"no orphan candidate can be promoted without family lineage"},
        {"control_layer":"deflated_or_probabilistic_sharpe","purpose":"adjust apparent edge for non-normal returns and repeated trials","required_columns":"raw_sharpe,n_trials,skew,kurtosis,obs_count,deflated_sharpe_or_psr","promotion_gate":"adjusted score must remain credible, not only raw holdout mean"},
        {"control_layer":"reality_check_style_family_report","purpose":"evaluate best rule against family-level data snooping risk","required_columns":"family_best,bootstrap_null,adjusted_p_value,fold_count","promotion_gate":"family-adjusted result must pass before demo"},
        {"control_layer":"final_locked_holdout_protection","purpose":"prevent repeated use of newest 20pct for selection","required_columns":"holdout_access_count,decision_use,stage_id","promotion_gate":"final holdout cannot be reused for iterative tuning without reset"},
    ]


def build_path_label_framework() -> List[Dict[str, Any]]:
    return [
        {"label_layer":"fixed_horizon_endpoint","status":"allowed_for_first_pass_only","definition":"net return at fixed horizon after entry lag and cost","risk":"misses stop path, intratrade drawdown, dwell time"},
        {"label_layer":"mfe_mae_path_audit","status":"required_before_execution_replay","definition":"maximum favorable/adverse excursion during trade horizon","risk":"candidate can look good at endpoint but be untradable due to adverse path"},
        {"label_layer":"triple_barrier_label","status":"recommended_for_promotion","definition":"take-profit, stop-loss and time barrier using volatility-scaled thresholds","risk":"requires careful cost and spread modeling"},
        {"label_layer":"dwell_time_and_turnover","status":"required_before_demo","definition":"holding-time distribution, overlap, trade count, daily turnover","risk":"excess churn and session clustering can destroy executable edge"},
        {"label_layer":"spread_slippage_stress","status":"required_before_demo","definition":"base/stressed broker spread and slippage replay by session/news state","risk":"cost assumptions can dominate XAUUSD M5 candidate edge"},
    ]


def build_temporal_join_test_plan(enforcement_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for r in enforcement_rows:
        sid = r["source_id"]
        rows.append({
            "source_id": sid,
            "test_id": f"ASOF_JOIN_{sid}",
            "test_goal": "ensure feature value is unavailable before available_time_utc and never joined on observation date alone",
            "required_before": "new_discovery" if not r["pass_for_new_discovery"] else "promotion",
            "expected_failure_now": not r["pass_for_new_discovery"],
            "minimum_assertions": "no join when bar_time < available_time_utc; completed-bar/HTF embargo; missing contract blocks scan",
        })
    return rows


def decision_md(summary: Dict[str, Any], top_blockers: List[Dict[str, Any]]) -> str:
    blockers_md = "\n".join(
        f"| {b['source_id']} | {b['historical_asof_status']} | {b['blocking_issue']} | {b['enforcement_action']} |"
        for b in top_blockers[:20]
    ) or "| none | - | - | - |"
    return f"""# Stage170C As-Of Join Enforcement and Validation Framework

Generated UTC: `{summary['generated_utc']}`

Decision: `{summary['decision']}`  
Recommended action: `{summary['recommended_action']}`

## Scope

This is a read-only enforcement/framework stage. It creates no trading candidates, writes no MT5 execution signal, and authorizes no demo/live order.

## Enforcement result

Contract rows checked: `{summary['contract_enforcement']['contract_rows']}`  
Rows blocking new discovery: `{summary['contract_enforcement']['blocking_new_discovery_rows']}`  
Rows blocking commercial promotion: `{summary['contract_enforcement']['blocking_promotion_rows']}`

## Blocking rows

| source_id | historical_asof_status | blocking_issue | enforcement_action |
|---|---:|---|---|
{blockers_md}

## Validation framework outputs

- Purged/embargoed walk-forward folds: `{summary['framework_counts']['walk_forward_folds']}`
- Temporal join test rows: `{summary['framework_counts']['temporal_join_tests']}`
- Multiple-testing control rows: `{summary['framework_counts']['multiple_testing_controls']}`
- Path-label framework rows: `{summary['framework_counts']['path_label_framework_rows']}`

## Verdict

New discovery remains frozen until blocking as-of rows are edited and enforced in loaders. The next productive step is not another scan; it is loader-level enforcement of this contract plus walk-forward/multiple-testing support.

## Next

1. Review `stage170c_data_contract_enforcement_report.csv` and fix rows that block new discovery.
2. Convert `stage170c_temporal_join_test_report.csv` into automated loader tests.
3. Implement purged walk-forward and multiple-testing controls before any new candidate promotion.
4. Keep GDELT/news as a guard only unless hand-labeled event-study features are added.
"""


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=STAGE)
    parser.add_argument("--root", required=True)
    parser.add_argument("--bars-m5", required=False)
    parser.add_argument("--event-panel", required=False)
    parser.add_argument("--stage170b-summary", required=False)
    parser.add_argument("--data-asof-contract", required=False)
    parser.add_argument("--event-inbox", required=False)
    parser.add_argument("--n-walk-forward-folds", type=int, default=6)
    parser.add_argument("--embargo-hours", type=int, default=24)
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser()
    out_dir = root / "reports" / REPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    stage170b_summary_path = Path(args.stage170b_summary).expanduser() if args.stage170b_summary else root / "reports" / "stage170b_data_asof_contract_validation_redesign" / "stage170b_data_asof_contract_summary.json"
    contract_path = Path(args.data_asof_contract).expanduser() if args.data_asof_contract else root / "reports" / "stage170b_data_asof_contract_validation_redesign" / "stage170b_data_asof_contract.csv"

    stage170b_summary = read_json(stage170b_summary_path)
    contract_rows, contract_meta = load_contract(contract_path)
    enforcement_rows = enforce_contract(contract_rows)

    bars_meta: Dict[str, Any] = {"provided": bool(args.bars_m5)}
    walk_forward_rows: List[Dict[str, Any]] = []
    if args.bars_m5:
        bar_result = load_bar_times(Path(args.bars_m5))
        if "times" in bar_result:
            times = bar_result.pop("times")
            bars_meta = bar_result.get("meta", {})
            walk_forward_rows = build_walk_forward(times, n_folds=args.n_walk_forward_folds, embargo_hours=args.embargo_hours)
        else:
            bars_meta = bar_result

    event_panel_meta = inspect_csv(Path(args.event_panel).expanduser() if args.event_panel else None)
    temporal_join_rows = build_temporal_join_test_plan(enforcement_rows)
    multiple_testing_rows = build_multiple_testing_template()
    path_label_rows = build_path_label_framework()

    blocking_new = [r for r in enforcement_rows if not r["pass_for_new_discovery"]]
    blocking_promo = [r for r in enforcement_rows if not r["pass_for_commercial_promotion"]]
    decision = "STAGE170C_ASOF_ENFORCEMENT_BLOCKS_NEW_DISCOVERY" if blocking_new else "STAGE170C_ASOF_FRAMEWORK_READY_FOR_READONLY_DISCOVERY_ONLY"
    recommended = "FREEZE_NEW_DISCOVERY; FIX_BLOCKING_ASOF_ROWS; IMPLEMENT_LOADER_TESTS" if blocking_new else "ALLOW_READONLY_RESEARCH_ONLY; BUILD_WALK_FORWARD_AND_MULTIPLE_TESTING_BEFORE_PROMOTION"

    summary: Dict[str, Any] = {
        "stage": STAGE,
        "generated_utc": utc_now_iso(),
        "root": str(root),
        "order_routing_allowed": ORDER_ROUTING_ALLOWED,
        "demo_release_allowed": DEMO_RELEASE_ALLOWED,
        "status": "STAGE170C_COMPLETE_ASOF_ENFORCEMENT_FRAMEWORK_READY",
        "decision": decision,
        "severity": "HIGH" if blocking_new else "MEDIUM_HIGH",
        "recommended_action": recommended,
        "inputs": {
            "bars_m5": args.bars_m5,
            "event_panel": args.event_panel,
            "stage170b_summary": str(stage170b_summary_path),
            "data_asof_contract": str(contract_path),
            "event_inbox": args.event_inbox,
        },
        "stage170b_verdict": {
            "decision": stage170b_summary.get("decision"),
            "recommended_action": stage170b_summary.get("recommended_action"),
            "methodology_gate": stage170b_summary.get("methodology_gate", {}),
        },
        "inspections": {
            "bars_m5": bars_meta,
            "event_panel": event_panel_meta,
            "contract": contract_meta,
        },
        "contract_enforcement": {
            "contract_rows": len(enforcement_rows),
            "blocking_new_discovery_rows": len(blocking_new),
            "blocking_promotion_rows": len(blocking_promo),
            "pass_guard_only_rows": sum(1 for r in enforcement_rows if r.get("pass_for_guard_only")),
        },
        "framework_counts": {
            "walk_forward_folds": len(walk_forward_rows),
            "temporal_join_tests": len(temporal_join_rows),
            "multiple_testing_controls": len(multiple_testing_rows),
            "path_label_framework_rows": len(path_label_rows),
        },
        "methodology_gate": {
            "new_discovery_allowed": False if blocking_new else True,
            "commercial_promotion_allowed": False,
            "demo_release_allowed": False,
            "news_alpha_allowed": False,
            "news_guard_allowed": True,
            "next_required_stage": "Stage170D_LOADER_LEVEL_ASOF_ENFORCEMENT_AND_WALK_FORWARD_ENGINE" if blocking_new else "Stage170D_PURGED_WALK_FORWARD_AND_MULTIPLE_TESTING_ENGINE",
        },
        "outputs": {
            "summary_json": str(out_dir / "stage170c_asof_enforcement_summary.json"),
            "decision_md": str(out_dir / "stage170c_decision.md"),
            "contract_enforcement_csv": str(out_dir / "stage170c_data_contract_enforcement_report.csv"),
            "temporal_join_test_report_csv": str(out_dir / "stage170c_temporal_join_test_report.csv"),
            "purged_walk_forward_folds_csv": str(out_dir / "stage170c_purged_walk_forward_folds.csv"),
            "multiple_testing_template_csv": str(out_dir / "stage170c_multiple_testing_adjustment_template.csv"),
            "path_label_framework_csv": str(out_dir / "stage170c_path_label_framework.csv"),
        },
        "next": [
            "Do not run new discovery while as-of contract rows block new discovery.",
            "Review and edit the source-level contract so every source has observed_time, available_time, embargo and revision policy.",
            "Turn temporal join tests into automated loader tests before alpha scanning.",
            "Build purged walk-forward and multiple-testing controls before candidate promotion.",
        ],
    }

    write_csv(out_dir / "stage170c_data_contract_enforcement_report.csv", enforcement_rows)
    write_csv(out_dir / "stage170c_temporal_join_test_report.csv", temporal_join_rows)
    write_csv(out_dir / "stage170c_purged_walk_forward_folds.csv", walk_forward_rows)
    write_csv(out_dir / "stage170c_multiple_testing_adjustment_template.csv", multiple_testing_rows)
    write_csv(out_dir / "stage170c_path_label_framework.csv", path_label_rows)
    (out_dir / "stage170c_asof_enforcement_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "stage170c_decision.md").write_text(decision_md(summary, blocking_new), encoding="utf-8")

    print(json.dumps({
        "status": summary["status"],
        "decision": summary["decision"],
        "blocking_new_discovery_rows": len(blocking_new),
        "walk_forward_folds": len(walk_forward_rows),
        "summary_json": summary["outputs"]["summary_json"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
