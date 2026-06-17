#!/usr/bin/env python3
"""
Stage41_PARALLEL_THESIS_MEGASCAN_V2

Independent XAUUSD H1 thesis megascan after Stage38/39/40 archive.
This script is intentionally research-only: it cannot promote candidates and it
never writes EA/paper-live/live execution artifacts.

Outputs:
  reports/stage41/stage41_parallel_thesis_megascan_v2_candidates.csv
  reports/stage41/stage41_parallel_thesis_megascan_v2_events.csv
  reports/stage41/stage41_parallel_thesis_megascan_v2_summary.json
  reports/stage41/stage41_parallel_thesis_megascan_v2.md
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning, message="Mean of empty slice")
warnings.filterwarnings("ignore", message="Converting to PeriodArray/Index representation will drop timezone information.", category=UserWarning)

STAGE_NAME = "Stage41_PARALLEL_THESIS_MEGASCAN_V2"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_TABLE = "bars"
DEFAULT_OUTDIR = Path("reports/stage41")
DEFAULT_SOURCE = "amarkets_mt5"
DEFAULT_SYMBOL = "XAUUSD"
DEFAULT_TIMEFRAME = "H1"

NO_PROMOTION_STATE = {
    "promotion": "NO_GO",
    "EA": "NO_GO",
    "paper_live": "NO_GO",
    "live": "NO_GO",
}

CLASS_STRICT = "STRICT_STAGE41_SCAN_WATCH_ONLY_NO_PROMOTION"
CLASS_SOFT = "SOFT_STAGE41_SCAN_WATCH_ONLY_NO_PROMOTION"
CLASS_FAIL = "FAIL_BENCHMARK_OR_STABILITY_RESEARCH_ONLY"
CLASS_INSUFFICIENT = "INSUFFICIENT_EVENTS_RESEARCH_ONLY"
CLASS_ERROR = "ERROR_RESEARCH_ONLY"


@dataclass(frozen=True)
class ThesisSpec:
    family: str
    candidate: str
    side: str
    horizon: int
    min_gap: int
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
        "1H": "H1",
        "H1": "H1",
        "60": "H1",
        "60M": "H1",
        "M60": "H1",
        "60MIN": "H1",
        "60MINS": "H1",
        "60MINUTE": "H1",
        "60MINUTES": "H1",
        "5M": "M5",
        "M5": "M5",
        "5MIN": "M5",
        "5MINS": "M5",
        "5MINUTE": "M5",
        "5MINUTES": "M5",
        "15M": "M15",
        "M15": "M15",
        "15MIN": "M15",
        "15MINS": "M15",
        "15MINUTE": "M15",
        "15MINUTES": "M15",
        "30M": "M30",
        "M30": "M30",
        "30MIN": "M30",
        "4H": "H4",
        "H4": "H4",
        "240": "H4",
        "240M": "H4",
        "M240": "H4",
        "1D": "D1",
        "D1": "D1",
        "DAILY": "D1",
    }
    return aliases.get(raw, raw)


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
        if volume_col:
            selected.append(volume_col)
        if source_col and source_col not in selected:
            selected.append(source_col)
        if symbol_col and symbol_col not in selected:
            selected.append(symbol_col)
        if timeframe_col and timeframe_col not in selected:
            selected.append(timeframe_col)

        # DB-first, schema-tolerant loader:
        # Load the detected bars columns first, then apply normalized filters in pandas.
        # This avoids false zero-row failures from common DB spelling/casing variants,
        # e.g. utc_time + AMarkets MT5 + 1h versus timestamp + amarkets_mt5 + H1.
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
        "normalization": "source/symbol use strip+casefold+compact; timeframe uses aliases such as 1h/60/M60 -> H1",
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
    for c in ["open", "high", "low", "close", "volume"]:
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
                "source": source_col,
                "symbol": symbol_col,
                "timeframe": timeframe_col,
            },
            "available_dimensions_top20": dimension_preview,
            "filter_debug": filter_debug,
            "suggestion": "Run again with --source/--symbol/--timeframe matching one of available_dimensions_top20, or inspect the DB if these dimensions look wrong.",
        }
        raise RuntimeError(json.dumps(diagnostic, ensure_ascii=False, indent=2))

    # Drop raw dimension helper columns before feature engineering, but keep their detected values in metadata.
    loaded_dimension_values: Dict[str, List[str]] = {}
    for raw_col, key in [("__source_raw", "source"), ("__symbol_raw", "symbol"), ("__timeframe_raw", "timeframe")]:
        if raw_col in df.columns:
            vals = sorted({str(x) for x in df[raw_col].dropna().unique().tolist()})
            loaded_dimension_values[key] = vals[:20]
    df = df.drop(columns=[c for c in ["__source_raw", "__symbol_raw", "__timeframe_raw"] if c in df.columns])

    meta = {
        "db_path": str(db_path),
        "table": table,
        "source_filter_used": bool(source_col),
        "symbol_filter_used": bool(symbol_col),
        "timeframe_filter_used": bool(timeframe_col),
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "loaded_rows": int(len(df)),
        "loaded_start": df["ts_utc"].iloc[0].isoformat(),
        "loaded_end": df["ts_utc"].iloc[-1].isoformat(),
        "columns_detected": {
            "timestamp": ts_col,
            "open": open_col,
            "high": high_col,
            "low": low_col,
            "close": close_col,
            "volume": volume_col,
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


def _add_features(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["hour_utc"] = d["ts_utc"].dt.hour
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

    for w in [6, 12, 24, 48, 72, 96, 120, 168, 240]:
        d[f"ret{w}_bps"] = (d["close"] / d["close"].shift(w) - 1.0) * 10000.0
        d[f"fwd{w}_ret_bps"] = (d["close"].shift(-w) / d["close"] - 1.0) * 10000.0
        d[f"atr{w}_bps"] = d["tr_bps"].rolling(w, min_periods=max(6, w // 4)).mean()
        d[f"roll_high{w}"] = d["high"].shift(1).rolling(w, min_periods=max(6, w // 4)).max()
        d[f"roll_low{w}"] = d["low"].shift(1).rolling(w, min_periods=max(6, w // 4)).min()
        d[f"sma{w}"] = d["close"].rolling(w, min_periods=max(6, w // 4)).mean()

    d["sma_slope_24_72_bps"] = (d["sma24"] / d["sma72"] - 1.0) * 10000.0
    d["sma_slope_72_168_bps"] = (d["sma72"] / d["sma168"] - 1.0) * 10000.0
    d["htf_up"] = (d["close"] > d["sma168"]) & (d["sma24"] > d["sma72"]) & (d["ret96_bps"] > 0)
    d["htf_down"] = (d["close"] < d["sma168"]) & (d["sma24"] < d["sma72"]) & (d["ret96_bps"] < 0)

    # Daily and Asia range features. The Asia range is finalized only after 05:00 UTC.
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

    d = d.merge(daily[["prev_day_high", "prev_day_low", "prev_day_close", "prev_day_range_bps"]], left_on="date", right_index=True, how="left")
    d = d.merge(asia[["asia_high", "asia_low", "asia_range_bps"]], left_on="date", right_index=True, how="left")
    d.loc[d["hour_utc"] <= 5, ["asia_high", "asia_low", "asia_range_bps"]] = np.nan

    d["dist_prev_high_bps"] = (d["close"] / d["prev_day_high"] - 1.0) * 10000.0
    d["dist_prev_low_bps"] = (d["close"] / d["prev_day_low"] - 1.0) * 10000.0
    d["dist_asia_high_bps"] = (d["close"] / d["asia_high"] - 1.0) * 10000.0
    d["dist_asia_low_bps"] = (d["close"] / d["asia_low"] - 1.0) * 10000.0

    return d


def _build_signal_masks(d: pd.DataFrame) -> Tuple[pd.DataFrame, List[ThesisSpec]]:
    specs: List[ThesisSpec] = []

    def add(mask_name: str, family: str, candidate: str, side: str, horizon: int, min_gap: int, mask: pd.Series, description: str) -> None:
        d[mask_name] = mask.fillna(False).astype(bool)
        specs.append(ThesisSpec(family=family, candidate=candidate, side=side, horizon=horizon, min_gap=min_gap, mask_col=mask_name, description=description))

    # 41A: Multi-timeframe structure break + retest/hold.
    for w in [96, 168, 240]:
        for tol in [20, 35, 50]:
            base_high = d[f"roll_high{w}"]
            base_low = d[f"roll_low{w}"]
            long_mask = (
                d["htf_up"]
                & d["hour_utc"].between(7, 16)
                & (d["high"] > base_high * 1.0005)
                & (d["low"] <= base_high * (1.0 + tol / 10000.0))
                & (d["close"] > base_high)
                & (d["range_bps"] <= d["atr72_bps"] * 1.80)
            )
            short_mask = (
                d["htf_down"]
                & d["hour_utc"].between(7, 16)
                & (d["low"] < base_low * 0.9995)
                & (d["high"] >= base_low * (1.0 - tol / 10000.0))
                & (d["close"] < base_low)
                & (d["range_bps"] <= d["atr72_bps"] * 1.80)
            )
            for h in [24, 48, 72]:
                add(f"sig_41a_mtf_break_retest_long_w{w}_tol{tol}_h{h}", "41A_MTF_STRUCTURE_BREAK_RETEST", f"MTF_BREAK_RETEST_LONG_W{w}_TOL{tol}", "LONG", h, h, long_mask, "H1 retest/hold of prior multi-day structure high with H4/D1 proxy trend agreement.")
                add(f"sig_41a_mtf_break_retest_short_w{w}_tol{tol}_h{h}", "41A_MTF_STRUCTURE_BREAK_RETEST", f"MTF_BREAK_RETEST_SHORT_W{w}_TOL{tol}", "SHORT", h, h, short_mask, "H1 retest/hold of prior multi-day structure low with H4/D1 proxy trend agreement.")

    # 41B: NY impulse exhaustion reversal. Pre-defined NY late window; no post-hoc weak hour removal.
    for lookback in [6, 12]:
        for mult in [1.00, 1.25, 1.50]:
            impulse_down = d[f"ret{lookback}_bps"] < -(d["atr72_bps"] * mult)
            impulse_up = d[f"ret{lookback}_bps"] > (d["atr72_bps"] * mult)
            reversal_long = (
                d["hour_utc"].between(17, 21)
                & impulse_down
                & (d["signed_body_bps"] > 0)
                & (d["lower_wick_bps"] >= d["body_bps"] * 0.55)
                & (d["range_bps"] >= d["atr24_bps"] * 0.70)
            )
            reversal_short = (
                d["hour_utc"].between(17, 21)
                & impulse_up
                & (d["signed_body_bps"] < 0)
                & (d["upper_wick_bps"] >= d["body_bps"] * 0.55)
                & (d["range_bps"] >= d["atr24_bps"] * 0.70)
            )
            for h in [12, 24, 48]:
                add(f"sig_41b_ny_exhaust_long_l{lookback}_m{str(mult).replace('.', '')}_h{h}", "41B_NY_IMPULSE_EXHAUSTION_REVERSAL", f"NY_EXHAUST_REV_LONG_L{lookback}_M{mult}", "LONG", h, h, reversal_long, "Late-NY reversal after a volatility-normalized downside impulse and rejection wick.")
                add(f"sig_41b_ny_exhaust_short_l{lookback}_m{str(mult).replace('.', '')}_h{h}", "41B_NY_IMPULSE_EXHAUSTION_REVERSAL", f"NY_EXHAUST_REV_SHORT_L{lookback}_M{mult}", "SHORT", h, h, reversal_short, "Late-NY reversal after a volatility-normalized upside impulse and rejection wick.")

    # 41C: Shock cool-down continuation, not immediate shock reversal.
    for mult in [1.60, 2.00, 2.40]:
        prior_shock = d["tr_bps"].shift(1) > (d["atr120_bps"].shift(1) * mult)
        prior_up = d["signed_body_bps"].shift(1) > 0
        prior_down = d["signed_body_bps"].shift(1) < 0
        cooldown = d["range_bps"] < d["atr24_bps"] * 0.85
        prior_mid = (d["high"].shift(1) + d["low"].shift(1)) / 2.0
        long_mask = prior_shock & prior_up & cooldown & (d["close"] > prior_mid) & (d["close"] > d["open"]) & d["hour_utc"].between(6, 16)
        short_mask = prior_shock & prior_down & cooldown & (d["close"] < prior_mid) & (d["close"] < d["open"]) & d["hour_utc"].between(6, 16)
        for h in [12, 24, 48]:
            add(f"sig_41c_shock_cool_cont_long_m{str(mult).replace('.', '')}_h{h}", "41C_SHOCK_COOLDOWN_CONTINUATION", f"SHOCK_COOLDOWN_CONT_LONG_M{mult}", "LONG", h, h, long_mask, "Continuation only after a shock bar cools down and holds above the prior shock midpoint.")
            add(f"sig_41c_shock_cool_cont_short_m{str(mult).replace('.', '')}_h{h}", "41C_SHOCK_COOLDOWN_CONTINUATION", f"SHOCK_COOLDOWN_CONT_SHORT_M{mult}", "SHORT", h, h, short_mask, "Continuation only after a shock bar cools down and holds below the prior shock midpoint.")

    # 41D: Asia range break + retest continuation, different from plain Asia breakout.
    for tol in [15, 30, 45]:
        asia_ready = d["asia_high"].notna() & d["asia_low"].notna() & (d["asia_range_bps"].between(25, 180))
        long_mask = (
            asia_ready
            & d["hour_utc"].between(7, 13)
            & (d["high"] > d["asia_high"] * 1.0003)
            & (d["low"] <= d["asia_high"] * (1.0 + tol / 10000.0))
            & (d["close"] > d["asia_high"])
            & (d["close"] > d["sma72"])
        )
        short_mask = (
            asia_ready
            & d["hour_utc"].between(7, 13)
            & (d["low"] < d["asia_low"] * 0.9997)
            & (d["high"] >= d["asia_low"] * (1.0 - tol / 10000.0))
            & (d["close"] < d["asia_low"])
            & (d["close"] < d["sma72"])
        )
        for h in [12, 24, 48]:
            add(f"sig_41d_asia_retest_long_tol{tol}_h{h}", "41D_ASIA_RANGE_BREAK_RETEST", f"ASIA_BREAK_RETEST_LONG_TOL{tol}", "LONG", h, h, long_mask, "London/early-NY break and retest/hold of a completed Asia range high.")
            add(f"sig_41d_asia_retest_short_tol{tol}_h{h}", "41D_ASIA_RANGE_BREAK_RETEST", f"ASIA_BREAK_RETEST_SHORT_TOL{tol}", "SHORT", h, h, short_mask, "London/early-NY break and retest/hold of a completed Asia range low.")

    # 41E: Prior-day level reclaim/reject with session and trend constraints.
    for tol in [10, 25, 40]:
        prev_ready = d["prev_day_high"].notna() & d["prev_day_low"].notna() & (d["prev_day_range_bps"].between(50, 300))
        reclaim_long = (
            prev_ready
            & d["hour_utc"].between(8, 16)
            & (d["low"] <= d["prev_day_high"] * (1.0 + tol / 10000.0))
            & (d["close"] > d["prev_day_high"])
            & (d["signed_body_bps"] > 0)
            & (d["ret24_bps"] > -120)
        )
        reject_short = (
            prev_ready
            & d["hour_utc"].between(8, 16)
            & (d["high"] >= d["prev_day_low"] * (1.0 - tol / 10000.0))
            & (d["close"] < d["prev_day_low"])
            & (d["signed_body_bps"] < 0)
            & (d["ret24_bps"] < 120)
        )
        for h in [12, 24, 48]:
            add(f"sig_41e_prevday_reclaim_long_tol{tol}_h{h}", "41E_PRIOR_DAY_LEVEL_RECLAIM_REJECT", f"PREVDAY_HIGH_RECLAIM_LONG_TOL{tol}", "LONG", h, h, reclaim_long, "Reclaim/hold above prior-day high during liquid hours after tolerance-controlled retest.")
            add(f"sig_41e_prevday_reject_short_tol{tol}_h{h}", "41E_PRIOR_DAY_LEVEL_RECLAIM_REJECT", f"PREVDAY_LOW_REJECT_SHORT_TOL{tol}", "SHORT", h, h, reject_short, "Reject/hold below prior-day low during liquid hours after tolerance-controlled retest.")

    # 41F: Volatility regime expansion with multi-bar confirmation and early robustness required in classification.
    # This is deliberately not the failed Stage40 one-bar VOL_COMP_EXP_LONG_L120_Q0.15_M2.0.
    for comp_w in [72, 120, 168]:
        comp_floor = d["atr24_bps"] < d[f"atr{comp_w}_bps"] * 0.80
        two_bar_up = (d["close"] > d["open"]) & (d["close"].shift(1) > d["open"].shift(1)) & (d["close"] > d["high"].shift(1))
        two_bar_down = (d["close"] < d["open"]) & (d["close"].shift(1) < d["open"].shift(1)) & (d["close"] < d["low"].shift(1))
        normal_range = d["range_bps"] < d[f"atr{comp_w}_bps"] * 1.55
        for trend_gate in ["HTF", "NO_HTF"]:
            if trend_gate == "HTF":
                long_gate = d["htf_up"]
                short_gate = d["htf_down"]
            else:
                long_gate = d["ret24_bps"] > 0
                short_gate = d["ret24_bps"] < 0
            comp_ready = comp_floor.shift(2).fillna(False).astype(bool)
            long_mask = comp_ready & two_bar_up & normal_range & long_gate & d["hour_utc"].between(6, 16)
            short_mask = comp_ready & two_bar_down & normal_range & short_gate & d["hour_utc"].between(6, 16)
            for h in [24, 48, 72]:
                add(f"sig_41f_multibar_vol_expand_long_w{comp_w}_{trend_gate.lower()}_h{h}", "41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION", f"MULTIBAR_VOL_EXPAND_LONG_W{comp_w}_{trend_gate}", "LONG", h, h, long_mask, "Compression-to-expansion candidate requiring two-bar confirmation and explicit trend/volatility gate.")
                add(f"sig_41f_multibar_vol_expand_short_w{comp_w}_{trend_gate.lower()}_h{h}", "41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION", f"MULTIBAR_VOL_EXPAND_SHORT_W{comp_w}_{trend_gate}", "SHORT", h, h, short_mask, "Compression-to-expansion candidate requiring two-bar confirmation and explicit trend/volatility gate.")

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


def _future_path_stats(d: pd.DataFrame, event_idx: np.ndarray, horizon: int, side: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    lows = d["low"].to_numpy(dtype=float)
    highs = d["high"].to_numpy(dtype=float)
    closes = d["close"].to_numpy(dtype=float)
    mae: List[float] = []
    mfe: List[float] = []
    touch100: List[bool] = []
    n = len(d)
    for i in event_idx:
        if i + horizon >= n:
            mae.append(np.nan)
            mfe.append(np.nan)
            touch100.append(False)
            continue
        entry = closes[i]
        lo = np.nanmin(lows[i + 1 : i + horizon + 1])
        hi = np.nanmax(highs[i + 1 : i + horizon + 1])
        if not np.isfinite(entry) or entry <= 0:
            mae.append(np.nan)
            mfe.append(np.nan)
            touch100.append(False)
            continue
        if side == "LONG":
            ev_mae = (lo / entry - 1.0) * 10000.0
            ev_mfe = (hi / entry - 1.0) * 10000.0
        else:
            ev_mae = (entry / hi - 1.0) * 10000.0
            ev_mfe = (entry / lo - 1.0) * 10000.0
        mae.append(float(ev_mae))
        mfe.append(float(ev_mfe))
        touch100.append(bool(ev_mae <= -100.0))
    return np.asarray(mae), np.asarray(mfe), np.asarray(touch100, dtype=bool)


def _bootstrap_mean_stats(values: np.ndarray, seed: int = 41, rounds: int = 1000) -> Dict[str, float]:
    x = values[np.isfinite(values)]
    if len(x) < 10:
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

    if n < min_events or train_n < max(15, min_events // 3) or oos_n < max(10, min_events // 4):
        if n < min_events:
            reasons.append("event_clock_n_below_min")
        if train_n < max(15, min_events // 3):
            reasons.append("train_n_too_small")
        if oos_n < max(10, min_events // 4):
            reasons.append("oos_n_too_small")
        return CLASS_INSUFFICIENT, reasons

    strict_checks = {
        "cost_mean_gt_20": val("cost_stressed_mean_bps") > 20.0,
        "residual_gt_10": val("h1_benchmark_cost_adjusted_residual_bps") > 10.0,
        "train_gt_8": val("train_cost_mean_bps") > 8.0,
        "oos_gt_8": val("oos_cost_mean_bps") > 8.0,
        "worst_quarter_slip16_gt_0": val("worst_quarter_slip16_mean_bps") > 0.0,
        "boot_p10_gt_0": val("boot_p10_bps") > 0.0,
        "boot_prob_gt_90": val("boot_prob_mean_gt_0_pct") >= 90.0,
        "oos_touch100_le_55": val("oos_touch_stop_100bps_pct") <= 55.0,
        "top_year_share_le_55": val("top_year_event_share_pct") <= 55.0,
        "top_quarter_share_le_45": val("top_quarter_event_share_pct") <= 45.0,
        "positive_quarter_pct_ge_60": val("positive_quarter_pct") >= 60.0,
        "years_n_ge_3": years_n >= 3,
        "quarters_n_ge_8": quarters_n >= 8,
        "ex2025_gt_0": (np.isnan(val("ex2025_cost_mean_bps")) or val("ex2025_cost_mean_bps") > 0.0),
    }
    if all(strict_checks.values()):
        return CLASS_STRICT, []

    soft_checks = {
        "cost_mean_gt_8": val("cost_stressed_mean_bps") > 8.0,
        "residual_gt_0": val("h1_benchmark_cost_adjusted_residual_bps") > 0.0,
        "train_gt_0": val("train_cost_mean_bps") > 0.0,
        "oos_gt_0": val("oos_cost_mean_bps") > 0.0,
        "worst_quarter_slip16_gt_minus10": val("worst_quarter_slip16_mean_bps") > -10.0,
        "boot_p10_gt_minus5": val("boot_p10_bps") > -5.0,
        "boot_prob_gt_70": val("boot_prob_mean_gt_0_pct") >= 70.0,
        "oos_touch100_le_65": val("oos_touch_stop_100bps_pct") <= 65.0,
        "top_year_share_le_65": val("top_year_event_share_pct") <= 65.0,
        "positive_quarter_pct_ge_50": val("positive_quarter_pct") >= 50.0,
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
) -> Tuple[Dict[str, object], pd.DataFrame]:
    idx = _event_clock_indices(d[spec.mask_col], spec.min_gap)
    max_valid = len(d) - spec.horizon - 1
    idx = idx[idx <= max_valid]

    if spec.horizon not in [12, 24, 48, 72]:
        raise ValueError(f"Unexpected horizon={spec.horizon}")
    fwd = d[f"fwd{spec.horizon}_ret_bps"].to_numpy(dtype=float)
    side_sign = 1.0 if spec.side == "LONG" else -1.0
    raw_ret = fwd[idx] * side_sign if len(idx) else np.asarray([], dtype=float)
    cost_ret = raw_ret - cost_bps
    slip16_ret = cost_ret - slip_bps

    events = pd.DataFrame({
        "ts_utc": d.loc[idx, "ts_utc"].astype(str).to_numpy() if len(idx) else [],
        "family": spec.family,
        "candidate": spec.candidate,
        "side": spec.side,
        "horizon_h": spec.horizon,
        "entry_close": d.loc[idx, "close"].to_numpy(dtype=float) if len(idx) else [],
        "raw_return_bps": raw_ret,
        "cost_return_bps": cost_ret,
        "slip16_return_bps": slip16_ret,
        "hour_utc": d.loc[idx, "hour_utc"].to_numpy(dtype=int) if len(idx) else [],
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
            "horizon_h": spec.horizon,
            "description": spec.description,
            "event_clock_n": 0,
            "classification": CLASS_INSUFFICIENT,
            "failed_reasons": ["no_events"],
            **NO_PROMOTION_STATE,
        }
        return metrics, events

    mae, mfe, touch100 = _future_path_stats(d, idx, spec.horizon, spec.side)
    events["mae_bps"] = mae
    events["mfe_bps"] = mfe
    events["touch_stop_100bps"] = touch100

    # H1 benchmark: unconditional same-side return over all eligible H1 bars for the same horizon.
    all_fwd = d[f"fwd{spec.horizon}_ret_bps"].iloc[:max_valid].to_numpy(dtype=float) * side_sign
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
        "horizon_h": spec.horizon,
        "description": spec.description,
        "event_clock_n": int(len(events)),
        "raw_mean_bps": float(np.nanmean(events["raw_return_bps"])),
        "cost_stressed_mean_bps": float(np.nanmean(events["cost_return_bps"])),
        "slip16_mean_bps": float(np.nanmean(events["slip16_return_bps"])),
        "median_cost_bps": float(np.nanmedian(events["cost_return_bps"])),
        "win_rate_cost_pct": float((events["cost_return_bps"] > 0).mean() * 100.0),
        "h1_benchmark_cost_mean_bps": float(benchmark_cost),
        "h1_benchmark_cost_adjusted_residual_bps": float(np.nanmean(events["cost_return_bps"]) - benchmark_cost),
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
        "touch_stop_100bps_pct": float(events["touch_stop_100bps"].mean() * 100.0),
        "oos_median_mae_bps": float(np.nanmedian(oos_events["mae_bps"])) if not oos_events.empty else float("nan"),
        "oos_touch_stop_100bps_pct": float(oos_events["touch_stop_100bps"].mean() * 100.0) if not oos_events.empty else float("nan"),
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


def _write_markdown_report(
    out_path: Path,
    summary: Dict[str, object],
    candidates: pd.DataFrame,
) -> None:
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
    lines.append("Stage41 scan is a research shortlist step only. Any strict/soft row is watch-only and must go through a separate Stage41B path-stability/promotion audit before any operational layer is considered.")
    lines.append("")
    lines.append("## Input data")
    lines.append("")
    meta = summary.get("data", {}) if isinstance(summary.get("data"), dict) else {}
    lines.append("```text")
    for k in ["db_path", "table", "source", "symbol", "timeframe", "loaded_rows", "loaded_start", "loaded_end"]:
        lines.append(f"{k}: {meta.get(k)}")
    lines.append("```")
    lines.append("")
    lines.append("## Thesis families scanned")
    lines.append("")
    families = summary.get("families_scanned", [])
    for fam in families:
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
            "classification", "family", "candidate", "side", "horizon_h", "event_clock_n",
            "cost_stressed_mean_bps", "h1_benchmark_cost_adjusted_residual_bps",
            "train_cost_mean_bps", "oos_cost_mean_bps", "worst_quarter_slip16_mean_bps",
            "boot_p10_bps", "oos_touch_stop_100bps_pct", "top_year_event_share_pct", "failed_reasons",
        ]
        existing_cols = [c for c in display_cols if c in candidates.columns]
        top = candidates[existing_cols].head(40)
        lines.append(top.to_markdown(index=False))
    lines.append("")
    lines.append("## Anti-overfit note")
    lines.append("")
    lines.append("Do not rescue failed Stage41 rows by removing weak buckets after seeing this output. A later Stage41B may audit only pre-existing strict/soft shortlist rows with predefined path-stability, slip, LOYO, concentration, and OOS gates.")
    lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    df, meta = _read_sqlite_bars(
        db_path=Path(args.db),
        table=args.table,
        source=args.source,
        symbol=args.symbol,
        timeframe=args.timeframe,
    )
    featured = _add_features(df)
    featured, specs = _build_signal_masks(featured)

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
            )
            candidate_rows.append(metrics)
            if not events.empty:
                event_frames.append(events)
        except Exception as exc:  # keep megascan running; record the failed spec.
            row = {
                "stage": STAGE_NAME,
                "family": spec.family,
                "candidate": spec.candidate,
                "side": spec.side,
                "horizon_h": spec.horizon,
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
        sort_cols = ["_class_rank", "cost_stressed_mean_bps", "h1_benchmark_cost_adjusted_residual_bps", "event_clock_n"]
        existing = [c for c in sort_cols if c in candidates.columns]
        candidates = candidates.sort_values(existing, ascending=[True, False, False, False][: len(existing)]).drop(columns=["_class_rank"])

    events_all = pd.concat(event_frames, ignore_index=True) if event_frames else pd.DataFrame()

    candidates_path = outdir / "stage41_parallel_thesis_megascan_v2_candidates.csv"
    events_path = outdir / "stage41_parallel_thesis_megascan_v2_events.csv"
    summary_path = outdir / "stage41_parallel_thesis_megascan_v2_summary.json"
    md_path = outdir / "stage41_parallel_thesis_megascan_v2.md"

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
            "event_clock": "candidate-specific min_gap equals horizon",
            "train_oos_split": "chronological 70/30 event-clock split",
        },
        "families_scanned": sorted(candidates["family"].dropna().unique().tolist()) if not candidates.empty else [],
        "candidate_rows": int(len(candidates)),
        "events_rows_written": int(len(events_all)),
        "strict_stage41_scan_watch_count": strict_count,
        "soft_stage41_scan_watch_count": soft_count,
        "classification_counts": {str(k): int(v) for k, v in classification_counts.items()},
        "errors": errors,
        **NO_PROMOTION_STATE,
        "next_allowed_step": "Stage41B_STRICT_SHORTLIST_PATH_STABILITY_AUDIT only if strict_stage41_scan_watch_count > 0; otherwise archive Stage41 or start new thesis families.",
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    _write_markdown_report(md_path, summary, candidates)

    print(json.dumps({
        "stage": STAGE_NAME,
        "candidate_rows": int(len(candidates)),
        "events_rows_written": int(len(events_all)),
        "strict_stage41_scan_watch_count": strict_count,
        "soft_stage41_scan_watch_count": soft_count,
        "summary_path": str(summary_path),
        "candidates_path": str(candidates_path),
        "events_path": str(events_path),
        "markdown_path": str(md_path),
        **NO_PROMOTION_STATE,
    }, ensure_ascii=False, indent=2))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Stage41 parallel thesis megascan v2 for XAUUSD H1.")
    p.add_argument("--db", default=str(DEFAULT_DB), help="SQLite DB path. Default: data/local/xauusd_local_store.sqlite")
    p.add_argument("--table", default=DEFAULT_TABLE, help="Bars table name. Default: bars")
    p.add_argument("--source", default=DEFAULT_SOURCE, help="Source filter if source column exists. Default: amarkets_mt5")
    p.add_argument("--symbol", default=DEFAULT_SYMBOL, help="Symbol filter if symbol column exists. Default: XAUUSD")
    p.add_argument("--timeframe", default=DEFAULT_TIMEFRAME, help="Timeframe filter if timeframe column exists. Default: H1")
    p.add_argument("--outdir", default=str(DEFAULT_OUTDIR), help="Output directory. Default: reports/stage41")
    p.add_argument("--cost-bps", type=float, default=8.0, help="Round-trip cost assumption in bps subtracted from every event. Default: 8")
    p.add_argument("--slip-bps", type=float, default=16.0, help="Additional slippage stress used for slip16 stability. Default: 16")
    p.add_argument("--min-events", type=int, default=40, help="Minimum event-clock count for non-insufficient classification. Default: 40")
    return p


if __name__ == "__main__":
    raise SystemExit(run(build_arg_parser().parse_args()))
