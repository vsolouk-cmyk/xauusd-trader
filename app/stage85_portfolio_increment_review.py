#!/usr/bin/env python3
"""
Stage85 Portfolio Increment Review for Stage84 orthogonal hard-audit survivors.

This stage reviews the Stage84-selected orthogonal candidates against the existing
Stage77B observer portfolio. It does not authorize orders, broker connections,
EA promotion, paper-live, live, or threshold tuning.

Inputs:
- reports/stage77b_corrected_portfolio_candidate_selection_historical_asof/...summary.json
- reports/stage84_hard_audit_stage83_orthogonal_shortlist/...summary.json
- data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv

Outputs:
- stage85_portfolio_increment_review_summary.json
- stage85_portfolio_increment_review_report.md
- stage85_selected_for_stage86.csv
- stage85_portfolio_increment_review.csv
- stage85_latest_signal_snapshot.csv
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd


@dataclass(frozen=True)
class Condition:
    column: str
    op: str
    threshold: float


@dataclass(frozen=True)
class Rule:
    rule_id: str
    label: str
    bucket: str
    horizon_trading_days: int
    cooldown_trading_days: int
    conditions: Tuple[Condition, ...]


BASE_RULES: Dict[str, Rule] = {
    "K06_RESILIENT_GOLD_VS_DXY_H120": Rule(
        "K06_RESILIENT_GOLD_VS_DXY_H120",
        "K06_RESILIENT_GOLD_VS_DXY",
        "stage77b_base",
        120,
        120,
        (
            Condition("gold_sma20_over_50", ">", 0.0),
            Condition("dxy_ret_20d", ">", 0.0),
            Condition("real_yield_change_20d", "<", 0.0),
        ),
    ),
    "K03_SAFE_HAVEN_REALYIELD_H120": Rule(
        "K03_SAFE_HAVEN_REALYIELD_H120",
        "K03_WGC_RISK_UNCERTAINTY_SAFE_HAVEN",
        "stage77b_base",
        120,
        120,
        (
            Condition("vix_change_20d", ">", 0.0),
            Condition("real_yield_change_20d", "<", 0.0),
        ),
    ),
    "K07_DXY_TREND_RELIEF_GOLD_TREND_H120": Rule(
        "K07_DXY_TREND_RELIEF_GOLD_TREND_H120",
        "K07_DXY_TREND_RELIEF_GOLD_TREND",
        "stage77b_base",
        120,
        120,
        (
            Condition("gold_sma20_over_50", ">", 0.0),
            Condition("dxy_sma20_over_50", "<", 0.0),
        ),
    ),
}


ORTHOGONAL_RULES: Dict[str, Rule] = {
    "S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120": Rule(
        "S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120",
        "REALYIELD_120D_DOWN_GOLD_NOT_TRENDING",
        "orthogonal_longer",
        120,
        120,
        (
            Condition("real_yield_change_120d", "<", 0.0),
            Condition("gold_sma20_over_50", "<", 0.0),
        ),
    ),
    "S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120": Rule(
        "S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120",
        "DXY_120D_DOWN_GOLD_NOT_TRENDING",
        "orthogonal_longer",
        120,
        120,
        (
            Condition("dxy_ret_120d", "<", 0.0),
            Condition("gold_sma20_over_50", "<", 0.0),
        ),
    ),
    # Other Stage83 rules are included for robust snapshots if the config asks for them.
    "S83_22_GOLD_60D_PULLBACK_CB_SUPPORT_H120": Rule(
        "S83_22_GOLD_60D_PULLBACK_CB_SUPPORT_H120",
        "GOLD_60D_PULLBACK_CB_SUPPORT",
        "orthogonal_pullback",
        120,
        120,
        (
            Condition("gold_ret_60d", "<", 0.0),
            Condition("central_bank_demand_tonnes_3m", ">", 0.0),
        ),
    ),
    "S83_21_GOLD_60D_PULLBACK_ETF_SUPPORT_H120": Rule(
        "S83_21_GOLD_60D_PULLBACK_ETF_SUPPORT_H120",
        "GOLD_60D_PULLBACK_ETF_SUPPORT",
        "orthogonal_pullback",
        120,
        120,
        (
            Condition("gold_ret_60d", "<", 0.0),
            Condition("etf_flow_tonnes_3m", ">", 0.0),
        ),
    ),
}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def ensure_numeric(df: pd.DataFrame, cols: List[str]) -> None:
    for c in cols:
        if c in df.columns:
            converted = pd.to_numeric(df[c], errors="coerce")
            # Preserve clearly non-numeric columns. If at least one value converts, use the numeric version.
            if converted.notna().any() or df[c].isna().all():
                df[c] = converted


def add_derived_features(df: pd.DataFrame, date_col: str, price_col: str) -> List[str]:
    added: List[str] = []
    numeric_candidates = [
        price_col,
        "gold_close",
        "dxy",
        "real_yield",
        "vix",
        "etf_flow_tonnes_3m",
        "central_bank_demand_tonnes_3m",
    ]
    ensure_numeric(df, numeric_candidates)

    def add_col(name: str, series: pd.Series) -> None:
        nonlocal added
        if name not in df.columns:
            df[name] = series
            added.append(name)

    if price_col in df.columns:
        add_col("gold_ret_20d", df[price_col].pct_change(20))
        add_col("gold_ret_60d", df[price_col].pct_change(60))
        add_col("gold_ret_120d", df[price_col].pct_change(120))
        if "gold_sma20_over_50" not in df.columns:
            sma20 = df[price_col].rolling(20).mean()
            sma50 = df[price_col].rolling(50).mean()
            df["gold_sma20_over_50"] = (sma20 / sma50) - 1.0
            added.append("gold_sma20_over_50")
    if "dxy" in df.columns:
        add_col("dxy_ret_20d", df["dxy"].pct_change(20))
        add_col("dxy_ret_60d", df["dxy"].pct_change(60))
        add_col("dxy_ret_120d", df["dxy"].pct_change(120))
        if "dxy_sma20_over_50" not in df.columns:
            sma20 = df["dxy"].rolling(20).mean()
            sma50 = df["dxy"].rolling(50).mean()
            df["dxy_sma20_over_50"] = (sma20 / sma50) - 1.0
            added.append("dxy_sma20_over_50")
    if "real_yield" in df.columns:
        add_col("real_yield_change_20d", df["real_yield"].diff(20))
        add_col("real_yield_change_60d", df["real_yield"].diff(60))
        add_col("real_yield_change_120d", df["real_yield"].diff(120))
    if "vix" in df.columns:
        add_col("vix_change_20d", df["vix"].diff(20))
        add_col("vix_change_60d", df["vix"].diff(60))
    return added


def eval_condition(series_value: Any, cond: Condition) -> Tuple[bool, str]:
    try:
        v = float(series_value)
    except Exception:
        return False, "missing"
    if pd.isna(v):
        return False, "missing"
    if cond.op == ">":
        ok = v > cond.threshold
    elif cond.op == "<":
        ok = v < cond.threshold
    elif cond.op == ">=":
        ok = v >= cond.threshold
    elif cond.op == "<=":
        ok = v <= cond.threshold
    else:
        raise ValueError(f"unsupported operator: {cond.op}")
    return bool(ok), "ok" if ok else f"{v}{cond.op}{cond.threshold}"


def rule_mask(df: pd.DataFrame, rule: Rule) -> Tuple[pd.Series, List[str], int]:
    required = [c.column for c in rule.conditions]
    missing_columns = [c for c in required if c not in df.columns]
    if missing_columns:
        return pd.Series(False, index=df.index), missing_columns, len(df)

    # Numeric conversion for required columns.
    ensure_numeric(df, required)

    complete = pd.Series(True, index=df.index)
    for c in required:
        complete &= df[c].notna()

    if complete.any():
        first_complete = int(complete[complete].index[0])
        missing_after_first = int((~complete.loc[first_complete:]).sum())
    else:
        first_complete = len(df)
        missing_after_first = len(df)

    mask = complete.copy()
    for cond in rule.conditions:
        if cond.op == ">":
            mask &= df[cond.column] > cond.threshold
        elif cond.op == "<":
            mask &= df[cond.column] < cond.threshold
        elif cond.op == ">=":
            mask &= df[cond.column] >= cond.threshold
        elif cond.op == "<=":
            mask &= df[cond.column] <= cond.threshold
        else:
            raise ValueError(f"unsupported operator: {cond.op}")
    return mask.fillna(False).astype(bool), [], missing_after_first


def latest_snapshot(df: pd.DataFrame, rule: Rule) -> Dict[str, Any]:
    row = df.iloc[-1]
    failures = []
    condition_results = []
    for cond in rule.conditions:
        if cond.column not in df.columns:
            passed = False
            reason = "missing_column"
            value = None
        else:
            value = row.get(cond.column)
            passed, reason = eval_condition(value, cond)
        condition_results.append({
            "column": cond.column,
            "operator": cond.op,
            "threshold": cond.threshold,
            "value": None if value is None or pd.isna(value) else float(value),
            "passed": passed,
            "reason": reason,
        })
        if not passed:
            failures.append(f"{cond.column}:{reason}")
    return {
        "rule_id": rule.rule_id,
        "label": rule.label,
        "latest_signal_active": len(failures) == 0,
        "latest_failures": "|".join(failures),
        "condition_results": condition_results,
    }


def union_mask(masks: Dict[str, pd.Series], rule_ids: List[str], index: pd.Index) -> pd.Series:
    u = pd.Series(False, index=index)
    for rid in rule_ids:
        if rid in masks:
            u |= masks[rid]
    return u.astype(bool)


def pct(num: int, den: int) -> float:
    return 0.0 if den == 0 else round(100.0 * num / den, 4)


def load_config(path: Path) -> Dict[str, Any]:
    cfg = read_json(path)
    cfg.setdefault("stage77b_summary_relpath", "reports/stage77b_corrected_portfolio_candidate_selection_historical_asof/stage77b_corrected_portfolio_candidate_selection_historical_asof_summary.json")
    cfg.setdefault("stage84_summary_relpath", "reports/stage84_hard_audit_stage83_orthogonal_shortlist/stage84_hard_audit_stage83_orthogonal_shortlist_summary.json")
    cfg.setdefault("macro_dataset_relpath", "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv")
    cfg.setdefault("date_col", "feature_date_utc")
    cfg.setdefault("price_col", "gold_close")
    cfg.setdefault("max_additions", 2)
    cfg.setdefault("max_overlap_with_current_pct", 35.0)
    cfg.setdefault("min_incremental_union_active_days", 150)
    cfg.setdefault("min_hard_audit_score", 3500.0)
    cfg.setdefault("min_final_holdout_mean_bps", 1200.0)
    cfg.setdefault("min_post_plus_final_mean_bps", 1200.0)
    cfg.setdefault("min_total_win_rate", 0.60)
    cfg.setdefault("selected_output_relpath", "reports/stage85_portfolio_increment_review/stage85_selected_for_stage86.csv")
    return cfg


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    cfg = load_config(Path(args.config))
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    stage77b_summary = read_json(root / cfg["stage77b_summary_relpath"])
    stage84_summary = read_json(root / cfg["stage84_summary_relpath"])
    macro_path = root / cfg["macro_dataset_relpath"]
    df = pd.read_csv(macro_path)

    date_col = cfg["date_col"]
    price_col = cfg["price_col"]
    if date_col not in df.columns:
        raise ValueError(f"date column not found: {date_col}")
    if price_col not in df.columns:
        raise ValueError(f"price column not found: {price_col}")

    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.sort_values(date_col).reset_index(drop=True)
    derived_added = add_derived_features(df, date_col, price_col)

    current_rule_ids = list(stage77b_summary.get("selected_rule_ids") or stage77b_summary.get("current_stage77b_rule_ids") or [])
    if not current_rule_ids:
        current_rule_ids = [
            "K06_RESILIENT_GOLD_VS_DXY_H120",
            "K03_SAFE_HAVEN_REALYIELD_H120",
            "K07_DXY_TREND_RELIEF_GOLD_TREND_H120",
        ]

    candidate_items = stage84_summary.get("selected_for_stage85", [])
    candidate_rule_ids = [x["rule_id"] for x in candidate_items]

    all_rules: Dict[str, Rule] = {**BASE_RULES, **ORTHOGONAL_RULES}
    masks: Dict[str, pd.Series] = {}
    mask_issues: Dict[str, Dict[str, Any]] = {}
    for rid in sorted(set(current_rule_ids + candidate_rule_ids)):
        if rid not in all_rules:
            mask_issues[rid] = {"missing_rule_definition": True}
            continue
        m, missing_cols, missing_rows = rule_mask(df, all_rules[rid])
        masks[rid] = m
        mask_issues[rid] = {
            "missing_rule_definition": False,
            "missing_columns": missing_cols,
            "unexpected_missing_required_feature_rows": missing_rows,
        }

    current_union = union_mask(masks, current_rule_ids, df.index)
    selected: List[Dict[str, Any]] = []
    review_rows: List[Dict[str, Any]] = []
    running_union = current_union.copy()

    # Pre-compute candidate metrics by rule_id from Stage84.
    metric_by_id = {x["rule_id"]: x for x in candidate_items}

    for item in sorted(candidate_items, key=lambda x: float(x.get("hard_audit_score", 0.0)), reverse=True):
        rid = item["rule_id"]
        rule = all_rules.get(rid)
        if rule is None or rid not in masks:
            review_rows.append({"rule_id": rid, "pass_stage85_increment_review": False, "fail_reasons": "MISSING_RULE_DEFINITION"})
            continue
        cmask = masks[rid]
        overlap_with_current = int((cmask & current_union).sum())
        active_days = int(cmask.sum())
        incremental_vs_current = int((cmask & ~current_union).sum())
        overlap_pct = pct(overlap_with_current, active_days)
        jaccard_pct = pct(int((cmask & current_union).sum()), int((cmask | current_union).sum()))
        incremental_vs_running = int((cmask & ~running_union).sum())

        fail: List[str] = []
        if overlap_pct > float(cfg["max_overlap_with_current_pct"]):
            fail.append("OVERLAP_WITH_CURRENT_TOO_HIGH")
        if incremental_vs_current < int(cfg["min_incremental_union_active_days"]):
            fail.append("INCREMENTAL_DAYS_TOO_LOW")
        if float(item.get("hard_audit_score", 0.0)) < float(cfg["min_hard_audit_score"]):
            fail.append("HARD_AUDIT_SCORE_TOO_LOW")
        if float(item.get("final_holdout_mean_net_bps", 0.0)) < float(cfg["min_final_holdout_mean_bps"]):
            fail.append("FINAL_HOLDOUT_MEAN_TOO_LOW")
        if float(item.get("post_plus_final_mean_net_bps", 0.0)) < float(cfg["min_post_plus_final_mean_bps"]):
            fail.append("POST_PLUS_FINAL_MEAN_TOO_LOW")
        if float(item.get("total_win_rate", 0.0)) < float(cfg["min_total_win_rate"]):
            fail.append("TOTAL_WIN_RATE_TOO_LOW")
        mi = mask_issues.get(rid, {})
        if mi.get("missing_columns"):
            fail.append("MISSING_COLUMNS")
        if int(mi.get("unexpected_missing_required_feature_rows", 0)) > 0:
            fail.append("UNEXPECTED_MISSING_REQUIRED_FEATURE_ROWS")

        selected_flag = False
        if not fail and len(selected) < int(cfg["max_additions"]):
            selected_flag = True
            running_union |= cmask
            selected.append({
                "rule_id": rid,
                "label": rule.label,
                "bucket": rule.bucket,
                "horizon_trading_days": rule.horizon_trading_days,
                "condition_text": " AND ".join([f"{c.column}{c.op}{c.threshold}" for c in rule.conditions]),
                "hard_audit_score": float(item.get("hard_audit_score", 0.0)),
                "total_mean_net_bps": float(item.get("total_mean_net_bps", 0.0)),
                "total_win_rate": float(item.get("total_win_rate", 0.0)),
                "final_holdout_mean_net_bps": float(item.get("final_holdout_mean_net_bps", 0.0)),
                "post_plus_final_mean_net_bps": float(item.get("post_plus_final_mean_net_bps", 0.0)),
                "max_overlap_with_current_portfolio_pct": overlap_pct,
                "incremental_union_active_days": incremental_vs_current,
                "latest_signal_active": bool(item.get("latest_signal_active", False)),
            })

        review_rows.append({
            "rule_id": rid,
            "label": rule.label,
            "bucket": rule.bucket,
            "hard_audit_score": float(item.get("hard_audit_score", 0.0)),
            "active_days": active_days,
            "current_union_active_days_before": int(current_union.sum()),
            "union_active_days_after_candidate": int((current_union | cmask).sum()),
            "incremental_union_active_days": incremental_vs_current,
            "incremental_union_active_days_vs_running": incremental_vs_running,
            "max_overlap_with_current_portfolio_pct": overlap_pct,
            "jaccard_with_current_portfolio_pct": jaccard_pct,
            "total_mean_net_bps": float(item.get("total_mean_net_bps", 0.0)),
            "total_win_rate": float(item.get("total_win_rate", 0.0)),
            "final_holdout_mean_net_bps": float(item.get("final_holdout_mean_net_bps", 0.0)),
            "post_plus_final_mean_net_bps": float(item.get("post_plus_final_mean_net_bps", 0.0)),
            "latest_signal_active": bool(item.get("latest_signal_active", False)),
            "pass_stage85_increment_review": selected_flag,
            "fail_reasons": "|".join(fail),
        })

    final_portfolio_rule_ids = current_rule_ids + [x["rule_id"] for x in selected]
    latest_snapshots = [latest_snapshot(df, all_rules[rid]) for rid in final_portfolio_rule_ids if rid in all_rules]
    latest_active_rule_ids = [s["rule_id"] for s in latest_snapshots if s["latest_signal_active"]]
    selected_rule_id = latest_active_rule_ids[0] if latest_active_rule_ids else None

    decision = (
        "STAGE85_PORTFOLIO_INCREMENT_SELECTED_FOR_OBSERVER_EXPANSION_NO_ORDER"
        if selected else
        "STAGE85_KEEP_STAGE77B_PORTFOLIO_ONLY_NO_ORDER"
    )
    classification = "S85_INCREMENT_SELECTED" if selected else "S85_NO_INCREMENT_SELECTED"
    disposition = "PORTFOLIO_INCREMENT_SELECTED_FOR_STAGE86_OBSERVER_EXPANSION" if selected else "KEEP_STAGE77B_PORTFOLIO_ONLY"

    review_csv = out / "stage85_portfolio_increment_review.csv"
    selected_csv = out / "stage85_selected_for_stage86.csv"
    latest_csv = out / "stage85_latest_signal_snapshot.csv"

    def write_rows(path: Path, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    write_rows(review_csv, review_rows)
    write_rows(selected_csv, selected)
    write_rows(latest_csv, latest_snapshots)

    summary = {
        "stage": "Stage85_PORTFOLIO_INCREMENT_REVIEW",
        "root": str(root),
        "config": str(Path(args.config).resolve()),
        "generated_utc": utc_now(),
        "status": "STAGE85_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "principle": "Review Stage84 orthogonal hard-audit survivors for incremental portfolio contribution before any observer-only portfolio expansion. No orders, no broker connection, no EA change.",
        "macro_dataset": {
            "path": str(macro_path),
            "rows": int(len(df)),
            "date_col": date_col,
            "price_col": price_col,
            "min_date": str(df[date_col].min().date()),
            "max_date": str(df[date_col].max().date()),
            "sha256": sha256_file(macro_path),
            "derived_features_added": derived_added,
        },
        "current_stage77b_rule_ids": current_rule_ids,
        "stage84_candidate_rule_ids": candidate_rule_ids,
        "candidate_count": len(candidate_rule_ids),
        "selected_count": len(selected),
        "selected_rule_ids": [x["rule_id"] for x in selected],
        "selected_for_stage86": selected,
        "final_review_portfolio_rule_ids": final_portfolio_rule_ids,
        "current_union_active_days": int(current_union.sum()),
        "final_union_active_days_after_selected_additions": int(running_union.sum()),
        "incremental_union_active_days_selected": int((running_union & ~current_union).sum()),
        "latest_signal_snapshot": latest_snapshots,
        "latest_active_rule_ids_in_review_portfolio": latest_active_rule_ids,
        "latest_selected_rule_id": selected_rule_id,
        "constraints": {
            "max_additions": int(cfg["max_additions"]),
            "max_overlap_with_current_pct": float(cfg["max_overlap_with_current_pct"]),
            "min_incremental_union_active_days": int(cfg["min_incremental_union_active_days"]),
            "min_hard_audit_score": float(cfg["min_hard_audit_score"]),
            "min_final_holdout_mean_bps": float(cfg["min_final_holdout_mean_bps"]),
            "min_post_plus_final_mean_bps": float(cfg["min_post_plus_final_mean_bps"]),
            "min_total_win_rate": float(cfg["min_total_win_rate"]),
        },
        "issues": [],
        "hard_blocks": [
            "NO_AUTOMATED_ORDER",
            "NO_PAPER_ORDER",
            "NO_BROKER_CONNECTION",
            "NO_EA_PROMOTION",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_ORDER_AUTHORIZATION_FROM_STAGE85",
            "NO_THRESHOLD_TUNING_FROM_STAGE85_PORTFOLIO_REVIEW",
            "NO_DIRECT_MT5_OR_EA_CHANGE_FROM_STAGE85",
        ],
        "outputs": {
            "summary_json": str(out / "stage85_portfolio_increment_review_summary.json"),
            "report_md": str(out / "stage85_portfolio_increment_review_report.md"),
            "review_csv": str(review_csv),
            "selected_csv": str(selected_csv),
            "latest_signal_snapshot_csv": str(latest_csv),
        },
    }

    report_lines = [
        "# Stage85 Portfolio Increment Review",
        "",
        "## Decision",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- classification: `{summary['classification']}`",
        f"- disposition: `{summary['disposition']}`",
        "",
        "## Current Stage77B portfolio",
        *[f"- `{rid}`" for rid in current_rule_ids],
        "",
        "## Stage84 survivors reviewed",
        *[f"- `{rid}`" for rid in candidate_rule_ids],
        "",
        "## Selected for Stage86 observer expansion",
        *([f"- `{x['rule_id']}`: {x['label']} overlap=`{x['max_overlap_with_current_portfolio_pct']}` incremental_days=`{x['incremental_union_active_days']}` latest_active=`{x['latest_signal_active']}`" for x in selected] or ["- none"]),
        "",
        "## Candidate snapshot",
    ]
    for r in review_rows:
        report_lines.append(
            f"- `{r['rule_id']}` pass=`{r['pass_stage85_increment_review']}` "
            f"overlap=`{r['max_overlap_with_current_portfolio_pct']}` "
            f"incremental_days=`{r['incremental_union_active_days']}` "
            f"score=`{r['hard_audit_score']}` latest_active=`{r['latest_signal_active']}` "
            f"fail=`{r['fail_reasons']}`"
        )
    report_lines += [
        "",
        "## Latest signal snapshot",
        *[f"- `{s['rule_id']}` active=`{s['latest_signal_active']}` failures=`{s['latest_failures']}`" for s in latest_snapshots],
        "",
        "## Hard blocks",
        *[f"- `{x}`" for x in summary["hard_blocks"]],
        "",
    ]

    write_json(out / "stage85_portfolio_increment_review_summary.json", summary)
    (out / "stage85_portfolio_increment_review_report.md").write_text("\n".join(report_lines), encoding="utf-8")
    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "decision": summary["decision"],
        "summary_json": summary["outputs"]["summary_json"],
        "report_md": summary["outputs"]["report_md"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
