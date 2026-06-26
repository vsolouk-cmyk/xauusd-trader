#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def read_csv_header_and_count(path: Path) -> Tuple[List[str], int]:
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return [], 0
        n = sum(1 for _ in reader)
    return header, n


def rel(root: Path, p: str | Path) -> Path:
    q = Path(p)
    if q.is_absolute():
        return q
    return root / q


def build_hypotheses(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    scope_id = cfg["reduced_scope_id"]
    horizons = ";".join(str(x) for x in cfg["validation_design"]["forward_horizons_days"])
    return [
        {
            "hypothesis_id": "H64G_B0_ALWAYS_LONG_REFERENCE",
            "scope_id": scope_id,
            "role": "benchmark_not_candidate",
            "side": "long_only",
            "entry_policy": "hold gold proxy unconditionally on all eligible feature dates",
            "flat_policy": "none",
            "feature_dependencies": "gold_proxy_close_only_for_return_measurement_later",
            "forward_horizons_days": horizons,
            "primary_metric": "mean_net_bps_vs_zero_and_drawdown_reference",
            "selection_rule": "not selectable; benchmark only",
            "kill_rule": "not applicable",
        },
        {
            "hypothesis_id": "H64G_B1_GOLD_TREND_ONLY_REFERENCE",
            "scope_id": scope_id,
            "role": "benchmark_not_candidate",
            "side": "long_only_when_trend_positive_else_flat",
            "entry_policy": "gold_sma20_over_50 > 0 and gold_sma50_over_200 > 0",
            "flat_policy": "flat otherwise",
            "feature_dependencies": "gold_sma20_over_50;gold_sma50_over_200",
            "forward_horizons_days": horizons,
            "primary_metric": "excess_mean_net_bps_vs_always_long_reference",
            "selection_rule": "not selectable; trend benchmark only",
            "kill_rule": "if inferior to always-long in most splits, later macro candidates must still beat always-long",
        },
        {
            "hypothesis_id": "H64G_H1_MACRO_TAILWIND_TREND_LONG",
            "scope_id": scope_id,
            "role": "primary_candidate",
            "side": "long_only_when_macro_tailwind_and_gold_trend_positive_else_flat",
            "entry_policy": "gold_sma20_over_50 > 0 and gold_sma50_over_200 > 0 and dxy_ret_20d < 0 and real_yield_change_20d < 0",
            "flat_policy": "flat otherwise; no shorting in reduced scope",
            "feature_dependencies": "gold_sma20_over_50;gold_sma50_over_200;dxy_ret_20d;real_yield_change_20d",
            "forward_horizons_days": horizons,
            "primary_metric": "excess_mean_net_bps_vs_always_long_and_trend_only",
            "selection_rule": "candidate can pass only if it beats both benchmarks after fixed costs in >=3 of 4 splits and overall",
            "kill_rule": "kill if underperforms always-long overall or has negative mean in >=2 splits",
        },
        {
            "hypothesis_id": "H64G_H2_HEADWIND_AVOID_LONG_FILTER",
            "scope_id": scope_id,
            "role": "secondary_candidate",
            "side": "long_filter_only",
            "entry_policy": "allow trend-long only when not(dxy_ret_20d > 0 and real_yield_change_20d > 0)",
            "flat_policy": "flat in USD/yield headwind; no shorting in reduced scope",
            "feature_dependencies": "gold_sma20_over_50;gold_sma50_over_200;dxy_ret_20d;real_yield_change_20d",
            "forward_horizons_days": horizons,
            "primary_metric": "drawdown_reduction_and_excess_mean_vs_trend_only",
            "selection_rule": "candidate can pass only if it improves drawdown proxy without reducing mean in >=3 of 4 splits",
            "kill_rule": "kill if it merely reduces frequency without improving risk-adjusted return",
        },
        {
            "hypothesis_id": "H64G_H3_VOL_SHOCK_SUPPRESSED_MACRO_LONG",
            "scope_id": scope_id,
            "role": "tertiary_candidate",
            "side": "long_only_when_macro_tailwind_gold_trend_and_no_vix_shock_else_flat",
            "entry_policy": "H1 condition and vix_change_20d <= 0 and vix_sma20_over_50 <= 0",
            "flat_policy": "flat during rising VIX/vol-shock regime; no shorting in reduced scope",
            "feature_dependencies": "gold_sma20_over_50;gold_sma50_over_200;dxy_ret_20d;real_yield_change_20d;vix_change_20d;vix_sma20_over_50",
            "forward_horizons_days": horizons,
            "primary_metric": "excess_mean_and_drawdown_reduction_vs_H1",
            "selection_rule": "candidate can pass only if it improves both overall drawdown proxy and at least 3/4 split stability versus H1",
            "kill_rule": "kill if it creates concentration or unstable improvement in only one split",
        },
    ]


def build_split_design(cfg: Dict[str, Any], stage64f_summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    by_id = {r.get("split_id"): r for r in stage64f_summary.get("split_coverage", [])}
    rows: List[Dict[str, Any]] = []
    for s in cfg["validation_design"]["splits"]:
        f = by_id.get(s["split_id"], {})
        rows.append({
            "split_id": s["split_id"],
            "start": s["start"],
            "end": s["end"],
            "role": s["role"],
            "stage64f_rows": f.get("row_count"),
            "stage64f_ready": f.get("ready"),
            "minimum_rows": s.get("minimum_rows"),
            "design_note": s.get("design_note", ""),
        })
    return rows


def build_feature_contract(required_features: List[str]) -> List[Dict[str, Any]]:
    roles = {
        "gold_ret_20d": "gold_momentum_context_only_not_target",
        "gold_sma20_over_50": "gold_short_medium_trend_state",
        "gold_sma50_over_200": "gold_medium_long_trend_state",
        "gold_atr14_proxy_pct": "gold_realized_volatility_context",
        "dxy_ret_20d": "usd_pressure_momentum",
        "dxy_sma20_over_50": "usd_pressure_trend_state",
        "real_yield_change_20d": "opportunity_cost_pressure_delta",
        "vix_change_20d": "cross_asset_volatility_delta",
        "vix_sma20_over_50": "volatility_regime_state",
    }
    return [
        {
            "feature_column": col,
            "role": roles.get(col, "reduced_scope_feature"),
            "lag_policy": "asof_join_available_after_utc_lte_gold_available_after_utc",
            "allowed_in_stage64h": True,
            "may_define_target": False,
        }
        for col in required_features
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage64G walk-forward validation design only; no scan.")
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage64g_walk_forward_validation_design.json")
    ap.add_argument("--out", default="reports/stage64g_walk_forward_validation_design")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cfg_path = rel(root, args.config)
    out_dir = rel(root, args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = load_json(cfg_path)
    generated_utc = utc_now()

    stage64f_summary_path = rel(root, cfg["inputs"]["stage64f_summary"])
    stage64f_summary = load_json(stage64f_summary_path)

    dataset_path = Path(stage64f_summary.get("dataset_stats", {}).get("normalized_output") or rel(root, cfg["inputs"]["feature_dataset"]))
    if not dataset_path.is_absolute():
        dataset_path = root / dataset_path

    dataset_exists = dataset_path.exists()
    dataset_header: List[str] = []
    dataset_rows = 0
    if dataset_exists:
        dataset_header, dataset_rows = read_csv_header_and_count(dataset_path)

    required_features = cfg["validation_design"]["required_feature_columns"]
    forbidden_markers = cfg["safety"]["forbidden_column_markers"]
    missing_required_features = [c for c in required_features if c not in dataset_header]
    forbidden_columns = [c for c in dataset_header if any(m.lower() in c.lower() for m in forbidden_markers)]

    split_design = build_split_design(cfg, stage64f_summary)
    all_splits_ready = all(bool(r.get("stage64f_ready")) and int(r.get("stage64f_rows") or 0) >= int(r.get("minimum_rows") or 0) for r in split_design)

    stage64f_passed = stage64f_summary.get("decision") == "LAG_SAFE_FEATURE_DATASET_PREFLIGHT_PASS_STAGE64G_DESIGN_ALLOWED_NO_VALIDATION"
    dataset_ok = dataset_exists and dataset_rows >= cfg["validation_design"]["minimum_dataset_rows"] and not missing_required_features and not forbidden_columns and all_splits_ready

    candidate_count = 3
    horizon_count = len(cfg["validation_design"]["forward_horizons_days"])
    effective_test_count = candidate_count * horizon_count

    decision = "WALK_FORWARD_VALIDATION_DESIGN_COMPLETE_STAGE64H_ALLOWED_NO_ORDER" if (stage64f_passed and dataset_ok) else "BLOCK_STAGE64H_UNTIL_DATASET_OR_DESIGN_ISSUES_FIXED_NO_ORDER"

    hypotheses = build_hypotheses(cfg)
    feature_contract = build_feature_contract(required_features)

    protocol = {
        "design_mode": "fixed_hypotheses_no_parameter_search",
        "scope_id": cfg["reduced_scope_id"],
        "validation_not_run_in_stage64g": True,
        "candidate_hypotheses_for_correction": candidate_count,
        "benchmark_hypotheses_excluded_from_correction": 2,
        "forward_horizons_days": cfg["validation_design"]["forward_horizons_days"],
        "effective_test_count_for_initial_familywise_correction": effective_test_count,
        "multiple_testing_rule": "Bonferroni over candidate_hypotheses * forward_horizons; benchmarks are not selectable candidates.",
        "execution_assumption": cfg["validation_design"]["execution_assumption"],
        "cost_assumption_bps": cfg["validation_design"]["cost_assumption_bps"],
        "pass_criteria": cfg["validation_design"]["pass_criteria"],
        "kill_criteria": cfg["validation_design"]["kill_criteria"],
        "blocked_claims": cfg["safety"]["blocked_claims"],
    }

    summary = {
        "stage": "Stage64G_WALK_FORWARD_VALIDATION_DESIGN_NO_SCAN",
        "status": "WALK_FORWARD_VALIDATION_DESIGN_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_order": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "validation_allowed_in_stage64g": False,
        "stage64h_allowed_by_design": bool(stage64f_passed and dataset_ok),
        "generated_utc": generated_utc,
        "root": str(root),
        "inputs": {
            "config": str(cfg_path),
            "stage64f_summary": str(stage64f_summary_path),
            "feature_dataset": str(dataset_path),
        },
        "dataset_design_checks": {
            "stage64f_passed": stage64f_passed,
            "dataset_exists": dataset_exists,
            "dataset_rows": dataset_rows,
            "minimum_dataset_rows": cfg["validation_design"]["minimum_dataset_rows"],
            "missing_required_features": missing_required_features,
            "forbidden_columns": forbidden_columns,
            "all_splits_ready": all_splits_ready,
            "dataset_ok_for_stage64h_design": dataset_ok,
        },
        "hypothesis_design": {
            "total_rows": len(hypotheses),
            "candidate_hypotheses": candidate_count,
            "benchmark_hypotheses": 2,
            "horizons": cfg["validation_design"]["forward_horizons_days"],
            "effective_test_count": effective_test_count,
        },
        "source_warnings": stage64f_summary.get("source_warnings", []),
        "next_allowed_step": "Stage64H_REDUCED_SCOPE_WALK_FORWARD_VALIDATION_RUN_NO_ORDER" if (stage64f_passed and dataset_ok) else "FIX_STAGE64F_OR_STAGE64G_INPUTS_NO_VALIDATION",
        "hard_blocks": [
            "NO_PAPER_ORDER",
            "NO_EA_PROMOTION",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_VALIDATION_SCAN_IN_STAGE64G",
            "NO_FULL_SCOPE_VALIDATION_CLAIM",
            "NO_PARAMETER_SEARCH_OR_POST_HOC_FILTER_RESCUE",
        ],
        "outputs": {
            "summary_json": str(out_dir / "stage64g_walk_forward_validation_design_summary.json"),
            "report_md": str(out_dir / "stage64g_walk_forward_validation_design_report.md"),
            "hypotheses_csv": str(out_dir / "stage64g_predeclared_hypotheses.csv"),
            "hypotheses_json": str(out_dir / "stage64g_predeclared_hypotheses.json"),
            "split_design_csv": str(out_dir / "stage64g_walk_forward_split_design.csv"),
            "split_design_json": str(out_dir / "stage64g_walk_forward_split_design.json"),
            "feature_contract_csv": str(out_dir / "stage64g_feature_to_rule_contract.csv"),
            "feature_contract_json": str(out_dir / "stage64g_feature_to_rule_contract.json"),
            "validation_protocol_json": str(out_dir / "stage64g_validation_protocol.json"),
        },
    }

    write_csv(out_dir / "stage64g_predeclared_hypotheses.csv", hypotheses, [
        "hypothesis_id", "scope_id", "role", "side", "entry_policy", "flat_policy", "feature_dependencies", "forward_horizons_days", "primary_metric", "selection_rule", "kill_rule"
    ])
    write_json(out_dir / "stage64g_predeclared_hypotheses.json", hypotheses)

    write_csv(out_dir / "stage64g_walk_forward_split_design.csv", split_design, [
        "split_id", "start", "end", "role", "stage64f_rows", "stage64f_ready", "minimum_rows", "design_note"
    ])
    write_json(out_dir / "stage64g_walk_forward_split_design.json", split_design)

    write_csv(out_dir / "stage64g_feature_to_rule_contract.csv", feature_contract, [
        "feature_column", "role", "lag_policy", "allowed_in_stage64h", "may_define_target"
    ])
    write_json(out_dir / "stage64g_feature_to_rule_contract.json", feature_contract)
    write_json(out_dir / "stage64g_validation_protocol.json", protocol)
    write_json(out_dir / "stage64g_walk_forward_validation_design_summary.json", summary)

    report = out_dir / "stage64g_walk_forward_validation_design_report.md"
    with report.open("w", encoding="utf-8") as f:
        f.write("# Stage64G - Walk-Forward Validation Design (No Scan)\n\n")
        f.write(f"Generated UTC: `{generated_utc}`\n\n")
        f.write("## Status\n\n")
        f.write("- status: `WALK_FORWARD_VALIDATION_DESIGN_COMPLETE_NO_PROMOTION`\n")
        f.write(f"- decision: `{decision}`\n")
        f.write("- validation_allowed_in_stage64g: `false`\n")
        f.write("- promotion/paper/live: `NO_GO`\n\n")
        f.write("## Executive conclusion\n\n")
        f.write("Stage64G predeclares the reduced-scope P0+VIX walk-forward validation design. It does not run a validation scan, does not build targets, does not generate signals, and does not authorize any order path.\n\n")
        f.write("## Dataset design checks\n\n")
        for k, v in summary["dataset_design_checks"].items():
            f.write(f"- {k}: `{v}`\n")
        f.write("\n## Hypothesis design\n\n")
        f.write(f"- candidate hypotheses: `{candidate_count}`\n")
        f.write("- benchmark hypotheses: `2`\n")
        f.write(f"- horizons: `{cfg['validation_design']['forward_horizons_days']}`\n")
        f.write(f"- effective test count: `{effective_test_count}`\n")
        f.write("- multiple-testing rule: `Bonferroni over candidate_hypotheses * forward_horizons`\n\n")
        f.write("## Predeclared hypotheses\n\n")
        f.write("| hypothesis_id | role | side | entry_policy |\n")
        f.write("|---|---|---|---|\n")
        for h in hypotheses:
            f.write(f"| `{h['hypothesis_id']}` | {h['role']} | {h['side']} | {h['entry_policy']} |\n")
        f.write("\n## Split design\n\n")
        f.write("| split_id | start | end | role | stage64f_rows | ready |\n")
        f.write("|---|---|---|---|---:|---:|\n")
        for s in split_design:
            f.write(f"| `{s['split_id']}` | {s['start']} | {s['end']} | {s['role']} | {s['stage64f_rows']} | {s['stage64f_ready']} |\n")
        f.write("\n## Source warnings\n\n")
        for w in summary.get("source_warnings", []):
            f.write(f"- {w}\n")
        f.write("\n## Operational decision\n\n")
        f.write("No historical validation scan, signal generation, paper-order, paper-live, live, EA promotion, or broker connection is authorized by Stage64G.\n\n")
        f.write("## Next allowed step\n\n")
        f.write(f"`{summary['next_allowed_step']}`\n")

    return 0 if stage64f_passed and dataset_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
