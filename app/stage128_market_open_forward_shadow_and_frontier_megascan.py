#!/usr/bin/env python3
# Stage128_MARKET_OPEN_FORWARD_SHADOW_AND_FRONTIER_MEGASCAN
# Report-only / shadow-only. No broker, no order, no EA trading change.

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


STAGE = "Stage128_MARKET_OPEN_FORWARD_SHADOW_AND_FRONTIER_MEGASCAN"
STATUS = "STAGE128_COMPLETE_FORWARD_SHADOW_AND_FRONTIER_MEGASCAN_READY_NO_ORDER"
DECISION_DEFAULT = "STAGE128_FORWARD_SHADOW_CONTINUE_AND_MEGASCAN_REVIEW_READY_NO_ORDER"
CLASSIFICATION = "MARKET_OPEN_FORWARD_SHADOW_AND_FRONTIER_MEGASCAN_NO_ORDER"

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_TRADE_REQUEST_FROM_STAGE128",
    "NO_ORDER_SEND",
    "NO_CTRADE_USAGE",
    "NO_MT5_EA_CHANGE_FROM_STAGE128",
    "NO_PAPER_LIVE",
    "NO_LIVE",
]

LEGACY_RULES = [
    "K06_RESILIENT_GOLD_VS_DXY_H120",
    "K03_SAFE_HAVEN_REALYIELD_H120",
    "K07_DXY_TREND_RELIEF_GOLD_TREND_H120",
    "S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120",
    "S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120",
    "C96_07_CB_SUPPORT_NOT_CROWDED_H120",
    "S105_03_COT_DECROWDING_CB_SUPPORT_RY_RELIEF_H120",
]

DEFAULT_MT5_FILES = (
    "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/"
    "drive_c/Program Files/MetaTrader 5/MQL5/Files"
)
DEFAULT_MT5_INDICATORS = (
    "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/"
    "drive_c/Program Files/MetaTrader 5/MQL5/Indicators"
)


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_csv_safe(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv_rows(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    ensure_dir(path.parent)
    if fieldnames is None:
        keys: List[str] = []
        for r in rows:
            for k in r.keys():
                if k not in keys:
                    keys.append(k)
        fieldnames = keys
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})
    tmp.replace(path)


def write_kv(path: Path, kv: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        for k, v in kv.items():
            f.write(f"{k}|{'' if v is None else v}\n")
    tmp.replace(path)


def coerce_num(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s.astype(float)
    return pd.to_numeric(s, errors="coerce")


def find_first_col(df: pd.DataFrame, names: Iterable[str]) -> Optional[str]:
    lower = {c.lower(): c for c in df.columns}
    for n in names:
        if n in df.columns:
            return n
        if n.lower() in lower:
            return lower[n.lower()]
    return None


def find_time_col(df: pd.DataFrame) -> Optional[str]:
    return find_first_col(df, ["utc_time", "time", "datetime", "date", "timestamp"])


def find_return_col(df: pd.DataFrame, horizon_hours: int) -> Optional[str]:
    candidates = [
        f"fwd_ret_bps_h{horizon_hours}",
        f"forward_return_bps_h{horizon_hours}",
        f"fwd_return_bps_h{horizon_hours}",
        "_stage124_forward_return_bps",
        "_stage127_forward_return_bps",
        "fwd_ret_bps_h120",
        "future_ret_bps_h120",
        "return_bps_h120",
    ]
    return find_first_col(df, candidates)


def load_dataset(root: Path, horizon_hours: int) -> Tuple[pd.DataFrame, str, str]:
    candidates = [
        root / "data/fundamental_event_inbox/features/stage117_joined_macro_cot_dollar_h1_research_dataset.csv",
        root / "reports/stage117_segmented_macro_cot_dollar_discovery/stage117_joined_macro_cot_dollar_h1_research_dataset.csv",
    ]
    for p in candidates:
        if p.exists():
            df = pd.read_csv(p)
            tcol = find_time_col(df)
            if tcol:
                df[tcol] = pd.to_datetime(df[tcol], errors="coerce", utc=True)
                df = df[df[tcol].notna()].sort_values(tcol).reset_index(drop=True)
            rcol = find_return_col(df, horizon_hours)
            if rcol and rcol != "_stage128_forward_return_bps":
                df["_stage128_forward_return_bps"] = coerce_num(df[rcol])
                return df, str(p), f"mapped_from:{rcol}"
            return df, str(p), "return_col_missing"
    return pd.DataFrame(), "", "dataset_missing"


def split_by_time(df: pd.DataFrame, time_col: str) -> Dict[str, pd.DataFrame]:
    d = df.sort_values(time_col).reset_index(drop=True)
    n = len(d)
    a = int(n * 0.60)
    b = int(n * 0.80)
    return {
        "selection": d.iloc[:a].copy(),
        "validation": d.iloc[a:b].copy(),
        "tail": d.iloc[b:].copy(),
        "all": d.copy(),
    }


def quantile(df: pd.DataFrame, col: str, q: float) -> float:
    if col not in df.columns:
        return math.nan
    vals = coerce_num(df[col]).dropna()
    if len(vals) == 0:
        return math.nan
    return float(vals.quantile(q))


@dataclass
class RuleSpec:
    rule_id: str
    thesis: str
    feature_cols: List[str]
    condition_expr: str
    builder: Any


def mask_rule(df: pd.DataFrame, spec: RuleSpec, thresholds: Dict[str, float]) -> pd.Series:
    try:
        return spec.builder(df, thresholds).fillna(False).astype(bool)
    except Exception:
        return pd.Series([False] * len(df), index=df.index)


def year_concentration(df: pd.DataFrame, time_col: str) -> Tuple[float, str]:
    if df.empty or time_col not in df.columns:
        return math.nan, ""
    years = pd.to_datetime(df[time_col], utc=True, errors="coerce").dt.year.dropna()
    if len(years) == 0:
        return math.nan, ""
    vc = years.value_counts(normalize=True)
    return float(vc.iloc[0] * 100.0), str(int(vc.index[0]))


def nonoverlap(df: pd.DataFrame, time_col: str, spacing_hours: int) -> pd.DataFrame:
    if df.empty or time_col not in df.columns:
        return df.copy()
    d = df.sort_values(time_col).copy()
    chosen = []
    last = None
    gap = pd.Timedelta(hours=spacing_hours)
    for idx, row in d.iterrows():
        t = row[time_col]
        if pd.isna(t):
            continue
        if last is None or (t - last) >= gap:
            chosen.append(idx)
            last = t
    return d.loc[chosen].copy()


def max_drawdown(vals: List[float]) -> float:
    cum = 0.0
    peak = 0.0
    mdd = 0.0
    for v in vals:
        cum += float(v)
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)
    return float(mdd)


def longest_loss_streak(vals: List[float]) -> int:
    best = cur = 0
    for v in vals:
        if float(v) <= 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return int(best)


def evaluate_events(events: pd.DataFrame, time_col: str, split_name: str, cost_bps: float = 10.0) -> Dict[str, Any]:
    ret_col = "_stage128_forward_return_bps"
    valid = coerce_num(events[ret_col]).dropna() if ret_col in events.columns else pd.Series(dtype=float)
    cost = valid - cost_bps
    yc, ty = year_concentration(events, time_col)
    return {
        "split": split_name,
        "events": int(len(events)),
        "valid_return_events": int(len(valid)),
        "mean_bps": float(valid.mean()) if len(valid) else math.nan,
        "hit_rate": float((valid > 0).mean()) if len(valid) else math.nan,
        "cost10_mean_bps": float(cost.mean()) if len(cost) else math.nan,
        "cost10_hit_rate": float((cost > 0).mean()) if len(cost) else math.nan,
        "worst_cost10_bps": float(cost.min()) if len(cost) else math.nan,
        "best_cost10_bps": float(cost.max()) if len(cost) else math.nan,
        "cumulative_cost10_bps": float(cost.sum()) if len(cost) else math.nan,
        "max_drawdown_cost10_bps": max_drawdown(cost.tolist()) if len(cost) else math.nan,
        "longest_loss_streak_cost10": longest_loss_streak(cost.tolist()) if len(cost) else 0,
        "max_year_concentration_pct": yc,
        "top_year": ty,
    }


def build_rule_specs(selection: pd.DataFrame) -> Tuple[List[RuleSpec], Dict[str, float]]:
    # Thresholds are selection-only to reduce leakage.
    cols = set(selection.columns)
    th = {
        "vix60": quantile(selection, "vix_chg_20d", 0.60),
        "vix70": quantile(selection, "vix_chg_20d", 0.70),
        "dollar40": quantile(selection, "dollar_pressure_chg_20d", 0.40),
        "dollar50": quantile(selection, "dollar_pressure_chg_20d", 0.50),
        "dollar60": quantile(selection, "dollar_pressure_chg_20d", 0.60),
        "ry40": quantile(selection, "real_yield_10y_chg_20d", 0.40),
        "ry50": quantile(selection, "real_yield_10y_chg_20d", 0.50),
        "spdr60": quantile(selection, "spdr_value_chg_20d", 0.60),
        "spdr50": quantile(selection, "spdr_value_chg_20d", 0.50),
        "cot70": quantile(selection, "cot_mm_net_z", 0.70),
        "cot60": quantile(selection, "cot_mm_net_z", 0.60),
        "gold20_40": quantile(selection, "gold_ret_20d", 0.40),
        "gold60_40": quantile(selection, "gold_ret_60d", 0.40),
        "vix5_60": quantile(selection, "vix_chg_5d", 0.60),
        "dollar5_40": quantile(selection, "dollar_pressure_chg_5d", 0.40),
    }

    specs: List[RuleSpec] = []

    def has(*names: str) -> bool:
        return all(n in cols for n in names)

    if has("vix_chg_20d", "dollar_pressure_chg_20d", "real_yield_10y_chg_20d"):
        specs.append(RuleSpec(
            "F128_01_VIX_UP_DOLLAR_RELIEF_REALYIELD_RELIEF",
            "Safe-haven impulse with VIX rising while dollar and real-yield pressure are not tightening.",
            ["vix_chg_20d", "dollar_pressure_chg_20d", "real_yield_10y_chg_20d"],
            "vix_chg_20d>q60 AND dollar_pressure_chg_20d<q50 AND real_yield_10y_chg_20d<q50",
            lambda d,t: (coerce_num(d["vix_chg_20d"]) > t["vix60"]) & (coerce_num(d["dollar_pressure_chg_20d"]) < t["dollar50"]) & (coerce_num(d["real_yield_10y_chg_20d"]) < t["ry50"])
        ))
        specs.append(RuleSpec(
            "F128_02_STRICT_VIX_UP_DOLLAR_DOWN_REALYIELD_DOWN",
            "Stricter deconcentrated version of safe-haven impulse requiring both dollar and real-yield relief.",
            ["vix_chg_20d", "dollar_pressure_chg_20d", "real_yield_10y_chg_20d"],
            "vix_chg_20d>q70 AND dollar_pressure_chg_20d<q40 AND real_yield_10y_chg_20d<q40",
            lambda d,t: (coerce_num(d["vix_chg_20d"]) > t["vix70"]) & (coerce_num(d["dollar_pressure_chg_20d"]) < t["dollar40"]) & (coerce_num(d["real_yield_10y_chg_20d"]) < t["ry40"])
        ))

    if has("vix_chg_20d", "dollar_pressure_chg_20d", "cot_mm_net_z"):
        specs.append(RuleSpec(
            "F128_03_VIX_UP_DOLLAR_NOT_UP_COT_NOT_CROWDED",
            "VIX risk impulse while dollar pressure is capped and managed-money gold positioning is not crowded.",
            ["vix_chg_20d", "dollar_pressure_chg_20d", "cot_mm_net_z"],
            "vix_chg_20d>q60 AND dollar_pressure_chg_20d<q60 AND cot_mm_net_z<q70",
            lambda d,t: (coerce_num(d["vix_chg_20d"]) > t["vix60"]) & (coerce_num(d["dollar_pressure_chg_20d"]) < t["dollar60"]) & (coerce_num(d["cot_mm_net_z"]) < t["cot70"])
        ))

    if has("dollar_pressure_chg_20d", "real_yield_10y_chg_20d", "spdr_value_chg_20d"):
        specs.append(RuleSpec(
            "F128_04_SPDR_SUPPORT_DOLLAR_RY_RELIEF",
            "ETF-flow support when both dollar pressure and real-yield pressure are in relief.",
            ["spdr_value_chg_20d", "dollar_pressure_chg_20d", "real_yield_10y_chg_20d"],
            "spdr_value_chg_20d>q50 AND dollar_pressure_chg_20d<q50 AND real_yield_10y_chg_20d<q50",
            lambda d,t: (coerce_num(d["spdr_value_chg_20d"]) > t["spdr50"]) & (coerce_num(d["dollar_pressure_chg_20d"]) < t["dollar50"]) & (coerce_num(d["real_yield_10y_chg_20d"]) < t["ry50"])
        ))
        specs.append(RuleSpec(
            "F128_05_STRICT_SPDR_SUPPORT_DOLLAR_RY_RELIEF",
            "Stricter ETF-flow support with stronger SPDR accumulation and stronger macro relief.",
            ["spdr_value_chg_20d", "dollar_pressure_chg_20d", "real_yield_10y_chg_20d"],
            "spdr_value_chg_20d>q60 AND dollar_pressure_chg_20d<q40 AND real_yield_10y_chg_20d<q40",
            lambda d,t: (coerce_num(d["spdr_value_chg_20d"]) > t["spdr60"]) & (coerce_num(d["dollar_pressure_chg_20d"]) < t["dollar40"]) & (coerce_num(d["real_yield_10y_chg_20d"]) < t["ry40"])
        ))

    if has("vix_chg_5d", "dollar_pressure_chg_5d", "vix_chg_20d"):
        specs.append(RuleSpec(
            "F128_06_SHORT_EVENT_PROXY_VIX_UP_DOLLAR_DOWN",
            "Short-horizon event-risk proxy using 5-day VIX shock and 5-day dollar relief.",
            ["vix_chg_5d", "dollar_pressure_chg_5d", "vix_chg_20d"],
            "vix_chg_5d>q60 AND dollar_pressure_chg_5d<q40 AND vix_chg_20d>q60",
            lambda d,t: (coerce_num(d["vix_chg_5d"]) > t["vix5_60"]) & (coerce_num(d["dollar_pressure_chg_5d"]) < t["dollar5_40"]) & (coerce_num(d["vix_chg_20d"]) > t["vix60"])
        ))

    if has("gold_ret_20d", "dollar_pressure_chg_20d", "real_yield_10y_chg_20d"):
        specs.append(RuleSpec(
            "F128_07_GOLD_PULLBACK_MACRO_RELIEF",
            "Gold pullback inside macro relief regime.",
            ["gold_ret_20d", "dollar_pressure_chg_20d", "real_yield_10y_chg_20d"],
            "gold_ret_20d<q40 AND dollar_pressure_chg_20d<q50 AND real_yield_10y_chg_20d<q50",
            lambda d,t: (coerce_num(d["gold_ret_20d"]) < t["gold20_40"]) & (coerce_num(d["dollar_pressure_chg_20d"]) < t["dollar50"]) & (coerce_num(d["real_yield_10y_chg_20d"]) < t["ry50"])
        ))

    return specs, th


def scan_frontier(df: pd.DataFrame, horizon_hours: int, spacing_hours: int) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if df.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    time_col = find_time_col(df) or "utc_time"
    if time_col not in df.columns:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    splits = split_by_time(df, time_col)
    specs, thresholds = build_rule_specs(splits["selection"])
    metric_rows: List[Dict[str, Any]] = []
    selected: List[Dict[str, Any]] = []
    watch_or_reject: List[Dict[str, Any]] = []

    for spec in specs:
        missing = [c for c in spec.feature_cols if c not in df.columns]
        feature_available = not missing
        split_metrics: Dict[str, Dict[str, Any]] = {}
        all_events = pd.DataFrame()
        if feature_available:
            for split_name, dsplit in splits.items():
                mask = mask_rule(dsplit, spec, thresholds)
                ev = dsplit[mask].copy()
                if split_name == "all":
                    all_events = ev
                m = evaluate_events(ev, time_col, split_name)
                split_metrics[split_name] = m
                row = dict(m)
                row.update({
                    "rule_id": spec.rule_id,
                    "thesis": spec.thesis,
                    "condition_expr": spec.condition_expr,
                    "required_features": ",".join(spec.feature_cols),
                    "missing_features": "",
                    "feature_available": True,
                })
                metric_rows.append(row)
            no = nonoverlap(all_events, time_col, spacing_hours)
            no_m = evaluate_events(no, time_col, "nonoverlap_h120")
            no_m.update({
                "rule_id": spec.rule_id,
                "thesis": spec.thesis,
                "condition_expr": spec.condition_expr,
                "required_features": ",".join(spec.feature_cols),
                "missing_features": "",
                "feature_available": True,
            })
            metric_rows.append(no_m)

            reasons = []
            sel = split_metrics.get("selection", {})
            val = split_metrics.get("validation", {})
            tail = split_metrics.get("tail", {})
            allm = split_metrics.get("all", {})
            if sel.get("events", 0) < 100:
                reasons.append("selection_events_lt_100")
            if val.get("events", 0) < 30:
                reasons.append("validation_events_lt_30")
            if tail.get("events", 0) < 30:
                reasons.append("tail_events_lt_30")
            if no_m.get("events", 0) < 10:
                reasons.append("nonoverlap_events_lt_10")
            if (val.get("cost10_mean_bps", math.nan) <= 0) or math.isnan(val.get("cost10_mean_bps", math.nan)):
                reasons.append("validation_cost10_mean_not_positive")
            if (tail.get("cost10_mean_bps", math.nan) <= 0) or math.isnan(tail.get("cost10_mean_bps", math.nan)):
                reasons.append("tail_cost10_mean_not_positive")
            if (tail.get("cost10_hit_rate", 0) < 0.55):
                reasons.append("tail_cost10_hit_rate_lt_55pct")
            if (val.get("max_year_concentration_pct", 100) > 80):
                reasons.append(f"validation_year_concentration_gt_80pct:{val.get('max_year_concentration_pct', math.nan):.2f}")
            if (tail.get("max_year_concentration_pct", 100) > 80):
                reasons.append(f"tail_year_concentration_gt_80pct:{tail.get('max_year_concentration_pct', math.nan):.2f}")
            if (no_m.get("max_year_concentration_pct", 100) > 80):
                reasons.append(f"nonoverlap_year_concentration_gt_80pct:{no_m.get('max_year_concentration_pct', math.nan):.2f}")
            if (no_m.get("cost10_mean_bps", math.nan) <= 0) or math.isnan(no_m.get("cost10_mean_bps", math.nan)):
                reasons.append("nonoverlap_cost10_mean_not_positive")
            if (no_m.get("cost10_hit_rate", 0) < 0.55):
                reasons.append("nonoverlap_cost10_hit_rate_lt_55pct")

            carry = {
                "rule_id": spec.rule_id,
                "thesis": spec.thesis,
                "condition_expr": spec.condition_expr,
                "required_features": ",".join(spec.feature_cols),
                "selection_events": sel.get("events", 0),
                "validation_events": val.get("events", 0),
                "tail_events": tail.get("events", 0),
                "nonoverlap_events": no_m.get("events", 0),
                "validation_cost10_mean_bps": val.get("cost10_mean_bps", math.nan),
                "tail_cost10_mean_bps": tail.get("cost10_mean_bps", math.nan),
                "tail_cost10_hit_rate": tail.get("cost10_hit_rate", math.nan),
                "nonoverlap_cost10_mean_bps": no_m.get("cost10_mean_bps", math.nan),
                "nonoverlap_cost10_hit_rate": no_m.get("cost10_hit_rate", math.nan),
                "validation_max_year_concentration_pct": val.get("max_year_concentration_pct", math.nan),
                "tail_max_year_concentration_pct": tail.get("max_year_concentration_pct", math.nan),
                "nonoverlap_max_year_concentration_pct": no_m.get("max_year_concentration_pct", math.nan),
                "decision_reasons": ";".join(reasons),
                "decision": "PASS_STAGE129_REVIEW_QUEUE" if not reasons else "WATCH_OR_REJECT",
            }
            if not reasons:
                selected.append(carry)
            else:
                watch_or_reject.append(carry)
        else:
            watch_or_reject.append({
                "rule_id": spec.rule_id,
                "thesis": spec.thesis,
                "condition_expr": spec.condition_expr,
                "required_features": ",".join(spec.feature_cols),
                "missing_features": ",".join(missing),
                "feature_available": False,
                "decision": "MISSING_FEATURES",
                "decision_reasons": "missing_features",
            })

    return pd.DataFrame(metric_rows), pd.DataFrame(selected), pd.DataFrame(watch_or_reject), pd.DataFrame([thresholds])


def read_kv_file(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.exists():
        return out
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if "|" in line:
                k, v = line.split("|", 1)
            elif "," in line:
                k, v = line.split(",", 1)
            else:
                continue
            out[k.strip()] = v.strip()
    except Exception:
        return out
    return out


def build_shadow_snapshot(root: Path, mt5_files: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    candidates = [
        ("rule8_stage124f", mt5_files / "xauusd_stage124f_rule8_overlay_kv.csv"),
        ("rule9_stage126", mt5_files / "xauusd_stage126_rule9_frontier_status_kv.csv"),
        ("rule9_stage127_review", mt5_files / "xauusd_stage127_rule9_review_status_kv.csv"),
        ("stage125_watch", mt5_files / "xauusd_stage125_market_open_watch_status_kv.csv"),
    ]
    rows = []
    for name, path in candidates:
        kv = read_kv_file(path)
        rows.append({
            "name": name,
            "path": str(path),
            "seen": bool(kv),
            "kv_count": len(kv),
            "status": kv.get("status") or kv.get("replay_status") or kv.get("stage127_status") or "",
            "allow_trading": kv.get("allow_trading") or "false",
            "cost10_mean_bps": kv.get("cost10_mean_bps") or kv.get("tail_cost10_mean_bps") or "",
            "last_signal": kv.get("last_signal") or kv.get("last_signal_time_utc") or "",
            "rule": kv.get("rule") or kv.get("rule_id") or "",
        })
    health = {
        "shadow_kv_files_seen": int(sum(1 for r in rows if r["seen"])),
        "rule8_seen": bool(rows[0]["seen"]),
        "rule9_seen": bool(rows[1]["seen"] or rows[2]["seen"]),
        "recommended_runtime_mode": "KEEP_7_RULE_UNIFIED_OBSERVER_EA_PLUS_RULE8_RULE9_INDICATOR_OVERLAYS; NO_ORDER",
    }
    return rows, health


def data_route_plan() -> List[Dict[str, Any]]:
    return [
        {
            "data_need": "Direct DXY",
            "current_status": "direct web/stooq often blocked",
            "operational_route": "Use FRED/Fed DTWEXBGS broad dollar index as primary dollar-pressure fallback",
            "blocking_for_current_megascan": "NO",
            "priority": "keep",
        },
        {
            "data_need": "Economic event calendar / surprises",
            "current_status": "commercial calendars not required and often unreliable/blocked",
            "operational_route": "Use FRED release dates + FOMC + Treasury + BLS/BEA/Census actual release backbones; build surprise proxies from actual changes, not scraped surprise estimates",
            "blocking_for_current_megascan": "NO",
            "priority": "medium",
        },
        {
            "data_need": "WGC central-bank gold",
            "current_status": "direct WGC dashboard/download can be blocked or login-gated",
            "operational_route": "Keep excluded from hard features; use SPDR flow proxy now; add IMF reserve/gold proxy only when automated access is stable",
            "blocking_for_current_megascan": "NO",
            "priority": "medium_later",
        },
        {
            "data_need": "COT 2009",
            "current_status": "one old annual file may be blocked/broken",
            "operational_route": "CFTC 2010+ futures-only/disaggregated history is enough for 2022+ AMarkets history; old 2009 not a blocker",
            "blocking_for_current_megascan": "NO",
            "priority": "low",
        },
    ]


def copy_indicator(src_name: str, root: Path, mt5_indicators: Path) -> List[str]:
    src = root / "mql5/Indicators" / src_name
    if not src.exists():
        return []
    dests = [
        mt5_indicators / src_name,
        mt5_indicators / "Advisors/XAUUSD" / src_name,
    ]
    written = []
    for d in dests:
        ensure_dir(d.parent)
        d.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        written.append(str(d))
    return written


def run(
    root: Path,
    mt5_files: Path,
    mt5_indicators: Path,
    horizon_hours: int = 120,
    spacing_hours: int = 120,
    write_mt5_status_kv: bool = False,
    write_mql5_indicator: bool = False,
) -> Dict[str, Any]:
    root = root.expanduser()
    mt5_files = mt5_files.expanduser()
    mt5_indicators = mt5_indicators.expanduser()
    out_dir = ensure_dir(root / "reports/stage128_market_open_forward_shadow_and_frontier_megascan")
    shadow_dir = ensure_dir(root / "data/shadow_observer")

    stage127_summary = read_json(root / "reports/stage127_rule9_deconcentration_combo_overlap_review/stage127_rule9_deconcentration_combo_overlap_review_summary.json")
    dataset, dataset_path, return_source = load_dataset(root, horizon_hours)
    time_col = find_time_col(dataset) if not dataset.empty else None
    metrics, selected, watch, thresholds = scan_frontier(dataset, horizon_hours, spacing_hours) if time_col else (pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    shadow_rows, telemetry_health = build_shadow_snapshot(root, mt5_files)

    metrics_path = out_dir / "stage128_frontier_megascan_metrics.csv"
    selected_path = out_dir / "stage128_selected_for_stage129.csv"
    watch_path = out_dir / "stage128_watch_or_reject.csv"
    thresholds_path = out_dir / "stage128_selection_thresholds.csv"
    snapshot_path = out_dir / "stage128_forward_shadow_runtime_snapshot.csv"
    route_path = out_dir / "stage128_data_route_plan.csv"
    status_kv_repo = shadow_dir / "stage128_forward_shadow_and_megascan_status_kv.csv"
    status_kv_report = out_dir / "stage128_forward_shadow_and_megascan_status_kv.csv"
    governance_path = out_dir / "stage128_governance_no_order_manifest.csv"

    metrics.to_csv(metrics_path, index=False)
    selected.to_csv(selected_path, index=False)
    watch.to_csv(watch_path, index=False)
    thresholds.to_csv(thresholds_path, index=False)
    write_csv_rows(snapshot_path, shadow_rows)
    write_csv_rows(route_path, data_route_plan())
    write_csv_rows(governance_path, [{"block": b, "status": "ACTIVE"} for b in HARD_BLOCKS])

    selected_count = int(len(selected))
    watch_count = int(len(watch))
    if selected_count > 0:
        decision = "STAGE128_STAGE129_FRONTIER_REVIEW_QUEUE_READY_NO_ORDER"
    else:
        decision = "STAGE128_FORWARD_SHADOW_CONTINUE_NO_NEW_FRONTIER_SELECTION_NO_ORDER"

    kv = {
        "stage": STAGE,
        "status": STATUS,
        "decision": decision,
        "generated_utc": now_utc(),
        "allow_trading": "false",
        "order_send": "false",
        "selected_for_stage129_count": selected_count,
        "watch_or_reject_count": watch_count,
        "rule8_seen": str(telemetry_health.get("rule8_seen", False)).lower(),
        "rule9_seen": str(telemetry_health.get("rule9_seen", False)).lower(),
        "stage127_status": stage127_summary.get("stage127_status", ""),
        "stage127_selected_for_stage128_count": stage127_summary.get("selected_for_stage128_count", ""),
        "runtime_mode": telemetry_health.get("recommended_runtime_mode", ""),
    }
    write_kv(status_kv_repo, kv)
    write_kv(status_kv_report, kv)
    mt5_status_kv = ""
    if write_mt5_status_kv:
        mt5_status = mt5_files / "xauusd_stage128_forward_shadow_and_megascan_status_kv.csv"
        write_kv(mt5_status, kv)
        mt5_status_kv = str(mt5_status)

    mt5_indicators_written: List[str] = []
    if write_mql5_indicator:
        mt5_indicators_written.extend(copy_indicator("XAUUSD_Stage128_CompactShadowDashboardIndicator.mq5", root, mt5_indicators))

    summary = {
        "stage": STAGE,
        "generated_utc": now_utc(),
        "status": STATUS,
        "decision": decision,
        "classification": CLASSIFICATION,
        "hard_blocks": HARD_BLOCKS,
        "root": str(root),
        "market_open_runtime_mode": telemetry_health.get("recommended_runtime_mode", ""),
        "stage127_prior_status": stage127_summary.get("status", ""),
        "stage127_prior_decision": stage127_summary.get("decision", ""),
        "stage127_prior_selected_for_stage128_count": stage127_summary.get("selected_for_stage128_count", ""),
        "stage127_prior_watch_or_defer_count": stage127_summary.get("watch_or_defer_count", ""),
        "dataset_path": dataset_path,
        "dataset_rows": int(len(dataset)),
        "return_source": return_source,
        "frontier_metric_rows": int(len(metrics)),
        "selected_for_stage129_count": selected_count,
        "watch_or_reject_count": watch_count,
        "telemetry_health": telemetry_health,
        "mt5_status_kv_written": bool(write_mt5_status_kv),
        "mt5_status_kv": mt5_status_kv,
        "mt5_indicators_written": mt5_indicators_written,
        "forward_shadow_runtime_snapshot": str(snapshot_path),
        "frontier_megascan_metrics": str(metrics_path),
        "selected_for_stage129": str(selected_path),
        "watch_or_reject": str(watch_path),
        "selection_thresholds": str(thresholds_path),
        "data_route_plan": str(route_path),
        "status_kv_repo": str(status_kv_repo),
        "status_kv_report": str(status_kv_report),
        "governance_no_order_manifest": str(governance_path),
        "summary_json": str(out_dir / "stage128_market_open_forward_shadow_and_frontier_megascan_summary.json"),
        "report_md": str(out_dir / "stage128_market_open_forward_shadow_and_frontier_megascan_report.md"),
        "next": [
            "If selected_for_stage129_count is zero, keep Rule8/Rule9 as shadow overlays and collect forward telemetry.",
            "If selected_for_stage129_count is positive, review candidates in one consolidated Stage129 package only; no order path.",
            "Do not change Unified_ObserverOnly_EA trading logic from Stage128.",
        ],
    }
    write_json(out_dir / "stage128_market_open_forward_shadow_and_frontier_megascan_summary.json", summary)
    report = [
        f"# {STAGE}",
        "",
        f"Status: `{STATUS}`",
        f"Decision: `{decision}`",
        "",
        "## No-order governance",
        "",
        "\n".join(f"- {b}" for b in HARD_BLOCKS),
        "",
        "## Runtime",
        "",
        f"- {telemetry_health.get('recommended_runtime_mode', '')}",
        f"- Rule8 seen: {telemetry_health.get('rule8_seen')}",
        f"- Rule9 seen: {telemetry_health.get('rule9_seen')}",
        "",
        "## Frontier megascan",
        "",
        f"- metric rows: {len(metrics)}",
        f"- selected for Stage129: {selected_count}",
        f"- watch/reject: {watch_count}",
    ]
    (out_dir / "stage128_market_open_forward_shadow_and_frontier_megascan_report.md").write_text("\n".join(report), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--mt5-files", default=DEFAULT_MT5_FILES)
    ap.add_argument("--mt5-indicators", default=DEFAULT_MT5_INDICATORS)
    ap.add_argument("--horizon-hours", type=int, default=120)
    ap.add_argument("--spacing-hours", type=int, default=120)
    ap.add_argument("--write-mt5-status-kv", action="store_true")
    ap.add_argument("--write-mql5-indicator", action="store_true")
    args = ap.parse_args()
    run(
        Path(args.root),
        Path(args.mt5_files),
        Path(args.mt5_indicators),
        args.horizon_hours,
        args.spacing_hours,
        args.write_mt5_status_kv,
        args.write_mql5_indicator,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
