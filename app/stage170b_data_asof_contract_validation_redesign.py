#!/usr/bin/env python3
"""
Stage170B — Data As-Of Contract and Validation Redesign

Read-only governance stage for the XAUUSD project.
It does not create trading candidates, does not write MT5 execution signals,
and does not authorize demo/live orders.

Outputs:
- data_asof_contract.csv
- data_asof_contract_summary.json
- validation_redesign_matrix.csv
- purged_walk_forward_plan.csv
- multiple_testing_control_plan.csv
- stage170b_decision.md
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

STAGE = "Stage170B_DATA_ASOF_CONTRACT_AND_VALIDATION_REDESIGN"
REPORT_DIR = "stage170b_data_asof_contract_validation_redesign"

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


def inspect_csv(path: Optional[Path], max_rows: int = 5) -> Dict[str, Any]:
    if path is None:
        return {"provided": False, "exists": False}
    path = path.expanduser()
    meta: Dict[str, Any] = {
        "provided": True,
        "path": str(path),
        "exists": path.exists(),
    }
    if not path.exists():
        return meta
    try:
        sep = sniff_separator(path)
        df = pd.read_csv(path, sep=sep, nrows=max_rows)
        meta.update({
            "separator": "tab" if sep == "\t" else sep,
            "sample_rows_read": int(len(df)),
            "columns": list(map(str, df.columns)),
            "size_bytes": int(path.stat().st_size),
        })
    except Exception as exc:  # noqa: BLE001 - audit artifact should capture errors
        meta.update({"read_error": f"{type(exc).__name__}: {exc}"})
    return meta


@dataclass
class AsofRow:
    source_id: str
    source_group: str
    source_path_or_table: str
    observed_time_field: str
    effective_time_field: str
    available_time_field: str
    assumed_publication_lag: str
    revision_policy: str
    historical_asof_status: str
    intraday_join_policy: str
    embargo_policy: str
    current_use: str
    blocking_issue: str
    required_test: str
    owner_action: str


@dataclass
class ValidationRow:
    validation_layer: str
    purpose: str
    required_before: str
    design: str
    leakage_control: str
    output_artifact: str
    pass_fail_rule: str


@dataclass
class MultipleTestingRow:
    risk_area: str
    current_issue: str
    proposed_control: str
    implementation_note: str
    promotion_gate: str


@dataclass
class WalkForwardRow:
    fold_id: str
    train_window: str
    selection_window: str
    validation_window: str
    embargo: str
    notes: str


def build_contract_rows(args: argparse.Namespace, inspections: Dict[str, Dict[str, Any]]) -> List[AsofRow]:
    event_inbox = str(Path(args.event_inbox).expanduser()) if args.event_inbox else ""
    rows: List[AsofRow] = [
        AsofRow(
            source_id="AMARKETS_M5_BROKER_BARS",
            source_group="technical_broker_bars",
            source_path_or_table=str(Path(args.bars_m5).expanduser()),
            observed_time_field="<DATE> + <TIME> parsed to time_utc; project convention currently applies broker timestamp shift where needed",
            effective_time_field="bar close/open timestamp, timeframe dependent; must be explicit per loader",
            available_time_field="bar_end_time_utc + feed_latency_assumption",
            assumed_publication_lag="M5: 0 to 5 minutes depending on whether signal uses bar open or completed bar",
            revision_policy="append-only broker export; validate duplicate and timezone handling after each import",
            historical_asof_status="MEDIUM_HIGH if completed-bar rule is enforced; MEDIUM if same-bar features are allowed",
            intraday_join_policy="never use current incomplete bar for decision; features at t may only use bars ending <= t",
            embargo_policy="none for completed broker bars; one-bar embargo for ambiguous same-bar logic",
            current_use="primary technical price/volatility input",
            blocking_issue="must lock whether each rule uses bar open t, bar close t, or next bar execution t",
            required_test="loader_timezone_and_separator_test; completed_bar_no_lookahead_test; duplicate_timestamp_test",
            owner_action="codify execution timestamp convention before any new alpha promotion",
        ),
        AsofRow(
            source_id="AMARKETS_M1_M15_M30_H1_BROKER_BARS",
            source_group="technical_broker_bars",
            source_path_or_table=f"{event_inbox}/amarkets_xauusd_{{1m,15m,30m,1h}}.csv or derived DB bars",
            observed_time_field="broker timestamp columns or DB utc_time",
            effective_time_field="bar close/open timestamp by timeframe",
            available_time_field="bar_end_time_utc + feed_latency_assumption",
            assumed_publication_lag="timeframe duration; use completed bar only",
            revision_policy="append-only; derived bars must be rebuilt only from past lower timeframe bars",
            historical_asof_status="MEDIUM_HIGH after explicit derivation tests",
            intraday_join_policy="higher timeframe feature at M5 t must use only last completed higher timeframe bar",
            embargo_policy="embargo current H1/M30/M15 bar for M5 rules unless using completed bar",
            current_use="technical multi-timeframe context",
            blocking_issue="derived timeframe alignment can leak if current incomplete HTF bar is used",
            required_test="higher_timeframe_completed_bar_join_test",
            owner_action="add HTF-asof join helper shared by all scans",
        ),
        AsofRow(
            source_id="FRED_MACRO_DAILY_PANEL",
            source_group="macro_fundamental",
            source_path_or_table=args.macro_panel or "reports/data/local macro panel if present",
            observed_time_field="economic observation date",
            effective_time_field="economic period date",
            available_time_field="release timestamp/vintage timestamp required; if absent, not historically as-of safe",
            assumed_publication_lag="series-specific; daily close or release calendar dependent",
            revision_policy="revised; must use vintage/real-time data when available",
            historical_asof_status="LOW until vintage/available_time is added",
            intraday_join_policy="same-day macro cannot be used intraday unless release time is known and <= decision time",
            embargo_policy="daily macro embargo until next trading day unless explicit release timestamp exists",
            current_use="macro regime features / priors",
            blocking_issue="lookahead risk from using latest revised values in historical periods",
            required_test="macro_available_time_not_after_signal_test; revision_policy_audit",
            owner_action="create source-specific release/vintage map or embargo same-day macro",
        ),
        AsofRow(
            source_id="CFTC_COT_WEEKLY",
            source_group="positioning_fundamental",
            source_path_or_table=f"{event_inbox}/cot*.csv or DB/exogenous COT files",
            observed_time_field="report_as_of_date / Tuesday positioning date",
            effective_time_field="positioning week ending date",
            available_time_field="CFTC publication timestamp, typically Friday after market hours; exact timestamp required",
            assumed_publication_lag="several days after observed date",
            revision_policy="occasionally revised/corrected; use published value available as of signal time",
            historical_asof_status="MEDIUM_LOW until available_time is explicit",
            intraday_join_policy="COT can only affect signals after publication time, not during report week",
            embargo_policy="no COT usage before publication timestamp; if timestamp unknown, embargo until following Monday open",
            current_use="positioning regime / crowding overlay",
            blocking_issue="large lookahead risk if Tuesday observation is joined before Friday publication",
            required_test="cot_publication_lag_join_test",
            owner_action="add COT available_time_utc and enforce asof join",
        ),
        AsofRow(
            source_id="ETF_GLD_WGC_CENTRAL_BANK_GOLD",
            source_group="flow_fundamental",
            source_path_or_table=f"{event_inbox}/ETF/WGC/SPDR/central_bank_gold files",
            observed_time_field="flow date / report date",
            effective_time_field="flow period end",
            available_time_field="publication/download timestamp required",
            assumed_publication_lag="source dependent; often end-of-day or monthly lag",
            revision_policy="source dependent; must be tagged",
            historical_asof_status="LOW to MEDIUM until publication lag is explicit",
            intraday_join_policy="not usable intraday on same date unless release time is known",
            embargo_policy="embargo until next session or known publication time",
            current_use="regime prior / demand context",
            blocking_issue="calendar date is not availability date",
            required_test="flow_publication_lag_contract_test",
            owner_action="populate available_time_utc and frequency for each flow source",
        ),
        AsofRow(
            source_id="SCHEDULED_MACRO_EVENT_CALENDAR",
            source_group="calendar_fundamental",
            source_path_or_table=f"{event_inbox}/calendar_events.csv or equivalent",
            observed_time_field="scheduled_release_time_utc",
            effective_time_field="economic event period / release timestamp",
            available_time_field="calendar_known_time_utc for schedule; actual value release time for surprise",
            assumed_publication_lag="schedule known before event; actual value known at release time only",
            revision_policy="calendar may be revised; actual data may be revised",
            historical_asof_status="MEDIUM if schedule-only; LOW if actual surprise lacks release timestamp",
            intraday_join_policy="pre-event guard can use schedule; post-event surprise can only use actual after release time",
            embargo_policy="event blackout/guard windows must be explicit",
            current_use="event blackout/guard and possible macro surprise features",
            blocking_issue="mixing known schedule with unknown actual values can leak",
            required_test="scheduled_vs_actual_feature_separation_test",
            owner_action="split schedule features and released-value/surprise features",
        ),
        AsofRow(
            source_id="GDELT_NEWS_PANEL_STAGE166F",
            source_group="news_event_guard",
            source_path_or_table=str(Path(args.event_panel).expanduser()) if args.event_panel else "reports/stage166_current_event_shock_overlay/stage166_current_event_intraday_panel.csv",
            observed_time_field="GDELT time_bucket_utc / article event bucket",
            effective_time_field="article publication/count bucket",
            available_time_field="publication bucket + fetch/update latency; exact crawl availability not guaranteed",
            assumed_publication_lag="hourly bucket; operational use should treat as guard after bucket close",
            revision_policy="article counts can change as crawl updates; artifact snapshot must be versioned",
            historical_asof_status="MEDIUM as guard, LOW as alpha without hand labels and event-study validation",
            intraday_join_policy="use only closed hourly news bucket; no same-hour alpha claim",
            embargo_policy="one-hour embargo recommended for intraday rules unless exact publication timestamp exists",
            current_use="current-event guard only after Stage168/169 alpha kill",
            blocking_issue="article-count intensity is not causal directional event label",
            required_test="closed_hour_bucket_test; event_study_by_class_test; artifact_snapshot_manifest_test",
            owner_action="keep as guard; build hand-labeled event dataset before reattempting news alpha",
        ),
        AsofRow(
            source_id="MANUAL_CURRENT_EVENTS",
            source_group="manual_news_guard",
            source_path_or_table=f"{event_inbox}/manual_current_events.csv",
            observed_time_field="event_time_utc manually entered",
            effective_time_field="event occurrence/publication time",
            available_time_field="manual entry timestamp required but not yet captured",
            assumed_publication_lag="human entry dependent",
            revision_policy="manual edits must be append-only or versioned",
            historical_asof_status="LOW for backtest unless entry timestamp and source URL are versioned",
            intraday_join_policy="manual events usable operationally after entry time only",
            embargo_policy="manual event timestamp cannot be backfilled into historical discovery without label dataset flag",
            current_use="current regime guard / specialist override context",
            blocking_issue="manual backfill can create hindsight bias",
            required_test="manual_event_entry_timestamp_test; source_url_required_test",
            owner_action="add created_at_utc and label_source_quality columns",
        ),
    ]
    return rows


def build_validation_rows() -> List[ValidationRow]:
    return [
        ValidationRow(
            validation_layer="data_asof_contract",
            purpose="prove every feature was historically available at signal time",
            required_before="any new discovery promotion or demo release",
            design="source-level contract with observed/effective/available timestamps and revision policy",
            leakage_control="as-of joins; same-day embargo where release time unknown",
            output_artifact="data_asof_contract.csv; temporal_join_test_report.csv",
            pass_fail_rule="all blocking sources must have available_time policy and automated tests",
        ),
        ValidationRow(
            validation_layer="event_study_by_feature_class",
            purpose="measure whether news/event classes have empirical response curves before rule search",
            required_before="any future news-alpha scan",
            design="class x lag x horizon abnormal return/volatility/decay report",
            leakage_control="closed event bucket; no same-hour use unless timestamped",
            output_artifact="event_study_by_class_lag_decay.csv/md",
            pass_fail_rule="at least one class must show stable train and pre-holdout response before alpha search",
        ),
        ValidationRow(
            validation_layer="path_aware_label_audit",
            purpose="replace endpoint-only return with execution-relevant path labels",
            required_before="execution replay or demo candidate promotion",
            design="triple-barrier or MFE/MAE labels with stop/take-profit/timeout and hold time",
            leakage_control="bar-by-bar forward path only after entry timestamp",
            output_artifact="path_label_audit.csv; mfe_mae_distribution.csv",
            pass_fail_rule="candidate must survive path-based net outcome, not only fixed-horizon endpoint return",
        ),
        ValidationRow(
            validation_layer="purged_embargoed_walk_forward",
            purpose="reduce overfit and selection leakage across adjacent time windows",
            required_before="candidate shortlist promotion",
            design="rolling train/select/validate folds with embargo around split boundaries; final holdout untouched",
            leakage_control="purge overlapping label horizons; embargo max horizon after fold boundary",
            output_artifact="walk_forward_matrix.csv; fold_metrics.csv",
            pass_fail_rule="candidate family must pass majority of folds and not rely on final holdout selection",
        ),
        ValidationRow(
            validation_layer="multiple_testing_control",
            purpose="correct for thousands of scanned deterministic variants",
            required_before="commercial promotion",
            design="family lineage accounting, deflated/probabilistic Sharpe, reality-check-style or holdout selection limits",
            leakage_control="pre-register family count and selection criteria before scan where possible",
            output_artifact="data_snooping_adjustment_report.md/csv",
            pass_fail_rule="raw edge must remain credible after family-level adjustment",
        ),
        ValidationRow(
            validation_layer="cost_slippage_execution_replay",
            purpose="model broker execution feasibility under spread/news/session stress",
            required_before="demo release",
            design="spread distribution by session/news state; slippage stress; cooldown; max daily loss; order rounding",
            leakage_control="use only spread values available at/near execution; stress unseen periods separately",
            output_artifact="execution_replay_report.md; order_path_ledger.csv",
            pass_fail_rule="net performance must survive base and stressed cost scenarios",
        ),
        ValidationRow(
            validation_layer="regime_concentration_report",
            purpose="avoid year/month/day or one-regime dominance",
            required_before="demo release",
            design="metrics by year, month, volatility regime, dollar/yield macro regime, session, and news guard state",
            leakage_control="regime labels as-of only",
            output_artifact="regime_stratified_metrics.csv",
            pass_fail_rule="no single day/month/year/regime contributes excessive share of PnL/events",
        ),
    ]


def build_multiple_testing_rows() -> List[MultipleTestingRow]:
    return [
        MultipleTestingRow(
            risk_area="large deterministic rule scans",
            current_issue="Stages have scanned hundreds to thousands of variants across families, horizons, thresholds, confirmations",
            proposed_control="candidate_family_id, variant_count, selection_count, and pre/post selection ledger",
            implementation_note="every scan writes family lineage metadata before scoring; summaries report total tests per family",
            promotion_gate="no demo candidate unless family-adjusted metrics remain acceptable",
        ),
        MultipleTestingRow(
            risk_area="final holdout contamination",
            current_issue="newest 20% holdout has been used repeatedly for kill/keep decisions",
            proposed_control="freeze final holdout for final confirmation; add inner walk-forward for selection",
            implementation_note="create selection window before final holdout; do not tune after final holdout review",
            promotion_gate="candidate must be selected without final holdout and then pass final holdout once",
        ),
        MultipleTestingRow(
            risk_area="visual/top-failed mining",
            current_issue="attractive failed candidates can tempt rule redesign around holdout winners",
            proposed_control="redesign only at family/prior level, not around individual top failed rows",
            implementation_note="record redesign rationale before scan; prevent copying exact holdout-winning parameters",
            promotion_gate="redesigned family must pass walk-forward before final holdout",
        ),
        MultipleTestingRow(
            risk_area="news feature bucket proliferation",
            current_issue="GDELT keyword bucket scores may produce many correlated variants",
            proposed_control="event-study prefilter and hand-labeled class prior before rule search",
            implementation_note="only classes with train/pre-holdout response enter alpha scan",
            promotion_gate="raw news count features cannot be alpha without event-study support",
        ),
    ]


def build_walk_forward_rows() -> List[WalkForwardRow]:
    return [
        WalkForwardRow("WF1", "2022-01 to 2023-03", "2023-04 to 2023-06", "2023-07 to 2023-09", "max_horizon + 1 session", "early regime coverage; no final holdout use"),
        WalkForwardRow("WF2", "2022-04 to 2023-06", "2023-07 to 2023-09", "2023-10 to 2023-12", "max_horizon + 1 session", "rolling selection and validation"),
        WalkForwardRow("WF3", "2022-07 to 2023-09", "2023-10 to 2023-12", "2024-01 to 2024-03", "max_horizon + 1 session", "captures macro/geopolitical shifts"),
        WalkForwardRow("WF4", "2023-01 to 2024-03", "2024-04 to 2024-06", "2024-07 to 2024-09", "max_horizon + 1 session", "pre-2025 selection period"),
        WalkForwardRow("WF5", "2023-07 to 2024-09", "2024-10 to 2024-12", "2025-01 to 2025-04", "max_horizon + 1 session", "pre-final-holdout stress"),
        WalkForwardRow("FINAL_LOCKED", "selected without final holdout", "none", "2025-08-13 onward", "no tuning after review", "final confirmation only; not a search set"),
    ]


def write_csv(path: Path, rows: Iterable[Any]) -> None:
    rows = list(rows)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    dicts = [asdict(r) for r in rows]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(dicts[0].keys()))
        writer.writeheader()
        writer.writerows(dicts)


def write_decision_md(path: Path, summary: Dict[str, Any], contract_rows: List[AsofRow], validation_rows: List[ValidationRow]) -> None:
    blocking = [r for r in contract_rows if r.blocking_issue and r.historical_asof_status.startswith(("LOW", "MEDIUM_LOW"))]
    lines = [
        "# Stage170B Data As-Of Contract and Validation Redesign",
        "",
        f"Generated UTC: `{summary['generated_utc']}`",
        "",
        f"Decision: `{summary['decision']}`",
        f"Recommended action: `{summary['recommended_action']}`",
        "",
        "## Scope",
        "",
        "This is a read-only governance/design stage. It does not create trading candidates, does not write MT5 execution signals, and does not authorize demo/live orders.",
        "",
        "## Core conclusion",
        "",
        "New alpha discovery should remain frozen until the project enforces source-level as-of contracts and adds a validation layer that controls lookahead, path-label quality, walk-forward robustness and multiple testing.",
        "",
        "## Contract status",
        "",
        f"Contract rows: `{len(contract_rows)}`",
        f"Blocking or low-confidence rows: `{len(blocking)}`",
        "",
        "| source_id | historical_asof_status | blocking_issue | owner_action |",
        "|---|---:|---|---|",
    ]
    for row in contract_rows:
        lines.append(f"| {row.source_id} | {row.historical_asof_status} | {row.blocking_issue} | {row.owner_action} |")
    lines += [
        "",
        "## Validation redesign layers",
        "",
        "| layer | required_before | output_artifact | pass_fail_rule |",
        "|---|---|---|---|",
    ]
    for row in validation_rows:
        lines.append(f"| {row.validation_layer} | {row.required_before} | {row.output_artifact} | {row.pass_fail_rule} |")
    lines += [
        "",
        "## Next",
        "",
        "1. Review and edit `stage170b_data_asof_contract.csv` to replace assumptions with explicit source-specific availability times.",
        "2. Build loader-level tests that enforce the contract before any scan can run.",
        "3. Build the purged walk-forward and multiple-testing control framework before any candidate promotion.",
        "4. Keep GDELT/news as current-event guard unless a hand-labeled event-study dataset is created and passes pre-scan diagnostics.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=STAGE)
    parser.add_argument("--root", required=True)
    parser.add_argument("--bars-m5", required=True)
    parser.add_argument("--event-panel", required=False, default=None)
    parser.add_argument("--macro-panel", required=False, default=None)
    parser.add_argument("--stage170a-summary", required=False, default=None)
    parser.add_argument("--event-inbox", required=False, default=None)
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser()
    report_dir = root / "reports" / REPORT_DIR
    report_dir.mkdir(parents=True, exist_ok=True)

    inspections = {
        "bars_m5": inspect_csv(Path(args.bars_m5).expanduser()),
        "event_panel": inspect_csv(Path(args.event_panel).expanduser()) if args.event_panel else {"provided": False, "exists": False},
        "macro_panel": inspect_csv(Path(args.macro_panel).expanduser()) if args.macro_panel else {"provided": False, "exists": False},
        "stage170a_summary": {},
    }
    if args.stage170a_summary:
        sp = Path(args.stage170a_summary).expanduser()
        inspections["stage170a_summary"] = {"provided": True, "path": str(sp), "exists": sp.exists()}
        if sp.exists():
            try:
                inspections["stage170a_summary"].update(json.loads(sp.read_text(encoding="utf-8")))
            except Exception as exc:  # noqa: BLE001
                inspections["stage170a_summary"].update({"read_error": f"{type(exc).__name__}: {exc}"})
    else:
        inspections["stage170a_summary"] = {"provided": False, "exists": False}

    contract_rows = build_contract_rows(args, inspections)
    validation_rows = build_validation_rows()
    multiple_testing_rows = build_multiple_testing_rows()
    walk_forward_rows = build_walk_forward_rows()

    data_contract_csv = report_dir / "stage170b_data_asof_contract.csv"
    validation_csv = report_dir / "stage170b_validation_redesign_matrix.csv"
    mt_csv = report_dir / "stage170b_multiple_testing_control_plan.csv"
    wf_csv = report_dir / "stage170b_purged_walk_forward_plan.csv"
    decision_md = report_dir / "stage170b_decision.md"
    summary_json = report_dir / "stage170b_data_asof_contract_summary.json"

    write_csv(data_contract_csv, contract_rows)
    write_csv(validation_csv, validation_rows)
    write_csv(mt_csv, multiple_testing_rows)
    write_csv(wf_csv, walk_forward_rows)

    blocking_count = sum(1 for r in contract_rows if r.historical_asof_status.startswith(("LOW", "MEDIUM_LOW")))
    summary = {
        "stage": STAGE,
        "generated_utc": utc_now_iso(),
        "root": str(root),
        "order_routing_allowed": ORDER_ROUTING_ALLOWED,
        "demo_release_allowed": DEMO_RELEASE_ALLOWED,
        "status": "STAGE170B_COMPLETE_DATA_ASOF_CONTRACT_READY",
        "decision": "STAGE170B_DATA_CONTRACT_REQUIRED_BEFORE_NEW_DISCOVERY",
        "severity": "HIGH",
        "recommended_action": "FREEZE_NEW_DISCOVERY; ENFORCE_ASOF_CONTRACT; BUILD_VALIDATION_FRAMEWORK",
        "inputs": {
            "bars_m5": str(Path(args.bars_m5).expanduser()),
            "event_panel": str(Path(args.event_panel).expanduser()) if args.event_panel else None,
            "macro_panel": str(Path(args.macro_panel).expanduser()) if args.macro_panel else None,
            "stage170a_summary": str(Path(args.stage170a_summary).expanduser()) if args.stage170a_summary else None,
            "event_inbox": str(Path(args.event_inbox).expanduser()) if args.event_inbox else None,
        },
        "inspections": inspections,
        "contract_counts": {
            "contract_rows": len(contract_rows),
            "low_or_medium_low_asof_rows": blocking_count,
            "validation_layers": len(validation_rows),
            "multiple_testing_controls": len(multiple_testing_rows),
            "walk_forward_rows": len(walk_forward_rows),
        },
        "methodology_gate": {
            "new_discovery_allowed": False,
            "commercial_promotion_allowed": False,
            "news_alpha_allowed": False,
            "news_guard_allowed": True,
            "next_required_stage": "Stage170C_ASOF_JOIN_ENFORCEMENT_AND_PURGED_WALK_FORWARD_FRAMEWORK",
        },
        "outputs": {
            "summary_json": str(summary_json),
            "decision_md": str(decision_md),
            "data_asof_contract_csv": str(data_contract_csv),
            "validation_redesign_matrix_csv": str(validation_csv),
            "multiple_testing_control_plan_csv": str(mt_csv),
            "purged_walk_forward_plan_csv": str(wf_csv),
        },
        "next": [
            "Review and edit data_asof_contract.csv assumptions.",
            "Build automated loader tests that fail scans if source availability policy is missing.",
            "Build purged walk-forward, path-aware label and multiple-testing framework before new discovery.",
            "Do not run Stage170 discovery until this contract is accepted and enforced.",
        ],
    }

    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_decision_md(decision_md, summary, contract_rows, validation_rows)

    print(json.dumps({"status": summary["status"], "decision": summary["decision"], "outputs": summary["outputs"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
