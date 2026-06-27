#!/usr/bin/env python3
"""Stage84 hard audit for Stage83 orthogonal thesis shortlist.

No trading, no broker connection, no EA/MT5 mutation. This script replays the
Stage83 shortlist against the lag-safe macro dataset, applies stricter gates,
and emits candidates for a later portfolio-increment review.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import operator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

OPS = {
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
}

STAGE83_RULES: List[Dict[str, Any]] = [
    {
        "rule_id": "S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120",
        "label": "REALYIELD_120D_DOWN_GOLD_NOT_TRENDING",
        "bucket": "longer_orthogonal",
        "horizon_trading_days": 120,
        "cooldown_trading_days": 120,
        "conditions": [("real_yield_change_120d", "<", 0.0), ("gold_sma20_over_50", "<", 0.0)],
    },
    {
        "rule_id": "S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120",
        "label": "DXY_120D_DOWN_GOLD_NOT_TRENDING",
        "bucket": "longer_orthogonal",
        "horizon_trading_days": 120,
        "cooldown_trading_days": 120,
        "conditions": [("dxy_ret_120d", "<", 0.0), ("gold_sma20_over_50", "<", 0.0)],
    },
    {
        "rule_id": "S83_22_GOLD_60D_PULLBACK_CB_SUPPORT_H120",
        "label": "GOLD_60D_PULLBACK_CB_SUPPORT",
        "bucket": "long_pullback_cb",
        "horizon_trading_days": 120,
        "cooldown_trading_days": 120,
        "conditions": [("gold_ret_60d", "<", 0.0), ("central_bank_demand_tonnes_3m", ">", 0.0)],
    },
    {
        "rule_id": "S83_21_GOLD_60D_PULLBACK_ETF_SUPPORT_H120",
        "label": "GOLD_60D_PULLBACK_ETF_SUPPORT",
        "bucket": "long_pullback_flow",
        "horizon_trading_days": 120,
        "cooldown_trading_days": 120,
        "conditions": [("gold_ret_60d", "<", 0.0), ("etf_flow_tonnes_3m", ">", 0.0)],
    },
    {
        "rule_id": "S83_24_REALYIELD_120D_DOWN_CB_SUPPORT_GOLD_PULLBACK_H120",
        "label": "REALYIELD_120D_DOWN_CB_SUPPORT_GOLD_PULLBACK",
        "bucket": "longer_orthogonal",
        "horizon_trading_days": 120,
        "cooldown_trading_days": 120,
        "conditions": [("real_yield_change_120d", "<", 0.0), ("central_bank_demand_tonnes_3m", ">", 0.0), ("gold_ret_20d", "<", 0.0)],
    },
    {
        "rule_id": "S83_23_DXY_120D_DOWN_ETF_SUPPORT_GOLD_PULLBACK_H120",
        "label": "DXY_120D_DOWN_ETF_SUPPORT_GOLD_PULLBACK",
        "bucket": "longer_orthogonal",
        "horizon_trading_days": 120,
        "cooldown_trading_days": 120,
        "conditions": [("dxy_ret_120d", "<", 0.0), ("etf_flow_tonnes_3m", ">", 0.0), ("gold_ret_20d", "<", 0.0)],
    },
    {
        "rule_id": "S83_16_CB_DEMAND_CHANGE_POS_GOLD_PULLBACK_H60",
        "label": "CB_DEMAND_CHANGE_POS_GOLD_PULLBACK",
        "bucket": "cb_acceleration",
        "horizon_trading_days": 60,
        "cooldown_trading_days": 60,
        "conditions": [("central_bank_demand_change_20d", ">", 0.0), ("gold_ret_20d", "<", 0.0)],
    },
    {
        "rule_id": "S83_05_RISKOFF_GOLD_PULLBACK_H60",
        "label": "RISKOFF_GOLD_PULLBACK",
        "bucket": "safe_haven_pullback",
        "horizon_trading_days": 60,
        "cooldown_trading_days": 60,
        "conditions": [("vix_change_20d", ">", 0.0), ("gold_ret_20d", "<", 0.0)],
    },
]

CURRENT_PORTFOLIO_RULES: List[Dict[str, Any]] = [
    {
        "rule_id": "K06_RESILIENT_GOLD_VS_DXY_H120",
        "label": "K06_RESILIENT_GOLD_VS_DXY",
        "conditions": [("gold_sma20_over_50", ">", 0.0), ("dxy_ret_20d", ">", 0.0), ("real_yield_change_20d", "<", 0.0)],
    },
    {
        "rule_id": "K03_SAFE_HAVEN_REALYIELD_H120",
        "label": "K03_WGC_RISK_UNCERTAINTY_SAFE_HAVEN",
        "conditions": [("vix_change_20d", ">", 0.0), ("real_yield_change_20d", "<", 0.0)],
    },
    {
        "rule_id": "K07_DXY_TREND_RELIEF_GOLD_TREND_H120",
        "label": "K07_DXY_TREND_RELIEF_GOLD_TREND",
        "conditions": [("gold_sma20_over_50", ">", 0.0), ("dxy_sma20_over_50", "<", 0.0)],
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_path(root: Path, p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else root / path


def safe_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def add_derived_features(df: pd.DataFrame) -> List[str]:
    added: List[str] = []
    for col in df.columns:
        if col.endswith("_utc") or col in {"source", "symbol", "timeframe", "stage", "rule_id", "label"}:
            continue
        if df[col].dtype == object:
            converted = safe_num(df[col])
            if converted.notna().sum() > 0:
                df[col] = converted

    if "gold_close" in df.columns:
        gold = safe_num(df["gold_close"])
        for n in (20, 60, 120):
            col = f"gold_ret_{n}d"
            if col not in df.columns:
                df[col] = gold.pct_change(n)
                added.append(col)
        if "gold_sma20_over_50" not in df.columns:
            sma20 = gold.rolling(20, min_periods=20).mean()
            sma50 = gold.rolling(50, min_periods=50).mean()
            df["gold_sma20_over_50"] = (sma20 / sma50) - 1.0
            added.append("gold_sma20_over_50")
        if "gold_realized_vol_20d" not in df.columns:
            df["gold_realized_vol_20d"] = gold.pct_change().rolling(20, min_periods=20).std()
            added.append("gold_realized_vol_20d")

    if "dxy" in df.columns:
        dxy = safe_num(df["dxy"])
        for n in (20, 60, 120):
            col = f"dxy_ret_{n}d"
            if col not in df.columns:
                df[col] = dxy.pct_change(n)
                added.append(col)
        if "dxy_sma20_over_50" not in df.columns:
            sma20 = dxy.rolling(20, min_periods=20).mean()
            sma50 = dxy.rolling(50, min_periods=50).mean()
            df["dxy_sma20_over_50"] = (sma20 / sma50) - 1.0
            added.append("dxy_sma20_over_50")

    if "real_yield" in df.columns:
        ry = safe_num(df["real_yield"])
        for n in (20, 60, 120):
            col = f"real_yield_change_{n}d"
            if col not in df.columns:
                df[col] = ry.diff(n)
                added.append(col)

    if "vix" in df.columns:
        vix = safe_num(df["vix"])
        for n in (20, 60):
            col = f"vix_change_{n}d"
            if col not in df.columns:
                df[col] = vix.diff(n)
                added.append(col)
        if "vix_ret_20d" not in df.columns:
            df["vix_ret_20d"] = vix.pct_change(20)
            added.append("vix_ret_20d")

    if "etf_flow_tonnes_3m" in df.columns:
        etf = safe_num(df["etf_flow_tonnes_3m"])
        if "etf_flow_change_20d" not in df.columns:
            df["etf_flow_change_20d"] = etf.diff(20)
            added.append("etf_flow_change_20d")
        if "etf_flow_positive" not in df.columns:
            df["etf_flow_positive"] = (etf > 0).astype(float)
            added.append("etf_flow_positive")

    if "central_bank_demand_tonnes_3m" in df.columns:
        cb = safe_num(df["central_bank_demand_tonnes_3m"])
        if "central_bank_demand_change_20d" not in df.columns:
            df["central_bank_demand_change_20d"] = cb.diff(20)
            added.append("central_bank_demand_change_20d")
        if "central_bank_demand_positive" not in df.columns:
            df["central_bank_demand_positive"] = (cb > 0).astype(float)
            added.append("central_bank_demand_positive")

    return added


def condition_text(conditions: Sequence[Tuple[str, str, float]]) -> str:
    return " AND ".join([f"{c}{op}{thr:g}" for c, op, thr in conditions])


def evaluate_rule(df: pd.DataFrame, conditions: Sequence[Tuple[str, str, float]]) -> Tuple[pd.Series, List[str], int, int, List[Dict[str, Any]], str]:
    masks = []
    missing_cols: List[str] = []
    condition_results_latest: List[Dict[str, Any]] = []
    for col, op, threshold in conditions:
        if col not in df.columns:
            missing_cols.append(col)
            masks.append(pd.Series(False, index=df.index))
            condition_results_latest.append({"column": col, "operator": op, "threshold": threshold, "value": None, "passed": False, "reason": "missing_column"})
            continue
        vals = safe_num(df[col])
        masks.append(OPS[op](vals, threshold).fillna(False))
        latest_val = vals.iloc[-1] if len(vals) else math.nan
        latest_pass = bool(OPS[op](latest_val, threshold)) if pd.notna(latest_val) else False
        condition_results_latest.append({
            "column": col,
            "operator": op,
            "threshold": threshold,
            "value": None if pd.isna(latest_val) else float(latest_val),
            "passed": latest_pass,
            "reason": "ok" if latest_pass else ("nan" if pd.isna(latest_val) else f"{latest_val}{op}{threshold}"),
        })
    if not masks:
        active = pd.Series(False, index=df.index)
    else:
        active = masks[0].copy()
        for m in masks[1:]:
            active = active & m
    required_cols = [c for c, _, _ in conditions if c in df.columns]
    if required_cols:
        complete = df[required_cols].notna().all(axis=1)
        if complete.any():
            first_complete_idx = int(complete.idxmax())
            missing_required_after = int((~complete.loc[first_complete_idx:]).sum())
            warmup_missing_rows_ignored = int((~complete.loc[:first_complete_idx]).sum())
        else:
            first_complete_idx = -1
            missing_required_after = len(df)
            warmup_missing_rows_ignored = len(df)
    else:
        first_complete_idx = -1
        missing_required_after = len(df)
        warmup_missing_rows_ignored = 0
    failures = [f"{r['column']}:{r['reason']}" for r in condition_results_latest if not r["passed"]]
    return active, missing_cols, missing_required_after, warmup_missing_rows_ignored, condition_results_latest, "|".join(failures)


def entry_indices(active: pd.Series, cooldown: int) -> List[int]:
    out: List[int] = []
    last = -10**9
    for i, flag in enumerate(active.tolist()):
        if bool(flag) and (i - last >= cooldown):
            out.append(i)
            last = i
    return out


def build_returns(df: pd.DataFrame, price_col: str, date_col: str, active: pd.Series, horizon: int, cooldown: int, cost_bps: float) -> Tuple[List[Dict[str, Any]], int]:
    prices = safe_num(df[price_col])
    dates = pd.to_datetime(df[date_col], utc=True, errors="coerce")
    rows: List[Dict[str, Any]] = []
    lookahead_violations = 0
    for idx in entry_indices(active, cooldown):
        exit_idx = idx + horizon
        if exit_idx >= len(df):
            continue
        ep = prices.iloc[idx]
        xp = prices.iloc[exit_idx]
        if pd.isna(ep) or pd.isna(xp) or ep == 0:
            continue
        if dates.iloc[exit_idx] <= dates.iloc[idx]:
            lookahead_violations += 1
        gross = ((float(xp) / float(ep)) - 1.0) * 10000.0
        net = gross - cost_bps
        rows.append({
            "entry_index": idx,
            "exit_index": exit_idx,
            "entry_date_utc": dates.iloc[idx].date().isoformat(),
            "exit_date_utc": dates.iloc[exit_idx].date().isoformat(),
            "entry_price": float(ep),
            "exit_price": float(xp),
            "gross_return_bps": round(gross, 4),
            "net_return_bps": round(net, 4),
            "entry_year": int(dates.iloc[idx].year),
        })
    return rows, lookahead_violations


def metric_summary(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    vals = [float(r["net_return_bps"]) for r in rows]
    if not vals:
        return {"entry_count": 0, "mean_net_bps": None, "median_net_bps": None, "win_rate": None, "min_net_bps": None, "max_net_bps": None, "total_net_bps": 0.0}
    s = pd.Series(vals, dtype=float)
    return {
        "entry_count": int(len(vals)),
        "mean_net_bps": round(float(s.mean()), 4),
        "median_net_bps": round(float(s.median()), 4),
        "win_rate": round(float((s > 0).mean()), 4),
        "min_net_bps": round(float(s.min()), 4),
        "max_net_bps": round(float(s.max()), 4),
        "total_net_bps": round(float(s.sum()), 4),
    }


def rows_between(rows: Sequence[Dict[str, Any]], start: str, end: str) -> List[Dict[str, Any]]:
    start_d = pd.Timestamp(start, tz="UTC")
    end_d = pd.Timestamp(end, tz="UTC")
    out = []
    for r in rows:
        d = pd.Timestamp(r["entry_date_utc"], tz="UTC")
        if start_d <= d <= end_d:
            out.append(r)
    return out


def overlap_pct(a: pd.Series, b: pd.Series) -> float:
    denom = int(a.sum())
    if denom <= 0:
        return 0.0
    return round(float((a & b).sum()) / float(denom) * 100.0, 4)


def jaccard_pct(a: pd.Series, b: pd.Series) -> float:
    union = int((a | b).sum())
    if union <= 0:
        return 0.0
    return round(float((a & b).sum()) / float(union) * 100.0, 4)


def year_share(rows: Sequence[Dict[str, Any]]) -> Tuple[Optional[int], float]:
    if not rows:
        return None, 0.0
    counts: Dict[int, int] = {}
    for r in rows:
        y = int(r["entry_year"])
        counts[y] = counts.get(y, 0) + 1
    y, c = max(counts.items(), key=lambda kv: kv[1])
    return y, round(c / len(rows), 4)


def fail_if(metrics: Dict[str, Any], constraints: Dict[str, Any]) -> List[str]:
    f: List[str] = []
    def val(k: str, default: float = 0.0) -> float:
        x = metrics.get(k)
        return default if x is None else float(x)
    if val("total_entry_count") < constraints["min_total_entries"]: f.append("TOTAL_ENTRIES_TOO_LOW")
    if val("total_mean_net_bps") < constraints["min_total_mean_net_bps"]: f.append("TOTAL_MEAN_TOO_LOW")
    if val("total_median_net_bps") < constraints["min_total_median_net_bps"]: f.append("TOTAL_MEDIAN_TOO_LOW")
    if val("total_win_rate") < constraints["min_total_win_rate"]: f.append("WIN_RATE_TOO_LOW")
    if abs(val("total_min_net_return_bps")) > constraints["max_abs_worst_loss_bps"]: f.append("WORST_LOSS_TOO_LARGE")
    if val("validation_entries") < constraints["min_validation_entries"]: f.append("VALIDATION_ENTRIES_TOO_LOW")
    if val("validation_mean_net_bps") < constraints["min_validation_mean_bps"]: f.append("VALIDATION_MEAN_TOO_LOW")
    if val("locked_forward_entries") < constraints["min_locked_forward_entries"]: f.append("LOCKED_FORWARD_ENTRIES_TOO_LOW")
    if val("locked_forward_mean_net_bps") < constraints["min_locked_forward_mean_bps"]: f.append("LOCKED_FORWARD_MEAN_TOO_LOW")
    if val("final_holdout_entries") < constraints["min_final_holdout_entries"]: f.append("FINAL_HOLDOUT_ENTRIES_TOO_LOW")
    if val("final_holdout_mean_net_bps") < constraints["min_final_holdout_mean_bps"]: f.append("FINAL_HOLDOUT_MEAN_TOO_LOW")
    if val("post_plus_final_entries") < constraints["min_post_plus_final_entries"]: f.append("POST_PLUS_FINAL_ENTRIES_TOO_LOW")
    if val("post_plus_final_mean_net_bps") < constraints["min_post_plus_final_mean_bps"]: f.append("POST_PLUS_FINAL_MEAN_TOO_LOW")
    if val("max_year_entry_share") > constraints["max_year_entry_share"]: f.append("YEAR_CONCENTRATION_TOO_HIGH")
    if val("max_overlap_with_current_portfolio_pct") > constraints["max_overlap_with_current_portfolio_pct"]: f.append("OVERLAP_WITH_CURRENT_PORTFOLIO_TOO_HIGH")
    if val("incremental_union_active_days") < constraints["min_incremental_union_active_days"]: f.append("INCREMENTAL_ACTIVE_DAYS_TOO_LOW")
    if val("missing_required_feature_rows") > constraints["max_missing_required_feature_rows"]: f.append("MISSING_REQUIRED_FEATURE_ROWS")
    if val("lookahead_violations") > constraints["max_lookahead_violations"]: f.append("LOOKAHEAD_VIOLATIONS")
    return f


def write_csv(path: Path, rows: Sequence[Dict[str, Any]], fieldnames: Optional[Sequence[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys: List[str] = []
        for r in rows:
            for k in r.keys():
                if k not in keys:
                    keys.append(k)
        fieldnames = keys
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fieldnames), extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    cfg = load_json(resolve_path(root, args.config))
    out_dir = resolve_path(root, args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    macro_path = resolve_path(root, cfg["macro_dataset_path"])
    stage83_path = resolve_path(root, cfg["stage83_summary_path"])
    stage83 = load_json(stage83_path) if stage83_path.exists() else {}
    df = pd.read_csv(macro_path)
    date_col = cfg.get("date_col", "feature_date_utc")
    price_col = cfg.get("price_col", "gold_close")
    if date_col not in df.columns:
        raise SystemExit(f"missing date column: {date_col}")
    if price_col not in df.columns:
        raise SystemExit(f"missing price column: {price_col}")
    df[date_col] = pd.to_datetime(df[date_col], utc=True, errors="coerce").dt.date.astype(str)
    df = df.sort_values(date_col).reset_index(drop=True)
    added = add_derived_features(df)

    current_masks: Dict[str, pd.Series] = {}
    for r in CURRENT_PORTFOLIO_RULES:
        m, *_ = evaluate_rule(df, r["conditions"])
        current_masks[r["rule_id"]] = m
    current_union = pd.Series(False, index=df.index)
    for m in current_masks.values():
        current_union = current_union | m

    shortlist_ids = set(stage83.get("shortlist_rule_ids") or [r["rule_id"] for r in STAGE83_RULES])
    rules = [r for r in STAGE83_RULES if r["rule_id"] in shortlist_ids]

    metrics_rows: List[Dict[str, Any]] = []
    entry_return_rows: List[Dict[str, Any]] = []
    active_masks: Dict[str, pd.Series] = {}

    splits = cfg["splits"]
    constraints = cfg["constraints"]
    asof = pd.Timestamp(cfg.get("asof_date_utc", "2024-01-01"), tz="UTC")
    cost = float(cfg.get("cost_bps_total_reference", 50.0))

    for r in rules:
        active, missing_cols, missing_required, warmup_ignored, latest_cond, latest_failures = evaluate_rule(df, r["conditions"])
        active_masks[r["rule_id"]] = active
        returns, lookahead = build_returns(df, price_col, date_col, active, int(r["horizon_trading_days"]), int(r["cooldown_trading_days"]), cost)
        for row in returns:
            entry_return_rows.append({"rule_id": r["rule_id"], "label": r["label"], **row})
        total = metric_summary(returns)
        train = metric_summary(rows_between(returns, *splits["TRAIN_DISCOVERY"]))
        val = metric_summary(rows_between(returns, *splits["VALIDATION_SELECTION"]))
        locked = metric_summary(rows_between(returns, *splits["LOCKED_HISTORICAL_FORWARD"]))
        final = metric_summary(rows_between(returns, *splits["FINAL_STATISTICAL_HOLDOUT"]))
        pre = [x for x in returns if pd.Timestamp(x["exit_date_utc"], tz="UTC") < asof]
        post = [x for x in returns if pd.Timestamp(x["entry_date_utc"], tz="UTC") >= asof]
        post_plus_final = final["entry_count"] and rows_between(returns, *splits["FINAL_STATISTICAL_HOLDOUT"]) or post
        y, ys = year_share(returns)
        ov = max([overlap_pct(active, cm) for cm in current_masks.values()] or [0.0])
        jac = max([jaccard_pct(active, cm) for cm in current_masks.values()] or [0.0])
        after_union = current_union | active
        inc_days = int(after_union.sum() - current_union.sum())
        latest_active = bool(active.iloc[-1]) if len(active) else False

        row = {
            "rule_id": r["rule_id"],
            "label": r["label"],
            "bucket": r["bucket"],
            "horizon_trading_days": r["horizon_trading_days"],
            "cooldown_trading_days": r["cooldown_trading_days"],
            "condition_text": condition_text(r["conditions"]),
            "missing_columns": "|".join(missing_cols),
            "missing_required_feature_rows": missing_required,
            "warmup_missing_rows_ignored": warmup_ignored,
            "lookahead_violations": lookahead,
            "active_days": int(active.sum()),
            "current_union_active_days_before": int(current_union.sum()),
            "current_union_active_days_after_candidate": int(after_union.sum()),
            "incremental_union_active_days": inc_days,
            "max_overlap_with_current_portfolio_pct": ov,
            "max_jaccard_with_current_portfolio_pct": jac,
            "latest_signal_active": latest_active,
            "latest_failures": latest_failures,
            "max_entry_year": y,
            "max_year_entry_share": ys,
            "total_entry_count": total["entry_count"],
            "total_mean_net_bps": total["mean_net_bps"],
            "total_median_net_bps": total["median_net_bps"],
            "total_win_rate": total["win_rate"],
            "total_min_net_return_bps": total["min_net_bps"],
            "total_max_net_return_bps": total["max_net_bps"],
            "total_total_net_return_bps": total["total_net_bps"],
            "train_entries": train["entry_count"],
            "train_mean_net_bps": train["mean_net_bps"],
            "train_median_net_bps": train["median_net_bps"],
            "train_win_rate": train["win_rate"],
            "validation_entries": val["entry_count"],
            "validation_mean_net_bps": val["mean_net_bps"],
            "validation_median_net_bps": val["median_net_bps"],
            "validation_win_rate": val["win_rate"],
            "locked_forward_entries": locked["entry_count"],
            "locked_forward_mean_net_bps": locked["mean_net_bps"],
            "locked_forward_median_net_bps": locked["median_net_bps"],
            "locked_forward_win_rate": locked["win_rate"],
            "final_holdout_entries": final["entry_count"],
            "final_holdout_mean_net_bps": final["mean_net_bps"],
            "final_holdout_median_net_bps": final["median_net_bps"],
            "final_holdout_win_rate": final["win_rate"],
            "pre_asof_entries": metric_summary(pre)["entry_count"],
            "pre_asof_mean_net_bps": metric_summary(pre)["mean_net_bps"],
            "pre_asof_median_net_bps": metric_summary(pre)["median_net_bps"],
            "pre_asof_win_rate": metric_summary(pre)["win_rate"],
            "post_asof_entries": metric_summary(post)["entry_count"],
            "post_asof_mean_net_bps": metric_summary(post)["mean_net_bps"],
            "post_asof_median_net_bps": metric_summary(post)["median_net_bps"],
            "post_asof_win_rate": metric_summary(post)["win_rate"],
            "post_plus_final_entries": metric_summary(post_plus_final)["entry_count"],
            "post_plus_final_mean_net_bps": metric_summary(post_plus_final)["mean_net_bps"],
            "post_plus_final_median_net_bps": metric_summary(post_plus_final)["median_net_bps"],
            "post_plus_final_win_rate": metric_summary(post_plus_final)["win_rate"],
        }
        fails = fail_if(row, constraints)
        score = 0.0
        for k, w in [
            ("post_plus_final_mean_net_bps", 1.0),
            ("final_holdout_mean_net_bps", 0.8),
            ("locked_forward_mean_net_bps", 0.4),
            ("total_mean_net_bps", 0.4),
            ("incremental_union_active_days", 0.5),
        ]:
            v = row.get(k)
            score += 0.0 if v is None else float(v) * w
        score -= float(row["max_overlap_with_current_portfolio_pct"]) * 10.0
        row["pass_hard_audit_candidate"] = len(fails) == 0
        row["hard_fail_reasons"] = "|".join(fails)
        row["hard_audit_score"] = round(score, 4)
        metrics_rows.append(row)

    metrics_rows.sort(key=lambda x: float(x.get("hard_audit_score") or 0), reverse=True)

    selected: List[Dict[str, Any]] = []
    max_selected = int(cfg.get("selection", {}).get("max_selected_for_stage85", 3))
    max_pair = float(cfg.get("selection", {}).get("max_pairwise_selected_overlap_pct", 45.0))
    for row in metrics_rows:
        if not row.get("pass_hard_audit_candidate"):
            continue
        candidate_mask = active_masks[row["rule_id"]]
        pair_ok = True
        for chosen in selected:
            pair = max(overlap_pct(candidate_mask, active_masks[chosen["rule_id"]]), overlap_pct(active_masks[chosen["rule_id"]], candidate_mask))
            if pair > max_pair:
                pair_ok = False
                row["selection_skip_reason"] = f"PAIRWISE_OVERLAP_TOO_HIGH_WITH_{chosen['rule_id']}:{pair}"
                break
        if pair_ok:
            row["selection_skip_reason"] = ""
            selected.append(row)
        if len(selected) >= max_selected:
            break

    latest_snapshot: List[Dict[str, Any]] = []
    for row in metrics_rows:
        latest_snapshot.append({
            "rule_id": row["rule_id"],
            "label": row["label"],
            "latest_signal_active": row["latest_signal_active"],
            "latest_failures": row["latest_failures"],
        })

    decision = "STAGE84_NO_ORTHOGONAL_HARD_AUDIT_SURVIVOR_NO_ORDER"
    classification = "S84_NO_HARD_AUDIT_SURVIVOR"
    disposition = "NO_ORTHOGONAL_CANDIDATE_SURVIVES_HARD_AUDIT"
    if selected:
        decision = "STAGE84_ORTHOGONAL_HARD_AUDIT_SHORTLIST_READY_FOR_PORTFOLIO_REVIEW_NO_ORDER"
        classification = "S84_ORTHOGONAL_HARD_AUDIT_SHORTLIST_READY"
        disposition = "ORTHOGONAL_HARD_AUDIT_SHORTLIST_READY_FOR_STAGE85"

    report_path = out_dir / "stage84_hard_audit_stage83_orthogonal_shortlist_report.md"
    summary_path = out_dir / "stage84_hard_audit_stage83_orthogonal_shortlist_summary.json"
    metrics_path = out_dir / "stage84_hard_audit_metrics.csv"
    selected_path = out_dir / "stage84_selected_for_stage85.csv"
    entry_path = out_dir / "stage84_hard_audit_entry_returns.csv"
    snapshot_path = out_dir / "stage84_latest_signal_snapshot.csv"

    write_csv(metrics_path, metrics_rows)
    write_csv(selected_path, selected, fieldnames=list(metrics_rows[0].keys()) if metrics_rows else [])
    write_csv(entry_path, entry_return_rows)
    write_csv(snapshot_path, latest_snapshot)

    summary = {
        "stage": "Stage84_HARD_AUDIT_STAGE83_ORTHOGONAL_SHORTLIST",
        "root": str(root),
        "config": str(resolve_path(root, args.config)),
        "generated_utc": utc_now(),
        "status": "STAGE84_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "principle": "Hard-audit Stage83 orthogonal discovery shortlist before any observer-portfolio expansion. No orders, no broker connection, no EA change.",
        "stage83_decision_reference": stage83.get("decision"),
        "macro_dataset": {
            "path": str(macro_path),
            "rows": int(len(df)),
            "date_col": date_col,
            "price_col": price_col,
            "min_date": str(df[date_col].min()),
            "max_date": str(df[date_col].max()),
            "sha256": sha256_file(macro_path),
            "derived_features_added": added,
        },
        "candidate_count": len(metrics_rows),
        "pass_hard_audit_count": int(sum(bool(r["pass_hard_audit_candidate"]) for r in metrics_rows)),
        "selected_count": len(selected),
        "selected_rule_ids": [r["rule_id"] for r in selected],
        "selected_for_stage85": selected,
        "latest_signal_snapshot": latest_snapshot,
        "constraints": constraints,
        "hard_blocks": cfg.get("hard_blocks", []),
        "outputs": {
            "summary_json": str(summary_path),
            "report_md": str(report_path),
            "metrics_csv": str(metrics_path),
            "selected_csv": str(selected_path),
            "entry_returns_csv": str(entry_path),
            "latest_signal_snapshot_csv": str(snapshot_path),
        },
    }
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    lines = [
        "# Stage84 Hard Audit - Stage83 Orthogonal Shortlist",
        "",
        "## Decision",
        f"- status: `STAGE84_COMPLETE_NO_PROMOTION`",
        f"- decision: `{decision}`",
        f"- classification: `{classification}`",
        f"- disposition: `{disposition}`",
        "",
        "## Selected for Stage85",
    ]
    if selected:
        for r in selected:
            lines.append(f"- `{r['rule_id']}`: {r['label']} score=`{r['hard_audit_score']}` mean=`{r['total_mean_net_bps']}` locked=`{r['locked_forward_mean_net_bps']}` final=`{r['final_holdout_mean_net_bps']}` post_plus_final=`{r['post_plus_final_mean_net_bps']}` latest_active=`{r['latest_signal_active']}`")
    else:
        lines.append("- none")
    lines += ["", "## Candidate snapshot"]
    for r in metrics_rows:
        lines.append(f"- `{r['rule_id']}` pass=`{r['pass_hard_audit_candidate']}` score=`{r['hard_audit_score']}` mean=`{r['total_mean_net_bps']}` median=`{r['total_median_net_bps']}` win=`{r['total_win_rate']}` worst=`{r['total_min_net_return_bps']}` overlap=`{r['max_overlap_with_current_portfolio_pct']}` incremental_days=`{r['incremental_union_active_days']}` latest_active=`{r['latest_signal_active']}` fail=`{r['hard_fail_reasons']}`")
    lines += ["", "## Hard blocks"] + [f"- `{x}`" for x in cfg.get("hard_blocks", [])]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "decision": decision,
        "selected_count": len(selected),
        "summary_json": str(summary_path),
        "report_md": str(report_path),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
