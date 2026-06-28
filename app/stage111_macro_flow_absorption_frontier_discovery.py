#!/usr/bin/env python3
"""
Stage111 - Macro/flow absorption frontier discovery.

Observer/order policy:
- Discovery only.
- No broker connection.
- No MT5 order authorization.
- No paper/live order path.

Purpose:
Search a non-duplicative frontier after the Stage108/109 7-rule observer:
ETF / central-bank / COT flow absorption after gold pullback or macro headwind.
The script uses historical segmentation and rolling historical-as-of checks.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import operator
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

STAGE = "Stage111_MACRO_FLOW_ABSORPTION_FRONTIER_DISCOVERY"
STATUS_COMPLETE = "STAGE111_COMPLETE_NO_PROMOTION"
DECISION_PREFIX = "STAGE111_"

DEFAULT_ACTIVE_RULES: List[Dict[str, Any]] = [
    {
        "rule_id": "K06_RESILIENT_GOLD_VS_DXY_H120",
        "label": "K06_RESILIENT_GOLD_VS_DXY",
        "conditions": [
            {"column": "gold_sma20_over_50", "op": ">", "threshold": 0.0},
            {"column": "dxy_ret_20d", "op": ">", "threshold": 0.0},
            {"column": "real_yield_change_20d", "op": "<", "threshold": 0.0},
        ],
    },
    {
        "rule_id": "K03_SAFE_HAVEN_REALYIELD_H120",
        "label": "K03_WGC_RISK_UNCERTAINTY_SAFE_HAVEN",
        "conditions": [
            {"column": "vix_change_20d", "op": ">", "threshold": 0.0},
            {"column": "real_yield_change_20d", "op": "<", "threshold": 0.0},
        ],
    },
    {
        "rule_id": "K07_DXY_TREND_RELIEF_GOLD_TREND_H120",
        "label": "K07_DXY_TREND_RELIEF_GOLD_TREND",
        "conditions": [
            {"column": "gold_sma20_over_50", "op": ">", "threshold": 0.0},
            {"column": "dxy_sma20_over_50", "op": "<", "threshold": 0.0},
        ],
    },
    {
        "rule_id": "S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120",
        "label": "REALYIELD_120D_DOWN_GOLD_NOT_TRENDING",
        "conditions": [
            {"column": "real_yield_change_120d", "op": "<", "threshold": 0.0},
            {"column": "gold_sma20_over_50", "op": "<", "threshold": 0.0},
        ],
    },
    {
        "rule_id": "S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120",
        "label": "DXY_120D_DOWN_GOLD_NOT_TRENDING",
        "conditions": [
            {"column": "dxy_ret_120d", "op": "<", "threshold": 0.0},
            {"column": "gold_sma20_over_50", "op": "<", "threshold": 0.0},
        ],
    },
    {
        "rule_id": "C96_07_CB_SUPPORT_NOT_CROWDED_H120",
        "label": "CB_SUPPORT_NOT_CROWDED",
        "conditions": [
            {"column": "cot_mm_net_z", "op": "<", "threshold": 1.0},
            {"column": "central_bank_demand_tonnes_3m", "op": ">", "threshold": 0.0},
            {"column": "gold_ret_20d", "op": "<", "threshold": 0.0},
        ],
    },
    {
        "rule_id": "S105_03_COT_DECROWDING_CB_SUPPORT_RY_RELIEF_H120",
        "label": "COT_DECROWDING_CB_SUPPORT_RY_RELIEF",
        "conditions": [
            {"column": "cot_mm_net_z_change_4w", "op": "<", "threshold": 0.0},
            {"column": "central_bank_demand_tonnes_3m", "op": ">", "threshold": 0.0},
            {"column": "real_yield_change_20d", "op": "<", "threshold": 0.0},
        ],
    },
]

OPS = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
}

@dataclass
class Condition:
    column: str
    op: str
    threshold: float

@dataclass
class Candidate:
    rule_id: str
    label: str
    family: str
    thesis: str
    horizon_trading_days: int
    conditions: List[Condition]

@dataclass
class CandidateMetrics:
    rule_id: str
    label: str
    family: str
    thesis: str
    horizon_trading_days: int
    n_total: int
    mean_net_bps: float
    median_net_bps: float
    win_rate: float
    n_train: int
    mean_train_bps: float
    n_validation: int
    mean_validation_bps: float
    n_tail_forward: int
    mean_tail_forward_bps: float
    tail_forward_win_rate: float
    positive_segments: int
    segment_count: int
    max_year_event_share: float
    union_overlap_share: float
    max_rule_overlap_share: float
    incremental_event_count: int
    asof_positive_rate: float
    asof_tests: int
    pass_gate: bool
    reject_reasons: str


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, default=str)
        f.write("\n")


def write_csv(path: Path, rows: Sequence[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys: List[str] = []
        for r in rows:
            for k in r.keys():
                if k not in keys:
                    keys.append(k)
        fieldnames = keys
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage111_macro_flow_absorption_frontier_discovery.json")
    ap.add_argument("--out", default="reports/stage111_macro_flow_absorption_frontier_discovery")
    ap.add_argument("--top", type=int, default=None, help="Override number of selected candidates to export.")
    return ap.parse_args()


def load_config(root: Path, config_arg: str) -> Dict[str, Any]:
    cfg_path = Path(config_arg)
    if not cfg_path.is_absolute():
        cfg_path = root / cfg_path
    if cfg_path.exists():
        cfg = read_json(cfg_path)
    else:
        cfg = {}
    cfg.setdefault("macro_dataset", "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv")
    cfg.setdefault("cot_dataset", "data/external_frontiers/cot_positioning_normalized.csv")
    cfg.setdefault("date_col", "date_utc")
    cfg.setdefault("price_col", "gold_close")
    cfg.setdefault("horizon_trading_days", 120)
    cfg.setdefault("cost_bps", 20.0)
    cfg.setdefault("top_n", 12)
    cfg.setdefault("segments", {
        "train": ["2011-01-01", "2018-12-31"],
        "validation": ["2019-01-01", "2022-12-31"],
        "tail_forward": ["2023-01-01", "2099-12-31"],
    })
    cfg.setdefault("asof_years", [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024])
    cfg.setdefault("gate", {
        "min_total_events": 25,
        "min_train_events": 6,
        "min_validation_events": 5,
        "min_tail_forward_events": 4,
        "min_mean_net_bps": 75.0,
        "min_validation_mean_bps": 0.0,
        "min_tail_forward_mean_bps": 0.0,
        "min_tail_forward_win_rate": 0.48,
        "min_positive_segments": 2,
        "max_year_event_share": 0.55,
        "max_union_overlap_share": 0.65,
        "max_rule_overlap_share": 0.75,
        "min_incremental_events": 5,
        "min_asof_positive_rate": 0.45,
    })
    cfg.setdefault("active_rules", DEFAULT_ACTIVE_RULES)
    return cfg


def resolve_path(root: Path, p: str) -> Path:
    pp = Path(p)
    return pp if pp.is_absolute() else root / pp


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def detect_date_col(df: pd.DataFrame, preferred: str) -> str:
    if preferred in df.columns:
        return preferred
    candidates = ["date", "date_utc", "time", "time_utc", "utc_time", "datetime", "timestamp"]
    for c in candidates:
        if c in df.columns:
            return c
    for c in df.columns:
        if "date" in c.lower() or "time" in c.lower():
            return c
    raise ValueError(f"No date column found. columns={list(df.columns)[:30]}")


def detect_price_col(df: pd.DataFrame, preferred: str) -> str:
    if preferred in df.columns:
        return preferred
    candidates = ["gold_close", "close", "xauusd_close", "gold", "price"]
    for c in candidates:
        if c in df.columns:
            return c
    close_like = [c for c in df.columns if c.lower().endswith("close") or "close" in c.lower()]
    if close_like:
        return close_like[0]
    raise ValueError(f"No price column found. columns={list(df.columns)[:30]}")


def safe_numeric(df: pd.DataFrame, exclude: Iterable[str]) -> pd.DataFrame:
    df = df.copy()
    exclude_set = set(exclude)
    for c in df.columns:
        if c in exclude_set:
            continue
        original_non_null = int(df[c].notna().sum())
        converted = pd.to_numeric(df[c], errors="coerce")
        converted_non_null = int(converted.notna().sum())
        if original_non_null == 0 or converted_non_null >= max(1, int(original_non_null * 0.70)):
            df[c] = converted
    return df


def load_macro_dataset(root: Path, cfg: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    path = resolve_path(root, cfg["macro_dataset"])
    if not path.exists():
        raise FileNotFoundError(f"Macro dataset not found: {path}")
    df = pd.read_csv(path)
    df = normalize_columns(df)
    date_col = detect_date_col(df, cfg.get("date_col", "date_utc"))
    price_col = detect_price_col(df, cfg.get("price_col", "gold_close"))
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce", utc=True).dt.tz_localize(None)
    df = df.dropna(subset=[date_col]).sort_values(date_col).reset_index(drop=True)
    df = safe_numeric(df, exclude=[date_col])
    if price_col != "gold_close" and "gold_close" not in df.columns:
        df["gold_close"] = pd.to_numeric(df[price_col], errors="coerce")
        price_col = "gold_close"
    meta = {
        "path": str(path),
        "exists": True,
        "rows": int(len(df)),
        "date_col": date_col,
        "price_col": price_col,
        "min_date": df[date_col].min().date().isoformat() if len(df) else None,
        "max_date": df[date_col].max().date().isoformat() if len(df) else None,
        "sha256": sha256_file(path),
    }
    return df, meta


def load_and_join_cot(root: Path, cfg: Dict[str, Any], macro: pd.DataFrame, macro_date_col: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    path = resolve_path(root, cfg.get("cot_dataset", ""))
    meta: Dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        meta["joined"] = False
        return macro, meta
    cot = pd.read_csv(path)
    cot = normalize_columns(cot)
    date_col = "available_after_utc" if "available_after_utc" in cot.columns else None
    if date_col is None:
        for cand in ["available_after", "report_date_utc", "date_utc", "date"]:
            if cand in cot.columns:
                date_col = cand
                break
    if date_col is None:
        meta["joined"] = False
        meta["error"] = "no usable COT date column"
        return macro, meta
    cot[date_col] = pd.to_datetime(cot[date_col], errors="coerce", utc=True).dt.tz_localize(None)
    cot = cot.dropna(subset=[date_col]).sort_values(date_col).reset_index(drop=True)
    cot = safe_numeric(cot, exclude=[date_col])
    # Avoid duplicate columns already in macro; keep COT version only when macro does not have it.
    keep_cols = [date_col]
    for c in cot.columns:
        if c == date_col:
            continue
        if c not in macro.columns:
            keep_cols.append(c)
    cot = cot[keep_cols]
    left = macro.sort_values(macro_date_col).reset_index(drop=True)
    joined = pd.merge_asof(left, cot, left_on=macro_date_col, right_on=date_col, direction="backward")
    if date_col in joined.columns and date_col != macro_date_col:
        joined = joined.drop(columns=[date_col])
    meta.update({
        "joined": True,
        "rows": int(len(cot)),
        "date_col": date_col,
        "joined_rows": int(len(joined)),
        "sha256": sha256_file(path),
    })
    return joined, meta


def add_missing_derived_features(df: pd.DataFrame, date_col: str, price_col: str) -> pd.DataFrame:
    df = df.copy()
    if "gold_close" not in df.columns:
        df["gold_close"] = pd.to_numeric(df[price_col], errors="coerce")
    for window in [20, 60, 120, 252]:
        col = f"gold_ret_{window}d"
        if col not in df.columns:
            df[col] = df["gold_close"].pct_change(window)
    if "gold_sma20_over_50" not in df.columns:
        df["gold_sma20_over_50"] = df["gold_close"].rolling(20).mean() / df["gold_close"].rolling(50).mean() - 1.0
    if "gold_sma50_over_200" not in df.columns:
        df["gold_sma50_over_200"] = df["gold_close"].rolling(50).mean() / df["gold_close"].rolling(200).mean() - 1.0
    for base in ["dxy", "real_yield", "vix"]:
        close_cols = [c for c in df.columns if c.lower() in [base, f"{base}_close", f"{base}_value"]]
        src = close_cols[0] if close_cols else None
        if src is not None:
            for window in [20, 60, 120]:
                col = f"{base}_ret_{window}d" if base != "real_yield" else f"{base}_change_{window}d"
                if col not in df.columns:
                    if base == "real_yield":
                        df[col] = df[src].diff(window)
                    else:
                        df[col] = df[src].pct_change(window)
            sma_col = f"{base}_sma20_over_50"
            if sma_col not in df.columns and base != "real_yield":
                df[sma_col] = df[src].rolling(20).mean() / df[src].rolling(50).mean() - 1.0
    if "vix_change_20d" not in df.columns:
        vix_cols = [c for c in df.columns if c.lower() in ["vix", "vix_close", "vix_value"]]
        if vix_cols:
            df["vix_change_20d"] = df[vix_cols[0]].diff(20)
    return df


def first_existing(columns: Iterable[str], patterns: Sequence[str]) -> Optional[str]:
    cols = list(columns)
    lower = {c.lower(): c for c in cols}
    for pat in patterns:
        if pat.lower() in lower:
            return lower[pat.lower()]
    for pat in patterns:
        rx = re.compile(pat, re.IGNORECASE)
        for c in cols:
            if rx.search(c):
                return c
    return None


def discover_feature_map(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    cols = df.columns
    return {
        "gold_ret_20d": first_existing(cols, ["gold_ret_20d"]),
        "gold_ret_60d": first_existing(cols, ["gold_ret_60d"]),
        "gold_sma20_over_50": first_existing(cols, ["gold_sma20_over_50"]),
        "gold_sma50_over_200": first_existing(cols, ["gold_sma50_over_200"]),
        "dxy_ret_20d": first_existing(cols, ["dxy_ret_20d", "dxy.*20.*ret"]),
        "dxy_ret_60d": first_existing(cols, ["dxy_ret_60d", "dxy.*60.*ret"]),
        "dxy_ret_120d": first_existing(cols, ["dxy_ret_120d", "dxy.*120.*ret"]),
        "dxy_sma20_over_50": first_existing(cols, ["dxy_sma20_over_50"]),
        "real_yield_change_20d": first_existing(cols, ["real_yield_change_20d", "real.*yield.*20.*change"]),
        "real_yield_change_60d": first_existing(cols, ["real_yield_change_60d", "real.*yield.*60.*change"]),
        "real_yield_change_120d": first_existing(cols, ["real_yield_change_120d", "real.*yield.*120.*change"]),
        "vix_change_20d": first_existing(cols, ["vix_change_20d", "vix.*20.*change"]),
        "vix_ret_20d": first_existing(cols, ["vix_ret_20d", "vix.*20.*ret"]),
        "cb_3m": first_existing(cols, ["central_bank_demand_tonnes_3m", "central.*bank.*3m", "cb.*3m"]),
        "cb_12m": first_existing(cols, ["central_bank_demand_tonnes_12m", "central.*bank.*12m", "cb.*12m"]),
        "etf_20d": first_existing(cols, ["gold_etf_flow_tonnes_20d", "etf_flow_tonnes_20d", "etf.*flow.*20", "etf.*change.*20", "gold_etf.*20"]),
        "etf_60d": first_existing(cols, ["gold_etf_flow_tonnes_60d", "etf_flow_tonnes_60d", "etf.*flow.*60", "etf.*change.*60", "gold_etf.*60"]),
        "cot_z": first_existing(cols, ["cot_mm_net_z", "money_manager_net_z", "mm_net_z"]),
        "cot_z_change_4w": first_existing(cols, ["cot_mm_net_z_change_4w", "cot.*z.*change.*4", "mm.*z.*change.*4"]),
        "cot_z_change_12w": first_existing(cols, ["cot_mm_net_z_change_12w", "cot.*z.*change.*12", "mm.*z.*change.*12"]),
    }


def cond(column: Optional[str], op: str, threshold: float) -> Optional[Condition]:
    if not column:
        return None
    return Condition(column=column, op=op, threshold=float(threshold))


def make_candidate(rule_id: str, label: str, family: str, thesis: str, horizon: int, conditions: Sequence[Optional[Condition]]) -> Optional[Candidate]:
    c = [x for x in conditions if x is not None]
    # Need at least three real conditions for a frontier rule, otherwise the test is too loose.
    if len(c) < 3:
        return None
    return Candidate(rule_id=rule_id, label=label, family=family, thesis=thesis, horizon_trading_days=horizon, conditions=c)


def generate_candidates(df: pd.DataFrame, horizon: int) -> Tuple[List[Candidate], Dict[str, Optional[str]]]:
    fm = discover_feature_map(df)
    candidates: List[Candidate] = []
    thesis = "ETF/central-bank/COT flow absorption after gold pullback or macro headwind; long-only H120 observer frontier."

    # A: flow support absorbs pullback; intentionally tests ETF/CB flow support beyond the current C96/S105 rules.
    for gold_col, gold_op, gold_thr, gold_tag in [
        (fm["gold_ret_20d"], "<", 0.0, "PULLBACK20"),
        (fm["gold_sma20_over_50"], "<", 0.0, "NOT_TRENDING"),
        (fm["gold_ret_60d"], "<", 0.0, "PULLBACK60"),
    ]:
        for etf_col, etf_tag in [(fm["etf_20d"], "ETF20"), (fm["etf_60d"], "ETF60")]:
            candidates.append(make_candidate(
                rule_id=f"S111_FA_{gold_tag}_{etf_tag}_CB_COT_H{horizon}",
                label=f"FLOW_ABSORPTION_{gold_tag}_{etf_tag}_CB_COT",
                family="FLOW_ABSORPTION_PULLBACK",
                thesis=thesis,
                horizon=horizon,
                conditions=[
                    cond(gold_col, gold_op, gold_thr),
                    cond(etf_col, ">", 0.0),
                    cond(fm["cb_3m"], ">", 0.0),
                    cond(fm["cot_z"], "<", 1.0),
                ],
            ))

    # B: macro headwind present but flow/resilience says gold is being absorbed rather than breaking.
    for head_col, head_op, head_tag in [
        (fm["dxy_ret_20d"], ">", "DXY20_UP"),
        (fm["dxy_ret_60d"], ">", "DXY60_UP"),
        (fm["real_yield_change_20d"], ">", "RY20_UP"),
        (fm["real_yield_change_60d"], ">", "RY60_UP"),
    ]:
        for gold_col, gold_op, gold_thr, gold_tag in [
            (fm["gold_ret_20d"], ">", 0.0, "GOLD20_UP"),
            (fm["gold_sma20_over_50"], ">", 0.0, "GOLD_TREND_UP"),
            (fm["gold_sma50_over_200"], ">", 0.0, "GOLD_STRUCT_UP"),
        ]:
            candidates.append(make_candidate(
                rule_id=f"S111_MH_{head_tag}_{gold_tag}_FLOW_H{horizon}",
                label=f"MACRO_HEADWIND_RESILIENCE_{head_tag}_{gold_tag}_FLOW",
                family="MACRO_HEADWIND_RESILIENCE",
                thesis=thesis,
                horizon=horizon,
                conditions=[
                    cond(head_col, head_op, 0.0),
                    cond(gold_col, gold_op, gold_thr),
                    cond(fm["etf_20d"], ">", 0.0),
                    cond(fm["cot_z"], "<", 1.5),
                ],
            ))

    # C: decrowding with flow support; this is intentionally audited against S105 overlap.
    for flow_col, flow_tag in [(fm["etf_20d"], "ETF20"), (fm["cb_3m"], "CB3M")]:
        for macro_col, macro_op, macro_tag in [
            (fm["real_yield_change_20d"], "<", "RY20_RELIEF"),
            (fm["dxy_ret_20d"], "<", "DXY20_RELIEF"),
            (fm["vix_change_20d"], ">", "VIX20_UP"),
        ]:
            candidates.append(make_candidate(
                rule_id=f"S111_CD_{flow_tag}_{macro_tag}_DECROWD_H{horizon}",
                label=f"COT_DECROWDING_FLOW_{flow_tag}_{macro_tag}",
                family="COT_DECROWDING_FLOW",
                thesis=thesis,
                horizon=horizon,
                conditions=[
                    cond(fm["cot_z_change_4w"], "<", 0.0),
                    cond(fm["cot_z"], "<", 1.0),
                    cond(flow_col, ">", 0.0),
                    cond(macro_col, macro_op, 0.0),
                ],
            ))

    # D: VIX/risk with flows; extends K03 by requiring flow confirmation instead of only real-yield relief.
    for risk_col, risk_tag in [(fm["vix_change_20d"], "VIX20_UP"), (fm["vix_ret_20d"], "VIXRET20_UP")]:
        for gold_col, gold_op, gold_tag in [(fm["gold_ret_20d"], "<", "GOLD_PULLBACK"), (fm["gold_sma20_over_50"], "<", "GOLD_NOT_TRENDING")]:
            candidates.append(make_candidate(
                rule_id=f"S111_RF_{risk_tag}_{gold_tag}_FLOW_H{horizon}",
                label=f"RISK_FLOW_ABSORPTION_{risk_tag}_{gold_tag}",
                family="RISK_FLOW_ABSORPTION",
                thesis=thesis,
                horizon=horizon,
                conditions=[
                    cond(risk_col, ">", 0.0),
                    cond(gold_col, gold_op, 0.0),
                    cond(fm["etf_20d"], ">", 0.0),
                    cond(fm["cot_z"], "<", 1.5),
                ],
            ))

    out = [c for c in candidates if c is not None]
    # de-duplicate by rule_id while preserving order
    seen = set()
    unique = []
    for c in out:
        if c.rule_id not in seen:
            unique.append(c)
            seen.add(c.rule_id)
    return unique, fm


def eval_conditions(df: pd.DataFrame, conditions: Sequence[Condition]) -> pd.Series:
    if not conditions:
        return pd.Series(False, index=df.index)
    mask = pd.Series(True, index=df.index)
    for c in conditions:
        if c.column not in df.columns or c.op not in OPS:
            return pd.Series(False, index=df.index)
        s = pd.to_numeric(df[c.column], errors="coerce")
        mask &= OPS[c.op](s, c.threshold).fillna(False)
    return mask.fillna(False)


def candidate_to_dict(c: Candidate) -> Dict[str, Any]:
    return {
        "rule_id": c.rule_id,
        "label": c.label,
        "family": c.family,
        "thesis": c.thesis,
        "horizon_trading_days": c.horizon_trading_days,
        "conditions_json": json.dumps([asdict(x) for x in c.conditions], ensure_ascii=False),
        "conditions_readable": " & ".join(f"{x.column}{x.op}{x.threshold:g}" for x in c.conditions),
    }


def metric_block(df: pd.DataFrame, signal: pd.Series, ret_col: str) -> Tuple[int, float, float, float]:
    values = pd.to_numeric(df.loc[signal, ret_col], errors="coerce").dropna()
    n = int(len(values))
    if n == 0:
        return 0, 0.0, 0.0, 0.0
    return n, float(values.mean()), float(values.median()), float((values > 0).mean())


def segment_mask(df: pd.DataFrame, date_col: str, start: str, end: str) -> pd.Series:
    s = pd.Timestamp(start)
    e = pd.Timestamp(end)
    return (df[date_col] >= s) & (df[date_col] <= e)


def year_event_share(df: pd.DataFrame, signal: pd.Series, date_col: str, ret_col: str) -> float:
    sub = df.loc[signal & df[ret_col].notna(), [date_col]]
    if len(sub) == 0:
        return 0.0
    counts = sub[date_col].dt.year.value_counts()
    return float(counts.max() / counts.sum()) if counts.sum() else 0.0


def overlap_stats(candidate_signal: pd.Series, existing_signals: Dict[str, pd.Series]) -> Tuple[float, float, int, Dict[str, float]]:
    cand_n = int(candidate_signal.sum())
    if cand_n == 0 or not existing_signals:
        return 0.0, 0.0, cand_n, {}
    union = pd.Series(False, index=candidate_signal.index)
    per_rule: Dict[str, float] = {}
    for rid, sig in existing_signals.items():
        sig = sig.reindex(candidate_signal.index, fill_value=False)
        inter = int((candidate_signal & sig).sum())
        per_rule[rid] = inter / cand_n if cand_n else 0.0
        union |= sig
    union_inter = int((candidate_signal & union).sum())
    union_share = union_inter / cand_n if cand_n else 0.0
    max_rule = max(per_rule.values()) if per_rule else 0.0
    incremental = int((candidate_signal & ~union).sum())
    return union_share, max_rule, incremental, per_rule


def asof_forward_tests(df: pd.DataFrame, signal: pd.Series, date_col: str, ret_col: str, asof_years: Sequence[int]) -> Tuple[float, int, List[Dict[str, Any]]]:
    rows: List[Dict[str, Any]] = []
    positives = 0
    tests = 0
    for y in asof_years:
        start = pd.Timestamp(year=y + 1, month=1, day=1)
        end = pd.Timestamp(year=y + 1, month=12, day=31)
        m = signal & (df[date_col] >= start) & (df[date_col] <= end) & df[ret_col].notna()
        n, mean_bps, median_bps, win_rate = metric_block(df, m, ret_col)
        if n <= 0:
            continue
        tests += 1
        if mean_bps > 0:
            positives += 1
        rows.append({
            "asof_date": f"{y}-12-31",
            "forward_year": y + 1,
            "n_forward_events": n,
            "mean_forward_net_bps": mean_bps,
            "median_forward_net_bps": median_bps,
            "forward_win_rate": win_rate,
            "positive_forward": bool(mean_bps > 0),
        })
    rate = positives / tests if tests else 0.0
    return float(rate), int(tests), rows


def evaluate_candidate(
    df: pd.DataFrame,
    candidate: Candidate,
    date_col: str,
    ret_col: str,
    segments: Dict[str, Sequence[str]],
    existing_signals: Dict[str, pd.Series],
    gate: Dict[str, Any],
    asof_years: Sequence[int],
) -> Tuple[CandidateMetrics, pd.Series, List[Dict[str, Any]], Dict[str, float]]:
    sig = eval_conditions(df, candidate.conditions) & df[ret_col].notna()
    n_total, mean_bps, median_bps, win_rate = metric_block(df, sig, ret_col)

    seg_results: Dict[str, Tuple[int, float, float, float]] = {}
    positive_segments = 0
    for name, bounds in segments.items():
        sm = sig & segment_mask(df, date_col, bounds[0], bounds[1])
        seg_results[name] = metric_block(df, sm, ret_col)
        if seg_results[name][0] > 0 and seg_results[name][1] > 0:
            positive_segments += 1

    n_train, mean_train, _, _ = seg_results.get("train", (0, 0.0, 0.0, 0.0))
    n_val, mean_val, _, _ = seg_results.get("validation", (0, 0.0, 0.0, 0.0))
    n_tail, mean_tail, _, win_tail = seg_results.get("tail_forward", (0, 0.0, 0.0, 0.0))
    max_year_share = year_event_share(df, sig, date_col, ret_col)
    union_share, max_rule_share, incremental_count, per_rule_overlap = overlap_stats(sig, existing_signals)
    asof_rate, asof_tests, asof_rows = asof_forward_tests(df, sig, date_col, ret_col, asof_years)

    reasons: List[str] = []
    if n_total < int(gate["min_total_events"]):
        reasons.append(f"n_total<{gate['min_total_events']}")
    if n_train < int(gate["min_train_events"]):
        reasons.append(f"n_train<{gate['min_train_events']}")
    if n_val < int(gate["min_validation_events"]):
        reasons.append(f"n_validation<{gate['min_validation_events']}")
    if n_tail < int(gate["min_tail_forward_events"]):
        reasons.append(f"n_tail_forward<{gate['min_tail_forward_events']}")
    if mean_bps < float(gate["min_mean_net_bps"]):
        reasons.append(f"mean_net_bps<{gate['min_mean_net_bps']}")
    if mean_val < float(gate["min_validation_mean_bps"]):
        reasons.append(f"validation_mean<{gate['min_validation_mean_bps']}")
    if mean_tail < float(gate["min_tail_forward_mean_bps"]):
        reasons.append(f"tail_forward_mean<{gate['min_tail_forward_mean_bps']}")
    if win_tail < float(gate["min_tail_forward_win_rate"]):
        reasons.append(f"tail_forward_win_rate<{gate['min_tail_forward_win_rate']}")
    if positive_segments < int(gate["min_positive_segments"]):
        reasons.append(f"positive_segments<{gate['min_positive_segments']}")
    if max_year_share > float(gate["max_year_event_share"]):
        reasons.append(f"max_year_event_share>{gate['max_year_event_share']}")
    if union_share > float(gate["max_union_overlap_share"]):
        reasons.append(f"union_overlap>{gate['max_union_overlap_share']}")
    if max_rule_share > float(gate["max_rule_overlap_share"]):
        reasons.append(f"max_rule_overlap>{gate['max_rule_overlap_share']}")
    if incremental_count < int(gate["min_incremental_events"]):
        reasons.append(f"incremental_events<{gate['min_incremental_events']}")
    if asof_tests > 0 and asof_rate < float(gate["min_asof_positive_rate"]):
        reasons.append(f"asof_positive_rate<{gate['min_asof_positive_rate']}")

    metrics = CandidateMetrics(
        rule_id=candidate.rule_id,
        label=candidate.label,
        family=candidate.family,
        thesis=candidate.thesis,
        horizon_trading_days=candidate.horizon_trading_days,
        n_total=n_total,
        mean_net_bps=mean_bps,
        median_net_bps=median_bps,
        win_rate=win_rate,
        n_train=n_train,
        mean_train_bps=mean_train,
        n_validation=n_val,
        mean_validation_bps=mean_val,
        n_tail_forward=n_tail,
        mean_tail_forward_bps=mean_tail,
        tail_forward_win_rate=win_tail,
        positive_segments=positive_segments,
        segment_count=len(segments),
        max_year_event_share=max_year_share,
        union_overlap_share=union_share,
        max_rule_overlap_share=max_rule_share,
        incremental_event_count=incremental_count,
        asof_positive_rate=asof_rate,
        asof_tests=asof_tests,
        pass_gate=len(reasons) == 0,
        reject_reasons=";".join(reasons),
    )
    return metrics, sig, asof_rows, per_rule_overlap


def build_existing_signals(df: pd.DataFrame, active_rules: Sequence[Dict[str, Any]]) -> Dict[str, pd.Series]:
    out: Dict[str, pd.Series] = {}
    for r in active_rules:
        conds = [Condition(column=x["column"], op=x.get("op", x.get("operator", ">")), threshold=float(x["threshold"])) for x in r.get("conditions", [])]
        out[r.get("rule_id", "UNKNOWN")] = eval_conditions(df, conds)
    return out


def rank_metrics(row: Dict[str, Any]) -> Tuple[float, ...]:
    return (
        1.0 if row.get("pass_gate") else 0.0,
        float(row.get("mean_tail_forward_bps", 0.0)),
        float(row.get("mean_validation_bps", 0.0)),
        float(row.get("mean_net_bps", 0.0)),
        float(row.get("incremental_event_count", 0)),
        -float(row.get("union_overlap_share", 0.0)),
    )


def run(root: Path, cfg: Dict[str, Any], out_dir: Path, top_override: Optional[int] = None) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    macro, macro_meta = load_macro_dataset(root, cfg)
    date_col = macro_meta["date_col"]
    price_col = macro_meta["price_col"]
    joined, cot_meta = load_and_join_cot(root, cfg, macro, date_col)
    joined = add_missing_derived_features(joined, date_col, price_col)
    joined = joined.sort_values(date_col).reset_index(drop=True)

    horizon = int(cfg["horizon_trading_days"])
    cost_bps = float(cfg.get("cost_bps", 20.0))
    ret_col = f"forward_{horizon}d_long_net_bps"
    joined[ret_col] = (joined["gold_close"].shift(-horizon) / joined["gold_close"] - 1.0) * 10000.0 - cost_bps

    candidates, feature_map = generate_candidates(joined, horizon)
    existing = build_existing_signals(joined, cfg.get("active_rules", DEFAULT_ACTIVE_RULES))

    metrics_rows: List[Dict[str, Any]] = []
    candidate_rows: List[Dict[str, Any]] = []
    asof_rows: List[Dict[str, Any]] = []
    overlap_rows: List[Dict[str, Any]] = []
    signal_snapshots: List[Dict[str, Any]] = []
    signal_masks: Dict[str, pd.Series] = {}

    for c in candidates:
        m, sig, asof, per_rule = evaluate_candidate(
            joined,
            c,
            date_col,
            ret_col,
            cfg["segments"],
            existing,
            cfg["gate"],
            cfg.get("asof_years", []),
        )
        md = asdict(m)
        md.update({
            "conditions_readable": " & ".join(f"{x.column}{x.op}{x.threshold:g}" for x in c.conditions),
            "conditions_json": json.dumps([asdict(x) for x in c.conditions], ensure_ascii=False),
        })
        metrics_rows.append(md)
        candidate_rows.append(candidate_to_dict(c))
        signal_masks[c.rule_id] = sig
        for a in asof:
            aa = {"rule_id": c.rule_id, "label": c.label, "family": c.family}
            aa.update(a)
            asof_rows.append(aa)
        for rid, share in per_rule.items():
            overlap_rows.append({"candidate_rule_id": c.rule_id, "existing_rule_id": rid, "candidate_event_overlap_share": share})
        # last 8 signals per candidate for inspection only; not an MT5 bridge.
        sub = joined.loc[sig, [date_col, ret_col]].tail(8)
        for _, rr in sub.iterrows():
            signal_snapshots.append({
                "rule_id": c.rule_id,
                "label": c.label,
                "signal_date_utc": rr[date_col].date().isoformat(),
                "forward_net_bps": float(rr[ret_col]) if pd.notna(rr[ret_col]) else "",
            })

    metrics_rows.sort(key=rank_metrics, reverse=True)
    top_n = int(top_override if top_override is not None else cfg.get("top_n", 12))
    selected_rows = [r for r in metrics_rows if r["pass_gate"]][:top_n]
    review_rows = metrics_rows[: max(top_n, 20)]

    decision = "STAGE111_SELECT_FOR_STAGE112_OBSERVER_REVIEW_NO_ORDER" if selected_rows else "STAGE111_NO_INCREMENTAL_FRONTIER_SELECTED_NO_ORDER"
    classification = "S111_FRONTIER_SELECTED_NO_ORDER" if selected_rows else "S111_FRONTIER_NO_PASS_NO_ORDER"

    write_csv(out_dir / "stage111_generated_candidates.csv", candidate_rows)
    write_csv(out_dir / "stage111_candidate_metrics.csv", metrics_rows)
    write_csv(out_dir / "stage111_selected_for_stage112.csv", selected_rows)
    write_csv(out_dir / "stage111_review_queue.csv", review_rows)
    write_csv(out_dir / "stage111_asof_forward_checks.csv", asof_rows)
    write_csv(out_dir / "stage111_overlap_matrix.csv", overlap_rows)
    write_csv(out_dir / "stage111_recent_signal_snapshot.csv", signal_snapshots)

    summary = {
        "stage": STAGE,
        "root": str(root),
        "generated_utc": utc_now(),
        "status": STATUS_COMPLETE,
        "decision": decision,
        "classification": classification,
        "disposition": "DISCOVERY_ONLY_NO_ORDER",
        "selected_thesis": "Macro/flow absorption frontier: ETF, central-bank and COT support after gold pullback or macro headwind.",
        "why_this_frontier": [
            "The Stage108/109 observer already covers DXY relief, real-yield relief, central-bank support and COT decrowding.",
            "Stage111 tests a complementary mechanism: institutional flow support and gold absorption under pullback/headwind regimes.",
            "Historical segmentation and tail-forward-as-proxy are primary; waiting for slow forward-only samples is not the main discovery path.",
        ],
        "macro_dataset": macro_meta,
        "cot_dataset": cot_meta,
        "data_join": {
            "rows": int(len(joined)),
            "outcome_valid_rows": int(joined[ret_col].notna().sum()),
            "feature_map": feature_map,
        },
        "horizon_trading_days": horizon,
        "cost_bps": cost_bps,
        "active_observer_rules_reference": [r.get("rule_id") for r in cfg.get("active_rules", DEFAULT_ACTIVE_RULES)],
        "generated_candidate_count": int(len(candidate_rows)),
        "pass_gate_count": int(len(selected_rows)),
        "selected_rule_ids": [r["rule_id"] for r in selected_rows],
        "hard_blocks": [
            "NO_AUTOMATED_ORDER",
            "NO_PAPER_ORDER",
            "NO_BROKER_CONNECTION",
            "NO_MT5_OR_EA_CHANGE_FROM_STAGE111",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_ORDER_AUTHORIZATION_FROM_STAGE111",
        ],
        "outputs": {
            "summary_json": str(out_dir / "stage111_macro_flow_absorption_frontier_discovery_summary.json"),
            "report_md": str(out_dir / "stage111_macro_flow_absorption_frontier_discovery_report.md"),
            "generated_candidates": str(out_dir / "stage111_generated_candidates.csv"),
            "candidate_metrics": str(out_dir / "stage111_candidate_metrics.csv"),
            "selected_for_stage112": str(out_dir / "stage111_selected_for_stage112.csv"),
            "review_queue": str(out_dir / "stage111_review_queue.csv"),
            "asof_forward_checks": str(out_dir / "stage111_asof_forward_checks.csv"),
            "overlap_matrix": str(out_dir / "stage111_overlap_matrix.csv"),
            "recent_signal_snapshot": str(out_dir / "stage111_recent_signal_snapshot.csv"),
        },
    }
    write_json(out_dir / "stage111_macro_flow_absorption_frontier_discovery_summary.json", summary)
    write_report(out_dir / "stage111_macro_flow_absorption_frontier_discovery_report.md", summary, selected_rows, review_rows, feature_map)
    return summary


def write_report(path: Path, summary: Dict[str, Any], selected_rows: List[Dict[str, Any]], review_rows: List[Dict[str, Any]], feature_map: Dict[str, Optional[str]]) -> None:
    lines: List[str] = []
    lines.append("# Stage111 Macro/Flow Absorption Frontier Discovery")
    lines.append("")
    lines.append(f"- status: `{summary['status']}`")
    lines.append(f"- decision: `{summary['decision']}`")
    lines.append(f"- classification: `{summary['classification']}`")
    lines.append("- order status: `NO_ORDER_AUTHORIZATION_FROM_STAGE111`")
    lines.append("")
    lines.append("## Selected thesis")
    lines.append("")
    lines.append(summary["selected_thesis"])
    lines.append("")
    lines.append("This stage is discovery-only. It does not modify EA code, does not copy an MT5 bridge CSV, and does not authorize paper/live orders.")
    lines.append("")
    lines.append("## Data")
    lines.append("")
    lines.append(f"- macro dataset: `{summary['macro_dataset']['path']}`")
    lines.append(f"- macro rows: `{summary['macro_dataset']['rows']}`")
    lines.append(f"- COT dataset: `{summary['cot_dataset']['path']}`")
    lines.append(f"- joined rows: `{summary['data_join']['rows']}`")
    lines.append(f"- valid outcome rows: `{summary['data_join']['outcome_valid_rows']}`")
    lines.append("")
    lines.append("## Feature map")
    lines.append("")
    for k, v in feature_map.items():
        lines.append(f"- `{k}` -> `{v}`")
    lines.append("")
    lines.append("## Selected candidates")
    lines.append("")
    if not selected_rows:
        lines.append("No candidate passed the Stage111 gate. Keep the 7-rule observer unchanged and continue discovery with the next frontier.")
    else:
        for r in selected_rows:
            lines.append(f"- `{r['rule_id']}` | family `{r['family']}` | tail mean `{float(r['mean_tail_forward_bps']):.2f}` bps | union overlap `{float(r['union_overlap_share']):.3f}`")
    lines.append("")
    lines.append("## Top review queue")
    lines.append("")
    for r in review_rows[:15]:
        lines.append(
            f"- `{r['rule_id']}` | pass `{r['pass_gate']}` | n `{r['n_total']}` | mean `{float(r['mean_net_bps']):.2f}` bps | "
            f"validation `{float(r['mean_validation_bps']):.2f}` | tail `{float(r['mean_tail_forward_bps']):.2f}` | reject `{r.get('reject_reasons','')}`"
        )
    lines.append("")
    lines.append("## Hard blocks")
    lines.append("")
    for b in summary["hard_blocks"]:
        lines.append(f"- `{b}`")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    root = Path(args.root).expanduser().resolve()
    cfg = load_config(root, args.config)
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    summary = run(root, cfg, out_dir, top_override=args.top)
    print(json.dumps({
        "status": summary["status"],
        "decision": summary["decision"],
        "selected_count": summary["pass_gate_count"],
        "selected_rule_ids": summary["selected_rule_ids"],
        "out": str(out_dir),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
