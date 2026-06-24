#!/usr/bin/env python3
"""
Stage45B3 external context baseline design precheck.

Purpose:
- Consume Stage45B2 and Stage45B2A audit/repair summaries.
- Decide whether external context is usable for a predefined baseline-design stage.
- Detect design-level blockers such as overly broad news blackout coverage before
  any new baseline scan is allowed.

This script is a precheck only. It does not create signals, shortlist candidates,
rescue archived rows, or authorize EA/paper/live/live.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

STAGE = "Stage45B3_EXTERNAL_CONTEXT_BASELINE_DESIGN_PRECHECK"
NO_GO = "NO_GO"


def json_default(obj: Any) -> Any:
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        val = float(obj)
        return None if math.isnan(val) else val
    if isinstance(obj, (Path,)):
        return str(obj)
    return str(obj)


def read_json(path: Path) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    meta = {"path": str(path), "exists": path.exists(), "error": None}
    if not path.exists():
        meta["error"] = "missing"
        return None, meta
    try:
        return json.loads(path.read_text(encoding="utf-8")), meta
    except Exception as exc:  # pragma: no cover - defensive for corrupted reports
        meta["error"] = f"json_parse_error: {exc}"
        return None, meta


def pct(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        x = float(v)
        if math.isnan(x):
            return None
        return x
    except Exception:
        return None


def pass_fail(value: Optional[float], threshold: float, op: str) -> bool:
    if value is None:
        return False
    if op == ">=":
        return value >= threshold
    if op == "<=":
        return value <= threshold
    if op == ">":
        return value > threshold
    if op == "<":
        return value < threshold
    raise ValueError(f"unsupported op: {op}")


def get_nested(obj: Dict[str, Any], path: List[str], default: Any = None) -> Any:
    cur: Any = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def metric_row(area: str, metric: str, value: Any, op: str, threshold: Any, ok: bool, severity: str, note: str) -> Dict[str, Any]:
    return {
        "area": area,
        "metric": metric,
        "value": value,
        "operator": op,
        "threshold": threshold,
        "ok": bool(ok),
        "severity": severity,
        "note": note,
    }


def build_precheck_matrix(stage45b2: Optional[Dict[str, Any]], stage45b2a: Optional[Dict[str, Any]], args: argparse.Namespace) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    rows: List[Dict[str, Any]] = []
    blockers: List[str] = []
    warnings: List[str] = []

    b2_decision = get_nested(stage45b2 or {}, ["decision", "status"])
    b2a_decision = get_nested(stage45b2a or {}, ["decision", "status"])

    rows.append(metric_row(
        "stage_chain", "stage45b2a_status", b2a_decision, "==",
        "EXTERNAL_CONTEXT_ALIGNMENT_REPAIR_READY_NO_PROMOTION",
        b2a_decision == "EXTERNAL_CONTEXT_ALIGNMENT_REPAIR_READY_NO_PROMOTION",
        "blocker", "Stage45B2A must repair alignment before design precheck can pass.",
    ))
    if b2a_decision != "EXTERNAL_CONTEXT_ALIGNMENT_REPAIR_READY_NO_PROMOTION":
        blockers.append("stage45b2a_not_ready")

    p0_keys = get_nested(stage45b2 or {}, ["p0_schema_ok_keys"], []) or []
    required = {"dxy", "us10y_yield", "cme_gc_reference", "news_calendar"}
    p0_ok = required.issubset(set(p0_keys))
    rows.append(metric_row(
        "p0", "required_external_context_schema_ready", sorted(p0_keys), "superset",
        sorted(required), p0_ok, "blocker", "DXY, US10Y, CME reference, and news calendar must all be schema-valid.",
    ))
    if not p0_ok:
        blockers.append("p0_schema_not_ready")

    for key in ["dxy", "us10y_yield", "real_yield_optional"]:
        cov = get_nested(stage45b2 or {}, ["context_coverage", key, "safe_lag_coverage_pct"])
        cov_f = pct(cov)
        ok = pass_fail(cov_f, args.min_daily_safe_lag_coverage_pct, ">=")
        rows.append(metric_row(
            "daily_context", f"{key}_safe_lag_coverage_pct", cov_f, ">=", args.min_daily_safe_lag_coverage_pct,
            ok, "blocker" if key in ("dxy", "us10y_yield") else "warning",
            "Daily context must be forward-filled only after safe lag; optional real yield is useful but not mandatory.",
        ))
        if key in ("dxy", "us10y_yield") and not ok:
            blockers.append(f"{key}_safe_lag_coverage_too_low")
        elif key == "real_yield_optional" and not ok:
            warnings.append("optional_real_yield_safe_lag_coverage_low_or_missing")

    cme_overlap = pct(get_nested(stage45b2 or {}, ["cme_reference_alignment", "overlap_pct_of_bar_days"]))
    cme_corr = pct(get_nested(stage45b2 or {}, ["cme_reference_alignment", "return_corr"]))
    cme_sign = pct(get_nested(stage45b2 or {}, ["cme_reference_alignment", "return_sign_agreement_pct"]))
    for metric, value, threshold, blocker_name in [
        ("cme_overlap_pct_of_bar_days", cme_overlap, args.min_cme_overlap_pct, "cme_overlap_too_low"),
        ("cme_return_corr", cme_corr, args.min_cme_return_corr, "cme_return_corr_too_low"),
        ("cme_return_sign_agreement_pct", cme_sign, args.min_cme_sign_agreement_pct, "cme_sign_agreement_too_low"),
    ]:
        ok = pass_fail(value, threshold, ">=")
        rows.append(metric_row(
            "cme_reference", metric, value, ">=", threshold, ok, "blocker",
            "CME/Yahoo GC reference must be aligned enough to support reference-feed sanity checks.",
        ))
        if not ok:
            blockers.append(blocker_name)

    selected_variant = get_nested(stage45b2a or {}, ["selected_blackout_variant"])
    selected_bars = pct(get_nested(stage45b2a or {}, ["selected_bars_in_blackout"]))
    loaded_rows = pct(get_nested(stage45b2a or {}, ["bar_load_meta", "loaded_rows"]))
    selected_pct = None if selected_bars is None or loaded_rows in (None, 0) else selected_bars / loaded_rows
    if selected_pct is None:
        selected_pct = pct(get_nested(stage45b2a or {}, ["blackout_repair_profiles", str(selected_variant), "bars_in_blackout_pct"]))
        if selected_pct is not None and selected_pct > 1.0:
            selected_pct = selected_pct / 100.0

    rows.append(metric_row(
        "news_blackout", "selected_blackout_variant", selected_variant, "in", "macro_usd_or_unknown|macro_semantic_only",
        selected_variant in ("macro_usd_or_unknown", "macro_semantic_only"), "warning",
        "Use a macro-focused variant rather than all news/generic gold news.",
    ))
    if selected_variant not in ("macro_usd_or_unknown", "macro_semantic_only"):
        warnings.append("selected_blackout_variant_not_macro_focused")

    min_ok = pass_fail(selected_pct, args.min_selected_blackout_pct, ">=")
    max_ok = pass_fail(selected_pct, args.max_selected_blackout_pct, "<=")
    rows.append(metric_row(
        "news_blackout", "selected_blackout_coverage_pct", selected_pct, ">=", args.min_selected_blackout_pct,
        min_ok, "blocker", "Blackout must cover at least a small non-zero share of bars.",
    ))
    rows.append(metric_row(
        "news_blackout", "selected_blackout_coverage_pct", selected_pct, "<=", args.max_selected_blackout_pct,
        max_ok, "blocker", "If blackout removes too many bars, the calendar is not suitable for baseline design.",
    ))
    if not min_ok:
        blockers.append("news_blackout_coverage_zero_or_too_low")
    if not max_ok:
        blockers.append("news_blackout_coverage_too_broad")

    category_counts = get_nested(stage45b2 or {}, ["news_calendar_alignment", "event_category_counts_top20"], []) or []
    top_categories = [str(x.get("category", "")) for x in category_counts[:8] if isinstance(x, dict)]
    numeric_shock_like = any("shock" in c.lower() for c in top_categories)
    source_counts = get_nested(stage45b2 or {}, ["news_calendar_alignment", "event_source_counts_top20"], []) or []
    top_sources = [str(x.get("source", "")) for x in source_counts[:8] if isinstance(x, dict)]
    fred_backfill_like = any("fred_numeric_backfill" in s.lower() for s in top_sources)
    mixed_semantics = numeric_shock_like or fred_backfill_like or "news_calendar_contains_mixed_semantics_review_recommended" in get_nested(stage45b2a or {}, ["decision", "warnings"], [])
    rows.append(metric_row(
        "news_semantics", "mixed_numeric_backfill_or_shock_semantics", mixed_semantics, "==", False,
        not mixed_semantics, "warning", "Numeric-shock backfills are useful context but too broad for scheduled macro blackout.",
    ))
    if mixed_semantics:
        warnings.append("news_calendar_mixed_semantics_review_required")

    return rows, sorted(set(blockers)), sorted(set(warnings))


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys: List[str] = []
        for row in rows:
            for key in row.keys():
                if key not in keys:
                    keys.append(key)
        fieldnames = keys
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def feature_contract_rows(stage45b2: Optional[Dict[str, Any]], stage45b2a: Optional[Dict[str, Any]], max_blackout_pct: float) -> List[Dict[str, Any]]:
    dxy_cov = get_nested(stage45b2 or {}, ["context_coverage", "dxy", "safe_lag_coverage_pct"])
    us10y_cov = get_nested(stage45b2 or {}, ["context_coverage", "us10y_yield", "safe_lag_coverage_pct"])
    real_cov = get_nested(stage45b2 or {}, ["context_coverage", "real_yield_optional", "safe_lag_coverage_pct"])
    cme_corr = get_nested(stage45b2 or {}, ["cme_reference_alignment", "return_corr"])
    selected_variant = get_nested(stage45b2a or {}, ["selected_blackout_variant"])
    selected_pct = get_nested(stage45b2a or {}, ["blackout_repair_profiles", str(selected_variant), "bars_in_blackout_pct"])
    if selected_pct is not None and float(selected_pct) > 1:
        selected_pct = float(selected_pct) / 100.0

    return [
        {
            "feature_group": "daily_macro_context",
            "candidate_features": "dxy_close_lag1,dxy_ret_1d_lag1,dxy_slope_5d_lag1",
            "input_file": "data/external/dxy.csv",
            "alignment_rule": "daily_safe_lag_1d_forward_fill",
            "readiness": "READY" if pct(dxy_cov) is not None and pct(dxy_cov) >= 0.95 else "BLOCKED",
            "reason": f"safe_lag_coverage={dxy_cov}",
        },
        {
            "feature_group": "nominal_yield_context",
            "candidate_features": "us10y_yield_lag1,us10y_delta_1d_lag1,us10y_slope_5d_lag1",
            "input_file": "data/external/us10y_yield.csv",
            "alignment_rule": "daily_safe_lag_1d_forward_fill",
            "readiness": "READY" if pct(us10y_cov) is not None and pct(us10y_cov) >= 0.95 else "BLOCKED",
            "reason": f"safe_lag_coverage={us10y_cov}",
        },
        {
            "feature_group": "real_yield_context_optional",
            "candidate_features": "real_yield_lag1,real_yield_delta_1d_lag1",
            "input_file": "data/external/real_yield.csv",
            "alignment_rule": "daily_safe_lag_1d_forward_fill",
            "readiness": "READY_OPTIONAL" if pct(real_cov) is not None and pct(real_cov) >= 0.95 else "OPTIONAL_MISSING_OR_WEAK",
            "reason": f"safe_lag_coverage={real_cov}",
        },
        {
            "feature_group": "reference_feed_sanity",
            "candidate_features": "mt5_vs_gc_return_sign_agreement,gc_ret_1d_reference,gc_gap_reference",
            "input_file": "data/reference/cme_gc.csv",
            "alignment_rule": "daily_reference_overlap_only_not_execution_grade",
            "readiness": "READY_REFERENCE_ONLY" if pct(cme_corr) is not None and pct(cme_corr) >= 0.65 else "BLOCKED",
            "reason": f"return_corr={cme_corr}; source must stay reference_only",
        },
        {
            "feature_group": "news_blackout",
            "candidate_features": "is_news_blackout,minutes_to_event,event_category",
            "input_file": "data/external/news_blackout_windows.csv",
            "alignment_rule": "interval_overlap_utc_predefined_window",
            "readiness": "BLOCKED_TOO_BROAD" if pct(selected_pct) is None or pct(selected_pct) > max_blackout_pct else "READY",
            "reason": f"selected_variant={selected_variant}; selected_blackout_pct={selected_pct}; max_allowed={max_blackout_pct}",
        },
    ]


def news_quality_rows(stage45b2: Optional[Dict[str, Any]], stage45b2a: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    alignment = get_nested(stage45b2 or {}, ["news_calendar_alignment"], {}) or {}
    rows.append({
        "metric": "schema_ok",
        "value": alignment.get("schema_ok"),
        "interpretation": "Schema is sufficient for parsing, but not enough for strategy design.",
    })
    rows.append({
        "metric": "row_count",
        "value": alignment.get("row_count"),
        "interpretation": "Event count is sufficient, but event semantics must be constrained.",
    })
    rows.append({
        "metric": "selected_variant",
        "value": get_nested(stage45b2a or {}, ["selected_blackout_variant"]),
        "interpretation": "Selected variant should be macro-focused.",
    })
    rows.append({
        "metric": "selected_bars_in_blackout",
        "value": get_nested(stage45b2a or {}, ["selected_bars_in_blackout"]),
        "interpretation": "Too broad if it removes a large share of all M15 bars.",
    })
    for item in alignment.get("event_category_counts_top20", [])[:20]:
        if isinstance(item, dict):
            rows.append({
                "metric": "category_count",
                "value": f"{item.get('category')}={item.get('n')}",
                "interpretation": "Large shock/backfill categories should not automatically be treated as scheduled-news blackout.",
            })
    for item in alignment.get("event_source_counts_top20", [])[:20]:
        if isinstance(item, dict):
            rows.append({
                "metric": "source_count",
                "value": f"{item.get('source')}={item.get('n')}",
                "interpretation": "Backfilled numerical shock sources are useful as context labels, not necessarily event no-trade windows.",
            })
    return rows


def build_summary(repo_root: Path, args: argparse.Namespace) -> Dict[str, Any]:
    outdir = repo_root / args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    b2, b2_meta = read_json(repo_root / args.stage45b2_summary)
    b2a, b2a_meta = read_json(repo_root / args.stage45b2a_summary)

    matrix, blockers, warnings = build_precheck_matrix(b2, b2a, args)
    feature_rows = feature_contract_rows(b2, b2a, args.max_selected_blackout_pct)
    news_rows = news_quality_rows(b2, b2a)

    if blockers:
        status = "EXTERNAL_CONTEXT_BASELINE_DESIGN_PRECHECK_BLOCKED_NO_PROMOTION"
        recommended_next_stage = "Stage45B3A_NEWS_CALENDAR_SEMANTIC_REDUCTION"
    else:
        status = "EXTERNAL_CONTEXT_BASELINE_DESIGN_PRECHECK_READY_NO_PROMOTION"
        recommended_next_stage = "Stage46_EXTERNAL_CONTEXT_BASELINE_SCAN_DESIGN"

    summary: Dict[str, Any] = {
        "stage": STAGE,
        "settings": {
            "repo_root": str(repo_root),
            "stage45b2_summary": args.stage45b2_summary,
            "stage45b2a_summary": args.stage45b2a_summary,
            "outdir": args.outdir,
            "thresholds": {
                "min_daily_safe_lag_coverage_pct": args.min_daily_safe_lag_coverage_pct,
                "min_cme_overlap_pct": args.min_cme_overlap_pct,
                "min_cme_return_corr": args.min_cme_return_corr,
                "min_cme_sign_agreement_pct": args.min_cme_sign_agreement_pct,
                "min_selected_blackout_pct": args.min_selected_blackout_pct,
                "max_selected_blackout_pct": args.max_selected_blackout_pct,
            },
        },
        "stage45b2_reference": {"meta": b2_meta, "status": get_nested(b2 or {}, ["decision", "status"]), "recommended_next_stage": get_nested(b2 or {}, ["decision", "recommended_next_stage"])},
        "stage45b2a_reference": {"meta": b2a_meta, "status": get_nested(b2a or {}, ["decision", "status"]), "recommended_next_stage": get_nested(b2a or {}, ["decision", "recommended_next_stage"])},
        "precheck_matrix": matrix,
        "feature_contract": feature_rows,
        "news_calendar_quality_profile": news_rows,
        "decision": {
            "status": status,
            "promotion": NO_GO,
            "EA": NO_GO,
            "paper_live": NO_GO,
            "live": NO_GO,
            "blockers": blockers,
            "warnings": warnings,
            "recommended_next_stage": recommended_next_stage,
            "rationale": [
                "Stage45B3 is a design precheck only; it does not create signals or scan candidates.",
                "External context may be technically aligned while still being unsuitable for baseline design if blackout semantics are too broad.",
                "If blocked, repair the calendar semantics before any external-context baseline scan design.",
            ],
            "not_allowed": [
                "candidate_rescue_from_stage41_42_43",
                "post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets",
                "EA_paper_live_live_from_archived_rows",
                "ML_before_robust_cost_aware_baseline",
                "new_blind_megascan_before_external_context_baseline_design_precheck_is_clean",
            ],
        },
        "promotion": NO_GO,
        "EA": NO_GO,
        "paper_live": NO_GO,
        "live": NO_GO,
        "next_allowed_step": recommended_next_stage,
    }

    matrix_path = outdir / "stage45b3_design_precheck_matrix.csv"
    feature_path = outdir / "stage45b3_context_feature_contract.csv"
    news_path = outdir / "stage45b3_news_calendar_quality_profile.csv"
    summary_path = outdir / "stage45b3_external_context_baseline_design_precheck_summary.json"
    md_path = outdir / "stage45b3_external_context_baseline_design_precheck.md"

    write_csv(matrix_path, matrix)
    write_csv(feature_path, feature_rows)
    write_csv(news_path, news_rows)
    summary["outputs"] = {
        "summary_json": str(summary_path),
        "markdown": str(md_path),
        "design_precheck_matrix_csv": str(matrix_path),
        "context_feature_contract_csv": str(feature_path),
        "news_calendar_quality_profile_csv": str(news_path),
    }

    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=json_default), encoding="utf-8")
    md_path.write_text(render_markdown(summary), encoding="utf-8")
    return summary


def render_markdown(summary: Dict[str, Any]) -> str:
    decision = summary["decision"]
    lines: List[str] = []
    lines.append(f"# {STAGE}")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    for key in ["promotion", "EA", "paper_live", "live"]:
        lines.append(f"{key} = {summary.get(key)}")
    lines.append(f"status = {decision.get('status')}")
    lines.append(f"recommended_next_stage = {decision.get('recommended_next_stage')}")
    lines.append("```")
    lines.append("")
    lines.append("Stage45B3 is a baseline-design precheck only. It does not create trading signals, shortlist candidates, or promote archived rows.")
    lines.append("")
    lines.append("## Blockers and warnings")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps({"blockers": decision.get("blockers", []), "warnings": decision.get("warnings", [])}, indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")
    lines.append("## Precheck matrix")
    lines.append("")
    lines.append("| area | metric | value | rule | ok | severity |")
    lines.append("| :-- | :-- | :-- | :-- | :-- | :-- |")
    for row in summary.get("precheck_matrix", []):
        value = str(row.get("value", "")).replace("|", "/")
        rule = f"{row.get('operator')} {row.get('threshold')}".replace("|", "/")
        lines.append(f"| {row.get('area')} | {row.get('metric')} | {value} | {rule} | {row.get('ok')} | {row.get('severity')} |")
    lines.append("")
    lines.append("## Feature contract")
    lines.append("")
    lines.append("| feature_group | readiness | alignment_rule | reason |")
    lines.append("| :-- | :-- | :-- | :-- |")
    for row in summary.get("feature_contract", []):
        lines.append(f"| {row.get('feature_group')} | {row.get('readiness')} | {row.get('alignment_rule')} | {str(row.get('reason')).replace('|','/')} |")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    if "news_blackout_coverage_too_broad" in decision.get("blockers", []):
        lines.append("The external context is technically aligned, but the selected news blackout is too broad for baseline design. A blackout that removes most M15 bars would make downstream evidence hard to interpret and could hide overfitting.")
        lines.append("")
        lines.append("The next valid step is to reduce the news calendar to scheduled macro events or construct a separate shock-regime feature instead of treating all numeric shock backfills as no-trade events.")
    else:
        lines.append("The external context passes the design precheck. The next valid step is a predefined external-context baseline scan design, not candidate rescue.")
    lines.append("")
    lines.append("## Not allowed")
    lines.append("")
    for item in decision.get("not_allowed", []):
        lines.append(f"- `{item}`")
    lines.append("")
    lines.append("## Anti-overfit note")
    lines.append("")
    lines.append("Do not use this precheck to rescue Stage41/42/43 rows. If the precheck is blocked, repair the context design first. If it passes, the next step must still be a predefined baseline design.")
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=STAGE)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--stage45b2-summary", default="reports/stage45b2/stage45b2_external_context_alignment_audit_summary.json")
    parser.add_argument("--stage45b2a-summary", default="reports/stage45b2a/stage45b2a_external_context_alignment_repair_summary.json")
    parser.add_argument("--outdir", default="reports/stage45b3")
    parser.add_argument("--min-daily-safe-lag-coverage-pct", type=float, default=0.95)
    parser.add_argument("--min-cme-overlap-pct", type=float, default=0.70)
    parser.add_argument("--min-cme-return-corr", type=float, default=0.65)
    parser.add_argument("--min-cme-sign-agreement-pct", type=float, default=0.60)
    parser.add_argument("--min-selected-blackout-pct", type=float, default=0.001)
    parser.add_argument("--max-selected-blackout-pct", type=float, default=0.25)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).expanduser().resolve()
    summary = build_summary(repo_root, args)
    if args.print_summary:
        print(json.dumps({
            "stage": STAGE,
            "status": summary["decision"]["status"],
            "blockers": summary["decision"].get("blockers", []),
            "warnings": summary["decision"].get("warnings", []),
            "recommended_next_stage": summary["decision"].get("recommended_next_stage"),
            "outputs": summary.get("outputs", {}),
        }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
