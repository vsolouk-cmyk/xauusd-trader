#!/usr/bin/env python3
"""
Stage46A_EXTERNAL_CONTEXT_BASELINE_SCAN_IMPLEMENTATION

Fresh external-context baseline implementation for XAUUSD M15.
This stage does not rescue Stage41/42/43 candidates, does not create EA/paper/live
permissions, and does not promote anything. It only implements the predefined
Stage46 design contract in a cost-aware research pass.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

STAGE = "Stage46A_EXTERNAL_CONTEXT_BASELINE_SCAN_IMPLEMENTATION"
DEFAULT_DB = "data/local/xauusd_local_store.sqlite"
DEFAULT_TABLE = "bars"
DEFAULT_SOURCE = "amarkets_mt5"
DEFAULT_SYMBOL = "XAUUSD"
DEFAULT_TIMEFRAME = "M15"
DEFAULT_OUTDIR = "reports/stage46a"

NO_GO = {
    "promotion": "NO_GO",
    "EA": "NO_GO",
    "paper_live": "NO_GO",
    "live": "NO_GO",
}

FORBIDDEN = [
    "candidate_rescue_from_stage41_42_43",
    "post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets",
    "EA_paper_live_live_from_archived_rows",
    "ML_before_robust_cost_aware_baseline",
    "running_uncontracted_external_context_scan",
]


@dataclass
class CandidateSpec:
    candidate_id: str
    family_id: str
    direction: str
    hold_bars: int
    news_mode: str
    params: Dict[str, Any]


def utc_series(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, errors="coerce", utc=True)


def safe_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def profile_numeric(s: pd.Series) -> Dict[str, Any]:
    x = pd.to_numeric(s, errors="coerce").dropna()
    if x.empty:
        return {"n": 0}
    qs = x.quantile([0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99])
    return {
        "n": int(x.shape[0]),
        "min": float(x.min()),
        "p10": float(qs.loc[0.10]),
        "p25": float(qs.loc[0.25]),
        "median": float(qs.loc[0.50]),
        "p75": float(qs.loc[0.75]),
        "p90": float(qs.loc[0.90]),
        "p95": float(qs.loc[0.95]),
        "p99": float(qs.loc[0.99]),
        "max": float(x.max()),
        "mean": float(x.mean()),
    }


def load_bars(
    repo_root: Path,
    db_path: str,
    table: str,
    source: str,
    symbol: str,
    timeframe: str,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    path = repo_root / db_path
    meta: Dict[str, Any] = {
        "db_path": str(path),
        "table": table,
        "requested_source": source,
        "requested_symbol": symbol,
        "requested_timeframe": timeframe,
        "exists": path.exists(),
    }
    if not path.exists():
        meta.update({"loaded_rows": 0, "error": "db_missing"})
        return pd.DataFrame(), meta

    con = sqlite3.connect(str(path))
    try:
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]
        meta["columns"] = cols
        if not cols:
            meta.update({"loaded_rows": 0, "error": "table_missing_or_empty_schema"})
            return pd.DataFrame(), meta
        if "utc_time" not in cols:
            meta.update({"loaded_rows": 0, "error": "utc_time_column_missing"})
            return pd.DataFrame(), meta

        fields = ["utc_time", "open", "high", "low", "close", "spread", "tick_volume", "volume"]
        selected = [c for c in fields if c in cols]
        where: List[str] = []
        params: List[Any] = []
        for col, val in (("source", source), ("symbol", symbol), ("timeframe", timeframe)):
            if col in cols:
                where.append(f"{col} = ?")
                params.append(val)
        query = f"SELECT {', '.join(selected)} FROM {table}"
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY utc_time"
        df = pd.read_sql_query(query, con, params=params)
    finally:
        con.close()

    if df.empty:
        meta.update({"loaded_rows": 0, "error": "no_rows_after_filter"})
        return df, meta

    df["utc_time"] = utc_series(df["utc_time"])
    for c in ["open", "high", "low", "close", "spread", "tick_volume", "volume"]:
        if c in df.columns:
            df[c] = safe_num(df[c])
    df = df.dropna(subset=["utc_time", "open", "high", "low", "close"]).copy()
    df = df.sort_values("utc_time").drop_duplicates("utc_time").reset_index(drop=True)
    df["bar_date"] = df["utc_time"].dt.floor("D")
    df["year"] = df["utc_time"].dt.year.astype(int)
    df["quarter"] = df["utc_time"].dt.to_period("Q").astype(str)

    if "spread" in df.columns:
        df["spread_bps"] = (df["spread"].abs() / df["close"].replace(0, np.nan)) * 10000.0
        # protect against malformed spread units; keep cost-aware but finite
        df["spread_bps"] = df["spread_bps"].clip(lower=0, upper=100)
    else:
        df["spread_bps"] = 0.0
    df["round_trip_cost_bps"] = 2.0 * df["spread_bps"].fillna(0.0)

    meta.update(
        {
            "loaded_rows": int(len(df)),
            "loaded_start": df["utc_time"].min().isoformat(),
            "loaded_end": df["utc_time"].max().isoformat(),
            "daily_count": int(df["bar_date"].nunique()),
            "spread_bps_profile": profile_numeric(df["spread_bps"]),
            "round_trip_cost_bps_profile": profile_numeric(df["round_trip_cost_bps"]),
            "error": None,
        }
    )
    return df, meta


def read_csv_profile(repo_root: Path, rel_path: str, required_cols: Iterable[str]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    path = repo_root / rel_path
    meta: Dict[str, Any] = {"path": rel_path, "exists": path.exists(), "schema_ok": False}
    if not path.exists():
        meta.update({"row_count": 0, "error": "missing"})
        return pd.DataFrame(), meta
    try:
        df = pd.read_csv(path)
    except Exception as exc:  # pragma: no cover - defensive
        meta.update({"row_count": 0, "error": repr(exc)})
        return pd.DataFrame(), meta
    cols = list(df.columns)
    missing = [c for c in required_cols if c not in df.columns]
    meta.update({"columns": cols, "row_count": int(len(df)), "schema_ok": not missing, "missing_columns": missing})
    if "timestamp" in df.columns:
        ts = utc_series(df["timestamp"])
        meta["valid_timestamp_count"] = int(ts.notna().sum())
        if ts.notna().any():
            meta["start"] = ts.min().isoformat()
            meta["end"] = ts.max().isoformat()
    if missing:
        meta["error"] = "missing_required_columns"
    else:
        meta["error"] = None
    return df, meta


def add_daily_feature(
    bars: pd.DataFrame,
    daily: pd.DataFrame,
    value_col: str,
    prefix: str,
    lag_days: int,
) -> pd.DataFrame:
    if daily.empty or "timestamp" not in daily.columns or value_col not in daily.columns:
        for c in [f"{prefix}_value_lag1", f"{prefix}_ret_1d_lag1", f"{prefix}_slope_5d_lag1"]:
            bars[c] = np.nan
        return bars

    d = daily[["timestamp", value_col]].copy()
    d["timestamp"] = utc_series(d["timestamp"]).dt.floor("D")
    d[value_col] = safe_num(d[value_col])
    d = d.dropna(subset=["timestamp", value_col]).sort_values("timestamp").drop_duplicates("timestamp")
    if d.empty:
        return add_daily_feature(bars, pd.DataFrame(), value_col, prefix, lag_days)

    d[f"{prefix}_value"] = d[value_col]
    if prefix in ("us10y", "real_yield"):
        d[f"{prefix}_ret_1d"] = d[value_col].diff() * 100.0  # percent points -> bps
        d[f"{prefix}_slope_5d"] = (d[value_col] - d[value_col].shift(5)) * 100.0
    else:
        d[f"{prefix}_ret_1d"] = (d[value_col] / d[value_col].shift(1) - 1.0) * 10000.0
        d[f"{prefix}_slope_5d"] = (d[value_col] / d[value_col].shift(5) - 1.0) * 10000.0

    left = bars[["utc_time", "bar_date"]].copy()
    left["context_date"] = left["bar_date"] - pd.Timedelta(days=int(lag_days))
    right = d[["timestamp", f"{prefix}_value", f"{prefix}_ret_1d", f"{prefix}_slope_5d"]].copy()
    merged = pd.merge_asof(
        left.sort_values("context_date"),
        right.sort_values("timestamp"),
        left_on="context_date",
        right_on="timestamp",
        direction="backward",
    ).sort_index()
    bars[f"{prefix}_value_lag1"] = merged[f"{prefix}_value"].to_numpy()
    bars[f"{prefix}_ret_1d_lag1"] = merged[f"{prefix}_ret_1d"].to_numpy()
    bars[f"{prefix}_slope_5d_lag1"] = merged[f"{prefix}_slope_5d"].to_numpy()
    return bars


def add_news_blackout(bars: pd.DataFrame, windows: pd.DataFrame) -> pd.DataFrame:
    bars["is_news_blackout"] = False
    bars["minutes_to_event"] = np.nan
    if windows.empty or not {"window_start", "window_end"}.issubset(windows.columns):
        return bars
    w = windows.copy()
    w["window_start"] = utc_series(w["window_start"])
    w["window_end"] = utc_series(w["window_end"])
    if "event_timestamp" in w.columns:
        w["event_timestamp"] = utc_series(w["event_timestamp"])
    else:
        w["event_timestamp"] = pd.NaT
    w = w.dropna(subset=["window_start", "window_end"]).sort_values("window_start")
    if w.empty:
        return bars

    bar_start = bars["utc_time"].astype("int64").to_numpy()
    # infer bar end from median diff; fallback M15
    if len(bar_start) > 1:
        diffs = np.diff(bar_start)
        tf_ns = int(np.nanmedian(diffs[diffs > 0])) if np.any(diffs > 0) else int(pd.Timedelta(minutes=15).value)
    else:
        tf_ns = int(pd.Timedelta(minutes=15).value)
    bar_end = bar_start + tf_ns
    mask = np.zeros(len(bars), dtype=bool)

    # For each event window mark overlapping bars. Calendar is small; loop is acceptable.
    for _, row in w.iterrows():
        ws = int(row["window_start"].value)
        we = int(row["window_end"].value)
        if we <= bar_start[0] or ws >= bar_end[-1]:
            continue
        left = int(np.searchsorted(bar_end, ws, side="right"))
        right = int(np.searchsorted(bar_start, we, side="left"))
        if right > left:
            mask[left:right] = True
    bars["is_news_blackout"] = mask

    # minutes to next event: sparse but useful for audit; use searchsorted over event timestamps
    ev = w["event_timestamp"].dropna().astype("int64").sort_values().to_numpy()
    if len(ev):
        idx = np.searchsorted(ev, bar_start, side="left")
        mins = np.full(len(bar_start), np.nan)
        ok = idx < len(ev)
        mins[ok] = (ev[idx[ok]] - bar_start[ok]) / 1e9 / 60.0
        bars["minutes_to_event"] = mins
    return bars


def add_reference_gc(bars: pd.DataFrame, gc: pd.DataFrame, lag_days: int) -> pd.DataFrame:
    if gc.empty or "timestamp" not in gc.columns or "close" not in gc.columns:
        bars["gc_ret_1d_reference_lag1"] = np.nan
        return bars
    g = gc[["timestamp", "close"]].copy()
    g["timestamp"] = utc_series(g["timestamp"]).dt.floor("D")
    g["close"] = safe_num(g["close"])
    g = g.dropna(subset=["timestamp", "close"]).sort_values("timestamp").drop_duplicates("timestamp")
    g["gc_ret_1d_reference"] = (g["close"] / g["close"].shift(1) - 1.0) * 10000.0
    left = bars[["bar_date"]].copy()
    left["context_date"] = left["bar_date"] - pd.Timedelta(days=int(lag_days))
    merged = pd.merge_asof(
        left.sort_values("context_date"),
        g[["timestamp", "gc_ret_1d_reference"]].sort_values("timestamp"),
        left_on="context_date",
        right_on="timestamp",
        direction="backward",
    ).sort_index()
    bars["gc_ret_1d_reference_lag1"] = merged["gc_ret_1d_reference"].to_numpy()
    return bars


def build_features(repo_root: Path, bars: pd.DataFrame, daily_safe_lag_days: int) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    profiles: Dict[str, Any] = {}
    dxy, profiles["dxy"] = read_csv_profile(repo_root, "data/external/dxy.csv", ["timestamp", "close"])
    us10y, profiles["us10y"] = read_csv_profile(repo_root, "data/external/us10y_yield.csv", ["timestamp", "yield"])
    real_yield, profiles["real_yield"] = read_csv_profile(repo_root, "data/external/real_yield.csv", ["timestamp", "yield"])
    gc, profiles["cme_gc_reference"] = read_csv_profile(repo_root, "data/reference/cme_gc.csv", ["timestamp", "open", "high", "low", "close"])
    windows, profiles["news_blackout_windows"] = read_csv_profile(repo_root, "data/external/news_blackout_windows.csv", ["window_start", "window_end"])

    out = bars.copy()
    out = add_daily_feature(out, dxy, "close", "dxy", daily_safe_lag_days)
    out = add_daily_feature(out, us10y, "yield", "us10y", daily_safe_lag_days)
    out = add_daily_feature(out, real_yield, "yield", "real_yield", daily_safe_lag_days)
    out = add_reference_gc(out, gc, daily_safe_lag_days)
    out = add_news_blackout(out, windows)

    coverage_cols = [
        "dxy_slope_5d_lag1",
        "us10y_ret_1d_lag1",
        "real_yield_ret_1d_lag1",
        "gc_ret_1d_reference_lag1",
        "is_news_blackout",
    ]
    feature_coverage = []
    for c in coverage_cols:
        if c in out.columns:
            if out[c].dtype == bool:
                valid = int(out[c].notna().sum())
                extra = {"true_pct": float(out[c].mean())}
            else:
                valid = int(out[c].notna().sum())
                extra = profile_numeric(out[c])
            feature_coverage.append(
                {
                    "feature": c,
                    "valid_count": valid,
                    "coverage_pct": float(valid / len(out)) if len(out) else 0.0,
                    "profile": extra,
                }
            )
    profiles["feature_coverage"] = feature_coverage
    return out, profiles


def non_overlapping_indices(mask: np.ndarray, hold_bars: int) -> np.ndarray:
    idxs = np.flatnonzero(mask)
    if len(idxs) == 0:
        return idxs
    chosen: List[int] = []
    next_allowed = 0
    max_entry = len(mask) - int(hold_bars) - 1
    for i in idxs:
        if i > max_entry:
            break
        if i >= next_allowed:
            chosen.append(int(i))
            next_allowed = int(i) + int(hold_bars)
    return np.asarray(chosen, dtype=int)


def generate_specs(df: pd.DataFrame, hold_grid: List[int]) -> List[CandidateSpec]:
    specs: List[CandidateSpec] = []
    news_modes = ["exclude", "tag_only"]
    directions = ["long", "short"]

    # A: DXY/Yield trend filter. Quantiles are computed once before scan.
    for direction in directions:
        for hold in hold_grid:
            for news_mode in news_modes:
                for q in [0.25, 0.50, 0.75]:
                    for context_mode in ["confirm", "avoid"]:
                        cid = f"EXTCTX_A_{direction.upper()}_H{hold}_Q{q:.2f}_{context_mode}_{news_mode}"
                        specs.append(
                            CandidateSpec(
                                cid,
                                "EXTCTX_A_DXY_YIELD_TREND_FILTER",
                                direction,
                                hold,
                                news_mode,
                                {"dxy_slope_quantile": q, "context_mode": context_mode},
                            )
                        )

    # C: Reference-feed confirmation.
    for direction in directions:
        for hold in hold_grid:
            for news_mode in news_modes:
                for confirm_mode in ["lagged_reference_sign"]:
                    cid = f"EXTCTX_C_{direction.upper()}_H{hold}_{confirm_mode}_{news_mode}"
                    specs.append(
                        CandidateSpec(
                            cid,
                            "EXTCTX_C_REFERENCE_FEED_SANITY",
                            direction,
                            hold,
                            news_mode,
                            {"confirm_mode": confirm_mode},
                        )
                    )

    # D: Transparent composite score.
    for direction in directions:
        for hold in hold_grid:
            for news_mode in news_modes:
                for threshold in [2, 3]:
                    for use_real in [False, True]:
                        cid = f"EXTCTX_D_{direction.upper()}_H{hold}_T{threshold}_REAL{int(use_real)}_{news_mode}"
                        specs.append(
                            CandidateSpec(
                                cid,
                                "EXTCTX_D_COMPOSITE_CONTEXT_SCORE",
                                direction,
                                hold,
                                news_mode,
                                {"threshold": threshold, "use_real_yield": use_real},
                            )
                        )
    return specs


def candidate_mask(df: pd.DataFrame, spec: CandidateSpec, thresholds: Dict[str, float]) -> pd.Series:
    valid = pd.Series(True, index=df.index)
    for c in ["dxy_slope_5d_lag1", "us10y_ret_1d_lag1", "gc_ret_1d_reference_lag1"]:
        if c not in df.columns:
            valid &= False
        else:
            valid &= df[c].notna()

    if spec.family_id == "EXTCTX_A_DXY_YIELD_TREND_FILTER":
        q = float(spec.params["dxy_slope_quantile"])
        mode = str(spec.params["context_mode"])
        qval = float(thresholds.get(f"dxy_slope_q{q:.2f}", np.nan))
        if not np.isfinite(qval):
            return pd.Series(False, index=df.index)
        if spec.direction == "long":
            supportive = (df["dxy_slope_5d_lag1"] <= qval) & (df["us10y_ret_1d_lag1"] <= 0)
            hostile = (df["dxy_slope_5d_lag1"] > qval) & (df["us10y_ret_1d_lag1"] > 0)
        else:
            supportive = (df["dxy_slope_5d_lag1"] >= qval) & (df["us10y_ret_1d_lag1"] >= 0)
            hostile = (df["dxy_slope_5d_lag1"] < qval) & (df["us10y_ret_1d_lag1"] < 0)
        mask = supportive if mode == "confirm" else (~hostile)
        valid &= mask

    elif spec.family_id == "EXTCTX_C_REFERENCE_FEED_SANITY":
        if spec.direction == "long":
            valid &= df["gc_ret_1d_reference_lag1"] > 0
        else:
            valid &= df["gc_ret_1d_reference_lag1"] < 0

    elif spec.family_id == "EXTCTX_D_COMPOSITE_CONTEXT_SCORE":
        score = pd.Series(0.0, index=df.index)
        score += np.where(df["dxy_slope_5d_lag1"] < 0, 1, np.where(df["dxy_slope_5d_lag1"] > 0, -1, 0))
        score += np.where(df["us10y_ret_1d_lag1"] < 0, 1, np.where(df["us10y_ret_1d_lag1"] > 0, -1, 0))
        score += np.where(df["gc_ret_1d_reference_lag1"] > 0, 1, np.where(df["gc_ret_1d_reference_lag1"] < 0, -1, 0))
        if spec.params.get("use_real_yield") and "real_yield_ret_1d_lag1" in df.columns:
            valid &= df["real_yield_ret_1d_lag1"].notna()
            score += np.where(df["real_yield_ret_1d_lag1"] < 0, 1, np.where(df["real_yield_ret_1d_lag1"] > 0, -1, 0))
        threshold = int(spec.params["threshold"])
        if spec.direction == "long":
            valid &= score >= threshold
        else:
            valid &= score <= -threshold
        df["_last_composite_score"] = score
    else:
        valid &= False

    if spec.news_mode == "exclude" and "is_news_blackout" in df.columns:
        valid &= ~df["is_news_blackout"].fillna(False).astype(bool)
    return valid.fillna(False)


def benchmark_metrics(df: pd.DataFrame, hold_grid: List[int]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for hold in hold_grid:
        future = df["close"].shift(-hold)
        ret = (future / df["close"] - 1.0) * 10000.0
        for direction in ["long", "short"]:
            pnl = ret if direction == "long" else -ret
            net = pnl - df["round_trip_cost_bps"].fillna(0.0)
            mask = net.notna().to_numpy()
            idx = non_overlapping_indices(mask, hold)
            vals = net.iloc[idx].dropna() if len(idx) else pd.Series(dtype=float)
            rows.append(
                {
                    "hold_bars": hold,
                    "direction": direction,
                    "benchmark_event_count": int(len(vals)),
                    "benchmark_mean_net_bps": float(vals.mean()) if len(vals) else None,
                    "benchmark_median_net_bps": float(vals.median()) if len(vals) else None,
                    "benchmark_win_rate": float((vals > 0).mean()) if len(vals) else None,
                }
            )
    return rows


def bootstrap_p05(vals: pd.Series, n_boot: int, seed: int) -> Optional[float]:
    x = pd.to_numeric(vals, errors="coerce").dropna().to_numpy(dtype=float)
    if len(x) < 30 or n_boot <= 0:
        return None
    rng = np.random.default_rng(seed)
    # Memory-light bootstrap loop; candidate count is moderate.
    means = np.empty(n_boot, dtype=float)
    n = len(x)
    for i in range(n_boot):
        means[i] = rng.choice(x, size=n, replace=True).mean()
    return float(np.quantile(means, 0.05))


def classify_candidate(m: Dict[str, Any]) -> str:
    n = m.get("event_count", 0) or 0
    mean = m.get("mean_net_bps")
    train = m.get("train_mean_net_bps")
    oos = m.get("oos_mean_net_bps")
    worst_q = m.get("worst_quarter_mean_net_bps")
    boot = m.get("bootstrap_mean_p05_bps")
    residual = m.get("residual_vs_benchmark_bps")
    year_conc = m.get("max_year_event_pct")

    def gt(x: Any, y: float) -> bool:
        return x is not None and np.isfinite(x) and float(x) > y

    def ge(x: Any, y: float) -> bool:
        return x is not None and np.isfinite(x) and float(x) >= y

    if (
        n >= 250
        and gt(mean, 0.0)
        and gt(train, 0.0)
        and gt(oos, 0.0)
        and ge(worst_q, -15.0)
        and gt(boot, -2.0)
        and gt(residual, 0.0)
        and (year_conc is None or year_conc <= 0.45)
    ):
        return "STRICT_EXTERNAL_CONTEXT_SURVIVOR_CANDIDATE_REQUIRES_STAGE46B_AUDIT"
    if (
        n >= 100
        and gt(mean, 0.0)
        and gt(oos, 0.0)
        and ge(worst_q, -35.0)
        and (boot is None or gt(boot, -10.0))
        and gt(residual, 0.0)
        and (year_conc is None or year_conc <= 0.60)
    ):
        return "SOFT_EXTERNAL_CONTEXT_CANDIDATE_RESEARCH_ONLY_REQUIRES_AUDIT"
    return "FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY"


def evaluate_candidate(
    df: pd.DataFrame,
    spec: CandidateSpec,
    thresholds: Dict[str, float],
    bench_map: Dict[Tuple[int, str], float],
    n_bootstrap: int,
    seed: int,
) -> Tuple[Dict[str, Any], pd.DataFrame]:
    hold = int(spec.hold_bars)
    # Pandas/NumPy can expose boolean arrays as read-only views on some runtimes.
    # Force writable copies before in-place boolean operations.
    sig = np.asarray(candidate_mask(df.copy(), spec, thresholds).to_numpy(dtype=bool), dtype=bool).copy()
    # ensure exit is available
    valid_exit = np.asarray(df["close"].shift(-hold).notna().to_numpy(dtype=bool), dtype=bool).copy()
    sig = sig & valid_exit
    idx = non_overlapping_indices(sig, hold)

    if len(idx) == 0:
        metrics = {
            **asdict(spec),
            "params_json": json.dumps(spec.params, sort_keys=True),
            "event_count": 0,
            "classification": "INSUFFICIENT_EVENTS_RESEARCH_ONLY",
        }
        return metrics, pd.DataFrame()

    entry = df.iloc[idx].copy()
    exit_close = df["close"].shift(-hold).iloc[idx].to_numpy(dtype=float)
    gross_long = (exit_close / entry["close"].to_numpy(dtype=float) - 1.0) * 10000.0
    gross = gross_long if spec.direction == "long" else -gross_long
    cost = entry["round_trip_cost_bps"].fillna(0.0).to_numpy(dtype=float)
    net = gross - cost

    events = pd.DataFrame(
        {
            "candidate_id": spec.candidate_id,
            "family_id": spec.family_id,
            "direction": spec.direction,
            "hold_bars": hold,
            "news_mode": spec.news_mode,
            "entry_time": entry["utc_time"].dt.strftime("%Y-%m-%dT%H:%M:%SZ").to_numpy(),
            "entry_close": entry["close"].to_numpy(dtype=float),
            "exit_close": exit_close,
            "gross_bps": gross,
            "round_trip_cost_bps": cost,
            "net_bps": net,
            "year": entry["year"].to_numpy(dtype=int),
            "quarter": entry["quarter"].astype(str).to_numpy(),
            "is_news_blackout": entry.get("is_news_blackout", pd.Series(False, index=entry.index)).astype(bool).to_numpy(),
        }
    )

    vals = pd.Series(net)
    years = events.groupby("year")["net_bps"].agg(["count", "mean"]).reset_index()
    quarters = events.groupby("quarter")["net_bps"].agg(["count", "mean"]).reset_index()
    train_vals = events.loc[events["year"] <= 2024, "net_bps"]
    oos_vals = events.loc[events["year"] >= 2025, "net_bps"]
    bench = bench_map.get((hold, spec.direction))
    mean_net = float(vals.mean())
    residual = None if bench is None or not np.isfinite(bench) else mean_net - float(bench)
    max_year_pct = float(years["count"].max() / len(events)) if len(years) else None

    metrics = {
        "candidate_id": spec.candidate_id,
        "family_id": spec.family_id,
        "direction": spec.direction,
        "hold_bars": hold,
        "news_mode": spec.news_mode,
        "params_json": json.dumps(spec.params, sort_keys=True),
        "event_count": int(len(events)),
        "mean_gross_bps": float(np.nanmean(gross)),
        "mean_cost_bps": float(np.nanmean(cost)),
        "mean_net_bps": mean_net,
        "median_net_bps": float(vals.median()),
        "win_rate": float((vals > 0).mean()),
        "total_net_bps": float(vals.sum()),
        "train_event_count": int(len(train_vals)),
        "train_mean_net_bps": float(train_vals.mean()) if len(train_vals) else None,
        "oos_event_count": int(len(oos_vals)),
        "oos_mean_net_bps": float(oos_vals.mean()) if len(oos_vals) else None,
        "quarter_count": int(len(quarters)),
        "worst_quarter_mean_net_bps": float(quarters["mean"].min()) if len(quarters) else None,
        "best_quarter_mean_net_bps": float(quarters["mean"].max()) if len(quarters) else None,
        "max_year_event_pct": max_year_pct,
        "benchmark_mean_net_bps": None if bench is None or not np.isfinite(bench) else float(bench),
        "residual_vs_benchmark_bps": residual,
        "bootstrap_mean_p05_bps": bootstrap_p05(vals, n_bootstrap, seed + (abs(hash(spec.candidate_id)) % 100000)),
    }
    metrics["classification"] = classify_candidate(metrics)
    return metrics, events


def write_markdown(summary: Dict[str, Any], path: Path) -> None:
    dec = summary["decision"]
    rows = summary.get("top_candidates", [])[:15]
    lines: List[str] = []
    lines.append(f"# {STAGE}\n")
    lines.append("## Decision\n")
    lines.append("```text")
    for k in ["promotion", "EA", "paper_live", "live"]:
        lines.append(f"{k} = {dec[k]}")
    lines.append(f"status = {dec['status']}")
    lines.append(f"recommended_next_stage = {dec['recommended_next_stage']}")
    lines.append("```\n")
    lines.append("Stage46A implements the predefined Stage46 external-context baseline design in a fresh cost-aware scan. It does not rescue Stage41/42/43 rows and does not authorize EA, paper-live, or live trading.\n")
    lines.append("## Scan summary\n")
    lines.append("```json")
    lines.append(json.dumps(summary.get("scan_summary", {}), indent=2, ensure_ascii=False))
    lines.append("```\n")
    lines.append("## Top candidates by mean net bps\n")
    if rows:
        lines.append("| candidate_id | class | n | mean_net | oos_mean | worst_q | residual |")
        lines.append("| :-- | :-- | --: | --: | --: | --: | --: |")
        for r in rows:
            lines.append(
                f"| {r.get('candidate_id')} | {r.get('classification')} | {r.get('event_count')} | "
                f"{fmt(r.get('mean_net_bps'))} | {fmt(r.get('oos_mean_net_bps'))} | "
                f"{fmt(r.get('worst_quarter_mean_net_bps'))} | {fmt(r.get('residual_vs_benchmark_bps'))} |"
            )
    else:
        lines.append("No candidate metrics were produced.\n")
    lines.append("\n## Guardrails\n")
    for item in FORBIDDEN:
        lines.append(f"- `{item}`")
    lines.append("\n## Anti-overfit note\n")
    lines.append("This implementation is a fresh predefined external-context baseline pass. Any strict or soft row must still pass a separate Stage46B audit before any promotion discussion.\n")
    path.write_text("\n".join(lines), encoding="utf-8")


def fmt(x: Any) -> str:
    if x is None:
        return ""
    try:
        if not np.isfinite(float(x)):
            return ""
        return f"{float(x):.3f}"
    except Exception:
        return str(x)


def build_summary(args: argparse.Namespace) -> Dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    outdir = repo_root / args.outdir
    ensure_dir(outdir)

    bars, bar_meta = load_bars(repo_root, args.db_path, args.table, args.source, args.symbol, args.timeframe)
    stage46_summary_path = repo_root / args.stage46_summary
    stage46_ref: Dict[str, Any] = {"path": str(stage46_summary_path), "exists": stage46_summary_path.exists()}
    if stage46_summary_path.exists():
        try:
            j = json.loads(stage46_summary_path.read_text(encoding="utf-8"))
            stage46_ref.update(
                {
                    "status": j.get("decision", {}).get("status"),
                    "next_allowed_step": j.get("next_allowed_step"),
                    "ready_for_stage46a": j.get("next_allowed_step") == "Stage46A_EXTERNAL_CONTEXT_BASELINE_SCAN_IMPLEMENTATION",
                    "blockers": j.get("decision", {}).get("blockers", []),
                }
            )
        except Exception as exc:
            stage46_ref.update({"error": repr(exc), "ready_for_stage46a": False})
    else:
        stage46_ref.update({"ready_for_stage46a": False, "error": "missing_stage46_summary"})

    blockers: List[str] = []
    warnings: List[str] = []
    if not stage46_ref.get("ready_for_stage46a"):
        blockers.append("stage46_design_contract_not_ready")
    if bars.empty:
        blockers.append("m15_bars_missing_or_empty")

    feature_meta: Dict[str, Any] = {}
    candidate_metrics: List[Dict[str, Any]] = []
    event_sample = pd.DataFrame()
    benchmarks: List[Dict[str, Any]] = []

    if not blockers:
        bars, feature_meta = build_features(repo_root, bars, args.daily_safe_lag_days)
        feature_coverage = {r["feature"]: r["coverage_pct"] for r in feature_meta.get("feature_coverage", [])}
        for required_feature in ["dxy_slope_5d_lag1", "us10y_ret_1d_lag1", "gc_ret_1d_reference_lag1"]:
            if feature_coverage.get(required_feature, 0.0) < args.min_feature_coverage_pct:
                blockers.append(f"feature_coverage_too_low:{required_feature}")
        if feature_coverage.get("is_news_blackout", 0.0) < 0.99:
            warnings.append("news_blackout_flag_not_fully_available")

    if not blockers:
        hold_grid = [int(x) for x in args.hold_bars]
        benchmarks = benchmark_metrics(bars, hold_grid)
        bench_map = {
            (int(r["hold_bars"]), str(r["direction"])): float(r["benchmark_mean_net_bps"])
            for r in benchmarks
            if r.get("benchmark_mean_net_bps") is not None
        }
        thresholds: Dict[str, float] = {}
        dxy_slope = bars["dxy_slope_5d_lag1"].dropna()
        for q in [0.25, 0.50, 0.75]:
            thresholds[f"dxy_slope_q{q:.2f}"] = float(dxy_slope.quantile(q)) if len(dxy_slope) else float("nan")

        specs = generate_specs(bars, hold_grid)
        all_events: List[pd.DataFrame] = []
        for spec in specs:
            metrics, events = evaluate_candidate(
                bars,
                spec,
                thresholds,
                bench_map,
                n_bootstrap=int(args.bootstrap_iterations),
                seed=int(args.seed),
            )
            candidate_metrics.append(metrics)
            if not events.empty and len(pd.concat(all_events, ignore_index=True)) if all_events else 0 < int(args.max_event_sample_rows):
                all_events.append(events.head(max(0, int(args.max_event_sample_rows))))
        if all_events:
            event_sample = pd.concat(all_events, ignore_index=True).head(int(args.max_event_sample_rows))

    metrics_df = pd.DataFrame(candidate_metrics)
    if not metrics_df.empty:
        metrics_df = metrics_df.sort_values(["classification", "mean_net_bps", "event_count"], ascending=[True, False, False])
        metrics_df.to_csv(outdir / "stage46a_candidate_metrics.csv", index=False)
    else:
        pd.DataFrame().to_csv(outdir / "stage46a_candidate_metrics.csv", index=False)

    if not event_sample.empty:
        event_sample.to_csv(outdir / "stage46a_event_audit_sample.csv", index=False)
    else:
        pd.DataFrame().to_csv(outdir / "stage46a_event_audit_sample.csv", index=False)

    pd.DataFrame(benchmarks).to_csv(outdir / "stage46a_benchmark_metrics.csv", index=False)
    pd.DataFrame(feature_meta.get("feature_coverage", [])).to_csv(outdir / "stage46a_feature_coverage.csv", index=False)

    class_counts = metrics_df["classification"].value_counts().to_dict() if not metrics_df.empty and "classification" in metrics_df.columns else {}
    strict_count = int(sum(v for k, v in class_counts.items() if str(k).startswith("STRICT")))
    soft_count = int(sum(v for k, v in class_counts.items() if str(k).startswith("SOFT")))
    fail_count = int(sum(v for k, v in class_counts.items() if str(k).startswith("FAIL") or str(k).startswith("INSUFFICIENT")))
    top_candidates = metrics_df.head(20).replace({np.nan: None}).to_dict(orient="records") if not metrics_df.empty else []

    if blockers:
        status = "EXTERNAL_CONTEXT_BASELINE_SCAN_IMPLEMENTATION_BLOCKED_NO_PROMOTION"
        recommended = "Stage46A_CONTINUE_EXTERNAL_CONTEXT_BASELINE_SCAN_IMPLEMENTATION_REPAIR"
    elif strict_count or soft_count:
        status = "EXTERNAL_CONTEXT_BASELINE_SCAN_IMPLEMENTED_CANDIDATES_REQUIRE_AUDIT_NO_PROMOTION"
        recommended = "Stage46B_EXTERNAL_CONTEXT_CANDIDATE_AUDIT"
    else:
        status = "EXTERNAL_CONTEXT_BASELINE_SCAN_IMPLEMENTED_NO_SURVIVORS_NO_PROMOTION"
        recommended = "Stage46C_EXTERNAL_CONTEXT_FAILURE_ANALYSIS_OR_ARCHIVE"

    scan_summary = {
        "candidate_rows": int(len(metrics_df)) if not metrics_df.empty else 0,
        "strict_count": strict_count,
        "soft_count": soft_count,
        "fail_or_insufficient_count": fail_count,
        "classification_counts": class_counts,
        "event_sample_rows_written": int(len(event_sample)),
    }

    summary: Dict[str, Any] = {
        "stage": STAGE,
        "settings": {
            "repo_root": str(repo_root),
            "db_path": args.db_path,
            "table": args.table,
            "source": args.source,
            "symbol": args.symbol,
            "timeframe": args.timeframe,
            "outdir": args.outdir,
            "daily_safe_lag_days": args.daily_safe_lag_days,
            "hold_bars": [int(x) for x in args.hold_bars],
            "bootstrap_iterations": int(args.bootstrap_iterations),
            "min_feature_coverage_pct": float(args.min_feature_coverage_pct),
        },
        "stage46_reference": stage46_ref,
        "bar_load_meta": bar_meta,
        "feature_meta": feature_meta,
        "scan_summary": scan_summary,
        "top_candidates": top_candidates,
        "decision": {
            "status": status,
            **NO_GO,
            "blockers": blockers,
            "warnings": warnings + ["fresh_stage46a_pass_no_archived_candidate_rescue"],
            "recommended_next_stage": recommended,
            "rationale": [
                "Stage46A implements the predefined Stage46 external-context baseline design in a fresh pass.",
                "All daily macro context is lagged by one daily session to reduce lookahead risk.",
                "News blackout windows are used only as predefined guard/tag features, not optimized post-hoc.",
                "This stage does not authorize EA, paper-live, live trading, or promotion.",
            ],
            "not_allowed": FORBIDDEN,
        },
        **NO_GO,
        "next_allowed_step": recommended,
        "outputs": {
            "summary_json": str(outdir / "stage46a_external_context_baseline_scan_implementation_summary.json"),
            "markdown": str(outdir / "stage46a_external_context_baseline_scan_implementation.md"),
            "candidate_metrics_csv": str(outdir / "stage46a_candidate_metrics.csv"),
            "event_audit_sample_csv": str(outdir / "stage46a_event_audit_sample.csv"),
            "benchmark_metrics_csv": str(outdir / "stage46a_benchmark_metrics.csv"),
            "feature_coverage_csv": str(outdir / "stage46a_feature_coverage.csv"),
        },
    }

    summary_path = outdir / "stage46a_external_context_baseline_scan_implementation_summary.json"
    md_path = outdir / "stage46a_external_context_baseline_scan_implementation.md"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    write_markdown(summary, md_path)
    if args.print_summary:
        print(
            json.dumps(
                {
                    "stage": STAGE,
                    "status": status,
                    "candidate_rows": scan_summary["candidate_rows"],
                    "strict_count": strict_count,
                    "soft_count": soft_count,
                    "blockers": blockers,
                    "next_allowed_step": recommended,
                    "summary_path": str(summary_path),
                    "markdown_path": str(md_path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    return summary


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=STAGE)
    p.add_argument("--repo-root", default=".")
    p.add_argument("--db-path", default=DEFAULT_DB)
    p.add_argument("--table", default=DEFAULT_TABLE)
    p.add_argument("--source", default=DEFAULT_SOURCE)
    p.add_argument("--symbol", default=DEFAULT_SYMBOL)
    p.add_argument("--timeframe", default=DEFAULT_TIMEFRAME)
    p.add_argument("--stage46-summary", default="reports/stage46/stage46_external_context_baseline_scan_design_summary.json")
    p.add_argument("--outdir", default=DEFAULT_OUTDIR)
    p.add_argument("--daily-safe-lag-days", type=int, default=1)
    p.add_argument("--hold-bars", type=int, nargs="+", default=[4, 8, 16])
    p.add_argument("--bootstrap-iterations", type=int, default=300)
    p.add_argument("--min-feature-coverage-pct", type=float, default=0.90)
    p.add_argument("--max-event-sample-rows", type=int, default=10000)
    p.add_argument("--seed", type=int, default=4601)
    p.add_argument("--print-summary", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    build_summary(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
