#!/usr/bin/env python3
"""
Stage126: consolidated hardening review for Stage125 frontier candidate(s) and optional MT5 status overlay.

This is report/status only. It never opens broker connections, sends orders, uses CTrade, or writes active trading surfaces.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

STAGE = "Stage126_FRONTIER_CANDIDATE_HARDENING_AND_SHADOW_OVERLAY"
STATUS_OK = "STAGE126_COMPLETE_FRONTIER_CANDIDATE_HARDENING_READY_NO_ORDER"
DECISION_OK = "STAGE126_STAGE127_SHADOW_REVIEW_QUEUE_READY_NO_ORDER"
STATUS_NO_CANDIDATE = "STAGE126_COMPLETE_NO_STAGE125_CANDIDATES_NO_ORDER"
DECISION_NO_CANDIDATE = "STAGE126_NO_STAGE127_QUEUE_COLLECT_FORWARD_TELEMETRY"
STATUS_BLOCKED = "STAGE126_BLOCKED_INPUTS_MISSING_NO_ORDER"
DECISION_BLOCKED = "STAGE126_BLOCKED_NO_STAGE127_QUEUE"

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_TRADE_REQUEST_FROM_STAGE126",
    "NO_ORDER_SEND",
    "NO_CTRADE_USAGE",
    "NO_MT5_EA_CHANGE_FROM_STAGE126",
    "NO_PAPER_LIVE",
    "NO_LIVE",
]

DEFAULT_MT5_FILES = Path("/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files")
DEFAULT_MT5_INDICATORS = Path("/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Indicators/Advisors/XAUUSD")

CANDIDATE_ID = "F125_04_SAFE_HAVEN_VIX_UP_DOLLAR_NOT_UP"
RULE9_ID = "S126_01_SAFE_HAVEN_VIX_UP_DOLLAR_NOT_UP_SHADOW"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_float(v, default=math.nan) -> float:
    try:
        if v is None:
            return default
        if isinstance(v, str) and not v.strip():
            return default
        x = float(v)
        if math.isfinite(x):
            return x
        return default
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


def load_csv_if_exists(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def parse_conditions(cond: str) -> List[Tuple[str, str, float]]:
    """Parse compact Stage125 condition strings such as vix_chg_20dgt0.49;dollar_pressure_chg_20dlt0.2258."""
    if not isinstance(cond, str):
        return []
    out: List[Tuple[str, str, float]] = []
    # Prefer longest operators first; feature names can contain underscores and digits.
    pattern = re.compile(r"^([A-Za-z0-9_]+?)(gte|lte|gt|lt|ge|le)([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)$")
    for part in [p.strip() for p in cond.split(";") if p.strip()]:
        m = pattern.match(part)
        if not m:
            continue
        col, op, val = m.group(1), m.group(2), float(m.group(3))
        if op == "ge":
            op = "gte"
        if op == "le":
            op = "lte"
        out.append((col, op, val))
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
    warnings: List[str] = []
    out = df.copy()
    time_col = None
    for c in ["utc_time", "time", "timestamp", "date"]:
        if c in out.columns:
            time_col = c
            break
    if time_col is None:
        raise ValueError("No time column found in dataset")
    out[time_col] = pd.to_datetime(out[time_col], utc=True, errors="coerce")
    out = out.dropna(subset=[time_col]).sort_values(time_col).reset_index(drop=True)
    if "utc_time" not in out.columns:
        out["utc_time"] = out[time_col]

    for c in ["fwd_ret_bps_h120", "fwd_ret_bps_120h", "forward_return_bps", "_stage124_forward_return_bps"]:
        if c in out.columns:
            out["_stage126_forward_return_bps"] = to_num(out[c])
            return out, "_stage126_forward_return_bps", warnings + [f"mapped_from:{c}"]
    if "close" in out.columns:
        close = to_num(out["close"])
        out["_stage126_forward_return_bps"] = (close.shift(-horizon_hours) / close - 1.0) * 10000.0
        return out, "_stage126_forward_return_bps", warnings + [f"computed_from_close_shift_{horizon_hours}h"]
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


def spaced_events(df: pd.DataFrame, hours: int) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    out_rows = []
    last_ts = None
    for _, row in df.sort_values("utc_time").iterrows():
        ts = row["utc_time"]
        if pd.isna(ts):
            continue
        if last_ts is None or (ts - last_ts).total_seconds() >= hours * 3600:
            out_rows.append(row)
            last_ts = ts
    return pd.DataFrame(out_rows)


def metric_row(rule_id: str, split: str, ev: pd.DataFrame, ret_col: str, cost_bps: float = 10.0) -> Dict[str, object]:
    r = to_num(ev[ret_col]) if ret_col in ev.columns else pd.Series(dtype=float)
    r = r.dropna()
    cost_r = r - cost_bps
    return {
        "rule_id": rule_id,
        "split": split,
        "events": int(len(ev)),
        "valid_return_events": int(len(r)),
        "mean_bps": float(r.mean()) if len(r) else math.nan,
        "hit_rate": float((r > 0).mean()) if len(r) else math.nan,
        "cost10_mean_bps": float(cost_r.mean()) if len(cost_r) else math.nan,
        "cost10_hit_rate": float((cost_r > 0).mean()) if len(cost_r) else math.nan,
        "worst_bps": float(r.min()) if len(r) else math.nan,
        "best_bps": float(r.max()) if len(r) else math.nan,
        "max_year_concentration_pct": year_concentration(ev["utc_time"]) if "utc_time" in ev.columns else math.nan,
    }


def decide_candidate(split_df: pd.DataFrame, non_overlap_all: int, missing_features: Sequence[str]) -> Tuple[str, str, List[str]]:
    reasons: List[str] = []
    if missing_features:
        reasons.append("missing_required_features:" + ",".join(missing_features))
    rows = {str(r["split"]): r for _, r in split_df.iterrows()}
    all_row = rows.get("all", {})
    val = rows.get("validation", {})
    tail = rows.get("tail", {})

    if safe_float(all_row.get("events"), 0) < 150:
        reasons.append("all_events_lt_150")
    if safe_float(val.get("events"), 0) < 15:
        reasons.append("validation_events_lt_15")
    if safe_float(tail.get("events"), 0) < 15:
        reasons.append("tail_events_lt_15")
    if safe_float(val.get("cost10_mean_bps")) <= 0:
        reasons.append("validation_cost10_mean_not_positive")
    if safe_float(tail.get("cost10_mean_bps")) <= 0:
        reasons.append("tail_cost10_mean_not_positive")
    if safe_float(tail.get("cost10_hit_rate"), 0) < 0.53:
        reasons.append("tail_cost10_hit_rate_lt_53pct")
    if safe_float(tail.get("max_year_concentration_pct"), 999) > 80:
        reasons.append("tail_year_concentration_gt_80pct")
    if non_overlap_all < 10:
        reasons.append("nonoverlap_events_lt_10")

    if not reasons:
        return "PASS_STAGE127_SHADOW_REVIEW_QUEUE", "STAGE127_RULE9_SHADOW_OVERLAY_REVIEW_READY_NO_ORDER", []
    # Keep positive but not hardened candidates in watch, not discard.
    positive_econ = safe_float(all_row.get("cost10_mean_bps")) > 0 and safe_float(all_row.get("cost10_hit_rate"), 0) >= 0.55
    if positive_econ and not missing_features:
        return "WATCH_STAGE127_ONLY_AFTER_FORWARD_CONFIRMATION", "COLLECT_MARKET_OPEN_FORWARD_TELEMETRY_FIRST", reasons
    return "REJECT_OR_DEFER_NO_STAGE127", "DO_NOT_BUILD_STAGE127_FROM_THIS_CANDIDATE", reasons


def build_kv(rows: Dict[str, object]) -> str:
    ordered = []
    for k, v in rows.items():
        if isinstance(v, float):
            if math.isnan(v):
                v = ""
            else:
                v = f"{v:.6g}"
        ordered.append(f"{k}|{v}")
    return "\n".join(ordered) + "\n"


def copy_indicator_source(src: Path, dst_dir: Path) -> Path:
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    atomic_write_text(dst, src.read_text(encoding="utf-8"))
    return dst


def run(root: Path, mt5_files: Path, mt5_indicators: Path, write_mt5_status_kv: bool, write_mql5_indicator: bool, horizon_hours: int) -> Dict[str, object]:
    root = root.expanduser().resolve()
    out_dir = root / "reports" / "stage126_frontier_candidate_hardening_and_shadow_overlay"
    out_dir.mkdir(parents=True, exist_ok=True)
    data_shadow_dir = root / "data" / "shadow_observer"
    data_shadow_dir.mkdir(parents=True, exist_ok=True)

    stage125_dir = root / "reports" / "stage125_market_open_shadow_telemetry_and_frontier_discovery"
    selected_path = stage125_dir / "stage125_selected_for_stage126.csv"
    summary125_path = stage125_dir / "stage125_market_open_shadow_telemetry_and_frontier_discovery_summary.json"
    dataset_path = root / "data" / "fundamental_event_inbox" / "features" / "stage117_joined_macro_cot_dollar_h1_research_dataset.csv"

    generated = utc_now()
    selected = load_csv_if_exists(selected_path)
    summary125 = {}
    if summary125_path.exists():
        try:
            summary125 = json.loads(summary125_path.read_text(encoding="utf-8"))
            dataset_path = Path(summary125.get("dataset_path") or dataset_path)
        except Exception:
            pass

    if selected.empty:
        summary = {
            "stage": STAGE,
            "generated_utc": generated,
            "status": STATUS_NO_CANDIDATE,
            "decision": DECISION_NO_CANDIDATE,
            "classification": "FRONTIER_HARDENING_NO_CANDIDATE_NO_ORDER",
            "hard_blocks": HARD_BLOCKS,
            "root": str(root),
            "stage125_selected_for_stage126": str(selected_path),
            "selected_rows_seen": 0,
            "stage127_candidate_count": 0,
            "next": ["Keep forward shadow telemetry running; do not build Stage127 until a candidate appears."],
        }
        atomic_write_text(out_dir / "stage126_frontier_candidate_hardening_and_shadow_overlay_summary.json", json.dumps(summary, indent=2))
        atomic_write_df(out_dir / "stage126_selected_for_stage127.csv", pd.DataFrame())
        return summary

    if not dataset_path.exists():
        summary = {
            "stage": STAGE,
            "generated_utc": generated,
            "status": STATUS_BLOCKED,
            "decision": DECISION_BLOCKED,
            "classification": "FRONTIER_HARDENING_INPUTS_MISSING_NO_ORDER",
            "hard_blocks": HARD_BLOCKS,
            "root": str(root),
            "dataset_path": str(dataset_path),
            "selected_rows_seen": int(len(selected)),
            "block_reasons": ["stage117_joined_dataset_missing"],
            "stage127_candidate_count": 0,
        }
        atomic_write_text(out_dir / "stage126_frontier_candidate_hardening_and_shadow_overlay_summary.json", json.dumps(summary, indent=2))
        return summary

    dataset = pd.read_csv(dataset_path)
    dataset, ret_col, ret_warnings = ensure_time_and_return(dataset, horizon_hours=horizon_hours)
    dataset["_split"] = split_labels(len(dataset))

    all_metrics: List[Dict[str, object]] = []
    all_split_metrics: List[Dict[str, object]] = []
    feature_rows: List[Dict[str, object]] = []
    selected_rows: List[Dict[str, object]] = []
    watch_rows: List[Dict[str, object]] = []
    kv_status: Dict[str, object] = {
        "stage": STAGE,
        "generated_utc": generated,
        "mode": "RULE9_FRONTIER_SHADOW_REVIEW_ONLY_NO_ORDER",
        "allow_trading": "false",
        "order_path": "blocked",
    }

    for _, cand in selected.iterrows():
        cid = str(cand.get("candidate_id", "")).strip() or CANDIDATE_ID
        thesis = str(cand.get("thesis", ""))
        conditions = parse_conditions(str(cand.get("conditions", "")))
        if not conditions and cid == CANDIDATE_ID:
            conditions = [("vix_chg_20d", "gt", 0.49), ("dollar_pressure_chg_20d", "lt", 0.2258)]
        feature_cols = [c.strip() for c in str(cand.get("feature_columns", "")).split(";") if c.strip()]
        if not feature_cols:
            feature_cols = sorted(set([c for c, _, _ in conditions]))

        mask, missing = apply_conditions(dataset, conditions)
        ev = dataset.loc[mask].copy()
        sp = spaced_events(ev, horizon_hours)
        split_rows = [metric_row(cid, "all", ev, ret_col)]
        for split in ["selection", "validation", "tail"]:
            split_rows.append(metric_row(cid, split, ev[ev["_split"] == split], ret_col))
        for r in split_rows:
            r["candidate_id"] = cid
            r["rule_id"] = RULE9_ID if cid == CANDIDATE_ID else cid
            all_split_metrics.append(r)

        for col in feature_cols:
            full_cov = float(to_num(dataset[col]).notna().mean() * 100.0) if col in dataset.columns else 0.0
            event_cov = float(to_num(ev[col]).notna().mean() * 100.0) if col in ev.columns and len(ev) else 0.0
            feature_rows.append({
                "candidate_id": cid,
                "feature": col,
                "present": col in dataset.columns,
                "full_coverage_pct": full_cov,
                "event_coverage_pct": event_cov,
            })

        split_df_tmp = pd.DataFrame(split_rows)
        status, decision, reasons = decide_candidate(split_df_tmp, int(len(sp)), missing)
        all_row = split_rows[0]
        tail_row = [r for r in split_rows if r["split"] == "tail"][0]
        metric = {
            "candidate_id": cid,
            "rule_id": RULE9_ID if cid == CANDIDATE_ID else cid,
            "thesis": thesis,
            "conditions": ";".join([f"{c}{op}{v}" for c, op, v in conditions]),
            "status": status,
            "decision": decision,
            "reasons": ";".join(reasons),
            "events": all_row["events"],
            "valid_return_events": all_row["valid_return_events"],
            "mean_bps": all_row["mean_bps"],
            "hit_rate": all_row["hit_rate"],
            "cost10_mean_bps": all_row["cost10_mean_bps"],
            "cost10_hit_rate": all_row["cost10_hit_rate"],
            "tail_events": tail_row["events"],
            "tail_cost10_mean_bps": tail_row["cost10_mean_bps"],
            "tail_cost10_hit_rate": tail_row["cost10_hit_rate"],
            "nonoverlap_events_h120": int(len(sp)),
            "max_year_concentration_pct": all_row["max_year_concentration_pct"],
            "missing_feature_keys": ";".join(missing),
        }
        all_metrics.append(metric)
        if status == "PASS_STAGE127_SHADOW_REVIEW_QUEUE":
            selected_rows.append(metric)
        else:
            watch_rows.append(metric)

        # For the first candidate, publish status for overlay even if WATCH; it is explicitly no-order.
        if not kv_status.get("candidate_id"):
            kv_status.update({
                "candidate_id": cid,
                "rule_id": metric["rule_id"],
                "candidate_status": status,
                "decision": decision,
                "events": metric["events"],
                "cost10_mean_bps": metric["cost10_mean_bps"],
                "cost10_hit_rate": metric["cost10_hit_rate"],
                "tail_cost10_mean_bps": metric["tail_cost10_mean_bps"],
                "tail_cost10_hit_rate": metric["tail_cost10_hit_rate"],
                "nonoverlap_events_h120": metric["nonoverlap_events_h120"],
                "reasons": metric["reasons"],
                "thesis": thesis or "Safe-haven VIX up / dollar not up",
            })

    metrics_df = pd.DataFrame(all_metrics)
    split_df = pd.DataFrame(all_split_metrics)
    feature_df = pd.DataFrame(feature_rows)
    selected_df = pd.DataFrame(selected_rows)
    watch_df = pd.DataFrame(watch_rows)

    metrics_path = out_dir / "stage126_frontier_candidate_hardening_metrics.csv"
    split_path = out_dir / "stage126_split_hardening_metrics.csv"
    feature_path = out_dir / "stage126_feature_availability.csv"
    selected_out_path = out_dir / "stage126_selected_for_stage127.csv"
    watch_path = out_dir / "stage126_watch_or_reject.csv"
    kv_repo_path = data_shadow_dir / "stage126_rule9_frontier_status_kv.csv"
    kv_report_path = out_dir / "stage126_rule9_frontier_status_kv.csv"
    governance_path = out_dir / "stage126_governance_no_order_manifest.csv"

    atomic_write_df(metrics_path, metrics_df)
    atomic_write_df(split_path, split_df)
    atomic_write_df(feature_path, feature_df)
    atomic_write_df(selected_out_path, selected_df)
    atomic_write_df(watch_path, watch_df)
    kv_text = build_kv(kv_status)
    atomic_write_text(kv_repo_path, kv_text)
    atomic_write_text(kv_report_path, kv_text)
    governance = pd.DataFrame([
        {"surface": "automated_order", "status": "BLOCKED", "reason": "Stage126 is review/status only"},
        {"surface": "paper_order", "status": "BLOCKED", "reason": "No paper/live path from Stage126"},
        {"surface": "broker_connection", "status": "BLOCKED", "reason": "No broker API usage"},
        {"surface": "mt5_indicator_status", "status": "OPTIONAL_STATUS_ONLY", "reason": "Indicator displays CSV; no OrderSend/CTrade"},
        {"surface": "stage127_queue", "status": "READY" if len(selected_df) else "NOT_READY", "reason": "Only hard-passed candidates enter Stage127"},
    ])
    atomic_write_df(governance_path, governance)

    mt5_status_kv = None
    if write_mt5_status_kv:
        mt5_status_kv = mt5_files.expanduser() / "xauusd_stage126_rule9_frontier_status_kv.csv"
        atomic_write_text(mt5_status_kv, kv_text)

    mt5_indicator_source = None
    if write_mql5_indicator:
        src = root / "mql5" / "Indicators" / "XAUUSD_Stage126_Rule9FrontierOverlayIndicator.mq5"
        if src.exists():
            mt5_indicator_source = copy_indicator_source(src, mt5_indicators.expanduser())

    status = STATUS_OK
    decision = DECISION_OK if len(selected_df) else "STAGE126_NO_STAGE127_QUEUE_COLLECT_FORWARD_TELEMETRY"
    summary = {
        "stage": STAGE,
        "generated_utc": generated,
        "status": status,
        "decision": decision,
        "classification": "FRONTIER_CANDIDATE_HARDENING_AND_SHADOW_OVERLAY_NO_ORDER",
        "hard_blocks": HARD_BLOCKS,
        "root": str(root),
        "market_open_context": "Stage125 confirmed market-open shadow telemetry path",
        "stage125_selected_rows_seen": int(len(selected)),
        "dataset_path": str(dataset_path),
        "dataset_rows": int(len(dataset)),
        "return_col_detected": ret_col,
        "return_source": ";".join(ret_warnings),
        "candidate_rows_reviewed": int(len(metrics_df)),
        "stage127_candidate_count": int(len(selected_df)),
        "watch_or_reject_count": int(len(watch_df)),
        "mt5_status_kv_written": bool(write_mt5_status_kv),
        "mt5_status_kv": str(mt5_status_kv) if mt5_status_kv else "",
        "mt5_indicator_written": bool(mt5_indicator_source),
        "mt5_indicator_source": str(mt5_indicator_source) if mt5_indicator_source else "",
        "recommended_runtime_mode": "KEEP_7_RULE_UNIFIED_OBSERVER_EA_RUNNING_PLUS_STAGE124F_RULE8_OVERLAY; ADD_STAGE126_RULE9_OVERLAY_ONLY_IF_PASS",
        "metrics": str(metrics_path),
        "split_metrics": str(split_path),
        "feature_availability": str(feature_path),
        "selected_for_stage127": str(selected_out_path),
        "watch_or_reject": str(watch_path),
        "status_kv_repo": str(kv_repo_path),
        "status_kv_report": str(kv_report_path),
        "governance_no_order_manifest": str(governance_path),
        "next": [
            "If stage127_candidate_count > 0, review Stage126 selected_for_stage127 and decide whether to attach the Stage126 rule-9 indicator overlay.",
            "Do not open order, paper-live, CTrade, or broker paths from Stage126.",
            "If stage127_candidate_count is zero, collect market-open forward telemetry instead of building another promotion stage.",
        ],
    }
    summary_path = out_dir / "stage126_frontier_candidate_hardening_and_shadow_overlay_summary.json"
    report_path = out_dir / "stage126_frontier_candidate_hardening_and_shadow_overlay_report.md"
    summary["summary_json"] = str(summary_path)
    summary["report_md"] = str(report_path)
    atomic_write_text(summary_path, json.dumps(summary, indent=2))
    report = [
        f"# {STAGE}",
        "",
        f"Generated UTC: {generated}",
        f"Status: {summary['status']}",
        f"Decision: {summary['decision']}",
        "",
        "## Candidate decision",
        metrics_df.to_markdown(index=False) if not metrics_df.empty else "No candidate rows.",
        "",
        "## Governance",
        governance.to_markdown(index=False),
        "",
        "No automated order, paper/live order, CTrade, OrderSend, or broker connection is enabled by this stage.",
    ]
    atomic_write_text(report_path, "\n".join(report) + "\n")
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=STAGE)
    p.add_argument("--root", default="/Users/vahid/Desktop/xauusd-trader")
    p.add_argument("--mt5-files", default=str(DEFAULT_MT5_FILES))
    p.add_argument("--mt5-indicators", default=str(DEFAULT_MT5_INDICATORS))
    p.add_argument("--write-mt5-status-kv", action="store_true")
    p.add_argument("--write-mql5-indicator", action="store_true")
    p.add_argument("--horizon-hours", type=int, default=120)
    args = p.parse_args(argv)
    summary = run(Path(args.root), Path(args.mt5_files), Path(args.mt5_indicators), args.write_mt5_status_kv, args.write_mql5_indicator, args.horizon_hours)
    print(f"{STAGE} | status={summary.get('status')} | decision={summary.get('decision')} | stage127_candidate_count={summary.get('stage127_candidate_count', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
