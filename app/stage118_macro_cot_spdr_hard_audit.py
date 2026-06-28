#!/usr/bin/env python3
"""Stage118 macro/COT/SPDR hard audit.

Data-only audit for Stage117 review-queue rules. No MT5/EA/broker/order changes.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

STAGE = "Stage118_MACRO_COT_SPDR_HARD_AUDIT"
STATUS = "STAGE118_COMPLETE_HARD_AUDIT_READY_NO_PROMOTION"
DECISION = "STAGE118_HARD_AUDIT_OUTPUT_READY_NO_ORDER"
HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_MT5_OR_EA_CHANGE_FROM_STAGE118",
    "NO_EA_CHANGE",
    "NO_OBSERVER_UPDATE_FROM_STAGE118",
    "NO_PAPER_LIVE",
    "NO_LIVE",
]

AUDIT_REPORT_DIR = "stage118_macro_cot_spdr_hard_audit"
STAGE117_REPORT_DIR = "stage117_segmented_macro_cot_dollar_discovery"
FEATURE_DIR = Path("data/fundamental_event_inbox/features")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_csv_field_limit() -> None:
    max_size = getattr(__import__("sys"), "maxsize", 2**31 - 1)
    while True:
        try:
            csv.field_size_limit(max_size)
            return
        except OverflowError:
            max_size = int(max_size / 10)


ensure_csv_field_limit()


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception as exc:  # pragma: no cover - diagnostic path
        raise RuntimeError(f"could not read CSV {path}: {exc}") from exc


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def safe_to_csv(df: pd.DataFrame, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return str(path)


def safe_to_json(obj: dict, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def coerce_time(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, utc=True, errors="coerce")


def num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def has_cols(df: pd.DataFrame, cols: Sequence[str]) -> bool:
    return all(c in df.columns for c in cols)


@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    description: str
    required_features: Sequence[str]
    expression_name: str
    candidate_only: bool = False


RULES: Dict[str, RuleSpec] = {
    "S117_01_RY_DOWN_DOLLAR_DOWN_COT_NOT_CROWDED": RuleSpec(
        "S117_01_RY_DOWN_DOLLAR_DOWN_COT_NOT_CROWDED",
        "Real-yield decline + dollar-pressure decline + COT not crowded",
        ["real_yield_10y_chg_20d", "dollar_pressure_chg_20d", "cot_mm_net_z"],
        "RY_DOWN_DOLLAR_DOWN_COT_NOT_CROWDED",
        False,
    ),
    "S117_06_SPDR_FLOW_SUPPORT_MACRO_RELIEF": RuleSpec(
        "S117_06_SPDR_FLOW_SUPPORT_MACRO_RELIEF",
        "SPDR support with macro relief, candidate-only",
        ["spdr_value_chg_20d", "dollar_pressure_chg_20d", "real_yield_10y_chg_20d"],
        "SPDR_FLOW_SUPPORT_MACRO_RELIEF",
        True,
    ),
}


def load_thresholds(path: Path) -> Dict[str, float]:
    df = read_csv(path)
    if df.empty:
        return {}
    row = df.iloc[0].to_dict()
    out: Dict[str, float] = {}
    for k, v in row.items():
        try:
            if pd.notna(v):
                out[str(k)] = float(v)
        except Exception:
            pass
    return out


def make_rule_mask(df: pd.DataFrame, rule: RuleSpec, th: Dict[str, float]) -> pd.Series:
    idx = df.index
    false = pd.Series(False, index=idx)

    def col(c: str) -> pd.Series:
        return num(df[c]) if c in df.columns else pd.Series(np.nan, index=idx)

    if not has_cols(df, rule.required_features):
        return false

    if rule.expression_name == "RY_DOWN_DOLLAR_DOWN_COT_NOT_CROWDED":
        return (
            (col("real_yield_10y_chg_20d") <= th.get("real_yield_10y_chg_20d_q25", -0.05))
            & (col("dollar_pressure_chg_20d") <= th.get("dollar_pressure_chg_20d_q25", -0.5))
            & (col("cot_mm_net_z") <= 1.0)
        ).fillna(False)

    if rule.expression_name == "SPDR_FLOW_SUPPORT_MACRO_RELIEF":
        return (
            (col("spdr_value_chg_20d") >= th.get("spdr_value_chg_20d_q75", 0.0))
            & (col("dollar_pressure_chg_20d") <= th.get("dollar_pressure_chg_20d_q50", 0.0))
            & (col("real_yield_10y_chg_20d") <= th.get("real_yield_10y_chg_20d_q50", 0.0))
        ).fillna(False)

    return false


def infer_return_col(df: pd.DataFrame) -> Optional[str]:
    candidates = [
        "fwd_ret_bps_h120",
        "forward_return_bps",
        "h120_forward_return_bps",
        "target_h120_bps",
        "future_return_h120_bps",
        "fwd_return_h120_bps",
        "ret_h120_bps",
    ]
    for c in candidates:
        if c in df.columns:
            return c
    for c in df.columns:
        lc = c.lower()
        if "bps" in lc and ("fwd" in lc or "forward" in lc or "h120" in lc):
            return c
    return None


def non_overlapping_events(events: pd.DataFrame, time_col: str, horizon_hours: int) -> pd.DataFrame:
    if events.empty or time_col not in events.columns:
        return events.copy()
    e = events.copy()
    e[time_col] = coerce_time(e[time_col])
    e = e.dropna(subset=[time_col]).sort_values(time_col)
    keep = []
    last = None
    gap = pd.Timedelta(hours=int(horizon_hours))
    for idx, t in e[time_col].items():
        if last is None or t >= last + gap:
            keep.append(idx)
            last = t
    return e.loc[keep].copy()


def year_concentration(events: pd.DataFrame, time_col: str) -> float:
    if events.empty or time_col not in events.columns:
        return math.nan
    years = coerce_time(events[time_col]).dt.year.dropna()
    if years.empty:
        return math.nan
    return float(years.value_counts(normalize=True).max() * 100.0)


def month_concentration(events: pd.DataFrame, time_col: str) -> float:
    if events.empty or time_col not in events.columns:
        return math.nan
    t = coerce_time(events[time_col]).dropna()
    if t.empty:
        return math.nan
    ym = t.dt.to_period("M").astype(str)
    return float(ym.value_counts(normalize=True).max() * 100.0)


def compute_stats(events: pd.DataFrame, return_col: str, time_col: str, cost_bps: float = 0.0) -> Dict[str, object]:
    if events.empty or return_col not in events.columns:
        return {
            "events": 0,
            "mean_bps": math.nan,
            "median_bps": math.nan,
            "hit_rate": math.nan,
            "p10_bps": math.nan,
            "p25_bps": math.nan,
            "p75_bps": math.nan,
            "p90_bps": math.nan,
            "worst_bps": math.nan,
            "best_bps": math.nan,
            "year_concentration_pct": math.nan,
            "month_concentration_pct": math.nan,
        }
    r = num(events[return_col]).dropna() - float(cost_bps)
    if r.empty:
        return {"events": 0, "mean_bps": math.nan, "median_bps": math.nan, "hit_rate": math.nan, "p10_bps": math.nan, "p25_bps": math.nan, "p75_bps": math.nan, "p90_bps": math.nan, "worst_bps": math.nan, "best_bps": math.nan, "year_concentration_pct": math.nan, "month_concentration_pct": math.nan}
    use_events = events.loc[r.index]
    return {
        "events": int(len(r)),
        "mean_bps": float(r.mean()),
        "median_bps": float(r.median()),
        "hit_rate": float((r > 0).mean()),
        "p10_bps": float(r.quantile(0.10)),
        "p25_bps": float(r.quantile(0.25)),
        "p75_bps": float(r.quantile(0.75)),
        "p90_bps": float(r.quantile(0.90)),
        "worst_bps": float(r.min()),
        "best_bps": float(r.max()),
        "year_concentration_pct": year_concentration(use_events, time_col),
        "month_concentration_pct": month_concentration(use_events, time_col),
    }


def calc_feature_coverage(df: pd.DataFrame, features: Sequence[str], mask: pd.Series) -> Dict[str, object]:
    out = {}
    base = max(int(mask.sum()), 1)
    for f in features:
        if f not in df.columns:
            out[f"coverage_{f}"] = 0.0
        else:
            out[f"coverage_{f}"] = float(100.0 * df.loc[mask, f].notna().sum() / base)
    return out


def jaccard(a: pd.Series, b: pd.Series) -> float:
    aa = a.fillna(False).astype(bool)
    bb = b.fillna(False).astype(bool)
    inter = int((aa & bb).sum())
    union = int((aa | bb).sum())
    return float(inter / union) if union else math.nan


def longest_loss_streak(returns: pd.Series) -> int:
    r = num(returns).dropna()
    max_streak = 0
    cur = 0
    for v in r:
        if v <= 0:
            cur += 1
            max_streak = max(max_streak, cur)
        else:
            cur = 0
    return int(max_streak)


def max_drawdown_of_cumsum(returns: pd.Series) -> float:
    r = num(returns).dropna()
    if r.empty:
        return math.nan
    curve = r.cumsum()
    dd = curve - curve.cummax()
    return float(dd.min())


def audit_decision(rule: RuleSpec, split_stats: Dict[str, Dict[str, object]], non_overlap_stats: Dict[str, Dict[str, object]], validation_context: dict) -> Tuple[str, str, List[str]]:
    reasons: List[str] = []
    v = split_stats.get("validation_cost10", {})
    t = split_stats.get("tail_forward_proxy_cost10", {})
    nv = non_overlap_stats.get("validation_cost10", {})
    nt = non_overlap_stats.get("tail_forward_proxy_cost10", {})

    validation_events = int(v.get("events") or 0)
    tail_events = int(t.get("events") or 0)
    tail_mean = float(t.get("mean_bps") if pd.notna(t.get("mean_bps", np.nan)) else np.nan)
    validation_mean = float(v.get("mean_bps") if pd.notna(v.get("mean_bps", np.nan)) else np.nan)
    tail_hit = float(t.get("hit_rate") if pd.notna(t.get("hit_rate", np.nan)) else np.nan)
    no_tail_events = int(nt.get("events") or 0)
    no_tail_mean = float(nt.get("mean_bps") if pd.notna(nt.get("mean_bps", np.nan)) else np.nan)
    no_tail_hit = float(nt.get("hit_rate") if pd.notna(nt.get("hit_rate", np.nan)) else np.nan)

    if validation_events < 30:
        reasons.append("validation_events_below_30")
    if tail_events < 30:
        reasons.append("tail_events_below_30")
    if not math.isfinite(validation_mean) or validation_mean <= 0:
        reasons.append("validation_cost10_mean_not_positive")
    if not math.isfinite(tail_mean) or tail_mean <= 0:
        reasons.append("tail_cost10_mean_not_positive")
    if not math.isfinite(tail_hit) or tail_hit < 0.50:
        reasons.append("tail_cost10_hit_rate_below_50pct")
    if no_tail_events < 3:
        reasons.append("nonoverlap_tail_events_too_low")
    if math.isfinite(no_tail_mean) and no_tail_mean <= 0:
        reasons.append("nonoverlap_tail_cost10_mean_not_positive")

    degradation_ratio = tail_mean / validation_mean if math.isfinite(tail_mean) and math.isfinite(validation_mean) and abs(validation_mean) > 1e-9 else math.nan
    if math.isfinite(degradation_ratio) and degradation_ratio < 0.25:
        reasons.append("tail_vs_validation_cost10_mean_degradation_gt_75pct")

    if rule.candidate_only:
        spdr_status = str(validation_context.get("spdr_gld_status", ""))
        if spdr_status and spdr_status != "VALIDATED_CANDIDATE":
            reasons.append(f"spdr_source_status_{spdr_status}")
        if tail_mean < 25.0:
            reasons.append("candidate_only_tail_cost10_mean_below_25bps")
        if not math.isfinite(tail_hit) or tail_hit < 0.55:
            reasons.append("candidate_only_tail_cost10_hit_below_55pct")
        if math.isfinite(no_tail_mean) and no_tail_mean < 10.0:
            reasons.append("candidate_only_nonoverlap_tail_cost10_mean_below_10bps")

    blockers = [r for r in reasons if r not in {"tail_vs_validation_cost10_mean_degradation_gt_75pct"}]
    if not blockers and not reasons:
        return "HARD_PASS_STAGE119_AUDIT_QUEUE", "Can enter Stage119 combined audit / observer design review; still no order.", reasons
    if blockers:
        return "FAIL_NO_STAGE119", "Do not advance; hard audit blockers present.", reasons
    return "WATCH_STAGE119_ONLY_WITH_EXTRA_CONFIRMATION", "Can be carried as watch-only into Stage119 if portfolio context justifies it; no promotion.", reasons


def find_stage116_summary(root: Path) -> dict:
    p = root / "reports" / "stage116_source_specific_wgc_spdr_dxy_validator" / "stage116_source_specific_wgc_spdr_dxy_validator_summary.json"
    return read_json(p)


def run(root: Path, horizon_hours: int = 120, cost_bps: Optional[Sequence[float]] = None) -> dict:
    cost_bps = list(cost_bps or [0.0, 5.0, 10.0, 15.0, 25.0])
    report_dir = root / "reports" / AUDIT_REPORT_DIR
    report_dir.mkdir(parents=True, exist_ok=True)

    stage117_dir = root / "reports" / STAGE117_REPORT_DIR
    feature_dir = root / FEATURE_DIR
    joined_path = feature_dir / "stage117_joined_macro_cot_dollar_h1_research_dataset.csv"
    selected_path = stage117_dir / "stage117_selected_for_stage118.csv"
    metrics_path = stage117_dir / "stage117_candidate_metrics.csv"
    thresholds_path = stage117_dir / "stage117_selection_thresholds.csv"

    joined = read_csv(joined_path)
    if joined.empty:
        raise RuntimeError(f"missing or empty Stage117 joined dataset: {joined_path}")
    if "utc_time" not in joined.columns:
        raise RuntimeError("Stage117 joined dataset must contain utc_time")
    joined["utc_time"] = coerce_time(joined["utc_time"])
    joined = joined.dropna(subset=["utc_time"]).sort_values("utc_time").reset_index(drop=True)
    return_col = infer_return_col(joined)
    if return_col is None:
        raise RuntimeError("Could not infer forward return column in Stage117 joined dataset")
    if "split" not in joined.columns:
        raise RuntimeError("Stage117 joined dataset must contain split")

    selected = read_csv(selected_path)
    selected_rule_ids = [str(x) for x in selected.get("rule_id", pd.Series(dtype=str)).dropna().tolist()]
    if not selected_rule_ids:
        selected_rule_ids = list(RULES.keys())
    selected_rule_ids = [r for r in selected_rule_ids if r in RULES]
    if not selected_rule_ids:
        raise RuntimeError("No known Stage117 rule IDs were selected for Stage118")

    thresholds = load_thresholds(thresholds_path)
    stage116_summary = find_stage116_summary(root)
    validation_context = {
        "direct_dxy_valid": stage116_summary.get("direct_dxy_valid"),
        "dxy_fallback_active": stage116_summary.get("dxy_fallback_active"),
        "validated_dollar_pressure_rows": stage116_summary.get("validated_dollar_pressure_rows"),
        "spdr_gld_status": stage116_summary.get("spdr_gld_status"),
        "spdr_gld_rows": stage116_summary.get("spdr_gld_rows"),
        "wgc_gold_etf_status": stage116_summary.get("wgc_gold_etf_status"),
        "wgc_central_bank_status": stage116_summary.get("wgc_central_bank_status"),
    }

    masks: Dict[str, pd.Series] = {}
    audit_rows: List[dict] = []
    split_rows: List[dict] = []
    nonoverlap_rows: List[dict] = []
    feature_rows: List[dict] = []
    stress_rows: List[dict] = []

    for rule_id in selected_rule_ids:
        rule = RULES[rule_id]
        mask = make_rule_mask(joined, rule, thresholds)
        masks[rule_id] = mask
        feature_avail = has_cols(joined, rule.required_features)
        coverage = calc_feature_coverage(joined, rule.required_features, mask)
        for feature in rule.required_features:
            total_cov = 100.0 * joined[feature].notna().sum() / max(len(joined), 1) if feature in joined.columns else 0.0
            event_cov = coverage.get(f"coverage_{feature}", 0.0)
            feature_rows.append({"rule_id": rule_id, "feature": feature, "full_coverage_pct": total_cov, "event_coverage_pct": event_cov})

        split_stats_by_name: Dict[str, Dict[str, object]] = {}
        non_stats_by_name: Dict[str, Dict[str, object]] = {}
        for split in ["selection", "validation", "tail_forward_proxy"]:
            split_mask = (joined["split"].astype(str) == split) & mask
            events = joined.loc[split_mask].copy()
            non = non_overlapping_events(events, "utc_time", horizon_hours)
            for c in cost_bps:
                st = compute_stats(events, return_col, "utc_time", c)
                nst = compute_stats(non, return_col, "utc_time", c)
                split_key = f"{split}_cost{int(c)}"
                if abs(c - 10.0) < 1e-9:
                    split_stats_by_name[split_key] = st
                    non_stats_by_name[split_key] = nst
                split_rows.append({"rule_id": rule_id, "split": split, "cost_bps": c, "overlap_mode": "raw_hourly", **st})
                nonoverlap_rows.append({"rule_id": rule_id, "split": split, "cost_bps": c, "overlap_mode": f"nonoverlap_{horizon_hours}h", **nst})
                if split in {"validation", "tail_forward_proxy"}:
                    stress_rows.append({"rule_id": rule_id, "split": split, "cost_bps": c, "raw_mean_bps": st.get("mean_bps"), "raw_hit_rate": st.get("hit_rate"), "nonoverlap_mean_bps": nst.get("mean_bps"), "nonoverlap_hit_rate": nst.get("hit_rate")})

        # Extra path diagnostics on all raw events.
        all_events = joined.loc[mask].copy()
        lr = longest_loss_streak(num(all_events[return_col])) if not all_events.empty else 0
        mdd = max_drawdown_of_cumsum(num(all_events[return_col])) if not all_events.empty else math.nan
        decision, interpretation, reasons = audit_decision(rule, split_stats_by_name, non_stats_by_name, validation_context)
        audit_rows.append({
            "rule_id": rule_id,
            "description": rule.description,
            "candidate_only": rule.candidate_only,
            "required_features": ",".join(rule.required_features),
            "feature_available": feature_avail,
            "audit_decision": decision,
            "interpretation": interpretation,
            "audit_reasons": ";".join(reasons),
            "raw_all_events": int(mask.sum()),
            "longest_loss_streak_raw_all": lr,
            "max_drawdown_bps_raw_all_cumsum": mdd,
            "stage116_dxy_fallback_active": validation_context.get("dxy_fallback_active"),
            "stage116_direct_dxy_valid": validation_context.get("direct_dxy_valid"),
            "stage116_spdr_status": validation_context.get("spdr_gld_status"),
        })

    # Overlap matrix for raw hourly masks and non-overlap time buckets.
    overlap_rows: List[dict] = []
    for a in selected_rule_ids:
        for b in selected_rule_ids:
            overlap_rows.append({"rule_id_a": a, "rule_id_b": b, "raw_hourly_jaccard": jaccard(masks[a], masks[b]), "raw_hourly_intersection": int((masks[a] & masks[b]).sum()), "raw_hourly_union": int((masks[a] | masks[b]).sum())})

    audit_df = pd.DataFrame(audit_rows)
    split_df = pd.DataFrame(split_rows)
    nonoverlap_df = pd.DataFrame(nonoverlap_rows)
    stress_df = pd.DataFrame(stress_rows)
    feature_df = pd.DataFrame(feature_rows)
    overlap_df = pd.DataFrame(overlap_rows)

    selected_stage119 = audit_df[audit_df["audit_decision"].isin(["HARD_PASS_STAGE119_AUDIT_QUEUE", "WATCH_STAGE119_ONLY_WITH_EXTRA_CONFIRMATION"])].copy()
    rejected = audit_df[audit_df["audit_decision"] == "FAIL_NO_STAGE119"].copy()

    audit_metrics_path = safe_to_csv(audit_df, report_dir / "stage118_rule_audit_metrics.csv")
    split_metrics_path = safe_to_csv(split_df, report_dir / "stage118_split_cost_stress_metrics.csv")
    nonoverlap_metrics_path = safe_to_csv(nonoverlap_df, report_dir / "stage118_nonoverlap_cost_stress_metrics.csv")
    stress_path = safe_to_csv(stress_df, report_dir / "stage118_cost_stress_summary.csv")
    coverage_path = safe_to_csv(feature_df, report_dir / "stage118_feature_coverage_by_rule.csv")
    overlap_path = safe_to_csv(overlap_df, report_dir / "stage118_overlap_matrix.csv")
    selected_stage119_path = safe_to_csv(selected_stage119, report_dir / "stage118_selected_for_stage119.csv")
    rejected_path = safe_to_csv(rejected, report_dir / "stage118_rejected_rules.csv")

    hard_pass_count = int((audit_df["audit_decision"] == "HARD_PASS_STAGE119_AUDIT_QUEUE").sum()) if not audit_df.empty else 0
    watch_count = int((audit_df["audit_decision"] == "WATCH_STAGE119_ONLY_WITH_EXTRA_CONFIRMATION").sum()) if not audit_df.empty else 0
    fail_count = int((audit_df["audit_decision"] == "FAIL_NO_STAGE119").sum()) if not audit_df.empty else 0

    summary = {
        "stage": STAGE,
        "generated_utc": utc_now_iso(),
        "status": STATUS,
        "decision": DECISION,
        "classification": "HARD_AUDIT_ONLY_NO_ORDER",
        "hard_blocks": HARD_BLOCKS,
        "root": str(root),
        "stage117_joined_dataset": str(joined_path),
        "stage117_selected_input": str(selected_path),
        "stage117_thresholds_input": str(thresholds_path),
        "return_col": return_col,
        "horizon_hours": int(horizon_hours),
        "audited_rule_count": int(len(audit_df)),
        "hard_pass_count": hard_pass_count,
        "watch_count": watch_count,
        "fail_count": fail_count,
        "stage116_context": validation_context,
        "audit_metrics": audit_metrics_path,
        "split_cost_stress_metrics": split_metrics_path,
        "nonoverlap_cost_stress_metrics": nonoverlap_metrics_path,
        "cost_stress_summary": stress_path,
        "feature_coverage_by_rule": coverage_path,
        "overlap_matrix": overlap_path,
        "selected_for_stage119": selected_stage119_path,
        "rejected_rules": rejected_path,
        "next": [
            "If hard_pass_count or watch_count is positive, Stage119 should run combined portfolio/overlap/observer-readiness review only; no observer update yet.",
            "Rules with FAIL_NO_STAGE119 should not be carried forward unless the data/source bug is corrected and Stage117 is rerun.",
            "No paper, demo, MT5, EA, or live order is authorized by Stage118.",
        ],
    }
    summary_path = safe_to_json(summary, report_dir / "stage118_macro_cot_spdr_hard_audit_summary.json")

    report_lines = [
        f"# {STAGE}",
        "",
        f"Generated UTC: {summary['generated_utc']}",
        "",
        f"Status: `{STATUS}`",
        f"Decision: `{DECISION}`",
        "",
        "## Interpretation",
        "",
        "Stage118 performs hard audit of Stage117 review-queue rules. It does not promote, update observers, touch MT5/EA, or authorize any order.",
        "",
        "## Audit result counts",
        "",
        f"- Hard pass count: `{hard_pass_count}`",
        f"- Watch count: `{watch_count}`",
        f"- Fail count: `{fail_count}`",
        "",
        "## Rule decisions",
        "",
    ]
    if not audit_df.empty:
        for _, r in audit_df.iterrows():
            report_lines += [
                f"### {r['rule_id']}",
                "",
                f"- Decision: `{r['audit_decision']}`",
                f"- Candidate-only: `{r['candidate_only']}`",
                f"- Reasons: `{r['audit_reasons'] or 'NONE'}`",
                "",
            ]
    report_lines += [
        "## Outputs",
        "",
        f"- Summary JSON: `{summary_path}`",
        f"- Rule audit metrics: `{audit_metrics_path}`",
        f"- Split cost stress metrics: `{split_metrics_path}`",
        f"- Non-overlap metrics: `{nonoverlap_metrics_path}`",
        f"- Overlap matrix: `{overlap_path}`",
        f"- Selected for Stage119: `{selected_stage119_path}`",
        "",
    ]
    report_path = report_dir / "stage118_macro_cot_spdr_hard_audit_report.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    summary["summary_json"] = summary_path
    summary["report_md"] = str(report_path)
    safe_to_json(summary, report_dir / "stage118_macro_cot_spdr_hard_audit_summary.json")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Stage118 hard audit for Stage117 macro/COT/SPDR rules")
    ap.add_argument("--root", default=os.getcwd(), help="Repo root")
    ap.add_argument("--horizon-hours", type=int, default=120, help="Forward horizon / non-overlap gap")
    args = ap.parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    run(root=root, horizon_hours=args.horizon_hours)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
