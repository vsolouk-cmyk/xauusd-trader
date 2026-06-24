#!/usr/bin/env python3
"""
Stage42_PARALLEL_INTRADAY_EXECUTION_MEGASCAN_V3

Independent XAUUSD intraday thesis megascan after Stage41 archive.
Default timeframe is M15 because the local DB contains a much deeper M15 history
than H1. This script is research-only: it cannot promote candidates and it never
writes EA/paper-live/live execution artifacts.

Outputs:
  reports/stage42/stage42_parallel_intraday_execution_megascan_v3_candidates.csv
  reports/stage42/stage42_parallel_intraday_execution_megascan_v3_events.csv
  reports/stage42/stage42_parallel_intraday_execution_megascan_v3_summary.json
  reports/stage42/stage42_parallel_intraday_execution_megascan_v3.md
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning, message="Mean of empty slice")
warnings.filterwarnings(
    "ignore",
    message="Converting to PeriodArray/Index representation will drop timezone information.",
    category=UserWarning,
)

STAGE_NAME = "Stage42_PARALLEL_INTRADAY_EXECUTION_MEGASCAN_V3"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_TABLE = "bars"
DEFAULT_OUTDIR = Path("reports/stage42")
DEFAULT_SOURCE = "amarkets_mt5"
DEFAULT_SYMBOL = "XAUUSD"
DEFAULT_TIMEFRAME = "M15"

NO_PROMOTION_STATE = {
    "promotion": "NO_GO",
    "EA": "NO_GO",
    "paper_live": "NO_GO",
    "live": "NO_GO",
}

CLASS_STRICT = "STRICT_STAGE42_INTRADAY_SCAN_WATCH_ONLY_NO_PROMOTION"
CLASS_SOFT = "SOFT_STAGE42_INTRADAY_SCAN_WATCH_ONLY_NO_PROMOTION"
CLASS_FAIL = "FAIL_BENCHMARK_OR_INTRADAY_STABILITY_RESEARCH_ONLY"
CLASS_INSUFFICIENT = "INSUFFICIENT_EVENTS_RESEARCH_ONLY"
CLASS_ERROR = "ERROR_RESEARCH_ONLY"


@dataclass(frozen=True)
class ThesisSpec:
    family: str
    candidate: str
    side: str
    horizon_bars: int
    min_gap_bars: int
    mask_col: str
    description: str


def _first_existing(cols: Sequence[str], names: Sequence[str]) -> Optional[str]:
    lower_map = {c.lower(): c for c in cols}
    for name in names:
        if name.lower() in lower_map:
            return lower_map[name.lower()]
    return None


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _norm_text(value: object) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip().casefold()


def _norm_compact(value: object) -> str:
    return "".join(ch for ch in _norm_text(value) if ch.isalnum())


def _norm_timeframe(value: object) -> str:
    raw = _norm_compact(value).upper()
    aliases = {
        "1H": "H1", "H1": "H1", "60": "H1", "60M": "H1", "M60": "H1",
        "60MIN": "H1", "60MINS": "H1", "60MINUTE": "H1", "60MINUTES": "H1",
        "1M": "M1", "M1": "M1", "1MIN": "M1", "1MINUTE": "M1",
        "5M": "M5", "M5": "M5", "5MIN": "M5", "5MINS": "M5", "5MINUTE": "M5", "5MINUTES": "M5",
        "15M": "M15", "M15": "M15", "15MIN": "M15", "15MINS": "M15", "15MINUTE": "M15", "15MINUTES": "M15",
        "30M": "M30", "M30": "M30", "30MIN": "M30", "30MINS": "M30",
        "4H": "H4", "H4": "H4", "240": "H4", "240M": "H4", "M240": "H4",
        "1D": "D1", "D1": "D1", "DAILY": "D1",
    }
    return aliases.get(raw, raw)


def _timeframe_minutes(tf: object) -> int:
    norm = _norm_timeframe(tf)
    mapping = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}
    if norm not in mapping:
        raise ValueError(f"Unsupported timeframe for intraday Stage42: {tf!r} -> {norm!r}")
    minutes = mapping[norm]
    if minutes > 60:
        raise ValueError(f"Stage42 is intraday-only; use M1/M5/M15/M30/H1, got {norm}")
    return minutes


def _series_norm(series: pd.Series) -> pd.Series:
    return series.astype("string").fillna("").map(_norm_text)


def _series_compact(series: pd.Series) -> pd.Series:
    return series.astype("string").fillna("").map(_norm_compact)


def _series_timeframe(series: pd.Series) -> pd.Series:
    return series.astype("string").fillna("").map(_norm_timeframe)


def _distinct_preview(conn: sqlite3.Connection, table: str, col: Optional[str], limit: int = 20) -> List[Dict[str, object]]:
    if not col:
        return []
    sql = (
        f"SELECT {_quote_ident(col)} AS value, COUNT(*) AS n "
        f"FROM {_quote_ident(table)} GROUP BY {_quote_ident(col)} "
        f"ORDER BY n DESC, value ASC LIMIT ?"
    )
    try:
        rows = pd.read_sql_query(sql, conn, params=[int(limit)])
    except Exception:
        return []
    out: List[Dict[str, object]] = []
    for _, r in rows.iterrows():
        out.append({"value": None if pd.isna(r["value"]) else str(r["value"]), "n": int(r["n"])})
    return out


def _read_sqlite_bars(
    db_path: Path,
    table: str,
    source: str,
    symbol: str,
    timeframe: str,
) -> Tuple[pd.DataFrame, Dict[str, object]]:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    with sqlite3.connect(str(db_path)) as conn:
        table_cols = pd.read_sql_query(f"PRAGMA table_info({_quote_ident(table)})", conn)
        if table_cols.empty:
            raise RuntimeError(f"No table metadata found for table={table!r}")
        cols = table_cols["name"].astype(str).tolist()

        ts_col = _first_existing(cols, ["ts_utc", "utc_time", "timestamp_utc", "time_utc", "datetime_utc", "timestamp", "source_time", "time", "datetime", "date"])
        open_col = _first_existing(cols, ["open", "o"])
        high_col = _first_existing(cols, ["high", "h"])
        low_col = _first_existing(cols, ["low", "l"])
        close_col = _first_existing(cols, ["close", "c"])
        volume_col = _first_existing(cols, ["volume", "tick_volume", "real_volume", "vol"])
        spread_col = _first_existing(cols, ["spread", "spread_points", "spread_bps"])
        source_col = _first_existing(cols, ["source", "data_source", "feed"])
        symbol_col = _first_existing(cols, ["symbol", "instrument", "pair"])
        timeframe_col = _first_existing(cols, ["timeframe", "tf", "granularity"])

        required = {"timestamp": ts_col, "open": open_col, "high": high_col, "low": low_col, "close": close_col}
        missing = [k for k, v in required.items() if v is None]
        if missing:
            raise RuntimeError(f"Missing required OHLC columns in {table!r}: {missing}; available={cols}")

        dimension_preview = {
            "source": _distinct_preview(conn, table, source_col),
            "symbol": _distinct_preview(conn, table, symbol_col),
            "timeframe": _distinct_preview(conn, table, timeframe_col),
        }

        selected = [ts_col, open_col, high_col, low_col, close_col]
        for optional_col in [volume_col, spread_col, source_col, symbol_col, timeframe_col]:
            if optional_col and optional_col not in selected:
                selected.append(optional_col)

        sql = f"SELECT {', '.join(_quote_ident(c) for c in selected)} FROM {_quote_ident(table)} ORDER BY {_quote_ident(ts_col)} ASC"
        raw = pd.read_sql_query(sql, conn)

    rename = {
        ts_col: "ts_utc",
        open_col: "open",
        high_col: "high",
        low_col: "low",
        close_col: "close",
    }
    if volume_col:
        rename[volume_col] = "volume"
    if spread_col:
        rename[spread_col] = "spread_raw"
    if source_col:
        rename[source_col] = "__source_raw"
    if symbol_col:
        rename[symbol_col] = "__symbol_raw"
    if timeframe_col:
        rename[timeframe_col] = "__timeframe_raw"

    df = raw.rename(columns=rename)
    pre_filter_rows = int(len(df))
    filter_debug: Dict[str, object] = {
        "requested_source": source,
        "requested_symbol": symbol,
        "requested_timeframe": timeframe,
        "pre_filter_rows": pre_filter_rows,
        "normalization": "source/symbol use strip+casefold+compact; timeframe uses aliases such as 15m/M15/15MIN -> M15",
    }

    mask = pd.Series(True, index=df.index)
    if source_col and "__source_raw" in df.columns:
        exact = _series_norm(df["__source_raw"]) == _norm_text(source)
        compact = _series_compact(df["__source_raw"]) == _norm_compact(source)
        source_mask = exact | compact
        filter_debug["source_exact_matches"] = int(exact.sum())
        filter_debug["source_compact_matches"] = int(compact.sum())
        mask &= source_mask
    if symbol_col and "__symbol_raw" in df.columns:
        exact = _series_norm(df["__symbol_raw"]) == _norm_text(symbol)
        compact = _series_compact(df["__symbol_raw"]) == _norm_compact(symbol)
        symbol_mask = exact | compact
        filter_debug["symbol_exact_matches"] = int(exact.sum())
        filter_debug["symbol_compact_matches"] = int(compact.sum())
        mask &= symbol_mask
    if timeframe_col and "__timeframe_raw" in df.columns:
        tf_norm = _series_timeframe(df["__timeframe_raw"])
        requested_tf = _norm_timeframe(timeframe)
        timeframe_mask = tf_norm == requested_tf
        filter_debug["requested_timeframe_normalized"] = requested_tf
        filter_debug["timeframe_alias_matches"] = int(timeframe_mask.sum())
        mask &= timeframe_mask

    df = df.loc[mask].copy()
    filter_debug["post_filter_rows_before_ohlc_clean"] = int(len(df))

    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close", "volume", "spread_raw"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["ts_utc", "open", "high", "low", "close"])
    df = df.drop_duplicates(subset=["ts_utc"], keep="last").sort_values("ts_utc").reset_index(drop=True)
    filter_debug["post_filter_rows_after_ohlc_clean"] = int(len(df))

    if df.empty:
        diagnostic = {
            "error": "No bars loaded after normalized filtering",
            "db_path": str(db_path),
            "table": table,
            "detected_columns": {
                "timestamp": ts_col,
                "open": open_col,
                "high": high_col,
                "low": low_col,
                "close": close_col,
                "volume": volume_col,
                "spread": spread_col,
                "source": source_col,
                "symbol": symbol_col,
                "timeframe": timeframe_col,
            },
            "available_dimensions_top20": dimension_preview,
            "filter_debug": filter_debug,
            "suggestion": "Run again with --source/--symbol/--timeframe matching available_dimensions_top20, e.g. --timeframe M15 or --timeframe 15m.",
        }
        raise RuntimeError(json.dumps(diagnostic, ensure_ascii=False, indent=2))

    loaded_dimension_values: Dict[str, List[str]] = {}
    for raw_col, key in [("__source_raw", "source"), ("__symbol_raw", "symbol"), ("__timeframe_raw", "timeframe")]:
        if raw_col in df.columns:
            vals = sorted({str(x) for x in df[raw_col].dropna().unique().tolist()})
            loaded_dimension_values[key] = vals[:20]
    df = df.drop(columns=[c for c in ["__source_raw", "__symbol_raw", "__timeframe_raw"] if c in df.columns])

    tf_minutes = _timeframe_minutes(timeframe)
    loaded_start = df["ts_utc"].iloc[0].isoformat()
    loaded_end = df["ts_utc"].iloc[-1].isoformat()
    meta = {
        "db_path": str(db_path),
        "table": table,
        "source_filter_used": bool(source_col),
        "symbol_filter_used": bool(symbol_col),
        "timeframe_filter_used": bool(timeframe_col),
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "timeframe_normalized": _norm_timeframe(timeframe),
        "timeframe_minutes": tf_minutes,
        "loaded_rows": int(len(df)),
        "loaded_start": loaded_start,
        "loaded_end": loaded_end,
        "columns_detected": {
            "timestamp": ts_col,
            "open": open_col,
            "high": high_col,
            "low": low_col,
            "close": close_col,
            "volume": volume_col,
            "spread": spread_col,
            "source": source_col,
            "symbol": symbol_col,
            "timeframe": timeframe_col,
        },
        "available_dimensions_top20": dimension_preview,
        "loaded_dimension_values_top20": loaded_dimension_values,
        "filter_debug": filter_debug,
    }
    return df, meta


def _safe_div(a: pd.Series, b: pd.Series) -> pd.Series:
    return a / b.replace(0, np.nan)


def _bars_for_hours(hours: float, tf_minutes: int, minimum: int = 1) -> int:
    return max(minimum, int(round(hours * 60.0 / tf_minutes)))


def _add_features(df: pd.DataFrame, tf_minutes: int) -> Tuple[pd.DataFrame, Dict[str, int]]:
    d = df.copy()
    d["hour_utc"] = d["ts_utc"].dt.hour
    d["minute_utc"] = d["ts_utc"].dt.minute
    d["minute_of_day"] = d["hour_utc"] * 60 + d["minute_utc"]
    d["weekday"] = d["ts_utc"].dt.day_name()
    d["year"] = d["ts_utc"].dt.year
    d["quarter"] = d["ts_utc"].dt.to_period("Q").astype(str)
    d["date"] = d["ts_utc"].dt.date.astype(str)

    def session(h: int) -> str:
        if 0 <= h <= 5:
            return "ASIA_CORE"
        if 6 <= h <= 8:
            return "LONDON_OPEN"
        if 9 <= h <= 11:
            return "LONDON_MID"
        if 12 <= h <= 16:
            return "LONDON_NY_OVERLAP"
        if 17 <= h <= 21:
            return "NY_LATE"
        return "ROLLOVER"

    d["session_utc"] = d["hour_utc"].map(session)
    d["tradable_session"] = d["hour_utc"].between(6, 20)

    prev_close = d["close"].shift(1)
    tr1 = d["high"] - d["low"]
    tr2 = (d["high"] - prev_close).abs()
    tr3 = (d["low"] - prev_close).abs()
    tr_abs = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    d["tr_bps"] = _safe_div(tr_abs, d["close"]) * 10000.0
    d["range_bps"] = _safe_div(d["high"] - d["low"], d["close"]) * 10000.0
    d["body_bps"] = _safe_div((d["close"] - d["open"]).abs(), d["close"]) * 10000.0
    d["signed_body_bps"] = _safe_div(d["close"] - d["open"], d["close"]) * 10000.0
    d["upper_wick_bps"] = _safe_div(d["high"] - d[["open", "close"]].max(axis=1), d["close"]) * 10000.0
    d["lower_wick_bps"] = _safe_div(d[["open", "close"]].min(axis=1) - d["low"], d["close"]) * 10000.0

    bars = {
        "b1h": _bars_for_hours(1, tf_minutes),
        "b2h": _bars_for_hours(2, tf_minutes),
        "b4h": _bars_for_hours(4, tf_minutes),
        "b8h": _bars_for_hours(8, tf_minutes),
        "b12h": _bars_for_hours(12, tf_minutes),
        "b24h": _bars_for_hours(24, tf_minutes),
        "b48h": _bars_for_hours(48, tf_minutes),
    }

    rolling_windows = sorted(set([bars["b1h"], bars["b2h"], bars["b4h"], bars["b8h"], bars["b12h"], bars["b24h"], bars["b48h"]]))
    for w in rolling_windows:
        minp = max(3, min(w, max(3, w // 4)))
        d[f"ret{w}_bps"] = (d["close"] / d["close"].shift(w) - 1.0) * 10000.0
        d[f"atr{w}_bps"] = d["tr_bps"].rolling(w, min_periods=minp).mean()
        d[f"roll_high{w}"] = d["high"].shift(1).rolling(w, min_periods=minp).max()
        d[f"roll_low{w}"] = d["low"].shift(1).rolling(w, min_periods=minp).min()
        d[f"sma{w}"] = d["close"].rolling(w, min_periods=minp).mean()

    # Default M15 horizons: 1h, 2h, 4h, 8h. For M5/M30 these scale by bars.
    for h in [bars["b1h"], bars["b2h"], bars["b4h"], bars["b8h"]]:
        d[f"fwd{h}_ret_bps"] = (d["close"].shift(-h) / d["close"] - 1.0) * 10000.0

    d["trend_up_4h_24h"] = (d["close"] > d[f"sma{bars['b24h']}"]) & (d[f"ret{bars['b4h']}_bps"] > 0)
    d["trend_down_4h_24h"] = (d["close"] < d[f"sma{bars['b24h']}"]) & (d[f"ret{bars['b4h']}_bps"] < 0)
    d["micro_up"] = (d[f"ret{bars['b1h']}_bps"] > 0) & (d["close"] > d[f"sma{bars['b4h']}"])
    d["micro_down"] = (d[f"ret{bars['b1h']}_bps"] < 0) & (d["close"] < d[f"sma{bars['b4h']}"])

    daily = d.groupby("date", sort=True).agg(
        day_high=("high", "max"),
        day_low=("low", "min"),
        day_open=("open", "first"),
        day_close=("close", "last"),
    )
    daily["prev_day_high"] = daily["day_high"].shift(1)
    daily["prev_day_low"] = daily["day_low"].shift(1)
    daily["prev_day_close"] = daily["day_close"].shift(1)
    daily["prev_day_range_bps"] = (daily["prev_day_high"] / daily["prev_day_low"] - 1.0) * 10000.0

    asia = d[d["hour_utc"].between(0, 5)].groupby("date", sort=True).agg(
        asia_high=("high", "max"),
        asia_low=("low", "min"),
    )
    asia["asia_range_bps"] = (asia["asia_high"] / asia["asia_low"] - 1.0) * 10000.0

    london_morning = d[d["hour_utc"].between(6, 10)].groupby("date", sort=True).agg(
        london_morning_high=("high", "max"),
        london_morning_low=("low", "min"),
        london_morning_close=("close", "last"),
    )
    london_morning["london_morning_mid"] = (london_morning["london_morning_high"] + london_morning["london_morning_low"]) / 2.0
    london_morning["london_morning_range_bps"] = (london_morning["london_morning_high"] / london_morning["london_morning_low"] - 1.0) * 10000.0

    d = d.merge(daily[["prev_day_high", "prev_day_low", "prev_day_close", "prev_day_range_bps"]], left_on="date", right_index=True, how="left")
    d = d.merge(asia[["asia_high", "asia_low", "asia_range_bps"]], left_on="date", right_index=True, how="left")
    d = d.merge(
        london_morning[["london_morning_high", "london_morning_low", "london_morning_mid", "london_morning_range_bps"]],
        left_on="date",
        right_index=True,
        how="left",
    )
    d.loc[d["hour_utc"] <= 5, ["asia_high", "asia_low", "asia_range_bps"]] = np.nan
    d.loc[d["hour_utc"] <= 10, ["london_morning_high", "london_morning_low", "london_morning_mid", "london_morning_range_bps"]] = np.nan

    return d, bars


def _build_signal_masks(d: pd.DataFrame, bars: Dict[str, int]) -> Tuple[pd.DataFrame, List[ThesisSpec]]:
    specs: List[ThesisSpec] = []
    horizons = [bars["b1h"], bars["b2h"], bars["b4h"], bars["b8h"]]
    horizon_subset_fast = [bars["b1h"], bars["b2h"], bars["b4h"]]

    def add(mask_name: str, family: str, candidate: str, side: str, horizon: int, min_gap: int, mask: pd.Series, description: str) -> None:
        d[mask_name] = mask.fillna(False).astype(bool)
        specs.append(ThesisSpec(family=family, candidate=candidate, side=side, horizon_bars=horizon, min_gap_bars=min_gap, mask_col=mask_name, description=description))

    # 42A: London open Asia-range micro break + retest/hold.
    for tol in [8, 15, 25, 40]:
        asia_ready = d["asia_high"].notna() & d["asia_low"].notna() & d["asia_range_bps"].between(20, 160)
        liquid_time = d["hour_utc"].between(6, 10)
        long_mask = (
            asia_ready & liquid_time
            & (d["high"] > d["asia_high"] * 1.0002)
            & (d["low"] <= d["asia_high"] * (1.0 + tol / 10000.0))
            & (d["close"] > d["asia_high"])
            & (d["signed_body_bps"] > 0)
            & (d["range_bps"] < d[f"atr{bars['b24h']}_bps"] * 1.80)
        )
        short_mask = (
            asia_ready & liquid_time
            & (d["low"] < d["asia_low"] * 0.9998)
            & (d["high"] >= d["asia_low"] * (1.0 - tol / 10000.0))
            & (d["close"] < d["asia_low"])
            & (d["signed_body_bps"] < 0)
            & (d["range_bps"] < d[f"atr{bars['b24h']}_bps"] * 1.80)
        )
        for h in horizon_subset_fast:
            add(f"sig_42a_london_asia_break_hold_long_tol{tol}_h{h}", "42A_LONDON_ASIA_RANGE_MICRO_RETEST", f"LONDON_ASIA_BREAK_HOLD_LONG_TOL{tol}", "LONG", h, h, long_mask, "M15 London-open Asia range break, retest, and hold continuation.")
            add(f"sig_42a_london_asia_break_hold_short_tol{tol}_h{h}", "42A_LONDON_ASIA_RANGE_MICRO_RETEST", f"LONDON_ASIA_BREAK_HOLD_SHORT_TOL{tol}", "SHORT", h, h, short_mask, "M15 London-open Asia range break, retest, and hold continuation.")

    # 42B: NY/open impulse pullback continuation after controlled retrace.
    for impulse in [20, 35, 50, 70]:
        impulse_up = d[f"ret{bars['b1h']}_bps"] > impulse
        impulse_down = d[f"ret{bars['b1h']}_bps"] < -impulse
        ny_window = d["hour_utc"].between(12, 16)
        controlled_bar = d["range_bps"] < d[f"atr{bars['b8h']}_bps"] * 1.45
        long_mask = ny_window & impulse_up & controlled_bar & (d["low"] <= d[f"sma{bars['b1h']}"] * 1.0015) & (d["close"] > d[f"sma{bars['b1h']}"]) & d["micro_up"]
        short_mask = ny_window & impulse_down & controlled_bar & (d["high"] >= d[f"sma{bars['b1h']}"] * 0.9985) & (d["close"] < d[f"sma{bars['b1h']}"]) & d["micro_down"]
        for h in horizons:
            add(f"sig_42b_ny_impulse_pullback_long_i{impulse}_h{h}", "42B_NY_IMPULSE_PULLBACK_CONTINUATION", f"NY_IMPULSE_PULLBACK_LONG_I{impulse}", "LONG", h, h, long_mask, "NY overlap continuation after a one-hour impulse and controlled pullback to micro mean.")
            add(f"sig_42b_ny_impulse_pullback_short_i{impulse}_h{h}", "42B_NY_IMPULSE_PULLBACK_CONTINUATION", f"NY_IMPULSE_PULLBACK_SHORT_I{impulse}", "SHORT", h, h, short_mask, "NY overlap continuation after a one-hour impulse and controlled pullback to micro mean.")

    # 42C: Previous-day level sweep and reclaim/reject intraday reversal.
    for tol in [5, 12, 20, 35]:
        prev_ready = d["prev_day_high"].notna() & d["prev_day_low"].notna() & d["prev_day_range_bps"].between(50, 350)
        active = d["hour_utc"].between(7, 17)
        sweep_high_reject_short = (
            prev_ready & active
            & (d["high"] > d["prev_day_high"] * (1.0 + tol / 10000.0))
            & (d["close"] < d["prev_day_high"])
            & (d["upper_wick_bps"] >= d["body_bps"] * 0.75)
            & (d["signed_body_bps"] < 0)
        )
        sweep_low_reclaim_long = (
            prev_ready & active
            & (d["low"] < d["prev_day_low"] * (1.0 - tol / 10000.0))
            & (d["close"] > d["prev_day_low"])
            & (d["lower_wick_bps"] >= d["body_bps"] * 0.75)
            & (d["signed_body_bps"] > 0)
        )
        for h in horizon_subset_fast:
            add(f"sig_42c_prevday_sweep_reclaim_long_tol{tol}_h{h}", "42C_PREVDAY_LIQUIDITY_SWEEP_REVERSAL", f"PREVDAY_LOW_SWEEP_RECLAIM_LONG_TOL{tol}", "LONG", h, h, sweep_low_reclaim_long, "Intraday liquidity sweep below previous-day low followed by reclaim.")
            add(f"sig_42c_prevday_sweep_reject_short_tol{tol}_h{h}", "42C_PREVDAY_LIQUIDITY_SWEEP_REVERSAL", f"PREVDAY_HIGH_SWEEP_REJECT_SHORT_TOL{tol}", "SHORT", h, h, sweep_high_reject_short, "Intraday liquidity sweep above previous-day high followed by rejection.")

    # 42D: Intraday compression -> two-bar expansion confirmation, not the failed H1 Stage40/41 one-bar variant.
    for comp_hours in [4, 8, 12, 24]:
        w = _bars_for_hours(comp_hours, max(1, int(24 * 60 / bars["b24h"]))) if False else {4: bars["b4h"], 8: bars["b8h"], 12: bars["b12h"], 24: bars["b24h"]}[comp_hours]
        compression = d[f"atr{bars['b1h']}_bps"] < d[f"atr{w}_bps"] * 0.72
        two_up = (d["close"] > d["open"]) & (d["close"].shift(1) > d["open"].shift(1)) & (d["close"] > d["high"].shift(1))
        two_down = (d["close"] < d["open"]) & (d["close"].shift(1) < d["open"].shift(1)) & (d["close"] < d["low"].shift(1))
        clean_range = d["range_bps"] < d[f"atr{bars['b24h']}_bps"] * 1.65
        long_mask = compression.shift(2).fillna(False).astype(bool) & two_up & clean_range & d["trend_up_4h_24h"] & d["tradable_session"]
        short_mask = compression.shift(2).fillna(False).astype(bool) & two_down & clean_range & d["trend_down_4h_24h"] & d["tradable_session"]
        for h in horizons:
            add(f"sig_42d_intraday_comp_expand_long_c{comp_hours}_h{h}", "42D_INTRADAY_COMPRESSION_EXPANSION_CONFIRM", f"INTRADAY_COMP_EXPAND_LONG_C{comp_hours}H", "LONG", h, h, long_mask, "Intraday compression followed by two-bar expansion confirmation with trend gate.")
            add(f"sig_42d_intraday_comp_expand_short_c{comp_hours}_h{h}", "42D_INTRADAY_COMPRESSION_EXPANSION_CONFIRM", f"INTRADAY_COMP_EXPAND_SHORT_C{comp_hours}H", "SHORT", h, h, short_mask, "Intraday compression followed by two-bar expansion confirmation with trend gate.")

    # 42E: London morning range acceptance/rejection in NY overlap.
    for tol in [10, 20, 35]:
        lm_ready = d["london_morning_high"].notna() & d["london_morning_low"].notna() & d["london_morning_range_bps"].between(35, 220)
        ny_overlap = d["hour_utc"].between(12, 16)
        accept_long = (
            lm_ready & ny_overlap
            & (d["low"] <= d["london_morning_high"] * (1.0 + tol / 10000.0))
            & (d["close"] > d["london_morning_high"])
            & (d["close"] > d["london_morning_mid"])
            & (d["signed_body_bps"] > 0)
        )
        reject_short = (
            lm_ready & ny_overlap
            & (d["high"] >= d["london_morning_low"] * (1.0 - tol / 10000.0))
            & (d["close"] < d["london_morning_low"])
            & (d["close"] < d["london_morning_mid"])
            & (d["signed_body_bps"] < 0)
        )
        for h in horizons:
            add(f"sig_42e_london_range_accept_long_tol{tol}_h{h}", "42E_LONDON_RANGE_ACCEPTANCE_REJECTION", f"LONDON_RANGE_ACCEPT_LONG_TOL{tol}", "LONG", h, h, accept_long, "NY-overlap acceptance above London morning range high.")
            add(f"sig_42e_london_range_reject_short_tol{tol}_h{h}", "42E_LONDON_RANGE_ACCEPTANCE_REJECTION", f"LONDON_RANGE_REJECT_SHORT_TOL{tol}", "SHORT", h, h, reject_short, "NY-overlap rejection below London morning range low.")

    # 42F: Micro trend pullback hold with path-risk feasibility emphasis.
    for pull_bps in [8, 15, 25, 40]:
        active = d["hour_utc"].between(7, 16)
        long_mask = (
            active & d["trend_up_4h_24h"]
            & (d["low"] <= d[f"sma{bars['b2h']}"] * (1.0 + pull_bps / 10000.0))
            & (d["close"] > d[f"sma{bars['b2h']}"])
            & (d["signed_body_bps"] > 0)
            & (d["range_bps"] < d[f"atr{bars['b8h']}_bps"] * 1.35)
        )
        short_mask = (
            active & d["trend_down_4h_24h"]
            & (d["high"] >= d[f"sma{bars['b2h']}"] * (1.0 - pull_bps / 10000.0))
            & (d["close"] < d[f"sma{bars['b2h']}"])
            & (d["signed_body_bps"] < 0)
            & (d["range_bps"] < d[f"atr{bars['b8h']}_bps"] * 1.35)
        )
        for h in horizons:
            add(f"sig_42f_microtrend_pullback_long_p{pull_bps}_h{h}", "42F_MICROTREND_PULLBACK_HOLD", f"MICROTREND_PULLBACK_LONG_P{pull_bps}", "LONG", h, h, long_mask, "Micro trend pullback to two-hour mean with hold confirmation.")
            add(f"sig_42f_microtrend_pullback_short_p{pull_bps}_h{h}", "42F_MICROTREND_PULLBACK_HOLD", f"MICROTREND_PULLBACK_SHORT_P{pull_bps}", "SHORT", h, h, short_mask, "Micro trend pullback to two-hour mean with hold confirmation.")

    return d, specs


def _event_clock_indices(mask: pd.Series, min_gap: int) -> np.ndarray:
    idx = np.flatnonzero(mask.to_numpy(dtype=bool))
    if len(idx) == 0:
        return idx
    kept: List[int] = []
    last = -10**12
    for i in idx:
        if i >= last + min_gap:
            kept.append(int(i))
            last = int(i)
    return np.asarray(kept, dtype=int)


def _future_path_stats(d: pd.DataFrame, event_idx: np.ndarray, horizon: int, side: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    lows = d["low"].to_numpy(dtype=float)
    highs = d["high"].to_numpy(dtype=float)
    closes = d["close"].to_numpy(dtype=float)
    mae: List[float] = []
    mfe: List[float] = []
    touch35: List[bool] = []
    touch50: List[bool] = []
    n = len(d)
    for i in event_idx:
        if i + horizon >= n:
            mae.append(np.nan)
            mfe.append(np.nan)
            touch35.append(False)
            touch50.append(False)
            continue
        entry = closes[i]
        lo = np.nanmin(lows[i + 1 : i + horizon + 1])
        hi = np.nanmax(highs[i + 1 : i + horizon + 1])
        if not np.isfinite(entry) or entry <= 0:
            mae.append(np.nan)
            mfe.append(np.nan)
            touch35.append(False)
            touch50.append(False)
            continue
        if side == "LONG":
            ev_mae = (lo / entry - 1.0) * 10000.0
            ev_mfe = (hi / entry - 1.0) * 10000.0
        else:
            ev_mae = (entry / hi - 1.0) * 10000.0
            ev_mfe = (entry / lo - 1.0) * 10000.0
        mae.append(float(ev_mae))
        mfe.append(float(ev_mfe))
        touch35.append(bool(ev_mae <= -35.0))
        touch50.append(bool(ev_mae <= -50.0))
    return np.asarray(mae), np.asarray(mfe), np.asarray(touch35, dtype=bool), np.asarray(touch50, dtype=bool)


def _bootstrap_mean_stats(values: np.ndarray, seed: int = 42, rounds: int = 1000) -> Dict[str, float]:
    x = values[np.isfinite(values)]
    if len(x) < 20:
        return {"boot_p10_bps": float("nan"), "boot_p50_bps": float("nan"), "boot_prob_mean_gt_0_pct": float("nan")}
    rng = np.random.default_rng(seed)
    means = rng.choice(x, size=(rounds, len(x)), replace=True).mean(axis=1)
    return {
        "boot_p10_bps": float(np.percentile(means, 10)),
        "boot_p50_bps": float(np.percentile(means, 50)),
        "boot_prob_mean_gt_0_pct": float((means > 0).mean() * 100.0),
    }


def _split_train_oos(events: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
    if events.empty:
        return pd.Series(dtype=bool), pd.Series(dtype=bool)
    ordered = events.sort_values("ts_utc").reset_index(drop=False)
    split_pos = max(1, int(math.floor(len(ordered) * 0.70)))
    train_orig = set(ordered.loc[: split_pos - 1, "index"].tolist())
    train_mask = events.index.to_series().isin(train_orig)
    return train_mask, ~train_mask


def _classify(metrics: Dict[str, object], min_events: int) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    n = int(metrics.get("event_clock_n", 0) or 0)
    train_n = int(metrics.get("train_n", 0) or 0)
    oos_n = int(metrics.get("oos_n", 0) or 0)
    quarters_n = int(metrics.get("quarters_n", 0) or 0)
    years_n = int(metrics.get("years_n", 0) or 0)

    def val(name: str, default: float = float("nan")) -> float:
        x = metrics.get(name, default)
        try:
            return float(x)
        except (TypeError, ValueError):
            return default

    if n < min_events or train_n < max(50, min_events // 3) or oos_n < max(35, min_events // 4):
        if n < min_events:
            reasons.append("event_clock_n_below_min")
        if train_n < max(50, min_events // 3):
            reasons.append("train_n_too_small")
        if oos_n < max(35, min_events // 4):
            reasons.append("oos_n_too_small")
        return CLASS_INSUFFICIENT, reasons

    strict_checks = {
        "cost_mean_gt_4": val("cost_stressed_mean_bps") > 4.0,
        "residual_gt_2": val("intraday_benchmark_cost_adjusted_residual_bps") > 2.0,
        "train_gt_2": val("train_cost_mean_bps") > 2.0,
        "oos_gt_2": val("oos_cost_mean_bps") > 2.0,
        "worst_quarter_slip16_gt_minus8": val("worst_quarter_slip16_mean_bps") > -8.0,
        "boot_p10_gt_minus1": val("boot_p10_bps") > -1.0,
        "boot_prob_gt_85": val("boot_prob_mean_gt_0_pct") >= 85.0,
        "oos_touch50_le_70": val("oos_touch_stop_50bps_pct") <= 70.0,
        "top_year_share_le_45": val("top_year_event_share_pct") <= 45.0,
        "top_quarter_share_le_28": val("top_quarter_event_share_pct") <= 28.0,
        "positive_quarter_pct_ge_55": val("positive_quarter_pct") >= 55.0,
        "years_n_ge_3": years_n >= 3,
        "quarters_n_ge_8": quarters_n >= 8,
        "ex2025_gt_0": (np.isnan(val("ex2025_cost_mean_bps")) or val("ex2025_cost_mean_bps") > 0.0),
    }
    if all(strict_checks.values()):
        return CLASS_STRICT, []

    soft_checks = {
        "cost_mean_gt_15": val("cost_stressed_mean_bps") > 1.5,
        "residual_gt_0": val("intraday_benchmark_cost_adjusted_residual_bps") > 0.0,
        "train_gt_0": val("train_cost_mean_bps") > 0.0,
        "oos_gt_0": val("oos_cost_mean_bps") > 0.0,
        "worst_quarter_slip16_gt_minus20": val("worst_quarter_slip16_mean_bps") > -20.0,
        "boot_p10_gt_minus5": val("boot_p10_bps") > -5.0,
        "boot_prob_gt_65": val("boot_prob_mean_gt_0_pct") >= 65.0,
        "oos_touch50_le_80": val("oos_touch_stop_50bps_pct") <= 80.0,
        "top_year_share_le_60": val("top_year_event_share_pct") <= 60.0,
        "positive_quarter_pct_ge_45": val("positive_quarter_pct") >= 45.0,
    }
    if all(soft_checks.values()):
        failed_strict = [name for name, ok in strict_checks.items() if not ok]
        return CLASS_SOFT, failed_strict

    failed_soft = [name for name, ok in soft_checks.items() if not ok]
    return CLASS_FAIL, failed_soft


def _evaluate_spec(
    d: pd.DataFrame,
    spec: ThesisSpec,
    cost_bps: float,
    slip_bps: float,
    min_events: int,
    tf_minutes: int,
) -> Tuple[Dict[str, object], pd.DataFrame]:
    idx = _event_clock_indices(d[spec.mask_col], spec.min_gap_bars)
    max_valid = len(d) - spec.horizon_bars - 1
    idx = idx[idx <= max_valid]

    fwd_col = f"fwd{spec.horizon_bars}_ret_bps"
    if fwd_col not in d.columns:
        raise ValueError(f"Missing forward column: {fwd_col}")
    fwd = d[fwd_col].to_numpy(dtype=float)
    side_sign = 1.0 if spec.side == "LONG" else -1.0
    raw_ret = fwd[idx] * side_sign if len(idx) else np.asarray([], dtype=float)
    cost_ret = raw_ret - cost_bps
    slip16_ret = cost_ret - slip_bps
    horizon_minutes = int(spec.horizon_bars * tf_minutes)

    events = pd.DataFrame({
        "ts_utc": d.loc[idx, "ts_utc"].astype(str).to_numpy() if len(idx) else [],
        "family": spec.family,
        "candidate": spec.candidate,
        "side": spec.side,
        "horizon_bars": spec.horizon_bars,
        "horizon_minutes": horizon_minutes,
        "entry_close": d.loc[idx, "close"].to_numpy(dtype=float) if len(idx) else [],
        "raw_return_bps": raw_ret,
        "cost_return_bps": cost_ret,
        "slip16_return_bps": slip16_ret,
        "hour_utc": d.loc[idx, "hour_utc"].to_numpy(dtype=int) if len(idx) else [],
        "minute_of_day": d.loc[idx, "minute_of_day"].to_numpy(dtype=int) if len(idx) else [],
        "weekday": d.loc[idx, "weekday"].to_numpy() if len(idx) else [],
        "session_utc": d.loc[idx, "session_utc"].to_numpy() if len(idx) else [],
        "year": d.loc[idx, "year"].to_numpy(dtype=int) if len(idx) else [],
        "quarter": d.loc[idx, "quarter"].to_numpy() if len(idx) else [],
    })

    if events.empty:
        metrics: Dict[str, object] = {
            "stage": STAGE_NAME,
            "family": spec.family,
            "candidate": spec.candidate,
            "side": spec.side,
            "horizon_bars": spec.horizon_bars,
            "horizon_minutes": horizon_minutes,
            "description": spec.description,
            "event_clock_n": 0,
            "classification": CLASS_INSUFFICIENT,
            "failed_reasons": "no_events",
            **NO_PROMOTION_STATE,
        }
        return metrics, events

    mae, mfe, touch35, touch50 = _future_path_stats(d, idx, spec.horizon_bars, spec.side)
    events["mae_bps"] = mae
    events["mfe_bps"] = mfe
    events["touch_stop_35bps"] = touch35
    events["touch_stop_50bps"] = touch50

    all_fwd = d[fwd_col].iloc[:max_valid].to_numpy(dtype=float) * side_sign
    benchmark_cost = np.nanmean(all_fwd - cost_bps)

    train_mask, oos_mask = _split_train_oos(events)

    quarter_means = events.groupby("quarter")["cost_return_bps"].mean().sort_index()
    quarter_slip_means = events.groupby("quarter")["slip16_return_bps"].mean().sort_index()
    year_means = events.groupby("year")["cost_return_bps"].mean().sort_index()
    q_counts = events.groupby("quarter").size()
    y_counts = events.groupby("year").size()

    ex2025 = events[events["year"] != 2025]
    oos_events = events[oos_mask]

    metrics = {
        "stage": STAGE_NAME,
        "family": spec.family,
        "candidate": spec.candidate,
        "side": spec.side,
        "horizon_bars": spec.horizon_bars,
        "horizon_minutes": horizon_minutes,
        "description": spec.description,
        "event_clock_n": int(len(events)),
        "raw_mean_bps": float(np.nanmean(events["raw_return_bps"])),
        "cost_stressed_mean_bps": float(np.nanmean(events["cost_return_bps"])),
        "slip16_mean_bps": float(np.nanmean(events["slip16_return_bps"])),
        "median_cost_bps": float(np.nanmedian(events["cost_return_bps"])),
        "win_rate_cost_pct": float((events["cost_return_bps"] > 0).mean() * 100.0),
        "intraday_benchmark_cost_mean_bps": float(benchmark_cost),
        "intraday_benchmark_cost_adjusted_residual_bps": float(np.nanmean(events["cost_return_bps"]) - benchmark_cost),
        "train_n": int(train_mask.sum()),
        "oos_n": int(oos_mask.sum()),
        "train_cost_mean_bps": float(np.nanmean(events.loc[train_mask, "cost_return_bps"])),
        "oos_cost_mean_bps": float(np.nanmean(events.loc[oos_mask, "cost_return_bps"])),
        "train_win_rate_cost_pct": float((events.loc[train_mask, "cost_return_bps"] > 0).mean() * 100.0) if train_mask.any() else float("nan"),
        "oos_win_rate_cost_pct": float((events.loc[oos_mask, "cost_return_bps"] > 0).mean() * 100.0) if oos_mask.any() else float("nan"),
        "worst_quarter_cost_mean_bps": float(quarter_means.min()) if not quarter_means.empty else float("nan"),
        "worst_quarter_slip16_mean_bps": float(quarter_slip_means.min()) if not quarter_slip_means.empty else float("nan"),
        "positive_quarter_pct": float((quarter_means > 0).mean() * 100.0) if not quarter_means.empty else float("nan"),
        "quarters_n": int(len(quarter_means)),
        "worst_year_cost_mean_bps": float(year_means.min()) if not year_means.empty else float("nan"),
        "positive_year_pct": float((year_means > 0).mean() * 100.0) if not year_means.empty else float("nan"),
        "years_n": int(len(year_means)),
        "top_quarter_event_share_pct": float(q_counts.max() / len(events) * 100.0) if not q_counts.empty else float("nan"),
        "top_year_event_share_pct": float(y_counts.max() / len(events) * 100.0) if not y_counts.empty else float("nan"),
        "ex2025_n": int(len(ex2025)),
        "ex2025_cost_mean_bps": float(np.nanmean(ex2025["cost_return_bps"])) if not ex2025.empty else float("nan"),
        "median_mae_bps": float(np.nanmedian(events["mae_bps"])),
        "median_mfe_bps": float(np.nanmedian(events["mfe_bps"])),
        "touch_stop_35bps_pct": float(events["touch_stop_35bps"].mean() * 100.0),
        "touch_stop_50bps_pct": float(events["touch_stop_50bps"].mean() * 100.0),
        "oos_median_mae_bps": float(np.nanmedian(oos_events["mae_bps"])) if not oos_events.empty else float("nan"),
        "oos_touch_stop_35bps_pct": float(oos_events["touch_stop_35bps"].mean() * 100.0) if not oos_events.empty else float("nan"),
        "oos_touch_stop_50bps_pct": float(oos_events["touch_stop_50bps"].mean() * 100.0) if not oos_events.empty else float("nan"),
        **_bootstrap_mean_stats(events["cost_return_bps"].to_numpy(dtype=float)),
        **NO_PROMOTION_STATE,
    }
    classification, reasons = _classify(metrics, min_events=min_events)
    metrics["classification"] = classification
    metrics["failed_reasons"] = ";".join(reasons)
    return metrics, events


def _json_default(obj: object) -> object:
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        x = float(obj)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    return obj


def _markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "No rows."
    try:
        return df.to_markdown(index=False)
    except Exception:
        return df.to_csv(index=False)


def _write_markdown_report(out_path: Path, summary: Dict[str, object], candidates: pd.DataFrame) -> None:
    lines: List[str] = []
    lines.append(f"# {STAGE_NAME}")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    lines.append("promotion = NO_GO")
    lines.append("EA = NO_GO")
    lines.append("paper_live = NO_GO")
    lines.append("live = NO_GO")
    lines.append("```")
    lines.append("")
    lines.append("Stage42 is an intraday execution-feasibility research scan only. Strict/soft rows are watch-only and require a separate Stage42B path-stability/promotion audit before any operational layer is considered.")
    lines.append("")
    lines.append("## Input data")
    lines.append("")
    meta = summary.get("data", {}) if isinstance(summary.get("data"), dict) else {}
    lines.append("```text")
    for k in ["db_path", "table", "source", "symbol", "timeframe", "timeframe_normalized", "timeframe_minutes", "loaded_rows", "loaded_start", "loaded_end"]:
        lines.append(f"{k}: {meta.get(k)}")
    lines.append("```")
    lines.append("")
    lines.append("## Thesis families scanned")
    lines.append("")
    for fam in summary.get("families_scanned", []):
        lines.append(f"- `{fam}`")
    lines.append("")
    lines.append("## Classification counts")
    lines.append("")
    lines.append("```text")
    for k, v in summary.get("classification_counts", {}).items():
        lines.append(f"{k}: {v}")
    lines.append("```")
    lines.append("")
    lines.append("## Top rows by classification then cost mean")
    lines.append("")
    if candidates.empty:
        lines.append("No candidates were produced.")
    else:
        display_cols = [
            "classification", "family", "candidate", "side", "horizon_minutes", "event_clock_n",
            "cost_stressed_mean_bps", "intraday_benchmark_cost_adjusted_residual_bps",
            "train_cost_mean_bps", "oos_cost_mean_bps", "worst_quarter_slip16_mean_bps",
            "boot_p10_bps", "oos_touch_stop_50bps_pct", "top_year_event_share_pct", "failed_reasons",
        ]
        existing_cols = [c for c in display_cols if c in candidates.columns]
        lines.append(_markdown_table(candidates[existing_cols].head(50)))
    lines.append("")
    lines.append("## Anti-overfit note")
    lines.append("")
    lines.append("Do not rescue failed Stage42 rows by removing weak hours, months, years, or stop-touch buckets after seeing this output. A later Stage42B may audit only pre-existing strict/soft shortlist rows with predefined path-stability, slip, LOYO, concentration, and OOS gates.")
    lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    tf_minutes = _timeframe_minutes(args.timeframe)
    df, meta = _read_sqlite_bars(
        db_path=Path(args.db),
        table=args.table,
        source=args.source,
        symbol=args.symbol,
        timeframe=args.timeframe,
    )
    # Use actual normalized minutes from metadata to keep alias handling consistent.
    tf_minutes = int(meta["timeframe_minutes"])
    featured, bars = _add_features(df, tf_minutes=tf_minutes)
    featured, specs = _build_signal_masks(featured, bars)

    candidate_rows: List[Dict[str, object]] = []
    event_frames: List[pd.DataFrame] = []
    errors: List[Dict[str, object]] = []

    for spec in specs:
        try:
            metrics, events = _evaluate_spec(
                featured,
                spec,
                cost_bps=float(args.cost_bps),
                slip_bps=float(args.slip_bps),
                min_events=int(args.min_events),
                tf_minutes=tf_minutes,
            )
            candidate_rows.append(metrics)
            if not events.empty:
                event_frames.append(events)
        except Exception as exc:
            row = {
                "stage": STAGE_NAME,
                "family": spec.family,
                "candidate": spec.candidate,
                "side": spec.side,
                "horizon_bars": spec.horizon_bars,
                "horizon_minutes": int(spec.horizon_bars * tf_minutes),
                "description": spec.description,
                "event_clock_n": 0,
                "classification": CLASS_ERROR,
                "failed_reasons": f"{type(exc).__name__}: {exc}",
                **NO_PROMOTION_STATE,
            }
            candidate_rows.append(row)
            errors.append(row)

    candidates = pd.DataFrame(candidate_rows)
    if not candidates.empty:
        class_rank = {CLASS_STRICT: 0, CLASS_SOFT: 1, CLASS_FAIL: 2, CLASS_INSUFFICIENT: 3, CLASS_ERROR: 4}
        candidates["_class_rank"] = candidates["classification"].map(class_rank).fillna(9)
        sort_cols = ["_class_rank", "cost_stressed_mean_bps", "intraday_benchmark_cost_adjusted_residual_bps", "event_clock_n"]
        existing = [c for c in sort_cols if c in candidates.columns]
        candidates = candidates.sort_values(existing, ascending=[True, False, False, False][: len(existing)]).drop(columns=["_class_rank"])

    events_all = pd.concat(event_frames, ignore_index=True) if event_frames else pd.DataFrame()

    candidates_path = outdir / "stage42_parallel_intraday_execution_megascan_v3_candidates.csv"
    events_path = outdir / "stage42_parallel_intraday_execution_megascan_v3_events.csv"
    summary_path = outdir / "stage42_parallel_intraday_execution_megascan_v3_summary.json"
    md_path = outdir / "stage42_parallel_intraday_execution_megascan_v3.md"

    candidates.to_csv(candidates_path, index=False)
    events_all.to_csv(events_path, index=False)

    classification_counts = candidates["classification"].value_counts(dropna=False).to_dict() if not candidates.empty else {}
    strict_count = int(classification_counts.get(CLASS_STRICT, 0))
    soft_count = int(classification_counts.get(CLASS_SOFT, 0))
    summary = {
        "stage": STAGE_NAME,
        "data": meta,
        "settings": {
            "cost_bps": float(args.cost_bps),
            "slip_bps": float(args.slip_bps),
            "min_events": int(args.min_events),
            "event_clock": "candidate-specific min_gap equals horizon_bars",
            "train_oos_split": "chronological 70/30 event-clock split",
            "intraday_path_risk": "MAE/MFE plus touch_stop_35bps and touch_stop_50bps",
            "derived_bars": bars,
        },
        "families_scanned": sorted(candidates["family"].dropna().unique().tolist()) if not candidates.empty else [],
        "candidate_rows": int(len(candidates)),
        "events_rows_written": int(len(events_all)),
        "strict_stage42_intraday_scan_watch_count": strict_count,
        "soft_stage42_intraday_scan_watch_count": soft_count,
        "classification_counts": {str(k): int(v) for k, v in classification_counts.items()},
        "errors": errors,
        **NO_PROMOTION_STATE,
        "next_allowed_step": "Stage42B_STRICT_SHORTLIST_PATH_STABILITY_AUDIT only if strict_stage42_intraday_scan_watch_count > 0; otherwise archive Stage42 or start new thesis families.",
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    _write_markdown_report(md_path, summary, candidates)

    print(json.dumps({
        "stage": STAGE_NAME,
        "timeframe": meta.get("timeframe"),
        "timeframe_normalized": meta.get("timeframe_normalized"),
        "loaded_rows": meta.get("loaded_rows"),
        "candidate_rows": int(len(candidates)),
        "events_rows_written": int(len(events_all)),
        "strict_stage42_intraday_scan_watch_count": strict_count,
        "soft_stage42_intraday_scan_watch_count": soft_count,
        "summary_path": str(summary_path),
        "candidates_path": str(candidates_path),
        "events_path": str(events_path),
        "markdown_path": str(md_path),
        **NO_PROMOTION_STATE,
    }, ensure_ascii=False, indent=2))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Stage42 parallel intraday execution-feasibility megascan v3 for XAUUSD.")
    p.add_argument("--db", default=str(DEFAULT_DB), help="SQLite DB path. Default: data/local/xauusd_local_store.sqlite")
    p.add_argument("--table", default=DEFAULT_TABLE, help="Bars table name. Default: bars")
    p.add_argument("--source", default=DEFAULT_SOURCE, help="Source filter if source column exists. Default: amarkets_mt5")
    p.add_argument("--symbol", default=DEFAULT_SYMBOL, help="Symbol filter if symbol column exists. Default: XAUUSD")
    p.add_argument("--timeframe", default=DEFAULT_TIMEFRAME, help="Intraday timeframe filter. Default: M15; aliases such as 15m are accepted")
    p.add_argument("--outdir", default=str(DEFAULT_OUTDIR), help="Output directory. Default: reports/stage42")
    p.add_argument("--cost-bps", type=float, default=8.0, help="Round-trip cost assumption in bps subtracted from every event. Default: 8")
    p.add_argument("--slip-bps", type=float, default=16.0, help="Additional slippage stress used for slip16 stability. Default: 16")
    p.add_argument("--min-events", type=int, default=120, help="Minimum event-clock count for non-insufficient classification. Default: 120")
    return p


if __name__ == "__main__":
    raise SystemExit(run(build_arg_parser().parse_args()))
