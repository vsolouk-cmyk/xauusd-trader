#!/usr/bin/env python3
"""Stage56 parallel alternative megascan for broker-real XAUUSD.

This is a research scanner only. It reads local AMarkets multitf SQLite data and
runs three alternative thesis families in one bounded batch. It does not connect
to a broker, does not place orders, and does not authorize promotion.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sqlite3
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

STAGE = "Stage56_PARALLEL_ALTERNATIVE_MEGASCAN_NO_PROMOTION"
NO_GO = {"promotion": "NO_GO", "EA": "NO_GO", "paper_live": "NO_GO", "live": "NO_GO"}
FAMILIES = [
    "ALT_A_PULLBACK_AFTER_SQUEEZE_FAILURE",
    "ALT_B_INTRADAY_TREND_PULLBACK_TO_M15_VALUE_AREA",
    "ALT_C_SESSION_RANGE_REVERSION_AFTER_EXHAUSTION",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default: Any = None) -> Any:
    if not path or not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def normalize_time_col(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["time_utc", "open", "high", "low", "close"]).sort_values("time_utc")
    return df.reset_index(drop=True)


def load_timeframe(db_path: Path, timeframe: str) -> pd.DataFrame:
    with sqlite3.connect(str(db_path)) as con:
        df = pd.read_sql_query(
            """
            SELECT time_utc, open, high, low, close, tick_volume, spread_cost_bps
            FROM amarkets_bars
            WHERE timeframe = ?
            ORDER BY time_utc
            """,
            con,
            params=(timeframe,),
        )
    if df.empty:
        return df
    for col in ["open", "high", "low", "close", "tick_volume", "spread_cost_bps"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return normalize_time_col(df)


def load_market_data(db_path: Path) -> Dict[str, pd.DataFrame]:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")
    data = {tf: load_timeframe(db_path, tf) for tf in ["M5", "M15", "M30", "H1"]}
    missing = [tf for tf, df in data.items() if df.empty]
    if missing:
        raise RuntimeError(f"Missing/empty timeframes in DB: {missing}")
    return data


def load_costs(cost_model_path: Optional[Path], config: Dict[str, Any]) -> Dict[str, float]:
    fallbacks = config.get("cost_model_fallbacks", {})
    stress = float(fallbacks.get("stress_cost_bps", 2.982003733153722))
    extreme = float(fallbacks.get("extreme_cost_bps", 3.0380209087577326))
    if cost_model_path and cost_model_path.exists():
        raw = read_json(cost_model_path, {}) or {}
        # Accept both flat Stage48F schema and nested cost blocks.
        for k in ["stress_cost_bps", "recommended_stress_cost_bps"]:
            if isinstance(raw.get(k), (int, float)):
                stress = float(raw[k])
        for k in ["extreme_cost_bps", "recommended_extreme_cost_bps"]:
            if isinstance(raw.get(k), (int, float)):
                extreme = float(raw[k])
        if isinstance(raw.get("costs"), dict):
            c = raw["costs"]
            if isinstance(c.get("stress_cost_bps"), (int, float)):
                stress = float(c["stress_cost_bps"])
            if isinstance(c.get("extreme_cost_bps"), (int, float)):
                extreme = float(c["extreme_cost_bps"])
    return {"stress_cost_bps": stress, "extreme_cost_bps": extreme}


def bps_return(entry: np.ndarray, exit_: np.ndarray, direction: np.ndarray) -> np.ndarray:
    return direction * ((exit_ - entry) / entry) * 10000.0


def asof_align(left: pd.DataFrame, right: pd.DataFrame, right_cols: List[str], suffix: str) -> pd.DataFrame:
    r = right[["time_utc"] + right_cols].sort_values("time_utc").copy()
    r = r.rename(columns={c: f"{c}_{suffix}" for c in right_cols})
    return pd.merge_asof(left.sort_values("time_utc"), r, on="time_utc", direction="backward")


def prepare_features(data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    m5 = data["M5"].copy()
    m15 = data["M15"].copy()
    m30 = data["M30"].copy()
    h1 = data["H1"].copy()

    for df in [m5, m15, m30, h1]:
        df["range_bps"] = ((df["high"] - df["low"]) / df["close"].replace(0, np.nan)) * 10000.0
        df["ret_bps"] = df["close"].pct_change() * 10000.0
        df["year"] = df["time_utc"].dt.year
        df["date"] = df["time_utc"].dt.date.astype(str)
        df["hour_utc"] = df["time_utc"].dt.hour

    for w in [16, 20, 32, 40, 48, 80]:
        if w <= len(m15):
            m15[f"sma_{w}"] = m15["close"].rolling(w, min_periods=max(5, w // 3)).mean()
        if w <= len(m30):
            m30[f"sma_{w}"] = m30["close"].rolling(w, min_periods=max(5, w // 3)).mean()

    # Precompute rolling quantiles for squeeze windows.
    for cw in [48, 96, 192]:
        for pct in [20, 30]:
            if cw <= len(m15):
                m15[f"range_q{pct}_cw{cw}"] = (
                    m15["range_bps"].rolling(cw, min_periods=max(10, cw // 4)).quantile(pct / 100.0).shift(1)
                )

    return {"M5": m5.reset_index(drop=True), "M15": m15.reset_index(drop=True), "M30": m30.reset_index(drop=True), "H1": h1.reset_index(drop=True)}


def next_m5_entries(signals: pd.DataFrame, m5: pd.DataFrame, horizon: int, stress_cost_bps: float) -> pd.DataFrame:
    if signals.empty:
        return pd.DataFrame()
    base = signals.sort_values("signal_time_utc").copy()
    base = base.rename(columns={"signal_time_utc": "time_utc"})
    m5_sorted = m5[["time_utc", "close", "spread_cost_bps"]].sort_values("time_utc").copy()
    entry = pd.merge_asof(base, m5_sorted, on="time_utc", direction="forward", allow_exact_matches=False)
    entry = entry.dropna(subset=["close"]).rename(columns={"time_utc": "signal_time_utc", "close": "entry_price", "spread_cost_bps": "entry_spread_cost_bps"})
    if entry.empty:
        return pd.DataFrame()
    # Find entry index and horizon exit index.
    m5_index = pd.Series(np.arange(len(m5_sorted)), index=m5_sorted["time_utc"].values)
    entry_times = entry["signal_time_utc"].values
    # signal_time_utc is actually the chosen m5 entry time after merge column handling above.
    # Re-merge to keep entry_time explicitly.
    tmp = base.sort_values("time_utc").copy()
    e2 = pd.merge_asof(tmp, m5_sorted.rename(columns={"time_utc": "entry_time_utc"}), left_on="time_utc", right_on="entry_time_utc", direction="forward", allow_exact_matches=False)
    e2 = e2.dropna(subset=["entry_time_utc", "close"]).rename(columns={"time_utc": "signal_time_utc", "close": "entry_price", "spread_cost_bps": "entry_spread_cost_bps"})
    if e2.empty:
        return pd.DataFrame()
    pos = np.searchsorted(m5_sorted["time_utc"].values, e2["entry_time_utc"].values)
    exit_pos = pos + int(horizon)
    valid = exit_pos < len(m5_sorted)
    e2 = e2.loc[valid].copy()
    exit_pos = exit_pos[valid]
    if e2.empty:
        return pd.DataFrame()
    e2["exit_time_utc"] = m5_sorted.iloc[exit_pos]["time_utc"].values
    e2["exit_price"] = m5_sorted.iloc[exit_pos]["close"].values
    e2["horizon_m5_bars"] = int(horizon)
    e2["entry_spread_cost_bps"] = pd.to_numeric(e2["entry_spread_cost_bps"], errors="coerce").fillna(stress_cost_bps)
    effective_cost = np.maximum(e2["entry_spread_cost_bps"].astype(float).values, stress_cost_bps)
    e2["gross_bps"] = bps_return(e2["entry_price"].astype(float).values, e2["exit_price"].astype(float).values, e2["direction"].astype(float).values)
    e2["stress_bps"] = e2["gross_bps"].values - effective_cost
    e2["stress_bps_cost_x15"] = e2["gross_bps"].values - (effective_cost * 1.5)
    e2["stress_bps_cost_x2"] = e2["gross_bps"].values - (effective_cost * 2.0)
    e2["entry_year"] = pd.to_datetime(e2["entry_time_utc"], utc=True).dt.year
    e2["entry_date"] = pd.to_datetime(e2["entry_time_utc"], utc=True).dt.date.astype(str)
    return e2


def scan_alt_a(features: Dict[str, pd.DataFrame], config: Dict[str, Any], costs: Dict[str, float]) -> List[pd.DataFrame]:
    m15 = features["M15"].copy()
    m30 = features["M30"].copy()
    m5 = features["M5"]
    cfg = config.get("alt_a", {})
    outputs: List[pd.DataFrame] = []
    # Align m30 SMA values to m15.
    m15a = asof_align(m15, m30, [c for c in m30.columns if c.startswith("sma_")], "m30")
    m15a["prior_high"] = m15a["high"].shift(1)
    m15a["prior_low"] = m15a["low"].shift(1)
    for cw in cfg.get("compression_windows", [48, 96]):
        for pct in cfg.get("compression_percentiles", [20, 30]):
            qcol = f"range_q{pct}_cw{cw}"
            if qcol not in m15a.columns:
                continue
            compressed = m15a["range_bps"] <= m15a[qcol]
            for buf in cfg.get("breakout_buffers_bps", [3, 5]):
                up_break = compressed & (m15a["close"] > m15a["prior_high"] * (1.0 + buf / 10000.0))
                dn_break = compressed & (m15a["close"] < m15a["prior_low"] * (1.0 - buf / 10000.0))
                for fail_bars in cfg.get("failure_confirm_bars", [1, 2]):
                    # Failure confirmed when later close returns inside the prior boundary.
                    close_fwd = m15a["close"].shift(-fail_bars)
                    time_fwd = m15a["time_utc"].shift(-fail_bars)
                    fail_up = up_break & (close_fwd < m15a["prior_high"])
                    fail_dn = dn_break & (close_fwd > m15a["prior_low"])
                    for m30w in cfg.get("m30_sma_windows", [20, 40]):
                        trend_col = f"sma_{m30w}_m30"
                        if trend_col not in m15a.columns:
                            continue
                        # Opposite/pullback family: prefer failure against/without strong breakout trend.
                        m30_close = asof_align(m15a[["time_utc"]].copy(), m30, ["close"], "m30")["close_m30"]
                        m30_up = m30_close > m15a[trend_col]
                        m30_dn = m30_close < m15a[trend_col]
                        sig_short = fail_up & (~m30_up.fillna(False))
                        sig_long = fail_dn & (~m30_dn.fillna(False))
                        sig = pd.concat([
                            pd.DataFrame({"signal_time_utc": time_fwd[sig_short], "direction": -1, "direction_label": "SHORT"}),
                            pd.DataFrame({"signal_time_utc": time_fwd[sig_long], "direction": 1, "direction_label": "LONG"}),
                        ], ignore_index=True).dropna(subset=["signal_time_utc"])
                        if sig.empty:
                            continue
                        sig["family"] = "ALT_A_PULLBACK_AFTER_SQUEEZE_FAILURE"
                        sig["candidate_id"] = f"S56A_CW{cw}_P{pct}_B{buf}_F{fail_bars}_M30{m30w}"
                        sig["params"] = json.dumps({"cw": cw, "pct": pct, "buffer_bps": buf, "failure_confirm_bars": fail_bars, "m30_sma": m30w}, sort_keys=True)
                        for h in cfg.get("horizon_m5_bars", [6, 12]):
                            tr = next_m5_entries(sig, m5, int(h), costs["stress_cost_bps"])
                            if not tr.empty:
                                tr["candidate_id"] = tr["candidate_id"] + f"_H{h}"
                                tr["horizon_m5_bars"] = int(h)
                                outputs.append(tr)
    return outputs


def scan_alt_b(features: Dict[str, pd.DataFrame], config: Dict[str, Any], costs: Dict[str, float]) -> List[pd.DataFrame]:
    m15 = features["M15"].copy()
    m30 = features["M30"].copy()
    m5 = features["M5"]
    cfg = config.get("alt_b", {})
    outputs: List[pd.DataFrame] = []
    m15a = asof_align(m15, m30, ["close"] + [c for c in m30.columns if c.startswith("sma_")], "m30")
    for m30w in cfg.get("m30_sma_windows", [20, 40, 80]):
        m30_col = f"sma_{m30w}_m30"
        if m30_col not in m15a.columns:
            continue
        trend_up = m15a["close_m30"] > m15a[m30_col]
        trend_dn = m15a["close_m30"] < m15a[m30_col]
        for value_w in cfg.get("m15_value_sma_windows", [16, 32, 48]):
            value_col = f"sma_{value_w}"
            if value_col not in m15a.columns:
                continue
            dist_to_value_bps = ((m15a["close"] - m15a[value_col]).abs() / m15a["close"].replace(0, np.nan)) * 10000.0
            for imp_lb in cfg.get("impulse_lookback_m15_bars", [2, 4, 8]):
                impulse = (m15a["close"] / m15a["close"].shift(imp_lb) - 1.0) * 10000.0
                for imp_min in cfg.get("impulse_min_bps", [8, 12]):
                    for pb_dist in cfg.get("pullback_max_distance_bps", [3, 6, 10]):
                        long_sig = trend_up & (impulse.shift(1) > imp_min) & (dist_to_value_bps <= pb_dist) & (m15a["close"] >= m15a[value_col])
                        short_sig = trend_dn & (impulse.shift(1) < -imp_min) & (dist_to_value_bps <= pb_dist) & (m15a["close"] <= m15a[value_col])
                        sig = pd.concat([
                            pd.DataFrame({"signal_time_utc": m15a.loc[long_sig, "time_utc"], "direction": 1, "direction_label": "LONG"}),
                            pd.DataFrame({"signal_time_utc": m15a.loc[short_sig, "time_utc"], "direction": -1, "direction_label": "SHORT"}),
                        ], ignore_index=True).dropna(subset=["signal_time_utc"])
                        if sig.empty:
                            continue
                        sig["family"] = "ALT_B_INTRADAY_TREND_PULLBACK_TO_M15_VALUE_AREA"
                        sig["candidate_id"] = f"S56B_M30{m30w}_VAL{value_w}_IMP{imp_lb}_MIN{imp_min}_PB{pb_dist}"
                        sig["params"] = json.dumps({"m30_sma": m30w, "value_sma": value_w, "impulse_lb": imp_lb, "impulse_min_bps": imp_min, "pullback_max_dist_bps": pb_dist}, sort_keys=True)
                        for h in cfg.get("horizon_m5_bars", [6, 12, 18]):
                            tr = next_m5_entries(sig, m5, int(h), costs["stress_cost_bps"])
                            if not tr.empty:
                                tr["candidate_id"] = tr["candidate_id"] + f"_H{h}"
                                tr["horizon_m5_bars"] = int(h)
                                outputs.append(tr)
    return outputs


def scan_alt_c(features: Dict[str, pd.DataFrame], config: Dict[str, Any], costs: Dict[str, float]) -> List[pd.DataFrame]:
    m15 = features["M15"].copy()
    m5 = features["M5"]
    cfg = config.get("alt_c", {})
    outputs: List[pd.DataFrame] = []
    m15["date_dt"] = pd.to_datetime(m15["time_utc"], utc=True).dt.date.astype(str)
    # Session open and cumulative extension from session open.
    sessions = cfg.get("sessions", {"london": [7, 11], "new_york": [12, 16]})
    for session_name, hours in sessions.items():
        h0, h1 = int(hours[0]), int(hours[1])
        s = m15[(m15["hour_utc"] >= h0) & (m15["hour_utc"] <= h1)].copy()
        if s.empty:
            continue
        s["session_open"] = s.groupby("date_dt")["open"].transform("first")
        s["extension_bps"] = ((s["close"] - s["session_open"]) / s["session_open"].replace(0, np.nan)) * 10000.0
        s["abs_extension_bps"] = s["extension_bps"].abs()
        for days in cfg.get("rolling_days", [20, 40]):
            # Approximate M15 bars in session per day.
            bars_window = max(20, days * max(1, (h1 - h0 + 1) * 4))
            for pct in cfg.get("extension_percentiles", [80, 90]):
                threshold = s["abs_extension_bps"].rolling(bars_window, min_periods=max(20, bars_window // 4)).quantile(pct / 100.0).shift(1)
                exhausted_up = s["extension_bps"] > threshold
                exhausted_dn = s["extension_bps"] < -threshold
                for confirm in cfg.get("reversal_confirm_bps", [3, 5, 8]):
                    # Confirmation is current bar closing against the extension by confirm bps from bar high/low.
                    short_sig = exhausted_up & (((s["high"] - s["close"]) / s["close"].replace(0, np.nan)) * 10000.0 >= confirm)
                    long_sig = exhausted_dn & (((s["close"] - s["low"]) / s["close"].replace(0, np.nan)) * 10000.0 >= confirm)
                    sig = pd.concat([
                        pd.DataFrame({"signal_time_utc": s.loc[short_sig, "time_utc"], "direction": -1, "direction_label": "SHORT"}),
                        pd.DataFrame({"signal_time_utc": s.loc[long_sig, "time_utc"], "direction": 1, "direction_label": "LONG"}),
                    ], ignore_index=True).dropna(subset=["signal_time_utc"])
                    if sig.empty:
                        continue
                    sig["family"] = "ALT_C_SESSION_RANGE_REVERSION_AFTER_EXHAUSTION"
                    sig["candidate_id"] = f"S56C_{session_name.upper()}_D{days}_P{pct}_RC{confirm}"
                    sig["params"] = json.dumps({"session": session_name, "rolling_days": days, "extension_pct": pct, "reversal_confirm_bps": confirm}, sort_keys=True)
                    for h in cfg.get("horizon_m5_bars", [6, 12]):
                        tr = next_m5_entries(sig, m5, int(h), costs["stress_cost_bps"])
                        if not tr.empty:
                            tr["candidate_id"] = tr["candidate_id"] + f"_H{h}"
                            tr["horizon_m5_bars"] = int(h)
                            outputs.append(tr)
    return outputs


def decluster_trades(trades: pd.DataFrame, min_gap_minutes: int = 60) -> pd.DataFrame:
    if trades.empty:
        return trades
    t = trades.sort_values("entry_time_utc").copy()
    keep = []
    last_by_dir: Dict[int, pd.Timestamp] = {}
    for idx, row in t.iterrows():
        d = int(row.get("direction", 0))
        ts = pd.to_datetime(row["entry_time_utc"], utc=True)
        last = last_by_dir.get(d)
        if last is None or (ts - last).total_seconds() >= min_gap_minutes * 60:
            keep.append(idx)
            last_by_dir[d] = ts
    return t.loc[keep].copy()


def max_drawdown(values: pd.Series) -> float:
    if values.empty:
        return float("nan")
    curve = values.fillna(0).cumsum()
    dd = curve - curve.cummax()
    return float(dd.min())


def summarize_candidate(candidate_id: str, trades: pd.DataFrame, thresholds: Dict[str, Any]) -> Dict[str, Any]:
    t = trades.sort_values("entry_time_utc").copy()
    n = len(t)
    if n == 0:
        return {"candidate_id": candidate_id, "trade_count": 0, "status": "NO_TRADES"}
    split_idx = int(math.floor(n * 0.8))
    is_t = t.iloc[:split_idx] if split_idx > 0 else t.iloc[:0]
    oos_t = t.iloc[split_idx:] if split_idx < n else t.iloc[:0]
    years = t.groupby("entry_year")["stress_bps"].mean().to_dict()
    positive_year_count = sum(1 for v in years.values() if v > 0)
    negative_year_count = sum(1 for v in years.values() if v < 0)
    worst_year = min(years.values()) if years else float("nan")
    dirs = t["direction_label"].value_counts(normalize=True).to_dict()
    max_dir_share = max(dirs.values()) if dirs else 0.0
    dec = decluster_trades(t, 60)
    mean = float(t["stress_bps"].mean())
    med = float(t["stress_bps"].median())
    wr = float((t["stress_bps"] > 0).mean())
    std = float(t["stress_bps"].std(ddof=1)) if n > 1 else float("nan")
    tstat = float(mean / (std / math.sqrt(n))) if std and std > 0 and n > 1 else float("nan")
    oos_mean = float(oos_t["stress_bps"].mean()) if len(oos_t) else float("nan")
    oos_wr = float((oos_t["stress_bps"] > 0).mean()) if len(oos_t) else float("nan")
    cost_x15 = float(t["stress_bps_cost_x15"].mean()) if "stress_bps_cost_x15" in t else float("nan")
    cost_x2 = float(t["stress_bps_cost_x2"].mean()) if "stress_bps_cost_x2" in t else float("nan")
    dec_mean = float(dec["stress_bps"].mean()) if len(dec) else float("nan")
    dec_wr = float((dec["stress_bps"] > 0).mean()) if len(dec) else float("nan")
    day_counts = t["entry_date"].value_counts(normalize=True)
    max_day_share = float(day_counts.max()) if not day_counts.empty else 0.0
    failures = []
    if n < int(thresholds.get("min_trade_count", 150)):
        failures.append("trade_count_lt_min")
    if len(oos_t) < int(thresholds.get("min_oos_trade_count", 30)):
        failures.append("oos_trade_count_lt_min")
    if mean < float(thresholds.get("min_mean_stress_bps", 1.0)):
        failures.append("mean_stress_lt_min")
    if med < float(thresholds.get("min_median_stress_bps", 0.0)):
        failures.append("median_stress_lt_min")
    if wr < float(thresholds.get("min_win_rate", 0.52)):
        failures.append("win_rate_lt_min")
    if not math.isfinite(oos_mean) or oos_mean < float(thresholds.get("min_oos_mean_stress_bps", 0.5)):
        failures.append("oos_mean_lt_min")
    if not math.isfinite(oos_wr) or oos_wr < float(thresholds.get("min_oos_win_rate", 0.52)):
        failures.append("oos_win_rate_lt_min")
    if positive_year_count < int(thresholds.get("min_positive_years", 3)):
        failures.append("positive_years_lt_min")
    if negative_year_count > int(thresholds.get("max_negative_years", 1)):
        failures.append("negative_years_gt_max")
    if math.isfinite(worst_year) and worst_year < float(thresholds.get("min_worst_year_stress_bps", -2.0)):
        failures.append("worst_year_lt_min")
    if cost_x2 < float(thresholds.get("min_cost_x2_mean_stress_bps", 0.0)):
        failures.append("cost_x2_mean_lt_min")
    if dec_mean < float(thresholds.get("min_declustered_mean_stress_bps", 0.5)):
        failures.append("declustered_mean_lt_min")
    if max_dir_share > float(thresholds.get("max_direction_imbalance", 0.85)):
        failures.append("direction_imbalance_gt_max")
    status = "HARD_AUDIT_PASS_NEEDS_FORWARD_SHADOW_DESIGN" if not failures else "NO_PASS"
    first = pd.to_datetime(t["entry_time_utc"].iloc[0], utc=True)
    last = pd.to_datetime(t["entry_time_utc"].iloc[-1], utc=True)
    return {
        "candidate_id": candidate_id,
        "family": str(t["family"].iloc[0]),
        "status": status,
        "failures": ";".join(failures),
        "trade_count": n,
        "oos_trade_count": len(oos_t),
        "mean_stress_bps": mean,
        "median_stress_bps": med,
        "win_rate": wr,
        "t_stat": tstat,
        "is_mean_stress_bps": float(is_t["stress_bps"].mean()) if len(is_t) else float("nan"),
        "is_win_rate": float((is_t["stress_bps"] > 0).mean()) if len(is_t) else float("nan"),
        "oos_mean_stress_bps": oos_mean,
        "oos_win_rate": oos_wr,
        "positive_year_count": positive_year_count,
        "negative_year_count": negative_year_count,
        "worst_year_mean_stress_bps": worst_year,
        "cost_x15_mean_stress_bps": cost_x15,
        "cost_x2_mean_stress_bps": cost_x2,
        "declustered_trade_count": len(dec),
        "declustered_mean_stress_bps": dec_mean,
        "declustered_win_rate": dec_wr,
        "max_direction_share": max_dir_share,
        "max_day_share": max_day_share,
        "first_entry_utc": first.isoformat().replace("+00:00", "Z"),
        "last_entry_utc": last.isoformat().replace("+00:00", "Z"),
        "span_days": (last - first).total_seconds() / 86400.0,
        "params": str(t["params"].iloc[0]) if "params" in t else "{}",
    }


def run_family(family: str, features: Dict[str, pd.DataFrame], config: Dict[str, Any], costs: Dict[str, float]) -> Tuple[str, pd.DataFrame]:
    if family == "ALT_A_PULLBACK_AFTER_SQUEEZE_FAILURE":
        parts = scan_alt_a(features, config, costs)
    elif family == "ALT_B_INTRADAY_TREND_PULLBACK_TO_M15_VALUE_AREA":
        parts = scan_alt_b(features, config, costs)
    elif family == "ALT_C_SESSION_RANGE_REVERSION_AFTER_EXHAUSTION":
        parts = scan_alt_c(features, config, costs)
    else:
        raise ValueError(f"Unknown family: {family}")
    if not parts:
        return family, pd.DataFrame()
    return family, pd.concat(parts, ignore_index=True)


def write_report(summary: Dict[str, Any], candidates: pd.DataFrame, out: Path) -> None:
    lines = []
    lines.append("# Stage56 Parallel Alternative Megascan")
    lines.append("")
    for k in ["status", "decision", "next_allowed_step", "promotion", "EA", "paper_live", "live"]:
        lines.append(f"- {k}: `{summary.get(k)}`")
    lines.append("")
    lines.append("## Inputs")
    lines.append(f"- db: `{summary.get('db')}`")
    lines.append(f"- cost_model: `{summary.get('cost_model')}`")
    lines.append(f"- families: `{', '.join(summary.get('families', []))}`")
    lines.append("")
    lines.append("## Scan summary")
    fs = summary.get("family_summary", {})
    for fam, row in fs.items():
        lines.append(f"- `{fam}`: candidates=`{row.get('candidate_count')}`, trades=`{row.get('trade_count')}`, pass=`{row.get('hard_audit_pass_count')}`")
    lines.append("")
    lines.append(f"- total_candidates: `{summary.get('total_candidates')}`")
    lines.append(f"- hard_audit_pass_count: `{summary.get('hard_audit_pass_count')}`")
    lines.append("")
    lines.append("## Top candidates")
    if candidates.empty:
        lines.append("- none")
    else:
        top = candidates.sort_values(["status", "oos_mean_stress_bps", "mean_stress_bps"], ascending=[True, False, False]).head(20)
        for _, r in top.iterrows():
            lines.append(
                f"- `{r['candidate_id']}` family=`{r['family']}` status=`{r['status']}` trades=`{int(r['trade_count'])}` "
                f"mean=`{r['mean_stress_bps']:.3f}` wr=`{r['win_rate']:.3f}` oos_mean=`{r['oos_mean_stress_bps']:.3f}` "
                f"oos_wr=`{r['oos_win_rate']:.3f}` failures=`{r.get('failures','')}`"
            )
    lines.append("")
    lines.append("## Interpretation")
    lines.append("Stage56 is a parallel historical megascan/audit only. It does not use historical results as forward evidence and does not authorize promotion, EA, paper-live, live trading, or order submission.")
    (out / "stage56_parallel_alt_megascan_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Stage56 parallel alternative megascan")
    ap.add_argument("--root", default=".")
    ap.add_argument("--db", default="data/broker_normalized/amarkets_multitf.sqlite")
    ap.add_argument("--cost-model", default="reports/stage48f/stage48f_cost_model.json")
    ap.add_argument("--config", default="configs/stage56_parallel_alt_megascan.json")
    ap.add_argument("--out", default="reports/stage56_parallel_alt_megascan")
    ap.add_argument("--families", default=",".join(FAMILIES), help="Comma-separated families")
    ap.add_argument("--max-workers", type=int, default=None, help="Optional process workers. Default from config; 1 recommended on older Macs.")
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    db_path = (root / args.db).resolve() if not Path(args.db).is_absolute() else Path(args.db)
    cost_model = (root / args.cost_model).resolve() if args.cost_model and not Path(args.cost_model).is_absolute() else Path(args.cost_model)
    config_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    out = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    ensure_dir(out)

    config = read_json(config_path, {}) or {}
    thresholds = dict(config.get("audit_thresholds", {}))
    limits = config.get("scan_limits", {})
    thresholds["min_trade_count"] = limits.get("min_trade_count", 150)
    thresholds["min_oos_trade_count"] = limits.get("min_oos_trade_count", 30)
    families = [f.strip() for f in args.families.split(",") if f.strip()]
    costs = load_costs(cost_model, config)
    generated_utc = utc_now()

    try:
        data = load_market_data(db_path)
        features = prepare_features(data)
    except Exception as e:
        summary = {
            "stage": STAGE,
            "status": "ERROR_NO_PROMOTION",
            **NO_GO,
            "decision": "FIX_STAGE56_INPUTS_NO_PROMOTION",
            "next_allowed_step": "FIX_STAGE56_INPUTS_NO_PROMOTION",
            "error": str(e),
            "generated_utc": generated_utc,
        }
        (out / "stage56_parallel_alt_megascan_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return 2

    workers = args.max_workers if args.max_workers is not None else int(limits.get("max_workers", 1))
    workers = max(1, min(workers, len(families)))

    all_parts: List[pd.DataFrame] = []
    family_errors: Dict[str, str] = {}
    if workers == 1:
        for fam in families:
            try:
                _, tr = run_family(fam, features, config, costs)
                if not tr.empty:
                    all_parts.append(tr)
            except Exception as e:
                family_errors[fam] = str(e)
    else:
        # This is optional. It can be memory-heavy because each process receives feature frames.
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(run_family, fam, features, config, costs): fam for fam in families}
            for fut in as_completed(futs):
                fam = futs[fut]
                try:
                    _, tr = fut.result()
                    if not tr.empty:
                        all_parts.append(tr)
                except Exception as e:
                    family_errors[fam] = str(e)

    trades = pd.concat(all_parts, ignore_index=True) if all_parts else pd.DataFrame()
    if not trades.empty:
        # Drop exact duplicate entries across nearly equivalent candidates only within candidate_id.
        trades = trades.drop_duplicates(subset=["candidate_id", "entry_time_utc", "direction"]).reset_index(drop=True)

    candidate_rows: List[Dict[str, Any]] = []
    if not trades.empty:
        for cid, grp in trades.groupby("candidate_id", sort=False):
            candidate_rows.append(summarize_candidate(str(cid), grp, thresholds))
    candidates = pd.DataFrame(candidate_rows)
    if not candidates.empty:
        candidates = candidates.sort_values(["status", "oos_mean_stress_bps", "mean_stress_bps", "trade_count"], ascending=[True, False, False, False]).reset_index(drop=True)

    # Trim exports for practicality.
    top_n_global = int(limits.get("top_n_global", 80))
    top_candidates = candidates.head(top_n_global).copy() if not candidates.empty else candidates
    pass_count = int((candidates["status"] == "HARD_AUDIT_PASS_NEEDS_FORWARD_SHADOW_DESIGN").sum()) if not candidates.empty else 0

    family_summary: Dict[str, Dict[str, Any]] = {}
    for fam in families:
        fam_trades = trades[trades["family"] == fam] if not trades.empty and "family" in trades else pd.DataFrame()
        fam_cand = candidates[candidates["family"] == fam] if not candidates.empty and "family" in candidates else pd.DataFrame()
        family_summary[fam] = {
            "trade_count": int(len(fam_trades)),
            "candidate_count": int(len(fam_cand)),
            "hard_audit_pass_count": int((fam_cand["status"] == "HARD_AUDIT_PASS_NEEDS_FORWARD_SHADOW_DESIGN").sum()) if not fam_cand.empty else 0,
            "error": family_errors.get(fam),
        }

    decision = "ALT_MEGASCAN_PASS_NEEDS_FORWARD_SHADOW_DESIGN_NO_PROMOTION" if pass_count > 0 else "ALT_MEGASCAN_COMPLETE_NO_PASS_NO_PROMOTION"
    next_step = "DESIGN_SEPARATE_FORWARD_SHADOW_FOR_ALT_SHORTLIST_NO_PROMOTION" if pass_count > 0 else "ARCHIVE_ALT_MEGASCAN_OR_EXPAND_CONTEXT_NO_PROMOTION"
    summary = {
        "stage": STAGE,
        "status": "PARALLEL_ALT_MEGASCAN_COMPLETE_NO_PROMOTION",
        **NO_GO,
        "decision": decision,
        "next_allowed_step": next_step,
        "root": str(root),
        "db": str(db_path),
        "cost_model": str(cost_model),
        "config": str(config_path),
        "families": families,
        "workers": workers,
        "rows": {tf: int(len(df)) for tf, df in data.items()},
        "costs": costs,
        "family_summary": family_summary,
        "total_trade_rows": int(len(trades)),
        "total_candidates": int(len(candidates)),
        "exported_top_candidates": int(len(top_candidates)),
        "hard_audit_pass_count": pass_count,
        "family_errors": family_errors,
        "generated_utc": generated_utc,
    }

    # CSV outputs.
    if not top_candidates.empty:
        top_candidates.to_csv(out / "stage56_parallel_alt_megascan_candidates.csv", index=False)
    else:
        pd.DataFrame(columns=["candidate_id", "family", "status", "trade_count", "mean_stress_bps", "win_rate", "oos_mean_stress_bps", "oos_win_rate", "failures"]).to_csv(out / "stage56_parallel_alt_megascan_candidates.csv", index=False)

    # Event sample for top candidates.
    sample_n = int(limits.get("event_sample_per_candidate", 10))
    if not trades.empty and not top_candidates.empty:
        keep_ids = set(top_candidates["candidate_id"].head(min(20, len(top_candidates))).astype(str))
        sample = trades[trades["candidate_id"].astype(str).isin(keep_ids)].groupby("candidate_id", group_keys=False).head(sample_n)
        cols = [c for c in ["candidate_id", "family", "entry_time_utc", "exit_time_utc", "direction_label", "entry_price", "exit_price", "gross_bps", "stress_bps", "entry_spread_cost_bps", "horizon_m5_bars", "params"] if c in sample.columns]
        sample[cols].to_csv(out / "stage56_parallel_alt_megascan_event_sample.csv", index=False)
    else:
        pd.DataFrame(columns=["candidate_id", "family", "entry_time_utc", "exit_time_utc", "direction_label", "stress_bps"]).to_csv(out / "stage56_parallel_alt_megascan_event_sample.csv", index=False)

    (out / "stage56_parallel_alt_megascan_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    write_report(summary, top_candidates, out)
    print(json.dumps({"stage": STAGE, "status": summary["status"], "decision": decision, "hard_audit_pass_count": pass_count, "out": str(out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
