#!/usr/bin/env python3
"""Stage112 volatility / risk-premium rotation frontier discovery for XAUUSD.

Discovery-only. No broker, EA, MT5 bridge, paper-order, or live-order action.

The stage uses historical segmentation: selection -> validation -> tail-forward proxy.
Quantile thresholds are learned only from the selection segment and then applied
unchanged to later segments.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

STAGE = "Stage112_VOL_RISK_PREMIUM_ROTATION_FRONTIER_DISCOVERY"
DECISION_NO_PASS = "STAGE112_NO_INCREMENTAL_FRONTIER_SELECTED_NO_ORDER"
DECISION_PASS = "STAGE112_FRONTIER_SELECTED_FOR_STAGE113_REVIEW_NO_ORDER"
CLASS_NO_PASS = "S112_FRONTIER_NO_PASS_NO_ORDER"
CLASS_PASS = "S112_FRONTIER_REVIEW_ONLY_NO_ORDER"

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_MT5_OR_EA_CHANGE_FROM_STAGE112",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE112",
]

ACTIVE_OBSERVER_RULES = [
    "K06_RESILIENT_GOLD_VS_DXY_H120",
    "K03_SAFE_HAVEN_REALYIELD_H120",
    "K07_DXY_TREND_RELIEF_GOLD_TREND_H120",
    "S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120",
    "S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120",
    "C96_07_CB_SUPPORT_NOT_CROWDED_H120",
    "S105_03_COT_DECROWDING_CB_SUPPORT_RY_RELIEF_H120",
]

DEFAULT_CONFIG: Dict[str, Any] = {
    "macro_dataset": "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
    "horizon_trading_days": 120,
    "cost_bps": 20.0,
    "selection_frac": 0.60,
    "validation_frac": 0.20,
    "tail_forward_frac": 0.20,
    "min_selection_events": 25,
    "min_validation_events": 10,
    "min_tail_forward_events": 5,
    "min_selection_mean_net_bps": 10.0,
    "min_validation_mean_net_bps": 0.0,
    "min_tail_forward_mean_net_bps": 0.0,
    "min_tail_forward_win_rate": 0.50,
    "max_observer_overlap_ratio": 0.60,
    "max_year_concentration": 0.70,
    "max_selected": 5,
    "write_split_files": True,
    "hard_blocks": HARD_BLOCKS,
}

CANDIDATE_FAMILIES = [
    {
        "rule_id": "S112_01_VIX_SHOCK_GOLD_RESILIENT_DXY_NOT_CONFIRMING_H120",
        "family": "VOL_RISK_PREMIUM_ROTATION",
        "direction": "LONG",
        "description": "VIX/risk shock with gold already resilient while DXY is not confirming the stress move.",
        "conditions": [
            ["vix_change_20d", ">=", "q70"],
            ["gold_ret_20d", ">=", "q50"],
            ["dxy_ret_20d", "<=", "q60"],
            ["real_yield_change_20d", "<=", "q65"],
        ],
    },
    {
        "rule_id": "S112_02_VIX_RET_SPIKE_GOLD_DXY_DIVERGENCE_H120",
        "family": "VOL_RISK_PREMIUM_ROTATION",
        "direction": "LONG",
        "description": "VIX return spike while gold holds up and DXY is not strongly bid.",
        "conditions": [
            ["vix_ret_20d", ">=", "q70"],
            ["gold_ret_20d", ">=", "q45"],
            ["dxy_ret_20d", "<=", "q55"],
        ],
    },
    {
        "rule_id": "S112_03_VOL_RELIEF_GOLD_TREND_RECOVERY_H120",
        "family": "VOL_RISK_PREMIUM_ROTATION",
        "direction": "LONG",
        "description": "Volatility relief after stress with gold trend recovery and no DXY headwind.",
        "conditions": [
            ["vix_change_20d", "<=", "q35"],
            ["gold_ret_20d", ">=", "q60"],
            ["dxy_ret_60d", "<=", "q50"],
        ],
    },
    {
        "rule_id": "S112_04_SAFE_HAVEN_RISK_PREMIUM_REALYIELD_NON_PRESSURE_H120",
        "family": "VOL_RISK_PREMIUM_ROTATION",
        "direction": "LONG",
        "description": "Risk premium rising while real yields are not adding pressure and gold is not weak.",
        "conditions": [
            ["vix_change_20d", ">=", "q60"],
            ["real_yield_change_60d", "<=", "q50"],
            ["gold_ret_60d", ">=", "q40"],
        ],
    },
    {
        "rule_id": "S112_05_CB_SUPPORT_VOL_COMPRESSION_GOLD_RECOVERY_H120",
        "family": "CB_VOL_INTERACTION",
        "direction": "LONG",
        "description": "Central-bank support with quieter volatility and short-term gold recovery.",
        "conditions": [
            ["central_bank_demand_tonnes_3m", ">=", "q60"],
            ["abs_vix_change_20d", "<=", "q60"],
            ["gold_ret_20d", ">=", "q50"],
            ["dxy_ret_20d", "<=", "q60"],
        ],
    },
    {
        "rule_id": "S112_06_DXY_RELIEF_WITH_RISK_PREMIUM_BID_H120",
        "family": "DXY_VOL_INTERACTION",
        "direction": "LONG",
        "description": "DXY relief plus rising risk premium; checks if VIX adds incremental timing to DXY relief.",
        "conditions": [
            ["dxy_ret_60d", "<=", "q35"],
            ["vix_change_20d", ">=", "q55"],
            ["gold_ret_20d", ">=", "q45"],
        ],
    },
    {
        "rule_id": "S112_07_VOL_SHOCK_AFTER_GOLD_PULLBACK_REALYIELD_CAPPED_H120",
        "family": "PULLBACK_VOL_REVERSAL",
        "direction": "LONG",
        "description": "Gold pullback into volatility shock, but real-yield pressure is capped.",
        "conditions": [
            ["vix_change_20d", ">=", "q70"],
            ["gold_ret_20d", "<=", "q45"],
            ["real_yield_change_20d", "<=", "q55"],
        ],
    },
    {
        "rule_id": "S112_08_LONG_TREND_RISK_PREMIUM_NOT_EXTREME_H120",
        "family": "TREND_VOL_MODERATION",
        "direction": "LONG",
        "description": "Gold trend positive while volatility is elevated but not extreme; tests a moderation filter.",
        "conditions": [
            ["gold_sma20_over_50", ">=", "q55"],
            ["gold_sma50_over_200", ">=", "q50"],
            ["vix_change_20d", ">=", "q45"],
            ["vix_change_20d", "<=", "q80"],
        ],
    },
]

FEATURE_ALIASES = {
    "date": ["date_utc", "utc_time", "timestamp", "time", "date"],
    "gold_close": ["gold_close", "close", "xauusd_close", "xau_close"],
    "gold_ret_20d": ["gold_ret_20d", "xau_ret_20d"],
    "gold_ret_60d": ["gold_ret_60d", "xau_ret_60d"],
    "gold_sma20_over_50": ["gold_sma20_over_50", "xau_sma20_over_50"],
    "gold_sma50_over_200": ["gold_sma50_over_200", "xau_sma50_over_200"],
    "dxy_ret_20d": ["dxy_ret_20d", "dxy_change_20d"],
    "dxy_ret_60d": ["dxy_ret_60d", "dxy_change_60d"],
    "dxy_ret_120d": ["dxy_ret_120d", "dxy_change_120d"],
    "dxy_sma20_over_50": ["dxy_sma20_over_50"],
    "real_yield_change_20d": ["real_yield_change_20d", "real_yield_ret_20d", "us10y_real_change_20d"],
    "real_yield_change_60d": ["real_yield_change_60d", "real_yield_ret_60d", "us10y_real_change_60d"],
    "real_yield_change_120d": ["real_yield_change_120d", "real_yield_ret_120d", "us10y_real_change_120d"],
    "vix_change_20d": ["vix_change_20d", "vix_ret_20d", "vix_chg_20d"],
    "vix_ret_20d": ["vix_ret_20d", "vix_change_20d", "vix_chg_20d"],
    "central_bank_demand_tonnes_3m": ["central_bank_demand_tonnes_3m", "cb_3m", "central_bank_3m"],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def write_rows(path: Path, rows: Sequence[Dict[str, Any]], fieldnames: Optional[Sequence[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys: List[str] = []
        for r in rows:
            for k in r.keys():
                if k not in keys:
                    keys.append(k)
        fieldnames = keys
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames))
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})


def pick_col(df: pd.DataFrame, logical: str) -> Optional[str]:
    aliases = FEATURE_ALIASES.get(logical, [logical])
    lower_map = {str(c).lower(): c for c in df.columns}
    for a in aliases:
        if a in df.columns:
            return a
        if a.lower() in lower_map:
            return lower_map[a.lower()]
    return None


def resolve_columns(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    keys = sorted(set(FEATURE_ALIASES.keys()) - {"date"})
    out = {k: pick_col(df, k) for k in keys}
    out["date"] = pick_col(df, "date")
    return out


def numeric_series(df: pd.DataFrame, col: Optional[str]) -> pd.Series:
    if col is None or col not in df.columns:
        return pd.Series([math.nan] * len(df), index=df.index, dtype="float64")
    return pd.to_numeric(df[col], errors="coerce")


def load_macro(path: Path) -> Tuple[pd.DataFrame, Dict[str, Optional[str]]]:
    if not path.exists():
        raise FileNotFoundError(f"macro dataset not found: {path}")
    df = pd.read_csv(path)
    cols = resolve_columns(df)
    if cols.get("date") is None:
        raise ValueError("No usable date column found in macro dataset")
    if cols.get("gold_close") is None:
        raise ValueError("No usable gold close column found in macro dataset")
    df["_date"] = pd.to_datetime(df[cols["date"]], errors="coerce", utc=True)
    df = df.dropna(subset=["_date"]).sort_values("_date").reset_index(drop=True)
    for logical, col in cols.items():
        if logical == "date":
            continue
        df[f"_{logical}"] = numeric_series(df, col)
    if "_abs_vix_change_20d" not in df.columns:
        df["_abs_vix_change_20d"] = df["_vix_change_20d"].abs()
    return df, cols


def add_outcomes(df: pd.DataFrame, horizon: int, cost_bps: float) -> pd.DataFrame:
    out = df.copy()
    close = out["_gold_close"].astype(float)
    raw = (close.shift(-horizon) / close - 1.0) * 10000.0
    out["_fwd_raw_bps"] = raw
    out["_fwd_net_bps"] = raw - float(cost_bps)
    out["_outcome_valid"] = out["_fwd_net_bps"].notna()
    out["_year"] = out["_date"].dt.year
    return out


def split_segments(df: pd.DataFrame, selection_frac: float, validation_frac: float) -> Dict[str, pd.DataFrame]:
    n = len(df)
    if n < 50:
        raise ValueError(f"Not enough rows for segmented discovery: {n}")
    selection_end = max(1, int(n * selection_frac))
    validation_end = max(selection_end + 1, int(n * (selection_frac + validation_frac)))
    validation_end = min(validation_end, n - 1)
    return {
        "selection": df.iloc[:selection_end].copy(),
        "validation": df.iloc[selection_end:validation_end].copy(),
        "tail_forward_proxy": df.iloc[validation_end:].copy(),
    }


def qname(q: float) -> str:
    return f"q{int(round(q * 100))}"


def selection_thresholds(selection: pd.DataFrame, features: Iterable[str]) -> Dict[str, Dict[str, Optional[float]]]:
    qs = [0.20, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
    thresholds: Dict[str, Dict[str, Optional[float]]] = {}
    for feature in features:
        source_col = f"_{feature}"
        if feature == "abs_vix_change_20d":
            source_col = "_abs_vix_change_20d"
        if source_col not in selection.columns:
            thresholds[feature] = {qname(q): None for q in qs}
            continue
        s = pd.to_numeric(selection[source_col], errors="coerce").dropna()
        if s.empty:
            thresholds[feature] = {qname(q): None for q in qs}
            continue
        thresholds[feature] = {qname(q): float(s.quantile(q)) for q in qs}
    return thresholds


def required_features() -> List[str]:
    feats: List[str] = []
    for spec in CANDIDATE_FAMILIES:
        for c in spec["conditions"]:
            if c[0] not in feats:
                feats.append(c[0])
    for f in [
        "gold_ret_20d", "gold_ret_60d", "gold_sma20_over_50", "gold_sma50_over_200",
        "dxy_ret_20d", "dxy_ret_60d", "dxy_ret_120d", "real_yield_change_20d",
        "real_yield_change_60d", "real_yield_change_120d", "vix_change_20d", "vix_ret_20d",
        "central_bank_demand_tonnes_3m", "abs_vix_change_20d",
    ]:
        if f not in feats:
            feats.append(f)
    return feats


def condition_mask(df: pd.DataFrame, cond: Sequence[str], thresholds: Dict[str, Dict[str, Optional[float]]]) -> Tuple[pd.Series, Optional[str]]:
    feature, op, value_key = cond
    col = f"_{feature}"
    if feature == "abs_vix_change_20d":
        col = "_abs_vix_change_20d"
    if col not in df.columns:
        return pd.Series([False] * len(df), index=df.index), f"missing_feature:{feature}"
    val = thresholds.get(feature, {}).get(value_key)
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return pd.Series([False] * len(df), index=df.index), f"missing_threshold:{feature}:{value_key}"
    s = pd.to_numeric(df[col], errors="coerce")
    if op == ">=":
        return s >= val, None
    if op == "<=":
        return s <= val, None
    if op == ">":
        return s > val, None
    if op == "<":
        return s < val, None
    raise ValueError(f"Unsupported operator: {op}")


def candidate_mask(df: pd.DataFrame, spec: Dict[str, Any], thresholds: Dict[str, Dict[str, Optional[float]]]) -> Tuple[pd.Series, List[str]]:
    mask = pd.Series([True] * len(df), index=df.index)
    issues: List[str] = []
    for cond in spec["conditions"]:
        cm, issue = condition_mask(df, cond, thresholds)
        mask &= cm.fillna(False)
        if issue:
            issues.append(issue)
    return mask & df["_outcome_valid"].fillna(False), issues


def summarize_events(df: pd.DataFrame, mask: pd.Series, label: str) -> Dict[str, Any]:
    subset = df.loc[mask].copy()
    n = int(len(subset))
    if n == 0:
        return {
            f"{label}_events": 0,
            f"{label}_mean_net_bps": None,
            f"{label}_median_net_bps": None,
            f"{label}_win_rate": None,
            f"{label}_min_net_bps": None,
            f"{label}_max_net_bps": None,
            f"{label}_first_date": None,
            f"{label}_last_date": None,
            f"{label}_year_concentration": None,
        }
    ycounts = subset["_year"].value_counts(dropna=True)
    return {
        f"{label}_events": n,
        f"{label}_mean_net_bps": round(float(subset["_fwd_net_bps"].mean()), 4),
        f"{label}_median_net_bps": round(float(subset["_fwd_net_bps"].median()), 4),
        f"{label}_win_rate": round(float((subset["_fwd_net_bps"] > 0).mean()), 4),
        f"{label}_min_net_bps": round(float(subset["_fwd_net_bps"].min()), 4),
        f"{label}_max_net_bps": round(float(subset["_fwd_net_bps"].max()), 4),
        f"{label}_first_date": subset["_date"].min().date().isoformat(),
        f"{label}_last_date": subset["_date"].max().date().isoformat(),
        f"{label}_year_concentration": round(float(ycounts.max() / n), 4) if n else None,
    }


def observer_masks(df: pd.DataFrame, thresholds: Dict[str, Dict[str, Optional[float]]]) -> Dict[str, pd.Series]:
    def cond(feature: str, op: str, key: str) -> pd.Series:
        return condition_mask(df, [feature, op, key], thresholds)[0]
    masks = {
        "K06_RESILIENT_GOLD_VS_DXY_H120": cond("gold_ret_60d", ">=", "q55") & cond("dxy_ret_60d", ">=", "q55"),
        "K03_SAFE_HAVEN_REALYIELD_H120": cond("real_yield_change_60d", ">=", "q55") & cond("gold_ret_20d", ">=", "q50"),
        "K07_DXY_TREND_RELIEF_GOLD_TREND_H120": cond("dxy_ret_120d", "<=", "q40") & cond("gold_sma50_over_200", ">=", "q50"),
        "S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120": cond("real_yield_change_120d", "<=", "q40") & cond("gold_sma50_over_200", "<=", "q55"),
        "S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120": cond("dxy_ret_120d", "<=", "q40") & cond("gold_sma50_over_200", "<=", "q55"),
        "C96_07_CB_SUPPORT_NOT_CROWDED_H120": cond("central_bank_demand_tonnes_3m", ">=", "q60"),
        "S105_03_COT_DECROWDING_CB_SUPPORT_RY_RELIEF_H120": cond("central_bank_demand_tonnes_3m", ">=", "q50") & cond("real_yield_change_60d", "<=", "q45") & cond("dxy_ret_60d", "<=", "q45"),
    }
    return {k: (v & df["_outcome_valid"].fillna(False)).fillna(False) for k, v in masks.items()}


def overlap_stats(candidate: pd.Series, observers: Dict[str, pd.Series]) -> Tuple[float, str, List[Dict[str, Any]]]:
    denom = int(candidate.sum())
    rows = []
    if denom == 0:
        return 0.0, "", rows
    max_ratio = 0.0
    max_rule = ""
    for rule, omask in observers.items():
        inter = int((candidate & omask).sum())
        obs_n = int(omask.sum())
        ratio = inter / denom if denom else 0.0
        rows.append({
            "observer_rule_id": rule,
            "candidate_events": denom,
            "observer_events": obs_n,
            "intersection_events": inter,
            "candidate_overlap_ratio": round(ratio, 4),
        })
        if ratio > max_ratio:
            max_ratio = ratio
            max_rule = rule
    return max_ratio, max_rule, rows


def evaluate_candidates(df: pd.DataFrame, segments: Dict[str, pd.DataFrame], thresholds: Dict[str, Dict[str, Optional[float]]], cfg: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    metrics: List[Dict[str, Any]] = []
    generated: List[Dict[str, Any]] = []
    selected: List[Dict[str, Any]] = []
    overlap_rows: List[Dict[str, Any]] = []
    full_observers = observer_masks(df, thresholds)

    for spec in CANDIDATE_FAMILIES:
        full_mask, issues = candidate_mask(df, spec, thresholds)
        generated.append({
            "rule_id": spec["rule_id"],
            "family": spec["family"],
            "direction": spec["direction"],
            "description": spec["description"],
            "conditions_json": json.dumps(spec["conditions"]),
            "issues": ";".join(sorted(set(issues))),
            "full_events": int(full_mask.sum()),
        })
        row: Dict[str, Any] = {
            "stage": STAGE,
            "rule_id": spec["rule_id"],
            "family": spec["family"],
            "direction": spec["direction"],
            "description": spec["description"],
            "conditions_json": json.dumps(spec["conditions"]),
            "issues": ";".join(sorted(set(issues))),
            "full_events": int(full_mask.sum()),
        }
        for seg_name, seg_df in segments.items():
            seg_mask, _ = candidate_mask(seg_df, spec, thresholds)
            row.update(summarize_events(seg_df, seg_mask, seg_name))
        max_overlap, max_rule, per_rule = overlap_stats(full_mask, full_observers)
        row["max_observer_overlap_ratio"] = round(max_overlap, 4)
        row["max_overlap_rule"] = max_rule
        for ov in per_rule:
            ov.update({"rule_id": spec["rule_id"], "family": spec["family"]})
            overlap_rows.append(ov)

        row["gate_decision"] = gate_decision(row, cfg)
        row["gate_reasons"] = gate_reasons(row, cfg)
        metrics.append(row)
        if row["gate_decision"] == "PASS_STAGE113_REVIEW_NO_ORDER":
            selected.append(row)

    selected = sorted(
        selected,
        key=lambda r: (
            r.get("tail_forward_proxy_mean_net_bps") or -999999,
            r.get("validation_mean_net_bps") or -999999,
            -(r.get("max_observer_overlap_ratio") or 999999),
        ),
        reverse=True,
    )[: int(cfg.get("max_selected", 5))]
    return generated, metrics, selected, overlap_rows


def safe_float(v: Any, default: float = -999999.0) -> float:
    if v is None or v == "":
        return default
    try:
        if math.isnan(float(v)):
            return default
        return float(v)
    except Exception:
        return default


def gate_reasons(row: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    reasons: List[str] = []
    if int(row.get("selection_events") or 0) < int(cfg["min_selection_events"]):
        reasons.append("LOW_SELECTION_EVENTS")
    if int(row.get("validation_events") or 0) < int(cfg["min_validation_events"]):
        reasons.append("LOW_VALIDATION_EVENTS")
    if int(row.get("tail_forward_proxy_events") or 0) < int(cfg["min_tail_forward_events"]):
        reasons.append("LOW_TAIL_FORWARD_EVENTS")
    if safe_float(row.get("selection_mean_net_bps")) < float(cfg["min_selection_mean_net_bps"]):
        reasons.append("WEAK_SELECTION_MEAN")
    if safe_float(row.get("validation_mean_net_bps")) < float(cfg["min_validation_mean_net_bps"]):
        reasons.append("WEAK_VALIDATION_MEAN")
    if safe_float(row.get("tail_forward_proxy_mean_net_bps")) < float(cfg["min_tail_forward_mean_net_bps"]):
        reasons.append("WEAK_TAIL_FORWARD_MEAN")
    if safe_float(row.get("tail_forward_proxy_win_rate"), 0.0) < float(cfg["min_tail_forward_win_rate"]):
        reasons.append("WEAK_TAIL_FORWARD_WIN_RATE")
    if safe_float(row.get("max_observer_overlap_ratio"), 1.0) > float(cfg["max_observer_overlap_ratio"]):
        reasons.append("HIGH_OBSERVER_OVERLAP")
    yc = max(
        safe_float(row.get("selection_year_concentration"), 0.0),
        safe_float(row.get("validation_year_concentration"), 0.0),
        safe_float(row.get("tail_forward_proxy_year_concentration"), 0.0),
    )
    if yc > float(cfg["max_year_concentration"]):
        reasons.append("YEAR_CONCENTRATED")
    if row.get("issues"):
        reasons.append("FEATURE_OR_THRESHOLD_ISSUES")
    return ";".join(reasons) if reasons else "PASS"


def gate_decision(row: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    return "PASS_STAGE113_REVIEW_NO_ORDER" if gate_reasons(row, cfg) == "PASS" else "KILL_OR_REVIEW_ONLY"


def write_split_files(outdir: Path, segments: Dict[str, pd.DataFrame], thresholds: Dict[str, Dict[str, Optional[float]]], cfg: Dict[str, Any]) -> Dict[str, str]:
    split_dir = outdir / "splits"
    split_dir.mkdir(parents=True, exist_ok=True)
    outputs: Dict[str, str] = {}
    keep_cols = [c for c in ["_date", "_gold_close", "_fwd_raw_bps", "_fwd_net_bps", "_year"] if c in next(iter(segments.values())).columns]
    for name, seg in segments.items():
        path = split_dir / f"stage112_{name}_rows.csv"
        seg[keep_cols].to_csv(path, index=False)
        outputs[f"split_{name}"] = str(path)
    threshold_rows = []
    for feat, qs in thresholds.items():
        r = {"feature": feat}
        r.update(qs)
        threshold_rows.append(r)
    threshold_path = split_dir / "stage112_selection_quantile_thresholds.csv"
    write_rows(threshold_path, threshold_rows)
    outputs["thresholds"] = str(threshold_path)
    manifest = {
        "stage": STAGE,
        "generated_utc": utc_now(),
        "policy": "Historical segmentation persisted for auditability; thresholds are learned from selection only.",
        "selection_frac": cfg["selection_frac"],
        "validation_frac": cfg["validation_frac"],
        "tail_forward_frac": cfg["tail_forward_frac"],
        "segments": {
            name: {
                "rows": int(len(seg)),
                "min_date": seg["_date"].min().date().isoformat() if len(seg) else None,
                "max_date": seg["_date"].max().date().isoformat() if len(seg) else None,
            }
            for name, seg in segments.items()
        },
        "outputs": outputs,
    }
    manifest_path = split_dir / "stage112_split_manifest.json"
    write_json(manifest_path, manifest)
    outputs["split_manifest"] = str(manifest_path)
    return outputs


def recent_snapshot(df: pd.DataFrame, thresholds: Dict[str, Dict[str, Optional[float]]]) -> List[Dict[str, Any]]:
    if df.empty:
        return []
    last = df.tail(1).copy()
    rows = []
    for spec in CANDIDATE_FAMILIES:
        mask, issues = candidate_mask(last, spec, thresholds)
        rows.append({
            "asof_date": last["_date"].iloc[0].date().isoformat(),
            "rule_id": spec["rule_id"],
            "family": spec["family"],
            "signal_now": int(bool(mask.iloc[0])) if len(mask) else 0,
            "issues": ";".join(sorted(set(issues))),
            "note": "diagnostic_only_no_mt5_csv_from_stage112",
        })
    return rows


def make_report(summary: Dict[str, Any], selected: List[Dict[str, Any]]) -> str:
    lines = [
        "# Stage112 Vol / Risk-Premium Rotation Frontier Discovery",
        "",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- classification: `{summary['classification']}`",
        "- order status: `NO_ORDER_AUTHORIZATION_FROM_STAGE112`",
        "",
        "## Thesis",
        "",
        summary["selected_thesis"],
        "",
        "Stage112 is discovery-only. It does not modify EA code, does not write an MT5 bridge CSV, and does not authorize paper/live orders.",
        "",
        "## Data",
        "",
        f"- macro dataset: `{summary['macro_dataset']['path']}`",
        f"- macro rows: `{summary['macro_dataset']['rows']}`",
        f"- date range: `{summary['macro_dataset']['min_date']}` -> `{summary['macro_dataset']['max_date']}`",
        f"- valid outcome rows: `{summary['data_join']['outcome_valid_rows']}`",
        "",
        "## Segmentation",
        "",
    ]
    for k, v in summary["segments"].items():
        lines.append(f"- {k}: `{v['rows']}` rows, `{v['min_date']}` -> `{v['max_date']}`")
    lines += [
        "",
        "Quantile thresholds are learned only on the selection segment and then applied unchanged to validation and tail-forward proxy.",
        "",
        "## Result",
        "",
        f"- generated candidate count: `{summary['generated_candidate_count']}`",
        f"- pass gate count: `{summary['pass_gate_count']}`",
    ]
    if selected:
        lines += ["", "## Selected for Stage113 review", ""]
        for r in selected:
            lines.append(f"- `{r['rule_id']}`: tail mean `{r.get('tail_forward_proxy_mean_net_bps')}` bps, validation mean `{r.get('validation_mean_net_bps')}` bps, overlap `{r.get('max_observer_overlap_ratio')}`")
    else:
        lines += ["", "No incremental candidate passed the Stage112 segmented gate."]
    lines += ["", "## Hard blocks", ""]
    for b in HARD_BLOCKS:
        lines.append(f"- `{b}`")
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=STAGE)
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--config", default="configs/stage112_vol_risk_premium_rotation_frontier_discovery.json")
    parser.add_argument("--out", default="reports/stage112_vol_risk_premium_rotation_frontier_discovery")
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    cfg_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    cfg = DEFAULT_CONFIG.copy()
    cfg.update(read_json(cfg_path))
    outdir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    macro_path = (root / cfg["macro_dataset"]).resolve() if not Path(cfg["macro_dataset"]).is_absolute() else Path(cfg["macro_dataset"])
    df, cols = load_macro(macro_path)
    df = add_outcomes(df, int(cfg["horizon_trading_days"]), float(cfg["cost_bps"]))
    segments = split_segments(df, float(cfg["selection_frac"]), float(cfg["validation_frac"]))
    thresholds = selection_thresholds(segments["selection"], required_features())
    split_outputs = write_split_files(outdir, segments, thresholds, cfg) if cfg.get("write_split_files", True) else {}

    generated, metrics, selected, overlap_rows = evaluate_candidates(df, segments, thresholds, cfg)
    recent = recent_snapshot(df, thresholds)

    generated_path = outdir / "stage112_generated_candidates.csv"
    metrics_path = outdir / "stage112_candidate_metrics.csv"
    selected_path = outdir / "stage112_selected_for_stage113.csv"
    review_path = outdir / "stage112_review_queue.csv"
    overlap_path = outdir / "stage112_overlap_matrix.csv"
    recent_path = outdir / "stage112_recent_signal_snapshot.csv"
    thresholds_path = outdir / "stage112_thresholds_flat.csv"

    write_rows(generated_path, generated)
    write_rows(metrics_path, metrics)
    write_rows(selected_path, selected, fieldnames=list(metrics[0].keys()) if metrics else None)
    review = [r for r in metrics if r.get("gate_decision") != "PASS_STAGE113_REVIEW_NO_ORDER"]
    write_rows(review_path, review, fieldnames=list(metrics[0].keys()) if metrics else None)
    write_rows(overlap_path, overlap_rows)
    write_rows(recent_path, recent)
    threshold_rows = []
    for feat, qs in thresholds.items():
        r = {"feature": feat}
        r.update(qs)
        threshold_rows.append(r)
    write_rows(thresholds_path, threshold_rows)

    decision = DECISION_PASS if selected else DECISION_NO_PASS
    classification = CLASS_PASS if selected else CLASS_NO_PASS
    status = "STAGE112_COMPLETE_NO_PROMOTION"

    summary = {
        "stage": STAGE,
        "root": str(root),
        "generated_utc": utc_now(),
        "status": status,
        "decision": decision,
        "classification": classification,
        "disposition": "DISCOVERY_ONLY_NO_ORDER",
        "selected_thesis": "Volatility / risk-premium rotation frontier: test whether VIX/risk-premium states add incremental H120 timing beyond the current 7-rule macro/COT observer.",
        "why_this_frontier": [
            "Stage111 failed cleanly because the available dataset does not include ETF-flow and COT numeric features required by that thesis.",
            "The current macro dataset does include VIX/risk-premium features, DXY, real-yield, gold trend, and central-bank 3m demand.",
            "The current observer is heavily DXY/real-yield/CB/COT oriented; VIX interaction is a plausible non-duplicate next frontier.",
            "Historical segmentation and tail-forward proxy remain the primary discovery path during the weekend market closure.",
        ],
        "macro_dataset": {
            "path": str(macro_path),
            "exists": macro_path.exists(),
            "rows": int(len(df)),
            "date_col": cols.get("date"),
            "price_col": cols.get("gold_close"),
            "min_date": df["_date"].min().date().isoformat() if len(df) else None,
            "max_date": df["_date"].max().date().isoformat() if len(df) else None,
            "sha256": sha256_file(macro_path),
        },
        "data_join": {
            "rows": int(len(df)),
            "outcome_valid_rows": int(df["_outcome_valid"].sum()),
            "feature_map": {k: v for k, v in cols.items() if k != "date"},
        },
        "segments": {
            name: {
                "rows": int(len(seg)),
                "min_date": seg["_date"].min().date().isoformat() if len(seg) else None,
                "max_date": seg["_date"].max().date().isoformat() if len(seg) else None,
            }
            for name, seg in segments.items()
        },
        "horizon_trading_days": int(cfg["horizon_trading_days"]),
        "cost_bps": float(cfg["cost_bps"]),
        "active_observer_rules_reference": ACTIVE_OBSERVER_RULES,
        "generated_candidate_count": len(generated),
        "pass_gate_count": len(selected),
        "selected_rule_ids": [r["rule_id"] for r in selected],
        "hard_blocks": HARD_BLOCKS,
        "split_outputs": split_outputs,
        "outputs": {
            "summary_json": str(outdir / "stage112_vol_risk_premium_rotation_frontier_discovery_summary.json"),
            "report_md": str(outdir / "stage112_vol_risk_premium_rotation_frontier_discovery_report.md"),
            "generated_candidates": str(generated_path),
            "candidate_metrics": str(metrics_path),
            "selected_for_stage113": str(selected_path),
            "review_queue": str(review_path),
            "overlap_matrix": str(overlap_path),
            "recent_signal_snapshot": str(recent_path),
            "thresholds_flat": str(thresholds_path),
        },
    }

    summary_path = outdir / "stage112_vol_risk_premium_rotation_frontier_discovery_summary.json"
    report_path = outdir / "stage112_vol_risk_premium_rotation_frontier_discovery_report.md"
    write_json(summary_path, summary)
    report_path.write_text(make_report(summary, selected), encoding="utf-8")

    print(json.dumps({
        "stage": STAGE,
        "status": status,
        "decision": decision,
        "classification": classification,
        "generated_candidate_count": len(generated),
        "pass_gate_count": len(selected),
        "selected_rule_ids": [r["rule_id"] for r in selected],
        "summary_json": str(summary_path),
        "report_md": str(report_path),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
