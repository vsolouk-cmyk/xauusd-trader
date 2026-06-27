#!/usr/bin/env python3
"""Stage82 portfolio increment review for Stage81B hard-audit survivors.

Observer/research only. No trading, broker connection, or EA promotion.
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

STAGE = "Stage82_PORTFOLIO_INCREMENT_REVIEW"

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE82",
    "NO_THRESHOLD_TUNING_FROM_STAGE82_PORTFOLIO_REVIEW",
    "NO_DIRECT_MT5_OR_EA_CHANGE_FROM_STAGE82",
]

@dataclass(frozen=True)
class Condition:
    column: str
    op: str
    threshold: float

@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    label: str
    bucket: str
    horizon_trading_days: int
    cooldown_trading_days: int
    priority: int
    conditions: Tuple[Condition, ...]


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys: List[str] = []
        for r in rows:
            for k in r.keys():
                if k not in keys:
                    keys.append(k)
        fieldnames = keys
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})


def as_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == "":
            return default
        return float(x)
    except Exception:
        return default


def as_int(x: Any, default: int = 0) -> int:
    try:
        if x is None or x == "":
            return default
        return int(float(x))
    except Exception:
        return default


def boolish(x: Any) -> bool:
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return bool(x)
    return str(x).strip().lower() in {"true", "1", "yes", "y"}


def numeric_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series([float("nan")] * len(df), index=df.index)
    return pd.to_numeric(df[col], errors="coerce")


def add_derived_features(df: pd.DataFrame) -> List[str]:
    added: List[str] = []
    # Convert existing mostly numeric columns with coercion. Metadata columns remain usable as strings.
    for c in df.columns:
        if c in {"feature_date_utc", "date", "utc_time", "symbol", "source", "timeframe"}:
            continue
        converted = pd.to_numeric(df[c], errors="coerce")
        # Replace only if there is at least one numeric value or the original column was already numeric-like.
        if converted.notna().any() or pd.api.types.is_numeric_dtype(df[c]):
            df[c] = converted

    if "gold_ret_20d" not in df.columns and "gold_close" in df.columns:
        df["gold_ret_20d"] = numeric_series(df, "gold_close").pct_change(20)
        added.append("gold_ret_20d")
    if "gold_ret_60d" not in df.columns and "gold_close" in df.columns:
        df["gold_ret_60d"] = numeric_series(df, "gold_close").pct_change(60)
        added.append("gold_ret_60d")
    if "dxy_ret_60d" not in df.columns and "dxy" in df.columns:
        df["dxy_ret_60d"] = numeric_series(df, "dxy").pct_change(60)
        added.append("dxy_ret_60d")
    if "real_yield_change_60d" not in df.columns and "real_yield" in df.columns:
        df["real_yield_change_60d"] = numeric_series(df, "real_yield") - numeric_series(df, "real_yield").shift(60)
        added.append("real_yield_change_60d")
    return added


def get_date_col(df: pd.DataFrame, preferred: str) -> str:
    if preferred in df.columns:
        return preferred
    for c in ["feature_date_utc", "date", "utc_time", "time"]:
        if c in df.columns:
            return c
    raise ValueError("No usable date column found")


def rule_specs() -> Dict[str, RuleSpec]:
    specs = [
        RuleSpec(
            "K06_RESILIENT_GOLD_VS_DXY_H120", "K06_RESILIENT_GOLD_VS_DXY", "stage77b_current", 120, 120, 1,
            (Condition("gold_sma20_over_50", ">", 0.0), Condition("dxy_ret_20d", ">", 0.0), Condition("real_yield_change_20d", "<", 0.0)),
        ),
        RuleSpec(
            "K03_SAFE_HAVEN_REALYIELD_H120", "K03_WGC_RISK_UNCERTAINTY_SAFE_HAVEN", "stage77b_current", 120, 120, 2,
            (Condition("vix_change_20d", ">", 0.0), Condition("real_yield_change_20d", "<", 0.0)),
        ),
        RuleSpec(
            "K07_DXY_TREND_RELIEF_GOLD_TREND_H120", "K07_DXY_TREND_RELIEF_GOLD_TREND", "stage77b_current", 120, 120, 3,
            (Condition("gold_sma20_over_50", ">", 0.0), Condition("dxy_sma20_over_50", "<", 0.0)),
        ),
        RuleSpec(
            "S80_04_REALYIELD_60D_RELIEF_GOLD_TREND_H120", "SIXTY_DAY_REAL_YIELD_RELIEF_GOLD_TREND", "stage81b_survivor", 120, 120, 11,
            (Condition("real_yield_change_60d", "<", 0.0), Condition("gold_sma20_over_50", ">", 0.0)),
        ),
        RuleSpec(
            "S80_31_DXY_60D_RELIEF_CB_SUPPORT_H120", "SIXTY_DAY_DXY_RELIEF_WITH_CB_SUPPORT", "stage81b_survivor", 120, 120, 12,
            (Condition("dxy_ret_60d", "<", 0.0), Condition("central_bank_demand_tonnes_3m", ">", 0.0)),
        ),
        RuleSpec(
            "S80_33_DXY_60D_RELIEF_ETF_SUPPORT_H120", "SIXTY_DAY_DXY_RELIEF_WITH_ETF_SUPPORT", "stage81b_survivor", 120, 120, 13,
            (Condition("dxy_ret_60d", "<", 0.0), Condition("etf_flow_tonnes_3m", ">", 0.0)),
        ),
        RuleSpec(
            "S80_17_RISKOFF_GOLD_TREND_H120", "RISK_OFF_GOLD_TREND", "stage81b_survivor", 120, 120, 14,
            (Condition("vix_change_20d", ">", 0.0), Condition("gold_sma20_over_50", ">", 0.0)),
        ),
    ]
    return {s.rule_id: s for s in specs}


def condition_mask(df: pd.DataFrame, cond: Condition) -> pd.Series:
    if cond.column not in df.columns:
        return pd.Series([False] * len(df), index=df.index)
    x = pd.to_numeric(df[cond.column], errors="coerce")
    if cond.op == ">":
        return x > cond.threshold
    if cond.op == "<":
        return x < cond.threshold
    if cond.op == ">=":
        return x >= cond.threshold
    if cond.op == "<=":
        return x <= cond.threshold
    if cond.op == "==":
        return x == cond.threshold
    raise ValueError(f"Unsupported operator: {cond.op}")


def evaluate_rule_active(df: pd.DataFrame, spec: RuleSpec) -> Tuple[pd.Series, List[str]]:
    missing = [c.column for c in spec.conditions if c.column not in df.columns]
    mask = pd.Series([True] * len(df), index=df.index)
    for cond in spec.conditions:
        if cond.column not in df.columns:
            mask &= False
        else:
            mask &= condition_mask(df, cond)
    return mask.fillna(False), missing


def latest_rule_snapshot(df: pd.DataFrame, spec: RuleSpec, latest_idx: int) -> Dict[str, Any]:
    failures: List[str] = []
    condition_results: List[Dict[str, Any]] = []
    for cond in spec.conditions:
        if cond.column not in df.columns:
            passed = False
            value: Any = ""
            reason = "missing_column"
        else:
            value = as_float(df.iloc[latest_idx].get(cond.column), float("nan"))
            if cond.op == ">":
                passed = value > cond.threshold
            elif cond.op == "<":
                passed = value < cond.threshold
            elif cond.op == ">=":
                passed = value >= cond.threshold
            elif cond.op == "<=":
                passed = value <= cond.threshold
            elif cond.op == "==":
                passed = value == cond.threshold
            else:
                passed = False
            reason = "ok" if passed else f"{value}{cond.op}{cond.threshold}"
        condition_results.append({
            "column": cond.column,
            "operator": cond.op,
            "threshold": cond.threshold,
            "value": value,
            "passed": passed,
            "reason": reason,
        })
        if not passed:
            failures.append(f"{cond.column}:{reason}")
    return {
        "rule_id": spec.rule_id,
        "label": spec.label,
        "signal_active": len(failures) == 0,
        "failures": "|".join(failures),
        "condition_results": condition_results,
    }


def pct_overlap(a: pd.Series, b: pd.Series) -> float:
    a = a.astype(bool)
    b = b.astype(bool)
    denom = int(a.sum())
    if denom == 0:
        return 0.0
    return round(100.0 * int((a & b).sum()) / denom, 4)


def jaccard(a: pd.Series, b: pd.Series) -> float:
    a = a.astype(bool)
    b = b.astype(bool)
    denom = int((a | b).sum())
    if denom == 0:
        return 0.0
    return round(100.0 * int((a & b).sum()) / denom, 4)


def active_day_union(masks: Iterable[pd.Series]) -> int:
    masks = list(masks)
    if not masks:
        return 0
    out = pd.Series([False] * len(masks[0]), index=masks[0].index)
    for m in masks:
        out |= m.astype(bool)
    return int(out.sum())


def read_config(path: Path) -> Dict[str, Any]:
    default = {
        "macro_dataset_path": "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
        "date_col": "feature_date_utc",
        "stage77b_summary_path": "reports/stage77b_corrected_portfolio_candidate_selection_historical_asof/stage77b_corrected_portfolio_candidate_selection_historical_asof_summary.json",
        "stage81b_summary_path": "reports/stage81b_corrected_hard_audit_stage80_shortlist/stage81b_corrected_hard_audit_stage80_shortlist_summary.json",
        "max_additions": 2,
        "max_overlap_with_current_pct": 50.0,
        "max_pairwise_addition_overlap_pct": 60.0,
        "min_hard_audit_score": 3500.0,
        "min_final_holdout_mean_bps": 1000.0,
        "min_post_plus_final_mean_bps": 1000.0,
        "min_total_win_rate": 0.58,
        "min_incremental_union_active_days": 50,
    }
    if path.exists():
        loaded = load_json(path)
        default.update(loaded)
    return default


def candidate_from_stage81b(row: Dict[str, Any], masks: Dict[str, pd.Series], current_ids: List[str], config: Dict[str, Any]) -> Dict[str, Any]:
    rid = str(row.get("rule_id", ""))
    cand_mask = masks.get(rid)
    current_masks = [masks[c] for c in current_ids if c in masks]
    max_current_overlap = max([pct_overlap(cand_mask, cm) for cm in current_masks], default=0.0) if cand_mask is not None else 0.0
    max_current_jaccard = max([jaccard(cand_mask, cm) for cm in current_masks], default=0.0) if cand_mask is not None else 0.0
    current_union_before = active_day_union(current_masks)
    current_union_after = active_day_union(current_masks + ([cand_mask] if cand_mask is not None else []))
    incremental_days = max(0, current_union_after - current_union_before)

    hard_score = as_float(row.get("hard_audit_score"))
    final_mean = as_float(row.get("final_holdout_mean_net_bps"))
    post_mean = as_float(row.get("post_plus_final_mean_net_bps"))
    total_win = as_float(row.get("total_win_rate"))
    total_mean = as_float(row.get("total_mean_net_return_bps"))
    locked_mean = as_float(row.get("locked_forward_mean_net_bps"))
    worst = as_float(row.get("total_min_net_return_bps"))

    fail_reasons: List[str] = []
    if not boolish(row.get("pass_hard_audit_candidate", True)):
        fail_reasons.append("NOT_HARD_AUDIT_PASS")
    if max_current_overlap > as_float(config.get("max_overlap_with_current_pct", 50.0)):
        fail_reasons.append("OVERLAP_WITH_CURRENT_PORTFOLIO_TOO_HIGH")
    if hard_score < as_float(config.get("min_hard_audit_score", 3500.0)):
        fail_reasons.append("HARD_AUDIT_SCORE_TOO_LOW")
    if final_mean < as_float(config.get("min_final_holdout_mean_bps", 1000.0)):
        fail_reasons.append("FINAL_HOLDOUT_MEAN_TOO_LOW")
    if post_mean < as_float(config.get("min_post_plus_final_mean_bps", 1000.0)):
        fail_reasons.append("POST_PLUS_FINAL_MEAN_TOO_LOW")
    if total_win < as_float(config.get("min_total_win_rate", 0.58)):
        fail_reasons.append("TOTAL_WIN_RATE_TOO_LOW")
    if incremental_days < as_int(config.get("min_incremental_union_active_days", 50)):
        fail_reasons.append("INCREMENTAL_ACTIVE_DAY_CONTRIBUTION_TOO_LOW")

    # Penalize overlap, reward recent holdout and locked-forward quality, and reward incremental regime coverage.
    increment_score = (
        hard_score
        + 0.30 * post_mean
        + 0.20 * final_mean
        + 0.10 * locked_mean
        + 0.05 * total_mean
        + 1.00 * incremental_days
        - 12.0 * max_current_overlap
        - max(0.0, abs(worst) - 1200.0) * 0.15
    )

    out = dict(row)
    out.update({
        "max_overlap_with_current_portfolio_pct": round(max_current_overlap, 4),
        "max_jaccard_with_current_portfolio_pct": round(max_current_jaccard, 4),
        "current_union_active_days_before": current_union_before,
        "current_union_active_days_after_candidate": current_union_after,
        "incremental_union_active_days": incremental_days,
        "portfolio_increment_score": round(increment_score, 4),
        "pass_stage82_increment_filter": len(fail_reasons) == 0,
        "stage82_fail_reasons": "|".join(fail_reasons),
    })
    return out


def select_additions(candidates: List[Dict[str, Any]], masks: Dict[str, pd.Series], config: Dict[str, Any]) -> List[Dict[str, Any]]:
    max_additions = as_int(config.get("max_additions", 2), 2)
    max_pairwise = as_float(config.get("max_pairwise_addition_overlap_pct", 60.0), 60.0)
    selected: List[Dict[str, Any]] = []
    for c in sorted(candidates, key=lambda r: as_float(r.get("portfolio_increment_score")), reverse=True):
        if not boolish(c.get("pass_stage82_increment_filter")):
            continue
        rid = str(c.get("rule_id", ""))
        cm = masks.get(rid)
        if cm is None:
            continue
        pairwise = 0.0
        for s in selected:
            sm = masks.get(str(s.get("rule_id", "")))
            if sm is not None:
                pairwise = max(pairwise, pct_overlap(cm, sm))
        c = dict(c)
        c["max_overlap_with_selected_additions_pct"] = round(pairwise, 4)
        if pairwise > max_pairwise:
            c["pass_stage82_increment_filter"] = False
            existing = str(c.get("stage82_fail_reasons", ""))
            c["stage82_fail_reasons"] = (existing + "|" if existing else "") + "OVERLAP_WITH_SELECTED_ADDITIONS_TOO_HIGH"
            continue
        selected.append(c)
        if len(selected) >= max_additions:
            break
    return selected


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage82_portfolio_increment_review.json")
    ap.add_argument("--out", default="reports/stage82_portfolio_increment_review")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    config_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config).resolve()
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out).resolve()
    config = read_config(config_path)

    macro_path = Path(config["macro_dataset_path"])
    if not macro_path.is_absolute():
        macro_path = root / macro_path
    stage77b_path = Path(config["stage77b_summary_path"])
    if not stage77b_path.is_absolute():
        stage77b_path = root / stage77b_path
    stage81b_path = Path(config["stage81b_summary_path"])
    if not stage81b_path.is_absolute():
        stage81b_path = root / stage81b_path

    issues: List[str] = []
    if not macro_path.exists():
        raise FileNotFoundError(f"macro dataset not found: {macro_path}")
    if not stage77b_path.exists():
        raise FileNotFoundError(f"Stage77B summary not found: {stage77b_path}")
    if not stage81b_path.exists():
        raise FileNotFoundError(f"Stage81B summary not found: {stage81b_path}")

    stage77b = load_json(stage77b_path)
    stage81b = load_json(stage81b_path)
    if stage77b.get("disposition") != "PORTFOLIO_READY_WITH_K06_PLUS_COMPLEMENTS":
        issues.append("STAGE77B_DISPOSITION_NOT_REQUIRED_VALUE")
    if stage81b.get("disposition") != "HARD_AUDIT_SHORTLIST_READY_FOR_PORTFOLIO_REVIEW":
        issues.append("STAGE81B_DISPOSITION_NOT_REQUIRED_VALUE")

    df = pd.read_csv(macro_path)
    date_col = get_date_col(df, str(config.get("date_col", "feature_date_utc")))
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce", utc=True)
    df = df.dropna(subset=[date_col]).sort_values(date_col).reset_index(drop=True)
    derived_added = add_derived_features(df)
    latest_idx = len(df) - 1
    latest_date = df.iloc[latest_idx][date_col].date().isoformat() if latest_idx >= 0 else None

    specs = rule_specs()
    current_ids = [str(x) for x in stage77b.get("selected_rule_ids", [])]
    if not current_ids:
        current_ids = ["K06_RESILIENT_GOLD_VS_DXY_H120", "K03_SAFE_HAVEN_REALYIELD_H120", "K07_DXY_TREND_RELIEF_GOLD_TREND_H120"]
    survivor_rows = stage81b.get("selected_for_stage82", []) or []
    survivor_ids = [str(x.get("rule_id", "")) for x in survivor_rows]

    needed_ids = list(dict.fromkeys(current_ids + survivor_ids))
    masks: Dict[str, pd.Series] = {}
    missing_map: Dict[str, List[str]] = {}
    latest_snapshots: List[Dict[str, Any]] = []
    for rid in needed_ids:
        spec = specs.get(rid)
        if spec is None:
            issues.append(f"MISSING_RULE_SPEC:{rid}")
            continue
        mask, missing = evaluate_rule_active(df, spec)
        masks[rid] = mask
        missing_map[rid] = missing
        latest_snapshots.append(latest_rule_snapshot(df, spec, latest_idx))

    current_union_days = active_day_union([masks[x] for x in current_ids if x in masks])
    stage82_candidates = [candidate_from_stage81b(r, masks, current_ids, config) for r in survivor_rows]
    selected = select_additions(stage82_candidates, masks, config)
    final_portfolio_ids = current_ids + [str(s.get("rule_id")) for s in selected]
    final_union_days = active_day_union([masks[x] for x in final_portfolio_ids if x in masks])

    pairwise_rows: List[Dict[str, Any]] = []
    all_review_ids = list(dict.fromkeys(current_ids + survivor_ids))
    for i, a in enumerate(all_review_ids):
        for b in all_review_ids[i+1:]:
            if a in masks and b in masks:
                pairwise_rows.append({
                    "rule_a": a,
                    "rule_b": b,
                    "a_overlap_b_pct_of_a_active": pct_overlap(masks[a], masks[b]),
                    "b_overlap_a_pct_of_b_active": pct_overlap(masks[b], masks[a]),
                    "jaccard_pct": jaccard(masks[a], masks[b]),
                })

    active_selected = [s for s in latest_snapshots if s.get("rule_id") in final_portfolio_ids and boolish(s.get("signal_active"))]
    selected_rule_id = active_selected[0]["rule_id"] if active_selected else None

    if issues:
        status = "STAGE82_COMPLETE_NO_PROMOTION_WITH_ISSUES"
        decision = "STAGE82_PORTFOLIO_INCREMENT_REVIEW_BLOCKED_BY_ISSUES_NO_ORDER"
        classification = "S82_BLOCKED_BY_ISSUES"
        disposition = "PORTFOLIO_INCREMENT_REVIEW_BLOCKED"
    elif selected:
        status = "STAGE82_COMPLETE_NO_PROMOTION"
        decision = "STAGE82_PORTFOLIO_INCREMENT_READY_FOR_OBSERVER_REVIEW_NO_ORDER"
        classification = "S82_INCREMENT_READY_FOR_OBSERVER_REVIEW"
        disposition = "PORTFOLIO_INCREMENT_READY_FOR_OBSERVER_REVIEW"
    else:
        status = "STAGE82_COMPLETE_NO_PROMOTION"
        decision = "STAGE82_KEEP_STAGE77B_PORTFOLIO_ONLY_NO_ORDER"
        classification = "S82_NO_INCREMENT_SELECTED"
        disposition = "KEEP_STAGE77B_PORTFOLIO_ONLY"

    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "stage82_portfolio_increment_review_summary.json"
    report_path = out_dir / "stage82_portfolio_increment_review_report.md"
    review_csv = out_dir / "stage82_portfolio_increment_review.csv"
    selected_csv = out_dir / "stage82_selected_for_stage83.csv"
    pairwise_csv = out_dir / "stage82_pairwise_overlap_review.csv"
    latest_csv = out_dir / "stage82_latest_signal_snapshot.csv"

    write_csv(review_csv, stage82_candidates)
    write_csv(selected_csv, selected)
    write_csv(pairwise_csv, pairwise_rows)
    write_csv(latest_csv, latest_snapshots)

    summary: Dict[str, Any] = {
        "stage": STAGE,
        "root": str(root),
        "config": str(config_path),
        "generated_utc": now_utc(),
        "status": status,
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "principle": "Review Stage81B hard-audit survivors for incremental portfolio contribution before any observer-only portfolio expansion. No order authorization.",
        "macro_dataset": {
            "path": str(macro_path),
            "rows": int(len(df)),
            "date_col": date_col,
            "min_date": df[date_col].min().date().isoformat() if len(df) else None,
            "max_date": df[date_col].max().date().isoformat() if len(df) else None,
            "derived_features_added": derived_added,
        },
        "latest_feature_date_utc": latest_date,
        "current_stage77b_rule_ids": current_ids,
        "stage81b_survivor_rule_ids": survivor_ids,
        "candidate_count": len(stage82_candidates),
        "selected_count": len(selected),
        "selected_rule_ids": [str(s.get("rule_id")) for s in selected],
        "selected_for_stage83": selected,
        "final_review_portfolio_rule_ids": final_portfolio_ids,
        "current_union_active_days": current_union_days,
        "final_union_active_days_after_selected_additions": final_union_days,
        "incremental_union_active_days_selected": final_union_days - current_union_days,
        "latest_signal_snapshot": latest_snapshots,
        "latest_active_rule_ids_in_review_portfolio": [str(x.get("rule_id")) for x in active_selected],
        "latest_selected_rule_id": selected_rule_id,
        "issues": issues,
        "constraints": {
            "max_additions": as_int(config.get("max_additions", 2)),
            "max_overlap_with_current_pct": as_float(config.get("max_overlap_with_current_pct", 50.0)),
            "max_pairwise_addition_overlap_pct": as_float(config.get("max_pairwise_addition_overlap_pct", 60.0)),
            "min_hard_audit_score": as_float(config.get("min_hard_audit_score", 3500.0)),
            "min_final_holdout_mean_bps": as_float(config.get("min_final_holdout_mean_bps", 1000.0)),
            "min_post_plus_final_mean_bps": as_float(config.get("min_post_plus_final_mean_bps", 1000.0)),
            "min_total_win_rate": as_float(config.get("min_total_win_rate", 0.58)),
            "min_incremental_union_active_days": as_int(config.get("min_incremental_union_active_days", 50)),
        },
        "hard_blocks": HARD_BLOCKS,
        "outputs": {
            "summary_json": str(summary_path),
            "report_md": str(report_path),
            "review_csv": str(review_csv),
            "selected_csv": str(selected_csv),
            "pairwise_overlap_csv": str(pairwise_csv),
            "latest_signal_snapshot_csv": str(latest_csv),
        },
    }
    write_json(summary_path, summary)

    lines: List[str] = []
    lines.append("# Stage82 Portfolio Increment Review")
    lines.append("")
    lines.append("## Decision")
    lines.append(f"- status: `{status}`")
    lines.append(f"- decision: `{decision}`")
    lines.append(f"- classification: `{classification}`")
    lines.append(f"- disposition: `{disposition}`")
    lines.append("")
    lines.append("## Current Stage77B portfolio")
    for rid in current_ids:
        lines.append(f"- `{rid}`")
    lines.append("")
    lines.append("## Stage81B survivors reviewed")
    for rid in survivor_ids:
        lines.append(f"- `{rid}`")
    lines.append("")
    lines.append("## Selected for Stage83 observer review")
    if selected:
        for s in selected:
            lines.append(
                f"- `{s.get('rule_id')}`: {s.get('label')} score=`{s.get('portfolio_increment_score')}` "
                f"incremental_days=`{s.get('incremental_union_active_days')}` overlap_current=`{s.get('max_overlap_with_current_portfolio_pct')}`"
            )
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Latest signal snapshot")
    for snap in latest_snapshots:
        lines.append(f"- `{snap.get('rule_id')}` active=`{snap.get('signal_active')}` failures=`{snap.get('failures')}`")
    lines.append("")
    lines.append("## Issues")
    if issues:
        for issue in issues:
            lines.append(f"- `{issue}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Hard blocks")
    for block in HARD_BLOCKS:
        lines.append(f"- `{block}`")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "stage": STAGE,
        "status": status,
        "decision": decision,
        "selected_rule_ids": [str(s.get("rule_id")) for s in selected],
        "summary_json": str(summary_path),
        "report_md": str(report_path),
        "issues": issues,
    }, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
