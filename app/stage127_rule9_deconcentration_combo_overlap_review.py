#!/usr/bin/env python3
"""
Stage127: Rule9 deconcentration, non-overlap path, and combo-overlap review.

This is shadow/review only. It never sends orders, uses CTrade, opens broker connections,
or writes any active trading/order surface.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

STAGE = "Stage127_RULE9_DECONCENTRATION_COMBO_OVERLAP_REVIEW"
STATUS_OK = "STAGE127_COMPLETE_RULE9_DECONCENTRATION_COMBO_REVIEW_READY_NO_ORDER"
DECISION_WATCH = "STAGE127_RULE9_FORWARD_SHADOW_WATCH_REQUIRED_NO_PROMOTION"
DECISION_SELECTED = "STAGE127_STAGE128_RULE9_SHADOW_PORTFOLIO_REVIEW_QUEUE_READY_NO_ORDER"
STATUS_BLOCKED = "STAGE127_BLOCKED_INPUTS_MISSING_NO_ORDER"
DECISION_BLOCKED = "STAGE127_BLOCKED_NO_STAGE128_QUEUE"

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_TRADE_REQUEST_FROM_STAGE127",
    "NO_ORDER_SEND",
    "NO_CTRADE_USAGE",
    "NO_MT5_EA_CHANGE_FROM_STAGE127",
    "NO_PAPER_LIVE",
    "NO_LIVE",
]

DEFAULT_MT5_FILES = Path("/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files")
DEFAULT_MT5_INDICATORS_ROOT = Path("/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Indicators")
DEFAULT_MT5_INDICATORS_NESTED = DEFAULT_MT5_INDICATORS_ROOT / "Advisors" / "XAUUSD"

RULE9_ID = "S126_01_SAFE_HAVEN_VIX_UP_DOLLAR_NOT_UP_SHADOW"
CANDIDATE_ID = "F125_04_SAFE_HAVEN_VIX_UP_DOLLAR_NOT_UP"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_float(v, default=math.nan) -> float:
    try:
        if v is None:
            return default
        if isinstance(v, str) and not v.strip():
            return default
        x = float(v)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def to_num(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s.astype(float)
    return pd.to_numeric(s, errors="coerce")


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_df(path: Path, df: pd.DataFrame, **kwargs) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    df.to_csv(tmp, index=False, **kwargs)
    os.replace(tmp, path)


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def parse_conditions(cond: str) -> List[Tuple[str, str, float]]:
    if not isinstance(cond, str):
        return []
    out: List[Tuple[str, str, float]] = []
    pattern = re.compile(r"^([A-Za-z0-9_]+?)(gte|lte|gt|lt|ge|le)([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)$")
    for part in [p.strip() for p in cond.split(";") if p.strip()]:
        m = pattern.match(part)
        if not m:
            continue
        op = m.group(2)
        if op == "ge":
            op = "gte"
        if op == "le":
            op = "lte"
        out.append((m.group(1), op, float(m.group(3))))
    return out


def apply_conditions(df: pd.DataFrame, conditions: Sequence[Tuple[str, str, float]]) -> Tuple[pd.Series, List[str]]:
    mask = pd.Series(True, index=df.index)
    missing: List[str] = []
    for col, op, val in conditions:
        if col not in df.columns:
            missing.append(col)
            mask &= False
            continue
        x = to_num(df[col])
        if op == "gt":
            mask &= x > val
        elif op == "gte":
            mask &= x >= val
        elif op == "lt":
            mask &= x < val
        elif op == "lte":
            mask &= x <= val
        else:
            missing.append(f"unsupported_op:{col}:{op}")
            mask &= False
    return mask.fillna(False), missing


def ensure_time_and_return(df: pd.DataFrame, horizon_hours: int = 120) -> Tuple[pd.DataFrame, str, List[str]]:
    out = df.copy()
    time_col = next((c for c in ["utc_time", "time", "timestamp", "date"] if c in out.columns), None)
    if time_col is None:
        raise ValueError("No time column found in dataset")
    out[time_col] = pd.to_datetime(out[time_col], utc=True, errors="coerce")
    out = out.dropna(subset=[time_col]).sort_values(time_col).reset_index(drop=True)
    if "utc_time" not in out.columns:
        out["utc_time"] = out[time_col]

    for c in ["_stage126_forward_return_bps", "_stage124_forward_return_bps", "fwd_ret_bps_h120", "fwd_ret_bps_120h", "forward_return_bps"]:
        if c in out.columns:
            out["_stage127_forward_return_bps"] = to_num(out[c])
            return out, "_stage127_forward_return_bps", [f"mapped_from:{c}"]
    if "close" in out.columns:
        close = to_num(out["close"])
        out["_stage127_forward_return_bps"] = (close.shift(-horizon_hours) / close - 1.0) * 10000.0
        return out, "_stage127_forward_return_bps", [f"computed_from_close_shift_{horizon_hours}h"]
    raise ValueError("No forward return column and no close column to compute one")


def split_labels(n: int) -> List[str]:
    a = int(n * 0.60)
    b = int(n * 0.80)
    return ["selection" if i < a else "validation" if i < b else "tail" for i in range(n)]


def year_concentration(times: pd.Series) -> float:
    if len(times) == 0:
        return math.nan
    years = pd.to_datetime(times, utc=True, errors="coerce").dt.year.dropna()
    if len(years) == 0:
        return math.nan
    return float(years.value_counts(normalize=True).iloc[0] * 100.0)


def top_year(times: pd.Series) -> str:
    years = pd.to_datetime(times, utc=True, errors="coerce").dt.year.dropna()
    if len(years) == 0:
        return ""
    return str(int(years.value_counts().index[0]))


def spaced_events(df: pd.DataFrame, hours: int = 120) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    rows = []
    last_ts = None
    for _, row in df.sort_values("utc_time").iterrows():
        ts = row.get("utc_time")
        if pd.isna(ts):
            continue
        if last_ts is None or (ts - last_ts).total_seconds() >= hours * 3600:
            rows.append(row)
            last_ts = ts
    return pd.DataFrame(rows)


def metric_row(rule_id: str, split: str, ev: pd.DataFrame, ret_col: str, cost_bps: float = 10.0) -> Dict[str, object]:
    r = to_num(ev[ret_col]).dropna() if ret_col in ev.columns else pd.Series(dtype=float)
    cr = r - cost_bps
    return {
        "rule_id": rule_id,
        "split": split,
        "events": int(len(ev)),
        "valid_return_events": int(len(r)),
        "mean_bps": float(r.mean()) if len(r) else math.nan,
        "hit_rate": float((r > 0).mean()) if len(r) else math.nan,
        "cost10_mean_bps": float(cr.mean()) if len(cr) else math.nan,
        "cost10_hit_rate": float((cr > 0).mean()) if len(cr) else math.nan,
        "worst_bps": float(r.min()) if len(r) else math.nan,
        "best_bps": float(r.max()) if len(r) else math.nan,
        "max_year_concentration_pct": year_concentration(ev["utc_time"]) if "utc_time" in ev.columns else math.nan,
        "top_year": top_year(ev["utc_time"]) if "utc_time" in ev.columns else "",
    }


def path_metrics(ev: pd.DataFrame, ret_col: str, cost_bps: float = 10.0) -> Dict[str, object]:
    if ev.empty or ret_col not in ev.columns:
        return {
            "events": 0, "valid_return_events": 0, "cost10_mean_bps": math.nan, "cost10_hit_rate": math.nan,
            "cumulative_cost10_bps": math.nan, "max_drawdown_cost10_bps": math.nan,
            "longest_loss_streak_cost10": 0, "worst_cost10_bps": math.nan, "best_cost10_bps": math.nan,
        }
    r = to_num(ev.sort_values("utc_time")[ret_col]).dropna() - cost_bps
    if len(r) == 0:
        return {
            "events": int(len(ev)), "valid_return_events": 0, "cost10_mean_bps": math.nan, "cost10_hit_rate": math.nan,
            "cumulative_cost10_bps": math.nan, "max_drawdown_cost10_bps": math.nan,
            "longest_loss_streak_cost10": 0, "worst_cost10_bps": math.nan, "best_cost10_bps": math.nan,
        }
    cum = r.cumsum()
    peak = cum.cummax()
    dd = cum - peak
    streak = 0
    longest = 0
    for v in r:
        if v <= 0:
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 0
    return {
        "events": int(len(ev)),
        "valid_return_events": int(len(r)),
        "cost10_mean_bps": float(r.mean()),
        "cost10_hit_rate": float((r > 0).mean()),
        "cumulative_cost10_bps": float(cum.iloc[-1]),
        "max_drawdown_cost10_bps": float(dd.min()),
        "longest_loss_streak_cost10": int(longest),
        "worst_cost10_bps": float(r.min()),
        "best_cost10_bps": float(r.max()),
    }


def hour_set(df: pd.DataFrame, time_col: str = "utc_time") -> set:
    if df.empty or time_col not in df.columns:
        return set()
    ts = pd.to_datetime(df[time_col], utc=True, errors="coerce").dropna().dt.floor("h")
    return set(ts.astype(str))


def overlap_row(left_name: str, right_name: str, left: pd.DataFrame, right: pd.DataFrame) -> Dict[str, object]:
    a, b = hour_set(left), hour_set(right)
    inter = len(a & b)
    union = len(a | b)
    return {
        "left_rule": left_name,
        "right_rule": right_name,
        "left_events": len(a),
        "right_events": len(b),
        "intersection_events": inter,
        "union_events": union,
        "jaccard": float(inter / union) if union else math.nan,
        "status": "AVAILABLE" if union else "NOT_AVAILABLE",
    }


def load_stage124_events(root: Path) -> pd.DataFrame:
    candidates = [
        root / "reports" / "stage124_consolidated_shadow_csv_ea_and_frontier_discovery" / "stage124_consolidated_replay_events.csv",
        root / "reports" / "stage123_static_replay_shadow_observer_package" / "stage123_static_replay_events.csv",
    ]
    for p in candidates:
        df = load_csv(p)
        if not df.empty:
            time_col = next((c for c in ["utc_time", "event_time", "signal_time", "time", "timestamp"] if c in df.columns), None)
            if time_col:
                df["utc_time"] = pd.to_datetime(df[time_col], utc=True, errors="coerce")
                return df.dropna(subset=["utc_time"])
    return pd.DataFrame()


def legacy_rule_masks(df: pd.DataFrame) -> Dict[str, pd.Series]:
    specs = {
        "K06_RESILIENT_GOLD_VS_DXY_H120": [("gold_sma20_over_50", "gt", 0.0), ("real_yield_change_20d", "lt", 0.0)],
        "K03_SAFE_HAVEN_REALYIELD_H120": [("real_yield_change_20d", "lt", 0.0)],
        "K07_DXY_TREND_RELIEF_GOLD_TREND_H120": [("gold_sma20_over_50", "gt", 0.0), ("dxy_sma20_over_50", "lt", 0.0)],
        "S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120": [("real_yield_change_120d", "lt", 0.0)],
        "S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120": [("dxy_ret_120d", "lt", 0.0)],
        "C96_07_CB_SUPPORT_NOT_CROWDED_H120": [("cot_mm_net_z", "lt", 1.0), ("central_bank_demand_tonnes_3m", "gt", 0.0)],
        "S105_03_COT_DECROWDING_CB_SUPPORT_RY_RELIEF_H120": [("cot_mm_net_z_change_4w", "lt", 0.0), ("central_bank_demand_tonnes_3m", "gt", 0.0), ("real_yield_change_20d", "lt", 0.0)],
    }
    out: Dict[str, pd.Series] = {}
    for name, conds in specs.items():
        mask, missing = apply_conditions(df, conds)
        if missing:
            continue
        out[name] = mask
    return out


def decide_stage127(split_df: pd.DataFrame, nonoverlap: Dict[str, object], overlap_df: pd.DataFrame) -> Tuple[str, str, List[str]]:
    reasons: List[str] = []
    rows = {str(r["split"]): r for _, r in split_df.iterrows()}
    val = rows.get("validation", {})
    tail = rows.get("tail", {})
    all_row = rows.get("all", {})

    validation_conc = safe_float(val.get("max_year_concentration_pct"), 999)
    if validation_conc > 80:
        reasons.append(f"validation_year_concentration_gt_80pct:{validation_conc:.2f}")
    if safe_float(val.get("cost10_mean_bps")) <= 0:
        reasons.append("validation_cost10_mean_not_positive")
    if safe_float(tail.get("cost10_mean_bps")) <= 0:
        reasons.append("tail_cost10_mean_not_positive")
    if safe_float(tail.get("cost10_hit_rate"), 0) < 0.55:
        reasons.append("tail_cost10_hit_rate_lt_55pct")
    if safe_float(nonoverlap.get("events"), 0) < 30:
        reasons.append("nonoverlap_events_lt_30")
    if safe_float(nonoverlap.get("cost10_mean_bps")) <= 0:
        reasons.append("nonoverlap_cost10_mean_not_positive")
    if safe_float(nonoverlap.get("max_drawdown_cost10_bps"), 0) < -2500:
        reasons.append("nonoverlap_max_drawdown_cost10_lt_minus_2500bps")

    available_overlaps = overlap_df[overlap_df.get("status", "") == "AVAILABLE"] if not overlap_df.empty else pd.DataFrame()
    if not available_overlaps.empty:
        max_j = safe_float(available_overlaps["jaccard"].max(), 0.0)
        if max_j > 0.35:
            reasons.append(f"combo_overlap_jaccard_gt_35pct:{max_j:.3f}")

    if not reasons:
        return "PASS_STAGE128_SHADOW_PORTFOLIO_REVIEW_QUEUE", DECISION_SELECTED, []

    # Strong economics but concentration/overlap concern -> watch-only, not reject.
    positive = (
        safe_float(all_row.get("cost10_mean_bps")) > 0
        and safe_float(tail.get("cost10_mean_bps")) > 0
        and safe_float(nonoverlap.get("cost10_mean_bps")) > 0
        and safe_float(tail.get("cost10_hit_rate"), 0) >= 0.55
    )
    if positive:
        return "WATCH_FORWARD_SHADOW_DECONCENTRATION_REQUIRED", DECISION_WATCH, reasons
    return "REJECT_OR_DEFER_RULE9_NO_STAGE128", "STAGE127_RULE9_REJECT_OR_DEFER_NO_STAGE128_QUEUE", reasons


def build_kv(rows: Dict[str, object]) -> str:
    lines = []
    for k, v in rows.items():
        if isinstance(v, float):
            v = "" if math.isnan(v) else f"{v:.6g}"
        lines.append(f"{k}|{v}")
    return "\n".join(lines) + "\n"


def copy_to_many(src: Path, destinations: Iterable[Path]) -> List[str]:
    written = []
    text = src.read_text(encoding="utf-8")
    for dst_dir in destinations:
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / src.name
        atomic_write_text(dst, text)
        written.append(str(dst))
    return written


def run(root: Path, mt5_files: Path, write_mt5_status_kv: bool, write_mql5_indicators: bool, horizon_hours: int = 120) -> Dict[str, object]:
    root = root.expanduser()
    generated = utc_now()
    out_dir = root / "reports" / "stage127_rule9_deconcentration_combo_overlap_review"
    data_shadow_dir = root / "data" / "shadow_observer"
    out_dir.mkdir(parents=True, exist_ok=True)
    data_shadow_dir.mkdir(parents=True, exist_ok=True)

    selected_path = root / "reports" / "stage126_frontier_candidate_hardening_and_shadow_overlay" / "stage126_selected_for_stage127.csv"
    split126_path = root / "reports" / "stage126_frontier_candidate_hardening_and_shadow_overlay" / "stage126_split_hardening_metrics.csv"
    dataset_path = root / "data" / "fundamental_event_inbox" / "features" / "stage117_joined_macro_cot_dollar_h1_research_dataset.csv"

    selected = load_csv(selected_path)
    split126 = load_csv(split126_path)
    if selected.empty or not dataset_path.exists():
        summary = {
            "stage": STAGE,
            "generated_utc": generated,
            "status": STATUS_BLOCKED,
            "decision": DECISION_BLOCKED,
            "classification": "RULE9_DECONCENTRATION_COMBO_REVIEW_NO_ORDER",
            "hard_blocks": HARD_BLOCKS,
            "root": str(root),
            "selected_path": str(selected_path),
            "dataset_path": str(dataset_path),
            "block_reason": "missing_stage126_selected_or_dataset",
        }
        summary_path = out_dir / "stage127_rule9_deconcentration_combo_overlap_review_summary.json"
        summary["summary_json"] = str(summary_path)
        atomic_write_text(summary_path, json.dumps(summary, indent=2))
        print(f"{STAGE} | status={summary['status']} | decision={summary['decision']} | selected_for_stage128_count=0")
        return summary

    dataset_raw = pd.read_csv(dataset_path)
    dataset, ret_col, ret_warnings = ensure_time_and_return(dataset_raw, horizon_hours)
    dataset["_split"] = split_labels(len(dataset))

    cand = selected.iloc[0].to_dict()
    conditions = parse_conditions(str(cand.get("conditions", ""))) or [("vix_chg_20d", "gt", 0.49), ("dollar_pressure_chg_20d", "lt", 0.2258)]
    mask, missing = apply_conditions(dataset, conditions)
    events = dataset.loc[mask].copy()
    non_overlap_events = spaced_events(events, horizon_hours)

    split_rows = [metric_row(RULE9_ID, "all", events, ret_col)]
    for split in ["selection", "validation", "tail"]:
        split_rows.append(metric_row(RULE9_ID, split, events[events["_split"] == split], ret_col))
    split_df = pd.DataFrame(split_rows)

    nonoverlap_metrics = path_metrics(non_overlap_events, ret_col)
    nonoverlap_metrics.update({
        "rule_id": RULE9_ID,
        "candidate_id": str(cand.get("candidate_id", CANDIDATE_ID)),
        "spacing_hours": horizon_hours,
        "max_year_concentration_pct": year_concentration(non_overlap_events["utc_time"]) if "utc_time" in non_overlap_events.columns else math.nan,
        "top_year": top_year(non_overlap_events["utc_time"]) if "utc_time" in non_overlap_events.columns else "",
    })
    nonoverlap_df = pd.DataFrame([nonoverlap_metrics])

    # Combo overlap review: Stage124 rule8 if replay events exist; plus reconstructed legacy rule masks when columns are available.
    overlap_rows: List[Dict[str, object]] = []
    stage124_events = load_stage124_events(root)
    if not stage124_events.empty:
        overlap_rows.append(overlap_row(RULE9_ID, "S120_01_SPDR_FLOW_SUPPORT_MACRO_RELIEF_OBSERVER_DESIGN", events, stage124_events))
    else:
        overlap_rows.append({
            "left_rule": RULE9_ID,
            "right_rule": "S120_01_SPDR_FLOW_SUPPORT_MACRO_RELIEF_OBSERVER_DESIGN",
            "left_events": int(len(hour_set(events))),
            "right_events": 0,
            "intersection_events": 0,
            "union_events": int(len(hour_set(events))),
            "jaccard": math.nan,
            "status": "NOT_AVAILABLE_STAGE124_REPLAY_EVENTS_MISSING",
        })

    for legacy_name, legacy_mask in legacy_rule_masks(dataset).items():
        legacy_events = dataset.loc[legacy_mask].copy()
        overlap_rows.append(overlap_row(RULE9_ID, legacy_name, events, legacy_events))
    overlap_df = pd.DataFrame(overlap_rows)

    status, decision, reasons = decide_stage127(split_df, nonoverlap_metrics, overlap_df)
    summary_row = {
        "candidate_id": str(cand.get("candidate_id", CANDIDATE_ID)),
        "rule_id": RULE9_ID,
        "stage127_status": status,
        "stage127_decision": decision,
        "reasons": ";".join(reasons),
        "events": int(len(events)),
        "nonoverlap_events_h120": int(nonoverlap_metrics.get("events", 0)),
        "nonoverlap_cost10_mean_bps": nonoverlap_metrics.get("cost10_mean_bps", math.nan),
        "nonoverlap_cost10_hit_rate": nonoverlap_metrics.get("cost10_hit_rate", math.nan),
        "nonoverlap_max_drawdown_cost10_bps": nonoverlap_metrics.get("max_drawdown_cost10_bps", math.nan),
        "validation_year_concentration_pct": safe_float(split_df.loc[split_df["split"] == "validation", "max_year_concentration_pct"].iloc[0]) if (split_df["split"] == "validation").any() else math.nan,
        "tail_cost10_mean_bps": safe_float(split_df.loc[split_df["split"] == "tail", "cost10_mean_bps"].iloc[0]) if (split_df["split"] == "tail").any() else math.nan,
        "max_available_combo_jaccard": safe_float(overlap_df.loc[overlap_df["status"] == "AVAILABLE", "jaccard"].max(), math.nan) if not overlap_df.empty and "status" in overlap_df.columns else math.nan,
        "missing_features": ";".join(missing),
    }
    review_df = pd.DataFrame([summary_row])
    selected128 = review_df[review_df["stage127_status"] == "PASS_STAGE128_SHADOW_PORTFOLIO_REVIEW_QUEUE"].copy()
    watch_df = review_df[review_df["stage127_status"] != "PASS_STAGE128_SHADOW_PORTFOLIO_REVIEW_QUEUE"].copy()

    decon_path = out_dir / "stage127_rule9_deconcentration_metrics.csv"
    split_path = out_dir / "stage127_split_validation_concentration.csv"
    nonoverlap_path = out_dir / "stage127_nonoverlap_path_metrics.csv"
    overlap_path = out_dir / "stage127_combo_overlap_review.csv"
    selected_path_out = out_dir / "stage127_selected_for_stage128.csv"
    watch_path = out_dir / "stage127_watch_or_defer.csv"
    kv_repo = data_shadow_dir / "stage127_rule9_review_status_kv.csv"
    kv_report = out_dir / "stage127_rule9_review_status_kv.csv"
    governance_path = out_dir / "stage127_governance_no_order_manifest.csv"

    atomic_write_df(decon_path, review_df)
    atomic_write_df(split_path, split_df)
    atomic_write_df(nonoverlap_path, nonoverlap_df)
    atomic_write_df(overlap_path, overlap_df)
    atomic_write_df(selected_path_out, selected128)
    atomic_write_df(watch_path, watch_df)

    kv_text = build_kv({
        "stage": STAGE,
        "generated_utc": generated,
        "mode": "RULE9_DECONCENTRATION_COMBO_REVIEW_NO_ORDER",
        "allow_trading": "false",
        "order_path": "blocked",
        "rule_id": RULE9_ID,
        "stage127_status": status,
        "decision": decision,
        "reasons": ";".join(reasons),
        "events": int(len(events)),
        "nonoverlap_events_h120": nonoverlap_metrics.get("events", 0),
        "nonoverlap_cost10_mean_bps": nonoverlap_metrics.get("cost10_mean_bps", math.nan),
        "validation_year_concentration_pct": summary_row["validation_year_concentration_pct"],
        "selected_for_stage128_count": int(len(selected128)),
    })
    atomic_write_text(kv_repo, kv_text)
    atomic_write_text(kv_report, kv_text)
    mt5_status_kv = ""
    if write_mt5_status_kv:
        mt5_path = mt5_files.expanduser() / "xauusd_stage127_rule9_review_status_kv.csv"
        atomic_write_text(mt5_path, kv_text)
        mt5_status_kv = str(mt5_path)

    indicator_written_paths: List[str] = []
    if write_mql5_indicators:
        indicator_sources = [
            root / "mql5" / "Indicators" / "XAUUSD_Stage124F_Rule8OverlayIndicator.mq5",
            root / "mql5" / "Indicators" / "XAUUSD_Stage126_Rule9FrontierOverlayIndicator.mq5",
        ]
        for src in indicator_sources:
            if src.exists():
                indicator_written_paths.extend(copy_to_many(src, [DEFAULT_MT5_INDICATORS_ROOT.expanduser(), DEFAULT_MT5_INDICATORS_NESTED.expanduser()]))

    governance = pd.DataFrame([
        {"surface": "automated_order", "status": "BLOCKED", "reason": "Stage127 is review only"},
        {"surface": "paper_order", "status": "BLOCKED", "reason": "No paper/live path"},
        {"surface": "broker_connection", "status": "BLOCKED", "reason": "No broker API use"},
        {"surface": "mt5_ea_change", "status": "BLOCKED", "reason": "No EA changes from Stage127"},
        {"surface": "indicator_layout", "status": "OPTIONAL_STATUS_ONLY", "reason": "Stage124F/126 overlays may be rewritten for readability only"},
        {"surface": "stage128_queue", "status": "READY" if len(selected128) else "NOT_READY", "reason": decision},
    ])
    atomic_write_df(governance_path, governance)

    summary = {
        "stage": STAGE,
        "generated_utc": generated,
        "status": STATUS_OK,
        "decision": decision,
        "classification": "RULE9_DECONCENTRATION_COMBO_OVERLAP_REVIEW_NO_ORDER",
        "hard_blocks": HARD_BLOCKS,
        "root": str(root),
        "stage126_selected_rows_seen": int(len(selected)),
        "dataset_path": str(dataset_path),
        "dataset_rows": int(len(dataset)),
        "return_col_detected": ret_col,
        "return_source": ";".join(ret_warnings),
        "rule9_events": int(len(events)),
        "nonoverlap_events_h120": int(nonoverlap_metrics.get("events", 0)),
        "validation_year_concentration_pct": summary_row["validation_year_concentration_pct"],
        "tail_cost10_mean_bps": summary_row["tail_cost10_mean_bps"],
        "max_available_combo_jaccard": summary_row["max_available_combo_jaccard"],
        "selected_for_stage128_count": int(len(selected128)),
        "watch_or_defer_count": int(len(watch_df)),
        "stage127_status": status,
        "stage127_reasons": reasons,
        "mt5_status_kv_written": bool(write_mt5_status_kv),
        "mt5_status_kv": mt5_status_kv,
        "mt5_indicators_written": indicator_written_paths,
        "recommended_runtime_mode": "KEEP_7_RULE_UNIFIED_OBSERVER_EA_PLUS_STAGE124F_RULE8_AND_STAGE126_RULE9_INDICATOR_OVERLAYS; NO_ORDER",
        "deconcentration_metrics": str(decon_path),
        "split_validation_concentration": str(split_path),
        "nonoverlap_path_metrics": str(nonoverlap_path),
        "combo_overlap_review": str(overlap_path),
        "selected_for_stage128": str(selected_path_out),
        "watch_or_defer": str(watch_path),
        "status_kv_repo": str(kv_repo),
        "status_kv_report": str(kv_report),
        "governance_no_order_manifest": str(governance_path),
        "next": [
            "If selected_for_stage128_count is zero, keep Rule9 as shadow overlay and collect market-open forward telemetry.",
            "If selected_for_stage128_count is positive, Stage128 can review portfolio integration only; no order path.",
            "Do not change Unified_ObserverOnly_EA trading logic from Stage127.",
        ],
    }
    summary_path = out_dir / "stage127_rule9_deconcentration_combo_overlap_review_summary.json"
    report_path = out_dir / "stage127_rule9_deconcentration_combo_overlap_review_report.md"
    summary["summary_json"] = str(summary_path)
    summary["report_md"] = str(report_path)
    atomic_write_text(summary_path, json.dumps(summary, indent=2))
    report = [
        f"# {STAGE}",
        "",
        f"Generated UTC: {generated}",
        f"Status: {STATUS_OK}",
        f"Decision: {decision}",
        "",
        "## Rule9 decision",
        review_df.to_markdown(index=False),
        "",
        "## Split concentration",
        split_df.to_markdown(index=False),
        "",
        "## Non-overlap path",
        nonoverlap_df.to_markdown(index=False),
        "",
        "## Combo overlap",
        overlap_df.to_markdown(index=False),
        "",
        "No automated order, paper/live order, CTrade, OrderSend, broker connection, or EA trading change is enabled by this stage.",
    ]
    atomic_write_text(report_path, "\n".join(report) + "\n")

    print(f"{STAGE} | status={summary['status']} | decision={summary['decision']} | selected_for_stage128_count={summary['selected_for_stage128_count']} | watch_or_defer_count={summary['watch_or_defer_count']}")
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=STAGE)
    p.add_argument("--root", default="/Users/vahid/Desktop/xauusd-trader")
    p.add_argument("--mt5-files", default=str(DEFAULT_MT5_FILES))
    p.add_argument("--write-mt5-status-kv", action="store_true")
    p.add_argument("--write-mql5-indicators", action="store_true")
    p.add_argument("--horizon-hours", type=int, default=120)
    args = p.parse_args(argv)
    run(Path(args.root), Path(args.mt5_files), args.write_mt5_status_kv, args.write_mql5_indicators, args.horizon_hours)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
