#!/usr/bin/env python3
"""
Stage39C microstructure/session-condition diagnostic for XAUUSD Stage39B watch rows.

Research-only diagnostic. This script is deliberately NOT a promotion, EA, paper-live,
or live-trading gate.

Inputs:
  - SQLite bars table with H1 rows (and optionally other timeframes in same table).
  - Optional Stage39B summary JSON to determine the Stage39B path-watch candidate set.
  - Optional Stage39B event rows CSV; if unusable, events are recomputed from H1 bars.

Outputs:
  reports/stage39c/stage39c_condition_candidate_summary.csv
  reports/stage39c/stage39c_condition_bucket_summary.csv
  reports/stage39c/stage39c_condition_event_rows.csv
  reports/stage39c/stage39c_condition_cross_matrix.csv
  reports/stage39c/stage39c_condition_diagnostic_summary.json
  reports/stage39c/stage39c_microstructure_session_condition.md
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
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


STAGE = "Stage39C_MICROSTRUCTURE_SESSION_CONDITION_DIAGNOSTIC"
DECISION_SCOPE = "RESEARCH_STAGE_ONLY_NO_PROMOTION"

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
OPEN_CANDIDATES = ["open", "o"]
HIGH_CANDIDATES = ["high", "h"]
LOW_CANDIDATES = ["low", "l"]
CLOSE_CANDIDATES = ["close", "c"]
SPREAD_CANDIDATES = ["spread", "spread_points", "spread_bps"]
SYMBOL_CANDIDATES = ["symbol", "ticker", "instrument"]
SOURCE_CANDIDATES = ["source", "provider", "feed"]
TIMEFRAME_CANDIDATES = ["timeframe", "tf", "interval"]
VOLUME_CANDIDATES = ["tick_volume", "volume", "real_volume", "vol"]

PATH_WATCH_CANDIDATE_NAMES = [
    "BB_LOWER_REV_LONG_W120_K2.5",
    "RANGE_BOTTOM_REV_LONG_W48_Q0.05",
]

DEFAULT_CANDIDATE_SPECS = [
    {
        "candidate": "BB_LOWER_REV_LONG_W120_K2.5",
        "family": "BOLLINGER_REVERSAL",
        "side": "LONG",
        "horizon_hours": 72,
        "lookback_hours": 120,
        "trigger_type": "bb_lower",
        "threshold": 2.5,
        "stage39b_classification": "PATH_DIAGNOSTIC_WATCH_ONLY_NO_PROMOTION",
        "source_stage39b_residual_bps": 12.93,
        "source_stage39b_event_clock_n": 80,
        "source_stage39b_median_mae_bps": -87.00,
        "source_stage39b_median_mfe_bps": 153.37,
    },
    {
        "candidate": "RANGE_BOTTOM_REV_LONG_W48_Q0.05",
        "family": "ROLLING_RANGE_REVERSAL",
        "side": "LONG",
        "horizon_hours": 72,
        "lookback_hours": 48,
        "trigger_type": "range_bottom",
        "threshold": 0.05,
        "stage39b_classification": "PATH_DIAGNOSTIC_WATCH_ONLY_NO_PROMOTION",
        "source_stage39b_residual_bps": 8.96,
        "source_stage39b_event_clock_n": 145,
        "source_stage39b_median_mae_bps": -76.42,
        "source_stage39b_median_mfe_bps": 123.10,
    },
]


@dataclass
class CandidateSpec:
    candidate: str
    family: str
    side: str
    horizon_hours: int
    lookback_hours: int
    trigger_type: str
    threshold: float
    stage39b_classification: str = "PATH_DIAGNOSTIC_WATCH_ONLY_NO_PROMOTION"
    source_stage39b_residual_bps: Optional[float] = None
    source_stage39b_event_clock_n: Optional[int] = None
    source_stage39b_median_mae_bps: Optional[float] = None
    source_stage39b_median_mfe_bps: Optional[float] = None


def norm_name(s: Any) -> str:
    return str(s).strip().lower()


def normalize_symbol(s: Any) -> str:
    return str(s).strip().upper()


def normalize_source(s: Any) -> str:
    return str(s).strip().lower()


def normalize_timeframe(s: Any) -> str:
    raw = str(s).strip().upper().replace(" ", "").replace("_", "")
    aliases = {
        "H1": "H1",
        "1H": "H1",
        "60M": "H1",
        "M60": "H1",
        "60MIN": "H1",
        "60MINUTE": "H1",
        "60MINUTES": "H1",
        "1HR": "H1",
        "1HOUR": "H1",
        "1HOURS": "H1",
        "M1": "M1",
        "1M": "M1",
        "1MIN": "M1",
        "1MINUTE": "M1",
        "M5": "M5",
        "5M": "M5",
        "5MIN": "M5",
        "5MINUTE": "M5",
        "M15": "M15",
        "15M": "M15",
        "15MIN": "M15",
        "15MINUTE": "M15",
    }
    return aliases.get(raw, raw)


def pick_col(columns: Sequence[str], candidates: Sequence[str], required: bool = True) -> Optional[str]:
    exact = {c: c for c in columns}
    lower = {c.lower(): c for c in columns}
    for cand in candidates:
        if cand in exact:
            return exact[cand]
        if cand.lower() in lower:
            return lower[cand.lower()]
    if required:
        raise ValueError(f"Required column not found. Tried candidates={list(candidates)}; available={list(columns)}")
    return None


def sqlite_columns(db_path: str, table: str) -> List[str]:
    with sqlite3.connect(db_path) as con:
        rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    if not rows:
        raise ValueError(f"Table not found or has no schema: {db_path}:{table}")
    return [r[1] for r in rows]


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def sample_distinct(df: pd.DataFrame, col: Optional[str], limit: int = 12) -> List[str]:
    if not col or col not in df.columns:
        return []
    vals = df[col].dropna().astype(str).drop_duplicates().head(limit).tolist()
    return vals


def read_bars(
    db_path: str,
    table: str,
    symbol: Optional[str],
    source: Optional[str],
    timeframe: Optional[str],
    max_rows: Optional[int] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    columns = sqlite_columns(db_path, table)
    ts_col = pick_col(columns, TIMESTAMP_CANDIDATES, required=True)
    open_col = pick_col(columns, OPEN_CANDIDATES, required=True)
    high_col = pick_col(columns, HIGH_CANDIDATES, required=True)
    low_col = pick_col(columns, LOW_CANDIDATES, required=True)
    close_col = pick_col(columns, CLOSE_CANDIDATES, required=True)
    spread_col = pick_col(columns, SPREAD_CANDIDATES, required=False)
    symbol_col = pick_col(columns, SYMBOL_CANDIDATES, required=False)
    source_col = pick_col(columns, SOURCE_CANDIDATES, required=False)
    timeframe_col = pick_col(columns, TIMEFRAME_CANDIDATES, required=False)
    volume_col = pick_col(columns, VOLUME_CANDIDATES, required=False)

    selected = [ts_col, open_col, high_col, low_col, close_col]
    for c in [spread_col, symbol_col, source_col, timeframe_col, volume_col]:
        if c and c not in selected:
            selected.append(c)

    sql = f"SELECT {', '.join(quote_ident(c) for c in selected)} FROM {quote_ident(table)}"
    sql += f" ORDER BY {quote_ident(ts_col)}"
    if max_rows and max_rows > 0:
        sql += f" LIMIT {int(max_rows)}"

    with sqlite3.connect(db_path) as con:
        df = pd.read_sql_query(sql, con)

    pre_filter_rows = int(len(df))
    distinct_sample = {
        "symbol": sample_distinct(df, symbol_col),
        "source": sample_distinct(df, source_col),
        "timeframe": sample_distinct(df, timeframe_col),
    }

    filter_steps = []
    if symbol and symbol_col:
        before = len(df)
        req = normalize_symbol(symbol)
        df = df[df[symbol_col].map(normalize_symbol) == req].copy()
        filter_steps.append({"filter": "symbol", "requested": symbol, "normalized": req, "before": int(before), "after": int(len(df))})

    if source and source_col:
        before = len(df)
        req = normalize_source(source)
        df = df[df[source_col].map(normalize_source) == req].copy()
        filter_steps.append({"filter": "source", "requested": source, "normalized": req, "before": int(before), "after": int(len(df))})

    if timeframe and timeframe_col:
        before = len(df)
        req = normalize_timeframe(timeframe)
        df = df[df[timeframe_col].map(normalize_timeframe) == req].copy()
        filter_steps.append({"filter": "timeframe", "requested": timeframe, "normalized": req, "before": int(before), "after": int(len(df))})

    if df.empty:
        raise ValueError(
            "No rows loaded after tolerant filtering. "
            f"db={db_path} table={table} requested symbol={symbol} source={source} timeframe={timeframe}; "
            f"pre_filter_rows={pre_filter_rows}; distinct_values_sample={distinct_sample}; filter_steps={filter_steps}"
        )

    rename_map = {
        ts_col: "ts",
        open_col: "open",
        high_col: "high",
        low_col: "low",
        close_col: "close",
    }
    if spread_col:
        rename_map[spread_col] = "spread"
    if symbol_col:
        rename_map[symbol_col] = "symbol"
    if source_col:
        rename_map[source_col] = "source"
    if timeframe_col:
        rename_map[timeframe_col] = "timeframe"
    if volume_col:
        rename_map[volume_col] = "volume"

    df = df.rename(columns=rename_map)
    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    df = df.dropna(subset=["ts"]).sort_values("ts").drop_duplicates(subset=["ts"], keep="last").reset_index(drop=True)

    for col in ["open", "high", "low", "close", "spread", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)

    audit = {
        "db_path": db_path,
        "table": table,
        "available_columns": columns,
        "columns": {
            "timestamp": ts_col,
            "open": open_col,
            "high": high_col,
            "low": low_col,
            "close": close_col,
            "spread": spread_col,
            "symbol": symbol_col,
            "source": source_col,
            "timeframe": timeframe_col,
            "volume": volume_col,
        },
        "requested_filters": {"symbol": symbol, "source": source, "timeframe": timeframe},
        "distinct_values_sample": distinct_sample,
        "filter_steps": filter_steps,
        "pre_filter_rows": pre_filter_rows,
        "post_filter_rows": int(len(df)),
        "loaded_rows": int(len(df)),
        "date_min": df["ts"].min().isoformat() if len(df) else None,
        "date_max": df["ts"].max().isoformat() if len(df) else None,
    }
    return df, audit


def infer_bar_hours(ts: pd.Series) -> float:
    diffs = ts.sort_values().diff().dropna().dt.total_seconds() / 3600.0
    diffs = diffs[(diffs > 0) & (diffs < 48)]
    if diffs.empty:
        return 1.0
    return float(diffs.median())


def bps(ret: pd.Series) -> pd.Series:
    return ret * 10000.0


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    prev_close = out["close"].shift(1)
    tr = pd.concat(
        [
            (out["high"] - out["low"]).abs(),
            (out["high"] - prev_close).abs(),
            (out["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["tr_bps"] = (tr / out["close"].replace(0, np.nan)) * 10000.0
    out["atr24_bps"] = out["tr_bps"].rolling(24, min_periods=12).mean()
    out["atr72_bps"] = out["tr_bps"].rolling(72, min_periods=24).mean()
    out["ret1_bps"] = out["close"].pct_change(1) * 10000.0
    out["ret24_bps"] = out["close"].pct_change(24) * 10000.0
    out["ret72_bps"] = out["close"].pct_change(72) * 10000.0
    out["ret120_bps"] = out["close"].pct_change(120) * 10000.0

    if "spread" in out.columns:
        out["spread"] = pd.to_numeric(out["spread"], errors="coerce")
        out["spread_roll_median_24"] = out["spread"].rolling(24, min_periods=8).median()
        out["spread_roll_median_120"] = out["spread"].rolling(120, min_periods=24).median()
        spread_mean = out["spread"].rolling(240, min_periods=48).mean()
        spread_std = out["spread"].rolling(240, min_periods=48).std(ddof=0)
        out["spread_z240"] = (out["spread"] - spread_mean) / spread_std.replace(0, np.nan)
    else:
        out["spread"] = np.nan
        out["spread_roll_median_24"] = np.nan
        out["spread_roll_median_120"] = np.nan
        out["spread_z240"] = np.nan

    out["hour_utc"] = out["ts"].dt.hour
    out["weekday"] = out["ts"].dt.day_name()
    out["year"] = out["ts"].dt.year
    out["month"] = out["ts"].dt.month
    out["session_utc"] = out["hour_utc"].map(session_name)

    return out


def session_name(hour: int) -> str:
    h = int(hour)
    if 0 <= h <= 6:
        return "ASIA_00_06"
    if 7 <= h <= 12:
        return "LONDON_07_12"
    if 13 <= h <= 19:
        return "NY_13_19"
    return "LATE_20_23"


def safe_qcut_labels(s: pd.Series, labels: Sequence[str]) -> pd.Series:
    x = pd.to_numeric(s, errors="coerce")
    out = pd.Series(index=s.index, dtype="object")
    ok = x.dropna()
    if len(ok) < len(labels) * 5 or ok.nunique() < len(labels):
        out.loc[x.notna()] = "UNBUCKETED"
        out.loc[x.isna()] = "NA"
        return out
    try:
        cut = pd.qcut(x, q=len(labels), labels=labels, duplicates="drop")
        out.loc[:] = cut.astype("object")
        out.loc[x.isna()] = "NA"
    except Exception:
        out.loc[x.notna()] = "UNBUCKETED"
        out.loc[x.isna()] = "NA"
    return out


def classify_spread_z(z: Any) -> str:
    try:
        v = float(z)
    except Exception:
        return "NA"
    if math.isnan(v):
        return "NA"
    if v <= -0.5:
        return "SPREAD_LOW_Z_LE_-0.5"
    if v < 0.5:
        return "SPREAD_NORMAL_Z_-0.5_0.5"
    if v < 1.5:
        return "SPREAD_ELEVATED_Z_0.5_1.5"
    return "SPREAD_STRESS_Z_GE_1.5"


def classify_prior_ret(v: Any) -> str:
    try:
        x = float(v)
    except Exception:
        return "NA"
    if math.isnan(x):
        return "NA"
    if x <= -200:
        return "DOWN_EXTREME_LE_-200BPS"
    if x <= -75:
        return "DOWN_MODERATE_-200_-75BPS"
    if x < 75:
        return "NEUTRAL_-75_75BPS"
    if x < 200:
        return "UP_MODERATE_75_200BPS"
    return "UP_EXTREME_GE_200BPS"


def load_stage39b_specs(summary_path: Optional[str]) -> Tuple[List[CandidateSpec], Dict[str, Any]]:
    info: Dict[str, Any] = {"source": "defaults", "summary_path": summary_path, "loaded": False}
    specs: List[CandidateSpec] = []

    if summary_path and Path(summary_path).exists():
        try:
            obj = json.loads(Path(summary_path).read_text(encoding="utf-8"))
            rows = obj.get("stage39a_context", {}).get("candidate_specs", [])
            # Keep only the two Stage39B path diagnostic watch candidates.
            # Some summaries include four Stage39A strict rows; Stage39B lets only two continue.
            for row in rows:
                name = str(row.get("candidate", ""))
                if name not in PATH_WATCH_CANDIDATE_NAMES:
                    continue
                specs.append(
                    CandidateSpec(
                        candidate=name,
                        family=str(row.get("family", "")),
                        side=str(row.get("side", "LONG")).upper(),
                        horizon_hours=int(float(row.get("horizon_hours", 72))),
                        lookback_hours=int(float(row.get("lookback_hours", 0))),
                        trigger_type=str(row.get("trigger_type", "")),
                        threshold=float(row.get("threshold", np.nan)),
                        stage39b_classification="PATH_DIAGNOSTIC_WATCH_ONLY_NO_PROMOTION",
                        source_stage39b_residual_bps=try_float(row.get("source_stage39a_residual_bps")),
                        source_stage39b_event_clock_n=try_int(row.get("source_stage39a_event_clock_n")),
                        source_stage39b_median_mae_bps=try_float(row.get("source_stage39a_median_mae_bps")),
                        source_stage39b_median_mfe_bps=try_float(row.get("source_stage39a_median_mfe_bps")),
                    )
                )
            # Override with Stage39B candidate values from markdown/summary if known from Stage39B output.
            overrides = {
                "BB_LOWER_REV_LONG_W120_K2.5": {"n": 80, "mae": -87.00, "mfe": 153.37, "res": 12.93},
                "RANGE_BOTTOM_REV_LONG_W48_Q0.05": {"n": 145, "mae": -76.42, "mfe": 123.10, "res": 8.96},
            }
            for sp in specs:
                ov = overrides.get(sp.candidate)
                if ov:
                    sp.source_stage39b_event_clock_n = ov["n"]
                    sp.source_stage39b_median_mae_bps = ov["mae"]
                    sp.source_stage39b_median_mfe_bps = ov["mfe"]
                    sp.source_stage39b_residual_bps = ov["res"]
            if specs:
                info.update({"source": "stage39b_summary_json", "loaded": True, "candidate_count": len(specs)})
                return specs, info
        except Exception as exc:
            info.update({"error": repr(exc)})

    specs = [CandidateSpec(**row) for row in DEFAULT_CANDIDATE_SPECS]
    info.update({"source": "defaults", "loaded": False, "candidate_count": len(specs)})
    return specs, info


def try_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        v = float(x)
        if math.isnan(v):
            return None
        return v
    except Exception:
        return None


def try_int(x: Any) -> Optional[int]:
    try:
        if x is None:
            return None
        return int(float(x))
    except Exception:
        return None


def compute_trigger_mask(df: pd.DataFrame, spec: CandidateSpec) -> Tuple[pd.Series, pd.Series]:
    close = df["close"]
    if spec.trigger_type == "bb_lower":
        mean = close.rolling(spec.lookback_hours, min_periods=max(10, spec.lookback_hours // 2)).mean()
        std = close.rolling(spec.lookback_hours, min_periods=max(10, spec.lookback_hours // 2)).std(ddof=0)
        z = (close - mean) / std.replace(0, np.nan)
        severity = -z
        mask = z <= -abs(float(spec.threshold))
        return mask.fillna(False), severity
    if spec.trigger_type == "range_bottom":
        lo = df["low"].rolling(spec.lookback_hours, min_periods=max(10, spec.lookback_hours // 2)).min()
        hi = df["high"].rolling(spec.lookback_hours, min_periods=max(10, spec.lookback_hours // 2)).max()
        pos = (close - lo) / (hi - lo).replace(0, np.nan)
        severity = 1.0 - pos
        mask = pos <= float(spec.threshold)
        return mask.fillna(False), severity
    if spec.trigger_type == "ret_z_downside":
        ret = close.pct_change(spec.lookback_hours) * 10000.0
        mu = ret.rolling(240, min_periods=60).mean()
        sd = ret.rolling(240, min_periods=60).std(ddof=0)
        z = (ret - mu) / sd.replace(0, np.nan)
        severity = -z
        mask = z <= -abs(float(spec.threshold))
        return mask.fillna(False), severity
    raise ValueError(f"Unsupported trigger_type for Stage39C: {spec.trigger_type} ({spec.candidate})")


def event_clock_indices(trigger_idx: Sequence[int], horizon_bars: int, n_bars: int) -> List[int]:
    selected: List[int] = []
    next_allowed = -1
    last_start = n_bars - horizon_bars - 1
    for i in trigger_idx:
        i = int(i)
        if i > last_start:
            continue
        if i < next_allowed:
            continue
        selected.append(i)
        next_allowed = i + horizon_bars
    return selected


def load_events_csv(
    path: Optional[str],
    specs: List[CandidateSpec],
    bars: pd.DataFrame,
    bar_hours: float,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    info: Dict[str, Any] = {"path": path, "loaded": False}
    if not path or not Path(path).exists():
        info["reason"] = "missing_path"
        return pd.DataFrame(), info
    try:
        ev = pd.read_csv(path)
    except Exception as exc:
        info.update({"reason": "read_error", "error": repr(exc)})
        return pd.DataFrame(), info

    cand_col = pick_existing(ev.columns, ["candidate", "candidate_name", "strategy", "name"])
    ts_col = pick_existing(ev.columns, ["entry_ts", "event_ts", "timestamp", "ts", "ts_utc", "utc_time", "entry_time", "time"])
    if not cand_col or not ts_col:
        info.update({"reason": "missing_candidate_or_timestamp_col", "columns": list(ev.columns)})
        return pd.DataFrame(), info

    target_names = {sp.candidate for sp in specs}
    ev = ev[ev[cand_col].astype(str).isin(target_names)].copy()
    if ev.empty:
        info.update({"reason": "no_target_candidates_in_csv", "candidate_column": cand_col, "timestamp_column": ts_col})
        return pd.DataFrame(), info

    ev["candidate"] = ev[cand_col].astype(str)
    ev["ts"] = pd.to_datetime(ev[ts_col], utc=True, errors="coerce")
    ev = ev.dropna(subset=["ts"]).sort_values(["candidate", "ts"]).copy()
    if ev.empty:
        info.update({"reason": "no_parseable_timestamps"})
        return pd.DataFrame(), info

    # Map timestamps to nearest exact H1 bar index. If timestamps do not match bars exactly, this
    # loader becomes risky; fall back to recompute in that case.
    ts_to_idx = pd.Series(np.arange(len(bars)), index=bars["ts"]).to_dict()
    ev["bar_index"] = ev["ts"].map(ts_to_idx)
    match_rate = float(ev["bar_index"].notna().mean()) if len(ev) else 0.0
    if match_rate < 0.90:
        info.update({"reason": "low_timestamp_match_rate", "match_rate": match_rate})
        return pd.DataFrame(), info

    rows = []
    for sp in specs:
        sub = ev[ev["candidate"] == sp.candidate].copy()
        if sub.empty:
            continue
        horizon_bars = max(1, int(round(sp.horizon_hours / bar_hours)))
        raw_idx = sorted(sub["bar_index"].dropna().astype(int).tolist())
        selected = event_clock_indices(raw_idx, horizon_bars=horizon_bars, n_bars=len(bars))
        for i in selected:
            rows.append(
                {
                    "candidate": sp.candidate,
                    "event_source": "stage39b_event_rows_csv",
                    "bar_index": i,
                    "ts": bars.loc[i, "ts"],
                    "horizon_bars": horizon_bars,
                    "horizon_hours": sp.horizon_hours,
                    "lookback_hours": sp.lookback_hours,
                    "side": sp.side,
                    "trigger_type": sp.trigger_type,
                    "threshold": sp.threshold,
                    "trigger_severity": np.nan,
                }
            )
    out = pd.DataFrame(rows)
    if out.empty:
        info.update({"reason": "no_event_clock_rows_after_csv_load"})
        return out, info
    info.update({"loaded": True, "source": "stage39b_event_rows_csv", "rows": int(len(out))})
    return out, info


def pick_existing(columns: Sequence[str], names: Sequence[str]) -> Optional[str]:
    lower = {str(c).lower(): c for c in columns}
    for name in names:
        if name.lower() in lower:
            return lower[name.lower()]
    return None


def recompute_events(df: pd.DataFrame, specs: List[CandidateSpec], bar_hours: float) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    rows = []
    info: Dict[str, Any] = {}
    for sp in specs:
        mask, severity = compute_trigger_mask(df, sp)
        raw_idx = np.flatnonzero(mask.to_numpy())
        horizon_bars = max(1, int(round(sp.horizon_hours / bar_hours)))
        selected = event_clock_indices(raw_idx, horizon_bars=horizon_bars, n_bars=len(df))
        info[sp.candidate] = {
            "event_source": "recomputed_from_h1",
            "raw_trigger_count": int(len(raw_idx)),
            "event_clock_count": int(len(selected)),
            "horizon_bars": int(horizon_bars),
            "bar_hours": float(bar_hours),
        }
        for i in selected:
            rows.append(
                {
                    "candidate": sp.candidate,
                    "event_source": "recomputed_from_h1",
                    "bar_index": int(i),
                    "ts": df.loc[i, "ts"],
                    "horizon_bars": int(horizon_bars),
                    "horizon_hours": int(sp.horizon_hours),
                    "lookback_hours": int(sp.lookback_hours),
                    "side": sp.side,
                    "trigger_type": sp.trigger_type,
                    "threshold": float(sp.threshold),
                    "trigger_severity": float(severity.iloc[i]) if pd.notna(severity.iloc[i]) else np.nan,
                }
            )
    return pd.DataFrame(rows), info


def build_event_rows(df: pd.DataFrame, events: pd.DataFrame, specs: List[CandidateSpec], cost_bps: float) -> pd.DataFrame:
    specs_by_name = {sp.candidate: sp for sp in specs}
    rows = []
    for _, ev in events.iterrows():
        i = int(ev["bar_index"])
        sp = specs_by_name[str(ev["candidate"])]
        horizon_bars = int(ev["horizon_bars"])
        end_i = i + horizon_bars
        if i < 0 or end_i >= len(df):
            continue
        entry = float(df.loc[i, "close"])
        path = df.iloc[i + 1 : end_i + 1]
        if path.empty or entry <= 0:
            continue
        final_close = float(df.loc[end_i, "close"])
        if sp.side.upper() == "LONG":
            final_bps = (final_close / entry - 1.0) * 10000.0
            mfe_bps = ((path["high"].max() / entry) - 1.0) * 10000.0
            mae_bps = ((path["low"].min() / entry) - 1.0) * 10000.0
            touch_target_50 = bool((path["high"] >= entry * (1 + 0.005)).any())
            touch_target_100 = bool((path["high"] >= entry * (1 + 0.010)).any())
            touch_target_150 = bool((path["high"] >= entry * (1 + 0.015)).any())
            touch_stop_50 = bool((path["low"] <= entry * (1 - 0.005)).any())
            touch_stop_100 = bool((path["low"] <= entry * (1 - 0.010)).any())
            touch_stop_150 = bool((path["low"] <= entry * (1 - 0.015)).any())
        else:
            final_bps = (entry / final_close - 1.0) * 10000.0
            mfe_bps = ((entry / path["low"].min()) - 1.0) * 10000.0
            mae_bps = ((entry / path["high"].max()) - 1.0) * 10000.0
            touch_target_50 = bool((path["low"] <= entry * (1 - 0.005)).any())
            touch_target_100 = bool((path["low"] <= entry * (1 - 0.010)).any())
            touch_target_150 = bool((path["low"] <= entry * (1 - 0.015)).any())
            touch_stop_50 = bool((path["high"] >= entry * (1 + 0.005)).any())
            touch_stop_100 = bool((path["high"] >= entry * (1 + 0.010)).any())
            touch_stop_150 = bool((path["high"] >= entry * (1 + 0.015)).any())

        row = df.loc[i].to_dict()
        rows.append(
            {
                "stage": STAGE,
                "decision_scope": DECISION_SCOPE,
                "promotion": "NO_GO",
                "candidate": sp.candidate,
                "family": sp.family,
                "side": sp.side,
                "horizon_hours": int(sp.horizon_hours),
                "horizon_bars": horizon_bars,
                "lookback_hours": int(sp.lookback_hours),
                "trigger_type": sp.trigger_type,
                "threshold": float(sp.threshold),
                "event_source": ev.get("event_source", "unknown"),
                "bar_index": i,
                "entry_ts": row["ts"],
                "exit_ts": df.loc[end_i, "ts"],
                "entry_close": entry,
                "exit_close": final_close,
                "final_bps": final_bps,
                "cost_stressed_final_bps": final_bps - cost_bps,
                "mfe_bps": mfe_bps,
                "mae_bps": mae_bps,
                "touch_target_50bps": touch_target_50,
                "touch_target_100bps": touch_target_100,
                "touch_target_150bps": touch_target_150,
                "touch_stop_50bps": touch_stop_50,
                "touch_stop_100bps": touch_stop_100,
                "touch_stop_150bps": touch_stop_150,
                "trigger_severity": ev.get("trigger_severity", np.nan),
                "hour_utc": int(row.get("hour_utc", pd.NaT if False else 0)),
                "session_utc": row.get("session_utc", "NA"),
                "weekday": row.get("weekday", "NA"),
                "year": int(row.get("year")),
                "month": int(row.get("month")),
                "spread": row.get("spread", np.nan),
                "spread_roll_median_24": row.get("spread_roll_median_24", np.nan),
                "spread_roll_median_120": row.get("spread_roll_median_120", np.nan),
                "spread_z240": row.get("spread_z240", np.nan),
                "atr24_bps": row.get("atr24_bps", np.nan),
                "atr72_bps": row.get("atr72_bps", np.nan),
                "ret1_bps": row.get("ret1_bps", np.nan),
                "ret24_bps": row.get("ret24_bps", np.nan),
                "ret72_bps": row.get("ret72_bps", np.nan),
                "ret120_bps": row.get("ret120_bps", np.nan),
                "source_stage39b_residual_bps": sp.source_stage39b_residual_bps,
                "source_stage39b_event_clock_n": sp.source_stage39b_event_clock_n,
                "source_stage39b_median_mae_bps": sp.source_stage39b_median_mae_bps,
                "source_stage39b_median_mfe_bps": sp.source_stage39b_median_mfe_bps,
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    out["spread_regime"] = out["spread_z240"].map(classify_spread_z)
    out["prior_ret24_regime"] = out["ret24_bps"].map(classify_prior_ret)
    out["prior_ret72_regime"] = out["ret72_bps"].map(classify_prior_ret)
    out["atr24_bucket"] = out.groupby("candidate", group_keys=False)["atr24_bps"].apply(
        lambda s: safe_qcut_labels(s, ["ATR24_LOW", "ATR24_MID", "ATR24_HIGH"])
    )
    out["trigger_severity_bucket"] = out.groupby("candidate", group_keys=False)["trigger_severity"].apply(
        lambda s: safe_qcut_labels(s, ["SEVERITY_LOW", "SEVERITY_MID", "SEVERITY_HIGH"])
    )
    return out


def pct_bool(s: pd.Series) -> float:
    if len(s) == 0:
        return float("nan")
    return float(pd.Series(s).astype(bool).mean() * 100.0)


def summarize_group(g: pd.DataFrame, cost_bps: float, extra_slip: Sequence[float]) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "n": int(len(g)),
        "mean_final_bps": float(g["final_bps"].mean()) if len(g) else np.nan,
        "median_final_bps": float(g["final_bps"].median()) if len(g) else np.nan,
        "hit_rate_pct": float((g["final_bps"] > 0).mean() * 100.0) if len(g) else np.nan,
        "cost_stressed_mean_bps": float(g["cost_stressed_final_bps"].mean()) if len(g) else np.nan,
        "median_mae_bps": float(g["mae_bps"].median()) if len(g) else np.nan,
        "median_mfe_bps": float(g["mfe_bps"].median()) if len(g) else np.nan,
        "mean_mae_bps": float(g["mae_bps"].mean()) if len(g) else np.nan,
        "mean_mfe_bps": float(g["mfe_bps"].mean()) if len(g) else np.nan,
        "touch_stop_50bps_pct": pct_bool(g["touch_stop_50bps"]),
        "touch_stop_100bps_pct": pct_bool(g["touch_stop_100bps"]),
        "touch_stop_150bps_pct": pct_bool(g["touch_stop_150bps"]),
        "touch_target_50bps_pct": pct_bool(g["touch_target_50bps"]),
        "touch_target_100bps_pct": pct_bool(g["touch_target_100bps"]),
        "touch_target_150bps_pct": pct_bool(g["touch_target_150bps"]),
        "years_count": int(g["year"].nunique()) if "year" in g else 0,
        "ex2025_n": int((g["year"] != 2025).sum()) if "year" in g else 0,
        "ex2025_mean_bps": float(g.loc[g["year"] != 2025, "final_bps"].mean()) if "year" in g and (g["year"] != 2025).any() else np.nan,
    }
    # Leave-one-year-out mean on final bps
    loyo = {}
    if "year" in g:
        for year in sorted(g["year"].dropna().unique()):
            sub = g[g["year"] != year]
            if len(sub):
                loyo[str(int(year))] = float(sub["final_bps"].mean())
    d["leave_one_year_out_min_mean_bps"] = float(min(loyo.values())) if loyo else np.nan
    d["leave_one_year_out_json"] = json.dumps(loyo, ensure_ascii=False)
    for slip in extra_slip:
        key = f"mean_after_cost_plus_slip_{format_slip(slip)}bps"
        d[key] = float((g["final_bps"] - cost_bps - float(slip)).mean()) if len(g) else np.nan
    return d


def format_slip(x: float) -> str:
    if float(x).is_integer():
        return str(int(x))
    return str(x).replace(".", "p")


def summarize_candidates(events: pd.DataFrame, specs: List[CandidateSpec], cost_bps: float, extra_slip: Sequence[float]) -> pd.DataFrame:
    rows = []
    spec_map = {sp.candidate: sp for sp in specs}
    for cand, g in events.groupby("candidate"):
        sp = spec_map.get(cand)
        d = summarize_group(g, cost_bps, extra_slip)
        d.update(
            {
                "candidate": cand,
                "family": sp.family if sp else None,
                "side": sp.side if sp else None,
                "horizon_hours": sp.horizon_hours if sp else None,
                "lookback_hours": sp.lookback_hours if sp else None,
                "source_stage39b_residual_bps": sp.source_stage39b_residual_bps if sp else None,
                "source_stage39b_event_clock_n": sp.source_stage39b_event_clock_n if sp else None,
                "source_stage39b_median_mae_bps": sp.source_stage39b_median_mae_bps if sp else None,
                "source_stage39b_median_mfe_bps": sp.source_stage39b_median_mfe_bps if sp else None,
            }
        )
        d["residual_to_median_mae_abs"] = safe_ratio(d.get("source_stage39b_residual_bps"), abs_float(d.get("median_mae_bps")))
        d["classification"] = classify_candidate_level(d)
        rows.append(d)
    out = pd.DataFrame(rows)
    return reorder(out, ["classification", "candidate", "family", "side", "horizon_hours", "n", "mean_final_bps", "median_final_bps", "cost_stressed_mean_bps", "hit_rate_pct", "median_mae_bps", "median_mfe_bps", "ex2025_mean_bps", "leave_one_year_out_min_mean_bps", "touch_stop_100bps_pct", "touch_target_100bps_pct", "source_stage39b_residual_bps", "residual_to_median_mae_abs"])


def abs_float(x: Any) -> Optional[float]:
    v = try_float(x)
    return abs(v) if v is not None else None


def safe_ratio(a: Any, b: Any) -> Optional[float]:
    aa = try_float(a)
    bb = try_float(b)
    if aa is None or bb is None or bb == 0:
        return None
    return float(aa / bb)


def classify_candidate_level(d: Dict[str, Any]) -> str:
    n = d.get("n", 0) or 0
    cost_mean = d.get("cost_stressed_mean_bps", np.nan)
    med = d.get("median_final_bps", np.nan)
    hit = d.get("hit_rate_pct", np.nan)
    ex = d.get("ex2025_mean_bps", np.nan)
    loyo = d.get("leave_one_year_out_min_mean_bps", np.nan)
    med_mae = d.get("median_mae_bps", np.nan)
    stop100 = d.get("touch_stop_100bps_pct", np.nan)
    residual = d.get("source_stage39b_residual_bps", np.nan)
    ratio = safe_ratio(residual, abs_float(med_mae))

    # Stage39C remains research-only. This classification only says whether the
    # row deserves a conditional robustness check, not whether it is tradable.
    if n >= 60 and cost_mean >= 20 and med > 0 and hit >= 55 and ex > 0 and loyo > 0 and med_mae >= -100 and stop100 <= 50:
        return "CONDITION_RESEARCH_WATCH_ONLY_NO_PROMOTION"
    if ratio is not None and ratio < 0.12:
        return "RESIDUAL_TOO_SMALL_VS_PATH_RISK_NO_PROMOTION"
    if med_mae < -100 or stop100 > 55:
        return "ADVERSE_EXCURSION_TOO_HIGH_NO_PROMOTION"
    return "NO_STABLE_CONDITION_EDGE_NO_PROMOTION"


def summarize_buckets(
    events: pd.DataFrame,
    dimensions: Sequence[str],
    cost_bps: float,
    extra_slip: Sequence[float],
    min_bucket_events: int,
) -> pd.DataFrame:
    rows = []
    for dim in dimensions:
        if dim not in events.columns:
            continue
        for (cand, bucket), g in events.groupby(["candidate", dim], dropna=False):
            d = summarize_group(g, cost_bps, extra_slip)
            d.update({"candidate": cand, "dimension": dim, "bucket": str(bucket)})
            d["bucket_share_pct"] = float(len(g) / max(1, len(events[events["candidate"] == cand])) * 100.0)
            d["classification"] = classify_bucket_level(d, min_bucket_events=min_bucket_events)
            rows.append(d)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.sort_values(["classification", "candidate", "dimension", "cost_stressed_mean_bps"], ascending=[True, True, True, False])
    return reorder(out, ["classification", "candidate", "dimension", "bucket", "n", "bucket_share_pct", "mean_final_bps", "median_final_bps", "cost_stressed_mean_bps", "hit_rate_pct", "median_mae_bps", "median_mfe_bps", "ex2025_mean_bps", "leave_one_year_out_min_mean_bps", "touch_stop_100bps_pct", "touch_target_100bps_pct"])


def classify_bucket_level(d: Dict[str, Any], min_bucket_events: int) -> str:
    n = d.get("n", 0) or 0
    cost_mean = d.get("cost_stressed_mean_bps", np.nan)
    med = d.get("median_final_bps", np.nan)
    hit = d.get("hit_rate_pct", np.nan)
    ex = d.get("ex2025_mean_bps", np.nan)
    loyo = d.get("leave_one_year_out_min_mean_bps", np.nan)
    med_mae = d.get("median_mae_bps", np.nan)
    stop100 = d.get("touch_stop_100bps_pct", np.nan)

    if n < min_bucket_events:
        return "INSUFFICIENT_BUCKET_EVENTS_NO_PROMOTION"
    if cost_mean >= 25 and med > 0 and hit >= 58 and ex > 0 and loyo > 0 and med_mae >= -90 and stop100 <= 45:
        return "CONDITION_BUCKET_WATCH_ONLY_NO_PROMOTION"
    if cost_mean <= 0 or med <= 0:
        return "BAD_BUCKET_NO_PROMOTION"
    if med_mae < -110 or stop100 > 60:
        return "PATH_RISK_BUCKET_NO_PROMOTION"
    return "WEAK_BUCKET_NO_PROMOTION"


def build_cross_matrix(events: pd.DataFrame, cost_bps: float, min_bucket_events: int) -> pd.DataFrame:
    dims = [("session_utc", "atr24_bucket"), ("session_utc", "spread_regime"), ("session_utc", "prior_ret24_regime")]
    rows = []
    for dim1, dim2 in dims:
        if dim1 not in events.columns or dim2 not in events.columns:
            continue
        for (cand, b1, b2), g in events.groupby(["candidate", dim1, dim2], dropna=False):
            d = summarize_group(g, cost_bps, [])
            d.update({"candidate": cand, "dimension_1": dim1, "bucket_1": str(b1), "dimension_2": dim2, "bucket_2": str(b2)})
            d["classification"] = classify_bucket_level(d, min_bucket_events=min_bucket_events)
            rows.append(d)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.sort_values(["classification", "candidate", "cost_stressed_mean_bps"], ascending=[True, True, False])
    return reorder(out, ["classification", "candidate", "dimension_1", "bucket_1", "dimension_2", "bucket_2", "n", "mean_final_bps", "median_final_bps", "cost_stressed_mean_bps", "hit_rate_pct", "median_mae_bps", "median_mfe_bps", "ex2025_mean_bps", "leave_one_year_out_min_mean_bps", "touch_stop_100bps_pct"])


def reorder(df: pd.DataFrame, first_cols: Sequence[str]) -> pd.DataFrame:
    if df.empty:
        return df
    cols = [c for c in first_cols if c in df.columns] + [c for c in df.columns if c not in first_cols]
    return df[cols]


def safe_json(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): safe_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [safe_json(v) for v in obj]
    if isinstance(obj, tuple):
        return [safe_json(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if math.isnan(v) else v
    if isinstance(obj, float):
        return None if math.isnan(obj) else obj
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    if pd.isna(obj) if not isinstance(obj, (dict, list, tuple)) else False:
        return None
    return obj


def df_to_md(df: pd.DataFrame, max_rows: int = 20, floatfmt: str = ".2f") -> str:
    if df is None or df.empty:
        return "_No rows._"
    sub = df.head(max_rows).copy()
    # Keep markdown compact.
    for c in sub.columns:
        if pd.api.types.is_float_dtype(sub[c]):
            sub[c] = sub[c].map(lambda x: "" if pd.isna(x) else f"{x:{floatfmt}}")
    try:
        return sub.to_markdown(index=False)
    except Exception:
        return sub.to_csv(index=False)


def write_markdown(
    path: Path,
    data_audit: Dict[str, Any],
    specs_info: Dict[str, Any],
    event_info: Dict[str, Any],
    candidate_summary: pd.DataFrame,
    bucket_summary: pd.DataFrame,
    cross_matrix: pd.DataFrame,
    summary: Dict[str, Any],
) -> None:
    condition_watch = bucket_summary[bucket_summary.get("classification", pd.Series(dtype=str)).astype(str).eq("CONDITION_BUCKET_WATCH_ONLY_NO_PROMOTION")] if not bucket_summary.empty else pd.DataFrame()
    content = f"""# {STAGE}

## Decision

```text
scope = {DECISION_SCOPE}
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

Stage39C is a microstructure/session-condition diagnostic for the two Stage39B path-diagnostic watch rows only. It is not a promotion gate.

## Data audit

```json
{json.dumps(safe_json(data_audit), ensure_ascii=False, indent=2)}
```

## Candidate source

```json
{json.dumps(safe_json(specs_info), ensure_ascii=False, indent=2)}
```

## Event source

```json
{json.dumps(safe_json(event_info), ensure_ascii=False, indent=2)}
```

## Classification counts

```json
{json.dumps(safe_json(summary.get("classification_counts", {})), ensure_ascii=False, indent=2)}
```

## Candidate-level condition diagnostic

{df_to_md(candidate_summary, max_rows=20)}

## Condition bucket watch rows

{df_to_md(condition_watch, max_rows=30)}

## Top condition buckets by cost-stressed mean

{df_to_md(bucket_summary.sort_values("cost_stressed_mean_bps", ascending=False) if not bucket_summary.empty and "cost_stressed_mean_bps" in bucket_summary.columns else bucket_summary, max_rows=40)}

## Cross-condition matrix watch rows

{df_to_md(cross_matrix[cross_matrix.get("classification", pd.Series(dtype=str)).astype(str).eq("CONDITION_BUCKET_WATCH_ONLY_NO_PROMOTION")] if not cross_matrix.empty else pd.DataFrame(), max_rows=30)}

## Interpretation

- `CONDITION_RESEARCH_WATCH_ONLY_NO_PROMOTION` means the candidate remains research-observable after this diagnostic, not tradable.
- `CONDITION_BUCKET_WATCH_ONLY_NO_PROMOTION` means a session/microstructure bucket may deserve a separate robustness check.
- `RESIDUAL_TOO_SMALL_VS_PATH_RISK_NO_PROMOTION` means the benchmark residual is too small relative to adverse excursion.
- `ADVERSE_EXCURSION_TOO_HIGH_NO_PROMOTION` means the intrahorizon path risk remains too large.
- `INSUFFICIENT_BUCKET_EVENTS_NO_PROMOTION` means the bucket is too thin to use.

## Next allowed step

Only if one or more condition buckets are `CONDITION_BUCKET_WATCH_ONLY_NO_PROMOTION`, the next step is `Stage39D_CONDITION_ROBUSTNESS_AND_FORWARD_SPLIT_AUDIT`.

If no condition bucket survives, archive Stage39A/B/C and do not extend these rows with more filters.

`Stage39D`, if reached, is still research-only and not EA/paper-live/live.
"""
    path.write_text(content, encoding="utf-8")


def parse_slippage_list(s: str) -> List[float]:
    vals = []
    for part in str(s).split(","):
        part = part.strip()
        if not part:
            continue
        vals.append(float(part))
    return vals


def run(args: argparse.Namespace) -> None:
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    bars_raw, data_audit = read_bars(
        db_path=args.db,
        table=args.table,
        symbol=args.symbol,
        source=args.source,
        timeframe=args.timeframe,
        max_rows=args.max_rows,
    )
    bars = add_features(bars_raw)
    bar_hours = infer_bar_hours(bars["ts"])

    specs, specs_info = load_stage39b_specs(args.stage39b_summary)
    extra_slip = parse_slippage_list(args.extra_slippage_bps)

    events_csv_info: Dict[str, Any] = {}
    if args.force_recompute_events:
        events, event_info = recompute_events(bars, specs, bar_hours=bar_hours)
        event_info = {"mode": "force_recompute_events", "details": event_info}
    else:
        loaded_events, events_csv_info = load_events_csv(args.stage39b_event_rows, specs, bars, bar_hours=bar_hours)
        if not loaded_events.empty:
            events = loaded_events
            event_info = {"mode": "stage39b_event_rows_csv", "details": events_csv_info}
        else:
            events, recompute_info = recompute_events(bars, specs, bar_hours=bar_hours)
            event_info = {"mode": "fallback_recompute_events", "csv_attempt": events_csv_info, "details": recompute_info}

    if events.empty:
        raise ValueError("No Stage39C events could be built. Check Stage39B event rows or use --force-recompute-events.")

    event_rows = build_event_rows(bars, events, specs, cost_bps=float(args.cost_bps))
    if event_rows.empty:
        raise ValueError("No Stage39C event rows after forward path construction.")

    dimensions = [
        "session_utc",
        "weekday",
        "hour_utc",
        "spread_regime",
        "atr24_bucket",
        "prior_ret24_regime",
        "prior_ret72_regime",
        "trigger_severity_bucket",
    ]

    candidate_summary = summarize_candidates(event_rows, specs, cost_bps=float(args.cost_bps), extra_slip=extra_slip)
    bucket_summary = summarize_buckets(
        event_rows,
        dimensions=dimensions,
        cost_bps=float(args.cost_bps),
        extra_slip=extra_slip,
        min_bucket_events=int(args.min_bucket_events),
    )
    cross_matrix = build_cross_matrix(event_rows, cost_bps=float(args.cost_bps), min_bucket_events=int(args.min_bucket_events))

    classification_counts = (
        candidate_summary["classification"].value_counts().to_dict() if not candidate_summary.empty and "classification" in candidate_summary else {}
    )
    bucket_classification_counts = (
        bucket_summary["classification"].value_counts().to_dict() if not bucket_summary.empty and "classification" in bucket_summary else {}
    )
    cross_classification_counts = (
        cross_matrix["classification"].value_counts().to_dict() if not cross_matrix.empty and "classification" in cross_matrix else {}
    )

    condition_candidate_watch_count = int(
        (candidate_summary.get("classification", pd.Series(dtype=str)) == "CONDITION_RESEARCH_WATCH_ONLY_NO_PROMOTION").sum()
    ) if not candidate_summary.empty else 0
    condition_bucket_watch_count = int(
        (bucket_summary.get("classification", pd.Series(dtype=str)) == "CONDITION_BUCKET_WATCH_ONLY_NO_PROMOTION").sum()
    ) if not bucket_summary.empty else 0

    outputs = {
        "candidate_summary_csv": str(out_dir / "stage39c_condition_candidate_summary.csv"),
        "bucket_summary_csv": str(out_dir / "stage39c_condition_bucket_summary.csv"),
        "event_rows_csv": str(out_dir / "stage39c_condition_event_rows.csv"),
        "cross_matrix_csv": str(out_dir / "stage39c_condition_cross_matrix.csv"),
        "summary_json": str(out_dir / "stage39c_condition_diagnostic_summary.json"),
        "markdown": str(out_dir / "stage39c_microstructure_session_condition.md"),
    }

    candidate_summary.to_csv(outputs["candidate_summary_csv"], index=False)
    bucket_summary.to_csv(outputs["bucket_summary_csv"], index=False)
    event_rows.to_csv(outputs["event_rows_csv"], index=False)
    cross_matrix.to_csv(outputs["cross_matrix_csv"], index=False)

    summary = {
        "stage": STAGE,
        "decision_scope": DECISION_SCOPE,
        "promotion": "NO_GO",
        "ea": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "data_audit": data_audit,
        "parameters": {
            "symbol": args.symbol,
            "source": args.source,
            "timeframe": args.timeframe,
            "cost_bps": float(args.cost_bps),
            "extra_slippage_bps": extra_slip,
            "stage39b_summary": args.stage39b_summary,
            "stage39b_event_rows": args.stage39b_event_rows,
            "force_recompute_events": bool(args.force_recompute_events),
            "min_bucket_events": int(args.min_bucket_events),
            "bar_hours": float(bar_hours),
        },
        "stage39b_context": {
            "candidate_source": specs_info,
            "candidate_count": len(specs),
            "candidate_specs": [asdict(sp) for sp in specs],
            "allowed_input_classification": "PATH_DIAGNOSTIC_WATCH_ONLY_NO_PROMOTION",
        },
        "event_build_info": event_info,
        "classification_counts": classification_counts,
        "bucket_classification_counts": bucket_classification_counts,
        "cross_classification_counts": cross_classification_counts,
        "condition_candidate_watch_count": condition_candidate_watch_count,
        "condition_bucket_watch_count": condition_bucket_watch_count,
        "event_rows_written": int(len(event_rows)),
        "outputs": outputs,
        "top_condition_buckets_by_cost_mean": (
            bucket_summary.sort_values("cost_stressed_mean_bps", ascending=False).head(20).to_dict(orient="records")
            if not bucket_summary.empty and "cost_stressed_mean_bps" in bucket_summary.columns
            else []
        ),
    }

    Path(outputs["summary_json"]).write_text(json.dumps(safe_json(summary), ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(
        Path(outputs["markdown"]),
        data_audit=data_audit,
        specs_info=specs_info,
        event_info=event_info,
        candidate_summary=candidate_summary,
        bucket_summary=bucket_summary,
        cross_matrix=cross_matrix,
        summary=summary,
    )

    print(json.dumps(
        {
            "stage": STAGE,
            "promotion": "NO_GO",
            "condition_candidate_watch_count": condition_candidate_watch_count,
            "condition_bucket_watch_count": condition_bucket_watch_count,
            "outputs": outputs,
        },
        ensure_ascii=False,
        indent=2,
    ))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", required=True, help="SQLite DB path, e.g. data/local/xauusd_local_store.sqlite")
    p.add_argument("--table", default="bars", help="Bars table name")
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--source", default="amarkets_mt5")
    p.add_argument("--timeframe", default="H1")
    p.add_argument("--stage39b-summary", default="reports/stage39b/stage39b_event_path_diagnostic_summary.json")
    p.add_argument("--stage39b-event-rows", default="reports/stage39b/stage39b_event_path_event_rows.csv")
    p.add_argument("--force-recompute-events", action="store_true")
    p.add_argument("--cost-bps", type=float, default=8.0)
    p.add_argument("--extra-slippage-bps", default="0,4,8,12,16")
    p.add_argument("--min-bucket-events", type=int, default=30)
    p.add_argument("--output-dir", default="reports/stage39c")
    p.add_argument("--max-rows", type=int, default=None)
    return p.parse_args()


def main() -> None:
    run(parse_args())


if __name__ == "__main__":
    main()
