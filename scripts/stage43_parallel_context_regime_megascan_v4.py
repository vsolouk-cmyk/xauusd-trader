#!/usr/bin/env python3
"""
Stage43_PARALLEL_CONTEXT_REGIME_MEGASCAN_V4

Independent XAUUSD context/regime thesis megascan after Stage41/Stage42 archives.
Default timeframe is M15. Stage43 is not a rescue/filter extension of prior
failed rows; it builds predefined context regimes from endogenous data:
HTF trend proxy, volatility state, session context, prior-day location, and
compression/expansion state.

Research-only outputs:
  reports/stage43/stage43_parallel_context_regime_megascan_v4_candidates.csv
  reports/stage43/stage43_parallel_context_regime_megascan_v4_events.csv
  reports/stage43/stage43_parallel_context_regime_megascan_v4_summary.json
  reports/stage43/stage43_parallel_context_regime_megascan_v4.md
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
warnings.filterwarnings(
    "ignore",
    message="Converting to PeriodArray/Index representation will drop timezone information.",
    category=UserWarning,
)

STAGE_NAME = "Stage43_PARALLEL_CONTEXT_REGIME_MEGASCAN_V4"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_TABLE = "bars"
DEFAULT_OUTDIR = Path("reports/stage43")
DEFAULT_SOURCE = "amarkets_mt5"
DEFAULT_SYMBOL = "XAUUSD"
DEFAULT_TIMEFRAME = "M15"

NO_PROMOTION_STATE = {
    "promotion": "NO_GO",
    "EA": "NO_GO",
    "paper_live": "NO_GO",
    "live": "NO_GO",
}

CLASS_STRICT = "STRICT_STAGE43_CONTEXT_REGIME_SCAN_WATCH_ONLY_NO_PROMOTION"
CLASS_SOFT = "SOFT_STAGE43_CONTEXT_REGIME_SCAN_WATCH_ONLY_NO_PROMOTION"
CLASS_FAIL = "FAIL_BENCHMARK_OR_CONTEXT_STABILITY_RESEARCH_ONLY"
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
        "30M": "M30", "M30": "M30", "30MIN": "M30", "30MINS": "M30", "30MINUTE": "M30", "30MINUTES": "M30",
        "4H": "H4", "H4": "H4", "240": "H4", "240M": "H4", "M240": "H4",
        "1D": "D1", "D1": "D1", "DAILY": "D1",
    }
    return aliases.get(raw, raw)


def _timeframe_minutes(tf: object) -> int:
    norm = _norm_timeframe(tf)
    mapping = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}
    if norm not in mapping:
        raise ValueError(f"Unsupported timeframe for Stage43: {tf!r} -> {norm!r}")
    minutes = mapping[norm]
    if minutes > 60:
        raise ValueError(f"Stage43 is intraday/context scan; use M1/M5/M15/M30/H1, got {norm}")
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

    if source_col and source:
        exact = _series_norm(df["__source_raw"]) == _norm_text(source)
        compact = _series_compact(df["__source_raw"]) == _norm_compact(source)
        mask = exact | compact
        filter_debug["source_exact_matches"] = int(exact.sum())
        filter_debug["source_compact_matches"] = int(compact.sum())
        df = df.loc[mask].copy()
    else:
        filter_debug["source_filter_skipped"] = True

    if symbol_col and symbol:
        exact = _series_norm(df["__symbol_raw"]) == _norm_text(symbol)
        compact = _series_compact(df["__symbol_raw"]) == _norm_compact(symbol)
        mask = exact | compact
        filter_debug["symbol_exact_matches"] = int(exact.sum())
        filter_debug["symbol_compact_matches"] = int(compact.sum())
        df = df.loc[mask].copy()
    else:
        filter_debug["symbol_filter_skipped"] = True

    requested_tf_norm = _norm_timeframe(timeframe)
    filter_debug["requested_timeframe_normalized"] = requested_tf_norm
    if timeframe_col and timeframe:
        tf_norm = _series_timeframe(df["__timeframe_raw"])
        mask = tf_norm == requested_tf_norm
        filter_debug["timeframe_alias_matches"] = int(mask.sum())
        df = df.loc[mask].copy()
    else:
        filter_debug["timeframe_filter_skipped"] = True

    filter_debug["post_filter_rows_before_ohlc_clean"] = int(len(df))
    if df.empty:
        diagnostic = {
            "message": "No bars loaded after source/symbol/timeframe filtering.",
            "filter_debug": filter_debug,
            "available_dimensions_top20": dimension_preview,
        }
        raise RuntimeError(json.dumps(diagnostic, indent=2, ensure_ascii=False))

    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    else:
        df["volume"] = np.nan
    if "spread_raw" in df.columns:
        df["spread"] = pd.to_numeric(df["spread_raw"], errors="coerce")
    else:
        df["spread"] = np.nan

    df = df.dropna(subset=["ts_utc", "open", "high", "low", "close"])
    df = df.sort_values("ts_utc").drop_duplicates(subset=["ts_utc"], keep="last").reset_index(drop=True)
    filter_debug["post_filter_rows_after_ohlc_clean"] = int(len(df))
    if df.empty:
        raise RuntimeError("No valid OHLC rows after cleaning; check timestamp/OHLC data quality.")

    loaded_dimension_values_top20 = {
        "source": sorted(df["__source_raw"].dropna().astype(str).unique().tolist())[:20] if "__source_raw" in df else [],
        "symbol": sorted(df["__symbol_raw"].dropna().astype(str).unique().tolist())[:20] if "__symbol_raw" in df else [],
        "timeframe": sorted(df["__timeframe_raw"].dropna().astype(str).unique().tolist())[:20] if "__timeframe_raw" in df else [],
    }

    tf_minutes = _timeframe_minutes(timeframe)
    meta = {
        "db_path": str(db_path),
        "table": table,
        "source_filter_used": bool(source_col and source),
        "symbol_filter_used": bool(symbol_col and symbol),
        "timeframe_filter_used": bool(timeframe_col and timeframe),
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "timeframe_normalized": requested_tf_norm,
        "timeframe_minutes": tf_minutes,
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
            "spread": spread_col,
            "source": source_col,
            "symbol": symbol_col,
            "timeframe": timeframe_col,
        },
        "available_dimensions_top20": dimension_preview,
        "loaded_dimension_values_top20": loaded_dimension_values_top20,
        "filter_debug": filter_debug,
    }
    return df[["ts_utc", "open", "high", "low", "close", "volume", "spread"]].copy(), meta


def _safe_div(a: pd.Series, b: pd.Series) -> pd.Series:
    return a / b.replace(0, np.nan)


def _rolling_quantile(s: pd.Series, window: int, q: float, min_periods: Optional[int] = None) -> pd.Series:
    if min_periods is None:
        min_periods = max(20, int(window * 0.2))
    return s.rolling(window, min_periods=min_periods).quantile(q)


def _add_features(df: pd.DataFrame, tf_minutes: int) -> pd.DataFrame:
    out = df.copy()
    out["ts_utc"] = pd.to_datetime(out["ts_utc"], utc=True)
    out = out.sort_values("ts_utc").reset_index(drop=True)
    idx = pd.DatetimeIndex(out["ts_utc"])
    out["year"] = idx.year
    out["quarter"] = idx.to_period("Q").astype(str)
    out["month"] = idx.month
    out["weekday"] = idx.weekday
    out["hour_utc"] = idx.hour
    out["minute"] = idx.minute
    out["date"] = idx.floor("D")

    close = out["close"].astype(float)
    high = out["high"].astype(float)
    low = out["low"].astype(float)
    prev_close = close.shift(1)
    tr_abs = pd.concat([(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    out["tr_bps"] = _safe_div(tr_abs, prev_close) * 10000.0
    out["bar_range_bps"] = _safe_div(high - low, close) * 10000.0

    def bars(minutes: int) -> int:
        return max(1, int(round(minutes / tf_minutes)))

    b1h = bars(60)
    b2h = bars(120)
    b4h = bars(240)
    b8h = bars(480)
    b12h = bars(720)
    b24h = bars(1440)
    b48h = bars(2880)
    b5d = bars(1440 * 5)
    b10d = bars(1440 * 10)
    b20d = bars(1440 * 20)

    for n, label in [(1, "1b"), (b1h, "1h"), (b2h, "2h"), (b4h, "4h"), (b8h, "8h"), (b24h, "24h"), (b48h, "48h")]:
        out[f"ret_{label}_bps"] = (close / close.shift(n) - 1.0) * 10000.0

    out["atr_1h_bps"] = out["tr_bps"].rolling(b1h, min_periods=max(2, b1h // 2)).mean()
    out["atr_4h_bps"] = out["tr_bps"].rolling(b4h, min_periods=max(3, b4h // 2)).mean()
    out["atr_24h_bps"] = out["tr_bps"].rolling(b24h, min_periods=max(8, b24h // 3)).mean()
    out["atr_5d_bps"] = out["tr_bps"].rolling(b5d, min_periods=max(20, b5d // 3)).mean()
    out["atr_ratio_4h_24h"] = _safe_div(out["atr_4h_bps"], out["atr_24h_bps"])

    out["ma_4h"] = close.rolling(b4h, min_periods=max(4, b4h // 2)).mean()
    out["ma_24h"] = close.rolling(b24h, min_periods=max(8, b24h // 3)).mean()
    out["ma_5d"] = close.rolling(b5d, min_periods=max(20, b5d // 3)).mean()
    out["ma_20d"] = close.rolling(b20d, min_periods=max(80, b20d // 3)).mean()
    out["trend_fast_bps"] = _safe_div(out["ma_4h"] - out["ma_24h"], close) * 10000.0
    out["trend_slow_bps"] = _safe_div(out["ma_5d"] - out["ma_20d"], close) * 10000.0
    out["trend_up"] = (out["trend_fast_bps"] > 5.0) & (out["trend_slow_bps"] > -5.0)
    out["trend_down"] = (out["trend_fast_bps"] < -5.0) & (out["trend_slow_bps"] < 5.0)
    out["trend_neutral"] = ~(out["trend_up"] | out["trend_down"])

    q_window = max(b10d, 80)
    out["atr24_q35"] = _rolling_quantile(out["atr_24h_bps"], q_window, 0.35)
    out["atr24_q65"] = _rolling_quantile(out["atr_24h_bps"], q_window, 0.65)
    out["atr24_q80"] = _rolling_quantile(out["atr_24h_bps"], q_window, 0.80)
    out["vol_low"] = out["atr_24h_bps"] < out["atr24_q35"]
    out["vol_mid_or_high"] = out["atr_24h_bps"] >= out["atr24_q35"]
    out["vol_high"] = out["atr_24h_bps"] > out["atr24_q65"]
    out["vol_extreme"] = out["atr_24h_bps"] > out["atr24_q80"]
    out["compression"] = out["atr_4h_bps"] < _rolling_quantile(out["atr_4h_bps"], q_window, 0.25)
    out["expansion_bar"] = out["tr_bps"] > (out["atr_4h_bps"] * 1.25)

    # Prior-day and current-day context. These are known after a completed prior day; same-day open is known.
    daily = out.groupby("date", observed=True).agg(
        day_open=("open", "first"),
        day_high=("high", "max"),
        day_low=("low", "min"),
        day_close=("close", "last"),
    )
    prev_daily = daily.shift(1).rename(columns={
        "day_open": "prev_day_open",
        "day_high": "prev_day_high",
        "day_low": "prev_day_low",
        "day_close": "prev_day_close",
    })
    prev_daily["prev_day_range_bps"] = _safe_div(prev_daily["prev_day_high"] - prev_daily["prev_day_low"], prev_daily["prev_day_close"]) * 10000.0
    out = out.join(daily[["day_open"]], on="date")
    out = out.join(prev_daily, on="date")
    out["prev_day_mid"] = (out["prev_day_high"] + out["prev_day_low"]) / 2.0
    out["dist_prev_high_bps"] = _safe_div(close - out["prev_day_high"], close) * 10000.0
    out["dist_prev_low_bps"] = _safe_div(close - out["prev_day_low"], close) * 10000.0
    out["dist_day_open_bps"] = _safe_div(close - out["day_open"], close) * 10000.0

    range_q35 = _rolling_quantile(out["prev_day_range_bps"], max(b20d, 120), 0.35)
    range_q65 = _rolling_quantile(out["prev_day_range_bps"], max(b20d, 120), 0.65)
    out["prev_range_low"] = out["prev_day_range_bps"] < range_q35
    out["prev_range_high"] = out["prev_day_range_bps"] > range_q65

    # Asia range is only used after Asia session is completed.
    asia_slice = out[(out["hour_utc"] >= 0) & (out["hour_utc"] <= 5)]
    asia = asia_slice.groupby("date", observed=True).agg(asia_high=("high", "max"), asia_low=("low", "min"))
    asia["asia_mid"] = (asia["asia_high"] + asia["asia_low"]) / 2.0
    out = out.join(asia, on="date")
    out["asia_range_bps"] = _safe_div(out["asia_high"] - out["asia_low"], close) * 10000.0

    out["session_asia"] = (out["hour_utc"] >= 0) & (out["hour_utc"] <= 6)
    out["session_london"] = (out["hour_utc"] >= 7) & (out["hour_utc"] <= 12)
    out["session_ny"] = (out["hour_utc"] >= 13) & (out["hour_utc"] <= 20)
    out["session_overlap"] = (out["hour_utc"] >= 13) & (out["hour_utc"] <= 16)
    out["session_post_asia"] = (out["hour_utc"] >= 7) & (out["hour_utc"] <= 16)

    # Rolling local breakout levels shifted one bar to avoid same-bar lookahead.
    out["roll_high_1h_prev"] = high.rolling(b1h, min_periods=max(2, b1h // 2)).max().shift(1)
    out["roll_low_1h_prev"] = low.rolling(b1h, min_periods=max(2, b1h // 2)).min().shift(1)
    out["roll_high_4h_prev"] = high.rolling(b4h, min_periods=max(4, b4h // 2)).max().shift(1)
    out["roll_low_4h_prev"] = low.rolling(b4h, min_periods=max(4, b4h // 2)).min().shift(1)

    out.attrs["derived_bars"] = {
        "b1h": b1h,
        "b2h": b2h,
        "b4h": b4h,
        "b8h": b8h,
        "b12h": b12h,
        "b24h": b24h,
        "b48h": b48h,
        "b5d": b5d,
        "b10d": b10d,
        "b20d": b20d,
    }
    return out


def _add_candidate_masks(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[ThesisSpec]]:
    out = df.copy()
    b = out.attrs.get("derived_bars", {})
    b1h = int(b.get("b1h", 4))
    b2h = int(b.get("b2h", 8))
    b4h = int(b.get("b4h", 16))
    b8h = int(b.get("b8h", 32))
    horizons = [b1h, b2h, b4h, b8h]
    specs: List[ThesisSpec] = []

    def add_mask(family: str, candidate: str, side: str, base_mask: pd.Series, description: str, horizon_set: Iterable[int] = horizons) -> None:
        clean_base = base_mask.fillna(False).astype(bool)
        for h in horizon_set:
            mask_col = f"mask__{candidate}__{h}b"
            out[mask_col] = clean_base
            specs.append(ThesisSpec(
                family=family,
                candidate=candidate,
                side=side,
                horizon_bars=int(h),
                min_gap_bars=int(h),
                mask_col=mask_col,
                description=description,
            ))

    close = out["close"]
    low = out["low"]
    high = out["high"]

    session_masks = {
        "LDN": out["session_london"],
        "NY": out["session_ny"],
        "OVL": out["session_overlap"],
    }

    # 43A: HTF/context-aligned pullback continuation; not a pure microtrend rule.
    for sess_name, sess_mask in session_masks.items():
        for p in [12, 20, 35]:
            long_mask = out["trend_up"] & out["vol_mid_or_high"] & sess_mask & (out["ret_1h_bps"] <= -p) & (close > out["ma_5d"]) & (out["dist_day_open_bps"] > -80)
            short_mask = out["trend_down"] & out["vol_mid_or_high"] & sess_mask & (out["ret_1h_bps"] >= p) & (close < out["ma_5d"]) & (out["dist_day_open_bps"] < 80)
            add_mask("43A_CONTEXT_TREND_PULLBACK_CONTINUATION", f"CTX_TREND_PULLBACK_LONG_{sess_name}_P{p}", "LONG", long_mask, f"HTF trend-up plus {sess_name} pullback >= {p}bps in non-low-vol regime")
            add_mask("43A_CONTEXT_TREND_PULLBACK_CONTINUATION", f"CTX_TREND_PULLBACK_SHORT_{sess_name}_P{p}", "SHORT", short_mask, f"HTF trend-down plus {sess_name} pullback >= {p}bps in non-low-vol regime")

    # 43B: High-volatility impulse exhaustion, requiring prior-day location context.
    for sess_name, sess_mask in session_masks.items():
        for imp in [40, 70, 100]:
            near_low = (low <= out["prev_day_low"] * (1.0 + 0.0035)) | (close < out["prev_day_mid"])
            near_high = (high >= out["prev_day_high"] * (1.0 - 0.0035)) | (close > out["prev_day_mid"])
            long_mask = out["vol_high"] & sess_mask & (out["ret_2h_bps"] <= -imp) & near_low & ~out["trend_down"]
            short_mask = out["vol_high"] & sess_mask & (out["ret_2h_bps"] >= imp) & near_high & ~out["trend_up"]
            add_mask("43B_VOL_CONTEXT_IMPULSE_EXHAUSTION_REVERSAL", f"VOLCTX_EXHAUST_LONG_{sess_name}_I{imp}", "LONG", long_mask, f"High-vol impulse down >= {imp}bps into prior-day lower/value context")
            add_mask("43B_VOL_CONTEXT_IMPULSE_EXHAUSTION_REVERSAL", f"VOLCTX_EXHAUST_SHORT_{sess_name}_I{imp}", "SHORT", short_mask, f"High-vol impulse up >= {imp}bps into prior-day upper/value context")

    # 43C: Prior-day level reclaim/reject with predefined regime filters.
    for tol in [10, 20, 35, 50]:
        long_mask = out["session_post_asia"] & out["vol_mid_or_high"] & ~out["trend_down"] & (low <= out["prev_day_low"] * (1.0 + tol / 10000.0)) & (close > out["prev_day_low"]) & (out["ret_1h_bps"] > -60)
        short_mask = out["session_post_asia"] & out["vol_mid_or_high"] & ~out["trend_up"] & (high >= out["prev_day_high"] * (1.0 - tol / 10000.0)) & (close < out["prev_day_high"]) & (out["ret_1h_bps"] < 60)
        add_mask("43C_PRIOR_DAY_CONTEXT_RECLAIM_REJECT", f"PDR_CONTEXT_RECLAIM_LONG_TOL{tol}", "LONG", long_mask, f"Prior-day low reclaim with tol={tol}bps and no HTF down-regime")
        add_mask("43C_PRIOR_DAY_CONTEXT_RECLAIM_REJECT", f"PDR_CONTEXT_REJECT_SHORT_TOL{tol}", "SHORT", short_mask, f"Prior-day high reject with tol={tol}bps and no HTF up-regime")

    # 43D: Low-volatility context to expansion, but only when higher-timeframe context agrees.
    for mult in [1.10, 1.25, 1.45]:
        long_break = close > out["roll_high_1h_prev"]
        short_break = close < out["roll_low_1h_prev"]
        long_mask = out["session_post_asia"] & out["vol_low"] & out["compression"] & (out["tr_bps"] > out["atr_4h_bps"] * mult) & long_break & (out["trend_fast_bps"] > -5)
        short_mask = out["session_post_asia"] & out["vol_low"] & out["compression"] & (out["tr_bps"] > out["atr_4h_bps"] * mult) & short_break & (out["trend_fast_bps"] < 5)
        tag = str(mult).replace(".", "p")
        add_mask("43D_CONTEXT_COMPRESSION_TO_EXPANSION", f"CTX_COMP_EXPAND_LONG_M{tag}", "LONG", long_mask, f"Low-vol compression expansion long with multiplier {mult} and non-bearish context")
        add_mask("43D_CONTEXT_COMPRESSION_TO_EXPANSION", f"CTX_COMP_EXPAND_SHORT_M{tag}", "SHORT", short_mask, f"Low-vol compression expansion short with multiplier {mult} and non-bullish context")

    # 43E: Asia-range acceptance/rejection only under prior-day range regime, not raw session breakout.
    for tol in [8, 15, 25, 40]:
        long_accept = out["session_post_asia"] & out["prev_range_low"] & out["vol_mid_or_high"] & (close > out["asia_high"] * (1.0 + tol / 10000.0)) & (out["dist_day_open_bps"] > 0) & ~out["trend_down"]
        short_accept = out["session_post_asia"] & out["prev_range_low"] & out["vol_mid_or_high"] & (close < out["asia_low"] * (1.0 - tol / 10000.0)) & (out["dist_day_open_bps"] < 0) & ~out["trend_up"]
        long_reject = out["session_post_asia"] & out["prev_range_high"] & (high >= out["asia_high"] * (1.0 + tol / 10000.0)) & (close < out["asia_high"]) & ~out["trend_up"]
        short_reject = out["session_post_asia"] & out["prev_range_high"] & (low <= out["asia_low"] * (1.0 - tol / 10000.0)) & (close > out["asia_low"]) & ~out["trend_down"]
        add_mask("43E_ASIA_RANGE_REGIME_ACCEPT_REJECT", f"ASIA_REGIME_ACCEPT_LONG_TOL{tol}", "LONG", long_accept, f"Asia high acceptance after low prior-day range, tol={tol}bps")
        add_mask("43E_ASIA_RANGE_REGIME_ACCEPT_REJECT", f"ASIA_REGIME_ACCEPT_SHORT_TOL{tol}", "SHORT", short_accept, f"Asia low acceptance after low prior-day range, tol={tol}bps")
        add_mask("43E_ASIA_RANGE_REGIME_ACCEPT_REJECT", f"ASIA_REGIME_REJECT_SHORT_TOL{tol}", "SHORT", long_reject, f"Asia high rejection after high prior-day range, tol={tol}bps")
        add_mask("43E_ASIA_RANGE_REGIME_ACCEPT_REJECT", f"ASIA_REGIME_REJECT_LONG_TOL{tol}", "LONG", short_reject, f"Asia low rejection after high prior-day range, tol={tol}bps")

    # 43F: Neutral-regime value rotation after controlled impulse; explicitly excludes strong trend context.
    for p in [20, 35, 55]:
        for sess_name, sess_mask in session_masks.items():
            long_mask = out["trend_neutral"] & out["vol_low"] & sess_mask & (out["ret_1h_bps"] <= -p) & (close > out["prev_day_low"]) & (close < out["prev_day_high"])
            short_mask = out["trend_neutral"] & out["vol_low"] & sess_mask & (out["ret_1h_bps"] >= p) & (close < out["prev_day_high"]) & (close > out["prev_day_low"])
            add_mask("43F_NEUTRAL_REGIME_VALUE_ROTATION", f"NEUTRAL_VALUE_ROTATE_LONG_{sess_name}_P{p}", "LONG", long_mask, f"Neutral+low-vol value rotation long after {p}bps downside impulse in {sess_name}")
            add_mask("43F_NEUTRAL_REGIME_VALUE_ROTATION", f"NEUTRAL_VALUE_ROTATE_SHORT_{sess_name}_P{p}", "SHORT", short_mask, f"Neutral+low-vol value rotation short after {p}bps upside impulse in {sess_name}")

    return out, specs


def _event_indices(mask: pd.Series, horizon_bars: int, min_gap_bars: int, n_rows: int) -> np.ndarray:
    raw_idx = np.flatnonzero(mask.fillna(False).to_numpy(dtype=bool))
    raw_idx = raw_idx[raw_idx + horizon_bars < n_rows]
    if raw_idx.size == 0:
        return raw_idx
    selected: List[int] = []
    last = -10**12
    for i in raw_idx:
        if i >= last + min_gap_bars:
            selected.append(int(i))
            last = int(i)
    return np.asarray(selected, dtype=int)


def _side_mult(side: str) -> int:
    return 1 if side.upper() == "LONG" else -1


def _path_stats(df: pd.DataFrame, indices: np.ndarray, horizon_bars: int, side: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    close = df["close"].to_numpy(float)
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    mult = _side_mult(side)
    mae = np.full(indices.shape, np.nan, dtype=float)
    mfe = np.full(indices.shape, np.nan, dtype=float)
    touch50 = np.zeros(indices.shape, dtype=bool)
    touch75 = np.zeros(indices.shape, dtype=bool)
    for j, i in enumerate(indices):
        start = i + 1
        end = i + horizon_bars + 1
        if end > len(close):
            continue
        entry = close[i]
        if not np.isfinite(entry) or entry == 0:
            continue
        if mult > 0:
            adverse = (np.nanmin(low[start:end]) / entry - 1.0) * 10000.0
            favorable = (np.nanmax(high[start:end]) / entry - 1.0) * 10000.0
        else:
            adverse = (1.0 - np.nanmax(high[start:end]) / entry) * 10000.0
            favorable = (1.0 - np.nanmin(low[start:end]) / entry) * 10000.0
        mae[j] = adverse
        mfe[j] = favorable
        touch50[j] = bool(adverse <= -50.0)
        touch75[j] = bool(adverse <= -75.0)
    return mae, mfe, touch50, touch75


def _forward_returns(df: pd.DataFrame, indices: np.ndarray, horizon_bars: int, side: str, cost_bps: float) -> np.ndarray:
    close = df["close"].to_numpy(float)
    mult = _side_mult(side)
    entry = close[indices]
    exit_ = close[indices + horizon_bars]
    raw = mult * (exit_ / entry - 1.0) * 10000.0
    return raw - float(cost_bps)


def _benchmark_mean(df: pd.DataFrame, horizon_bars: int, side: str, cost_bps: float) -> float:
    n = len(df)
    all_mask = pd.Series(np.ones(n, dtype=bool))
    idx = _event_indices(all_mask, horizon_bars, horizon_bars, n)
    if idx.size == 0:
        return float("nan")
    return float(np.nanmean(_forward_returns(df, idx, horizon_bars, side, cost_bps)))


def _bootstrap_stats(values: np.ndarray, rng: np.random.Generator, n_boot: int = 800) -> Tuple[float, float]:
    values = values[np.isfinite(values)]
    n = len(values)
    if n == 0:
        return float("nan"), float("nan")
    if n == 1:
        return float(values[0]), 100.0 if values[0] > 0 else 0.0
    samples = rng.choice(values, size=(int(n_boot), n), replace=True)
    means = np.nanmean(samples, axis=1)
    return float(np.nanpercentile(means, 10)), float(np.mean(means > 0) * 100.0)


def _pct(condition: np.ndarray) -> float:
    condition = np.asarray(condition)
    if condition.size == 0:
        return float("nan")
    return float(np.nanmean(condition.astype(float)) * 100.0)


def _evaluate_candidate(
    df: pd.DataFrame,
    spec: ThesisSpec,
    cost_bps: float,
    slip_bps: float,
    min_events: int,
    rng: np.random.Generator,
    benchmark_cache: Dict[Tuple[int, str], float],
) -> Tuple[Dict[str, object], pd.DataFrame]:
    idx = _event_indices(df[spec.mask_col], spec.horizon_bars, spec.min_gap_bars, len(df))
    n = int(idx.size)
    base_row: Dict[str, object] = {
        "stage": STAGE_NAME,
        "family": spec.family,
        "candidate": spec.candidate,
        "side": spec.side,
        "horizon_bars": int(spec.horizon_bars),
        "horizon_minutes": int(spec.horizon_bars * df.attrs.get("timeframe_minutes", 15)),
        "event_clock_n": n,
        "description": spec.description,
    }
    if n == 0:
        base_row.update({
            "classification": CLASS_INSUFFICIENT,
            "failed_reasons": "insufficient_events",
        })
        return base_row, pd.DataFrame()

    returns = _forward_returns(df, idx, spec.horizon_bars, spec.side, cost_bps)
    returns_slip16 = returns - float(slip_bps)
    mae, mfe, touch50, touch75 = _path_stats(df, idx, spec.horizon_bars, spec.side)

    event_df = pd.DataFrame({
        "stage": STAGE_NAME,
        "family": spec.family,
        "candidate": spec.candidate,
        "side": spec.side,
        "horizon_bars": int(spec.horizon_bars),
        "horizon_minutes": int(spec.horizon_bars * df.attrs.get("timeframe_minutes", 15)),
        "entry_i": idx,
        "entry_ts_utc": df["ts_utc"].iloc[idx].astype(str).to_numpy(),
        "exit_ts_utc": df["ts_utc"].iloc[idx + spec.horizon_bars].astype(str).to_numpy(),
        "entry_close": df["close"].iloc[idx].to_numpy(float),
        "exit_close": df["close"].iloc[idx + spec.horizon_bars].to_numpy(float),
        "cost_return_bps": returns,
        "slip16_return_bps": returns_slip16,
        "mae_bps": mae,
        "mfe_bps": mfe,
        "touch_stop_50bps": touch50,
        "touch_stop_75bps": touch75,
        "year": df["year"].iloc[idx].to_numpy(int),
        "quarter": df["quarter"].iloc[idx].astype(str).to_numpy(),
        "hour_utc": df["hour_utc"].iloc[idx].to_numpy(int),
        "weekday": df["weekday"].iloc[idx].to_numpy(int),
        "trend_fast_bps": df["trend_fast_bps"].iloc[idx].to_numpy(float),
        "trend_slow_bps": df["trend_slow_bps"].iloc[idx].to_numpy(float),
        "atr_24h_bps": df["atr_24h_bps"].iloc[idx].to_numpy(float),
        "atr_ratio_4h_24h": df["atr_ratio_4h_24h"].iloc[idx].to_numpy(float),
    })

    if n < min_events:
        base_row.update({
            "classification": CLASS_INSUFFICIENT,
            "cost_stressed_mean_bps": float(np.nanmean(returns)),
            "failed_reasons": f"event_clock_n_lt_{min_events}",
        })
        return base_row, event_df

    split = max(1, min(n - 1, int(math.floor(n * 0.70))))
    train = returns[:split]
    oos = returns[split:]
    oos_touch50 = touch50[split:]

    bench_key = (int(spec.horizon_bars), spec.side)
    if bench_key not in benchmark_cache:
        benchmark_cache[bench_key] = _benchmark_mean(df, spec.horizon_bars, spec.side, cost_bps)
    bench = benchmark_cache[bench_key]
    residual = float(np.nanmean(returns) - bench) if np.isfinite(bench) else float("nan")

    by_quarter = event_df.groupby("quarter", observed=True)["slip16_return_bps"].mean()
    worst_quarter_slip16 = float(by_quarter.min()) if not by_quarter.empty else float("nan")
    pos_quarter_pct = float((by_quarter > 0).mean() * 100.0) if not by_quarter.empty else float("nan")
    by_year_n = event_df.groupby("year", observed=True).size()
    top_year_share_pct = float(by_year_n.max() / n * 100.0) if n else float("nan")
    boot_p10, boot_prob = _bootstrap_stats(returns, rng)

    metrics = {
        "cost_stressed_mean_bps": float(np.nanmean(returns)),
        "context_benchmark_cost_adjusted_mean_bps": float(bench),
        "context_benchmark_cost_adjusted_residual_bps": residual,
        "train_cost_mean_bps": float(np.nanmean(train)),
        "oos_cost_mean_bps": float(np.nanmean(oos)),
        "median_mae_bps": float(np.nanmedian(mae)),
        "median_mfe_bps": float(np.nanmedian(mfe)),
        "touch_stop_50bps_pct": _pct(touch50),
        "touch_stop_75bps_pct": _pct(touch75),
        "oos_touch_stop_50bps_pct": _pct(oos_touch50),
        "worst_quarter_slip16_mean_bps": worst_quarter_slip16,
        "positive_quarter_pct": pos_quarter_pct,
        "boot_p10_bps": boot_p10,
        "boot_prob_mean_gt_0_pct": boot_prob,
        "top_year_event_share_pct": top_year_share_pct,
    }

    failed: List[str] = []
    if metrics["cost_stressed_mean_bps"] <= 12.0:
        failed.append("cost_mean_gt_12")
    if metrics["context_benchmark_cost_adjusted_residual_bps"] <= 3.0:
        failed.append("residual_gt_3")
    if metrics["train_cost_mean_bps"] <= 0.0:
        failed.append("train_gt_0")
    if metrics["oos_cost_mean_bps"] <= 0.0:
        failed.append("oos_gt_0")
    if metrics["worst_quarter_slip16_mean_bps"] <= -20.0:
        failed.append("worst_quarter_slip16_gt_minus20")
    if metrics["boot_p10_bps"] <= -5.0:
        failed.append("boot_p10_gt_minus5")
    if metrics["boot_prob_mean_gt_0_pct"] <= 65.0:
        failed.append("boot_prob_gt_65")
    if metrics["positive_quarter_pct"] < 45.0:
        failed.append("positive_quarter_pct_ge_45")
    if metrics["top_year_event_share_pct"] > 38.0:
        failed.append("top_year_event_share_le_38")
    if metrics["oos_touch_stop_50bps_pct"] > 65.0:
        failed.append("oos_touch50_le_65")

    strict = not failed
    soft_failed_allowed = {"cost_mean_gt_12", "residual_gt_3", "boot_p10_gt_minus5"}
    soft = (not strict) and set(failed).issubset(soft_failed_allowed) and metrics["train_cost_mean_bps"] > 0 and metrics["oos_cost_mean_bps"] > 0

    if strict:
        classification = CLASS_STRICT
    elif soft:
        classification = CLASS_SOFT
    else:
        classification = CLASS_FAIL

    base_row.update(metrics)
    base_row.update({
        "classification": classification,
        "failed_reasons": ";".join(failed) if failed else "",
    })
    return base_row, event_df


def _evaluate_all(
    df: pd.DataFrame,
    specs: Sequence[ThesisSpec],
    cost_bps: float,
    slip_bps: float,
    min_events: int,
    seed: int,
) -> Tuple[pd.DataFrame, pd.DataFrame, List[str]]:
    rows: List[Dict[str, object]] = []
    event_frames: List[pd.DataFrame] = []
    errors: List[str] = []
    rng = np.random.default_rng(seed)
    benchmark_cache: Dict[Tuple[int, str], float] = {}
    for spec in specs:
        try:
            row, events = _evaluate_candidate(df, spec, cost_bps, slip_bps, min_events, rng, benchmark_cache)
            rows.append(row)
            if not events.empty:
                event_frames.append(events)
        except Exception as exc:  # keep scan alive; error rows remain research-only
            rows.append({
                "stage": STAGE_NAME,
                "family": spec.family,
                "candidate": spec.candidate,
                "side": spec.side,
                "horizon_bars": int(spec.horizon_bars),
                "horizon_minutes": int(spec.horizon_bars * df.attrs.get("timeframe_minutes", 15)),
                "event_clock_n": 0,
                "classification": CLASS_ERROR,
                "failed_reasons": type(exc).__name__,
                "description": spec.description,
            })
            errors.append(f"{spec.candidate}/{spec.horizon_bars}: {type(exc).__name__}: {exc}")
    candidates = pd.DataFrame(rows)
    if not candidates.empty:
        sort_cols = ["classification", "cost_stressed_mean_bps", "event_clock_n"]
        for c in sort_cols:
            if c not in candidates.columns:
                candidates[c] = np.nan
        candidates = candidates.sort_values(sort_cols, ascending=[True, False, False]).reset_index(drop=True)
    events_all = pd.concat(event_frames, ignore_index=True) if event_frames else pd.DataFrame()
    return candidates, events_all, errors


def _json_default(obj: object) -> object:
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        if not np.isfinite(obj):
            return None
        return float(obj)
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    return str(obj)


def _write_outputs(
    outdir: Path,
    candidates: pd.DataFrame,
    events: pd.DataFrame,
    summary: Dict[str, object],
) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    candidates_path = outdir / "stage43_parallel_context_regime_megascan_v4_candidates.csv"
    events_path = outdir / "stage43_parallel_context_regime_megascan_v4_events.csv"
    summary_path = outdir / "stage43_parallel_context_regime_megascan_v4_summary.json"
    md_path = outdir / "stage43_parallel_context_regime_megascan_v4.md"

    candidates.to_csv(candidates_path, index=False)
    events.to_csv(events_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=_json_default), encoding="utf-8")

    class_counts = candidates["classification"].value_counts(dropna=False).to_dict() if not candidates.empty else {}
    top_cols = [
        "classification", "family", "candidate", "side", "horizon_minutes", "event_clock_n",
        "cost_stressed_mean_bps", "context_benchmark_cost_adjusted_residual_bps",
        "train_cost_mean_bps", "oos_cost_mean_bps", "worst_quarter_slip16_mean_bps",
        "boot_p10_bps", "oos_touch_stop_50bps_pct", "top_year_event_share_pct", "failed_reasons",
    ]
    top = candidates.copy()
    for c in top_cols:
        if c not in top.columns:
            top[c] = np.nan
    top = top.sort_values(["classification", "cost_stressed_mean_bps"], ascending=[True, False]).head(45)[top_cols]

    md = []
    md.append(f"# {STAGE_NAME}\n")
    md.append("## Decision\n")
    md.append("```text\npromotion = NO_GO\nEA = NO_GO\npaper_live = NO_GO\nlive = NO_GO\n```\n")
    md.append("Stage43 is a context/regime research scan only. Strict/soft rows are watch-only and require a separate Stage43B path-stability/promotion audit before any operational layer is considered.\n")
    md.append("## Input data\n")
    data = summary.get("data", {})
    md.append("```text\n" + "\n".join(f"{k}: {v}" for k, v in data.items() if k in ["db_path", "table", "source", "symbol", "timeframe", "timeframe_normalized", "timeframe_minutes", "loaded_rows", "loaded_start", "loaded_end"]) + "\n```\n")
    md.append("## Thesis families scanned\n")
    for fam in summary.get("families_scanned", []):
        md.append(f"- `{fam}`")
    md.append("\n## Classification counts\n")
    md.append("```text\n" + "\n".join(f"{k}: {v}" for k, v in class_counts.items()) + "\n```\n")
    md.append("## Top rows by classification then cost mean\n")
    if top.empty:
        md.append("No candidate rows were generated.\n")
    else:
        md.append(top.to_markdown(index=False))
    md.append("\n## Anti-overfit note\n")
    md.append("Do not rescue failed Stage43 rows by removing weak hours, months, years, quarters, volatility states, or stop-touch buckets after seeing this output. A later Stage43B may audit only pre-existing strict/soft shortlist rows with predefined path-stability, slip, LOYO, concentration, and OOS gates.\n")
    md_path.write_text("\n".join(md), encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=STAGE_NAME)
    p.add_argument("--db", default=str(DEFAULT_DB), help="SQLite DB path")
    p.add_argument("--table", default=DEFAULT_TABLE, help="SQLite table name")
    p.add_argument("--source", default=DEFAULT_SOURCE, help="Source filter")
    p.add_argument("--symbol", default=DEFAULT_SYMBOL, help="Symbol filter")
    p.add_argument("--timeframe", default=DEFAULT_TIMEFRAME, help="Timeframe filter, default M15")
    p.add_argument("--outdir", default=str(DEFAULT_OUTDIR), help="Output directory")
    p.add_argument("--cost-bps", type=float, default=8.0, help="Cost assumption deducted from every event return")
    p.add_argument("--slip-bps", type=float, default=16.0, help="Additional slippage stress for quarter stability")
    p.add_argument("--min-events", type=int, default=120, help="Minimum event-clock samples for classification")
    p.add_argument("--seed", type=int, default=43043, help="Bootstrap RNG seed")
    return p


def run(args: argparse.Namespace) -> int:
    df, meta = _read_sqlite_bars(
        db_path=Path(args.db),
        table=args.table,
        source=args.source,
        symbol=args.symbol,
        timeframe=args.timeframe,
    )
    tf_minutes = int(meta["timeframe_minutes"])
    feat = _add_features(df, tf_minutes)
    feat.attrs["timeframe_minutes"] = tf_minutes
    feat.attrs["derived_bars"] = feat.attrs.get("derived_bars", {})
    feat, specs = _add_candidate_masks(feat)
    feat.attrs["timeframe_minutes"] = tf_minutes

    candidates, events, errors = _evaluate_all(
        feat,
        specs,
        cost_bps=float(args.cost_bps),
        slip_bps=float(args.slip_bps),
        min_events=int(args.min_events),
        seed=int(args.seed),
    )

    strict_count = int((candidates.get("classification") == CLASS_STRICT).sum()) if not candidates.empty else 0
    soft_count = int((candidates.get("classification") == CLASS_SOFT).sum()) if not candidates.empty else 0
    class_counts = candidates["classification"].value_counts(dropna=False).to_dict() if not candidates.empty else {}
    families = sorted({s.family for s in specs})

    summary = {
        "stage": STAGE_NAME,
        "data": meta,
        "settings": {
            "cost_bps": float(args.cost_bps),
            "slip_bps": float(args.slip_bps),
            "min_events": int(args.min_events),
            "event_clock": "candidate-specific min_gap equals horizon_bars",
            "train_oos_split": "chronological 70/30 event-clock split",
            "context_regime_inputs": "HTF trend proxy, volatility state, session context, prior-day location/range, Asia range, compression/expansion",
            "derived_bars": feat.attrs.get("derived_bars", {}),
        },
        "families_scanned": families,
        "candidate_rows": int(len(candidates)),
        "events_rows_written": int(len(events)),
        "strict_stage43_context_regime_scan_watch_count": strict_count,
        "soft_stage43_context_regime_scan_watch_count": soft_count,
        "classification_counts": {str(k): int(v) for k, v in class_counts.items()},
        "errors": errors,
        **NO_PROMOTION_STATE,
        "next_allowed_step": "Stage43B_STRICT_SHORTLIST_PATH_STABILITY_AUDIT only if strict_stage43_context_regime_scan_watch_count > 0; otherwise archive Stage43 or start new thesis families.",
    }
    _write_outputs(Path(args.outdir), candidates, events, summary)
    print(json.dumps({
        "stage": STAGE_NAME,
        "candidate_rows": int(len(candidates)),
        "events_rows_written": int(len(events)),
        "strict_watch_count": strict_count,
        "soft_watch_count": soft_count,
        "promotion": "NO_GO",
        "outdir": str(args.outdir),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(build_arg_parser().parse_args()))
