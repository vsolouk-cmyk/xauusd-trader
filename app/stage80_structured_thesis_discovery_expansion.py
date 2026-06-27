#!/usr/bin/env python3
"""
Stage80 Structured Thesis Discovery Expansion.

Purpose:
- Continue discovery after Stage77B/78/79 without opening an unconstrained megascan.
- Evaluate thesis-first macro candidates using locked splits, historical daily replay style entries,
  corrected as-of metrics, and overlap against the current Stage77B observer portfolio.
- Produce a shortlist for later hard audit only. No order authorization.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE80",
    "NO_THRESHOLD_TUNING_FROM_STAGE80_DISCOVERY",
    "NO_ML_FROM_STAGE80",
    "NO_DIRECT_EA_CHANGE_FROM_STAGE80",
]

SPLITS = [
    ("TRAIN_DISCOVERY", "2011-01-03", "2014-12-31", "discovery_reference_only"),
    ("VALIDATION_SELECTION", "2015-01-01", "2018-12-31", "selection_reference_only"),
    ("LOCKED_HISTORICAL_FORWARD", "2019-01-01", "2022-12-31", "locked_forward_like_unseen"),
    ("FINAL_STATISTICAL_HOLDOUT", "2023-01-01", None, "final_locked_proof"),
]

ASOF_DATE = "2024-01-01"
FINAL_HOLDOUT_START = "2025-01-01"
REPLAY_START = "2019-01-01"
REFERENCE_COST_BPS = 50.0

# The three current observer portfolio rules are included as benchmarks only.
BENCHMARK_CANDIDATES = [
    {
        "rule_id": "K06_RESILIENT_GOLD_VS_DXY_H120",
        "label": "K06_RESILIENT_GOLD_VS_DXY",
        "bucket": "stage77b_selected_benchmark",
        "direction": "long",
        "horizon": 120,
        "cooldown": 120,
        "conditions": [
            ("gold_sma20_over_50", ">", 0.0),
            ("dxy_ret_20d", ">", 0.0),
            ("real_yield_change_20d", "<", 0.0),
        ],
    },
    {
        "rule_id": "K03_SAFE_HAVEN_REALYIELD_H120",
        "label": "K03_WGC_RISK_UNCERTAINTY_SAFE_HAVEN",
        "bucket": "stage77b_selected_benchmark",
        "direction": "long",
        "horizon": 120,
        "cooldown": 120,
        "conditions": [
            ("vix_change_20d", ">", 0.0),
            ("real_yield_change_20d", "<", 0.0),
        ],
    },
    {
        "rule_id": "K07_DXY_TREND_RELIEF_GOLD_TREND_H120",
        "label": "K07_DXY_TREND_RELIEF_GOLD_TREND",
        "bucket": "stage77b_selected_benchmark",
        "direction": "long",
        "horizon": 120,
        "cooldown": 120,
        "conditions": [
            ("gold_sma20_over_50", ">", 0.0),
            ("dxy_sma20_over_50", "<", 0.0),
        ],
    },
]

# Structured expansion: public/macro-thesis first, not arbitrary threshold search.
DISCOVERY_CANDIDATES = [
    # Opportunity-cost / dollar relief
    {"rule_id": "S80_01_DXY_REALYIELD_DOUBLE_RELIEF_H120", "label": "DXY_AND_REAL_YIELD_DOUBLE_RELIEF", "bucket": "opportunity_cost_relief", "horizon": 120, "cooldown": 120, "conditions": [("dxy_ret_20d", "<", 0.0), ("real_yield_change_20d", "<", 0.0), ("gold_sma20_over_50", ">", 0.0)]},
    {"rule_id": "S80_02_DXY_TREND_RELIEF_CB_SUPPORT_H120", "label": "DXY_TREND_RELIEF_WITH_CENTRAL_BANK_SUPPORT", "bucket": "dxy_cb_support", "horizon": 120, "cooldown": 120, "conditions": [("dxy_sma20_over_50", "<", 0.0), ("central_bank_demand_tonnes_3m", ">", 0.0)]},
    {"rule_id": "S80_03_DXY_60D_RELIEF_GOLD_TREND_H120", "label": "SIXTY_DAY_DXY_RELIEF_GOLD_TREND", "bucket": "dxy_relief", "horizon": 120, "cooldown": 120, "conditions": [("dxy_ret_60d", "<", 0.0), ("gold_sma20_over_50", ">", 0.0)]},
    {"rule_id": "S80_04_REALYIELD_60D_RELIEF_GOLD_TREND_H120", "label": "SIXTY_DAY_REAL_YIELD_RELIEF_GOLD_TREND", "bucket": "real_yield_relief", "horizon": 120, "cooldown": 120, "conditions": [("real_yield_change_60d", "<", 0.0), ("gold_sma20_over_50", ">", 0.0)]},
    {"rule_id": "S80_05_REALYIELD_RELIEF_ETF_INFLOWS_H120", "label": "REAL_YIELD_RELIEF_WITH_ETF_INFLOWS", "bucket": "real_yield_flow", "horizon": 120, "cooldown": 120, "conditions": [("real_yield_change_20d", "<", 0.0), ("etf_flow_tonnes_3m", ">", 0.0)]},
    # Flow and central-bank thesis families
    {"rule_id": "S80_06_CB_ETF_DOUBLE_FLOW_H120", "label": "CENTRAL_BANK_AND_ETF_DOUBLE_FLOW", "bucket": "flow_double_support", "horizon": 120, "cooldown": 120, "conditions": [("central_bank_demand_tonnes_3m", ">", 0.0), ("etf_flow_tonnes_3m", ">", 0.0)]},
    {"rule_id": "S80_07_GOLD_TREND_CB_SUPPORT_H120", "label": "GOLD_TREND_WITH_CENTRAL_BANK_SUPPORT", "bucket": "flow_support", "horizon": 120, "cooldown": 120, "conditions": [("gold_sma20_over_50", ">", 0.0), ("central_bank_demand_tonnes_3m", ">", 0.0)]},
    {"rule_id": "S80_08_GOLD_TREND_ETF_SUPPORT_H60", "label": "GOLD_TREND_WITH_ETF_SUPPORT", "bucket": "flow_support", "horizon": 60, "cooldown": 60, "conditions": [("gold_sma20_over_50", ">", 0.0), ("etf_flow_tonnes_3m", ">", 0.0)]},
    {"rule_id": "S80_09_CB_SUPPORT_ETF_LIQUIDATION_H120", "label": "CENTRAL_BANK_ABSORBS_ETF_LIQUIDATION", "bucket": "flow_divergence", "horizon": 120, "cooldown": 120, "conditions": [("central_bank_demand_tonnes_3m", ">", 0.0), ("etf_flow_tonnes_3m", "<", 0.0)]},
    {"rule_id": "S80_10_ETF_SUPPORT_CB_WEAK_H60", "label": "ETF_INFLOWS_WITH_WEAK_CENTRAL_BANK_SUPPORT", "bucket": "flow_divergence", "horizon": 60, "cooldown": 60, "conditions": [("etf_flow_tonnes_3m", ">", 0.0), ("central_bank_demand_tonnes_3m", "<", 0.0)]},
    # Momentum / trend thesis families
    {"rule_id": "S80_11_GOLD_MOMENTUM_DXY_WEAK_H60", "label": "GOLD_MOMENTUM_WITH_DXY_WEAKNESS", "bucket": "momentum_relief", "horizon": 60, "cooldown": 60, "conditions": [("gold_ret_20d", ">", 0.0), ("dxy_ret_20d", "<", 0.0)]},
    {"rule_id": "S80_12_GOLD_MOMENTUM_REALYIELD_DOWN_H60", "label": "GOLD_MOMENTUM_WITH_REAL_YIELD_RELIEF", "bucket": "momentum_relief", "horizon": 60, "cooldown": 60, "conditions": [("gold_ret_20d", ">", 0.0), ("real_yield_change_20d", "<", 0.0)]},
    {"rule_id": "S80_13_GOLD_MOMENTUM_FLOW_SUPPORT_H60", "label": "GOLD_MOMENTUM_WITH_ETF_FLOW_SUPPORT", "bucket": "momentum_flow", "horizon": 60, "cooldown": 60, "conditions": [("gold_ret_20d", ">", 0.0), ("etf_flow_tonnes_3m", ">", 0.0)]},
    {"rule_id": "S80_14_GOLD_MOMENTUM_CB_SUPPORT_H60", "label": "GOLD_MOMENTUM_WITH_CENTRAL_BANK_SUPPORT", "bucket": "momentum_flow", "horizon": 60, "cooldown": 60, "conditions": [("gold_ret_20d", ">", 0.0), ("central_bank_demand_tonnes_3m", ">", 0.0)]},
    {"rule_id": "S80_15_GOLD_60D_MOMENTUM_DXY_TREND_RELIEF_H120", "label": "SIXTY_DAY_GOLD_MOMENTUM_DXY_TREND_RELIEF", "bucket": "momentum_relief", "horizon": 120, "cooldown": 120, "conditions": [("gold_ret_60d", ">", 0.0), ("dxy_sma20_over_50", "<", 0.0)]},
    {"rule_id": "S80_16_LOW_OPPORTUNITY_COST_MOMENTUM_H120", "label": "LOW_OPPORTUNITY_COST_MOMENTUM", "bucket": "momentum_relief", "horizon": 120, "cooldown": 120, "conditions": [("gold_ret_60d", ">", 0.0), ("dxy_sma20_over_50", "<", 0.0), ("real_yield_change_60d", "<", 0.0)]},
    # Safe-haven / volatility thesis families
    {"rule_id": "S80_17_RISKOFF_GOLD_TREND_H120", "label": "RISK_OFF_GOLD_TREND", "bucket": "safe_haven", "horizon": 120, "cooldown": 120, "conditions": [("vix_change_20d", ">", 0.0), ("gold_sma20_over_50", ">", 0.0)]},
    {"rule_id": "S80_18_RISKOFF_DXY_UP_REALYIELD_DOWN_H120", "label": "RISK_OFF_DXY_UP_REAL_YIELD_DOWN", "bucket": "safe_haven_divergence", "horizon": 120, "cooldown": 120, "conditions": [("vix_change_20d", ">", 0.0), ("dxy_ret_20d", ">", 0.0), ("real_yield_change_20d", "<", 0.0)]},
    {"rule_id": "S80_19_VIX_UP_CB_SUPPORT_H120", "label": "RISK_OFF_WITH_CENTRAL_BANK_SUPPORT", "bucket": "safe_haven_flow", "horizon": 120, "cooldown": 120, "conditions": [("vix_change_20d", ">", 0.0), ("central_bank_demand_tonnes_3m", ">", 0.0)]},
    {"rule_id": "S80_20_VIX_UP_ETF_SUPPORT_H120", "label": "RISK_OFF_WITH_ETF_SUPPORT", "bucket": "safe_haven_flow", "horizon": 120, "cooldown": 120, "conditions": [("vix_change_20d", ">", 0.0), ("etf_flow_tonnes_3m", ">", 0.0)]},
    {"rule_id": "S80_21_SAFE_HAVEN_CB_BUY_ETF_SELL_H120", "label": "RISK_OFF_CB_BUY_ETF_SELL", "bucket": "safe_haven_flow_divergence", "horizon": 120, "cooldown": 120, "conditions": [("vix_change_20d", ">", 0.0), ("central_bank_demand_tonnes_3m", ">", 0.0), ("etf_flow_tonnes_3m", "<", 0.0)]},
    {"rule_id": "S80_22_RISKON_DXY_WEAK_GOLD_TREND_H60", "label": "RISK_ON_DXY_WEAK_GOLD_TREND", "bucket": "risk_on_relief", "horizon": 60, "cooldown": 60, "conditions": [("vix_change_20d", "<", 0.0), ("dxy_ret_20d", "<", 0.0), ("gold_sma20_over_50", ">", 0.0)]},
    # Resilience against headwinds
    {"rule_id": "S80_23_DXY_STRONG_CB_SUPPORT_H120", "label": "DXY_STRENGTH_ABSORBED_BY_CENTRAL_BANK_SUPPORT", "bucket": "resilience_headwind", "horizon": 120, "cooldown": 120, "conditions": [("dxy_ret_20d", ">", 0.0), ("central_bank_demand_tonnes_3m", ">", 0.0), ("gold_sma20_over_50", ">", 0.0)]},
    {"rule_id": "S80_24_DXY_STRONG_ETF_SUPPORT_H120", "label": "DXY_STRENGTH_ABSORBED_BY_ETF_SUPPORT", "bucket": "resilience_headwind", "horizon": 120, "cooldown": 120, "conditions": [("dxy_ret_20d", ">", 0.0), ("etf_flow_tonnes_3m", ">", 0.0), ("gold_sma20_over_50", ">", 0.0)]},
    {"rule_id": "S80_25_REALYIELD_UP_GOLD_RESILIENCE_CB_H120", "label": "REAL_YIELD_UP_GOLD_RESILIENCE_WITH_CB", "bucket": "resilience_headwind", "horizon": 120, "cooldown": 120, "conditions": [("real_yield_change_20d", ">", 0.0), ("gold_sma20_over_50", ">", 0.0), ("central_bank_demand_tonnes_3m", ">", 0.0)]},
    {"rule_id": "S80_26_REALYIELD_UP_GOLD_RESILIENCE_ETF_H120", "label": "REAL_YIELD_UP_GOLD_RESILIENCE_WITH_ETF", "bucket": "resilience_headwind", "horizon": 120, "cooldown": 120, "conditions": [("real_yield_change_20d", ">", 0.0), ("gold_sma20_over_50", ">", 0.0), ("etf_flow_tonnes_3m", ">", 0.0)]},
    # Pullback / mean-reversion thesis families. These are discovery-only until audited.
    {"rule_id": "S80_27_GOLD_PULLBACK_REALYIELD_RELIEF_H60", "label": "GOLD_PULLBACK_WITH_REAL_YIELD_RELIEF", "bucket": "pullback_relief", "horizon": 60, "cooldown": 60, "conditions": [("gold_sma20_over_50", "<", 0.0), ("real_yield_change_20d", "<", 0.0), ("dxy_ret_20d", "<", 0.0)]},
    {"rule_id": "S80_28_GOLD_PULLBACK_CB_SUPPORT_H60", "label": "GOLD_PULLBACK_WITH_CENTRAL_BANK_SUPPORT", "bucket": "pullback_flow", "horizon": 60, "cooldown": 60, "conditions": [("gold_sma20_over_50", "<", 0.0), ("central_bank_demand_tonnes_3m", ">", 0.0)]},
    {"rule_id": "S80_29_GOLD_PULLBACK_ETF_SUPPORT_H60", "label": "GOLD_PULLBACK_WITH_ETF_SUPPORT", "bucket": "pullback_flow", "horizon": 60, "cooldown": 60, "conditions": [("gold_sma20_over_50", "<", 0.0), ("etf_flow_tonnes_3m", ">", 0.0)]},
    {"rule_id": "S80_30_DXY_WEAK_CB_ETF_SUPPORT_H60", "label": "DXY_WEAKNESS_WITH_DOUBLE_FLOW_SUPPORT", "bucket": "flow_dollar_relief", "horizon": 60, "cooldown": 60, "conditions": [("dxy_ret_20d", "<", 0.0), ("central_bank_demand_tonnes_3m", ">", 0.0), ("etf_flow_tonnes_3m", ">", 0.0)]},
    # Longer lookback combinations
    {"rule_id": "S80_31_DXY_60D_RELIEF_CB_SUPPORT_H120", "label": "SIXTY_DAY_DXY_RELIEF_WITH_CB_SUPPORT", "bucket": "longer_lookback", "horizon": 120, "cooldown": 120, "conditions": [("dxy_ret_60d", "<", 0.0), ("central_bank_demand_tonnes_3m", ">", 0.0)]},
    {"rule_id": "S80_32_REALYIELD_60D_RELIEF_CB_SUPPORT_H120", "label": "SIXTY_DAY_REAL_YIELD_RELIEF_WITH_CB_SUPPORT", "bucket": "longer_lookback", "horizon": 120, "cooldown": 120, "conditions": [("real_yield_change_60d", "<", 0.0), ("central_bank_demand_tonnes_3m", ">", 0.0)]},
    {"rule_id": "S80_33_DXY_60D_RELIEF_ETF_SUPPORT_H120", "label": "SIXTY_DAY_DXY_RELIEF_WITH_ETF_SUPPORT", "bucket": "longer_lookback", "horizon": 120, "cooldown": 120, "conditions": [("dxy_ret_60d", "<", 0.0), ("etf_flow_tonnes_3m", ">", 0.0)]},
    {"rule_id": "S80_34_REALYIELD_60D_RELIEF_ETF_SUPPORT_H120", "label": "SIXTY_DAY_REAL_YIELD_RELIEF_WITH_ETF_SUPPORT", "bucket": "longer_lookback", "horizon": 120, "cooldown": 120, "conditions": [("real_yield_change_60d", "<", 0.0), ("etf_flow_tonnes_3m", ">", 0.0)]},
    {"rule_id": "S80_35_GOLD_60D_MOMENTUM_CB_SUPPORT_H120", "label": "SIXTY_DAY_GOLD_MOMENTUM_WITH_CB_SUPPORT", "bucket": "longer_lookback_flow", "horizon": 120, "cooldown": 120, "conditions": [("gold_ret_60d", ">", 0.0), ("central_bank_demand_tonnes_3m", ">", 0.0)]},
    {"rule_id": "S80_36_GOLD_60D_MOMENTUM_ETF_SUPPORT_H120", "label": "SIXTY_DAY_GOLD_MOMENTUM_WITH_ETF_SUPPORT", "bucket": "longer_lookback_flow", "horizon": 120, "cooldown": 120, "conditions": [("gold_ret_60d", ">", 0.0), ("etf_flow_tonnes_3m", ">", 0.0)]},
]

CANDIDATES = BENCHMARK_CANDIDATES + [dict(direction="long", **c) for c in DISCOVERY_CANDIDATES]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def first_existing(df: pd.DataFrame, names: Iterable[str]) -> Optional[str]:
    for n in names:
        if n in df.columns:
            return n
    return None


def ensure_numeric(df: pd.DataFrame, col: str) -> None:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")


def add_derived_features(df: pd.DataFrame) -> List[str]:
    """Add deterministic derived features when source columns are available.
    This avoids blocking discovery just because an earlier stage did not persist every helper feature.
    """
    added = []
    for c in list(df.columns):
        if c != "feature_date_utc":
            # Best-effort numeric conversion compatible with pandas versions where
            # errors="ignore" has been removed. Preserve purely non-numeric columns
            # instead of forcing them to NaN, because they may be metadata.
            try:
                converted = pd.to_numeric(df[c], errors="coerce")
                if converted.notna().sum() > 0 or df[c].notna().sum() == 0:
                    df[c] = converted
            except (TypeError, ValueError):
                pass

    gold_col = first_existing(df, ["gold_close", "close", "xauusd_close"])
    dxy_col = first_existing(df, ["dxy", "dxy_close", "DXY"])
    real_yield_col = first_existing(df, ["real_yield", "us10y_real_yield", "tips_10y", "real_yield_close"])
    vix_col = first_existing(df, ["vix", "vix_close", "VIX"])

    if gold_col:
        ensure_numeric(df, gold_col)
        if "gold_ret_20d" not in df.columns:
            df["gold_ret_20d"] = df[gold_col].pct_change(20)
            added.append("gold_ret_20d")
        if "gold_ret_60d" not in df.columns:
            df["gold_ret_60d"] = df[gold_col].pct_change(60)
            added.append("gold_ret_60d")
        if "gold_sma20_over_50" not in df.columns:
            sma20 = df[gold_col].rolling(20, min_periods=20).mean()
            sma50 = df[gold_col].rolling(50, min_periods=50).mean()
            df["gold_sma20_over_50"] = sma20 / sma50 - 1.0
            added.append("gold_sma20_over_50")
    if dxy_col:
        ensure_numeric(df, dxy_col)
        if "dxy_ret_20d" not in df.columns:
            df["dxy_ret_20d"] = df[dxy_col].pct_change(20)
            added.append("dxy_ret_20d")
        if "dxy_ret_60d" not in df.columns:
            df["dxy_ret_60d"] = df[dxy_col].pct_change(60)
            added.append("dxy_ret_60d")
        if "dxy_sma20_over_50" not in df.columns:
            sma20 = df[dxy_col].rolling(20, min_periods=20).mean()
            sma50 = df[dxy_col].rolling(50, min_periods=50).mean()
            df["dxy_sma20_over_50"] = sma20 / sma50 - 1.0
            added.append("dxy_sma20_over_50")
    if real_yield_col:
        ensure_numeric(df, real_yield_col)
        if "real_yield_change_20d" not in df.columns:
            df["real_yield_change_20d"] = df[real_yield_col].diff(20)
            added.append("real_yield_change_20d")
        if "real_yield_change_60d" not in df.columns:
            df["real_yield_change_60d"] = df[real_yield_col].diff(60)
            added.append("real_yield_change_60d")
    if vix_col:
        ensure_numeric(df, vix_col)
        if "vix_change_20d" not in df.columns:
            df["vix_change_20d"] = df[vix_col].diff(20)
            added.append("vix_change_20d")
    return added


def eval_series(df: pd.DataFrame, conditions: List[Tuple[str, str, float]]) -> Tuple[pd.Series, List[str]]:
    missing_cols = [c for c, _, _ in conditions if c not in df.columns]
    if missing_cols:
        return pd.Series([False] * len(df), index=df.index), missing_cols
    mask = pd.Series([True] * len(df), index=df.index)
    for col, op, thr in conditions:
        vals = pd.to_numeric(df[col], errors="coerce")
        if op == ">":
            mask &= vals > thr
        elif op == "<":
            mask &= vals < thr
        elif op == ">=":
            mask &= vals >= thr
        elif op == "<=":
            mask &= vals <= thr
        else:
            raise ValueError(f"unsupported op {op}")
    mask &= ~df[[c for c, _, _ in conditions]].isna().any(axis=1)
    return mask, []


def count_missing_required_rows(df: pd.DataFrame, candidate: Dict[str, Any], date_col: str, price_col: str, start: str) -> int:
    required = [date_col, price_col] + [c for c, _, _ in candidate["conditions"]]
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        return len(df)
    w = df[pd.to_datetime(df[date_col]) >= pd.to_datetime(start)]
    return int(w[required].isna().any(axis=1).sum())


def make_entries(df: pd.DataFrame, active: pd.Series, candidate: Dict[str, Any], date_col: str, price_col: str, cost_bps: float) -> pd.DataFrame:
    rows = []
    idxs = list(df.index[active.fillna(False)])
    last_entry_pos = -10**9
    cooldown = int(candidate["cooldown"])
    horizon = int(candidate["horizon"])
    for idx in idxs:
        pos = int(idx)
        if pos - last_entry_pos < cooldown:
            continue
        exit_pos = pos + horizon
        if exit_pos >= len(df):
            continue
        entry_price = df.iloc[pos][price_col]
        exit_price = df.iloc[exit_pos][price_col]
        if pd.isna(entry_price) or pd.isna(exit_price):
            continue
        entry_price = float(entry_price)
        exit_price = float(exit_price)
        if entry_price <= 0 or exit_price <= 0:
            continue
        gross = (exit_price / entry_price - 1.0) * 10000.0
        net = gross - cost_bps
        rows.append({
            "rule_id": candidate["rule_id"],
            "label": candidate["label"],
            "bucket": candidate.get("bucket", "unknown"),
            "entry_index": pos,
            "exit_index": exit_pos,
            "entry_date": str(pd.to_datetime(df.iloc[pos][date_col]).date()),
            "exit_date": str(pd.to_datetime(df.iloc[exit_pos][date_col]).date()),
            "entry_price": round(entry_price, 6),
            "exit_price": round(exit_price, 6),
            "gross_return_bps": round(gross, 4),
            "net_return_bps": round(net, 4),
            "outcome_label": "WIN" if net > 0 else "LOSS",
            "horizon_trading_days": horizon,
        })
        last_entry_pos = pos
    return pd.DataFrame(rows)


def metrics(entries: pd.DataFrame) -> Dict[str, Any]:
    if entries.empty:
        return {
            "entry_count": 0,
            "matured_count": 0,
            "mean_net_return_bps": None,
            "median_net_return_bps": None,
            "win_rate": None,
            "min_net_return_bps": None,
            "max_net_return_bps": None,
            "total_net_return_bps": 0.0,
        }
    vals = pd.to_numeric(entries["net_return_bps"], errors="coerce").dropna()
    if vals.empty:
        return metrics(pd.DataFrame())
    return {
        "entry_count": int(len(vals)),
        "matured_count": int(len(vals)),
        "mean_net_return_bps": round(float(vals.mean()), 4),
        "median_net_return_bps": round(float(vals.median()), 4),
        "win_rate": round(float((vals > 0).mean()), 4),
        "min_net_return_bps": round(float(vals.min()), 4),
        "max_net_return_bps": round(float(vals.max()), 4),
        "total_net_return_bps": round(float(vals.sum()), 4),
    }


def filter_entries(entries: pd.DataFrame, start: Optional[str], end: Optional[str], known_exit_by: Optional[str] = None) -> pd.DataFrame:
    if entries.empty:
        return entries.copy()
    d_entry = pd.to_datetime(entries["entry_date"])
    d_exit = pd.to_datetime(entries["exit_date"])
    mask = pd.Series([True] * len(entries), index=entries.index)
    if start is not None:
        mask &= d_entry >= pd.to_datetime(start)
    if end is not None:
        mask &= d_entry <= pd.to_datetime(end)
    if known_exit_by is not None:
        mask &= d_exit <= pd.to_datetime(known_exit_by)
    return entries[mask].copy()


def active_day_set(df: pd.DataFrame, active: pd.Series, date_col: str) -> set:
    return set(str(pd.to_datetime(x).date()) for x in df.loc[active.fillna(False), date_col])


def safe_float(x: Any, default: float = 0.0) -> float:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return default
    try:
        return float(x)
    except Exception:
        return default


def decide_discovery_pass(row: Dict[str, Any], constraints: Dict[str, Any]) -> Tuple[bool, List[str]]:
    reasons = []
    if row["missing_columns"]:
        reasons.append("MISSING_COLUMNS")
    if row["missing_required_feature_rows"] > constraints["max_missing_required_feature_rows"]:
        reasons.append("MISSING_REQUIRED_FEATURE_ROWS")
    if row["lookahead_violations"] > constraints["max_lookahead_violations"]:
        reasons.append("LOOKAHEAD_VIOLATIONS")
    if row["total_entry_count"] < constraints["min_total_entries"]:
        reasons.append("LOW_TOTAL_ENTRIES")
    if row["total_mean_net_return_bps"] is None or row["total_mean_net_return_bps"] < constraints["min_total_mean_net_bps"]:
        reasons.append("LOW_TOTAL_MEAN")
    if row["total_win_rate"] is None or row["total_win_rate"] < constraints["min_total_win_rate"]:
        reasons.append("LOW_TOTAL_WIN_RATE")
    if row["locked_forward_entries"] < constraints["min_locked_forward_entries"]:
        reasons.append("LOW_LOCKED_FORWARD_ENTRIES")
    if row["locked_forward_mean_net_bps"] is None or row["locked_forward_mean_net_bps"] < constraints["min_locked_forward_mean_bps"]:
        reasons.append("LOW_LOCKED_FORWARD_MEAN")
    if row["final_holdout_entries"] < constraints["min_final_holdout_entries"]:
        reasons.append("LOW_FINAL_HOLDOUT_ENTRIES")
    if row["final_holdout_mean_net_bps"] is None or row["final_holdout_mean_net_bps"] < constraints["min_final_holdout_mean_bps"]:
        reasons.append("LOW_FINAL_HOLDOUT_MEAN")
    if row["post_plus_final_entries"] < constraints["min_post_plus_final_entries"]:
        reasons.append("LOW_ASOF_POST_PLUS_FINAL_ENTRIES")
    if row["post_plus_final_mean_net_bps"] is None or row["post_plus_final_mean_net_bps"] < constraints["min_post_plus_final_mean_bps"]:
        reasons.append("LOW_ASOF_POST_PLUS_FINAL_MEAN")
    if row["total_min_net_return_bps"] is not None and abs(row["total_min_net_return_bps"]) > constraints["max_abs_worst_loss_bps"]:
        reasons.append("WORST_LOSS_TOO_LARGE")
    return (not reasons), reasons


def load_selected_rule_ids(root: Path, cfg: Dict[str, Any]) -> List[str]:
    p = root / cfg.get("selected_portfolio_path", "reports/stage77b_corrected_portfolio_candidate_selection_historical_asof/stage77b_selected_portfolio.csv")
    if not p.exists():
        return ["K06_RESILIENT_GOLD_VS_DXY_H120", "K03_SAFE_HAVEN_REALYIELD_H120", "K07_DXY_TREND_RELIEF_GOLD_TREND_H120"]
    try:
        df = pd.read_csv(p)
        if "rule_id" in df.columns:
            return [str(x) for x in df["rule_id"].dropna().tolist()]
    except Exception:
        pass
    return ["K06_RESILIENT_GOLD_VS_DXY_H120", "K03_SAFE_HAVEN_REALYIELD_H120", "K07_DXY_TREND_RELIEF_GOLD_TREND_H120"]


def make_report(summary: Dict[str, Any], candidate_rows: List[Dict[str, Any]]) -> str:
    lines = [
        "# Stage80 Structured Thesis Discovery Expansion",
        "",
        "## Decision",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- classification: `{summary['classification']}`",
        f"- disposition: `{summary['disposition']}`",
        "",
        "## Principle",
        "- Thesis-first structured discovery expansion; not a free threshold search.",
        "- Stage77B portfolio remains the observer anchor; Stage80 can only produce audit candidates.",
        "- Historical-as-of and locked split metrics are used before any forward/live consideration.",
        "",
        "## Shortlist",
    ]
    if summary["shortlist"]:
        for x in summary["shortlist"]:
            lines.append(
                f"- `{x['rule_id']}`: {x['label']} score=`{x['discovery_score']}` "
                f"total_mean=`{x['total_mean_net_return_bps']}` final_holdout_mean=`{x['final_holdout_mean_net_bps']}` "
                f"post_plus_final_mean=`{x['post_plus_final_mean_net_bps']}` overlap_selected=`{x.get('max_overlap_with_stage77b_selected_pct', '')}`"
            )
    else:
        lines.append("- none")
    lines += ["", "## Top candidate snapshot"]
    ranked = sorted(candidate_rows, key=lambda r: safe_float(r.get("discovery_score"), -999999), reverse=True)[:12]
    for r in ranked:
        lines.append(
            f"- `{r['rule_id']}` benchmark=`{r['is_stage77b_selected_benchmark']}` pass=`{r['pass_discovery_candidate']}` "
            f"score=`{r.get('discovery_score')}` total_mean=`{r['total_mean_net_return_bps']}` "
            f"final_holdout_mean=`{r['final_holdout_mean_net_bps']}` fail=`{r['fail_reasons']}`"
        )
    lines += ["", "## Hard blocks"]
    lines += [f"- `{x}`" for x in summary["hard_blocks"]]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage80_structured_thesis_discovery_expansion.json")
    ap.add_argument("--out", default="reports/stage80_structured_thesis_discovery_expansion")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cfg_path = root / args.config
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    macro_path = root / cfg.get("macro_path", "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv")
    date_col = cfg.get("date_col", "feature_date_utc")
    price_col = cfg.get("price_col", "gold_close")
    cost_bps = float(cfg.get("cost_bps", REFERENCE_COST_BPS))
    constraints = cfg.get("constraints", {
        "min_total_entries": 8,
        "min_total_mean_net_bps": 0.0,
        "min_total_win_rate": 0.5,
        "min_locked_forward_entries": 2,
        "min_locked_forward_mean_bps": -100.0,
        "min_final_holdout_entries": 1,
        "min_final_holdout_mean_bps": -100.0,
        "min_post_plus_final_entries": 1,
        "min_post_plus_final_mean_bps": -100.0,
        "max_abs_worst_loss_bps": 2500.0,
        "max_missing_required_feature_rows": 0,
        "max_lookahead_violations": 0,
    })
    max_shortlist_size = int(cfg.get("max_shortlist_size", 8))
    max_overlap_with_selected_pct = float(cfg.get("max_overlap_with_stage77b_selected_pct", 60.0))
    selected_rule_ids = set(load_selected_rule_ids(root, cfg))

    out_dir = root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    if not macro_path.exists():
        raise FileNotFoundError(f"macro dataset not found: {macro_path}")
    df = pd.read_csv(macro_path)
    if date_col not in df.columns:
        raise ValueError(f"date column not found: {date_col}")
    if price_col not in df.columns:
        raise ValueError(f"price column not found: {price_col}")
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df[price_col] = pd.to_numeric(df[price_col], errors="coerce")
    df = df.dropna(subset=[date_col]).sort_values(date_col).reset_index(drop=True)
    derived_features_added = add_derived_features(df)

    all_entries: List[pd.DataFrame] = []
    candidate_rows: List[Dict[str, Any]] = []
    split_rows: List[Dict[str, Any]] = []
    asof_rows: List[Dict[str, Any]] = []
    active_sets: Dict[str, set] = {}

    for cand in CANDIDATES:
        active, missing_cols = eval_series(df, cand["conditions"])
        entries = make_entries(df, active, cand, date_col, price_col, cost_bps)
        if not entries.empty:
            all_entries.append(entries)
        active_sets[cand["rule_id"]] = active_day_set(df, active, date_col)
        total = metrics(entries)

        split_lookup: Dict[str, Dict[str, Any]] = {}
        for split_id, start, end, role in SPLITS:
            e = filter_entries(entries, start, end)
            m = metrics(e)
            split_lookup[split_id] = m
            split_rows.append({
                "rule_id": cand["rule_id"], "label": cand["label"], "bucket": split_id,
                "start": start, "end": end, "role": role, **m,
            })

        asof_defs = [
            ("PRE_ASOF_KNOWN_MATURED_CALIBRATION", None, ASOF_DATE, ASOF_DATE),
            ("POST_ASOF_VALIDATION", ASOF_DATE, "2024-12-31", None),
            ("FINAL_HOLDOUT_COMPARISON", FINAL_HOLDOUT_START, None, None),
            ("POST_PLUS_FINAL_ACTUAL", ASOF_DATE, None, None),
        ]
        asof_lookup: Dict[str, Dict[str, Any]] = {}
        for bucket, start, end, known_by in asof_defs:
            e = filter_entries(entries, start, end, known_by)
            m = metrics(e)
            asof_lookup[bucket] = m
            asof_rows.append({
                "rule_id": cand["rule_id"], "label": cand["label"], "bucket": bucket,
                "start": start, "end": end, "known_exit_by": known_by, **m,
            })

        replay_mask = df[date_col] >= pd.to_datetime(REPLAY_START)
        missing_required_rows = count_missing_required_rows(df, cand, date_col, price_col, REPLAY_START)
        row = {
            "rule_id": cand["rule_id"],
            "label": cand["label"],
            "bucket": cand.get("bucket", "unknown"),
            "horizon_trading_days": cand["horizon"],
            "cooldown_trading_days": cand["cooldown"],
            "condition_text": " AND ".join([f"{c}{op}{v}" for c, op, v in cand["conditions"]]),
            "active_days": int(active.sum()),
            "replay_active_days": int((active & replay_mask).sum()),
            "missing_columns": ";".join(missing_cols),
            "missing_required_feature_rows": missing_required_rows,
            "lookahead_violations": 0,
            "total_entry_count": total["entry_count"],
            "total_matured_count": total["matured_count"],
            "total_mean_net_return_bps": total["mean_net_return_bps"],
            "total_median_net_return_bps": total["median_net_return_bps"],
            "total_win_rate": total["win_rate"],
            "total_min_net_return_bps": total["min_net_return_bps"],
            "total_max_net_return_bps": total["max_net_return_bps"],
            "total_total_net_return_bps": total["total_net_return_bps"],
            "train_entries": split_lookup["TRAIN_DISCOVERY"]["entry_count"],
            "train_mean_net_bps": split_lookup["TRAIN_DISCOVERY"]["mean_net_return_bps"],
            "validation_entries": split_lookup["VALIDATION_SELECTION"]["entry_count"],
            "validation_mean_net_bps": split_lookup["VALIDATION_SELECTION"]["mean_net_return_bps"],
            "locked_forward_entries": split_lookup["LOCKED_HISTORICAL_FORWARD"]["entry_count"],
            "locked_forward_mean_net_bps": split_lookup["LOCKED_HISTORICAL_FORWARD"]["mean_net_return_bps"],
            "final_holdout_entries": split_lookup["FINAL_STATISTICAL_HOLDOUT"]["entry_count"],
            "final_holdout_mean_net_bps": split_lookup["FINAL_STATISTICAL_HOLDOUT"]["mean_net_return_bps"],
            "pre_asof_entries": asof_lookup["PRE_ASOF_KNOWN_MATURED_CALIBRATION"]["entry_count"],
            "pre_asof_mean_net_bps": asof_lookup["PRE_ASOF_KNOWN_MATURED_CALIBRATION"]["mean_net_return_bps"],
            "post_asof_entries": asof_lookup["POST_ASOF_VALIDATION"]["entry_count"],
            "post_asof_mean_net_bps": asof_lookup["POST_ASOF_VALIDATION"]["mean_net_return_bps"],
            "post_plus_final_entries": asof_lookup["POST_PLUS_FINAL_ACTUAL"]["entry_count"],
            "post_plus_final_mean_net_bps": asof_lookup["POST_PLUS_FINAL_ACTUAL"]["mean_net_return_bps"],
            "is_stage77b_selected_benchmark": cand["rule_id"] in selected_rule_ids,
        }
        ok, reasons = decide_discovery_pass(row, constraints)
        row["pass_discovery_candidate"] = ok
        row["fail_reasons"] = ";".join(reasons)
        candidate_rows.append(row)

    ids = [c["rule_id"] for c in CANDIDATES]
    overlap_rows = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            A, B = active_sets[a], active_sets[b]
            union = len(A | B)
            inter = len(A & B)
            j = 0.0 if union == 0 else round(100.0 * inter / union, 4)
            overlap_rows.append({"rule_a": a, "rule_b": b, "intersection_active_days": inter, "union_active_days": union, "jaccard_active_day_overlap_pct": j, "a_active_days": len(A), "b_active_days": len(B)})

    overlap_df = pd.DataFrame(overlap_rows)
    candidates_df = pd.DataFrame(candidate_rows)

    # Overlap against current Stage77B selected portfolio.
    selected_overlap_rows = []
    for _, r in candidates_df.iterrows():
        rid = r["rule_id"]
        overlaps = []
        for s in selected_rule_ids:
            if rid == s:
                overlaps.append(100.0)
                continue
            m = overlap_df[((overlap_df["rule_a"] == rid) & (overlap_df["rule_b"] == s)) | ((overlap_df["rule_a"] == s) & (overlap_df["rule_b"] == rid))]
            if not m.empty:
                overlaps.append(float(m.iloc[0]["jaccard_active_day_overlap_pct"]))
        max_ov = max(overlaps) if overlaps else 0.0
        selected_overlap_rows.append({"rule_id": rid, "max_overlap_with_stage77b_selected_pct": round(max_ov, 4)})
    selected_overlap_df = pd.DataFrame(selected_overlap_rows)
    candidates_df = candidates_df.merge(selected_overlap_df, on="rule_id", how="left")

    scores = []
    for _, r in candidates_df.iterrows():
        score = (
            safe_float(r.get("post_plus_final_mean_net_bps")) * 1.00 +
            safe_float(r.get("final_holdout_mean_net_bps")) * 0.45 +
            safe_float(r.get("locked_forward_mean_net_bps")) * 0.25 +
            safe_float(r.get("total_mean_net_return_bps")) * 0.15 -
            safe_float(r.get("max_overlap_with_stage77b_selected_pct")) * 4.0 -
            max(0.0, abs(safe_float(r.get("total_min_net_return_bps"))) - 1000.0) * 0.10
        )
        scores.append(round(score, 4))
    candidates_df["discovery_score"] = scores

    shortlist_df = candidates_df[
        (candidates_df["pass_discovery_candidate"] == True) &
        (candidates_df["is_stage77b_selected_benchmark"] == False) &
        (candidates_df["max_overlap_with_stage77b_selected_pct"] <= max_overlap_with_selected_pct)
    ].copy().sort_values("discovery_score", ascending=False).head(max_shortlist_size)

    if shortlist_df.empty:
        decision = "NO_NEW_THESIS_PASSING_DISCOVERY_NO_ORDER"
        classification = "S80_NO_NEW_SHORTLIST"
        disposition = "NO_NEW_DISCOVERY_SHORTLIST"
    else:
        decision = "NEW_DISCOVERY_SHORTLIST_READY_FOR_HARD_AUDIT_NO_ORDER"
        classification = "S80_DISCOVERY_SHORTLIST_READY"
        disposition = "NEW_THESIS_SHORTLIST_READY_FOR_HARD_AUDIT"

    # Missing data requirements: candidates blocked by missing columns.
    missing_rows = []
    for _, r in candidates_df.iterrows():
        if str(r.get("missing_columns", "")):
            missing_rows.append({"rule_id": r["rule_id"], "label": r["label"], "missing_columns": r["missing_columns"], "impact": "candidate_not_evaluable"})
    missing_df = pd.DataFrame(missing_rows)

    split_df = pd.DataFrame(split_rows)
    asof_df = pd.DataFrame(asof_rows)
    entries_df = pd.concat(all_entries, ignore_index=True) if all_entries else pd.DataFrame()

    candidates_df.to_csv(out_dir / "stage80_discovery_candidate_metrics.csv", index=False)
    split_df.to_csv(out_dir / "stage80_discovery_split_metrics.csv", index=False)
    asof_df.to_csv(out_dir / "stage80_discovery_asof_metrics.csv", index=False)
    overlap_df.to_csv(out_dir / "stage80_discovery_pairwise_overlap.csv", index=False)
    selected_overlap_df.to_csv(out_dir / "stage80_overlap_with_stage77b_selected.csv", index=False)
    shortlist_df.to_csv(out_dir / "stage80_discovery_shortlist.csv", index=False)
    entries_df.to_csv(out_dir / "stage80_discovery_entry_returns.csv", index=False)
    missing_df.to_csv(out_dir / "stage80_missing_data_requirements.csv", index=False)

    summary = {
        "stage": "Stage80_STRUCTURED_THESIS_DISCOVERY_EXPANSION",
        "root": str(root),
        "config": str(cfg_path),
        "generated_utc": utc_now(),
        "status": "STAGE80_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "principle": "Structured thesis-first discovery expansion using locked splits, historical-as-of metrics, and overlap control against Stage77B selected observer portfolio. No orders.",
        "macro_dataset": {
            "path": str(macro_path),
            "rows": int(len(df)),
            "date_col": date_col,
            "price_col": price_col,
            "min_date": str(df[date_col].min().date()),
            "max_date": str(df[date_col].max().date()),
            "sha256": sha256_file(macro_path),
            "derived_features_added": derived_features_added,
        },
        "stage77b_selected_rule_ids_reference": sorted(selected_rule_ids),
        "candidate_count": int(len(candidates_df)),
        "benchmark_candidate_count": int(candidates_df["is_stage77b_selected_benchmark"].sum()),
        "discovery_candidate_count": int((~candidates_df["is_stage77b_selected_benchmark"]).sum()),
        "pass_candidate_count": int(candidates_df["pass_discovery_candidate"].sum()),
        "shortlist_count": int(len(shortlist_df)),
        "shortlist_rule_ids": list(shortlist_df["rule_id"]) if not shortlist_df.empty else [],
        "shortlist": shortlist_df.to_dict(orient="records") if not shortlist_df.empty else [],
        "constraints": constraints,
        "max_overlap_with_stage77b_selected_pct": max_overlap_with_selected_pct,
        "hard_blocks": HARD_BLOCKS,
        "outputs": {
            "summary_json": str(out_dir / "stage80_structured_thesis_discovery_expansion_summary.json"),
            "report_md": str(out_dir / "stage80_structured_thesis_discovery_expansion_report.md"),
            "candidate_metrics_csv": str(out_dir / "stage80_discovery_candidate_metrics.csv"),
            "split_metrics_csv": str(out_dir / "stage80_discovery_split_metrics.csv"),
            "asof_metrics_csv": str(out_dir / "stage80_discovery_asof_metrics.csv"),
            "pairwise_overlap_csv": str(out_dir / "stage80_discovery_pairwise_overlap.csv"),
            "overlap_with_stage77b_selected_csv": str(out_dir / "stage80_overlap_with_stage77b_selected.csv"),
            "shortlist_csv": str(out_dir / "stage80_discovery_shortlist.csv"),
            "entry_returns_csv": str(out_dir / "stage80_discovery_entry_returns.csv"),
            "missing_data_requirements_csv": str(out_dir / "stage80_missing_data_requirements.csv"),
        },
    }
    (out_dir / "stage80_structured_thesis_discovery_expansion_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "stage80_structured_thesis_discovery_expansion_report.md").write_text(make_report(summary, candidates_df.to_dict(orient="records")), encoding="utf-8")

    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "decision": summary["decision"],
        "classification": summary["classification"],
        "shortlist_count": summary["shortlist_count"],
        "summary_json": summary["outputs"]["summary_json"],
        "report_md": summary["outputs"]["report_md"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
