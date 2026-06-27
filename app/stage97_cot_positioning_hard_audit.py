#!/usr/bin/env python3
"""
Stage97 COT Hard Audit

Hard-audits Stage96 COT positioning discovery shortlist before any portfolio
observer expansion. This stage is research-only and cannot authorize orders,
broker connection, EA promotion, paper-live, or live trading.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


STAGE = "Stage97_COT_POSITIONING_HARD_AUDIT"
REQUIRED_STAGE96_DECISIONS = {
    "STAGE96_COT_THESIS_SHORTLIST_READY_FOR_HARD_AUDIT_NO_ORDER",
}
REQUIRED_STAGE96_DISPOSITIONS = {
    "COT_THESIS_SHORTLIST_READY_FOR_STAGE97_HARD_AUDIT",
}

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE97",
    "NO_THRESHOLD_TUNING_FROM_STAGE97_HARD_AUDIT",
    "NO_DIRECT_MT5_OR_EA_CHANGE_FROM_STAGE97",
]


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def ensure_out(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)


def resolve_path(root: Path, path_str: str) -> Path:
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        p = root / p
    return p


def finite_float(v: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if v is None:
            return default
        if isinstance(v, str) and v.strip() == "":
            return default
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except Exception:
        return default


def finite_int(v: Any, default: int = 0) -> int:
    x = finite_float(v, None)
    if x is None:
        return default
    return int(round(x))


def normalize_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in {"true", "1", "yes", "y", "pass"}


def load_config(root: Path, config_path: Path) -> Dict[str, Any]:
    cfg = read_json(config_path)
    defaults = {
        "stage96_summary_path": "reports/stage96_cot_positioning_thesis_discovery/stage96_cot_positioning_thesis_discovery_summary.json",
        "stage96_shortlist_path": "reports/stage96_cot_positioning_thesis_discovery/stage96_cot_thesis_shortlist.csv",
        "stage96_metrics_path": "reports/stage96_cot_positioning_thesis_discovery/stage96_cot_candidate_metrics.csv",
        "max_selected_for_stage98": 3,
        "constraints": {
            "min_total_entry_count": 10,
            "min_total_mean_net_bps": 350.0,
            "min_total_median_net_bps": 0.0,
            "min_total_win_rate": 0.60,
            "max_abs_worst_loss_bps": 2200.0,
            "min_validation_entry_count": 2,
            "min_validation_mean_net_bps": 0.0,
            "min_locked_forward_entry_count": 3,
            "min_locked_forward_mean_net_bps": 100.0,
            "min_final_holdout_entry_count": 3,
            "min_final_holdout_mean_net_bps": 1000.0,
            "min_post_asof_entry_count": 2,
            "min_post_asof_mean_net_bps": 1000.0,
            "max_year_entry_share": 0.25,
            "max_missing_required_feature_rows": 0,
            "max_lookahead_violations": 0,
            "min_incremental_union_active_days": 50,
        },
        "selection": {
            "prefer_lower_overlap_after_score": True,
            "max_selected_for_stage98": 3
        }
    }
    merged = defaults
    for k, v in cfg.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k].update(v)
        else:
            merged[k] = v
    return merged


def metric_value(row: pd.Series, col: str, default: Optional[float] = None) -> Optional[float]:
    return finite_float(row[col], default) if col in row.index else default


def metric_int(row: pd.Series, col: str, default: int = 0) -> int:
    return finite_int(row[col], default) if col in row.index else default


def audit_row(row: pd.Series, constraints: Dict[str, Any]) -> Dict[str, Any]:
    fail: List[str] = []

    # Required discovery pass from Stage96
    if "pass_cot_discovery_candidate" in row.index and not normalize_bool(row["pass_cot_discovery_candidate"]):
        fail.append("FAILED_STAGE96_DISCOVERY")

    total_entries = metric_int(row, "total_entry_count")
    total_mean = metric_value(row, "total_mean_net_bps", -10**9)
    total_median = metric_value(row, "total_median_net_bps", -10**9)
    total_win = metric_value(row, "total_win_rate", -10**9)
    worst = metric_value(row, "total_min_net_return_bps", 0.0)
    validation_entries = metric_int(row, "validation_entry_count")
    validation_mean = metric_value(row, "validation_mean_net_bps", -10**9)
    locked_entries = metric_int(row, "locked_forward_entry_count")
    locked_mean = metric_value(row, "locked_forward_mean_net_bps", -10**9)
    final_entries = metric_int(row, "final_holdout_entry_count")
    final_mean = metric_value(row, "final_holdout_mean_net_bps", -10**9)
    post_entries = metric_int(row, "post_asof_entry_count")
    post_mean = metric_value(row, "post_asof_mean_net_bps", -10**9)
    year_share = metric_value(row, "max_year_entry_share", 1.0)
    missing = metric_int(row, "missing_required_feature_rows")
    lookahead = metric_int(row, "lookahead_violations")
    incremental_days = metric_int(row, "incremental_union_active_days")
    overlap = metric_value(row, "overlap_with_current_union_pct", None)

    if total_entries < constraints["min_total_entry_count"]:
        fail.append("TOTAL_ENTRIES_TOO_LOW")
    if total_mean is None or total_mean < constraints["min_total_mean_net_bps"]:
        fail.append("TOTAL_MEAN_TOO_LOW")
    if total_median is None or total_median < constraints["min_total_median_net_bps"]:
        fail.append("TOTAL_MEDIAN_TOO_LOW")
    if total_win is None or total_win < constraints["min_total_win_rate"]:
        fail.append("WIN_RATE_TOO_LOW")
    if worst is not None and worst < -abs(float(constraints["max_abs_worst_loss_bps"])):
        fail.append("WORST_LOSS_TOO_LARGE")
    if validation_entries < constraints["min_validation_entry_count"]:
        fail.append("VALIDATION_ENTRIES_TOO_LOW")
    if validation_mean is None or validation_mean < constraints["min_validation_mean_net_bps"]:
        fail.append("VALIDATION_MEAN_TOO_LOW")
    if locked_entries < constraints["min_locked_forward_entry_count"]:
        fail.append("LOCKED_FORWARD_ENTRIES_TOO_LOW")
    if locked_mean is None or locked_mean < constraints["min_locked_forward_mean_net_bps"]:
        fail.append("LOCKED_FORWARD_MEAN_TOO_LOW")
    if final_entries < constraints["min_final_holdout_entry_count"]:
        fail.append("FINAL_HOLDOUT_ENTRIES_TOO_LOW")
    if final_mean is None or final_mean < constraints["min_final_holdout_mean_net_bps"]:
        fail.append("FINAL_HOLDOUT_MEAN_TOO_LOW")
    if post_entries < constraints["min_post_asof_entry_count"]:
        fail.append("POST_ASOF_ENTRIES_TOO_LOW")
    if post_mean is None or post_mean < constraints["min_post_asof_mean_net_bps"]:
        fail.append("POST_ASOF_MEAN_TOO_LOW")
    if year_share is None or year_share > constraints["max_year_entry_share"]:
        fail.append("YEAR_CONCENTRATION_TOO_HIGH")
    if missing > constraints["max_missing_required_feature_rows"]:
        fail.append("MISSING_REQUIRED_FEATURE_ROWS")
    if lookahead > constraints["max_lookahead_violations"]:
        fail.append("LOOKAHEAD_VIOLATIONS")
    if incremental_days < constraints["min_incremental_union_active_days"]:
        fail.append("INCREMENTAL_DAYS_TOO_LOW")

    # Score: hard audit score is only for ranking hard-audit pass candidates.
    # High overlap is a penalty but not a Stage97 failure because Stage96 is residual_only;
    # Stage98 will decide portfolio expansion / observer inclusion.
    overlap_penalty = 0.0 if overlap is None else max(0.0, overlap - 50.0) * 8.0
    worst_penalty = 0.0 if worst is None else max(0.0, -worst - 1000.0) * 0.15
    score = (
        (final_mean or 0.0)
        + (post_mean or 0.0)
        + 0.75 * (locked_mean or 0.0)
        + 0.35 * (total_mean or 0.0)
        + 500.0 * (total_win or 0.0)
        + 0.25 * incremental_days
        - overlap_penalty
        - worst_penalty
    )

    return {
        "pass_cot_hard_audit_candidate": len(fail) == 0,
        "hard_fail_reasons": "|".join(fail),
        "cot_hard_audit_score": round(float(score), 4),
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="Repo root")
    ap.add_argument("--config", required=True, help="Stage97 config JSON")
    ap.add_argument("--out", required=True, help="Output directory")
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    config_path = resolve_path(root, args.config)
    out = resolve_path(root, args.out)
    ensure_out(out)

    cfg = load_config(root, config_path)
    summary_path = resolve_path(root, cfg["stage96_summary_path"])
    shortlist_path = resolve_path(root, cfg["stage96_shortlist_path"])
    metrics_path = resolve_path(root, cfg["stage96_metrics_path"])

    issues: List[str] = []
    references: List[Dict[str, Any]] = []

    stage96_summary: Dict[str, Any] = {}
    if summary_path.exists():
        stage96_summary = read_json(summary_path)
        references.append({
            "name": "stage96",
            "path": str(summary_path),
            "exists": True,
            "read_ok": True,
            "decision": stage96_summary.get("decision"),
            "disposition": stage96_summary.get("disposition"),
            "sha256": sha256_file(summary_path),
        })
        if stage96_summary.get("decision") not in REQUIRED_STAGE96_DECISIONS and stage96_summary.get("disposition") not in REQUIRED_STAGE96_DISPOSITIONS:
            issues.append("STAGE96_NOT_READY_FOR_STAGE97")
    else:
        references.append({"name": "stage96", "path": str(summary_path), "exists": False, "read_ok": False})
        issues.append("MISSING_STAGE96_SUMMARY")

    if shortlist_path.exists():
        base_df = pd.read_csv(shortlist_path)
        source_csv = shortlist_path
    elif metrics_path.exists():
        df_all = pd.read_csv(metrics_path)
        if "pass_cot_discovery_candidate" in df_all.columns:
            base_df = df_all[df_all["pass_cot_discovery_candidate"].map(normalize_bool)].copy()
        else:
            base_df = df_all.copy()
        source_csv = metrics_path
        issues.append("USED_METRICS_AS_FALLBACK_NO_SHORTLIST_CSV")
    else:
        base_df = pd.DataFrame()
        source_csv = shortlist_path
        issues.append("MISSING_STAGE96_SHORTLIST_AND_METRICS")

    if base_df.empty:
        metrics_out = out / "stage97_cot_hard_audit_metrics.csv"
        selected_out = out / "stage97_selected_for_stage98.csv"
        base_df.to_csv(metrics_out, index=False)
        base_df.to_csv(selected_out, index=False)
        status = "STAGE97_COMPLETE_NO_PROMOTION"
        decision = "NO_COT_HARD_AUDIT_SURVIVORS_NO_ORDER"
        classification = "S97_NO_COT_HARD_AUDIT_SURVIVORS"
        disposition = "NO_COT_HARD_AUDIT_SURVIVORS"
        selected = []
        pass_count = 0
    else:
        audited_rows = []
        for _, row in base_df.iterrows():
            audit = audit_row(row, cfg["constraints"])
            d = row.to_dict()
            d.update(audit)
            audited_rows.append(d)
        audited_df = pd.DataFrame(audited_rows)
        sort_cols = ["pass_cot_hard_audit_candidate", "cot_hard_audit_score"]
        audited_df = audited_df.sort_values(sort_cols, ascending=[False, False]).reset_index(drop=True)

        pass_df = audited_df[audited_df["pass_cot_hard_audit_candidate"].map(normalize_bool)].copy()
        pass_count = int(len(pass_df))
        max_selected = int(cfg.get("max_selected_for_stage98", cfg.get("selection", {}).get("max_selected_for_stage98", 3)))
        selected_df = pass_df.sort_values("cot_hard_audit_score", ascending=False).head(max_selected).copy()

        metrics_out = out / "stage97_cot_hard_audit_metrics.csv"
        selected_out = out / "stage97_selected_for_stage98.csv"
        audited_df.to_csv(metrics_out, index=False)
        selected_df.to_csv(selected_out, index=False)
        selected = selected_df.to_dict(orient="records")

        if pass_count > 0:
            status = "STAGE97_COMPLETE_NO_PROMOTION"
            decision = "STAGE97_COT_HARD_AUDIT_SHORTLIST_READY_FOR_PORTFOLIO_REVIEW_NO_ORDER"
            classification = "S97_COT_HARD_AUDIT_SHORTLIST_READY"
            disposition = "COT_HARD_AUDIT_SHORTLIST_READY_FOR_STAGE98_PORTFOLIO_REVIEW"
        else:
            status = "STAGE97_COMPLETE_NO_PROMOTION"
            decision = "NO_COT_HARD_AUDIT_SURVIVORS_NO_ORDER"
            classification = "S97_NO_COT_HARD_AUDIT_SURVIVORS"
            disposition = "NO_COT_HARD_AUDIT_SURVIVORS"

    summary = {
        "stage": STAGE,
        "root": str(root),
        "config": str(config_path),
        "status": status,
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "principle": "Hard-audit Stage96 COT discovery shortlist before any observer-portfolio expansion. No orders, no broker connection, no EA/MT5 change.",
        "stage96_reference": {
            "path": str(summary_path),
            "decision": stage96_summary.get("decision"),
            "classification": stage96_summary.get("classification"),
            "disposition": stage96_summary.get("disposition"),
            "cot_dataset": stage96_summary.get("cot_dataset"),
            "lookahead_violations": stage96_summary.get("lookahead_violations"),
            "residual_only": stage96_summary.get("residual_only"),
        },
        "input_csv": str(source_csv),
        "candidate_count": int(len(base_df)),
        "pass_hard_audit_count": pass_count,
        "selected_count": int(len(selected)),
        "selected_rule_ids": [r.get("rule_id") for r in selected],
        "selected_for_stage98": selected,
        "constraints": cfg["constraints"],
        "issues": issues,
        "hard_blocks": HARD_BLOCKS,
        "outputs": {
            "summary_json": str(out / "stage97_cot_positioning_hard_audit_summary.json"),
            "report_md": str(out / "stage97_cot_positioning_hard_audit_report.md"),
            "metrics_csv": str(out / "stage97_cot_hard_audit_metrics.csv"),
            "selected_csv": str(out / "stage97_selected_for_stage98.csv"),
        },
    }

    summary_out = out / "stage97_cot_positioning_hard_audit_summary.json"
    with summary_out.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)

    report_lines = [
        "# Stage97 COT Positioning Hard Audit",
        "",
        "## Decision",
        f"- status: `{status}`",
        f"- decision: `{decision}`",
        f"- classification: `{classification}`",
        f"- disposition: `{disposition}`",
        "",
        "## Selected for Stage98",
    ]
    if selected:
        for r in selected:
            report_lines.append(
                f"- `{r.get('rule_id')}`: {r.get('label')} score=`{r.get('cot_hard_audit_score')}` "
                f"mean=`{r.get('total_mean_net_bps')}` locked=`{r.get('locked_forward_mean_net_bps')}` "
                f"final=`{r.get('final_holdout_mean_net_bps')}` post_asof=`{r.get('post_asof_mean_net_bps')}` "
                f"incremental_days=`{r.get('incremental_union_active_days')}` overlap=`{r.get('overlap_with_current_union_pct')}`"
            )
    else:
        report_lines.append("- none")
    report_lines += [
        "",
        "## Hard blocks",
    ] + [f"- `{x}`" for x in HARD_BLOCKS]
    (out / "stage97_cot_positioning_hard_audit_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
