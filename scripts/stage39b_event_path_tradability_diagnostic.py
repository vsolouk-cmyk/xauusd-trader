#!/usr/bin/env python3
"""
Stage39B_EVENT_PATH_AND_TRADABILITY_DIAGNOSTIC

Research-only diagnostic after Stage39A benchmark-first scan.

This script is deliberately NOT a promotion gate.
It inspects Stage39A strict research-watch rows at event/path level:
- exact or reconstructed event-clock list
- MAE/MFE path profile
- year split and exclude-2025 sanity
- leave-one-year-out sanity
- cost/slippage stress
- simple stop/target touch diagnostics
- residual-to-path-risk ratio

Outputs are written under reports/stage39b by default.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sqlite3
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


STAGE = "Stage39B_EVENT_PATH_AND_TRADABILITY_DIAGNOSTIC"
DECISION_SCOPE = "RESEARCH_STAGE_ONLY_NO_PROMOTION"
PROMOTION = "NO_GO"

TIMESTAMP_CANDIDATES = [
    "ts_utc",
    "utc_time",
    "timestamp_utc",
    "time_utc",
    "datetime_utc",
    "date_utc",
    "ts",
    "timestamp",
    "time",
    "datetime",
    "date",
    "open_time",
    "bar_time",
]

OPEN_CANDIDATES = ["open", "o", "bid_open", "ask_open"]
HIGH_CANDIDATES = ["high", "h", "bid_high", "ask_high"]
LOW_CANDIDATES = ["low", "l", "bid_low", "ask_low"]
CLOSE_CANDIDATES = ["close", "c", "bid_close", "ask_close"]
SPREAD_CANDIDATES = ["spread", "spread_points", "mt5_spread"]
SYMBOL_CANDIDATES = ["symbol", "ticker", "instrument"]
SOURCE_CANDIDATES = ["source", "broker", "data_source"]
TIMEFRAME_CANDIDATES = ["timeframe", "tf", "interval"]


@dataclass(frozen=True)
class CandidateSpec:
    candidate: str
    family: str
    side: str
    horizon_hours: int
    lookback_hours: int
    trigger_type: str
    threshold: float
    source_stage39a_residual_bps: float
    source_stage39a_event_clock_n: int
    source_stage39a_median_mae_bps: float
    source_stage39a_median_mfe_bps: float


DEFAULT_STRICT_STAGE39A_CANDIDATES: List[CandidateSpec] = [
    CandidateSpec(
        candidate="BB_LOWER_REV_LONG_W120_K2.5",
        family="BOLLINGER_REVERSAL",
        side="LONG",
        horizon_hours=72,
        lookback_hours=120,
        trigger_type="bb_lower",
        threshold=2.5,
        source_stage39a_residual_bps=12.930408592169847,
        source_stage39a_event_clock_n=87,
        source_stage39a_median_mae_bps=-88.40617792181149,
        source_stage39a_median_mfe_bps=149.0487486707437,
    ),
    CandidateSpec(
        candidate="RANGE_BOTTOM_REV_LONG_W48_Q0.05",
        family="ROLLING_RANGE_REVERSAL",
        side="LONG",
        horizon_hours=72,
        lookback_hours=48,
        trigger_type="range_bottom",
        threshold=0.05,
        source_stage39a_residual_bps=8.961150568044353,
        source_stage39a_event_clock_n=177,
        source_stage39a_median_mae_bps=-82.90879175967936,
        source_stage39a_median_mfe_bps=120.25091360799101,
    ),
    CandidateSpec(
        candidate="RET_Z_DOWNSIDE_EXTREME_REV_LONG_L24_T1.5",
        family="RETURN_ZSCORE_REVERSAL",
        side="LONG",
        horizon_hours=120,
        lookback_hours=24,
        trigger_type="ret_z_downside",
        threshold=1.5,
        source_stage39a_residual_bps=6.98131119227718,
        source_stage39a_event_clock_n=172,
        source_stage39a_median_mae_bps=-120.22,
        source_stage39a_median_mfe_bps=175.98,
    ),
    CandidateSpec(
        candidate="BB_LOWER_REV_LONG_W24_K2",
        family="BOLLINGER_REVERSAL",
        side="LONG",
        horizon_hours=120,
        lookback_hours=24,
        trigger_type="bb_lower",
        threshold=2.0,
        source_stage39a_residual_bps=4.92131119227718,
        source_stage39a_event_clock_n=200,
        source_stage39a_median_mae_bps=-107.57,
        source_stage39a_median_mfe_bps=170.56,
    ),
]


def pick_col(columns: Sequence[str], candidates: Sequence[str], required: bool = True) -> Optional[str]:
    lower = {c.lower(): c for c in columns}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    if required:
        raise ValueError(
            f"Required column not found. Tried candidates={list(candidates)}; available={list(columns)}"
        )
    return None


def table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    if not rows:
        raise ValueError(f"Table not found or has no columns: {table}")
    return [r[1] for r in rows]


def sql_quote_ident(name: str) -> str:
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return '"' + name + '"'


def normalize_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalize_source_value(value: object) -> str:
    return normalize_text(value).lower()


def normalize_symbol_value(value: object) -> str:
    return normalize_text(value).upper()


def normalize_timeframe_value(value: object) -> str:
    txt = normalize_text(value).upper()
    compact = re.sub(r"[^A-Z0-9]", "", txt)
    aliases = {
        "H1": "H1",
        "1H": "H1",
        "60M": "H1",
        "60MIN": "H1",
        "60MINS": "H1",
        "60MINUTE": "H1",
        "60MINUTES": "H1",
        "1HR": "H1",
        "1HOUR": "H1",
        "1HOURS": "H1",
        "M60": "H1",
    }
    return aliases.get(compact, compact)


def sample_distinct_values(raw: pd.DataFrame, col: Optional[str], limit: int = 20) -> List[str]:
    if not col or col not in raw.columns:
        return []
    vals = raw[col].dropna().astype(str).map(lambda x: x.strip()).drop_duplicates().head(limit).tolist()
    return vals


def read_bars(
    db_path: str,
    table: str,
    symbol: Optional[str],
    source: Optional[str],
    timeframe: Optional[str],
    max_rows: Optional[int],
) -> Tuple[pd.DataFrame, Dict[str, object]]:
    """Read OHLC bars with DB-first filtering.

    Stage39A intentionally loaded the table first and then applied tolerant
    symbol/source/timeframe filters in pandas. Stage39B must do the same,
    because MT5-derived SQLite stores may use values such as `h1`, `1H`,
    `60M`, mixed-case source names, or whitespace-padded strings. Exact SQL
    predicates can therefore return zero rows even when the requested H1 data
    exists.
    """
    db = Path(db_path).expanduser()
    if not db.exists():
        raise FileNotFoundError(f"DB not found: {db}")

    with sqlite3.connect(str(db)) as conn:
        cols = table_columns(conn, table)
        ts_col = pick_col(cols, TIMESTAMP_CANDIDATES, required=True)
        open_col = pick_col(cols, OPEN_CANDIDATES, required=True)
        high_col = pick_col(cols, HIGH_CANDIDATES, required=True)
        low_col = pick_col(cols, LOW_CANDIDATES, required=True)
        close_col = pick_col(cols, CLOSE_CANDIDATES, required=True)
        spread_col = pick_col(cols, SPREAD_CANDIDATES, required=False)
        sym_col = pick_col(cols, SYMBOL_CANDIDATES, required=False)
        src_col = pick_col(cols, SOURCE_CANDIDATES, required=False)
        tf_col = pick_col(cols, TIMEFRAME_CANDIDATES, required=False)

        order = sql_quote_ident(ts_col)
        limit = f" LIMIT {int(max_rows)}" if max_rows else ""
        sql = f"SELECT * FROM {sql_quote_ident(table)} ORDER BY {order}{limit}"
        raw = pd.read_sql_query(sql, conn)

    pre_filter_rows = int(len(raw))
    distinct_values = {
        "symbol": sample_distinct_values(raw, sym_col),
        "source": sample_distinct_values(raw, src_col),
        "timeframe": sample_distinct_values(raw, tf_col),
    }

    filtered = raw.copy()
    filter_steps: List[Dict[str, object]] = []

    if symbol and sym_col:
        before = int(len(filtered))
        wanted = normalize_symbol_value(symbol)
        filtered = filtered[filtered[sym_col].map(normalize_symbol_value).eq(wanted)]
        filter_steps.append({"filter": "symbol", "requested": symbol, "normalized": wanted, "before": before, "after": int(len(filtered))})

    if source and src_col:
        before = int(len(filtered))
        wanted = normalize_source_value(source)
        filtered = filtered[filtered[src_col].map(normalize_source_value).eq(wanted)]
        filter_steps.append({"filter": "source", "requested": source, "normalized": wanted, "before": before, "after": int(len(filtered))})

    if timeframe and tf_col:
        before = int(len(filtered))
        wanted = normalize_timeframe_value(timeframe)
        filtered = filtered[filtered[tf_col].map(normalize_timeframe_value).eq(wanted)]
        filter_steps.append({"filter": "timeframe", "requested": timeframe, "normalized": wanted, "before": before, "after": int(len(filtered))})

    if filtered.empty:
        raise ValueError(
            "No rows loaded after tolerant DB-first filtering. "
            f"db={db}, table={table}, requested_symbol={symbol}, requested_source={source}, "
            f"requested_timeframe={timeframe}, pre_filter_rows={pre_filter_rows}, "
            f"detected_columns={{'timestamp': {ts_col!r}, 'symbol': {sym_col!r}, 'source': {src_col!r}, 'timeframe': {tf_col!r}}}, "
            f"distinct_values_sample={distinct_values}, filter_steps={filter_steps}"
        )

    df = pd.DataFrame()
    df["utc_time"] = pd.to_datetime(filtered[ts_col], utc=True, errors="coerce")
    df["open"] = pd.to_numeric(filtered[open_col], errors="coerce")
    df["high"] = pd.to_numeric(filtered[high_col], errors="coerce")
    df["low"] = pd.to_numeric(filtered[low_col], errors="coerce")
    df["close"] = pd.to_numeric(filtered[close_col], errors="coerce")
    df["spread"] = pd.to_numeric(filtered[spread_col], errors="coerce") if spread_col else np.nan

    df = df.dropna(subset=["utc_time", "open", "high", "low", "close"])
    df = df.sort_values("utc_time").drop_duplicates("utc_time").reset_index(drop=True)
    if df.empty:
        raise ValueError(
            "Rows existed after metadata filters, but no valid OHLC rows remained after timestamp/OHLC parsing. "
            f"db={db}, table={table}, columns={{'timestamp': {ts_col!r}, 'open': {open_col!r}, 'high': {high_col!r}, 'low': {low_col!r}, 'close': {close_col!r}}}"
        )
    df["year"] = df["utc_time"].dt.year.astype(int)

    meta = {
        "db_path": str(db),
        "table": table,
        "available_columns": cols,
        "columns": {
            "timestamp": ts_col,
            "open": open_col,
            "high": high_col,
            "low": low_col,
            "close": close_col,
            "spread": spread_col,
            "symbol": sym_col,
            "source": src_col,
            "timeframe": tf_col,
        },
        "requested_filters": {
            "symbol": symbol,
            "source": source,
            "timeframe": timeframe,
        },
        "distinct_values_sample": distinct_values,
        "filter_steps": filter_steps,
        "pre_filter_rows": pre_filter_rows,
        "post_filter_rows": int(len(filtered)),
        "loaded_rows": int(len(df)),
        "date_min": df["utc_time"].min().isoformat(),
        "date_max": df["utc_time"].max().isoformat(),
    }
    return df, meta


def infer_bar_hours(df: pd.DataFrame) -> float:
    dt = df["utc_time"].diff().dropna().dt.total_seconds() / 3600.0
    if dt.empty:
        return 1.0
    med = float(dt.median())
    if not math.isfinite(med) or med <= 0:
        return 1.0
    return med


def bps_return(entry: float, exit_: float, side: str) -> float:
    if not math.isfinite(entry) or entry <= 0 or not math.isfinite(exit_):
        return np.nan
    ret = (exit_ / entry - 1.0) * 10000.0
    return ret if side.upper() == "LONG" else -ret


def bps_move(entry: float, price: float, side: str) -> float:
    return bps_return(entry, price, side)


def deoverlap_indices(trigger_idx: Sequence[int], horizon_bars: int) -> List[int]:
    selected: List[int] = []
    next_allowed = -10**18
    for idx in sorted(int(i) for i in trigger_idx):
        if idx >= next_allowed:
            selected.append(idx)
            next_allowed = idx + horizon_bars
    return selected


def compute_trigger_mask(df: pd.DataFrame, spec: CandidateSpec) -> pd.Series:
    close = df["close"].astype(float)
    L = int(spec.lookback_hours)

    if spec.trigger_type == "bb_lower":
        mean = close.rolling(L, min_periods=L).mean()
        std = close.rolling(L, min_periods=L).std(ddof=0)
        z = (close - mean) / std.replace(0, np.nan)
        return z <= -float(spec.threshold)

    if spec.trigger_type == "range_bottom":
        roll_low = close.rolling(L, min_periods=L).min()
        roll_high = close.rolling(L, min_periods=L).max()
        pos = (close - roll_low) / (roll_high - roll_low).replace(0, np.nan)
        return pos <= float(spec.threshold)

    if spec.trigger_type == "ret_z_downside":
        # Cumulative L-hour return standardized by its own rolling L-window distribution.
        ret = close.pct_change(L) * 10000.0
        m = ret.rolling(L, min_periods=L).mean()
        s = ret.rolling(L, min_periods=L).std(ddof=0)
        z = (ret - m) / s.replace(0, np.nan)
        return z <= -float(spec.threshold)

    raise ValueError(f"Unsupported trigger_type: {spec.trigger_type}")


def read_stage39a_events(path: str) -> Optional[pd.DataFrame]:
    p = Path(path).expanduser()
    if not p.exists():
        return None
    df = pd.read_csv(p)
    if df.empty:
        return None
    return df


def event_csv_to_indices(events: pd.DataFrame, bars: pd.DataFrame, spec: CandidateSpec) -> Optional[List[int]]:
    if events is None or events.empty:
        return None

    cols = list(events.columns)
    cand_col = pick_col(cols, ["candidate", "signal", "setup"], required=False)
    horizon_col = pick_col(cols, ["horizon_hours", "horizon", "horizon_h"], required=False)
    ts_col = pick_col(
        cols,
        [
            "event_utc",
            "trigger_utc",
            "entry_utc",
            "utc_time",
            "ts_utc",
            "timestamp_utc",
            "timestamp",
            "time",
        ],
        required=False,
    )

    if not cand_col or not ts_col:
        return None

    sub = events[events[cand_col].astype(str) == spec.candidate].copy()
    if horizon_col:
        sub = sub[pd.to_numeric(sub[horizon_col], errors="coerce").astype("Int64") == int(spec.horizon_hours)]
    if sub.empty:
        return None

    t = pd.to_datetime(sub[ts_col], utc=True, errors="coerce").dropna().drop_duplicates().sort_values()
    if t.empty:
        return None

    time_to_idx = pd.Series(np.arange(len(bars)), index=bars["utc_time"])
    idx = []
    # Exact lookup first; if an event time is not exact, use nearest previous bar.
    bar_times = bars["utc_time"].to_numpy()
    for ts in t:
        if ts in time_to_idx.index:
            idx.append(int(time_to_idx.loc[ts]))
        else:
            pos = int(np.searchsorted(bar_times, np.datetime64(ts.to_datetime64()), side="right") - 1)
            if 0 <= pos < len(bars):
                idx.append(pos)
    return sorted(set(idx))


def build_event_rows_for_spec(
    bars: pd.DataFrame,
    spec: CandidateSpec,
    use_stage39a_events: Optional[pd.DataFrame],
    bar_hours: float,
    force_recompute: bool,
) -> Tuple[pd.DataFrame, Dict[str, object]]:
    horizon_bars = max(1, int(round(spec.horizon_hours / bar_hours)))

    raw_idx: List[int]
    source = "recomputed_from_stage39b_trigger"
    if not force_recompute and use_stage39a_events is not None:
        from_csv = event_csv_to_indices(use_stage39a_events, bars, spec)
        if from_csv:
            raw_idx = from_csv
            source = "stage39a_events_csv"
        else:
            mask = compute_trigger_mask(bars, spec)
            raw_idx = list(np.flatnonzero(mask.to_numpy()))
    else:
        mask = compute_trigger_mask(bars, spec)
        raw_idx = list(np.flatnonzero(mask.to_numpy()))

    valid_raw_idx = [i for i in raw_idx if i + horizon_bars < len(bars)]
    selected_idx = deoverlap_indices(valid_raw_idx, horizon_bars)

    rows: List[Dict[str, object]] = []
    for i in selected_idx:
        entry = float(bars.at[i, "close"])
        exit_i = i + horizon_bars
        exit_price = float(bars.at[exit_i, "close"])
        path = bars.iloc[i : exit_i + 1].copy()
        if spec.side.upper() == "LONG":
            path_bps = (path["close"].to_numpy(dtype=float) / entry - 1.0) * 10000.0
            high_bps = (path["high"].to_numpy(dtype=float) / entry - 1.0) * 10000.0
            low_bps = (path["low"].to_numpy(dtype=float) / entry - 1.0) * 10000.0
        else:
            path_bps = -(path["close"].to_numpy(dtype=float) / entry - 1.0) * 10000.0
            high_bps = -(path["low"].to_numpy(dtype=float) / entry - 1.0) * 10000.0
            low_bps = -(path["high"].to_numpy(dtype=float) / entry - 1.0) * 10000.0

        mfe = float(np.nanmax(high_bps))
        mae = float(np.nanmin(low_bps))
        final = bps_return(entry, exit_price, spec.side)
        max_adverse_hour = int(np.nanargmin(low_bps)) if np.isfinite(mae) else None
        max_favorable_hour = int(np.nanargmax(high_bps)) if np.isfinite(mfe) else None

        rows.append(
            {
                "stage": STAGE,
                "decision_scope": DECISION_SCOPE,
                "promotion": PROMOTION,
                "candidate": spec.candidate,
                "family": spec.family,
                "side": spec.side,
                "horizon_hours": int(spec.horizon_hours),
                "lookback_hours": int(spec.lookback_hours),
                "trigger_type": spec.trigger_type,
                "threshold": float(spec.threshold),
                "entry_idx": int(i),
                "entry_utc": bars.at[i, "utc_time"].isoformat(),
                "exit_idx": int(exit_i),
                "exit_utc": bars.at[exit_i, "utc_time"].isoformat(),
                "year": int(bars.at[i, "year"]),
                "entry_close": entry,
                "exit_close": exit_price,
                "final_bps": final,
                "mfe_bps": mfe,
                "mae_bps": mae,
                "max_adverse_hour": max_adverse_hour,
                "max_favorable_hour": max_favorable_hour,
                "source_stage39a_residual_bps": float(spec.source_stage39a_residual_bps),
                "source_stage39a_event_clock_n": int(spec.source_stage39a_event_clock_n),
            }
        )

    info = {
        "event_source": source,
        "raw_trigger_count": int(len(valid_raw_idx)),
        "event_clock_count": int(len(selected_idx)),
        "horizon_bars": int(horizon_bars),
        "bar_hours": float(bar_hours),
    }
    return pd.DataFrame(rows), info


def summarize_candidate(events: pd.DataFrame, spec: CandidateSpec, cost_bps: float, extra_slippage_bps: Sequence[float]) -> Dict[str, object]:
    final = events["final_bps"].astype(float)
    mae = events["mae_bps"].astype(float)
    mfe = events["mfe_bps"].astype(float)
    n = int(len(events))

    cost_stressed = final - float(cost_bps)
    residual_after_stage39a_benchmark = float(spec.source_stage39a_residual_bps)
    median_mae_abs = float(abs(np.nanmedian(mae))) if n else np.nan
    median_mfe = float(np.nanmedian(mfe)) if n else np.nan
    median_final = float(np.nanmedian(final)) if n else np.nan
    mean_final = float(np.nanmean(final)) if n else np.nan

    residual_to_median_mae = (
        residual_after_stage39a_benchmark / median_mae_abs if median_mae_abs and math.isfinite(median_mae_abs) else np.nan
    )
    median_mfe_to_median_mae = (
        median_mfe / median_mae_abs if median_mae_abs and math.isfinite(median_mae_abs) else np.nan
    )

    years = sorted(int(y) for y in events["year"].dropna().unique())
    year_means = {str(y): float(events.loc[events["year"] == y, "final_bps"].mean()) for y in years}
    year_counts = {str(y): int((events["year"] == y).sum()) for y in years}
    ex2025_mean = float(events.loc[events["year"] != 2025, "final_bps"].mean()) if n else np.nan
    pre2025_mean = float(events.loc[events["year"] < 2025, "final_bps"].mean()) if n else np.nan
    loo = {}
    for y in years:
        sub = events.loc[events["year"] != y, "final_bps"]
        loo[str(y)] = float(sub.mean()) if len(sub) else np.nan
    finite_loo_values = [float(v) for v in loo.values() if math.isfinite(float(v))]
    loo_min = min(finite_loo_values) if finite_loo_values else np.nan

    stress = {}
    for slip in extra_slippage_bps:
        stress[f"cost_plus_slip_{float(slip):g}_mean_bps"] = float(np.nanmean(final - cost_bps - float(slip)))
        stress[f"cost_plus_slip_{float(slip):g}_median_bps"] = float(np.nanmedian(final - cost_bps - float(slip)))

    # Simple touch diagnostics. These are not executable stop/TP backtests, only intrahorizon path stress probes.
    stop_levels = [50, 75, 100, 125, 150, 200]
    target_levels = [50, 75, 100, 125, 150, 200]
    touch = {}
    for s in stop_levels:
        touch[f"touch_stop_{s}bps_pct"] = float((mae <= -s).mean() * 100.0) if n else np.nan
    for t in target_levels:
        touch[f"touch_target_{t}bps_pct"] = float((mfe >= t).mean() * 100.0) if n else np.nan

    # Conservative diagnostic classification. This is intentionally not a promotion class.
    if n < 80:
        cls = "INSUFFICIENT_PATH_EVENTS_NO_PROMOTION"
    elif residual_after_stage39a_benchmark <= 0:
        cls = "NO_POSITIVE_STAGE39A_RESIDUAL_NO_PROMOTION"
    elif not math.isfinite(residual_to_median_mae) or residual_to_median_mae < 0.10:
        cls = "WEAK_RESIDUAL_VS_PATH_RISK_NO_PROMOTION"
    elif loo_min <= 0 or ex2025_mean <= 0:
        cls = "YEAR_ROBUSTNESS_WEAK_NO_PROMOTION"
    elif float(np.nanmean(cost_stressed)) <= 0:
        cls = "COST_STRESS_FAIL_NO_PROMOTION"
    else:
        cls = "PATH_DIAGNOSTIC_WATCH_ONLY_NO_PROMOTION"

    return {
        "stage": STAGE,
        "decision_scope": DECISION_SCOPE,
        "promotion": PROMOTION,
        "candidate": spec.candidate,
        "family": spec.family,
        "side": spec.side,
        "horizon_hours": int(spec.horizon_hours),
        "lookback_hours": int(spec.lookback_hours),
        "trigger_type": spec.trigger_type,
        "threshold": float(spec.threshold),
        "event_clock_n": n,
        "mean_final_bps": mean_final,
        "median_final_bps": median_final,
        "hit_rate_pct": float((final > 0).mean() * 100.0) if n else np.nan,
        "cost_bps": float(cost_bps),
        "cost_stressed_mean_bps": float(np.nanmean(cost_stressed)) if n else np.nan,
        "cost_stressed_median_bps": float(np.nanmedian(cost_stressed)) if n else np.nan,
        "median_mae_bps": float(np.nanmedian(mae)) if n else np.nan,
        "median_mfe_bps": median_mfe,
        "mean_mae_bps": float(np.nanmean(mae)) if n else np.nan,
        "mean_mfe_bps": float(np.nanmean(mfe)) if n else np.nan,
        "stage39a_h1_benchmark_cost_adjusted_residual_bps": residual_after_stage39a_benchmark,
        "residual_to_median_mae_abs": residual_to_median_mae,
        "median_mfe_to_median_mae_abs": median_mfe_to_median_mae,
        "ex2025_mean_bps": ex2025_mean,
        "pre2025_mean_bps": pre2025_mean,
        "leave_one_year_out_min_mean_bps": loo_min,
        "year_means_json": json.dumps(year_means, ensure_ascii=False),
        "year_counts_json": json.dumps(year_counts, ensure_ascii=False),
        "leave_one_year_out_json": json.dumps(loo, ensure_ascii=False),
        "classification": cls,
        **stress,
        **touch,
    }


def build_path_profile(bars: pd.DataFrame, events: pd.DataFrame, spec: CandidateSpec, bar_hours: float) -> pd.DataFrame:
    horizon_bars = max(1, int(round(spec.horizon_hours / bar_hours)))
    arrs = []
    for _, r in events.iterrows():
        i = int(r["entry_idx"])
        exit_i = i + horizon_bars
        if exit_i >= len(bars):
            continue
        entry = float(bars.at[i, "close"])
        path_close = bars.iloc[i : exit_i + 1]["close"].to_numpy(dtype=float)
        if spec.side.upper() == "LONG":
            bps = (path_close / entry - 1.0) * 10000.0
        else:
            bps = -(path_close / entry - 1.0) * 10000.0
        if len(bps) == horizon_bars + 1:
            arrs.append(bps)
    if not arrs:
        return pd.DataFrame()
    A = np.vstack(arrs)
    rows = []
    for h in range(A.shape[1]):
        vals = A[:, h]
        rows.append(
            {
                "candidate": spec.candidate,
                "side": spec.side,
                "horizon_hours": int(spec.horizon_hours),
                "path_hour": int(round(h * bar_hours)),
                "n": int(np.isfinite(vals).sum()),
                "mean_bps": float(np.nanmean(vals)),
                "p10_bps": float(np.nanpercentile(vals, 10)),
                "p25_bps": float(np.nanpercentile(vals, 25)),
                "median_bps": float(np.nanpercentile(vals, 50)),
                "p75_bps": float(np.nanpercentile(vals, 75)),
                "p90_bps": float(np.nanpercentile(vals, 90)),
            }
        )
    return pd.DataFrame(rows)


def maybe_write_plots(profile: pd.DataFrame, output_dir: Path) -> List[str]:
    paths: List[str] = []
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception:
        return paths

    plot_dir = output_dir / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)

    for cand, sub in profile.groupby("candidate"):
        sub = sub.sort_values("path_hour")
        fig = plt.figure(figsize=(9, 5))
        ax = fig.add_subplot(111)
        ax.plot(sub["path_hour"], sub["median_bps"], label="median")
        ax.plot(sub["path_hour"], sub["p25_bps"], label="p25")
        ax.plot(sub["path_hour"], sub["p75_bps"], label="p75")
        ax.plot(sub["path_hour"], sub["mean_bps"], label="mean")
        ax.axhline(0, linewidth=1)
        ax.set_title(f"{cand} path profile")
        ax.set_xlabel("hours after entry")
        ax.set_ylabel("directional bps")
        ax.legend()
        ax.grid(True, alpha=0.3)
        out = plot_dir / f"{cand}_path_profile.png"
        fig.tight_layout()
        fig.savefig(out, dpi=140)
        plt.close(fig)
        paths.append(str(out))
    return paths


def markdown_report(summary: Dict[str, object], cand_df: pd.DataFrame, year_df: pd.DataFrame, plot_paths: List[str]) -> str:
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
    lines.append("Stage39B is an event-path and tradability diagnostic for Stage39A strict research-watch rows. It is not a promotion gate.")
    lines.append("")
    lines.append("## Data audit")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(summary["data_audit"], indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")
    lines.append("## Classification counts")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(summary["classification_counts"], indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")
    lines.append("## Candidate path diagnostic summary")
    lines.append("")
    cols = [
        "classification",
        "candidate",
        "side",
        "horizon_hours",
        "event_clock_n",
        "mean_final_bps",
        "median_final_bps",
        "cost_stressed_mean_bps",
        "stage39a_h1_benchmark_cost_adjusted_residual_bps",
        "residual_to_median_mae_abs",
        "median_mae_bps",
        "median_mfe_bps",
        "ex2025_mean_bps",
        "leave_one_year_out_min_mean_bps",
        "touch_stop_100bps_pct",
        "touch_target_100bps_pct",
    ]
    view = cand_df[cols].copy()
    for c in view.columns:
        if pd.api.types.is_float_dtype(view[c]):
            view[c] = view[c].map(lambda x: "" if pd.isna(x) else f"{x:.2f}")
    lines.append(view.to_markdown(index=False))
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("- `PATH_DIAGNOSTIC_WATCH_ONLY_NO_PROMOTION` means the row can remain under research observation only.")
    lines.append("- `WEAK_RESIDUAL_VS_PATH_RISK_NO_PROMOTION` means Stage39A residual is too small relative to intrahorizon adverse excursion.")
    lines.append("- `YEAR_ROBUSTNESS_WEAK_NO_PROMOTION` means ex-2025 or leave-one-year-out sanity is not robust enough.")
    lines.append("- `INSUFFICIENT_PATH_EVENTS_NO_PROMOTION` means event path evidence is still too thin.")
    lines.append("")
    lines.append("## Path plots")
    lines.append("")
    if plot_paths:
        for p in plot_paths:
            lines.append(f"- `{p}`")
    else:
        lines.append("- Plot generation skipped because matplotlib was not available.")
    lines.append("")
    lines.append("## Next allowed step")
    lines.append("")
    lines.append("Only if one or more candidates remain `PATH_DIAGNOSTIC_WATCH_ONLY_NO_PROMOTION`, the next step is a Stage39C microstructure/session-condition diagnostic. Otherwise archive Stage39A/B and do not extend weak rows with filters.")
    lines.append("")
    return "\n".join(lines)


def write_year_split(events_all: pd.DataFrame) -> pd.DataFrame:
    if events_all.empty:
        return pd.DataFrame()
    g = events_all.groupby(["candidate", "year"], dropna=False)
    rows = []
    for (cand, year), sub in g:
        vals = sub["final_bps"].astype(float)
        rows.append(
            {
                "candidate": cand,
                "year": int(year),
                "n": int(len(sub)),
                "mean_final_bps": float(vals.mean()),
                "median_final_bps": float(vals.median()),
                "hit_rate_pct": float((vals > 0).mean() * 100.0),
                "median_mae_bps": float(sub["mae_bps"].median()),
                "median_mfe_bps": float(sub["mfe_bps"].median()),
            }
        )
    return pd.DataFrame(rows).sort_values(["candidate", "year"]).reset_index(drop=True)


def run(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    bars, data_audit = read_bars(
        db_path=args.db,
        table=args.table,
        symbol=args.symbol,
        source=args.source,
        timeframe=args.timeframe,
        max_rows=args.max_rows,
    )
    bar_hours = infer_bar_hours(bars)

    events_csv = read_stage39a_events(args.stage39a_events)

    specs = DEFAULT_STRICT_STAGE39A_CANDIDATES
    if args.candidates:
        keep = {x.strip() for x in args.candidates.split(",") if x.strip()}
        specs = [s for s in specs if s.candidate in keep]
        if not specs:
            raise ValueError(f"No candidate matched --candidates={args.candidates}")

    all_events = []
    build_info = {}
    for spec in specs:
        ev, info = build_event_rows_for_spec(
            bars=bars,
            spec=spec,
            use_stage39a_events=events_csv,
            bar_hours=bar_hours,
            force_recompute=args.force_recompute_events,
        )
        build_info[spec.candidate] = info
        all_events.append(ev)

    events_all = pd.concat(all_events, ignore_index=True) if all_events else pd.DataFrame()
    if events_all.empty:
        raise ValueError("No Stage39B diagnostic events generated.")

    candidate_rows = []
    extra_slips = [float(x) for x in args.extra_slippage_bps.split(",") if x.strip()]
    for spec in specs:
        sub = events_all[events_all["candidate"] == spec.candidate]
        candidate_rows.append(summarize_candidate(sub, spec, args.cost_bps, extra_slips))

    cand_df = pd.DataFrame(candidate_rows).sort_values(
        ["classification", "stage39a_h1_benchmark_cost_adjusted_residual_bps"],
        ascending=[True, False],
    )
    year_df = write_year_split(events_all)
    profile = pd.concat(
        [build_path_profile(bars, events_all[events_all["candidate"] == s.candidate], s, bar_hours) for s in specs],
        ignore_index=True,
    )
    plot_paths = maybe_write_plots(profile, output_dir) if not args.no_plots else []

    classification_counts = {
        str(k): int(v) for k, v in cand_df["classification"].value_counts(dropna=False).to_dict().items()
    }

    summary = {
        "stage": STAGE,
        "decision_scope": DECISION_SCOPE,
        "promotion": PROMOTION,
        "ea": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "data_audit": data_audit,
        "parameters": {
            "symbol": args.symbol,
            "source": args.source,
            "timeframe": args.timeframe,
            "cost_bps": float(args.cost_bps),
            "extra_slippage_bps": extra_slips,
            "stage39a_events": args.stage39a_events,
            "force_recompute_events": bool(args.force_recompute_events),
            "bar_hours": float(bar_hours),
        },
        "stage39a_context": {
            "strict_research_watch_source": "Stage39A strict rows only",
            "candidate_count": int(len(specs)),
            "candidate_specs": [asdict(s) for s in specs],
        },
        "event_build_info": build_info,
        "classification_counts": classification_counts,
        "path_watch_count": int((cand_df["classification"] == "PATH_DIAGNOSTIC_WATCH_ONLY_NO_PROMOTION").sum()),
        "outputs": {
            "candidate_summary_csv": str(output_dir / "stage39b_event_path_candidate_summary.csv"),
            "event_rows_csv": str(output_dir / "stage39b_event_path_event_rows.csv"),
            "year_split_csv": str(output_dir / "stage39b_event_path_year_split.csv"),
            "path_profile_csv": str(output_dir / "stage39b_event_path_profile.csv"),
            "summary_json": str(output_dir / "stage39b_event_path_diagnostic_summary.json"),
            "markdown": str(output_dir / "stage39b_event_path_tradability.md"),
            "plots": plot_paths,
        },
    }

    cand_df.to_csv(output_dir / "stage39b_event_path_candidate_summary.csv", index=False)
    events_all.to_csv(output_dir / "stage39b_event_path_event_rows.csv", index=False)
    year_df.to_csv(output_dir / "stage39b_event_path_year_split.csv", index=False)
    profile.to_csv(output_dir / "stage39b_event_path_profile.csv", index=False)
    with open(output_dir / "stage39b_event_path_diagnostic_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    with open(output_dir / "stage39b_event_path_tradability.md", "w", encoding="utf-8") as f:
        f.write(markdown_report(summary, cand_df, year_df, plot_paths))

    print(json.dumps({
        "stage": STAGE,
        "promotion": PROMOTION,
        "rows": int(len(events_all)),
        "classification_counts": classification_counts,
        "output_dir": str(output_dir),
    }, indent=2, ensure_ascii=False))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=STAGE)
    p.add_argument("--db", default="data/local/xauusd_local_store.sqlite")
    p.add_argument("--table", default="bars")
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--source", default="amarkets_mt5")
    p.add_argument("--timeframe", default="H1")
    p.add_argument("--stage39a-events", default="reports/stage39a/stage39a_reversal_mean_reversion_event_clock_events.csv")
    p.add_argument("--output-dir", default="reports/stage39b")
    p.add_argument("--cost-bps", type=float, default=8.0)
    p.add_argument("--extra-slippage-bps", default="0,4,8,12,16")
    p.add_argument("--candidates", default="", help="Optional comma-separated candidate names.")
    p.add_argument("--max-rows", type=int, default=0)
    p.add_argument("--force-recompute-events", action="store_true")
    p.add_argument("--no-plots", action="store_true")
    return p.parse_args()


def main() -> None:
    run(parse_args())


if __name__ == "__main__":
    main()
