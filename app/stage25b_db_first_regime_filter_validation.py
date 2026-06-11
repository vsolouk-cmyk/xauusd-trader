#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage25B DB-First Regime Filter Validation — Hotfix 1

Purpose:
- Use SQLite local store as the candle source of truth.
- Do NOT fall back to AMarkets CSV.
- Introspect SQLite schema to find OHLC candle tables, instead of assuming one fixed table name.
- Validate Stage25A regime/no-trade filter candidates on Stage23C exact trades using DB-derived features.

Research/shadow diagnostic only:
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "data" / "reports" / "stage25b_db_first_regime_filter_validation"
REPORT_MD = REPORT_DIR / "stage25b_db_first_regime_filter_validation.md"
REPORT_JSON = REPORT_DIR / "stage25b_db_first_regime_filter_validation.json"
FILTER_CSV = REPORT_DIR / "stage25b_filter_candidates.csv"
ENRICHED_TRADES_CSV = REPORT_DIR / "stage25b_enriched_stage23c_trades.csv"
COMPARISON_CSV = REPORT_DIR / "stage25b_stage25a_comparison.csv"
SCHEMA_CSV = REPORT_DIR / "stage25b_db_schema_diagnostic.csv"

DEFAULT_DB = ROOT / "data" / "local" / "xauusd_local_store.sqlite"
DEFAULT_TRADES = ROOT / "data" / "reports" / "stage23c_promotion_candidate_validation" / "stage23c_exact_trades.csv"
DEFAULT_STAGE25A_FILTERS = ROOT / "data" / "reports" / "stage25a_regime_filter_discovery" / "stage25a_filter_candidates.csv"

ROUNDTRIP_COST_X1 = 0.35


class DBFirstLoaderError(RuntimeError):
    pass


def env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    if raw:
        return Path(raw).expanduser()
    return default


def safe_json_default(v: Any) -> Any:
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        if np.isfinite(v):
            return float(v)
        return str(v)
    if isinstance(v, (np.ndarray,)):
        return v.tolist()
    if isinstance(v, (pd.Timestamp,)):
        return v.isoformat()
    return str(v)


def ensure_report_dir() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)


def sql_quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def list_sqlite_schema(conn: sqlite3.Connection) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    tables = pd.read_sql_query(
        "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') ORDER BY name",
        conn,
    )
    for _, trow in tables.iterrows():
        name = str(trow["name"])
        if name.startswith("sqlite_"):
            continue
        try:
            info = pd.read_sql_query(f"PRAGMA table_info({sql_quote(name)})", conn)
            try:
                cnt = pd.read_sql_query(f"SELECT COUNT(*) AS n FROM {sql_quote(name)}", conn)["n"].iloc[0]
            except Exception:
                cnt = None
            for _, crow in info.iterrows():
                rows.append(
                    {
                        "table": name,
                        "type": trow["type"],
                        "row_count": cnt,
                        "column": str(crow["name"]),
                        "declared_type": str(crow.get("type", "")),
                    }
                )
        except Exception as exc:
            rows.append(
                {
                    "table": name,
                    "type": trow["type"],
                    "row_count": None,
                    "column": f"<PRAGMA_ERROR:{type(exc).__name__}:{exc}>",
                    "declared_type": "",
                }
            )
    return pd.DataFrame(rows)


def norm_col(c: str) -> str:
    return (
        str(c)
        .strip()
        .lower()
        .replace("<", "")
        .replace(">", "")
        .replace(" ", "_")
        .replace("-", "_")
        .replace(".", "_")
    )


def choose_col(columns: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    mapping = {norm_col(c): c for c in columns}
    for cand in candidates:
        if norm_col(cand) in mapping:
            return mapping[norm_col(cand)]
    # relaxed: exact suffix/prefix
    for cand in candidates:
        nc = norm_col(cand)
        for k, original in mapping.items():
            if k == nc or k.endswith("_" + nc) or k.startswith(nc + "_"):
                return original
    return None


TIME_COLS = [
    "timestamp", "time", "datetime", "date_time", "bar_time", "broker_time", "broker_time_utc",
    "utc_time", "open_time", "start_time", "candle_time", "ts", "t"
]
DATE_COLS = ["date", "dt"]
TIME_ONLY_COLS = ["time_only", "clock", "hour_time"]
OPEN_COLS = ["open", "o", "bid_open", "ask_open", "mid_open"]
HIGH_COLS = ["high", "h", "bid_high", "ask_high", "mid_high"]
LOW_COLS = ["low", "l", "bid_low", "ask_low", "mid_low"]
CLOSE_COLS = ["close", "c", "bid_close", "ask_close", "mid_close"]
TF_COLS = ["timeframe", "tf", "interval", "granularity", "frame"]
SYMBOL_COLS = ["symbol", "instrument", "pair"]


@dataclass
class CandleLoadResult:
    df: pd.DataFrame
    table: str
    mode: str
    time_col: str
    open_col: str
    high_col: str
    low_col: str
    close_col: str
    timeframe_col: Optional[str] = None
    timeframe_value: Optional[str] = None
    symbol_col: Optional[str] = None


def parse_timestamp_series(s: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s):
        # seconds/ms/us/ns inference
        vals = pd.to_numeric(s, errors="coerce")
        finite = vals.dropna()
        if finite.empty:
            return pd.to_datetime(s, errors="coerce", utc=True)
        med = float(finite.abs().median())
        if med > 1e17:
            unit = "ns"
        elif med > 1e14:
            unit = "us"
        elif med > 1e11:
            unit = "ms"
        else:
            unit = "s"
        return pd.to_datetime(vals, errors="coerce", unit=unit, utc=True)
    return pd.to_datetime(s, errors="coerce", utc=True)


def normalize_ohlc_df(df: pd.DataFrame, table: str, mode: str, cols: Dict[str, Optional[str]], tf_value: Optional[str]) -> CandleLoadResult:
    if df.empty:
        raise DBFirstLoaderError(f"Candidate candle table {table} returned zero rows.")

    time_col = cols["time"]
    open_col = cols["open"]
    high_col = cols["high"]
    low_col = cols["low"]
    close_col = cols["close"]
    if not all([time_col, open_col, high_col, low_col, close_col]):
        raise DBFirstLoaderError(f"Table {table} does not have recognizable OHLC/time columns.")

    out = pd.DataFrame()
    out["timestamp"] = parse_timestamp_series(df[time_col])
    out["open"] = pd.to_numeric(df[open_col], errors="coerce")
    out["high"] = pd.to_numeric(df[high_col], errors="coerce")
    out["low"] = pd.to_numeric(df[low_col], errors="coerce")
    out["close"] = pd.to_numeric(df[close_col], errors="coerce")

    # Preserve optional volume/spread when available.
    for optional in ["tick_volume", "tickvol", "volume", "vol", "spread"]:
        col = choose_col(df.columns, [optional])
        if col and col not in out.columns:
            out[norm_col(optional)] = pd.to_numeric(df[col], errors="coerce")

    out = out.dropna(subset=["timestamp", "open", "high", "low", "close"])
    out = out.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    if out.empty:
        raise DBFirstLoaderError(f"Table {table} had OHLC columns but all rows became invalid after timestamp/OHLC parsing.")

    return CandleLoadResult(
        df=out,
        table=table,
        mode=mode,
        time_col=str(time_col),
        open_col=str(open_col),
        high_col=str(high_col),
        low_col=str(low_col),
        close_col=str(close_col),
        timeframe_col=cols.get("tf"),
        timeframe_value=tf_value,
        symbol_col=cols.get("symbol"),
    )


def table_name_suggests_tf(table: str, tf: str) -> bool:
    t = norm_col(table)
    tf = tf.lower()
    if tf == "m1":
        needles = ["m1", "1m", "minute1", "one_min", "1_min"]
    elif tf == "h1":
        needles = ["h1", "1h", "hour1", "one_hour", "1_hour"]
    else:
        needles = [tf]
    return any(n in t for n in needles)


def frame_matches_tf_value(v: Any, tf: str) -> bool:
    if pd.isna(v):
        return False
    s = str(v).strip().lower()
    if tf == "m1":
        return s in {"m1", "1m", "1min", "1_min", "minute", "1", "60", "60s"}
    if tf == "h1":
        return s in {"h1", "1h", "1hour", "1_hour", "hour", "60m", "3600", "3600s"}
    return s == tf.lower()


def symbol_where_clause(col: Optional[str]) -> Tuple[str, List[Any]]:
    # Keep broad by default. If symbol column exists, prefer XAU-like symbols but do not hard fail.
    if not col:
        return "", []
    return f" AND (UPPER({sql_quote(col)}) LIKE '%XAU%' OR UPPER({sql_quote(col)}) LIKE '%GOLD%') ", []


def load_candles_from_db(conn: sqlite3.Connection, schema_df: pd.DataFrame, tf: str) -> CandleLoadResult:
    if schema_df.empty:
        raise DBFirstLoaderError("SQLite DB has no user tables/views.")

    grouped = schema_df.groupby("table")
    candidates: List[Tuple[int, str, Dict[str, Optional[str]]]] = []

    for table, g in grouped:
        cols = list(g["column"].astype(str))
        if not cols:
            continue
        c_time = choose_col(cols, TIME_COLS)
        c_open = choose_col(cols, OPEN_COLS)
        c_high = choose_col(cols, HIGH_COLS)
        c_low = choose_col(cols, LOW_COLS)
        c_close = choose_col(cols, CLOSE_COLS)
        c_tf = choose_col(cols, TF_COLS)
        c_symbol = choose_col(cols, SYMBOL_COLS)

        # If no unified timestamp, try date+time in SQL later only if both exist.
        c_date = choose_col(cols, DATE_COLS)
        c_time_only = choose_col(cols, TIME_ONLY_COLS + ["time"])

        has_ohlc = all([c_open, c_high, c_low, c_close])
        has_time = bool(c_time) or bool(c_date and c_time_only)
        if not (has_ohlc and has_time):
            continue

        score = 0
        if table_name_suggests_tf(table, tf):
            score += 50
        if c_tf:
            score += 30
        if c_symbol:
            score += 5
        row_count = g["row_count"].dropna()
        if not row_count.empty:
            try:
                n = int(row_count.iloc[0])
                if tf == "m1" and n > 100000:
                    score += 15
                if tf == "h1" and 1000 < n < 200000:
                    score += 10
            except Exception:
                pass

        candidates.append(
            (
                score,
                table,
                {
                    "time": c_time,
                    "date": c_date,
                    "time_only": c_time_only,
                    "open": c_open,
                    "high": c_high,
                    "low": c_low,
                    "close": c_close,
                    "tf": c_tf,
                    "symbol": c_symbol,
                },
            )
        )

    errors: List[str] = []
    for _, table, cols in sorted(candidates, key=lambda x: x[0], reverse=True):
        try:
            select_parts: List[str] = []
            generated_time_alias = None
            if cols["time"]:
                select_parts.append(f"{sql_quote(cols['time'])} AS __time")
                time_key = "__time"
            else:
                # Combine DATE and TIME columns if needed.
                select_parts.append(
                    f"({sql_quote(cols['date'])} || ' ' || {sql_quote(cols['time_only'])}) AS __time"
                )
                time_key = "__time"
                generated_time_alias = "__time"

            for key in ["open", "high", "low", "close"]:
                select_parts.append(f"{sql_quote(cols[key])} AS __{key}")

            if cols.get("tf"):
                select_parts.append(f"{sql_quote(cols['tf'])} AS __tf")
            if cols.get("symbol"):
                select_parts.append(f"{sql_quote(cols['symbol'])} AS __symbol")

            where = " WHERE 1=1 "
            params: List[Any] = []
            tf_value = None
            if cols.get("tf"):
                # Try broad matching inside SQL.
                tf_col = sql_quote(cols["tf"])
                if tf == "m1":
                    values = ["M1", "m1", "1m", "1M", "1min", "1_min", "minute", "1", "60", "60s"]
                else:
                    values = ["H1", "h1", "1h", "1H", "1hour", "1_hour", "hour", "60m", "3600", "3600s"]
                placeholders = ",".join(["?"] * len(values))
                where += f" AND CAST({tf_col} AS TEXT) IN ({placeholders}) "
                params.extend(values)
                tf_value = "|".join(values)
            elif not table_name_suggests_tf(table, tf):
                # No timeframe column and table name does not indicate the requested frame. Try it later only if no better table works.
                pass

            sym_clause, sym_params = symbol_where_clause(cols.get("symbol"))
            where += sym_clause
            params.extend(sym_params)

            sql = f"SELECT {', '.join(select_parts)} FROM {sql_quote(table)} {where}"
            raw = pd.read_sql_query(sql, conn, params=params)

            # If symbol filter returned zero, retry without symbol filter.
            if raw.empty and cols.get("symbol"):
                where2 = where.replace(sym_clause, "")
                sql2 = f"SELECT {', '.join(select_parts)} FROM {sql_quote(table)} {where2}"
                raw = pd.read_sql_query(sql2, conn, params=params[: len(params) - len(sym_params)])

            if raw.empty:
                # If tf filter returned zero, retry without tf filter only when table name indicates tf.
                if cols.get("tf") and table_name_suggests_tf(table, tf):
                    select_no_tf = [p for p in select_parts]
                    sql3 = f"SELECT {', '.join(select_no_tf)} FROM {sql_quote(table)}"
                    raw = pd.read_sql_query(sql3, conn)
                else:
                    errors.append(f"{table}: zero rows for tf={tf}")
                    continue

            # Normalize alias names.
            alias_map = {
                "__time": "__time",
                "__open": "__open",
                "__high": "__high",
                "__low": "__low",
                "__close": "__close",
            }
            raw_cols = {
                "__time": "__time",
                "__open": "__open",
                "__high": "__high",
                "__low": "__low",
                "__close": "__close",
                "__tf": "__tf" if "__tf" in raw.columns else None,
                "__symbol": "__symbol" if "__symbol" in raw.columns else None,
            }
            # If table has tf column but broad SQL pulled more than requested somehow, filter in Python.
            if raw_cols["__tf"]:
                mask = raw["__tf"].apply(lambda v: frame_matches_tf_value(v, tf))
                if mask.any():
                    raw = raw.loc[mask].copy()

            normalized = normalize_ohlc_df(
                raw,
                table=table,
                mode="db_schema_introspection",
                cols={
                    "time": "__time",
                    "open": "__open",
                    "high": "__high",
                    "low": "__low",
                    "close": "__close",
                    "tf": cols.get("tf"),
                    "symbol": cols.get("symbol"),
                },
                tf_value=tf_value,
            )

            # Sanity by expected granularity.
            if tf == "m1" and len(normalized.df) < 10000:
                errors.append(f"{table}: only {len(normalized.df)} rows for M1; rejected as too small")
                continue
            if tf == "h1" and len(normalized.df) < 500:
                errors.append(f"{table}: only {len(normalized.df)} rows for H1; rejected as too small")
                continue

            return normalized

        except Exception as exc:
            errors.append(f"{table}: {type(exc).__name__}: {exc}")

    sample = ""
    if not schema_df.empty:
        overview = (
            schema_df.groupby("table")
            .agg(row_count=("row_count", "first"), columns=("column", lambda x: ", ".join(map(str, list(x)[:20]))))
            .reset_index()
            .head(20)
        )
        sample = overview.to_string(index=False)

    raise DBFirstLoaderError(
        f"No {tf.upper()} OHLC candles found in SQLite DB using schema introspection. "
        f"CSV fallback is intentionally disabled.\n\n"
        f"Attempted tables/errors:\n- " + "\n- ".join(errors[:30]) + "\n\n"
        f"Schema sample:\n{sample}"
    )


def resample_m1_to_m15(m1: pd.DataFrame) -> pd.DataFrame:
    x = m1.set_index("timestamp").sort_index()
    out = x.resample("15min").agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    out = out.dropna().reset_index()
    return out


def read_trades(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Stage23C exact trades file not found: {path}")

    df = pd.read_csv(path)
    if df.empty:
        raise DBFirstLoaderError(f"Stage23C exact trades file is empty: {path}")

    cols = {norm_col(c): c for c in df.columns}
    time_col = None
    for cand in ["entry_time", "timestamp", "entry_timestamp", "signal_time", "time"]:
        if norm_col(cand) in cols:
            time_col = cols[norm_col(cand)]
            break
    if not time_col:
        raise DBFirstLoaderError(f"No entry_time/timestamp column found in {path}. Columns={list(df.columns)}")

    direction_col = None
    for cand in ["direction", "side", "dir"]:
        if norm_col(cand) in cols:
            direction_col = cols[norm_col(cand)]
            break
    if not direction_col:
        raise DBFirstLoaderError(f"No direction column found in {path}. Columns={list(df.columns)}")

    out = df.copy()
    out["entry_time"] = pd.to_datetime(out[time_col], errors="coerce", utc=True)
    out["direction"] = out[direction_col].astype(str).str.lower().str.strip()

    for net_col, candidates in {
        "net_x1": ["net_x1", "x1", "ret_x1", "pnl_x1", "net"],
        "net_x4": ["net_x4", "x4", "ret_x4", "pnl_x4"],
        "net_x6": ["net_x6", "x6", "ret_x6", "pnl_x6"],
    }.items():
        found = None
        for cand in candidates:
            if norm_col(cand) in cols:
                found = cols[norm_col(cand)]
                break
        if found:
            out[net_col] = pd.to_numeric(out[found], errors="coerce")
        else:
            # Derive stricter cost variants if only net_x1 exists.
            if net_col == "net_x4" and "net_x1" in out:
                out[net_col] = out["net_x1"] - 3 * ROUNDTRIP_COST_X1
            elif net_col == "net_x6" and "net_x1" in out:
                out[net_col] = out["net_x1"] - 5 * ROUNDTRIP_COST_X1
            else:
                raise DBFirstLoaderError(f"Missing required net column {net_col} in {path}. Columns={list(df.columns)}")

    out = out.dropna(subset=["entry_time", "net_x1", "net_x4", "net_x6"])
    if out.empty:
        raise DBFirstLoaderError("No valid Stage23C trades after parsing entry_time/net columns.")
    return out.reset_index(drop=True)


def profit_factor(values: Sequence[float]) -> float:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return 0.0
    gains = arr[arr > 0].sum()
    losses = -arr[arr < 0].sum()
    if losses <= 1e-12:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)


def metric_block(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {
            "events": 0,
            "pf_x1": 0.0,
            "pf_x4": 0.0,
            "pf_x6": 0.0,
            "total_x1": 0.0,
            "total_x4": 0.0,
            "total_x6": 0.0,
            "win_rate_x4": 0.0,
            "median_x4": 0.0,
        }
    return {
        "events": int(len(df)),
        "pf_x1": profit_factor(df["net_x1"]),
        "pf_x4": profit_factor(df["net_x4"]),
        "pf_x6": profit_factor(df["net_x6"]),
        "total_x1": float(df["net_x1"].sum()),
        "total_x4": float(df["net_x4"].sum()),
        "total_x6": float(df["net_x6"].sum()),
        "win_rate_x4": float((df["net_x4"] > 0).mean()),
        "median_x4": float(df["net_x4"].median()),
    }


def session_slice(df: pd.DataFrame, day: pd.Timestamp, start_hour: int, end_hour: int) -> pd.DataFrame:
    start = pd.Timestamp(year=day.year, month=day.month, day=day.day, tz="UTC") + pd.Timedelta(hours=start_hour)
    end = pd.Timestamp(year=day.year, month=day.month, day=day.day, tz="UTC") + pd.Timedelta(hours=end_hour)
    return df[(df["timestamp"] >= start) & (df["timestamp"] < end)]


def build_daily_features(m15: pd.DataFrame) -> pd.DataFrame:
    x = m15.copy()
    x["day"] = x["timestamp"].dt.floor("D")
    rows: List[Dict[str, Any]] = []
    for day, g in x.groupby("day", sort=True):
        if g.empty:
            continue
        asia = session_slice(x, day, 0, 7)
        london = session_slice(x, day, 7, 13)
        early_ny = session_slice(x, day, 13, 16)

        def rng(s: pd.DataFrame) -> float:
            if s.empty:
                return np.nan
            return float(s["high"].max() - s["low"].min())

        def move(s: pd.DataFrame) -> float:
            if s.empty:
                return np.nan
            return float(s["close"].iloc[-1] - s["open"].iloc[0])

        def eff(s: pd.DataFrame) -> float:
            r = rng(s)
            if not np.isfinite(r) or r <= 1e-12 or s.empty:
                return np.nan
            return abs(move(s)) / r

        daily_open = float(g["open"].iloc[0])
        daily_close = float(g["close"].iloc[-1])
        daily_high = float(g["high"].max())
        daily_low = float(g["low"].min())
        daily_range = daily_high - daily_low
        day_move = daily_close - daily_open

        london_move = move(london)
        prior_placeholder = np.nan

        rows.append(
            {
                "day": day,
                "daily_open": daily_open,
                "daily_close": daily_close,
                "daily_high": daily_high,
                "daily_low": daily_low,
                "daily_range": daily_range,
                "day_move": day_move,
                "day_dir": np.sign(day_move),
                "asia_range": rng(asia),
                "asia_move": move(asia),
                "asia_dir": np.sign(move(asia)) if np.isfinite(move(asia)) else np.nan,
                "london_range": rng(london),
                "london_move": london_move,
                "london_dir": np.sign(london_move) if np.isfinite(london_move) else np.nan,
                "london_eff": eff(london),
                "early_ny_range": rng(early_ny),
                "early_ny_move": move(early_ny),
                "early_ny_dir": np.sign(move(early_ny)) if np.isfinite(move(early_ny)) else np.nan,
            }
        )

    feat = pd.DataFrame(rows).sort_values("day")
    feat["prior_day_range"] = feat["daily_range"].shift(1)
    feat["prior_day_move"] = feat["day_move"].shift(1)
    feat["prior_day_dir"] = feat["day_dir"].shift(1)
    return feat


def enrich_trades(trades: pd.DataFrame, m15: pd.DataFrame) -> pd.DataFrame:
    feat = build_daily_features(m15)
    out = trades.copy()
    out["day"] = out["entry_time"].dt.floor("D")
    out["trade_dir_num"] = np.where(out["direction"].str.contains("short"), -1, 1)
    enriched = out.merge(feat, on="day", how="left")
    enriched["london_aligned"] = enriched["trade_dir_num"] == enriched["london_dir"]
    enriched["prior_day_aligned"] = enriched["trade_dir_num"] == enriched["prior_day_dir"]
    enriched["entry_hour"] = enriched["entry_time"].dt.hour
    return enriched


def percentile_filter(df: pd.DataFrame, col: str, kind: str, pct: float) -> pd.Series:
    s = pd.to_numeric(df[col], errors="coerce")
    if s.notna().sum() < 20:
        return pd.Series(False, index=df.index)
    if kind == "drop_low":
        q = s.quantile(pct)
        return s >= q
    if kind == "drop_high":
        q = s.quantile(1.0 - pct)
        return s <= q
    if kind == "middle":
        lo = s.quantile(pct)
        hi = s.quantile(1.0 - pct)
        return (s >= lo) & (s <= hi)
    raise ValueError(kind)


def candidate_filters(df: pd.DataFrame) -> List[Tuple[str, pd.Series]]:
    filters: List[Tuple[str, pd.Series]] = []
    filters.append(("keep_short_only", df["trade_dir_num"] < 0))
    filters.append(("keep_long_only", df["trade_dir_num"] > 0))
    filters.append(("keep_london_aligned", df["london_aligned"].fillna(False)))
    filters.append(("drop_london_aligned", ~df["london_aligned"].fillna(False)))
    filters.append(("keep_prior_day_aligned", df["prior_day_aligned"].fillna(False)))
    filters.append(("drop_prior_day_aligned", ~df["prior_day_aligned"].fillna(False)))
    filters.append(("keep_entry_hour_13", df["entry_hour"] == 13))
    filters.append(("drop_entry_hour_13", df["entry_hour"] != 13))

    for col in ["prior_day_range", "asia_range", "london_range", "early_ny_range", "london_eff"]:
        if col not in df.columns:
            continue
        for pct in [0.20, 0.30]:
            filters.append((f"{col}_drop_low{int(pct*100)}", percentile_filter(df, col, "drop_low", pct)))
            filters.append((f"{col}_drop_high{int(pct*100)}", percentile_filter(df, col, "drop_high", pct)))
            filters.append((f"{col}_middle_{int(pct*100)}_{int((1-pct)*100)}", percentile_filter(df, col, "middle", pct)))

    # Diagnostic only: year drops, never operational.
    years = sorted(df["entry_time"].dt.year.dropna().astype(int).unique().tolist())
    for y in years:
        filters.append((f"diagnostic_drop_year_{y}", df["entry_time"].dt.year != y))

    return filters


def evaluate_filters(enriched: pd.DataFrame, base: Dict[str, Any]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    n = len(enriched)
    base_pf4 = float(base.get("pf_x4", 0.0))
    base_pf6 = float(base.get("pf_x6", 0.0))

    for name, mask in candidate_filters(enriched):
        mask = mask.fillna(False)
        kept = enriched.loc[mask].copy()
        if kept.empty:
            continue
        retained = len(kept) / max(1, n)
        m = metric_block(kept)
        improvement_pf4 = m["pf_x4"] - base_pf4
        improvement_pf6 = m["pf_x6"] - base_pf6

        is_diag = name.startswith("diagnostic_")
        candidate = (
            not is_diag
            and m["events"] >= 40
            and 0.25 <= retained <= 0.90
            and m["pf_x4"] >= max(1.25, base_pf4 + 0.25)
            and m["pf_x6"] >= max(1.05, base_pf6 + 0.10)
            and m["total_x4"] > 0
        )
        decision = "STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY" if candidate else "STAGE25B_REJECT"
        rows.append(
            {
                "decision": decision,
                "filter_name": name,
                "retained_events": m["events"],
                "retained_ratio": retained,
                "pf_x1": m["pf_x1"],
                "pf_x4": m["pf_x4"],
                "pf_x6": m["pf_x6"],
                "improvement_pf_x4": improvement_pf4,
                "improvement_pf_x6": improvement_pf6,
                "total_x4": m["total_x4"],
                "win_rate_x4": m["win_rate_x4"],
                "median_x4": m["median_x4"],
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["_rank"] = (
        (out["decision"].eq("STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY").astype(int) * 1000)
        + out["pf_x4"].replace(np.inf, 999).fillna(0) * 10
        + out["pf_x6"].replace(np.inf, 999).fillna(0) * 5
        + out["total_x4"].fillna(0) / 1000
    )
    out = out.sort_values("_rank", ascending=False).drop(columns=["_rank"]).reset_index(drop=True)
    return out


def compare_stage25a(stage25b: pd.DataFrame, stage25a_path: Path) -> pd.DataFrame:
    if not stage25a_path.exists() or stage25b.empty:
        return pd.DataFrame()
    try:
        a = pd.read_csv(stage25a_path)
    except Exception:
        return pd.DataFrame()

    if "filter_name" not in a.columns:
        return pd.DataFrame()

    keep_cols = [c for c in ["filter_name", "pf_x4", "pf_x6", "retained_events", "total_x4"] if c in a.columns]
    a = a[keep_cols].rename(columns={c: f"stage25a_{c}" for c in keep_cols if c != "filter_name"})
    b = stage25b[[c for c in ["filter_name", "pf_x4", "pf_x6", "retained_events", "total_x4", "decision"] if c in stage25b.columns]].copy()
    b = b.rename(columns={c: f"stage25b_{c}" for c in ["pf_x4", "pf_x6", "retained_events", "total_x4"] if c in b.columns})
    merged = b.merge(a, on="filter_name", how="left")
    if "stage25a_pf_x4" in merged.columns:
        merged["delta_pf_x4_b_minus_a"] = merged["stage25b_pf_x4"] - pd.to_numeric(merged["stage25a_pf_x4"], errors="coerce")
    if "stage25a_pf_x6" in merged.columns:
        merged["delta_pf_x6_b_minus_a"] = merged["stage25b_pf_x6"] - pd.to_numeric(merged["stage25a_pf_x6"], errors="coerce")
    return merged


def fmt(v: Any) -> str:
    if isinstance(v, (list, tuple, set)):
        return ", ".join(map(str, v))
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False, default=safe_json_default)
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass
    if isinstance(v, float):
        if math.isinf(v):
            return "inf"
        return f"{v:.4f}".rstrip("0").rstrip(".")
    return str(v)


def markdown_table(df: pd.DataFrame, cols: Sequence[str], max_rows: int = 30) -> str:
    if df is None or df.empty:
        return "No rows."
    show = df.loc[:, [c for c in cols if c in df.columns]].head(max_rows)
    header = "| " + " | ".join(show.columns) + " |"
    sep = "| " + " | ".join(["---"] * len(show.columns)) + " |"
    rows = ["| " + " | ".join(fmt(row[c]) for c in show.columns) + " |" for _, row in show.iterrows()]
    return "\n".join([header, sep] + rows)


def write_error_report(exc: BaseException, db_path: Optional[Path] = None, schema_df: Optional[pd.DataFrame] = None) -> None:
    ensure_report_dir()
    report = {
        "decision": "STAGE25B_ERROR_DIAGNOSTIC_ONLY",
        "error_type": type(exc).__name__,
        "error": str(exc),
        "db_path": str(db_path) if db_path else None,
        "scope": {
            "research_shadow_only": True,
            "stage18a_unchanged": True,
            "stage23d_unchanged": True,
            "no_ea_paper_live_orders": True,
            "csv_fallback_disabled": True,
        },
    }
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=safe_json_default), encoding="utf-8")

    lines = []
    lines.append("# Stage25B DB-First Regime Filter Validation")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    lines.append("STAGE25B_ERROR_DIAGNOSTIC_ONLY")
    lines.append("```")
    lines.append("")
    lines.append("## Error")
    lines.append("")
    lines.append("```text")
    lines.append(f"{type(exc).__name__}: {exc}")
    lines.append("```")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("- This is a diagnostic error, not an authorization change.")
    lines.append("- Stage18A v2 and Stage23D remain unchanged.")
    lines.append("- AMarkets CSV fallback is intentionally disabled in Stage25B.")
    lines.append("- Hotfix 1 uses SQLite schema introspection; if it still fails, inspect `stage25b_db_schema_diagnostic.csv`.")
    if schema_df is not None and not schema_df.empty:
        lines.append("")
        lines.append("## SQLite schema sample")
        overview = (
            schema_df.groupby("table")
            .agg(row_count=("row_count", "first"), columns=("column", lambda x: ", ".join(map(str, list(x)[:15]))))
            .reset_index()
            .head(20)
        )
        lines.append(markdown_table(overview, ["table", "row_count", "columns"], 20))

    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ensure_report_dir()
    db_path = env_path("STAGE25B_DB_PATH", DEFAULT_DB)
    trades_path = env_path("STAGE25B_TRADES_PATH", DEFAULT_TRADES)
    stage25a_path = env_path("STAGE25B_STAGE25A_FILTERS_PATH", DEFAULT_STAGE25A_FILTERS)

    schema_df: Optional[pd.DataFrame] = None
    try:
        if not db_path.exists():
            raise DBFirstLoaderError(f"SQLite DB not found: {db_path}")

        with sqlite3.connect(str(db_path)) as conn:
            schema_df = list_sqlite_schema(conn)
            schema_df.to_csv(SCHEMA_CSV, index=False)

            m1_res = load_candles_from_db(conn, schema_df, "m1")
            try:
                h1_res = load_candles_from_db(conn, schema_df, "h1")
            except Exception:
                # H1 can be derived from M1 if an explicit H1 table is absent.
                h1_df = (
                    m1_res.df.set_index("timestamp")
                    .resample("1h")
                    .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
                    .dropna()
                    .reset_index()
                )
                h1_res = CandleLoadResult(
                    df=h1_df,
                    table=f"{m1_res.table}__resampled_h1",
                    mode="derived_from_m1",
                    time_col="timestamp",
                    open_col="open",
                    high_col="high",
                    low_col="low",
                    close_col="close",
                )

        m1 = m1_res.df
        m15 = resample_m1_to_m15(m1)
        h1 = h1_res.df
        trades = read_trades(trades_path)
        enriched = enrich_trades(trades, m15)

        base = metric_block(enriched)
        filters = evaluate_filters(enriched, base)
        comparison = compare_stage25a(filters, stage25a_path)

        filters.to_csv(FILTER_CSV, index=False)
        enriched.to_csv(ENRICHED_TRADES_CSV, index=False)
        if not comparison.empty:
            comparison.to_csv(COMPARISON_CSV, index=False)
        else:
            pd.DataFrame().to_csv(COMPARISON_CSV, index=False)

        candidate_count = int((filters["decision"] == "STAGE25B_FILTER_CANDIDATE_REVIEW_ONLY").sum()) if not filters.empty else 0
        decision = (
            "STAGE25B_DB_FIRST_HAS_FILTER_CANDIDATE_REVIEW_ONLY"
            if candidate_count > 0
            else "STAGE25B_DB_FIRST_NO_FILTER_CANDIDATE_KEEP_RESEARCH_ONLY"
        )

        report = {
            "decision": decision,
            "scope": {
                "research_shadow_only": True,
                "stage18a_unchanged": True,
                "stage23d_unchanged": True,
                "no_ea_paper_live_orders": True,
                "csv_fallback_disabled": True,
            },
            "db": {
                "path": str(db_path),
                "m1_table": m1_res.table,
                "m1_mode": m1_res.mode,
                "m1_rows": int(len(m1)),
                "m1_span": [m1["timestamp"].min(), m1["timestamp"].max()],
                "h1_table": h1_res.table,
                "h1_mode": h1_res.mode,
                "h1_rows": int(len(h1)),
                "h1_span": [h1["timestamp"].min(), h1["timestamp"].max()],
                "m15_rows_derived": int(len(m15)),
                "m15_span": [m15["timestamp"].min(), m15["timestamp"].max()],
            },
            "trades": {
                "path": str(trades_path),
                "events": int(len(trades)),
            },
            "base_metrics": base,
            "filter_candidate_count": candidate_count,
            "stage25a_comparison_available": bool(not comparison.empty),
        }
        REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=safe_json_default), encoding="utf-8")

        lines: List[str] = []
        lines.append("# Stage25B DB-First Regime Filter Validation")
        lines.append("")
        lines.append("Generated UTC: `" + pd.Timestamp.utcnow().isoformat() + "`")
        lines.append("")
        lines.append("## Decision")
        lines.append("")
        lines.append("```text")
        lines.append(decision)
        lines.append("```")
        lines.append("")
        lines.append("## Scope guardrails")
        lines.append("")
        lines.append("- Research/shadow diagnostic only.")
        lines.append("- Stage18A v2 remains unchanged.")
        lines.append("- Stage23D remains unchanged.")
        lines.append("- No EA change, no automatic trading, no paper/live/order authorization.")
        lines.append("- AMarkets CSV fallback is intentionally disabled; candles are DB-first.")
        lines.append("")
        lines.append("## DB source of truth")
        lines.append("")
        lines.append(f"- db_path: `{db_path}`")
        lines.append(f"- m1_table: `{m1_res.table}`")
        lines.append(f"- m1_mode: `{m1_res.mode}`")
        lines.append(f"- m1_rows: `{len(m1)}`")
        lines.append(f"- m1_span: `{m1['timestamp'].min()} → {m1['timestamp'].max()}`")
        lines.append(f"- h1_table: `{h1_res.table}`")
        lines.append(f"- h1_mode: `{h1_res.mode}`")
        lines.append(f"- h1_rows: `{len(h1)}`")
        lines.append(f"- h1_span: `{h1['timestamp'].min()} → {h1['timestamp'].max()}`")
        lines.append(f"- m15_rows_derived_from_m1: `{len(m15)}`")
        lines.append("")
        lines.append("## Base Stage23C trade metrics, DB-derived features")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(base, ensure_ascii=False, indent=2, default=safe_json_default))
        lines.append("```")
        lines.append("")
        lines.append("## Top DB-first filter diagnostics")
        lines.append("")
        lines.append(markdown_table(
            filters,
            [
                "decision", "filter_name", "retained_events", "retained_ratio",
                "pf_x1", "pf_x4", "pf_x6", "improvement_pf_x4",
                "improvement_pf_x6", "total_x4", "win_rate_x4", "median_x4",
            ],
            35,
        ))
        if not comparison.empty:
            lines.append("")
            lines.append("## Stage25A vs Stage25B comparison")
            lines.append("")
            lines.append(markdown_table(
                comparison,
                [
                    "filter_name", "decision",
                    "stage25a_pf_x4", "stage25b_pf_x4", "delta_pf_x4_b_minus_a",
                    "stage25a_pf_x6", "stage25b_pf_x6", "delta_pf_x6_b_minus_a",
                    "stage25a_retained_events", "stage25b_retained_events",
                ],
                25,
            ))
        lines.append("")
        lines.append("## Interpretation")
        lines.append("")
        lines.append("- This module validates Stage25A-style filters using SQLite candles as source of truth.")
        lines.append("- Stage23C exact trade artifact is still used as the trade list; candle/regime features are rebuilt from DB.")
        lines.append("- Any filter candidate remains research-only and requires separate forward-shadow validation.")
        lines.append("- If filter candidates survive here, the next step is a DB-first filtered Stage23D tracker, not EA/paper/live.")
        lines.append("")
        lines.append("## Operational reminder")
        lines.append("")
        lines.append("```bash")
        lines.append("cd ~/Desktop/xauusd-trader")
        lines.append("python3 -m app.stage18a_unified_shadow_ops_cycle")
        lines.append("cat data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.md")
        lines.append("")
        lines.append("python3 -m app.stage23d_forward_shadow_candidate")
        lines.append("cat data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_candidate.md")
        lines.append("```")
        lines.append("")
        lines.append("## Output files")
        lines.append("")
        lines.append(f"- `{REPORT_JSON.relative_to(ROOT)}`")
        lines.append(f"- `{REPORT_MD.relative_to(ROOT)}`")
        lines.append(f"- `{FILTER_CSV.relative_to(ROOT)}`")
        lines.append(f"- `{ENRICHED_TRADES_CSV.relative_to(ROOT)}`")
        lines.append(f"- `{COMPARISON_CSV.relative_to(ROOT)}`")
        lines.append(f"- `{SCHEMA_CSV.relative_to(ROOT)}`")
        REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
        return 0

    except Exception as exc:
        if schema_df is not None:
            try:
                schema_df.to_csv(SCHEMA_CSV, index=False)
            except Exception:
                pass
        write_error_report(exc, db_path=db_path, schema_df=schema_df)
        # Also print concise error to stderr for terminal visibility.
        print(f"Stage25B diagnostic error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
