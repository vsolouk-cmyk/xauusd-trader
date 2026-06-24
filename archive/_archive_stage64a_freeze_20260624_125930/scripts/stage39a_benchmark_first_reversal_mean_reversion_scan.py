#!/usr/bin/env python3
"""
Stage39A_BENCHMARK_FIRST_REVERSAL_OR_MEAN_REVERSION_SCAN

Research-stage scanner only. This script does NOT promote any candidate to EA,
paper-live, or live. It starts a clean benchmark-first scan after Stage38I.

Core idea:
- Stage38 showed bull drift dominates many positive long-forward returns.
- Stage39A scans reversal/mean-reversion hypotheses only after benchmarking each
  candidate against unconditional direction-matched H1 drift and daily anchor drift.
- Output classifications are watch/fail/insufficient only; promotion is hard NO-GO.

Expected default repository context:
    repo: ~/Desktop/xauusd-trader
    db:   data/local/xauusd_local_store.sqlite
    table: bars
    symbol: XAUUSD
    source: amarkets_mt5
    timeframe: H1

Outputs:
    reports/stage39a/stage39a_reversal_mean_reversion_scan.csv
    reports/stage39a/stage39a_reversal_mean_reversion_scan_summary.json
    reports/stage39a/stage39a_reversal_mean_reversion_scan.md
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


STAGE_LABEL = "Stage39A_BENCHMARK_FIRST_REVERSAL_OR_MEAN_REVERSION_SCAN"
RESEARCH_DECISION = "RESEARCH_STAGE_ONLY_NO_PROMOTION"


TIMESTAMP_CANDIDATES = [
    # Project-local bars schema uses utc_time. Keep it near the top so DB-first
    # introspection works without requiring a manual column override.
    "ts_utc", "utc_time", "timestamp_utc", "time_utc", "datetime_utc", "date_utc",
    "ts", "timestamp", "time", "datetime", "date", "open_time", "bar_time",
]
SYMBOL_CANDIDATES = ["symbol", "pair", "instrument"]
SOURCE_CANDIDATES = ["source", "broker", "provider", "feed"]
TIMEFRAME_CANDIDATES = ["timeframe", "tf", "interval", "frame"]
OPEN_CANDIDATES = ["open", "o", "bid_open", "ask_open", "mid_open"]
HIGH_CANDIDATES = ["high", "h", "bid_high", "ask_high", "mid_high"]
LOW_CANDIDATES = ["low", "l", "bid_low", "ask_low", "mid_low"]
CLOSE_CANDIDATES = ["close", "c", "bid_close", "ask_close", "mid_close"]
SPREAD_CANDIDATES = ["spread", "spread_points", "spread_bps", "ask_bid_spread", "bid_ask_spread"]


@dataclass(frozen=True)
class CandidateSpec:
    name: str
    family: str
    side: str  # LONG or SHORT
    lookback_hours: Optional[int]
    trigger_description: str
    mask_builder: Callable[[pd.DataFrame], pd.Series]


def _norm_col(s: str) -> str:
    return str(s).strip().lower()


def pick_col(columns: Sequence[str], candidates: Sequence[str], required: bool = False) -> Optional[str]:
    by_norm = {_norm_col(c): c for c in columns}
    for cand in candidates:
        if _norm_col(cand) in by_norm:
            return by_norm[_norm_col(cand)]
    if required:
        raise ValueError(
            "Required column not found. "
            f"Tried candidates={list(candidates)}; available={list(columns)}. "
            "If the local DB uses a project-specific timestamp name, add it to TIMESTAMP_CANDIDATES."
        )
    return None


def safe_float_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype(float)


def parse_timestamp_series(s: pd.Series) -> pd.Series:
    # Handles ISO strings, pandas timestamps, and Unix seconds/milliseconds.
    if pd.api.types.is_numeric_dtype(s):
        vals = pd.to_numeric(s, errors="coerce")
        median_val = vals.dropna().median()
        if pd.isna(median_val):
            return pd.to_datetime(s, errors="coerce", utc=True)
        # Rough heuristic for epoch ms vs seconds.
        unit = "ms" if median_val > 10_000_000_000 else "s"
        return pd.to_datetime(vals, unit=unit, errors="coerce", utc=True)
    return pd.to_datetime(s, errors="coerce", utc=True)


def sqlite_tables(db_path: Path) -> List[str]:
    with sqlite3.connect(str(db_path)) as con:
        rows = con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    return [r[0] for r in rows]


def read_bars(
    db_path: Path,
    table: str,
    symbol: str,
    source: str,
    timeframe: str,
    max_rows: Optional[int] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite DB not found: {db_path}")

    tables = sqlite_tables(db_path)
    if table not in tables:
        raise ValueError(f"Table '{table}' not found in {db_path}. Available tables: {tables}")

    with sqlite3.connect(str(db_path)) as con:
        cols = pd.read_sql_query(f"PRAGMA table_info({table})", con)
        available_cols = cols["name"].tolist()
        ts_col = pick_col(available_cols, TIMESTAMP_CANDIDATES, required=True)
        open_col = pick_col(available_cols, OPEN_CANDIDATES, required=False)
        high_col = pick_col(available_cols, HIGH_CANDIDATES, required=False)
        low_col = pick_col(available_cols, LOW_CANDIDATES, required=False)
        close_col = pick_col(available_cols, CLOSE_CANDIDATES, required=True)
        symbol_col = pick_col(available_cols, SYMBOL_CANDIDATES, required=False)
        source_col = pick_col(available_cols, SOURCE_CANDIDATES, required=False)
        timeframe_col = pick_col(available_cols, TIMEFRAME_CANDIDATES, required=False)
        spread_col = pick_col(available_cols, SPREAD_CANDIDATES, required=False)

        sql = f"SELECT * FROM {table}"
        if max_rows is not None and max_rows > 0:
            sql += f" LIMIT {int(max_rows)}"
        raw = pd.read_sql_query(sql, con)

    meta = {
        "db_path": str(db_path),
        "table": table,
        "available_columns": available_cols,
        "columns": {
            "timestamp": ts_col,
            "open": open_col,
            "high": high_col,
            "low": low_col,
            "close": close_col,
            "symbol": symbol_col,
            "source": source_col,
            "timeframe": timeframe_col,
            "spread": spread_col,
        },
    }

    df = raw.copy()
    if symbol_col is not None:
        df = df[df[symbol_col].astype(str).str.upper().eq(symbol.upper())]
    if source_col is not None:
        df = df[df[source_col].astype(str).str.lower().eq(source.lower())]
    if timeframe_col is not None:
        tf_norm = timeframe.upper()
        allowed = {tf_norm, "1H" if tf_norm == "H1" else tf_norm, "60M", "60MIN", "60MINUTE", "1HR", "1HOUR"}
        df = df[df[timeframe_col].astype(str).str.upper().isin(allowed)]

    out = pd.DataFrame()
    out["ts_utc"] = parse_timestamp_series(df[ts_col])
    out["close"] = safe_float_series(df[close_col])
    out["open"] = safe_float_series(df[open_col]) if open_col else out["close"]
    out["high"] = safe_float_series(df[high_col]) if high_col else out[["open", "close"]].max(axis=1)
    out["low"] = safe_float_series(df[low_col]) if low_col else out[["open", "close"]].min(axis=1)
    if spread_col:
        out["spread_raw"] = safe_float_series(df[spread_col])
    else:
        out["spread_raw"] = np.nan

    out = out.dropna(subset=["ts_utc", "close"]).sort_values("ts_utc")
    out = out.drop_duplicates(subset=["ts_utc"], keep="last").reset_index(drop=True)

    if out.empty:
        raise ValueError(
            f"No rows after filtering table={table}, symbol={symbol}, source={source}, timeframe={timeframe}. "
            f"Detected columns={meta['columns']}"
        )

    meta["loaded_rows"] = int(len(out))
    meta["date_min"] = out["ts_utc"].min().isoformat()
    meta["date_max"] = out["ts_utc"].max().isoformat()
    return out, meta


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    x["hour"] = x["ts_utc"].dt.hour
    x["year"] = x["ts_utc"].dt.year
    x["ret_1h_bps"] = (x["close"] / x["close"].shift(1) - 1.0) * 10_000.0

    for lb in [6, 12, 24, 48, 72, 120]:
        ret_col = f"past_ret_{lb}h_bps"
        x[ret_col] = (x["close"] / x["close"].shift(lb) - 1.0) * 10_000.0
        z_win = max(lb * 5, 100)
        mean = x[ret_col].rolling(z_win, min_periods=max(30, lb)).mean()
        std = x[ret_col].rolling(z_win, min_periods=max(30, lb)).std()
        x[f"past_ret_{lb}h_z"] = (x[ret_col] - mean) / std.replace(0, np.nan)

    for win in [24, 48, 72, 120]:
        roll_hi = x["high"].rolling(win, min_periods=max(12, win // 2)).max()
        roll_lo = x["low"].rolling(win, min_periods=max(12, win // 2)).min()
        denom = (roll_hi - roll_lo).replace(0, np.nan)
        x[f"range_pos_{win}h"] = (x["close"] - roll_lo) / denom

        ma = x["close"].rolling(win, min_periods=max(12, win // 2)).mean()
        sd = x["close"].rolling(win, min_periods=max(12, win // 2)).std()
        x[f"bb_z_{win}h"] = (x["close"] - ma) / sd.replace(0, np.nan)

    x["rsi_14"] = compute_rsi(x["close"], 14)
    x["rsi_28"] = compute_rsi(x["close"], 28)

    if x["spread_raw"].notna().sum() > 100:
        s = x["spread_raw"]
        mu = s.rolling(240, min_periods=60).mean()
        sd = s.rolling(240, min_periods=60).std()
        x["spread_z_240h"] = (s - mu) / sd.replace(0, np.nan)
    else:
        x["spread_z_240h"] = np.nan

    return x


def build_candidate_specs() -> List[CandidateSpec]:
    specs: List[CandidateSpec] = []

    for lb in [24, 72, 120]:
        for thr in [1.5, 2.0, 2.5]:
            z_col = f"past_ret_{lb}h_z"
            specs.append(
                CandidateSpec(
                    name=f"RET_Z_DOWNSIDE_EXTREME_REV_LONG_L{lb}_T{thr:g}",
                    family="RETURN_ZSCORE_REVERSAL",
                    side="LONG",
                    lookback_hours=lb,
                    trigger_description=f"Long after {lb}H downside move with z <= -{thr:g}",
                    mask_builder=lambda d, z_col=z_col, thr=thr: d[z_col] <= -thr,
                )
            )
            specs.append(
                CandidateSpec(
                    name=f"RET_Z_UPSIDE_EXTREME_REV_SHORT_L{lb}_T{thr:g}",
                    family="RETURN_ZSCORE_REVERSAL",
                    side="SHORT",
                    lookback_hours=lb,
                    trigger_description=f"Short after {lb}H upside move with z >= +{thr:g}",
                    mask_builder=lambda d, z_col=z_col, thr=thr: d[z_col] >= thr,
                )
            )

    for win in [24, 48, 72, 120]:
        pos_col = f"range_pos_{win}h"
        for q in [0.05, 0.10]:
            specs.append(
                CandidateSpec(
                    name=f"RANGE_BOTTOM_REV_LONG_W{win}_Q{q:g}",
                    family="ROLLING_RANGE_REVERSAL",
                    side="LONG",
                    lookback_hours=win,
                    trigger_description=f"Long near bottom {q:g} of rolling {win}H range",
                    mask_builder=lambda d, pos_col=pos_col, q=q: d[pos_col] <= q,
                )
            )
            specs.append(
                CandidateSpec(
                    name=f"RANGE_TOP_REV_SHORT_W{win}_Q{q:g}",
                    family="ROLLING_RANGE_REVERSAL",
                    side="SHORT",
                    lookback_hours=win,
                    trigger_description=f"Short near top {1-q:g} of rolling {win}H range",
                    mask_builder=lambda d, pos_col=pos_col, q=q: d[pos_col] >= (1.0 - q),
                )
            )

    for period, col in [(14, "rsi_14"), (28, "rsi_28")]:
        for low_thr in [25, 30]:
            specs.append(
                CandidateSpec(
                    name=f"RSI_OVERSOLD_REV_LONG_RSI{period}_T{low_thr}",
                    family="RSI_REVERSAL",
                    side="LONG",
                    lookback_hours=period,
                    trigger_description=f"Long when RSI{period} <= {low_thr}",
                    mask_builder=lambda d, col=col, low_thr=low_thr: d[col] <= low_thr,
                )
            )
        for high_thr in [70, 75]:
            specs.append(
                CandidateSpec(
                    name=f"RSI_OVERBOUGHT_REV_SHORT_RSI{period}_T{high_thr}",
                    family="RSI_REVERSAL",
                    side="SHORT",
                    lookback_hours=period,
                    trigger_description=f"Short when RSI{period} >= {high_thr}",
                    mask_builder=lambda d, col=col, high_thr=high_thr: d[col] >= high_thr,
                )
            )

    for win in [24, 48, 72, 120]:
        bb_col = f"bb_z_{win}h"
        for k in [2.0, 2.5]:
            specs.append(
                CandidateSpec(
                    name=f"BB_LOWER_REV_LONG_W{win}_K{k:g}",
                    family="BOLLINGER_REVERSAL",
                    side="LONG",
                    lookback_hours=win,
                    trigger_description=f"Long when close is <= -{k:g} sigma vs {win}H rolling mean",
                    mask_builder=lambda d, bb_col=bb_col, k=k: d[bb_col] <= -k,
                )
            )
            specs.append(
                CandidateSpec(
                    name=f"BB_UPPER_REV_SHORT_W{win}_K{k:g}",
                    family="BOLLINGER_REVERSAL",
                    side="SHORT",
                    lookback_hours=win,
                    trigger_description=f"Short when close is >= +{k:g} sigma vs {win}H rolling mean",
                    mask_builder=lambda d, bb_col=bb_col, k=k: d[bb_col] >= k,
                )
            )

    # Optional spread-stress fade. It activates only if a spread column exists.
    specs.append(
        CandidateSpec(
            name="SPREAD_STRESS_AFTER_12H_DOWN_REV_LONG_Z2",
            family="SPREAD_STRESS_FADE",
            side="LONG",
            lookback_hours=12,
            trigger_description="Long after 12H downside move while spread_z_240h >= 2",
            mask_builder=lambda d: (d["spread_z_240h"] >= 2.0) & (d["past_ret_12h_z"] <= -1.0),
        )
    )
    specs.append(
        CandidateSpec(
            name="SPREAD_STRESS_AFTER_12H_UP_REV_SHORT_Z2",
            family="SPREAD_STRESS_FADE",
            side="SHORT",
            lookback_hours=12,
            trigger_description="Short after 12H upside move while spread_z_240h >= 2",
            mask_builder=lambda d: (d["spread_z_240h"] >= 2.0) & (d["past_ret_12h_z"] >= 1.0),
        )
    )

    return specs


def forward_return_bps(close: pd.Series, horizon_hours: int) -> pd.Series:
    return (close.shift(-horizon_hours) / close - 1.0) * 10_000.0


def daily_anchor_drift(df: pd.DataFrame, horizon_hours: int) -> Dict[str, float]:
    days = max(1, int(round(horizon_hours / 24)))
    daily = (
        df.set_index("ts_utc")["close"]
        .resample("1D")
        .last()
        .dropna()
    )
    fwd = (daily.shift(-days) / daily - 1.0) * 10_000.0
    return {
        "daily_anchor_count": int(fwd.dropna().shape[0]),
        "daily_anchor_long_mean_bps": float(fwd.mean()) if fwd.notna().any() else math.nan,
    }


def h1_all_drift(df: pd.DataFrame, horizon_hours: int) -> Dict[str, float]:
    fwd = forward_return_bps(df["close"], horizon_hours)
    return {
        "h1_all_count": int(fwd.dropna().shape[0]),
        "h1_all_long_mean_bps": float(fwd.mean()) if fwd.notna().any() else math.nan,
    }


def non_overlapping_indices(df: pd.DataFrame, mask: pd.Series, horizon_hours: int) -> List[int]:
    valid = df.loc[mask.fillna(False), ["ts_utc"]].copy()
    selected: List[int] = []
    next_allowed = None
    gap = pd.Timedelta(hours=horizon_hours)
    for idx, row in valid.iterrows():
        ts = row["ts_utc"]
        if next_allowed is None or ts >= next_allowed:
            selected.append(int(idx))
            next_allowed = ts + gap
    return selected


def split_stats(values: pd.Series) -> Dict[str, Any]:
    vals = pd.to_numeric(values, errors="coerce").dropna()
    if vals.empty:
        return {"n": 0, "mean_bps": math.nan, "median_bps": math.nan, "hit_rate_pct": math.nan}
    return {
        "n": int(vals.shape[0]),
        "mean_bps": float(vals.mean()),
        "median_bps": float(vals.median()),
        "hit_rate_pct": float((vals > 0).mean() * 100.0),
    }


def mae_mfe_stats(df: pd.DataFrame, selected_idx: Sequence[int], horizon_hours: int, side: str) -> Dict[str, float]:
    if not selected_idx:
        return {
            "median_mfe_bps": math.nan,
            "median_mae_bps": math.nan,
            "mean_mfe_bps": math.nan,
            "mean_mae_bps": math.nan,
        }

    side_mult = 1.0 if side == "LONG" else -1.0
    mfes: List[float] = []
    maes: List[float] = []

    for idx in selected_idx:
        if idx + horizon_hours >= len(df):
            continue
        entry = float(df.loc[idx, "close"])
        window = df.iloc[idx + 1 : idx + horizon_hours + 1]
        if window.empty or not np.isfinite(entry) or entry <= 0:
            continue

        if side == "LONG":
            mfe = (float(window["high"].max()) / entry - 1.0) * 10_000.0
            mae = (float(window["low"].min()) / entry - 1.0) * 10_000.0
        else:
            # Signed values from the short perspective.
            mfe = (entry / float(window["low"].min()) - 1.0) * 10_000.0
            mae = (entry / float(window["high"].max()) - 1.0) * 10_000.0

        if np.isfinite(mfe):
            mfes.append(mfe)
        if np.isfinite(mae):
            maes.append(mae)

    return {
        "median_mfe_bps": float(np.median(mfes)) if mfes else math.nan,
        "median_mae_bps": float(np.median(maes)) if maes else math.nan,
        "mean_mfe_bps": float(np.mean(mfes)) if mfes else math.nan,
        "mean_mae_bps": float(np.mean(maes)) if maes else math.nan,
    }


def leave_one_year_out_min(events: pd.DataFrame, value_col: str) -> Tuple[float, Dict[str, float]]:
    years = sorted(int(y) for y in events["year"].dropna().unique())
    out: Dict[str, float] = {}
    for y in years:
        vals = events.loc[events["year"] != y, value_col].dropna()
        out[str(y)] = float(vals.mean()) if not vals.empty else math.nan
    finite = [v for v in out.values() if np.isfinite(v)]
    return (float(min(finite)) if finite else math.nan, out)


def classify_result(
    *,
    event_n: int,
    min_events: int,
    event_clock_mean_bps: float,
    event_clock_cost_bps: float,
    benchmark_cost_residual_bps: float,
    ex2025_mean_bps: float,
    pre2025_mean_bps: float,
    first_half_mean_bps: float,
    second_half_mean_bps: float,
    loyo_min_bps: float,
    hit_rate_pct: float,
) -> str:
    if event_n < min_events:
        return "INSUFFICIENT_EVENTS_RESEARCH_ONLY"

    hard_pass = (
        np.isfinite(event_clock_mean_bps)
        and np.isfinite(event_clock_cost_bps)
        and np.isfinite(benchmark_cost_residual_bps)
        and event_clock_cost_bps > 0.0
        and benchmark_cost_residual_bps > 3.0
        and (not np.isfinite(ex2025_mean_bps) or ex2025_mean_bps > 0.0)
        and (not np.isfinite(pre2025_mean_bps) or pre2025_mean_bps > 0.0)
        and (not np.isfinite(first_half_mean_bps) or first_half_mean_bps > 0.0)
        and (not np.isfinite(second_half_mean_bps) or second_half_mean_bps > 0.0)
        and (not np.isfinite(loyo_min_bps) or loyo_min_bps > 0.0)
        and (not np.isfinite(hit_rate_pct) or hit_rate_pct >= 50.0)
    )
    if hard_pass:
        return "STRICT_RESEARCH_WATCH_ONLY_NO_PROMOTION"

    soft_watch = (
        np.isfinite(event_clock_cost_bps)
        and np.isfinite(benchmark_cost_residual_bps)
        and event_clock_cost_bps > 0.0
        and benchmark_cost_residual_bps > 0.0
    )
    if soft_watch:
        return "WATCH_ONLY_BENCHMARK_RESIDUAL_NO_PROMOTION"

    return "FAIL_BENCHMARK_RESEARCH_ONLY"


def evaluate_candidate(
    df: pd.DataFrame,
    spec: CandidateSpec,
    horizon_hours: int,
    h1_long_drift_bps: float,
    daily_long_drift_bps: float,
    cost_bps: float,
    min_events: int,
) -> Tuple[Dict[str, Any], Optional[pd.DataFrame]]:
    fwd_long = forward_return_bps(df["close"], horizon_hours)
    direction = 1.0 if spec.side == "LONG" else -1.0
    signed = fwd_long * direction

    mask = spec.mask_builder(df)
    mask = mask & signed.notna()

    raw_events = df.loc[mask.fillna(False), ["ts_utc", "year", "close"]].copy()
    raw_events["signed_forward_bps"] = signed.loc[raw_events.index]
    raw_stats = split_stats(raw_events["signed_forward_bps"])

    selected_idx = non_overlapping_indices(df, mask, horizon_hours)
    ev = df.loc[selected_idx, ["ts_utc", "year", "close"]].copy()
    ev["candidate"] = spec.name
    ev["family"] = spec.family
    ev["side"] = spec.side
    ev["horizon_hours"] = horizon_hours
    ev["signed_forward_bps"] = signed.loc[ev.index].values if selected_idx else []
    ev = ev.dropna(subset=["signed_forward_bps"])

    event_stats = split_stats(ev["signed_forward_bps"])
    mae_mfe = mae_mfe_stats(df, ev.index.tolist(), horizon_hours, spec.side)

    directional_h1_drift = h1_long_drift_bps if spec.side == "LONG" else -h1_long_drift_bps
    directional_daily_drift = daily_long_drift_bps if spec.side == "LONG" else -daily_long_drift_bps

    event_mean = event_stats["mean_bps"]
    event_cost = event_mean - cost_bps if np.isfinite(event_mean) else math.nan
    h1_resid = event_mean - directional_h1_drift if np.isfinite(event_mean) and np.isfinite(directional_h1_drift) else math.nan
    daily_resid = event_mean - directional_daily_drift if np.isfinite(event_mean) and np.isfinite(directional_daily_drift) else math.nan
    h1_cost_resid = h1_resid - cost_bps if np.isfinite(h1_resid) else math.nan

    pre2025_stats = split_stats(ev.loc[ev["year"] < 2025, "signed_forward_bps"])
    ex2025_stats = split_stats(ev.loc[ev["year"] != 2025, "signed_forward_bps"])
    y2025_stats = split_stats(ev.loc[ev["year"] == 2025, "signed_forward_bps"])

    if not ev.empty:
        mid_ts = ev["ts_utc"].min() + (ev["ts_utc"].max() - ev["ts_utc"].min()) / 2
        first_half_stats = split_stats(ev.loc[ev["ts_utc"] <= mid_ts, "signed_forward_bps"])
        second_half_stats = split_stats(ev.loc[ev["ts_utc"] > mid_ts, "signed_forward_bps"])
        loyo_min, loyo_map = leave_one_year_out_min(ev, "signed_forward_bps")
        year_means = {str(int(y)): float(g["signed_forward_bps"].mean()) for y, g in ev.groupby("year")}
        year_counts = {str(int(y)): int(g.shape[0]) for y, g in ev.groupby("year")}
    else:
        first_half_stats = split_stats(pd.Series(dtype=float))
        second_half_stats = split_stats(pd.Series(dtype=float))
        loyo_min, loyo_map = math.nan, {}
        year_means, year_counts = {}, {}

    classification = classify_result(
        event_n=event_stats["n"],
        min_events=min_events,
        event_clock_mean_bps=event_mean,
        event_clock_cost_bps=event_cost,
        benchmark_cost_residual_bps=h1_cost_resid,
        ex2025_mean_bps=ex2025_stats["mean_bps"],
        pre2025_mean_bps=pre2025_stats["mean_bps"],
        first_half_mean_bps=first_half_stats["mean_bps"],
        second_half_mean_bps=second_half_stats["mean_bps"],
        loyo_min_bps=loyo_min,
        hit_rate_pct=event_stats["hit_rate_pct"],
    )

    row = {
        "stage": STAGE_LABEL,
        "promotion": "NO_GO",
        "decision_scope": RESEARCH_DECISION,
        "candidate": spec.name,
        "family": spec.family,
        "side": spec.side,
        "lookback_hours": spec.lookback_hours,
        "trigger": spec.trigger_description,
        "horizon_hours": horizon_hours,
        "raw_n": raw_stats["n"],
        "raw_mean_bps": raw_stats["mean_bps"],
        "raw_median_bps": raw_stats["median_bps"],
        "raw_hit_rate_pct": raw_stats["hit_rate_pct"],
        "event_clock_n": event_stats["n"],
        "event_clock_mean_bps": event_mean,
        "event_clock_median_bps": event_stats["median_bps"],
        "event_clock_hit_rate_pct": event_stats["hit_rate_pct"],
        "round_trip_cost_bps": cost_bps,
        "event_clock_cost_stressed_mean_bps": event_cost,
        "directional_h1_all_drift_bps": directional_h1_drift,
        "directional_daily_anchor_drift_bps": directional_daily_drift,
        "h1_drift_adjusted_residual_bps": h1_resid,
        "daily_anchor_adjusted_residual_bps": daily_resid,
        "h1_benchmark_cost_adjusted_residual_bps": h1_cost_resid,
        "pre2025_n": pre2025_stats["n"],
        "pre2025_mean_bps": pre2025_stats["mean_bps"],
        "ex2025_n": ex2025_stats["n"],
        "ex2025_mean_bps": ex2025_stats["mean_bps"],
        "y2025_n": y2025_stats["n"],
        "y2025_mean_bps": y2025_stats["mean_bps"],
        "first_half_n": first_half_stats["n"],
        "first_half_mean_bps": first_half_stats["mean_bps"],
        "second_half_n": second_half_stats["n"],
        "second_half_mean_bps": second_half_stats["mean_bps"],
        "leave_one_year_out_min_mean_bps": loyo_min,
        "median_mfe_bps": mae_mfe["median_mfe_bps"],
        "median_mae_bps": mae_mfe["median_mae_bps"],
        "mean_mfe_bps": mae_mfe["mean_mfe_bps"],
        "mean_mae_bps": mae_mfe["mean_mae_bps"],
        "classification": classification,
        "year_means_json": json.dumps(year_means, sort_keys=True),
        "year_counts_json": json.dumps(year_counts, sort_keys=True),
        "leave_one_year_out_json": json.dumps(loyo_map, sort_keys=True),
    }
    return row, ev if not ev.empty else None


def write_markdown_report(
    out_path: Path,
    summary: Dict[str, Any],
    results: pd.DataFrame,
) -> None:
    top_cols = [
        "classification",
        "candidate",
        "family",
        "side",
        "horizon_hours",
        "event_clock_n",
        "event_clock_mean_bps",
        "event_clock_cost_stressed_mean_bps",
        "directional_h1_all_drift_bps",
        "h1_benchmark_cost_adjusted_residual_bps",
        "ex2025_mean_bps",
        "leave_one_year_out_min_mean_bps",
        "median_mae_bps",
        "median_mfe_bps",
    ]
    available_top_cols = [c for c in top_cols if c in results.columns]

    def fmt_float(v: Any) -> str:
        if isinstance(v, (float, np.floating)):
            if np.isfinite(v):
                return f"{float(v):.2f}"
            return "nan"
        if pd.isna(v):
            return "nan"
        return str(v)

    def markdown_table(frame: pd.DataFrame, columns: Sequence[str]) -> str:
        if frame.empty:
            return ""
        cols = [c for c in columns if c in frame.columns]
        if not cols:
            return ""
        rows = []
        rows.append("| " + " | ".join(cols) + " |")
        rows.append("| " + " | ".join(["---"] * len(cols)) + " |")
        for _, r in frame[cols].iterrows():
            rows.append("| " + " | ".join(fmt_float(r[c]).replace("|", "\\|") for c in cols) + " |")
        return "\n".join(rows)

    lines: List[str] = []
    lines.append(f"# {STAGE_LABEL}")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    lines.append(f"scope = {RESEARCH_DECISION}")
    lines.append("promotion = NO_GO")
    lines.append("EA = NO_GO")
    lines.append("paper_live = NO_GO")
    lines.append("live = NO_GO")
    lines.append("```")
    lines.append("")
    lines.append("This scan is benchmark-first. Any positive mean must be interpreted after direction-matched H1 drift, daily anchor drift, cost stress, year split, 2025 exclusion, leave-one-year-out, and MAE/MFE checks.")
    lines.append("")
    lines.append("## Data audit")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(summary["data_audit"], indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")
    lines.append("## Drift benchmarks")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(summary["benchmarks"], indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")
    lines.append("## Classification counts")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(summary["classification_counts"], indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")

    strict = results[results["classification"].eq("STRICT_RESEARCH_WATCH_ONLY_NO_PROMOTION")].copy()
    watch = results[results["classification"].eq("WATCH_ONLY_BENCHMARK_RESIDUAL_NO_PROMOTION")].copy()

    lines.append("## Strict research-watch rows")
    lines.append("")
    if strict.empty:
        lines.append("No strict research-watch rows found.")
    else:
        strict = strict.sort_values("h1_benchmark_cost_adjusted_residual_bps", ascending=False)
        lines.append(markdown_table(strict.head(25), available_top_cols))
    lines.append("")

    lines.append("## Soft watch rows")
    lines.append("")
    if watch.empty:
        lines.append("No soft watch rows found.")
    else:
        watch = watch.sort_values("h1_benchmark_cost_adjusted_residual_bps", ascending=False)
        lines.append(markdown_table(watch.head(25), available_top_cols))
    lines.append("")

    lines.append("## Top rows by benchmark-cost residual")
    lines.append("")
    if results.empty:
        lines.append("No results.")
    else:
        top = results.sort_values("h1_benchmark_cost_adjusted_residual_bps", ascending=False)
        lines.append(markdown_table(top.head(30), available_top_cols))
    lines.append("")
    lines.append("## Interpretation rule")
    lines.append("")
    lines.append("- `STRICT_RESEARCH_WATCH_ONLY_NO_PROMOTION` means a row is worth a deeper diagnostic, not tradable.")
    lines.append("- `WATCH_ONLY_BENCHMARK_RESIDUAL_NO_PROMOTION` means residual exists after the first benchmark, but robustness is not enough.")
    lines.append("- `FAIL_BENCHMARK_RESEARCH_ONLY` means do not extend with filters.")
    lines.append("- `INSUFFICIENT_EVENTS_RESEARCH_ONLY` means event count is too low for this stage.")
    lines.append("")
    lines.append("## Next allowed step")
    lines.append("")
    lines.append("Only if one or more strict research-watch rows exist: run a separate Stage39B diagnostic with event-list inspection, MAE/MFE path plots, year-specific sanity, and cost/slippage stress. Otherwise archive Stage39A and do not promote.")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> Dict[str, Any]:
    db_path = Path(args.db).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    df0, data_meta = read_bars(
        db_path=db_path,
        table=args.table,
        symbol=args.symbol,
        source=args.source,
        timeframe=args.timeframe,
        max_rows=args.max_rows,
    )
    df = add_features(df0)

    horizons = [int(h) for h in args.horizons.split(",") if h.strip()]
    specs = build_candidate_specs()

    benchmarks: Dict[str, Any] = {}
    rows: List[Dict[str, Any]] = []
    all_event_rows: List[pd.DataFrame] = []

    for horizon in horizons:
        h1_b = h1_all_drift(df, horizon)
        d_b = daily_anchor_drift(df, horizon)
        h1_mean = h1_b["h1_all_long_mean_bps"]
        daily_mean = d_b["daily_anchor_long_mean_bps"]
        benchmarks[str(horizon)] = {**h1_b, **d_b}

        for spec in specs:
            try:
                row, ev = evaluate_candidate(
                    df=df,
                    spec=spec,
                    horizon_hours=horizon,
                    h1_long_drift_bps=h1_mean,
                    daily_long_drift_bps=daily_mean,
                    cost_bps=float(args.cost_bps),
                    min_events=int(args.min_events),
                )
            except Exception as exc:
                row = {
                    "stage": STAGE_LABEL,
                    "promotion": "NO_GO",
                    "decision_scope": RESEARCH_DECISION,
                    "candidate": spec.name,
                    "family": spec.family,
                    "side": spec.side,
                    "lookback_hours": spec.lookback_hours,
                    "trigger": spec.trigger_description,
                    "horizon_hours": horizon,
                    "classification": "ERROR_RESEARCH_ONLY",
                    "error": repr(exc),
                }
                ev = None
            rows.append(row)
            if ev is not None and not ev.empty:
                all_event_rows.append(ev)

    results = pd.DataFrame(rows)
    if "h1_benchmark_cost_adjusted_residual_bps" in results.columns:
        results = results.sort_values(
            ["classification", "horizon_hours", "h1_benchmark_cost_adjusted_residual_bps"],
            ascending=[True, True, False],
            na_position="last",
        )

    csv_path = output_dir / "stage39a_reversal_mean_reversion_scan.csv"
    json_path = output_dir / "stage39a_reversal_mean_reversion_scan_summary.json"
    md_path = output_dir / "stage39a_reversal_mean_reversion_scan.md"
    events_path = output_dir / "stage39a_reversal_mean_reversion_event_clock_events.csv"

    results.to_csv(csv_path, index=False)

    if all_event_rows:
        events = pd.concat(all_event_rows, ignore_index=True)
        events.to_csv(events_path, index=False)
        events_rows = int(events.shape[0])
    else:
        events_rows = 0

    classification_counts = (
        results["classification"].value_counts(dropna=False).to_dict()
        if "classification" in results.columns else {}
    )

    strict_count = int((results["classification"] == "STRICT_RESEARCH_WATCH_ONLY_NO_PROMOTION").sum()) if "classification" in results.columns else 0
    watch_count = int((results["classification"] == "WATCH_ONLY_BENCHMARK_RESIDUAL_NO_PROMOTION").sum()) if "classification" in results.columns else 0

    top_rows = []
    if "h1_benchmark_cost_adjusted_residual_bps" in results.columns:
        top_rows = (
            results.sort_values("h1_benchmark_cost_adjusted_residual_bps", ascending=False)
            .head(10)
            .replace({np.nan: None})
            .to_dict(orient="records")
        )

    summary = {
        "stage": STAGE_LABEL,
        "decision_scope": RESEARCH_DECISION,
        "promotion": "NO_GO",
        "ea": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "data_audit": data_meta,
        "parameters": {
            "symbol": args.symbol,
            "source": args.source,
            "timeframe": args.timeframe,
            "horizons": horizons,
            "cost_bps": float(args.cost_bps),
            "min_events": int(args.min_events),
        },
        "benchmarks": benchmarks,
        "classification_counts": classification_counts,
        "strict_research_watch_count": strict_count,
        "soft_watch_count": watch_count,
        "events_rows_written": events_rows,
        "outputs": {
            "csv": str(csv_path),
            "summary_json": str(json_path),
            "markdown": str(md_path),
            "events_csv": str(events_path) if events_rows else None,
        },
        "top_rows_by_h1_benchmark_cost_residual": top_rows,
    }

    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown_report(md_path, summary, results)

    print(json.dumps({
        "stage": STAGE_LABEL,
        "decision_scope": RESEARCH_DECISION,
        "promotion": "NO_GO",
        "rows": int(results.shape[0]),
        "strict_research_watch_count": strict_count,
        "soft_watch_count": watch_count,
        "csv": str(csv_path),
        "summary_json": str(json_path),
        "markdown": str(md_path),
        "events_csv": str(events_path) if events_rows else None,
    }, indent=2, ensure_ascii=False))

    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Stage39A benchmark-first reversal/mean-reversion research scan for XAUUSD H1."
    )
    p.add_argument("--db", default="data/local/xauusd_local_store.sqlite", help="SQLite DB path.")
    p.add_argument("--table", default="bars", help="Bars table name.")
    p.add_argument("--symbol", default="XAUUSD", help="Symbol filter.")
    p.add_argument("--source", default="amarkets_mt5", help="Source/broker filter if source column exists.")
    p.add_argument("--timeframe", default="H1", help="Timeframe filter if timeframe column exists.")
    p.add_argument("--horizons", default="24,72,120", help="Comma-separated forward horizons in H1 bars.")
    p.add_argument("--cost-bps", type=float, default=8.0, help="Round-trip cost stress in bps.")
    p.add_argument("--min-events", type=int, default=30, help="Minimum non-overlapping event-clock events.")
    p.add_argument("--output-dir", default="reports/stage39a", help="Output directory.")
    p.add_argument("--max-rows", type=int, default=None, help="Optional debug limit.")
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
