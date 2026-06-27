#!/usr/bin/env python3
"""
Stage105 - Second-order COT/Macro thesis discovery.

Purpose:
  Continue thesis discovery after event-surprise data is blocked by paid API access.
  Uses only already-available lag-aware macro data and official COT positioning data.

Hard constraints:
  - No orders
  - No broker connection
  - No MT5/EA changes
  - No paper-live/live
  - No threshold tuning from this discovery stage
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

STAGE = "Stage105_SECOND_ORDER_COT_MACRO_THESIS_DISCOVERY"


@dataclass(frozen=True)
class CandidateRule:
    rule_id: str
    label: str
    bucket: str
    horizon_trading_days: int
    cooldown_trading_days: int
    condition_text: str
    required_columns: Tuple[str, ...]
    condition_fn: Callable[[pd.DataFrame], pd.Series]


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


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def safe_numeric_series(s: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s):
        return s
    cleaned = (
        s.astype(str)
        .str.strip()
        .str.replace(",", "", regex=False)
        .str.replace("%", "", regex=False)
        .replace({"": None, "nan": None, "None": None, "null": None, "N/A": None, "na": None})
    )
    converted = pd.to_numeric(cleaned, errors="coerce")
    # Keep as converted only if at least one finite value exists, otherwise caller may preserve textual column.
    return converted if converted.notna().any() else s


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    return out


def find_first_existing(cols: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    available = set(cols)
    for c in candidates:
        if c in available:
            return c
    lower_map = {str(c).lower(): c for c in cols}
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None


def load_macro(root: Path, cfg: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    rel = cfg.get("macro_dataset_path", "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv")
    path = root / rel
    if not path.exists():
        raise FileNotFoundError(f"macro dataset not found: {path}")
    df = normalize_columns(pd.read_csv(path))
    date_col = find_first_existing(df.columns, cfg.get("macro_date_columns", ["date", "date_utc", "utc_date", "asof_date_utc", "as_of_date", "trading_date", "timestamp", "utc_time", "time", "datetime"]))
    if date_col is None:
        raise ValueError(f"No macro date column found. Available columns={list(df.columns)[:40]}. Expected one of date/date_utc/utc_date/asof_date_utc/as_of_date/trading_date/timestamp/utc_time/time/datetime.")
    df["date_utc"] = pd.to_datetime(df[date_col], utc=True, errors="coerce").dt.normalize()
    df = df.dropna(subset=["date_utc"]).sort_values("date_utc").drop_duplicates("date_utc", keep="last").reset_index(drop=True)
    for c in df.columns:
        if c != "date_utc" and c != date_col:
            df[c] = safe_numeric_series(df[c])
    price_col = find_first_existing(df.columns, cfg.get("gold_price_columns", ["gold_close", "xauusd_close", "xau_close", "close", "price", "gold" ]))
    if price_col is None:
        raise ValueError("No gold price column found. Expected gold_close/xauusd_close/close/price.")
    df["gold_price_for_return"] = pd.to_numeric(df[price_col], errors="coerce")
    meta = {
        "path": str(path),
        "rows": int(len(df)),
        "min_date": str(df["date_utc"].min().date()) if len(df) else None,
        "max_date": str(df["date_utc"].max().date()) if len(df) else None,
        "date_col": date_col,
        "price_col": price_col,
        "sha256": sha256_file(path),
    }
    return df, meta


def load_cot(root: Path, cfg: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    rel = cfg.get("cot_dataset_path", "data/external_frontiers/cot_positioning_normalized.csv")
    path = root / rel
    if not path.exists():
        raise FileNotFoundError(f"COT dataset not found: {path}")
    df = normalize_columns(pd.read_csv(path))
    for c in df.columns:
        df[c] = safe_numeric_series(df[c])

    report_col = find_first_existing(df.columns, ["report_date_utc", "report_date", "date", "as_of_date"])
    if report_col is None:
        raise ValueError("No COT report date column found.")
    df["report_date_utc"] = pd.to_datetime(df[report_col], utc=True, errors="coerce").dt.normalize()

    available_col = find_first_existing(df.columns, ["available_after_utc", "available_date_utc", "available_after", "release_date_utc"])
    if available_col:
        df["cot_available_after_utc"] = pd.to_datetime(df[available_col], utc=True, errors="coerce").dt.normalize()
    else:
        lag_days = int(cfg.get("cot_default_release_lag_days", 3))
        df["cot_available_after_utc"] = df["report_date_utc"] + pd.to_timedelta(lag_days, unit="D")

    z_alias = find_first_existing(df.columns, cfg.get("cot_z_aliases", [
        "cot_mm_net_z",
        "managed_money_net_pct_oi_z_156w",
        "managed_money_net_z_156w",
        "mm_net_pct_oi_z_156w",
        "managed_money_net_pct_oi_z",
    ]))
    if z_alias:
        df["cot_mm_net_z"] = pd.to_numeric(df[z_alias], errors="coerce")

    chg_alias = find_first_existing(df.columns, cfg.get("cot_change_aliases", [
        "cot_mm_net_z_change_4w",
        "managed_money_net_pct_oi_change_4w",
        "managed_money_net_change_4w",
        "mm_net_pct_oi_change_4w",
        "managed_money_net_pct_oi_z_change_4w",
    ]))
    if chg_alias:
        df["cot_mm_net_z_change_4w"] = pd.to_numeric(df[chg_alias], errors="coerce")
    elif "cot_mm_net_z" in df.columns:
        df = df.sort_values("cot_available_after_utc")
        df["cot_mm_net_z_change_4w"] = df["cot_mm_net_z"].diff(4)

    df = df.dropna(subset=["cot_available_after_utc"]).sort_values("cot_available_after_utc").drop_duplicates("cot_available_after_utc", keep="last").reset_index(drop=True)
    meta = {
        "path": str(path),
        "rows": int(len(df)),
        "min_report_date_utc": str(df["report_date_utc"].min().date()) if len(df) else None,
        "max_report_date_utc": str(df["report_date_utc"].max().date()) if len(df) else None,
        "zscore_non_null": int(df.get("cot_mm_net_z", pd.Series(dtype=float)).notna().sum()) if "cot_mm_net_z" in df.columns else 0,
        "change_non_null": int(df.get("cot_mm_net_z_change_4w", pd.Series(dtype=float)).notna().sum()) if "cot_mm_net_z_change_4w" in df.columns else 0,
        "sha256": sha256_file(path),
    }
    return df, meta


def build_joined(root: Path, cfg: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    macro, macro_meta = load_macro(root, cfg)
    cot, cot_meta = load_cot(root, cfg)
    joined = pd.merge_asof(
        macro.sort_values("date_utc"),
        cot.sort_values("cot_available_after_utc"),
        left_on="date_utc",
        right_on="cot_available_after_utc",
        direction="backward",
        suffixes=("", "_cotraw"),
    )
    lookahead = joined[(joined["cot_available_after_utc"].notna()) & (joined["cot_available_after_utc"] > joined["date_utc"])]
    join_meta = {
        "joined_rows": int(len(joined)),
        "joined_cot_available_rows": int(joined["cot_mm_net_z"].notna().sum()) if "cot_mm_net_z" in joined.columns else 0,
        "lookahead_violations": int(len(lookahead)),
    }
    return joined, macro_meta, cot_meta, join_meta


def gt(df: pd.DataFrame, col: str, threshold: float) -> pd.Series:
    return pd.to_numeric(df[col], errors="coerce") > threshold


def lt(df: pd.DataFrame, col: str, threshold: float) -> pd.Series:
    return pd.to_numeric(df[col], errors="coerce") < threshold


def between(df: pd.DataFrame, col: str, low: float, high: float) -> pd.Series:
    s = pd.to_numeric(df[col], errors="coerce")
    return (s > low) & (s < high)


def get_candidates(cfg: Dict[str, Any]) -> List[CandidateRule]:
    horizon = int(cfg.get("horizon_trading_days", 120))
    cooldown = int(cfg.get("cooldown_trading_days", 120))
    return [
        CandidateRule(
            "S105_01_COT_NOT_CROWDED_GOLD_PULLBACK_RY_RELIEF_H120",
            "COT_NOT_CROWDED_GOLD_PULLBACK_RY_RELIEF",
            "cot_macro_second_order",
            horizon,
            cooldown,
            "cot_mm_net_z<1.0 AND gold_ret_20d<0.0 AND real_yield_change_20d<0.0",
            ("cot_mm_net_z", "gold_ret_20d", "real_yield_change_20d"),
            lambda d: lt(d, "cot_mm_net_z", 1.0) & lt(d, "gold_ret_20d", 0.0) & lt(d, "real_yield_change_20d", 0.0),
        ),
        CandidateRule(
            "S105_02_COT_NOT_CROWDED_DXY_WEAK_GOLD_PULLBACK_H120",
            "COT_NOT_CROWDED_DXY_WEAK_GOLD_PULLBACK",
            "cot_macro_second_order",
            horizon,
            cooldown,
            "cot_mm_net_z<1.0 AND dxy_ret_20d<0.0 AND gold_ret_20d<0.0",
            ("cot_mm_net_z", "dxy_ret_20d", "gold_ret_20d"),
            lambda d: lt(d, "cot_mm_net_z", 1.0) & lt(d, "dxy_ret_20d", 0.0) & lt(d, "gold_ret_20d", 0.0),
        ),
        CandidateRule(
            "S105_03_COT_DECROWDING_CB_SUPPORT_RY_RELIEF_H120",
            "COT_DECROWDING_CB_SUPPORT_RY_RELIEF",
            "cot_flow_interaction",
            horizon,
            cooldown,
            "cot_mm_net_z_change_4w<0.0 AND central_bank_demand_tonnes_3m>0.0 AND real_yield_change_20d<0.0",
            ("cot_mm_net_z_change_4w", "central_bank_demand_tonnes_3m", "real_yield_change_20d"),
            lambda d: lt(d, "cot_mm_net_z_change_4w", 0.0) & gt(d, "central_bank_demand_tonnes_3m", 0.0) & lt(d, "real_yield_change_20d", 0.0),
        ),
        CandidateRule(
            "S105_04_COT_WASHOUT_RECOVERY_GOLD_STABILIZING_H120",
            "COT_WASHOUT_RECOVERY_GOLD_STABILIZING",
            "cot_washout_recovery",
            horizon,
            cooldown,
            "cot_mm_net_z<-0.5 AND cot_mm_net_z_change_4w>0.25 AND gold_ret_20d>0.0",
            ("cot_mm_net_z", "cot_mm_net_z_change_4w", "gold_ret_20d"),
            lambda d: lt(d, "cot_mm_net_z", -0.5) & gt(d, "cot_mm_net_z_change_4w", 0.25) & gt(d, "gold_ret_20d", 0.0),
        ),
        CandidateRule(
            "S105_05_COT_NOT_CROWDED_DXY_120D_WEAK_GOLD_TREND_H120",
            "COT_NOT_CROWDED_DXY_120D_WEAK_GOLD_TREND",
            "cot_regime_interaction",
            horizon,
            cooldown,
            "cot_mm_net_z<1.0 AND dxy_ret_120d<0.0 AND gold_sma20_over_50>0.0",
            ("cot_mm_net_z", "dxy_ret_120d", "gold_sma20_over_50"),
            lambda d: lt(d, "cot_mm_net_z", 1.0) & lt(d, "dxy_ret_120d", 0.0) & gt(d, "gold_sma20_over_50", 0.0),
        ),
        CandidateRule(
            "S105_06_COT_NOT_CROWDED_VIX_UP_RY_RELIEF_H120",
            "COT_NOT_CROWDED_VIX_UP_RY_RELIEF",
            "safe_haven_positioning",
            horizon,
            cooldown,
            "cot_mm_net_z<1.0 AND vix_change_20d>0.0 AND real_yield_change_20d<0.0",
            ("cot_mm_net_z", "vix_change_20d", "real_yield_change_20d"),
            lambda d: lt(d, "cot_mm_net_z", 1.0) & gt(d, "vix_change_20d", 0.0) & lt(d, "real_yield_change_20d", 0.0),
        ),
        CandidateRule(
            "S105_07_NOT_EXTREME_LONG_GOLD_TREND_DXY_TREND_RELIEF_H120",
            "NOT_EXTREME_LONG_GOLD_TREND_DXY_TREND_RELIEF",
            "trend_positioning_filter",
            horizon,
            cooldown,
            "cot_mm_net_z<1.5 AND gold_sma20_over_50>0.0 AND dxy_sma20_over_50<0.0",
            ("cot_mm_net_z", "gold_sma20_over_50", "dxy_sma20_over_50"),
            lambda d: lt(d, "cot_mm_net_z", 1.5) & gt(d, "gold_sma20_over_50", 0.0) & lt(d, "dxy_sma20_over_50", 0.0),
        ),
        CandidateRule(
            "S105_08_COT_SHORT_WASHOUT_REALYIELD_120D_DOWN_H120",
            "COT_SHORT_WASHOUT_REALYIELD_120D_DOWN",
            "washout_real_yield_regime",
            horizon,
            cooldown,
            "cot_mm_net_z<-1.0 AND real_yield_change_120d<0.0",
            ("cot_mm_net_z", "real_yield_change_120d"),
            lambda d: lt(d, "cot_mm_net_z", -1.0) & lt(d, "real_yield_change_120d", 0.0),
        ),
        CandidateRule(
            "S105_09_CB_SUPPORT_COT_DECROWDING_GOLD_PULLBACK_H120",
            "CB_SUPPORT_COT_DECROWDING_GOLD_PULLBACK",
            "flow_positioning_interaction",
            horizon,
            cooldown,
            "central_bank_demand_tonnes_3m>0.0 AND cot_mm_net_z_change_4w<0.0 AND gold_ret_20d<0.0",
            ("central_bank_demand_tonnes_3m", "cot_mm_net_z_change_4w", "gold_ret_20d"),
            lambda d: gt(d, "central_bank_demand_tonnes_3m", 0.0) & lt(d, "cot_mm_net_z_change_4w", 0.0) & lt(d, "gold_ret_20d", 0.0),
        ),
        CandidateRule(
            "S105_10_ETF_SUPPORT_COT_DECROWDING_GOLD_PULLBACK_H120",
            "ETF_SUPPORT_COT_DECROWDING_GOLD_PULLBACK",
            "flow_positioning_interaction",
            horizon,
            cooldown,
            "etf_flow_tonnes_3m>0.0 AND cot_mm_net_z_change_4w<0.0 AND gold_ret_20d<0.0",
            ("etf_flow_tonnes_3m", "cot_mm_net_z_change_4w", "gold_ret_20d"),
            lambda d: gt(d, "etf_flow_tonnes_3m", 0.0) & lt(d, "cot_mm_net_z_change_4w", 0.0) & lt(d, "gold_ret_20d", 0.0),
        ),
        CandidateRule(
            "S105_11_COT_NEUTRAL_STRESS_RY_RELIEF_H120",
            "COT_NEUTRAL_STRESS_RY_RELIEF",
            "safe_haven_positioning",
            horizon,
            cooldown,
            "cot_mm_net_z>-0.5 AND cot_mm_net_z<1.0 AND vix_change_20d>0.0 AND real_yield_change_20d<0.0",
            ("cot_mm_net_z", "vix_change_20d", "real_yield_change_20d"),
            lambda d: between(d, "cot_mm_net_z", -0.5, 1.0) & gt(d, "vix_change_20d", 0.0) & lt(d, "real_yield_change_20d", 0.0),
        ),
        CandidateRule(
            "S105_12_COT_FILTERED_K06_RESILIENCE_H120",
            "COT_FILTERED_K06_RESILIENCE",
            "cot_filtered_known_thesis",
            horizon,
            cooldown,
            "cot_mm_net_z<1.0 AND gold_sma20_over_50>0.0 AND dxy_ret_20d>0.0 AND real_yield_change_20d<0.0",
            ("cot_mm_net_z", "gold_sma20_over_50", "dxy_ret_20d", "real_yield_change_20d"),
            lambda d: lt(d, "cot_mm_net_z", 1.0) & gt(d, "gold_sma20_over_50", 0.0) & gt(d, "dxy_ret_20d", 0.0) & lt(d, "real_yield_change_20d", 0.0),
        ),
    ]


def mask_for_conditions(df: pd.DataFrame, conditions: List[Dict[str, Any]]) -> pd.Series:
    if not conditions:
        return pd.Series(False, index=df.index)
    mask = pd.Series(True, index=df.index)
    for cond in conditions:
        col = cond["column"]
        op = cond["operator"]
        threshold = float(cond["threshold"])
        if col not in df.columns:
            return pd.Series(False, index=df.index)
        if op == ">":
            mask &= gt(df, col, threshold)
        elif op == "<":
            mask &= lt(df, col, threshold)
        elif op == ">=":
            mask &= pd.to_numeric(df[col], errors="coerce") >= threshold
        elif op == "<=":
            mask &= pd.to_numeric(df[col], errors="coerce") <= threshold
        else:
            raise ValueError(f"Unsupported operator {op}")
    return mask.fillna(False)


def current_portfolio_mask(df: pd.DataFrame, cfg: Dict[str, Any]) -> pd.Series:
    current_rules = cfg.get("current_unified_portfolio_rules") or [
        {"rule_id": "K06_RESILIENT_GOLD_VS_DXY_H120", "conditions": [
            {"column": "gold_sma20_over_50", "operator": ">", "threshold": 0.0},
            {"column": "dxy_ret_20d", "operator": ">", "threshold": 0.0},
            {"column": "real_yield_change_20d", "operator": "<", "threshold": 0.0},
        ]},
        {"rule_id": "K03_SAFE_HAVEN_REALYIELD_H120", "conditions": [
            {"column": "vix_change_20d", "operator": ">", "threshold": 0.0},
            {"column": "real_yield_change_20d", "operator": "<", "threshold": 0.0},
        ]},
        {"rule_id": "K07_DXY_TREND_RELIEF_GOLD_TREND_H120", "conditions": [
            {"column": "gold_sma20_over_50", "operator": ">", "threshold": 0.0},
            {"column": "dxy_sma20_over_50", "operator": "<", "threshold": 0.0},
        ]},
        {"rule_id": "S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120", "conditions": [
            {"column": "real_yield_change_120d", "operator": "<", "threshold": 0.0},
            {"column": "gold_sma20_over_50", "operator": "<", "threshold": 0.0},
        ]},
        {"rule_id": "S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120", "conditions": [
            {"column": "dxy_ret_120d", "operator": "<", "threshold": 0.0},
            {"column": "gold_sma20_over_50", "operator": "<", "threshold": 0.0},
        ]},
        {"rule_id": "C96_07_CB_SUPPORT_NOT_CROWDED_H120", "conditions": [
            {"column": "cot_mm_net_z", "operator": "<", "threshold": 1.0},
            {"column": "central_bank_demand_tonnes_3m", "operator": ">", "threshold": 0.0},
            {"column": "gold_ret_20d", "operator": "<", "threshold": 0.0},
        ]},
    ]
    union = pd.Series(False, index=df.index)
    for r in current_rules:
        union |= mask_for_conditions(df, r.get("conditions", []))
    return union.fillna(False)


def compute_entries(active_mask: pd.Series, horizon: int, cooldown: int, df: pd.DataFrame) -> List[int]:
    entries: List[int] = []
    last_entry_idx = -10**9
    active = active_mask.fillna(False).astype(bool).to_numpy()
    for i, is_active in enumerate(active):
        if not is_active:
            continue
        if i + horizon >= len(df):
            continue
        if i - last_entry_idx < cooldown:
            continue
        if pd.isna(df.iloc[i]["gold_price_for_return"]) or pd.isna(df.iloc[i + horizon]["gold_price_for_return"]):
            continue
        entries.append(i)
        last_entry_idx = i
    return entries


def summarize_returns(vals: Sequence[float]) -> Dict[str, Any]:
    s = pd.Series(list(vals), dtype="float64").dropna()
    if s.empty:
        return {
            "entry_count": 0,
            "mean_net_bps": None,
            "median_net_bps": None,
            "win_rate": None,
            "min_net_return_bps": None,
            "max_net_return_bps": None,
            "total_net_return_bps": 0.0,
        }
    return {
        "entry_count": int(len(s)),
        "mean_net_bps": round(float(s.mean()), 4),
        "median_net_bps": round(float(s.median()), 4),
        "win_rate": round(float((s > 0).mean()), 4),
        "min_net_return_bps": round(float(s.min()), 4),
        "max_net_return_bps": round(float(s.max()), 4),
        "total_net_return_bps": round(float(s.sum()), 4),
    }


def split_name_for_date(dt: pd.Timestamp, cfg: Dict[str, Any]) -> str:
    d = dt.date().isoformat()
    splits = cfg.get("splits", {
        "TRAIN_DISCOVERY": ["2011-01-01", "2014-12-31"],
        "VALIDATION_SELECTION": ["2015-01-01", "2018-12-31"],
        "LOCKED_HISTORICAL_FORWARD": ["2019-01-01", "2022-12-31"],
        "FINAL_STATISTICAL_HOLDOUT": ["2023-01-01", "2099-12-31"],
    })
    for name, bounds in splits.items():
        if bounds[0] <= d <= bounds[1]:
            return name
    return "OUT_OF_SPLIT"


def evaluate_rule(rule: CandidateRule, df: pd.DataFrame, current_union: pd.Series, cfg: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    missing_cols = [c for c in rule.required_columns if c not in df.columns]
    warmup_missing_rows_ignored = 0
    missing_required_feature_rows = 0
    if missing_cols:
        active = pd.Series(False, index=df.index)
    else:
        required_ok = df[list(rule.required_columns)].notna().all(axis=1)
        if required_ok.any():
            first_valid_pos = int(required_ok.to_numpy().argmax())
            warmup_missing_rows_ignored = int((~required_ok.iloc[:first_valid_pos]).sum())
            missing_required_feature_rows = int((~required_ok.iloc[first_valid_pos:]).sum())
        else:
            warmup_missing_rows_ignored = int((~required_ok).sum())
            missing_required_feature_rows = 0
        active = rule.condition_fn(df).fillna(False) & required_ok

    raw_active_days = int(active.sum())
    overlap_days = int((active & current_union).sum())
    residual_active_days = int((active & ~current_union).sum())
    current_days = int(current_union.sum())
    after_days = int((current_union | active).sum())
    incremental_days = int(after_days - current_days)
    overlap_pct = round(float(overlap_days / raw_active_days * 100.0), 4) if raw_active_days else None

    entries = compute_entries(active, rule.horizon_trading_days, rule.cooldown_trading_days, df)
    entry_rows: List[Dict[str, Any]] = []
    returns_by_split: Dict[str, List[float]] = {"TRAIN_DISCOVERY": [], "VALIDATION_SELECTION": [], "LOCKED_HISTORICAL_FORWARD": [], "FINAL_STATISTICAL_HOLDOUT": []}
    post_asof_returns: List[float] = []
    asof_date = pd.to_datetime(cfg.get("post_asof_start_date", "2024-01-01"), utc=True)
    cost_bps = float(cfg.get("cost_bps_total_reference", 50.0))
    for i in entries:
        entry = df.iloc[i]
        exit_row = df.iloc[i + rule.horizon_trading_days]
        entry_price = float(entry["gold_price_for_return"])
        exit_price = float(exit_row["gold_price_for_return"])
        gross = (exit_price / entry_price - 1.0) * 10000.0
        net = gross - cost_bps
        split = split_name_for_date(entry["date_utc"], cfg)
        if split in returns_by_split:
            returns_by_split[split].append(net)
        if entry["date_utc"] >= asof_date:
            post_asof_returns.append(net)
        entry_rows.append({
            "rule_id": rule.rule_id,
            "entry_date_utc": entry["date_utc"].date().isoformat(),
            "exit_date_utc": exit_row["date_utc"].date().isoformat(),
            "entry_price": entry_price,
            "exit_price": exit_price,
            "gross_return_bps": round(gross, 4),
            "net_return_bps": round(net, 4),
            "split": split,
        })

    total_summary = summarize_returns([r["net_return_bps"] for r in entry_rows])
    split_summaries = {name: summarize_returns(vals) for name, vals in returns_by_split.items()}
    post_asof = summarize_returns(post_asof_returns)

    years = [pd.to_datetime(r["entry_date_utc"]).year for r in entry_rows]
    if years:
        vc = pd.Series(years).value_counts()
        max_year = int(vc.index[0])
        max_year_share = round(float(vc.iloc[0] / len(years)), 4)
    else:
        max_year = None
        max_year_share = None

    constraints = cfg.get("constraints", {})
    fail_reasons: List[str] = []
    if total_summary["entry_count"] < int(constraints.get("min_total_entries", 5)):
        fail_reasons.append("TOTAL_ENTRIES_TOO_LOW")
    if (total_summary["mean_net_bps"] is None) or total_summary["mean_net_bps"] < float(constraints.get("min_total_mean_net_bps", 150.0)):
        fail_reasons.append("TOTAL_MEAN_TOO_LOW")
    if (total_summary["win_rate"] is None) or total_summary["win_rate"] < float(constraints.get("min_total_win_rate", 0.55)):
        fail_reasons.append("WIN_RATE_TOO_LOW")
    if total_summary["min_net_return_bps"] is not None and abs(total_summary["min_net_return_bps"]) > float(constraints.get("max_abs_worst_loss_bps", 2500.0)):
        fail_reasons.append("WORST_LOSS_TOO_LARGE")

    val = split_summaries["VALIDATION_SELECTION"]
    locked = split_summaries["LOCKED_HISTORICAL_FORWARD"]
    final = split_summaries["FINAL_STATISTICAL_HOLDOUT"]
    if val["entry_count"] < int(constraints.get("min_validation_entries", 1)):
        fail_reasons.append("VALIDATION_ENTRIES_TOO_LOW")
    if locked["entry_count"] < int(constraints.get("min_locked_forward_entries", 1)):
        fail_reasons.append("LOCKED_FORWARD_ENTRIES_TOO_LOW")
    if locked["mean_net_bps"] is None or locked["mean_net_bps"] < float(constraints.get("min_locked_forward_mean_bps", -100.0)):
        fail_reasons.append("LOCKED_FORWARD_MEAN_TOO_LOW")
    if final["entry_count"] < int(constraints.get("min_final_holdout_entries", 1)):
        fail_reasons.append("FINAL_HOLDOUT_ENTRIES_TOO_LOW")
    if final["mean_net_bps"] is None or final["mean_net_bps"] < float(constraints.get("min_final_holdout_mean_bps", 300.0)):
        fail_reasons.append("FINAL_HOLDOUT_MEAN_TOO_LOW")
    if post_asof["entry_count"] < int(constraints.get("min_post_asof_entries", 1)):
        fail_reasons.append("POST_ASOF_ENTRIES_TOO_LOW")
    if post_asof["mean_net_bps"] is None or post_asof["mean_net_bps"] < float(constraints.get("min_post_asof_mean_bps", 300.0)):
        fail_reasons.append("POST_ASOF_MEAN_TOO_LOW")
    if max_year_share is not None and max_year_share > float(constraints.get("max_year_entry_share", 0.45)):
        fail_reasons.append("YEAR_CONCENTRATION_TOO_HIGH")
    if missing_required_feature_rows > int(constraints.get("max_missing_required_feature_rows", 0)):
        fail_reasons.append("MISSING_REQUIRED_FEATURE_ROWS")
    if incremental_days < int(constraints.get("min_incremental_union_active_days", 75)):
        fail_reasons.append("INCREMENTAL_DAYS_TOO_LOW")
    max_overlap = float(constraints.get("max_overlap_with_current_pct", 85.0))
    if overlap_pct is not None and overlap_pct > max_overlap:
        fail_reasons.append("OVERLAP_WITH_CURRENT_TOO_HIGH")
    if missing_cols:
        fail_reasons.append("MISSING_COLUMNS:" + ",".join(missing_cols))

    score = 0.0
    for valx, weight in [
        (total_summary["mean_net_bps"], 1.0),
        (final["mean_net_bps"], 1.5),
        (post_asof["mean_net_bps"], 1.5),
        (locked["mean_net_bps"], 0.75),
    ]:
        if valx is not None:
            score += float(valx) * weight
    if total_summary["win_rate"] is not None:
        score += float(total_summary["win_rate"]) * 500.0
    score += incremental_days * float(cfg.get("incremental_day_score_weight", 0.5))
    if overlap_pct is not None:
        score -= overlap_pct * 10.0

    out = {
        "rule_id": rule.rule_id,
        "label": rule.label,
        "bucket": rule.bucket,
        "horizon_trading_days": rule.horizon_trading_days,
        "cooldown_trading_days": rule.cooldown_trading_days,
        "condition_text": rule.condition_text,
        "missing_columns": ",".join(missing_cols),
        "warmup_missing_rows_ignored": warmup_missing_rows_ignored,
        "missing_required_feature_rows": missing_required_feature_rows,
        "raw_active_days": raw_active_days,
        "residual_active_days": residual_active_days,
        "current_union_active_days": current_days,
        "current_union_active_days_after_candidate": after_days,
        "incremental_union_active_days": incremental_days,
        "overlap_with_current_union_days": overlap_days,
        "overlap_with_current_union_pct": overlap_pct,
        "total_entry_count": total_summary["entry_count"],
        "total_mean_net_bps": total_summary["mean_net_bps"],
        "total_median_net_bps": total_summary["median_net_bps"],
        "total_win_rate": total_summary["win_rate"],
        "total_min_net_return_bps": total_summary["min_net_return_bps"],
        "total_max_net_return_bps": total_summary["max_net_return_bps"],
        "total_total_net_return_bps": total_summary["total_net_return_bps"],
        "train_entry_count": split_summaries["TRAIN_DISCOVERY"]["entry_count"],
        "train_mean_net_bps": split_summaries["TRAIN_DISCOVERY"]["mean_net_bps"],
        "train_win_rate": split_summaries["TRAIN_DISCOVERY"]["win_rate"],
        "validation_entry_count": val["entry_count"],
        "validation_mean_net_bps": val["mean_net_bps"],
        "validation_win_rate": val["win_rate"],
        "locked_forward_entry_count": locked["entry_count"],
        "locked_forward_mean_net_bps": locked["mean_net_bps"],
        "locked_forward_win_rate": locked["win_rate"],
        "final_holdout_entry_count": final["entry_count"],
        "final_holdout_mean_net_bps": final["mean_net_bps"],
        "final_holdout_win_rate": final["win_rate"],
        "post_asof_entry_count": post_asof["entry_count"],
        "post_asof_mean_net_bps": post_asof["mean_net_bps"],
        "post_asof_win_rate": post_asof["win_rate"],
        "max_entry_year": max_year,
        "max_year_entry_share": max_year_share,
        "pass_second_order_discovery_candidate": len(fail_reasons) == 0,
        "fail_reasons": "|".join(fail_reasons),
        "second_order_discovery_score": round(score, 4),
        "lookahead_violations": 0,
    }
    return out, entry_rows


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: List[str] = []
    seen = set()
    for r in rows:
        for k in r.keys():
            if k not in seen:
                seen.add(k)
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def build_report(path: Path, summary: Dict[str, Any]) -> None:
    lines = [
        "# Stage105 Second-Order COT/Macro Thesis Discovery",
        "",
        "## Decision",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- classification: `{summary['classification']}`",
        f"- disposition: `{summary['disposition']}`",
        "",
        "## Context",
        "Event-surprise discovery is data-blocked under current free-data constraints, so Stage105 uses available official COT and macro datasets only.",
        "",
        "## Counts",
        f"- candidate_count: `{summary['candidate_count']}`",
        f"- pass_candidate_count: `{summary['pass_candidate_count']}`",
        f"- shortlist_count: `{summary['shortlist_count']}`",
        "",
        "## Shortlist",
    ]
    if summary["shortlist_rule_ids"]:
        for rid in summary["shortlist_rule_ids"]:
            lines.append(f"- `{rid}`")
    else:
        lines.append("- none")
    lines.extend(["", "## Hard blocks"])
    for hb in summary["hard_blocks"]:
        lines.append(f"- `{hb}`")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    cfg_path = Path(args.config).expanduser()
    if not cfg_path.is_absolute():
        cfg_path = root / cfg_path
    out = Path(args.out).expanduser()
    if not out.is_absolute():
        out = root / out
    out.mkdir(parents=True, exist_ok=True)
    cfg = read_json(cfg_path)

    joined, macro_meta, cot_meta, join_meta = build_joined(root, cfg)
    current_union = current_portfolio_mask(joined, cfg)

    metrics: List[Dict[str, Any]] = []
    entry_rows_all: List[Dict[str, Any]] = []
    for rule in get_candidates(cfg):
        m, erows = evaluate_rule(rule, joined, current_union, cfg)
        metrics.append(m)
        entry_rows_all.extend(erows)

    metrics_sorted = sorted(metrics, key=lambda r: (r.get("pass_second_order_discovery_candidate") is True, r.get("second_order_discovery_score") or -10**9), reverse=True)
    pass_rows = [r for r in metrics_sorted if r.get("pass_second_order_discovery_candidate") is True]
    max_shortlist = int(cfg.get("max_shortlist", 6))
    shortlist = pass_rows[:max_shortlist]

    if shortlist:
        decision = "STAGE105_SECOND_ORDER_COT_MACRO_SHORTLIST_READY_FOR_HARD_AUDIT_NO_ORDER"
        classification = "S105_SECOND_ORDER_SHORTLIST_READY"
        disposition = "SECOND_ORDER_COT_MACRO_SHORTLIST_READY_FOR_STAGE106_HARD_AUDIT"
    else:
        decision = "STAGE105_NO_SECOND_ORDER_COT_MACRO_SHORTLIST_NO_ORDER"
        classification = "S105_NO_SECOND_ORDER_SHORTLIST"
        disposition = "NO_SECOND_ORDER_COT_MACRO_SHORTLIST"

    metrics_path = out / "stage105_second_order_cot_macro_candidate_metrics.csv"
    shortlist_path = out / "stage105_second_order_cot_macro_shortlist.csv"
    entries_path = out / "stage105_second_order_cot_macro_entry_returns.csv"
    snapshot_path = out / "stage105_second_order_cot_macro_joined_snapshot.csv"
    write_csv(metrics_path, metrics_sorted)
    write_csv(shortlist_path, shortlist)
    write_csv(entries_path, entry_rows_all)
    joined.head(int(cfg.get("joined_snapshot_rows", 5000))).to_csv(snapshot_path, index=False)

    summary = {
        "stage": STAGE,
        "root": str(root),
        "config": str(cfg_path),
        "status": "STAGE105_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "principle": "Continue thesis discovery after event-surprise data is blocked. Use existing lag-aware macro and official COT data only. No order, broker, MT5, EA, paper-live, or live change.",
        "event_surprise_blocked_reason": cfg.get("event_surprise_blocked_reason", "EODHD economic-events requires paid plan; Trading Economics has no usable free tier for historical consensus."),
        "macro_dataset": macro_meta,
        "cot_dataset": cot_meta,
        "data_join": join_meta,
        "current_unified_portfolio_rule_count": int(len(cfg.get("current_unified_portfolio_rules", [])) or 6),
        "current_union_active_days": int(current_union.sum()),
        "candidate_count": int(len(metrics_sorted)),
        "pass_candidate_count": int(len(pass_rows)),
        "shortlist_count": int(len(shortlist)),
        "shortlist_rule_ids": [r["rule_id"] for r in shortlist],
        "shortlist": shortlist,
        "constraints": cfg.get("constraints", {}),
        "issues": [] if join_meta.get("lookahead_violations", 0) == 0 else ["LOOKAHEAD_VIOLATIONS"],
        "hard_blocks": [
            "NO_AUTOMATED_ORDER",
            "NO_PAPER_ORDER",
            "NO_BROKER_CONNECTION",
            "NO_EA_PROMOTION",
            "NO_MT5_OR_EA_CHANGE",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_ORDER_AUTHORIZATION_FROM_STAGE105",
            "NO_THRESHOLD_TUNING_FROM_STAGE105_DISCOVERY",
        ],
        "outputs": {
            "summary_json": str(out / "stage105_second_order_cot_macro_thesis_discovery_summary.json"),
            "report_md": str(out / "stage105_second_order_cot_macro_thesis_discovery_report.md"),
            "candidate_metrics_csv": str(metrics_path),
            "shortlist_csv": str(shortlist_path),
            "entry_returns_csv": str(entries_path),
            "joined_snapshot_csv": str(snapshot_path),
        },
    }
    write_json(out / "stage105_second_order_cot_macro_thesis_discovery_summary.json", summary)
    build_report(out / "stage105_second_order_cot_macro_thesis_discovery_report.md", summary)
    print(json.dumps({"status": summary["status"], "decision": decision, "shortlist_count": len(shortlist), "issues": summary["issues"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
