#!/usr/bin/env python3
"""
Stage40_PARALLEL_THESIS_MEGASCAN

Benchmark-first research scan across multiple independent Stage40 theses:
- 40A false-breakout / liquidity sweep reversal
- 40B volatility compression -> expansion continuation
- 40C session transition imbalance
- 40D failed continuation after extreme move
- 40E pullback continuation after trend confirmation
- 40F volatility shock reversal

This script is deliberately research-only. It cannot promote, create EA rules,
paper-live rules, or live rules. It produces ranked diagnostics and hard NO-GO
unless later independent audit stages survive.
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

STAGE = "Stage40_PARALLEL_THESIS_MEGASCAN"
DECISION_SCOPE = "RESEARCH_STAGE_ONLY_NO_PROMOTION"
NO_GO = "NO_GO"

TIMESTAMP_CANDIDATES = [
    "utc_time", "ts_utc", "entry_ts", "entry_utc", "timestamp_utc", "time_utc",
    "datetime_utc", "date_utc", "timestamp", "time", "datetime", "date", "open_time", "bar_time",
]
OPEN_CANDIDATES = ["open", "o"]
HIGH_CANDIDATES = ["high", "h"]
LOW_CANDIDATES = ["low", "l"]
CLOSE_CANDIDATES = ["close", "c"]
SPREAD_CANDIDATES = ["spread", "spread_points", "spread_bps"]
VOLUME_CANDIDATES = ["tick_volume", "volume", "real_volume", "vol"]
SYMBOL_CANDIDATES = ["symbol", "ticker", "instrument"]
SOURCE_CANDIDATES = ["source", "provider", "broker"]
TIMEFRAME_CANDIDATES = ["timeframe", "tf", "interval"]


def norm_name(x: Any) -> str:
    return str(x).strip().lower()


def normalize_timeframe(x: Any) -> str:
    s = norm_name(x).replace(" ", "").replace("_", "").replace("-", "")
    aliases = {
        "h1": "H1", "1h": "H1", "60m": "H1", "m60": "H1", "60min": "H1", "60minute": "H1",
        "1hr": "H1", "1hour": "H1", "hour1": "H1",
        "m15": "M15", "15m": "M15", "15min": "M15", "15minute": "M15",
        "m5": "M5", "5m": "M5", "5min": "M5", "5minute": "M5",
        "m1": "M1", "1m": "M1", "1min": "M1", "1minute": "M1",
    }
    return aliases.get(s, str(x).strip().upper())


def first_existing_col(columns: Sequence[str], candidates: Sequence[str], required: bool = True) -> Optional[str]:
    cols = list(columns)
    lowered = {c.lower(): c for c in cols}
    for cand in candidates:
        if cand in cols:
            return cand
        if cand.lower() in lowered:
            return lowered[cand.lower()]
    if required:
        raise ValueError(f"Required column not found; tried={list(candidates)} available={list(columns)}")
    return None


def table_columns(db_path: str, table: str) -> List[str]:
    with sqlite3.connect(db_path) as con:
        rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    if not rows:
        raise ValueError(f"Table not found or empty PRAGMA: {db_path}:{table}")
    return [r[1] for r in rows]


def read_bars(
    db_path: str,
    table: str,
    symbol: str,
    source: str,
    timeframe: str,
    max_rows: Optional[int] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    cols = table_columns(db_path, table)
    ts_col = first_existing_col(cols, TIMESTAMP_CANDIDATES)
    open_col = first_existing_col(cols, OPEN_CANDIDATES)
    high_col = first_existing_col(cols, HIGH_CANDIDATES)
    low_col = first_existing_col(cols, LOW_CANDIDATES)
    close_col = first_existing_col(cols, CLOSE_CANDIDATES)
    spread_col = first_existing_col(cols, SPREAD_CANDIDATES, required=False)
    volume_col = first_existing_col(cols, VOLUME_CANDIDATES, required=False)
    symbol_col = first_existing_col(cols, SYMBOL_CANDIDATES, required=False)
    source_col = first_existing_col(cols, SOURCE_CANDIDATES, required=False)
    timeframe_col = first_existing_col(cols, TIMEFRAME_CANDIDATES, required=False)

    order_clause = f"ORDER BY {ts_col}"
    limit_clause = f" LIMIT {int(max_rows)}" if max_rows else ""
    with sqlite3.connect(db_path) as con:
        raw = pd.read_sql_query(f"SELECT * FROM {table} {order_clause}{limit_clause}", con)

    meta: Dict[str, Any] = {
        "db_path": db_path,
        "table": table,
        "available_columns": cols,
        "columns": {
            "timestamp": ts_col,
            "open": open_col,
            "high": high_col,
            "low": low_col,
            "close": close_col,
            "spread": spread_col,
            "volume": volume_col,
            "symbol": symbol_col,
            "source": source_col,
            "timeframe": timeframe_col,
        },
        "requested_filters": {"symbol": symbol, "source": source, "timeframe": timeframe},
        "pre_filter_rows": int(len(raw)),
        "filter_steps": [],
    }

    df = raw.copy()
    if symbol_col:
        before = len(df)
        df = df[df[symbol_col].astype(str).str.strip().str.upper() == str(symbol).strip().upper()].copy()
        meta["filter_steps"].append({"filter": "symbol", "requested": symbol, "before": before, "after": int(len(df))})
    if source_col:
        before = len(df)
        df = df[df[source_col].map(norm_name) == norm_name(source)].copy()
        meta["filter_steps"].append({"filter": "source", "requested": source, "before": before, "after": int(len(df))})
    if timeframe_col:
        before = len(df)
        target_tf = normalize_timeframe(timeframe)
        df = df[df[timeframe_col].map(normalize_timeframe) == target_tf].copy()
        meta["filter_steps"].append({"filter": "timeframe", "requested": timeframe, "normalized": target_tf, "before": before, "after": int(len(df))})

    if df.empty:
        samples: Dict[str, List[Any]] = {}
        for name, col in [("symbol", symbol_col), ("source", source_col), ("timeframe", timeframe_col)]:
            if col:
                try:
                    samples[name] = raw[col].dropna().astype(str).drop_duplicates().head(20).tolist()
                except Exception:
                    samples[name] = []
        raise ValueError(
            "No rows loaded after tolerant filtering. "
            f"requested={meta['requested_filters']} pre_filter_rows={meta['pre_filter_rows']} samples={samples}"
        )

    out = pd.DataFrame({
        "ts": pd.to_datetime(df[ts_col], utc=True, errors="coerce"),
        "open": pd.to_numeric(df[open_col], errors="coerce"),
        "high": pd.to_numeric(df[high_col], errors="coerce"),
        "low": pd.to_numeric(df[low_col], errors="coerce"),
        "close": pd.to_numeric(df[close_col], errors="coerce"),
    })
    if spread_col:
        out["spread"] = pd.to_numeric(df[spread_col], errors="coerce")
    else:
        out["spread"] = np.nan
    if volume_col:
        out["volume"] = pd.to_numeric(df[volume_col], errors="coerce")
    else:
        out["volume"] = np.nan

    out = out.dropna(subset=["ts", "open", "high", "low", "close"]).sort_values("ts").reset_index(drop=True)
    out = out[~out["ts"].duplicated(keep="last")].reset_index(drop=True)
    if out.empty:
        raise ValueError("Rows were loaded but all were dropped after timestamp/OHLC cleaning")
    meta.update({
        "post_filter_rows": int(len(df)),
        "loaded_rows": int(len(out)),
        "date_min": out["ts"].min().isoformat(),
        "date_max": out["ts"].max().isoformat(),
    })
    return out, meta


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    x["ret1_bps"] = x["close"].pct_change(1) * 10000.0
    for w in [4, 8, 12, 24, 48, 72, 120, 240]:
        x[f"ret{w}_bps"] = x["close"].pct_change(w) * 10000.0
        x[f"roll_high_{w}"] = x["high"].rolling(w, min_periods=max(3, w // 3)).max().shift(1)
        x[f"roll_low_{w}"] = x["low"].rolling(w, min_periods=max(3, w // 3)).min().shift(1)
        x[f"roll_mean_{w}"] = x["close"].rolling(w, min_periods=max(3, w // 3)).mean().shift(1)
        x[f"roll_std_{w}"] = x["close"].rolling(w, min_periods=max(3, w // 3)).std(ddof=0).shift(1)
        x[f"range_{w}_bps"] = ((x[f"roll_high_{w}"] - x[f"roll_low_{w}"]) / x["close"] * 10000.0)
    tr1 = (x["high"] - x["low"]).abs()
    tr2 = (x["high"] - x["close"].shift(1)).abs()
    tr3 = (x["low"] - x["close"].shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    x["tr_bps"] = tr / x["close"] * 10000.0
    x["atr24_bps"] = x["tr_bps"].rolling(24, min_periods=12).mean().shift(1)
    x["atr72_bps"] = x["tr_bps"].rolling(72, min_periods=24).mean().shift(1)
    x["body_bps"] = (x["close"] - x["open"]) / x["open"] * 10000.0
    x["abs_body_bps"] = x["body_bps"].abs()
    x["upper_wick_bps"] = (x["high"] - x[["open", "close"]].max(axis=1)) / x["open"] * 10000.0
    x["lower_wick_bps"] = (x[["open", "close"]].min(axis=1) - x["low"]) / x["open"] * 10000.0
    x["hour_utc"] = x["ts"].dt.hour
    x["weekday"] = x["ts"].dt.day_name()
    x["year"] = x["ts"].dt.year
    x["month"] = x["ts"].dt.month
    x["session_utc"] = np.select(
        [x["hour_utc"].between(0, 6), x["hour_utc"].between(7, 12), x["hour_utc"].between(13, 17), x["hour_utc"].between(18, 23)],
        ["ASIA_00_06", "LONDON_07_12", "NY_13_17", "LATE_18_23"],
        default="UNKNOWN",
    )
    # Daily Asia range for session-transition thesis.
    x["date"] = x["ts"].dt.date.astype(str)
    asia = x[x["hour_utc"].between(0, 6)].groupby("date").agg(asia_high=("high", "max"), asia_low=("low", "min"), asia_range=("high", lambda s: np.nan))
    # Recompute asia range safely.
    asia_high = x[x["hour_utc"].between(0, 6)].groupby("date")["high"].max()
    asia_low = x[x["hour_utc"].between(0, 6)].groupby("date")["low"].min()
    asia = pd.DataFrame({"asia_high": asia_high, "asia_low": asia_low})
    asia["asia_range_bps"] = (asia["asia_high"] - asia["asia_low"]) / ((asia["asia_high"] + asia["asia_low"]) / 2.0) * 10000.0
    x = x.merge(asia, left_on="date", right_index=True, how="left")
    x["asia_range_bps_roll_median20"] = x.groupby("hour_utc")["asia_range_bps"].transform(lambda s: s.rolling(20, min_periods=5).median())
    return x


@dataclass(frozen=True)
class CandidateSpec:
    family: str
    candidate: str
    side: str
    trigger: str
    horizon: int
    params: Dict[str, Any]


def event_clock(indices: Iterable[int], horizon: int, n_bars: int) -> List[int]:
    out: List[int] = []
    next_allowed = -1
    for idx in sorted(int(i) for i in indices):
        if idx < 0 or idx + horizon >= n_bars:
            continue
        if idx >= next_allowed:
            out.append(idx)
            next_allowed = idx + horizon
    return out


def build_candidate_indices(df: pd.DataFrame, spec: CandidateSpec) -> List[int]:
    p = spec.params
    f = spec.family
    mask = pd.Series(False, index=df.index)
    eps = float(p.get("threshold_bps", 0.0)) / 10000.0

    if f == "FALSE_BREAKOUT_SWEEP_REVERSAL":
        lb = int(p["lookback"])
        rh = df[f"roll_high_{lb}"]
        rl = df[f"roll_low_{lb}"]
        if spec.side == "LONG":
            mask = (df["low"] < rl * (1.0 - eps)) & (df["close"] > rl) & (df["close"] > df["open"])
        else:
            mask = (df["high"] > rh * (1.0 + eps)) & (df["close"] < rh) & (df["close"] < df["open"])

    elif f == "VOL_COMPRESSION_EXPANSION":
        lb = int(p["lookback"])
        q = float(p["compression_q"])
        mult = float(p["expansion_mult"])
        range_col = f"range_{lb}_bps"
        roll_q = df[range_col].rolling(240, min_periods=80).quantile(q).shift(1)
        compressed = df[range_col] <= roll_q
        expansion = df["tr_bps"] >= (df["atr24_bps"] * mult)
        if spec.side == "LONG":
            mask = compressed & expansion & (df["close"] > df["open"])
        else:
            mask = compressed & expansion & (df["close"] < df["open"])

    elif f == "SESSION_TRANSITION_IMBALANCE":
        q = float(p["asia_range_q"])
        direction = p["direction"]
        asia_q = df["asia_range_bps"].rolling(120, min_periods=30).quantile(q).shift(1)
        compressed_asia = df["asia_range_bps"] <= asia_q
        london = df["hour_utc"].between(7, 12)
        if direction == "breakout_up":
            mask = london & compressed_asia & (df["high"] > df["asia_high"]) & (df["close"] > df["asia_high"])
        elif direction == "breakout_down":
            mask = london & compressed_asia & (df["low"] < df["asia_low"]) & (df["close"] < df["asia_low"])
        elif direction == "false_up":
            mask = london & (df["high"] > df["asia_high"]) & (df["close"] < df["asia_high"])
        else:
            mask = london & (df["low"] < df["asia_low"]) & (df["close"] > df["asia_low"])

    elif f == "FAILED_CONTINUATION_AFTER_EXTREME_MOVE":
        lb = int(p["lookback"])
        th = float(p["move_bps"])
        rh = df[f"roll_high_{lb}"]
        rl = df[f"roll_low_{lb}"]
        if spec.side == "SHORT":
            mask = (df[f"ret{lb}_bps"] >= th) & (df["high"] > rh) & (df["close"] < rh) & (df["close"] < df["open"])
        else:
            mask = (df[f"ret{lb}_bps"] <= -th) & (df["low"] < rl) & (df["close"] > rl) & (df["close"] > df["open"])

    elif f == "PULLBACK_CONTINUATION_AFTER_TREND":
        trend_lb = int(p["trend_lookback"])
        mean_lb = int(p["mean_lookback"])
        trend_th = float(p["trend_bps"])
        mean = df[f"roll_mean_{mean_lb}"]
        std = df[f"roll_std_{mean_lb}"]
        if spec.side == "LONG":
            trend = df[f"ret{trend_lb}_bps"] >= trend_th
            pullback = (df["low"] <= mean) & (df["close"] >= mean - 0.5 * std) & (df["close"] > df["open"])
            mask = trend & pullback
        else:
            trend = df[f"ret{trend_lb}_bps"] <= -trend_th
            pullback = (df["high"] >= mean) & (df["close"] <= mean + 0.5 * std) & (df["close"] < df["open"])
            mask = trend & pullback

    elif f == "VOLATILITY_SHOCK_REVERSAL":
        mult = float(p["range_atr_mult"])
        wick_ratio = float(p["wick_ratio"])
        shock = df["tr_bps"] >= df["atr24_bps"] * mult
        if spec.side == "LONG":
            mask = shock & (df["lower_wick_bps"] >= df["abs_body_bps"] * wick_ratio) & (df["close"] > df["open"])
        else:
            mask = shock & (df["upper_wick_bps"] >= df["abs_body_bps"] * wick_ratio) & (df["close"] < df["open"])

    else:
        raise ValueError(f"Unknown family: {f}")

    mask = mask.fillna(False)
    return mask[mask].index.astype(int).tolist()


def generate_specs(horizons: Sequence[int]) -> List[CandidateSpec]:
    specs: List[CandidateSpec] = []
    for h in horizons:
        for lb in [24, 72]:
            for th in [3, 8, 15]:
                specs.append(CandidateSpec("FALSE_BREAKOUT_SWEEP_REVERSAL", f"SWEEP_LOW_REV_LONG_L{lb}_T{th}", "LONG", f"Sweep below prior {lb}H low by {th}bps then close back inside", h, {"lookback": lb, "threshold_bps": th}))
                specs.append(CandidateSpec("FALSE_BREAKOUT_SWEEP_REVERSAL", f"SWEEP_HIGH_REV_SHORT_L{lb}_T{th}", "SHORT", f"Sweep above prior {lb}H high by {th}bps then close back inside", h, {"lookback": lb, "threshold_bps": th}))
        for lb in [24, 72, 120]:
            for q in [0.15, 0.25]:
                for m in [1.5, 2.0]:
                    specs.append(CandidateSpec("VOL_COMPRESSION_EXPANSION", f"VOL_COMP_EXP_LONG_L{lb}_Q{q}_M{m}", "LONG", f"Compressed {lb}H range then bullish expansion", h, {"lookback": lb, "compression_q": q, "expansion_mult": m}))
                    specs.append(CandidateSpec("VOL_COMPRESSION_EXPANSION", f"VOL_COMP_EXP_SHORT_L{lb}_Q{q}_M{m}", "SHORT", f"Compressed {lb}H range then bearish expansion", h, {"lookback": lb, "compression_q": q, "expansion_mult": m}))
        for q in [0.25, 0.4]:
            specs.append(CandidateSpec("SESSION_TRANSITION_IMBALANCE", f"ASIA_COMP_LONDON_BREAKOUT_LONG_Q{q}", "LONG", "Asia compression then London breakout up", h, {"asia_range_q": q, "direction": "breakout_up"}))
            specs.append(CandidateSpec("SESSION_TRANSITION_IMBALANCE", f"ASIA_COMP_LONDON_BREAKOUT_SHORT_Q{q}", "SHORT", "Asia compression then London breakout down", h, {"asia_range_q": q, "direction": "breakout_down"}))
            specs.append(CandidateSpec("SESSION_TRANSITION_IMBALANCE", f"LONDON_FALSE_ASIA_HIGH_SHORT_Q{q}", "SHORT", "London false break above Asia high", h, {"asia_range_q": q, "direction": "false_up"}))
            specs.append(CandidateSpec("SESSION_TRANSITION_IMBALANCE", f"LONDON_FALSE_ASIA_LOW_LONG_Q{q}", "LONG", "London false break below Asia low", h, {"asia_range_q": q, "direction": "false_down"}))
        for lb in [24, 72]:
            for th in [100, 200, 300]:
                specs.append(CandidateSpec("FAILED_CONTINUATION_AFTER_EXTREME_MOVE", f"FAILED_UP_CONT_SHORT_L{lb}_T{th}", "SHORT", f"Strong {lb}H up move, new high attempt fails", h, {"lookback": lb, "move_bps": th}))
                specs.append(CandidateSpec("FAILED_CONTINUATION_AFTER_EXTREME_MOVE", f"FAILED_DOWN_CONT_LONG_L{lb}_T{th}", "LONG", f"Strong {lb}H down move, new low attempt fails", h, {"lookback": lb, "move_bps": th}))
        for trend_lb in [72, 120]:
            for trend_th in [150, 300]:
                specs.append(CandidateSpec("PULLBACK_CONTINUATION_AFTER_TREND", f"UPTREND_PULLBACK_CONT_LONG_TL{trend_lb}_T{trend_th}", "LONG", f"Uptrend {trend_lb}H then controlled pullback continuation", h, {"trend_lookback": trend_lb, "trend_bps": trend_th, "mean_lookback": 24}))
                specs.append(CandidateSpec("PULLBACK_CONTINUATION_AFTER_TREND", f"DOWNTREND_PULLBACK_CONT_SHORT_TL{trend_lb}_T{trend_th}", "SHORT", f"Downtrend {trend_lb}H then controlled pullback continuation", h, {"trend_lookback": trend_lb, "trend_bps": trend_th, "mean_lookback": 24}))
        for mult in [2.0, 2.5, 3.0]:
            for wr in [1.0, 1.5]:
                specs.append(CandidateSpec("VOLATILITY_SHOCK_REVERSAL", f"LOWER_WICK_SHOCK_REV_LONG_M{mult}_W{wr}", "LONG", "Large H1 shock with lower-wick rejection", h, {"range_atr_mult": mult, "wick_ratio": wr}))
                specs.append(CandidateSpec("VOLATILITY_SHOCK_REVERSAL", f"UPPER_WICK_SHOCK_REV_SHORT_M{mult}_W{wr}", "SHORT", "Large H1 shock with upper-wick rejection", h, {"range_atr_mult": mult, "wick_ratio": wr}))
    return specs


def forward_path_metrics(df: pd.DataFrame, entry_idx: int, horizon: int, side: str) -> Optional[Dict[str, Any]]:
    exit_idx = entry_idx + horizon
    if entry_idx < 0 or exit_idx >= len(df):
        return None
    entry = float(df.at[entry_idx, "close"])
    exitp = float(df.at[exit_idx, "close"])
    path = df.iloc[entry_idx + 1: exit_idx + 1]
    if not np.isfinite(entry) or entry <= 0 or path.empty:
        return None
    if side == "LONG":
        final_bps = (exitp / entry - 1.0) * 10000.0
        mfe_bps = (float(path["high"].max()) / entry - 1.0) * 10000.0
        mae_bps = (float(path["low"].min()) / entry - 1.0) * 10000.0
    else:
        final_bps = (1.0 - exitp / entry) * 10000.0
        mfe_bps = (1.0 - float(path["low"].min()) / entry) * 10000.0
        mae_bps = (1.0 - float(path["high"].max()) / entry) * 10000.0
    return {
        "entry_idx": entry_idx,
        "exit_idx": exit_idx,
        "entry_ts": df.at[entry_idx, "ts"].isoformat(),
        "exit_ts": df.at[exit_idx, "ts"].isoformat(),
        "entry_close": entry,
        "exit_close": exitp,
        "final_bps": final_bps,
        "mfe_bps": mfe_bps,
        "mae_bps": mae_bps,
        "touch_target_50bps": bool(mfe_bps >= 50),
        "touch_target_100bps": bool(mfe_bps >= 100),
        "touch_target_150bps": bool(mfe_bps >= 150),
        "touch_stop_50bps": bool(mae_bps <= -50),
        "touch_stop_100bps": bool(mae_bps <= -100),
        "touch_stop_150bps": bool(mae_bps <= -150),
    }


def mean_or_nan(s: pd.Series) -> float:
    return float(pd.to_numeric(s, errors="coerce").mean()) if len(s) else float("nan")


def pct_true(s: pd.Series) -> float:
    return float(pd.Series(s).astype(bool).mean() * 100.0) if len(s) else float("nan")


def leave_one_year_out_min(events: pd.DataFrame, value_col: str) -> Tuple[float, Dict[str, float]]:
    if events.empty or "year" not in events:
        return float("nan"), {}
    years = sorted(int(y) for y in pd.Series(events["year"]).dropna().unique())
    vals: Dict[str, float] = {}
    for y in years:
        sub = events[events["year"] != y]
        if not sub.empty:
            vals[str(y)] = mean_or_nan(sub[value_col])
    return (min(vals.values()) if vals else float("nan"), vals)


def chronological_segments(events: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    ev = events.sort_values("entry_ts").reset_index(drop=True)
    n = len(ev)
    if n == 0:
        return {}
    q1 = n // 4
    q2 = n // 2
    q3 = (3 * n) // 4
    train_cut = max(1, int(math.floor(n * 0.67)))
    recent_cut = max(0, int(math.floor(n * 0.67)))
    return {
        "train": ev.iloc[:train_cut],
        "oos": ev.iloc[train_cut:],
        "first_half": ev.iloc[:q2],
        "second_half": ev.iloc[q2:],
        "q1": ev.iloc[:q1],
        "q2": ev.iloc[q1:q2],
        "q3": ev.iloc[q2:q3],
        "q4": ev.iloc[q3:],
        "recent_third": ev.iloc[recent_cut:],
    }


def summarize_events(events: pd.DataFrame, prefix: str = "") -> Dict[str, Any]:
    if events.empty:
        return {f"{prefix}n": 0}
    out: Dict[str, Any] = {
        f"{prefix}n": int(len(events)),
        f"{prefix}mean_final_bps": mean_or_nan(events["final_bps"]),
        f"{prefix}median_final_bps": float(pd.to_numeric(events["final_bps"], errors="coerce").median()),
        f"{prefix}cost_mean_bps": mean_or_nan(events["cost_stressed_final_bps"]),
        f"{prefix}hit_rate_pct": pct_true(pd.to_numeric(events["cost_stressed_final_bps"], errors="coerce") > 0),
        f"{prefix}median_mae_bps": float(pd.to_numeric(events["mae_bps"], errors="coerce").median()),
        f"{prefix}median_mfe_bps": float(pd.to_numeric(events["mfe_bps"], errors="coerce").median()),
        f"{prefix}touch_stop_100bps_pct": pct_true(events["touch_stop_100bps"]),
        f"{prefix}touch_target_100bps_pct": pct_true(events["touch_target_100bps"]),
        f"{prefix}mean_after_cost_plus_slip16_bps": mean_or_nan(events["cost_stressed_final_bps"]) - 16.0,
    }
    return out


def compute_benchmarks(df: pd.DataFrame, horizons: Sequence[int]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    daily_idx = df[df["hour_utc"] == 0].index.tolist()
    for h in horizons:
        long_ret = (df["close"].shift(-h) / df["close"] - 1.0) * 10000.0
        long_mean = mean_or_nan(long_ret.dropna())
        daily_long = long_ret.loc[[i for i in daily_idx if i + h < len(df)]].dropna()
        daily_mean = mean_or_nan(daily_long)
        out[str(h)] = {
            "h1_all_count": int(long_ret.notna().sum()),
            "h1_all_long_mean_bps": long_mean,
            "h1_all_short_mean_bps": -long_mean if np.isfinite(long_mean) else float("nan"),
            "daily_anchor_count": int(daily_long.notna().sum()),
            "daily_anchor_long_mean_bps": daily_mean,
            "daily_anchor_short_mean_bps": -daily_mean if np.isfinite(daily_mean) else float("nan"),
        }
    return out


def classify_row(row: Dict[str, Any], args: argparse.Namespace) -> str:
    n = row.get("event_clock_n", 0)
    if n < args.min_events:
        return "INSUFFICIENT_EVENTS_RESEARCH_ONLY"
    hard_fail_reasons = row.get("hard_fail_reasons", "")
    if hard_fail_reasons:
        return "FAIL_BENCHMARK_OR_STABILITY_RESEARCH_ONLY"
    if row.get("h1_benchmark_cost_adjusted_residual_bps", -1e9) >= args.strict_min_h1_cost_residual_bps:
        return "STRICT_PARALLEL_THESIS_WATCH_ONLY_NO_PROMOTION"
    if row.get("h1_benchmark_cost_adjusted_residual_bps", -1e9) >= args.soft_min_h1_cost_residual_bps:
        return "SOFT_PARALLEL_THESIS_WATCH_ONLY_NO_PROMOTION"
    return "FAIL_BENCHMARK_RESEARCH_ONLY"


def evaluate_spec(df: pd.DataFrame, spec: CandidateSpec, benchmarks: Dict[str, Any], cost_bps: float, args: argparse.Namespace) -> Tuple[Dict[str, Any], pd.DataFrame]:
    raw_idx = build_candidate_indices(df, spec)
    ec_idx = event_clock(raw_idx, spec.horizon, len(df))
    rows: List[Dict[str, Any]] = []
    for idx in ec_idx:
        m = forward_path_metrics(df, idx, spec.horizon, spec.side)
        if not m:
            continue
        base = df.iloc[idx]
        r = {
            "stage": STAGE,
            "decision_scope": DECISION_SCOPE,
            "promotion": NO_GO,
            "ea": NO_GO,
            "paper_live": NO_GO,
            "live": NO_GO,
            "family": spec.family,
            "candidate": spec.candidate,
            "side": spec.side,
            "trigger": spec.trigger,
            "horizon_hours": spec.horizon,
            "params_json": json.dumps(spec.params, sort_keys=True),
            "year": int(base["year"]),
            "month": int(base["month"]),
            "hour_utc": int(base["hour_utc"]),
            "weekday": str(base["weekday"]),
            "session_utc": str(base["session_utc"]),
            "atr24_bps": float(base.get("atr24_bps", np.nan)),
            "ret24_bps": float(base.get("ret24_bps", np.nan)),
            "ret72_bps": float(base.get("ret72_bps", np.nan)),
            "spread": float(base.get("spread", np.nan)) if pd.notna(base.get("spread", np.nan)) else np.nan,
        }
        r.update(m)
        r["cost_stressed_final_bps"] = r["final_bps"] - cost_bps
        rows.append(r)
    ev = pd.DataFrame(rows)

    hbench = benchmarks[str(spec.horizon)]
    directional_h1 = hbench["h1_all_long_mean_bps"] if spec.side == "LONG" else hbench["h1_all_short_mean_bps"]
    directional_daily = hbench["daily_anchor_long_mean_bps"] if spec.side == "LONG" else hbench["daily_anchor_short_mean_bps"]

    summary: Dict[str, Any] = {
        "stage": STAGE,
        "decision_scope": DECISION_SCOPE,
        "promotion": NO_GO,
        "ea": NO_GO,
        "paper_live": NO_GO,
        "live": NO_GO,
        "family": spec.family,
        "candidate": spec.candidate,
        "side": spec.side,
        "trigger": spec.trigger,
        "horizon_hours": spec.horizon,
        "params_json": json.dumps(spec.params, sort_keys=True),
        "raw_trigger_count": int(len(raw_idx)),
        "event_clock_n": int(len(ev)),
        "round_trip_cost_bps": cost_bps,
        "directional_h1_all_drift_bps": directional_h1,
        "directional_daily_anchor_drift_bps": directional_daily,
    }

    if ev.empty:
        summary.update({
            "event_clock_mean_bps": np.nan,
            "cost_stressed_mean_bps": np.nan,
            "h1_benchmark_cost_adjusted_residual_bps": np.nan,
            "daily_anchor_cost_adjusted_residual_bps": np.nan,
            "hard_fail_reasons": "no_event_clock_events",
            "classification": "INSUFFICIENT_EVENTS_RESEARCH_ONLY",
        })
        return summary, ev

    summary.update(summarize_events(ev, ""))
    summary["event_clock_mean_bps"] = summary.pop("mean_final_bps")
    summary["event_clock_median_bps"] = summary.pop("median_final_bps")
    summary["cost_stressed_mean_bps"] = summary.pop("cost_mean_bps")
    summary["event_clock_hit_rate_pct"] = summary.pop("hit_rate_pct")
    summary["median_mae_bps"] = summary.pop("median_mae_bps")
    summary["median_mfe_bps"] = summary.pop("median_mfe_bps")
    summary["touch_stop_100bps_pct"] = summary.pop("touch_stop_100bps_pct")
    summary["touch_target_100bps_pct"] = summary.pop("touch_target_100bps_pct")
    summary["mean_after_cost_plus_slip16_bps"] = summary.pop("mean_after_cost_plus_slip16_bps")

    summary["h1_drift_adjusted_residual_bps"] = summary["event_clock_mean_bps"] - directional_h1
    summary["daily_anchor_adjusted_residual_bps"] = summary["event_clock_mean_bps"] - directional_daily
    summary["h1_benchmark_cost_adjusted_residual_bps"] = summary["cost_stressed_mean_bps"] - directional_h1
    summary["daily_anchor_cost_adjusted_residual_bps"] = summary["cost_stressed_mean_bps"] - directional_daily
    pre2025 = ev[ev["year"] < 2025]
    ex2025 = ev[ev["year"] != 2025]
    y2025 = ev[ev["year"] == 2025]
    summary["pre2025_n"] = int(len(pre2025))
    summary["pre2025_cost_mean_bps"] = mean_or_nan(pre2025["cost_stressed_final_bps"])
    summary["ex2025_n"] = int(len(ex2025))
    summary["ex2025_cost_mean_bps"] = mean_or_nan(ex2025["cost_stressed_final_bps"])
    summary["y2025_n"] = int(len(y2025))
    summary["y2025_cost_mean_bps"] = mean_or_nan(y2025["cost_stressed_final_bps"])
    loyo_min, loyo = leave_one_year_out_min(ev, "cost_stressed_final_bps")
    summary["leave_one_year_out_min_cost_mean_bps"] = loyo_min
    summary["leave_one_year_out_json"] = json.dumps(loyo, sort_keys=True)
    year_means = ev.groupby("year")["cost_stressed_final_bps"].mean().to_dict()
    year_counts = ev.groupby("year").size().to_dict()
    summary["year_cost_mean_json"] = json.dumps({str(k): float(v) for k, v in year_means.items()}, sort_keys=True)
    summary["year_counts_json"] = json.dumps({str(k): int(v) for k, v in year_counts.items()}, sort_keys=True)

    segments = chronological_segments(ev)
    split_records = {}
    for name, seg in segments.items():
        split_records[name] = summarize_events(seg, "")
        summary[f"{name}_n"] = int(len(seg))
        summary[f"{name}_cost_mean_bps"] = mean_or_nan(seg["cost_stressed_final_bps"]) if len(seg) else np.nan
        summary[f"{name}_slip16_mean_bps"] = summary[f"{name}_cost_mean_bps"] - 16.0 if np.isfinite(summary[f"{name}_cost_mean_bps"]) else np.nan
        summary[f"{name}_hit_rate_pct"] = pct_true(pd.to_numeric(seg["cost_stressed_final_bps"], errors="coerce") > 0) if len(seg) else np.nan
        summary[f"{name}_median_mae_bps"] = float(pd.to_numeric(seg["mae_bps"], errors="coerce").median()) if len(seg) else np.nan
    q_costs = [summary.get(f"q{i}_cost_mean_bps", np.nan) for i in [1, 2, 3, 4]]
    q_slip16 = [summary.get(f"q{i}_slip16_mean_bps", np.nan) for i in [1, 2, 3, 4]]
    summary["worst_quarter_cost_mean_bps"] = float(np.nanmin(q_costs)) if any(np.isfinite(q_costs)) else np.nan
    summary["worst_quarter_slip16_mean_bps"] = float(np.nanmin(q_slip16)) if any(np.isfinite(q_slip16)) else np.nan

    fail_reasons: List[str] = []
    if summary["event_clock_n"] < args.min_events:
        fail_reasons.append("min_events")
    if summary.get("train_n", 0) < args.min_train_events:
        fail_reasons.append("min_train_events")
    if summary.get("oos_n", 0) < args.min_oos_events:
        fail_reasons.append("min_oos_events")
    if summary["h1_benchmark_cost_adjusted_residual_bps"] < args.soft_min_h1_cost_residual_bps:
        fail_reasons.append("h1_cost_residual_floor")
    if summary["ex2025_cost_mean_bps"] < args.min_ex2025_cost_mean_bps:
        fail_reasons.append("ex2025_floor")
    if summary["leave_one_year_out_min_cost_mean_bps"] < args.min_loyo_cost_mean_bps:
        fail_reasons.append("loyo_floor")
    if summary.get("train_cost_mean_bps", -1e9) < args.min_train_cost_mean_bps:
        fail_reasons.append("train_cost_floor")
    if summary.get("oos_cost_mean_bps", -1e9) < args.min_oos_cost_mean_bps:
        fail_reasons.append("oos_cost_floor")
    if summary.get("worst_quarter_cost_mean_bps", -1e9) < args.min_worst_quarter_cost_bps:
        fail_reasons.append("worst_quarter_cost_floor")
    if summary.get("worst_quarter_slip16_mean_bps", -1e9) < args.min_worst_quarter_slip16_bps:
        fail_reasons.append("worst_quarter_slip16_floor")
    if abs(summary.get("median_mae_bps", 0.0)) > args.max_median_mae_abs_bps:
        fail_reasons.append("median_mae_cap")
    if summary.get("touch_stop_100bps_pct", 0.0) > args.max_touch_stop_100_pct:
        fail_reasons.append("stop100_cap")
    summary["hard_fail_reasons"] = ";".join(fail_reasons)
    summary["classification"] = classify_row(summary, args)
    ev["candidate_classification"] = summary["classification"]
    return summary, ev


def write_markdown(out_path: Path, summary_json: Dict[str, Any], top: pd.DataFrame, family: pd.DataFrame) -> None:
    lines: List[str] = []
    lines.append(f"# {STAGE}")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    lines.append(f"scope = {DECISION_SCOPE}")
    lines.append("promotion = NO_GO")
    lines.append("EA = NO_GO")
    lines.append("paper_live = NO_GO")
    lines.append("live = NO_GO")
    lines.append("```")
    lines.append("")
    lines.append("Stage40 is a parallel benchmark-first research scan across independent theses. It is not a promotion gate.")
    lines.append("")
    lines.append("## Classification counts")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(summary_json.get("classification_counts", {}), indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append("## Thesis family summary")
    lines.append("")
    if family.empty:
        lines.append("No family summary rows.")
    else:
        lines.append(family.to_markdown(index=False))
    lines.append("")
    lines.append("## Top rows by benchmark-cost residual")
    lines.append("")
    if top.empty:
        lines.append("No rows.")
    else:
        cols = [
            "classification", "family", "candidate", "side", "horizon_hours", "event_clock_n",
            "cost_stressed_mean_bps", "h1_benchmark_cost_adjusted_residual_bps", "ex2025_cost_mean_bps",
            "leave_one_year_out_min_cost_mean_bps", "train_cost_mean_bps", "oos_cost_mean_bps",
            "worst_quarter_cost_mean_bps", "median_mae_bps", "touch_stop_100bps_pct", "hard_fail_reasons",
        ]
        cols = [c for c in cols if c in top.columns]
        lines.append(top[cols].head(40).to_markdown(index=False))
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("- `STRICT_PARALLEL_THESIS_WATCH_ONLY_NO_PROMOTION` means the row may enter a later dedicated audit, not trading.")
    lines.append("- `SOFT_PARALLEL_THESIS_WATCH_ONLY_NO_PROMOTION` means weak research watch only.")
    lines.append("- `FAIL_*` and `INSUFFICIENT_*` rows should not be extended with filters.")
    lines.append("- Any next step must freeze a small number of rows and re-audit path, condition, OOS, and recency bias.")
    lines.append("")
    lines.append("## Next allowed step")
    lines.append("")
    lines.append("If strict rows exist: `Stage40B_DEDICATED_SURVIVOR_AUDIT`. Otherwise archive Stage40 megascan.")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def parse_csv_ints(s: str) -> List[int]:
    return [int(x.strip()) for x in str(s).split(",") if x.strip()]


def run(args: argparse.Namespace) -> None:
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    bars, data_audit = read_bars(args.db, args.table, args.symbol, args.source, args.timeframe, args.max_rows)
    df = add_features(bars)
    horizons = parse_csv_ints(args.horizons)
    benchmarks = compute_benchmarks(df, horizons)
    specs = generate_specs(horizons)

    summaries: List[Dict[str, Any]] = []
    events_parts: List[pd.DataFrame] = []
    for spec in specs:
        try:
            summary, ev = evaluate_spec(df, spec, benchmarks, args.cost_bps, args)
        except Exception as exc:
            summary = {
                "stage": STAGE, "decision_scope": DECISION_SCOPE, "promotion": NO_GO,
                "ea": NO_GO, "paper_live": NO_GO, "live": NO_GO,
                "family": spec.family, "candidate": spec.candidate, "side": spec.side,
                "trigger": spec.trigger, "horizon_hours": spec.horizon,
                "params_json": json.dumps(spec.params, sort_keys=True),
                "raw_trigger_count": 0, "event_clock_n": 0,
                "hard_fail_reasons": f"exception:{type(exc).__name__}:{exc}",
                "classification": "ERROR_RESEARCH_ONLY_NO_PROMOTION",
            }
            ev = pd.DataFrame()
        summaries.append(summary)
        if not ev.empty:
            events_parts.append(ev)

    summary_df = pd.DataFrame(summaries)
    # Stable sort: strict/watch first then residual.
    class_rank = {
        "STRICT_PARALLEL_THESIS_WATCH_ONLY_NO_PROMOTION": 0,
        "SOFT_PARALLEL_THESIS_WATCH_ONLY_NO_PROMOTION": 1,
        "FAIL_BENCHMARK_OR_STABILITY_RESEARCH_ONLY": 2,
        "FAIL_BENCHMARK_RESEARCH_ONLY": 3,
        "INSUFFICIENT_EVENTS_RESEARCH_ONLY": 4,
        "ERROR_RESEARCH_ONLY_NO_PROMOTION": 5,
    }
    summary_df["_class_rank"] = summary_df["classification"].map(class_rank).fillna(9)
    if "h1_benchmark_cost_adjusted_residual_bps" in summary_df.columns:
        summary_df = summary_df.sort_values(["_class_rank", "h1_benchmark_cost_adjusted_residual_bps"], ascending=[True, False])
    summary_df = summary_df.drop(columns=["_class_rank"]).reset_index(drop=True)
    event_df = pd.concat(events_parts, ignore_index=True) if events_parts else pd.DataFrame()

    family_rows = []
    for fam, g in summary_df.groupby("family", dropna=False):
        family_rows.append({
            "family": fam,
            "candidate_rows": int(len(g)),
            "strict_watch_count": int((g["classification"] == "STRICT_PARALLEL_THESIS_WATCH_ONLY_NO_PROMOTION").sum()),
            "soft_watch_count": int((g["classification"] == "SOFT_PARALLEL_THESIS_WATCH_ONLY_NO_PROMOTION").sum()),
            "max_h1_cost_residual_bps": float(pd.to_numeric(g.get("h1_benchmark_cost_adjusted_residual_bps"), errors="coerce").max()),
            "best_candidate": str(g.iloc[0].get("candidate", "")) if len(g) else "",
        })
    family_df = pd.DataFrame(family_rows).sort_values(["strict_watch_count", "soft_watch_count", "max_h1_cost_residual_bps"], ascending=[False, False, False])

    csv_path = out_dir / "stage40_parallel_thesis_megascan_summary.csv"
    events_path = out_dir / "stage40_parallel_thesis_megascan_events.csv"
    family_path = out_dir / "stage40_parallel_thesis_family_summary.csv"
    json_path = out_dir / "stage40_parallel_thesis_megascan_summary.json"
    md_path = out_dir / "stage40_parallel_thesis_megascan.md"

    summary_df.to_csv(csv_path, index=False)
    event_df.to_csv(events_path, index=False)
    family_df.to_csv(family_path, index=False)

    classification_counts = summary_df["classification"].value_counts(dropna=False).to_dict()
    result = {
        "stage": STAGE,
        "decision_scope": DECISION_SCOPE,
        "promotion": NO_GO,
        "ea": NO_GO,
        "paper_live": NO_GO,
        "live": NO_GO,
        "data_audit": data_audit,
        "parameters": vars(args),
        "benchmarks": benchmarks,
        "candidate_rows": int(len(summary_df)),
        "events_rows_written": int(len(event_df)),
        "classification_counts": {str(k): int(v) for k, v in classification_counts.items()},
        "strict_parallel_thesis_watch_count": int((summary_df["classification"] == "STRICT_PARALLEL_THESIS_WATCH_ONLY_NO_PROMOTION").sum()),
        "soft_parallel_thesis_watch_count": int((summary_df["classification"] == "SOFT_PARALLEL_THESIS_WATCH_ONLY_NO_PROMOTION").sum()),
        "outputs": {
            "summary_csv": str(csv_path),
            "events_csv": str(events_path),
            "family_summary_csv": str(family_path),
            "summary_json": str(json_path),
            "markdown": str(md_path),
        },
        "top_rows_by_h1_benchmark_cost_residual": json.loads(summary_df.head(30).replace({np.nan: None}).to_json(orient="records")),
    }
    json_path.write_text(json.dumps(result, indent=2, sort_keys=False, default=str), encoding="utf-8")
    write_markdown(md_path, result, summary_df.head(40), family_df)
    print(json.dumps({"stage": STAGE, "classification_counts": result["classification_counts"], "outputs": result["outputs"]}, indent=2))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stage40 parallel thesis benchmark-first mega-scan")
    p.add_argument("--db", default="data/local/xauusd_local_store.sqlite")
    p.add_argument("--table", default="bars")
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--source", default="amarkets_mt5")
    p.add_argument("--timeframe", default="H1")
    p.add_argument("--horizons", default="4,8,24,72")
    p.add_argument("--cost-bps", type=float, default=8.0)
    p.add_argument("--max-rows", type=int, default=None)
    p.add_argument("--output-dir", default="reports/stage40")
    # Gate parameters. These are strict enough to avoid Stage39-style recency/overfit promotion.
    p.add_argument("--min-events", type=int, default=40)
    p.add_argument("--min-train-events", type=int, default=20)
    p.add_argument("--min-oos-events", type=int, default=10)
    p.add_argument("--soft-min-h1-cost-residual-bps", type=float, default=5.0)
    p.add_argument("--strict-min-h1-cost-residual-bps", type=float, default=15.0)
    p.add_argument("--min-ex2025-cost-mean-bps", type=float, default=5.0)
    p.add_argument("--min-loyo-cost-mean-bps", type=float, default=0.0)
    p.add_argument("--min-train-cost-mean-bps", type=float, default=0.0)
    p.add_argument("--min-oos-cost-mean-bps", type=float, default=0.0)
    p.add_argument("--min-worst-quarter-cost-bps", type=float, default=-10.0)
    p.add_argument("--min-worst-quarter-slip16-bps", type=float, default=-25.0)
    p.add_argument("--max-median-mae-abs-bps", type=float, default=150.0)
    p.add_argument("--max-touch-stop-100-pct", type=float, default=60.0)
    return p.parse_args()


def main() -> None:
    run(parse_args())


if __name__ == "__main__":
    main()
