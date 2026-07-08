#!/usr/bin/env python3
"""
Stage163: macro-supported side discovery for XAUUSD M5.

Read-only/offline scanner. It does not write MT5 KV files and does not enable orders.
It is designed for the case where Stage159 produced technical long candidates but
Stage161 classified all of them as macro-conflicted under the current macro regime.

The scanner searches both LONG and SHORT technical rules, then marks which side is
supported by the current macro pressure reported by Stage161. It is intentionally
execution-agnostic: if SHORT candidates survive, a separate EA/execution-side review
is still required before any demo order is allowed.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

STAGE = "Stage163_MACRO_SUPPORTED_SIDE_DISCOVERY"
DEFAULT_ROOT = "/Users/vahid/Desktop/xauusd-trader"
DEFAULT_BARS = "/Users/vahid/Downloads/xauusd_fundamental_event_inbox/amarkets_xauusd_5m.csv"
DEFAULT_STAGE161 = "reports/stage161_macro_aware_candidate_classifier/stage161_macro_aware_candidate_classifier_summary.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def write_rows_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    fieldnames: List[str] = []
    for row in rows:
        for k in row.keys():
            if k not in fieldnames:
                fieldnames.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def normalize_col(name: str) -> str:
    return str(name).strip().lower().replace(" ", "_").replace("-", "_")


def find_column(columns: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    lower_map = {normalize_col(c): c for c in columns}
    for cand in candidates:
        key = normalize_col(cand)
        if key in lower_map:
            return lower_map[key]
    for cand in candidates:
        ckey = normalize_col(cand)
        for key, original in lower_map.items():
            if ckey in key:
                return original
    return None


def load_bars(path: Path, timestamp_shift_hours: float = 0.0) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"bars file not found: {path}")
    # Try common separators; AMarkets exports have appeared as comma or semicolon.
    last_err: Optional[Exception] = None
    df: Optional[pd.DataFrame] = None
    for sep in [",", ";", "\t"]:
        try:
            tmp = pd.read_csv(path, sep=sep)
            if tmp.shape[1] >= 5:
                df = tmp
                break
        except Exception as exc:
            last_err = exc
    if df is None:
        if last_err:
            raise last_err
        raise ValueError(f"could not parse bars file: {path}")

    columns = list(df.columns)
    time_col = find_column(columns, ["utc_time", "time_utc", "datetime", "date", "time", "timestamp"])
    open_col = find_column(columns, ["open", "o"])
    high_col = find_column(columns, ["high", "h"])
    low_col = find_column(columns, ["low", "l"])
    close_col = find_column(columns, ["close", "c", "bid_close"])
    volume_col = find_column(columns, ["volume", "tick_volume", "vol"])
    if not all([time_col, open_col, high_col, low_col, close_col]):
        raise ValueError(
            "missing required OHLC/time columns; "
            f"found={columns[:20]} time={time_col} open={open_col} high={high_col} low={low_col} close={close_col}"
        )

    out = pd.DataFrame()
    out["utc_time"] = pd.to_datetime(df[time_col], errors="coerce", utc=True)
    if timestamp_shift_hours:
        out["utc_time"] = out["utc_time"] + pd.to_timedelta(timestamp_shift_hours, unit="h")
    for dst, src in [("open", open_col), ("high", high_col), ("low", low_col), ("close", close_col)]:
        out[dst] = pd.to_numeric(df[src], errors="coerce")
    if volume_col:
        out["volume"] = pd.to_numeric(df[volume_col], errors="coerce")
    else:
        out["volume"] = np.nan
    out = out.dropna(subset=["utc_time", "open", "high", "low", "close"]).sort_values("utc_time")
    out = out.drop_duplicates(subset=["utc_time"], keep="last").reset_index(drop=True)
    if out.empty:
        raise ValueError("no parseable bars after OHLC/time normalization")
    return out


def bps_change(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a / b - 1.0) * 10000.0


def compute_features(bars: pd.DataFrame, horizon_bars: int) -> pd.DataFrame:
    df = bars.copy()
    close = df["close"]
    high = df["high"]
    low = df["low"]
    # Return/trend features. Names intentionally align with Stage150/159 family style.
    for hours, bars_n in [(1, 12), (3, 36), (6, 72), (12, 144), (24, 288), (48, 576)]:
        df[f"ret_{hours}h_bps"] = bps_change(close, close.shift(bars_n))
    ma8 = close.rolling(8, min_periods=8).mean()
    ma20 = close.rolling(20, min_periods=20).mean()
    ma50 = close.rolling(50, min_periods=50).mean()
    ma100 = close.rolling(100, min_periods=100).mean()
    df["trend_8_20_bps"] = (ma8 - ma20) / close * 10000.0
    df["trend_20_50_bps"] = (ma20 - ma50) / close * 10000.0
    df["trend_50_100_bps"] = (ma50 - ma100) / close * 10000.0
    roll_high = high.rolling(288, min_periods=100).max()
    roll_low = low.rolling(288, min_periods=100).min()
    denom = (roll_high - roll_low).replace(0, np.nan)
    df["range_pos_24h"] = ((close - roll_low) / denom * 100.0).clip(0, 100)
    ret5 = bps_change(close, close.shift(1))
    df["vol_6h_bps"] = ret5.rolling(72, min_periods=36).std()
    future_close = close.shift(-horizon_bars)
    df["future_long_bps"] = bps_change(future_close, close)
    df["future_short_bps"] = -df["future_long_bps"]
    df["session"] = df["utc_time"].dt.hour.map(session_from_hour)
    df["fold"] = chrono_folds(len(df))
    return df


def session_from_hour(hour: int) -> str:
    # Broad FX/gold-style UTC buckets, not broker-local.
    if 0 <= int(hour) < 7:
        return "ASIA"
    if 7 <= int(hour) < 13:
        return "LONDON"
    if 13 <= int(hour) < 21:
        return "NY"
    return "LATE_US"


def chrono_folds(n: int) -> np.ndarray:
    if n <= 0:
        return np.array([], dtype=object)
    idx = np.arange(n, dtype=float) / max(n - 1, 1)
    labels = np.full(n, "F4_RECENT", dtype=object)
    labels[idx < 0.25] = "F1_OLD"
    labels[(idx >= 0.25) & (idx < 0.50)] = "F2_MID"
    labels[(idx >= 0.50) & (idx < 0.75)] = "F3_LATE"
    return labels


@dataclass(frozen=True)
class Condition:
    feature: str
    op: str
    threshold: float
    label: str

    def mask(self, values: np.ndarray) -> np.ndarray:
        if self.op == "GEQ":
            return values >= self.threshold
        if self.op == "LEQ":
            return values <= self.threshold
        raise ValueError(f"unsupported op: {self.op}")

    def as_dict(self) -> Dict[str, Any]:
        return {"feature": self.feature, "op": self.op, "threshold": self.threshold, "label": self.label}


def macro_supported_sides(stage161: Dict[str, Any]) -> Tuple[List[str], str, str]:
    ctx = stage161.get("macro_context") or {}
    pressure = str(ctx.get("gold_macro_pressure") or "").upper()
    if "HEADWIND" in pressure:
        return ["SHORT"], pressure, "Headwind for gold: prefer short-side discovery; long continuation is macro-conflicted."
    if "TAILWIND" in pressure:
        return ["LONG"], pressure, "Tailwind for gold: prefer long-side discovery; short continuation is macro-conflicted."
    return ["LONG", "SHORT"], pressure or "UNKNOWN", "Macro pressure is mixed/unknown: scan both sides, but no demo release without manual review."


def valid_feature_columns(df: pd.DataFrame) -> List[str]:
    preferred = [
        "ret_1h_bps", "ret_3h_bps", "ret_6h_bps", "ret_12h_bps", "ret_24h_bps", "ret_48h_bps",
        "trend_8_20_bps", "trend_20_50_bps", "trend_50_100_bps", "range_pos_24h", "vol_6h_bps",
    ]
    return [c for c in preferred if c in df.columns and pd.to_numeric(df[c], errors="coerce").notna().sum() > 100]


def build_conditions(df: pd.DataFrame, features: Sequence[str], quantiles: Sequence[float]) -> List[Condition]:
    conditions: List[Condition] = []
    for feature in features:
        vals = pd.to_numeric(df[feature], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        if vals.empty:
            continue
        for q in quantiles:
            thr = float(vals.quantile(q))
            q_label = int(round(q * 100))
            conditions.append(Condition(feature=feature, op="GEQ", threshold=thr, label=f"{feature}_GEQ{q_label}"))
            conditions.append(Condition(feature=feature, op="LEQ", threshold=thr, label=f"{feature}_LEQ{q_label}"))
    # Deduplicate condition labels in rare quantile collisions.
    seen = set()
    out = []
    for c in conditions:
        key = (c.feature, c.op, round(c.threshold, 8))
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def evaluate_mask(df: pd.DataFrame, mask: np.ndarray, outcome_col: str) -> Dict[str, Any]:
    vals = pd.to_numeric(df.loc[mask, outcome_col], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    n = int(vals.shape[0])
    if n == 0:
        return {"events": 0, "mean_bps": math.nan, "hit_rate": math.nan, "median_bps": math.nan, "p10_bps": math.nan}
    return {
        "events": n,
        "mean_bps": float(vals.mean()),
        "hit_rate": float((vals > 0).mean()),
        "median_bps": float(vals.median()),
        "p10_bps": float(vals.quantile(0.10)),
    }


def evaluate_candidate(df: pd.DataFrame, mask: np.ndarray, side: str) -> Dict[str, Any]:
    outcome_col = "future_long_bps" if side == "LONG" else "future_short_bps"
    result = {}
    overall = evaluate_mask(df, mask, outcome_col)
    for k, v in overall.items():
        result[k] = v
    for fold in ["F1_OLD", "F2_MID", "F3_LATE", "F4_RECENT"]:
        fm = mask & (df["fold"].to_numpy(dtype=object) == fold)
        ev = evaluate_mask(df, fm, outcome_col)
        result[f"{fold}_events"] = ev["events"]
        result[f"{fold}_mean_bps"] = ev["mean_bps"]
        result[f"{fold}_hit_rate"] = ev["hit_rate"]
    for session in ["ASIA", "LONDON", "NY", "LATE_US"]:
        sm = mask & (df["session"].to_numpy(dtype=object) == session)
        ev = evaluate_mask(df, sm, outcome_col)
        result[f"session_{session}_events"] = ev["events"]
        result[f"session_{session}_mean_bps"] = ev["mean_bps"]
    return result


def passes_candidate(row: Dict[str, Any], min_events: int, min_mean_bps: float, min_hit_rate: float, min_recent_mean_bps: float) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    def f(name: str, default: float = math.nan) -> float:
        try:
            return float(row.get(name, default))
        except Exception:
            return default
    if int(row.get("events") or 0) < min_events:
        reasons.append("events_lt_min")
    if f("mean_bps") < min_mean_bps:
        reasons.append("overall_mean_lt_min")
    if f("hit_rate") < min_hit_rate:
        reasons.append("overall_hit_lt_min")
    # Require at least three chronological folds to have positive mean.
    positive_folds = 0
    for fold in ["F1_OLD", "F2_MID", "F3_LATE", "F4_RECENT"]:
        if f(f"{fold}_mean_bps") > 0 and int(row.get(f"{fold}_events") or 0) >= max(5, min_events // 10):
            positive_folds += 1
    if positive_folds < 3:
        reasons.append("positive_folds_lt_3")
    if f("F4_RECENT_mean_bps") < min_recent_mean_bps:
        reasons.append("recent_mean_lt_min")
    # Avoid candidates that only work in one session.
    positive_sessions = 0
    for sess in ["ASIA", "LONDON", "NY", "LATE_US"]:
        if f(f"session_{sess}_mean_bps") > 0 and int(row.get(f"session_{sess}_events") or 0) >= max(5, min_events // 20):
            positive_sessions += 1
    if positive_sessions < 2:
        reasons.append("positive_sessions_lt_2")
    return (len(reasons) == 0), reasons


def scan_candidates(
    df: pd.DataFrame,
    supported_sides: Sequence[str],
    min_events: int,
    min_mean_bps: float,
    min_hit_rate: float,
    min_recent_mean_bps: float,
    max_pairs: int = 20000,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    features = valid_feature_columns(df)
    base_df = df.dropna(subset=features + ["future_long_bps", "future_short_bps"]).copy()
    if base_df.empty:
        return [], [], []
    quantiles = [0.35, 0.50, 0.65]
    conditions = build_conditions(base_df, features, quantiles)
    feature_arrays = {c: pd.to_numeric(base_df[c], errors="coerce").to_numpy(dtype=float) for c in features}
    cond_masks: List[Tuple[Condition, np.ndarray]] = []
    for cond in conditions:
        arr = feature_arrays[cond.feature]
        mask = cond.mask(arr) & np.isfinite(arr)
        if int(mask.sum()) >= min_events:
            cond_masks.append((cond, mask))

    pairs: List[Tuple[Tuple[Condition, ...], np.ndarray]] = []
    # Singles are included, then two-feature combinations. Avoid combining same feature with itself.
    for cond, mask in cond_masks:
        pairs.append(((cond,), mask))
    pair_count = 0
    for i, (c1, m1) in enumerate(cond_masks):
        for c2, m2 in cond_masks[i + 1:]:
            if c1.feature == c2.feature:
                continue
            mask = m1 & m2
            if int(mask.sum()) >= min_events:
                pairs.append(((c1, c2), mask))
                pair_count += 1
                if pair_count >= max_pairs:
                    break
        if pair_count >= max_pairs:
            break

    rows: List[Dict[str, Any]] = []
    shortlist: List[Dict[str, Any]] = []
    active: List[Dict[str, Any]] = []
    latest = base_df.iloc[-1]
    latest_time = str(latest.get("utc_time"))
    for side in ["LONG", "SHORT"]:
        for cond_tuple, mask in pairs:
            rule_id = f"D163_{side}_" + "__".join(c.label for c in cond_tuple)
            metrics = evaluate_candidate(base_df, mask, side)
            macro_alignment = "MACRO_SUPPORTED_SIDE" if side in supported_sides else "MACRO_CONFLICTED_SIDE"
            row: Dict[str, Any] = {
                "rule_id": rule_id,
                "side": side,
                "macro_alignment": macro_alignment,
                "condition_count": len(cond_tuple),
                "conditions_json": json.dumps([c.as_dict() for c in cond_tuple], ensure_ascii=False),
                "latest_feature_time_utc": latest_time,
            }
            row.update(metrics)
            ok, reasons = passes_candidate(row, min_events, min_mean_bps, min_hit_rate, min_recent_mean_bps)
            row["pass"] = bool(ok)
            row["fail_reasons"] = ";".join(reasons)
            current_active = True
            for c in cond_tuple:
                val = latest.get(c.feature, math.nan)
                if not np.isfinite(float(val)):
                    current_active = False
                    break
                if c.op == "GEQ" and not (float(val) >= c.threshold):
                    current_active = False
                    break
                if c.op == "LEQ" and not (float(val) <= c.threshold):
                    current_active = False
                    break
            row["current_active"] = bool(current_active)
            rows.append(row)
            if ok and macro_alignment == "MACRO_SUPPORTED_SIDE":
                shortlist.append(row)
                if current_active:
                    active.append(row)

    def sort_key(r: Dict[str, Any]) -> Tuple[float, float, int]:
        return (float(r.get("F4_RECENT_mean_bps") or -9999), float(r.get("mean_bps") or -9999), int(r.get("events") or 0))
    rows.sort(key=sort_key, reverse=True)
    shortlist.sort(key=sort_key, reverse=True)
    active.sort(key=sort_key, reverse=True)
    return rows, shortlist, active


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Stage163 macro-supported side discovery")
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--bars-m5", default=DEFAULT_BARS)
    ap.add_argument("--stage161-summary", default=DEFAULT_STAGE161)
    ap.add_argument("--timestamp-shift-hours", type=float, default=-3.0)
    ap.add_argument("--horizon-hours", type=float, default=4.0)
    ap.add_argument("--min-events", type=int, default=100)
    ap.add_argument("--min-mean-bps", type=float, default=1.5)
    ap.add_argument("--min-hit-rate", type=float, default=0.515)
    ap.add_argument("--min-recent-mean-bps", type=float, default=1.0)
    ap.add_argument("--out", default="reports/stage163_macro_supported_side_discovery")
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    bars_path = Path(args.bars_m5).expanduser().resolve()
    stage161_path = Path(args.stage161_summary)
    if not stage161_path.is_absolute():
        stage161_path = root / stage161_path
    out_dir = root / args.out
    ensure_dir(out_dir)

    summary: Dict[str, Any] = {
        "stage": STAGE,
        "generated_utc": utc_now(),
        "root": str(root),
        "bars_m5": str(bars_path),
        "stage161_summary": str(stage161_path),
        "order_routing_allowed": False,
        "demo_release_allowed": False,
    }
    try:
        stage161 = read_json(stage161_path)
        supported_sides, pressure, macro_note = macro_supported_sides(stage161)
        horizon_bars = max(1, int(round(float(args.horizon_hours) * 12)))
        bars = load_bars(bars_path, timestamp_shift_hours=float(args.timestamp_shift_hours))
        feat = compute_features(bars, horizon_bars=horizon_bars)
        rows, shortlist, active = scan_candidates(
            feat,
            supported_sides=supported_sides,
            min_events=int(args.min_events),
            min_mean_bps=float(args.min_mean_bps),
            min_hit_rate=float(args.min_hit_rate),
            min_recent_mean_bps=float(args.min_recent_mean_bps),
        )
        scores_path = out_dir / "stage163_macro_supported_side_candidate_scores.csv"
        shortlist_path = out_dir / "stage163_macro_supported_side_shortlist.csv"
        active_path = out_dir / "stage163_macro_supported_side_current_active.csv"
        context_path = out_dir / "stage163_macro_supported_side_context.json"
        summary_path = out_dir / "stage163_macro_supported_side_discovery_summary.json"
        write_rows_csv(scores_path, rows)
        write_rows_csv(shortlist_path, shortlist[:200])
        write_rows_csv(active_path, active[:200])
        context = {
            "stage161_macro_context": stage161.get("macro_context") or {},
            "stage161_decision": stage161.get("decision"),
            "stage161_macro_label_counts": stage161.get("macro_label_counts") or {},
            "macro_pressure": pressure,
            "supported_sides": supported_sides,
            "macro_note": macro_note,
            "horizon_hours": args.horizon_hours,
            "timestamp_shift_hours": args.timestamp_shift_hours,
        }
        write_json(context_path, context)

        side_counts: Dict[str, int] = {}
        align_counts: Dict[str, int] = {}
        for r in shortlist:
            side_counts[str(r.get("side"))] = side_counts.get(str(r.get("side")), 0) + 1
            align_counts[str(r.get("macro_alignment"))] = align_counts.get(str(r.get("macro_alignment")), 0) + 1
        if shortlist:
            decision = "STAGE163_MACRO_SUPPORTED_SIDE_SHORTLIST_READY_NO_DEMO_UNTIL_EXECUTION_SIDE_REVIEW"
            recommended = "REVIEW_MACRO_SUPPORTED_SIDE_SHORTLIST; DO_NOT_RELEASE_ORDERS_WITHOUT_SELL/BUY_EXECUTION_AND_GOVERNANCE_REVIEW"
            severity = "WARN"
        else:
            decision = "STAGE163_NO_MACRO_SUPPORTED_SIDE_CANDIDATE_KEEP_FREEZE"
            recommended = "KEEP_STAGE157_FREEZE_AND_WAIT_FOR_REGIME_CHANGE_OR_REBUILD_THESIS"
            severity = "HIGH"
        summary.update({
            "status": "STAGE163_COMPLETE_MACRO_SUPPORTED_SIDE_DISCOVERY_READY",
            "decision": decision,
            "severity": severity,
            "recommended_action": recommended,
            "bar_count": int(len(bars)),
            "feature_row_count": int(len(feat.dropna(subset=["future_long_bps", "future_short_bps"]))),
            "latest_bar_utc": str(bars["utc_time"].max()),
            "macro_pressure": pressure,
            "macro_supported_sides": supported_sides,
            "macro_note": macro_note,
            "candidate_score_count": len(rows),
            "macro_supported_shortlist_count": len(shortlist),
            "current_active_macro_supported_count": len(active),
            "shortlist_side_counts": side_counts,
            "shortlist_alignment_counts": align_counts,
            "top_shortlist_rule_ids": [r.get("rule_id") for r in shortlist[:10]],
            "outputs": {
                "summary_json": str(summary_path),
                "candidate_scores_csv": str(scores_path),
                "shortlist_csv": str(shortlist_path),
                "current_active_csv": str(active_path),
                "context_json": str(context_path),
            },
            "next": [
                "Keep Stage157 freeze active.",
                "If only SHORT candidates survive, do not use the current long-only demo path.",
                "A separate execution-side patch is required before any SELL demo order can be considered.",
                "If no macro-supported candidates survive, wait for regime change or rebuild the thesis at a higher timeframe.",
            ],
        })
        write_json(summary_path, summary)
        return 0
    except Exception as exc:
        summary.update({
            "status": "STAGE163_FAILED_ARTIFACTS_WRITTEN",
            "decision": "STAGE163_RUN_FAILED_KEEP_FREEZE",
            "severity": "HIGH",
            "recommended_action": "KEEP_STAGE157_FREEZE_AND_INSPECT_ERROR",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        })
        write_json(out_dir / "stage163_macro_supported_side_discovery_summary.json", summary)
        print(f"Stage163 failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
