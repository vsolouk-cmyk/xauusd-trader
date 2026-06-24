#!/usr/bin/env python3
"""
Stage45C_FEED_AND_TRANSACTION_COST_REALISM_AUDIT

Purpose
-------
Audit the broker/feed and transaction-cost realism of the local XAUUSD MT5
bar store before any further candle-only thesis scans.

This script is diagnostic-only:
- no signal generation
- no promotion
- no EA / paper-live / live authorization

It reads the SQLite bars table, detects schema aliases, loads requested timeframes,
profiles spread and gap quality, estimates spread cost in bps, and compares observed
cost realism with Stage45 recalibration needs when Stage45 output exists.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


STAGE = "Stage45C_FEED_AND_TRANSACTION_COST_REALISM_AUDIT"
NO_GO = "NO_GO"

TIMEFRAME_MINUTES = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
}

TIMEFRAME_ALIASES = {
    "1M": "M1", "M1": "M1", "1MIN": "M1", "1MINUTE": "M1", "60S": "M1",
    "5M": "M5", "M5": "M5", "5MIN": "M5", "5MINUTE": "M5",
    "15M": "M15", "M15": "M15", "15MIN": "M15", "15MINUTE": "M15",
    "30M": "M30", "M30": "M30", "30MIN": "M30", "30MINUTE": "M30",
    "1H": "H1", "H1": "H1", "60M": "H1", "60MIN": "H1", "1HR": "H1", "1HOUR": "H1",
    "4H": "H4", "H4": "H4", "240M": "H4",
    "1D": "D1", "D1": "D1", "DAILY": "D1",
}

ALIASES = {
    "timestamp": ["utc_time", "timestamp", "time", "datetime", "date", "source_time"],
    "open": ["open", "o"],
    "high": ["high", "h"],
    "low": ["low", "l"],
    "close": ["close", "c"],
    "spread": ["spread", "spread_points", "mt5_spread", "ask_bid_spread"],
    "volume": ["volume", "tick_volume", "real_volume", "vol"],
    "source": ["source", "feed", "broker"],
    "symbol": ["symbol", "instrument", "ticker"],
    "timeframe": ["timeframe", "tf", "interval"],
}


def _norm_compact(value: Any) -> str:
    return "".join(ch for ch in str(value).strip().casefold() if ch.isalnum())


def _norm_tf(value: Any) -> str:
    key = _norm_compact(value).upper()
    return TIMEFRAME_ALIASES.get(key, key)


def _q(series: pd.Series, probs: Sequence[float]) -> Dict[str, Optional[float]]:
    s = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if s.empty:
        return {f"p{int(p*100):02d}": None for p in probs}
    out: Dict[str, Optional[float]] = {}
    for p in probs:
        out[f"p{int(p*100):02d}"] = float(np.nanquantile(s.to_numpy(dtype=float), p))
    return out


def _profile(series: pd.Series) -> Dict[str, Optional[float]]:
    s = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if s.empty:
        return {"n": 0, "min": None, "p10": None, "median": None, "p90": None, "p95": None, "p99": None, "max": None, "mean": None}
    arr = s.to_numpy(dtype=float)
    return {
        "n": int(arr.size),
        "min": float(np.nanmin(arr)),
        "p10": float(np.nanquantile(arr, 0.10)),
        "median": float(np.nanmedian(arr)),
        "p90": float(np.nanquantile(arr, 0.90)),
        "p95": float(np.nanquantile(arr, 0.95)),
        "p99": float(np.nanquantile(arr, 0.99)),
        "max": float(np.nanmax(arr)),
        "mean": float(np.nanmean(arr)),
    }


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return None
        return float(x)
    except Exception:
        return None


def _detect_columns(cols: Sequence[str]) -> Dict[str, Optional[str]]:
    lower_to_actual = {c.lower(): c for c in cols}
    detected: Dict[str, Optional[str]] = {}
    for role, names in ALIASES.items():
        detected[role] = None
        for name in names:
            if name.lower() in lower_to_actual:
                detected[role] = lower_to_actual[name.lower()]
                break
    required = ["timestamp", "open", "high", "low", "close"]
    missing = [role for role in required if detected.get(role) is None]
    if missing:
        raise RuntimeError(f"Missing required columns: {missing}; available={list(cols)}")
    return detected


def _sqlite_columns(con: sqlite3.Connection, table: str) -> List[str]:
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    if not rows:
        raise RuntimeError(f"Table not found or empty schema: {table!r}")
    return [str(r[1]) for r in rows]


def _available_dimensions(con: sqlite3.Connection, table: str, detected: Dict[str, Optional[str]]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for role in ["source", "symbol", "timeframe"]:
        col = detected.get(role)
        if not col:
            continue
        q = f"SELECT {col} AS value, COUNT(*) AS n FROM {table} GROUP BY {col} ORDER BY n DESC LIMIT 20"
        out[role] = [{"value": r[0], "n": int(r[1])} for r in con.execute(q).fetchall()]
    return out


def _read_bars(
    db_path: Path,
    table: str,
    source: str,
    symbol: str,
    timeframe: str,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")
    con = sqlite3.connect(str(db_path))
    try:
        cols = _sqlite_columns(con, table)
        detected = _detect_columns(cols)
        available = _available_dimensions(con, table, detected)
        select_cols = [c for c in detected.values() if c]
        # Preserve order and uniqueness.
        select_cols = list(dict.fromkeys(select_cols))
        q = f"SELECT {', '.join(select_cols)} FROM {table}"
        raw = pd.read_sql_query(q, con)
    finally:
        con.close()

    rename = {v: k for k, v in detected.items() if v}
    df = raw.rename(columns=rename)
    pre_filter_rows = int(len(df))

    filter_debug: Dict[str, Any] = {
        "requested_source": source,
        "requested_symbol": symbol,
        "requested_timeframe": timeframe,
        "pre_filter_rows": pre_filter_rows,
        "normalization": "source/symbol use strip+casefold+compact; timeframe aliases such as 15m/M15/15MIN -> M15",
    }

    if "source" in df.columns and source:
        src_norm = _norm_compact(source)
        exact = df["source"].astype(str).str.strip().str.casefold() == str(source).strip().casefold()
        compact = df["source"].map(_norm_compact) == src_norm
        filter_debug["source_exact_matches"] = int(exact.sum())
        filter_debug["source_compact_matches"] = int(compact.sum())
        df = df[compact]

    if "symbol" in df.columns and symbol:
        sym_norm = _norm_compact(symbol)
        exact = df["symbol"].astype(str).str.strip().str.casefold() == str(symbol).strip().casefold()
        compact = df["symbol"].map(_norm_compact) == sym_norm
        filter_debug["symbol_exact_matches"] = int(exact.sum())
        filter_debug["symbol_compact_matches"] = int(compact.sum())
        df = df[compact]

    tf_norm = _norm_tf(timeframe)
    if "timeframe" in df.columns and timeframe:
        tf_matches = df["timeframe"].map(_norm_tf) == tf_norm
        filter_debug["requested_timeframe_normalized"] = tf_norm
        filter_debug["timeframe_alias_matches"] = int(tf_matches.sum())
        df = df[tf_matches]

    filter_debug["post_filter_rows_before_ohlc_clean"] = int(len(df))
    if df.empty:
        raise RuntimeError(
            "No bars loaded after filtering. Diagnostic="
            + json.dumps({"available_dimensions_top20": available, "filter_debug": filter_debug}, ensure_ascii=False)
        )

    for col in ["open", "high", "low", "close", "spread", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp", "open", "high", "low", "close"]).copy()
    df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"]).reset_index(drop=True)
    filter_debug["post_filter_rows_after_ohlc_clean"] = int(len(df))

    meta = {
        "db_path": str(db_path),
        "table": table,
        "columns_detected": detected,
        "available_dimensions_top20": available,
        "filter_debug": filter_debug,
        "timeframe_normalized": tf_norm,
        "timeframe_minutes": TIMEFRAME_MINUTES.get(tf_norm),
        "loaded_rows": int(len(df)),
        "loaded_start": df["timestamp"].min().isoformat() if not df.empty else None,
        "loaded_end": df["timestamp"].max().isoformat() if not df.empty else None,
    }
    return df, meta


def _tag_session(hour: int) -> str:
    if 0 <= hour < 7:
        return "ASIA_00_07"
    if 7 <= hour < 12:
        return "LONDON_07_12"
    if 12 <= hour < 16:
        return "LONDON_NY_OVERLAP_12_16"
    if 16 <= hour < 21:
        return "NY_16_21"
    return "ROLLOVER_OTHER_21_24"


def _infer_spread(df: pd.DataFrame, point_size: float, spread_mode: str) -> Dict[str, Any]:
    if "spread" not in df.columns:
        return {"has_spread": False, "selected_mode": None, "error": "spread column not found"}
    s = pd.to_numeric(df["spread"], errors="coerce").replace([np.inf, -np.inf], np.nan)
    valid = s.dropna()
    if valid.empty:
        return {"has_spread": True, "selected_mode": None, "error": "spread column exists but has no numeric values"}

    mid = ((df["high"] + df["low"] + df["close"] * 2.0) / 4.0).replace(0, np.nan)
    candidates: Dict[str, pd.Series] = {
        "raw_price_units": s,
        f"points_x_{point_size:g}": s * float(point_size),
        "points_x_0.001": s * 0.001,
        "points_x_0.01": s * 0.01,
        "points_x_0.1": s * 0.1,
    }
    profiles: Dict[str, Any] = {}
    for name, spread_price in candidates.items():
        bps = (spread_price / mid) * 10000.0
        profiles[name] = _profile(bps)

    if spread_mode == "price":
        selected = "raw_price_units"
    elif spread_mode == "points":
        selected = f"points_x_{point_size:g}"
    else:
        # MT5 spread often stores points. If raw median is implausibly wide in bps,
        # prefer configured point conversion. Otherwise use raw price units.
        raw_med = profiles.get("raw_price_units", {}).get("median")
        point_med = profiles.get(f"points_x_{point_size:g}", {}).get("median")
        if raw_med is not None and raw_med > 25 and point_med is not None:
            selected = f"points_x_{point_size:g}"
        elif raw_med is not None and raw_med <= 25:
            selected = "raw_price_units"
        else:
            selected = f"points_x_{point_size:g}"

    spread_price = candidates[selected]
    df["spread_price_selected"] = spread_price
    df["spread_bps_selected"] = (spread_price / mid) * 10000.0
    return {
        "has_spread": True,
        "spread_raw_profile": _profile(s),
        "conversion_profiles_bps": profiles,
        "selected_mode": selected,
        "selected_spread_bps_profile": _profile(df["spread_bps_selected"]),
    }


def _bar_quality(df: pd.DataFrame, tf_minutes: Optional[int]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    out["rows"] = int(len(df))
    out["start"] = df["timestamp"].min().isoformat() if len(df) else None
    out["end"] = df["timestamp"].max().isoformat() if len(df) else None
    if tf_minutes and len(df) > 1:
        delta_min = df["timestamp"].diff().dt.total_seconds() / 60.0
        out["delta_minutes_profile"] = _profile(delta_min)
        expected = float(tf_minutes)
        out["gap_count_gt_1p5x_expected"] = int((delta_min > expected * 1.5).sum())
        out["large_gap_count_gt_6x_expected"] = int((delta_min > expected * 6.0).sum())
        out["duplicate_timestamp_count"] = int(df["timestamp"].duplicated().sum())
    return out


def _timeframe_audit(df: pd.DataFrame, meta: Dict[str, Any], point_size: float, spread_mode: str, slip_scenarios: List[float]) -> Tuple[Dict[str, Any], pd.DataFrame, pd.DataFrame]:
    df = df.copy()
    tf = str(meta["timeframe_normalized"])
    tf_minutes = meta.get("timeframe_minutes")
    df["hour_utc"] = df["timestamp"].dt.hour
    df["weekday"] = df["timestamp"].dt.day_name()
    df["year"] = df["timestamp"].dt.year
    df["quarter"] = df["timestamp"].dt.tz_convert(None).dt.to_period("Q").astype(str)
    df["session"] = df["hour_utc"].map(_tag_session)
    df["bar_range_bps"] = ((df["high"] - df["low"]) / df["close"].replace(0, np.nan)) * 10000.0
    df["abs_close_ret_bps"] = (df["close"].pct_change().abs() * 10000.0)

    spread_info = _infer_spread(df, point_size=point_size, spread_mode=spread_mode)

    # Group outputs.
    group_rows: List[Dict[str, Any]] = []
    if spread_info.get("has_spread") and "spread_bps_selected" in df.columns:
        for group_name, col in [("session", "session"), ("hour_utc", "hour_utc"), ("weekday", "weekday"), ("quarter", "quarter")]:
            for key, g in df.groupby(col, dropna=False):
                prof = _profile(g["spread_bps_selected"])
                group_rows.append({"timeframe": tf, "group": group_name, "key": str(key), **prof})
    group_df = pd.DataFrame(group_rows)

    cost_rows: List[Dict[str, Any]] = []
    selected_spread_profile = spread_info.get("selected_spread_bps_profile", {}) or {}
    for q_name in ["median", "p90", "p95", "p99"]:
        spread_q = selected_spread_profile.get(q_name)
        if spread_q is None:
            continue
        for slip in slip_scenarios:
            cost_rows.append({
                "timeframe": tf,
                "spread_quantile": q_name,
                "spread_bps": float(spread_q),
                "assumed_extra_slip_bps": float(slip),
                "estimated_total_cost_bps": float(spread_q) + float(slip),
            })
    cost_df = pd.DataFrame(cost_rows)

    bar_range_prof = _profile(df["bar_range_bps"])
    abs_ret_prof = _profile(df["abs_close_ret_bps"])
    selected_median_spread = selected_spread_profile.get("median")
    range_median = bar_range_prof.get("median")
    spread_to_range = None
    if selected_median_spread is not None and range_median not in (None, 0):
        spread_to_range = float(selected_median_spread) / float(range_median)

    audit = {
        "timeframe": tf,
        "timeframe_minutes": tf_minutes,
        "data_quality": _bar_quality(df, tf_minutes),
        "spread_info": spread_info,
        "bar_range_bps_profile": bar_range_prof,
        "abs_close_ret_bps_profile": abs_ret_prof,
        "median_spread_to_median_bar_range_ratio": spread_to_range,
        "estimated_cost_scenarios": cost_rows,
    }
    return audit, group_df, cost_df


def _load_stage45_reference(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"exists": True, "path": str(path), "error": str(exc)}
    diag = data.get("diagnostic", {})
    decision = data.get("decision", {})
    cost_needed = diag.get("cost_needed_profile", {})
    scenarios = diag.get("scenario_analysis", [])
    return {
        "exists": True,
        "path": str(path),
        "recommended_next_stage": decision.get("recommended_next_stage") or data.get("next_allowed_step"),
        "rationale": decision.get("rationale", []),
        "required_uniform_bps_improvement_profile": cost_needed.get("required_uniform_bps_improvement_profile"),
        "scenario_pass_counts": [
            {
                "name": (s.get("scenario") or {}).get("name"),
                "cost_saving_bps": (s.get("scenario") or {}).get("cost_saving_bps"),
                "pass_count": s.get("pass_count"),
                "pass_by_stage": s.get("pass_by_stage"),
            }
            for s in scenarios
        ],
    }


def _decision(audits: List[Dict[str, Any]], stage45_ref: Dict[str, Any]) -> Dict[str, Any]:
    # The audit never promotes. It selects the next research direction.
    spread_available = any(a.get("spread_info", {}).get("has_spread") and a.get("spread_info", {}).get("selected_mode") for a in audits)
    p90_costs: List[float] = []
    p95_costs: List[float] = []
    spread_range_ratios: List[float] = []
    for a in audits:
        prof = a.get("spread_info", {}).get("selected_spread_bps_profile", {}) or {}
        if prof.get("p90") is not None:
            p90_costs.append(float(prof["p90"]))
        if prof.get("p95") is not None:
            p95_costs.append(float(prof["p95"]))
        ratio = a.get("median_spread_to_median_bar_range_ratio")
        if ratio is not None and math.isfinite(float(ratio)):
            spread_range_ratios.append(float(ratio))

    required_prof = stage45_ref.get("required_uniform_bps_improvement_profile") or {}
    required_min = _safe_float(required_prof.get("min"))
    required_p10 = _safe_float(required_prof.get("p10"))

    max_p90_spread = max(p90_costs) if p90_costs else None
    max_p95_spread = max(p95_costs) if p95_costs else None
    max_spread_range_ratio = max(spread_range_ratios) if spread_range_ratios else None

    rationale: List[str] = []
    next_stage = "Stage45B_EXTERNAL_CONTEXT_AND_REFERENCE_FEED_DECISION"
    status = "COST_REALISM_AUDITED_NO_PROMOTION"

    if not spread_available:
        next_stage = "Stage45C2_COLLECT_BID_ASK_OR_REPAIR_SPREAD_DATA"
        status = "SPREAD_DATA_NOT_USABLE"
        rationale.append("No usable spread column was found; broker/feed transaction-cost realism cannot be trusted yet.")
    else:
        rationale.append("Spread column was detected and converted to bps for broker/feed cost profiling.")
        if max_p90_spread is not None:
            rationale.append(f"Worst timeframe selected spread p90 is approximately {max_p90_spread:.3f} bps before extra slippage.")
        if max_spread_range_ratio is not None:
            rationale.append(f"Worst timeframe median spread / median bar range ratio is approximately {max_spread_range_ratio:.3f}.")

        # If observed spread is small but Stage45 still needs huge improvement, the missing ingredient is likely context/reference feed.
        if required_min is not None and max_p90_spread is not None:
            if max_p90_spread + 16.0 <= required_min:
                next_stage = "Stage45B_EXTERNAL_CONTEXT_AND_REFERENCE_FEED_DECISION"
                rationale.append("Observed spread alone is not enough to explain the Stage45 failure; external context/reference feed should be evaluated before more scans.")
            elif max_p90_spread + 8.0 > required_p10 if required_p10 is not None else False:
                next_stage = "Stage45C2_BROKER_COST_REDUCTION_OR_FEED_COMPARISON"
                rationale.append("Observed spread plus realistic slippage is large relative to the cost improvement needed; broker/feed comparison is required.")
            else:
                next_stage = "Stage45B_EXTERNAL_CONTEXT_AND_REFERENCE_FEED_DECISION"
                rationale.append("Cost realism is not decisive enough by itself; external context remains the next evidence-based branch.")
        else:
            next_stage = "Stage45B_EXTERNAL_CONTEXT_AND_REFERENCE_FEED_DECISION"
            rationale.append("Stage45 cost-needed reference was unavailable; after spread profiling, move to external/reference context decision.")

    return {
        "status": status,
        "promotion": NO_GO,
        "EA": NO_GO,
        "paper_live": NO_GO,
        "live": NO_GO,
        "recommended_next_stage": next_stage,
        "rationale": rationale,
        "not_allowed": [
            "candidate_rescue_from_stage41_42_43",
            "post_hoc_filtering_of_bad_hours_months_years_quarters_or_spread_buckets",
            "EA_paper_live_live_from_archived_rows",
            "ML_before_robust_cost_aware_baseline",
        ],
    }


def _write_md(summary: Dict[str, Any], path: Path) -> None:
    lines: List[str] = []
    lines.append(f"# {STAGE}")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    dec = summary.get("decision", {})
    lines.append(f"promotion = {summary.get('promotion')}")
    lines.append(f"EA = {summary.get('EA')}")
    lines.append(f"paper_live = {summary.get('paper_live')}")
    lines.append(f"live = {summary.get('live')}")
    lines.append(f"recommended_next_stage = {dec.get('recommended_next_stage')}")
    lines.append("```")
    lines.append("")
    lines.append("Stage45C is a broker/feed and transaction-cost realism audit only. It does not create trading signals, does not shortlist candidates, and cannot promote any prior row.")
    lines.append("")

    lines.append("## Inputs")
    lines.append("")
    lines.append("```text")
    lines.append(f"db_path: {summary.get('settings', {}).get('db_path')}")
    lines.append(f"table: {summary.get('settings', {}).get('table')}")
    lines.append(f"source: {summary.get('settings', {}).get('source')}")
    lines.append(f"symbol: {summary.get('settings', {}).get('symbol')}")
    lines.append(f"timeframes: {', '.join(summary.get('settings', {}).get('timeframes', []))}")
    lines.append("```")
    lines.append("")

    lines.append("## Per-timeframe spread and quality profile")
    lines.append("")
    lines.append("| timeframe | rows | start | end | selected_spread_mode | spread_median_bps | spread_p90_bps | spread_p95_bps | spread_p99_bps | median_bar_range_bps | spread/range median | gaps_gt_1p5x |")
    lines.append("| :-- | --: | :-- | :-- | :-- | --: | --: | --: | --: | --: | --: | --: |")
    for audit in summary.get("audits", []):
        q = audit.get("data_quality", {})
        sp = audit.get("spread_info", {})
        prof = sp.get("selected_spread_bps_profile", {}) or {}
        br = audit.get("bar_range_bps_profile", {}) or {}
        lines.append(
            "| {tf} | {rows} | {start} | {end} | {mode} | {med} | {p90} | {p95} | {p99} | {brmed} | {ratio} | {gaps} |".format(
                tf=audit.get("timeframe"),
                rows=q.get("rows"),
                start=q.get("start"),
                end=q.get("end"),
                mode=sp.get("selected_mode"),
                med=_fmt(prof.get("median")),
                p90=_fmt(prof.get("p90")),
                p95=_fmt(prof.get("p95")),
                p99=_fmt(prof.get("p99")),
                brmed=_fmt(br.get("median")),
                ratio=_fmt(audit.get("median_spread_to_median_bar_range_ratio")),
                gaps=q.get("gap_count_gt_1p5x_expected"),
            )
        )
    lines.append("")

    lines.append("## Stage45 reference")
    lines.append("")
    ref = summary.get("stage45_reference", {})
    lines.append("```json")
    lines.append(json.dumps(ref, ensure_ascii=False, indent=2)[:4000])
    lines.append("```")
    lines.append("")

    lines.append("## Decision rationale")
    lines.append("")
    lines.append("```text")
    for r in dec.get("rationale", []):
        lines.append(f"- {r}")
    lines.append("```")
    lines.append("")

    lines.append("## Not allowed")
    lines.append("")
    lines.append("```text")
    for r in dec.get("not_allowed", []):
        lines.append(f"- {r}")
    lines.append("```")
    lines.append("")
    lines.append("## Anti-overfit note")
    lines.append("")
    lines.append("Do not use this audit to rescue Stage41/42/43 rows by selecting favorable spread buckets after seeing the result. The audit can only choose the next evidence-based research direction.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fmt(x: Any) -> str:
    if x is None:
        return ""
    try:
        return f"{float(x):.3f}"
    except Exception:
        return str(x)


def _parse_timeframes(value: str) -> List[str]:
    items = [v.strip() for v in value.split(",") if v.strip()]
    return [_norm_tf(v) for v in items]


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=STAGE)
    p.add_argument("--db", default="data/local/xauusd_local_store.sqlite")
    p.add_argument("--table", default="bars")
    p.add_argument("--source", default="amarkets_mt5")
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--timeframes", default="M15,H1,M5", help="Comma-separated timeframes. Use aliases like 15m,H1,M5.")
    p.add_argument("--out-dir", default="reports/stage45c")
    p.add_argument("--stage45-summary", default="reports/stage45/stage45_cost_aware_baseline_recalibration_summary.json")
    p.add_argument("--spread-mode", choices=["auto", "price", "points"], default="auto")
    p.add_argument("--point-size", type=float, default=0.01, help="MT5 point size for spread conversion when spread is stored in points.")
    p.add_argument("--slip-scenarios", default="0,4,8,16", help="Comma-separated extra slippage bps scenarios.")
    p.add_argument("--print-summary", action="store_true")
    return p


def run(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = Path(args.db)
    timeframes = _parse_timeframes(args.timeframes)
    slip_scenarios = [float(x.strip()) for x in str(args.slip_scenarios).split(",") if x.strip()]

    audits: List[Dict[str, Any]] = []
    group_frames: List[pd.DataFrame] = []
    cost_frames: List[pd.DataFrame] = []
    errors: List[Dict[str, Any]] = []

    for tf in timeframes:
        try:
            df, meta = _read_bars(db_path, args.table, args.source, args.symbol, tf)
            audit, group_df, cost_df = _timeframe_audit(df, meta, point_size=args.point_size, spread_mode=args.spread_mode, slip_scenarios=slip_scenarios)
            audit["load_meta"] = meta
            audits.append(audit)
            if not group_df.empty:
                group_frames.append(group_df)
            if not cost_df.empty:
                cost_frames.append(cost_df)
        except Exception as exc:
            errors.append({"timeframe": tf, "error": str(exc)})

    stage45_ref = _load_stage45_reference(Path(args.stage45_summary))
    decision = _decision(audits, stage45_ref)

    spread_by_group = pd.concat(group_frames, ignore_index=True) if group_frames else pd.DataFrame()
    cost_scenarios = pd.concat(cost_frames, ignore_index=True) if cost_frames else pd.DataFrame()

    if not spread_by_group.empty:
        spread_by_group.to_csv(out_dir / "stage45c_spread_by_group.csv", index=False)
    else:
        (out_dir / "stage45c_spread_by_group.csv").write_text("", encoding="utf-8")
    if not cost_scenarios.empty:
        cost_scenarios.to_csv(out_dir / "stage45c_estimated_cost_scenarios.csv", index=False)
    else:
        (out_dir / "stage45c_estimated_cost_scenarios.csv").write_text("", encoding="utf-8")

    summary = {
        "stage": STAGE,
        "settings": {
            "db_path": str(db_path),
            "table": args.table,
            "source": args.source,
            "symbol": args.symbol,
            "timeframes": timeframes,
            "spread_mode": args.spread_mode,
            "point_size": args.point_size,
            "slip_scenarios_bps": slip_scenarios,
        },
        "audits": audits,
        "stage45_reference": stage45_ref,
        "errors": errors,
        "decision": decision,
        "promotion": NO_GO,
        "EA": NO_GO,
        "paper_live": NO_GO,
        "live": NO_GO,
        "next_allowed_step": decision.get("recommended_next_stage"),
    }

    summary_path = out_dir / "stage45c_feed_transaction_cost_realism_audit_summary.json"
    md_path = out_dir / "stage45c_feed_transaction_cost_realism_audit.md"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_md(summary, md_path)

    if args.print_summary:
        compact = {
            "stage": STAGE,
            "timeframes_audited": [a.get("timeframe") for a in audits],
            "errors": errors,
            "recommended_next_stage": decision.get("recommended_next_stage"),
            "promotion": NO_GO,
            "EA": NO_GO,
            "paper_live": NO_GO,
            "live": NO_GO,
            "summary_path": str(summary_path),
            "md_path": str(md_path),
        }
        print(json.dumps(compact, ensure_ascii=False, indent=2))
    return 0 if audits else 2


if __name__ == "__main__":
    raise SystemExit(run(build_arg_parser().parse_args()))
