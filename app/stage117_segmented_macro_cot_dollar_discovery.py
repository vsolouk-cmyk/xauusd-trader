#!/usr/bin/env python3
"""
Stage117_SEGMENTED_MACRO_COT_DOLLAR_DISCOVERY

Data-only segmented discovery using Stage115/116 feature-grade inputs and AMarkets H1 bars.
No order, no MT5, no EA, no broker connection.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import numpy as np
    import pandas as pd
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"Stage117 requires pandas/numpy: {exc}")


STAGE = "Stage117_SEGMENTED_MACRO_COT_DOLLAR_DISCOVERY"
STATUS = "STAGE117_COMPLETE_SEGMENTED_DISCOVERY_NO_PROMOTION"
DECISION = "STAGE117_SEGMENTED_DISCOVERY_REVIEW_READY_NO_ORDER"

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_MT5_OR_EA_CHANGE_FROM_STAGE117",
    "NO_EA_CHANGE",
    "NO_PAPER_LIVE",
    "NO_LIVE",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dirs(root: Path) -> Tuple[Path, Path]:
    report_dir = root / "reports" / "stage117_segmented_macro_cot_dollar_discovery"
    feature_dir = root / "data" / "fundamental_event_inbox" / "features"
    report_dir.mkdir(parents=True, exist_ok=True)
    feature_dir.mkdir(parents=True, exist_ok=True)
    return report_dir, feature_dir


def safe_to_csv(df: pd.DataFrame, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return str(path)


def write_json(obj: dict, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)


def normalize_colname(c: str) -> str:
    c = str(c).strip().lower()
    c = re.sub(r"[^a-z0-9]+", "_", c)
    return re.sub(r"_+", "_", c).strip("_")


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [normalize_colname(c) for c in out.columns]
    return out


def parse_datetime_series(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce", utc=True)


def first_existing_col(df: pd.DataFrame, names: Sequence[str]) -> Optional[str]:
    cols = set(df.columns)
    for n in names:
        nn = normalize_colname(n)
        if nn in cols:
            return nn
    return None


def coerce_numeric(df: pd.DataFrame, exclude: Sequence[str] = ()) -> pd.DataFrame:
    out = df.copy()
    ex = set(exclude)
    for c in out.columns:
        if c in ex:
            continue
        if out[c].dtype == object:
            out[c] = (
                out[c]
                .astype(str)
                .str.replace(",", "", regex=False)
                .str.replace("%", "", regex=False)
                .str.strip()
                .replace({"": np.nan, ".": np.nan, "nan": np.nan, "None": np.nan})
            )
        converted = pd.to_numeric(out[c], errors="coerce")
        # pandas>=3 rejects errors="ignore".  Stage117 numeric feature inputs
        # should be numeric after cleaning; non-numeric residue is safer as NaN
        # than as object dtype, because quantiles and threshold logic need floats.
        out[c] = converted
    return out


def find_sqlite_candidates(root: Path) -> List[Path]:
    candidates: List[Path] = []
    for folder in [root / "data" / "local", root / "data"]:
        if folder.exists():
            candidates.extend(folder.rglob("*.db"))
            candidates.extend(folder.rglob("*.sqlite"))
            candidates.extend(folder.rglob("*.sqlite3"))
    # Keep deterministic order, prefer local.
    return sorted(set(candidates), key=lambda p: (0 if "data/local" in str(p) else 1, len(str(p)), str(p)))


def try_load_bars_from_sqlite(db_path: Path, timeframe: str = "h1") -> Optional[pd.DataFrame]:
    try:
        con = sqlite3.connect(str(db_path))
        cur = con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        if "bars" not in tables:
            con.close()
            return None

        info = pd.read_sql_query("PRAGMA table_info(bars)", con)
        cols = set(info["name"].astype(str).str.lower())
        if not {"open", "high", "low", "close"}.issubset(cols):
            con.close()
            return None

        time_col = "utc_time" if "utc_time" in cols else ("time" if "time" in cols else None)
        if not time_col:
            con.close()
            return None

        query = f"SELECT * FROM bars"
        where = []
        if "timeframe" in cols:
            where.append("lower(timeframe) in ('h1','1h','60m','60min')")
        if "symbol" in cols:
            where.append("(lower(symbol) like '%xau%' or lower(symbol) like '%gold%')")
        if where:
            query += " WHERE " + " AND ".join(where)
        df = pd.read_sql_query(query, con)
        con.close()
        if df.empty:
            return None
        df = normalize_columns(df)
        time_col = "utc_time" if "utc_time" in df.columns else ("time" if "time" in df.columns else None)
        df["utc_time"] = parse_datetime_series(df[time_col])
        for c in ["open", "high", "low", "close"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=["utc_time", "open", "high", "low", "close"]).sort_values("utc_time")
        if len(df) < 1000:
            return None
        return df[["utc_time", "open", "high", "low", "close"] + [c for c in df.columns if c not in {"utc_time","open","high","low","close"}]]
    except Exception:
        return None


def find_csv_bar_candidates(root: Path, inbox: Optional[Path]) -> List[Path]:
    names = [
        "amarkets_xauusd_1h.csv",
        "amarkets_xauusd_h1.csv",
        "*amarkets*xauusd*1h*.csv",
        "*amarkets*xauusd*h1*.csv",
    ]
    folders = [root, root / "data", root / "data" / "fundamental_event_inbox", root / "data" / "fundamental_event_inbox" / "raw"]
    if inbox:
        folders.append(inbox)
    home = Path.home()
    folders.append(home / "Downloads")
    out: List[Path] = []
    for folder in folders:
        if not folder.exists():
            continue
        for pat in names:
            out.extend(folder.rglob(pat) if folder.is_dir() else [])
    return sorted(set(out), key=lambda p: (len(str(p)), str(p)))


def try_load_bars_from_csv(path: Path) -> Optional[pd.DataFrame]:
    try:
        df = pd.read_csv(path)
    except Exception:
        # Some MT5 exports can be tab-separated.
        try:
            df = pd.read_csv(path, sep="\t")
        except Exception:
            return None
    if df.empty:
        return None
    df = normalize_columns(df)
    time_col = first_existing_col(df, ["utc_time", "time_utc", "datetime", "time", "date"])
    if not time_col:
        return None

    # MT5 can split date/time.
    if time_col == "date" and "time" in df.columns:
        dt = df["date"].astype(str) + " " + df["time"].astype(str)
    else:
        dt = df[time_col]

    df["utc_time"] = parse_datetime_series(dt)
    # common column aliases
    alias = {
        "open": ["open", "o"],
        "high": ["high", "h"],
        "low": ["low", "l"],
        "close": ["close", "c"],
    }
    for out_col, names in alias.items():
        col = first_existing_col(df, names)
        if col and col != out_col:
            df[out_col] = df[col]
    if not {"open", "high", "low", "close"}.issubset(df.columns):
        return None
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["utc_time", "open", "high", "low", "close"]).sort_values("utc_time")
    if len(df) < 1000:
        return None
    return df[["utc_time", "open", "high", "low", "close"] + [c for c in df.columns if c not in {"utc_time","open","high","low","close"}]]


def load_h1_bars(root: Path, inbox: Optional[Path]) -> Tuple[pd.DataFrame, Dict[str, object]]:
    meta: Dict[str, object] = {"source": None, "path": None, "rows": 0}
    for db in find_sqlite_candidates(root):
        df = try_load_bars_from_sqlite(db)
        if df is not None:
            meta.update({"source": "sqlite_bars", "path": str(db), "rows": int(len(df))})
            return df, meta

    for csv_path in find_csv_bar_candidates(root, inbox):
        df = try_load_bars_from_csv(csv_path)
        if df is not None:
            meta.update({"source": "csv_bars", "path": str(csv_path), "rows": int(len(df))})
            return df, meta

    raise RuntimeError("Could not find usable H1 AMarkets/XAUUSD bars in SQLite or CSV candidates.")


def load_csv_optional(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return normalize_columns(pd.read_csv(path))
    except Exception:
        return pd.DataFrame()


def prepare_daily_macro(root: Path, feature_dir: Path) -> Tuple[pd.DataFrame, Dict[str, object]]:
    panel_path = feature_dir / "stage115_daily_macro_feature_panel.csv"
    dollar_path = feature_dir / "stage116_validated_dollar_pressure.csv"
    macro = load_csv_optional(panel_path)
    if macro.empty:
        raise RuntimeError(f"Missing or unreadable {panel_path}")
    date_col = first_existing_col(macro, ["date", "utc_date", "observation_date", "time", "datetime"])
    if not date_col:
        raise RuntimeError(f"No date column in {panel_path}")
    macro["date"] = pd.to_datetime(macro[date_col], errors="coerce").dt.tz_localize(None)
    macro = macro.dropna(subset=["date"]).sort_values("date")
    macro = coerce_numeric(macro, exclude=["date"])

    dollar = load_csv_optional(dollar_path)
    if not dollar.empty:
        dcol = first_existing_col(dollar, ["date", "utc_date", "observation_date", "time", "datetime"])
        valcol = first_existing_col(dollar, ["dollar_pressure_index", "DTWEXBGS", "dtwexbgs", "close", "value"])
        if dcol and valcol:
            dollar["date"] = pd.to_datetime(dollar[dcol], errors="coerce").dt.tz_localize(None)
            dollar["dollar_pressure_index_validated"] = pd.to_numeric(dollar[valcol], errors="coerce")
            dollar = dollar[["date", "dollar_pressure_index_validated"]].dropna(subset=["date"]).sort_values("date")
            macro = pd.merge_asof(macro.sort_values("date"), dollar.sort_values("date"), on="date", direction="backward")

    # Create canonical aliases.
    if "dollar_pressure_index_validated" in macro.columns:
        macro["dollar_pressure"] = pd.to_numeric(macro["dollar_pressure_index_validated"], errors="coerce")
    else:
        dc = first_existing_col(macro, ["dollar_pressure_index", "dtwexbgs", "DTWEXBGS"])
        if dc:
            macro["dollar_pressure"] = pd.to_numeric(macro[dc], errors="coerce")

    ry = first_existing_col(macro, ["dfii10", "real_yield", "real_yield_10y"])
    if ry:
        macro["real_yield_10y"] = pd.to_numeric(macro[ry], errors="coerce")
    vix = first_existing_col(macro, ["vixcls", "vix"])
    if vix:
        macro["vix"] = pd.to_numeric(macro[vix], errors="coerce")
    dgs10 = first_existing_col(macro, ["dgs10", "nominal_10y"])
    if dgs10:
        macro["us10y"] = pd.to_numeric(macro[dgs10], errors="coerce")
    t10 = first_existing_col(macro, ["t10yie", "breakeven_10y"])
    if t10:
        macro["breakeven_10y"] = pd.to_numeric(macro[t10], errors="coerce")
    hy = first_existing_col(macro, ["bamlh0a0hym2", "hy_spread"])
    if hy:
        macro["hy_spread"] = pd.to_numeric(macro[hy], errors="coerce")

    for base in ["dollar_pressure", "real_yield_10y", "vix", "us10y", "breakeven_10y", "hy_spread"]:
        if base in macro.columns:
            macro[f"{base}_chg_20d"] = macro[base] - macro[base].shift(20)
            macro[f"{base}_chg_60d"] = macro[base] - macro[base].shift(60)
            roll = macro[base].rolling(252, min_periods=60)
            macro[f"{base}_z_252d"] = (macro[base] - roll.mean()) / roll.std(ddof=0)

    keep = ["date"] + [c for c in macro.columns if c not in {"date"} and pd.api.types.is_numeric_dtype(macro[c])]
    meta = {
        "path": str(panel_path),
        "rows": int(len(macro)),
        "has_validated_dollar_pressure": bool("dollar_pressure_index_validated" in macro.columns),
        "canonical_features": [c for c in keep if c != "date"],
    }
    return macro[keep].drop_duplicates(subset=["date"]).sort_values("date"), meta


def prepare_cot(root: Path, feature_dir: Path) -> Tuple[pd.DataFrame, Dict[str, object]]:
    path = feature_dir / "stage115_cot_gold_weekly_features.csv"
    cot = load_csv_optional(path)
    if cot.empty:
        return pd.DataFrame(), {"path": str(path), "rows": 0, "status": "missing"}
    date_col = first_existing_col(cot, ["date", "report_date", "report_date_as_yyyy_mm_dd", "as_of_date", "week"])
    if not date_col:
        return pd.DataFrame(), {"path": str(path), "rows": int(len(cot)), "status": "no_date_col"}
    cot["date"] = pd.to_datetime(cot[date_col], errors="coerce").dt.tz_localize(None)
    cot = cot.dropna(subset=["date"]).sort_values("date")
    cot = coerce_numeric(cot, exclude=["date"])

    # canonical numeric aliases based on likely COT feature names.
    numeric_cols = [c for c in cot.columns if c != "date" and pd.api.types.is_numeric_dtype(cot[c])]
    for c in numeric_cols:
        if "managed" in c and "net" in c and "cot_mm_net" not in cot:
            cot["cot_mm_net"] = cot[c]
        if ("money" in c and "net" in c) and "cot_mm_net" not in cot:
            cot["cot_mm_net"] = cot[c]
        if "z" in c and "mm" in c and "cot_mm_net_z" not in cot:
            cot["cot_mm_net_z"] = cot[c]
        if "decrowd" in c and "4" in c and "cot_decrowd_4w" not in cot:
            cot["cot_decrowd_4w"] = cot[c]
        if "decrowd" in c and "12" in c and "cot_decrowd_12w" not in cot:
            cot["cot_decrowd_12w"] = cot[c]

    if "cot_mm_net" in cot.columns and "cot_mm_net_z" not in cot.columns:
        roll = cot["cot_mm_net"].rolling(156, min_periods=52)
        cot["cot_mm_net_z"] = (cot["cot_mm_net"] - roll.mean()) / roll.std(ddof=0)
    if "cot_mm_net" in cot.columns:
        cot["cot_mm_net_chg_4w"] = cot["cot_mm_net"] - cot["cot_mm_net"].shift(4)
        cot["cot_mm_net_chg_12w"] = cot["cot_mm_net"] - cot["cot_mm_net"].shift(12)
        if "cot_decrowd_4w" not in cot.columns:
            cot["cot_decrowd_4w"] = -cot["cot_mm_net_chg_4w"]
        if "cot_decrowd_12w" not in cot.columns:
            cot["cot_decrowd_12w"] = -cot["cot_mm_net_chg_12w"]

    keep = ["date"] + [c for c in cot.columns if c != "date" and pd.api.types.is_numeric_dtype(cot[c])]
    meta = {"path": str(path), "rows": int(len(cot)), "status": "ok", "features": [c for c in keep if c != "date"]}
    return cot[keep].drop_duplicates(subset=["date"]).sort_values("date"), meta


def prepare_spdr(root: Path, feature_dir: Path) -> Tuple[pd.DataFrame, Dict[str, object]]:
    path = feature_dir / "stage116_validated_spdr_gld_long.csv"
    spdr = load_csv_optional(path)
    if spdr.empty:
        return pd.DataFrame(), {"path": str(path), "rows": 0, "status": "missing"}
    date_col = first_existing_col(spdr, ["date", "utc_date", "as_of_date", "time", "datetime"])
    value_col = first_existing_col(spdr, ["value", "numeric_value", "close", "tonnes", "ounces", "shares", "nav"])
    field_col = first_existing_col(spdr, ["field", "metric", "column", "name"])
    if not date_col or not value_col:
        return pd.DataFrame(), {"path": str(path), "rows": int(len(spdr)), "status": "no_date_or_value"}
    spdr["date"] = pd.to_datetime(spdr[date_col], errors="coerce").dt.tz_localize(None)
    spdr["value"] = pd.to_numeric(spdr[value_col], errors="coerce")
    spdr = spdr.dropna(subset=["date", "value"]).sort_values("date")
    if field_col:
        # Prefer holdings/ounces/tonnes-like fields if present.
        mask = spdr[field_col].astype(str).str.lower().str.contains("tonne|ounce|holding|gold|nav|share", regex=True, na=False)
        if mask.any():
            spdr = spdr[mask]
        # Aggregate first to avoid exploding H1 joins.
        agg = spdr.groupby("date", as_index=False)["value"].mean()
    else:
        agg = spdr.groupby("date", as_index=False)["value"].mean()
    agg = agg.sort_values("date")
    agg["spdr_value"] = agg["value"]
    agg["spdr_value_chg_20d"] = agg["spdr_value"] - agg["spdr_value"].shift(20)
    agg["spdr_value_chg_60d"] = agg["spdr_value"] - agg["spdr_value"].shift(60)
    meta = {"path": str(path), "rows": int(len(agg)), "status": "ok"}
    return agg[["date", "spdr_value", "spdr_value_chg_20d", "spdr_value_chg_60d"]], meta


def join_features_to_bars(bars: pd.DataFrame, macro: pd.DataFrame, cot: pd.DataFrame, spdr: pd.DataFrame) -> pd.DataFrame:
    df = bars.copy().sort_values("utc_time")
    df["date"] = df["utc_time"].dt.tz_convert(None).dt.floor("D")

    merged = pd.merge_asof(
        df.sort_values("date"),
        macro.sort_values("date"),
        on="date",
        direction="backward",
    ).sort_values("utc_time")

    if not cot.empty:
        merged = pd.merge_asof(
            merged.sort_values("date"),
            cot.sort_values("date"),
            on="date",
            direction="backward",
            suffixes=("", "_cotdup"),
        ).sort_values("utc_time")

    if not spdr.empty:
        merged = pd.merge_asof(
            merged.sort_values("date"),
            spdr.sort_values("date"),
            on="date",
            direction="backward",
            suffixes=("", "_spdrdup"),
        ).sort_values("utc_time")

    merged["fwd_close_h120"] = merged["close"].shift(-120)
    merged["fwd_ret_bps_h120"] = (merged["fwd_close_h120"] / merged["close"] - 1.0) * 10000.0
    merged["year"] = merged["utc_time"].dt.year
    merged["hour"] = merged["utc_time"].dt.hour
    return merged.dropna(subset=["fwd_ret_bps_h120"])


@dataclass
class RuleSpec:
    rule_id: str
    description: str
    min_features: List[str]
    expression_name: str


def quantile(series: pd.Series, q: float) -> float:
    v = pd.to_numeric(series, errors="coerce").dropna()
    if v.empty:
        return float("nan")
    return float(v.quantile(q))


def build_thresholds(selection: pd.DataFrame) -> Dict[str, float]:
    feats = [
        "real_yield_10y_chg_20d", "real_yield_10y_chg_60d",
        "dollar_pressure_chg_20d", "dollar_pressure_chg_60d",
        "vix_chg_20d", "vix_z_252d",
        "cot_mm_net_z", "cot_mm_net_chg_4w", "cot_mm_net_chg_12w",
        "cot_decrowd_4w", "cot_decrowd_12w",
        "spdr_value_chg_20d", "spdr_value_chg_60d",
    ]
    out: Dict[str, float] = {}
    for f in feats:
        if f in selection.columns:
            out[f"{f}_q25"] = quantile(selection[f], 0.25)
            out[f"{f}_q50"] = quantile(selection[f], 0.50)
            out[f"{f}_q75"] = quantile(selection[f], 0.75)
    return out


def has_cols(df: pd.DataFrame, cols: Sequence[str]) -> bool:
    return all(c in df.columns for c in cols)


def make_rule_mask(df: pd.DataFrame, rule: RuleSpec, th: Dict[str, float]) -> pd.Series:
    idx = df.index
    false = pd.Series(False, index=idx)

    def col(c: str) -> pd.Series:
        return pd.to_numeric(df[c], errors="coerce") if c in df.columns else pd.Series(np.nan, index=idx)

    if not has_cols(df, rule.min_features):
        return false

    if rule.expression_name == "RY_DOWN_DOLLAR_DOWN_COT_NOT_CROWDED":
        return (
            (col("real_yield_10y_chg_20d") <= th.get("real_yield_10y_chg_20d_q25", -0.05)) &
            (col("dollar_pressure_chg_20d") <= th.get("dollar_pressure_chg_20d_q25", -0.5)) &
            (col("cot_mm_net_z") <= 1.0)
        ).fillna(False)

    if rule.expression_name == "RY_DOWN_DOLLAR_RELIEF_COT_DECROWD":
        return (
            (col("real_yield_10y_chg_60d") <= th.get("real_yield_10y_chg_60d_q25", -0.1)) &
            (col("dollar_pressure_chg_20d") <= th.get("dollar_pressure_chg_20d_q50", 0.0)) &
            ((col("cot_decrowd_4w") > th.get("cot_decrowd_4w_q50", 0.0)) | (col("cot_decrowd_12w") > th.get("cot_decrowd_12w_q50", 0.0)))
        ).fillna(False)

    if rule.expression_name == "SAFE_HAVEN_VIX_UP_DOLLAR_NOT_UP":
        return (
            (col("vix_chg_20d") >= th.get("vix_chg_20d_q75", 1.0)) &
            (col("dollar_pressure_chg_20d") <= th.get("dollar_pressure_chg_20d_q50", 0.0)) &
            (col("real_yield_10y_chg_20d") <= th.get("real_yield_10y_chg_20d_q50", 0.0))
        ).fillna(False)

    if rule.expression_name == "DOLLAR_PRESSURE_REVERSAL":
        return (
            (col("dollar_pressure_z_252d") >= th.get("dollar_pressure_z_252d_q75", 1.0) if "dollar_pressure_z_252d_q75" in th else col("dollar_pressure_chg_60d") >= th.get("dollar_pressure_chg_60d_q75", 1.0)) &
            (col("dollar_pressure_chg_20d") <= th.get("dollar_pressure_chg_20d_q25", -0.5))
        ).fillna(False)

    if rule.expression_name == "COT_DECROWDING_ONLY_WITH_MACRO_RELIEF":
        return (
            (col("cot_mm_net_z") >= -0.5) &
            (col("cot_decrowd_12w") >= th.get("cot_decrowd_12w_q75", 0.0)) &
            (col("real_yield_10y_chg_20d") <= th.get("real_yield_10y_chg_20d_q50", 0.0))
        ).fillna(False)

    if rule.expression_name == "SPDR_FLOW_SUPPORT_MACRO_RELIEF":
        return (
            (col("spdr_value_chg_20d") >= th.get("spdr_value_chg_20d_q75", 0.0)) &
            (col("dollar_pressure_chg_20d") <= th.get("dollar_pressure_chg_20d_q50", 0.0)) &
            (col("real_yield_10y_chg_20d") <= th.get("real_yield_10y_chg_20d_q50", 0.0))
        ).fillna(False)

    return false


RULES = [
    RuleSpec("S117_01_RY_DOWN_DOLLAR_DOWN_COT_NOT_CROWDED", "Real-yield decline + dollar-pressure decline + COT not crowded", ["real_yield_10y_chg_20d", "dollar_pressure_chg_20d", "cot_mm_net_z"], "RY_DOWN_DOLLAR_DOWN_COT_NOT_CROWDED"),
    RuleSpec("S117_02_RY_DOWN_DOLLAR_RELIEF_COT_DECROWD", "60d real-yield relief + dollar not rising + COT decrowding", ["real_yield_10y_chg_60d", "dollar_pressure_chg_20d", "cot_decrowd_4w", "cot_decrowd_12w"], "RY_DOWN_DOLLAR_RELIEF_COT_DECROWD"),
    RuleSpec("S117_03_SAFE_HAVEN_VIX_UP_DOLLAR_NOT_UP", "VIX up but dollar not up, real-yield relief", ["vix_chg_20d", "dollar_pressure_chg_20d", "real_yield_10y_chg_20d"], "SAFE_HAVEN_VIX_UP_DOLLAR_NOT_UP"),
    RuleSpec("S117_04_DOLLAR_PRESSURE_REVERSAL", "Dollar-pressure reversal proxy", ["dollar_pressure_chg_20d", "dollar_pressure_chg_60d"], "DOLLAR_PRESSURE_REVERSAL"),
    RuleSpec("S117_05_COT_DECROWDING_MACRO_RELIEF", "COT decrowding with real-yield relief", ["cot_mm_net_z", "cot_decrowd_12w", "real_yield_10y_chg_20d"], "COT_DECROWDING_ONLY_WITH_MACRO_RELIEF"),
    RuleSpec("S117_06_SPDR_FLOW_SUPPORT_MACRO_RELIEF", "SPDR support with macro relief, candidate-only", ["spdr_value_chg_20d", "dollar_pressure_chg_20d", "real_yield_10y_chg_20d"], "SPDR_FLOW_SUPPORT_MACRO_RELIEF"),
]


def split_by_time(df: pd.DataFrame) -> pd.Series:
    df = df.sort_values("utc_time")
    n = len(df)
    labels = pd.Series(index=df.index, dtype="object")
    i1 = int(n * 0.60)
    i2 = int(n * 0.80)
    labels.iloc[:i1] = "selection"
    labels.iloc[i1:i2] = "validation"
    labels.iloc[i2:] = "tail_forward_proxy"
    return labels


def evaluate_mask(df: pd.DataFrame, mask: pd.Series) -> Dict[str, object]:
    ev = df.loc[mask.fillna(False)].copy()
    n = len(ev)
    if n == 0:
        return {
            "events": 0,
            "mean_bps": np.nan,
            "median_bps": np.nan,
            "hit_rate": np.nan,
            "p10_bps": np.nan,
            "p90_bps": np.nan,
            "worst_bps": np.nan,
            "best_bps": np.nan,
            "max_year_concentration_pct": np.nan,
        }
    rets = pd.to_numeric(ev["fwd_ret_bps_h120"], errors="coerce").dropna()
    year_counts = ev["year"].value_counts(normalize=True) * 100.0
    return {
        "events": int(n),
        "mean_bps": float(rets.mean()),
        "median_bps": float(rets.median()),
        "hit_rate": float((rets > 0).mean()),
        "p10_bps": float(rets.quantile(0.10)),
        "p90_bps": float(rets.quantile(0.90)),
        "worst_bps": float(rets.min()),
        "best_bps": float(rets.max()),
        "max_year_concentration_pct": float(year_counts.max()) if not year_counts.empty else np.nan,
    }


def evaluate_rules(df: pd.DataFrame, thresholds: Dict[str, float]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    rows: List[Dict[str, object]] = []
    selected_rows: List[Dict[str, object]] = []
    for rule in RULES:
        mask = make_rule_mask(df, rule, thresholds)
        row: Dict[str, object] = {
            "rule_id": rule.rule_id,
            "description": rule.description,
            "required_features": ",".join(rule.min_features),
            "feature_available": bool(has_cols(df, rule.min_features)),
            "is_candidate_only": bool("SPDR" in rule.rule_id),
        }
        for split in ["selection", "validation", "tail_forward_proxy"]:
            stats = evaluate_mask(df[df["split"] == split], mask[df["split"] == split])
            for k, v in stats.items():
                row[f"{split}_{k}"] = v

        all_stats = evaluate_mask(df, mask)
        for k, v in all_stats.items():
            row[f"all_{k}"] = v

        # Conservative review gate; not a promotion gate.
        pass_review = (
            bool(row["feature_available"]) and
            row.get("selection_events", 0) >= 30 and
            row.get("validation_events", 0) >= 15 and
            row.get("tail_forward_proxy_events", 0) >= 10 and
            float(row.get("validation_mean_bps", np.nan)) > 0.0 and
            float(row.get("tail_forward_proxy_mean_bps", np.nan)) > 0.0 and
            float(row.get("tail_forward_proxy_hit_rate", 0.0)) >= 0.50 and
            float(row.get("tail_forward_proxy_max_year_concentration_pct", 100.0)) <= 80.0
        )
        row["review_gate"] = "PASS_REVIEW_QUEUE" if pass_review else "NO_PASS"
        rows.append(row)
        if pass_review:
            selected_rows.append(row)
    return pd.DataFrame(rows), pd.DataFrame(selected_rows)


def feature_coverage(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for c in df.columns:
        if c in {"utc_time", "date", "split"}:
            continue
        non_null = int(df[c].notna().sum())
        rows.append({
            "feature": c,
            "non_null_rows": non_null,
            "coverage_pct": round(100.0 * non_null / max(len(df), 1), 3),
            "dtype": str(df[c].dtype),
        })
    return pd.DataFrame(rows).sort_values(["coverage_pct", "feature"], ascending=[False, True])


def run(root: Path, inbox: Optional[Path] = None, horizon_hours: int = 120) -> dict:
    report_dir, feature_dir = ensure_dirs(root)

    bars, bars_meta = load_h1_bars(root, inbox)
    macro, macro_meta = prepare_daily_macro(root, feature_dir)
    cot, cot_meta = prepare_cot(root, feature_dir)
    spdr, spdr_meta = prepare_spdr(root, feature_dir)

    joined = join_features_to_bars(bars, macro, cot, spdr)
    if joined.empty:
        raise RuntimeError("Joined Stage117 dataset is empty after forward-return calculation.")

    joined["split"] = split_by_time(joined)
    splits = {
        "selection": joined[joined["split"] == "selection"],
        "validation": joined[joined["split"] == "validation"],
        "tail_forward_proxy": joined[joined["split"] == "tail_forward_proxy"],
    }
    thresholds = build_thresholds(splits["selection"])
    metrics, selected = evaluate_rules(joined, thresholds)
    coverage = feature_coverage(joined)

    split_paths = {}
    for name, sdf in splits.items():
        split_paths[name] = safe_to_csv(
            sdf[["utc_time", "open", "high", "low", "close", "fwd_ret_bps_h120", "split"] + [c for c in ["dollar_pressure", "real_yield_10y", "vix", "cot_mm_net_z", "cot_decrowd_4w", "cot_decrowd_12w", "spdr_value_chg_20d"] if c in sdf.columns]],
            report_dir / f"stage117_{name}_rows.csv",
        )

    candidate_metrics_path = safe_to_csv(metrics, report_dir / "stage117_candidate_metrics.csv")
    selected_path = safe_to_csv(selected, report_dir / "stage117_selected_for_stage118.csv")
    thresholds_path = safe_to_csv(pd.DataFrame([thresholds]), report_dir / "stage117_selection_thresholds.csv")
    coverage_path = safe_to_csv(coverage, report_dir / "stage117_feature_coverage.csv")

    joined_sample_cols = ["utc_time", "open", "high", "low", "close", "fwd_ret_bps_h120", "split"] + [
        c for c in [
            "dollar_pressure", "dollar_pressure_chg_20d", "real_yield_10y", "real_yield_10y_chg_20d",
            "vix", "vix_chg_20d", "cot_mm_net_z", "cot_decrowd_4w", "cot_decrowd_12w",
            "spdr_value", "spdr_value_chg_20d"
        ] if c in joined.columns
    ]
    joined_path = safe_to_csv(joined[joined_sample_cols], feature_dir / "stage117_joined_macro_cot_dollar_h1_research_dataset.csv")

    summary = {
        "stage": STAGE,
        "generated_utc": utc_now_iso(),
        "status": STATUS,
        "decision": DECISION,
        "classification": "SEGMENTED_DISCOVERY_ONLY_NO_ORDER",
        "hard_blocks": HARD_BLOCKS,
        "root": str(root),
        "inbox": str(inbox) if inbox else None,
        "bars_meta": bars_meta,
        "macro_meta": macro_meta,
        "cot_meta": cot_meta,
        "spdr_meta": spdr_meta,
        "joined_rows": int(len(joined)),
        "date_min": joined["utc_time"].min().isoformat() if len(joined) else None,
        "date_max": joined["utc_time"].max().isoformat() if len(joined) else None,
        "selection_rows": int(len(splits["selection"])),
        "validation_rows": int(len(splits["validation"])),
        "tail_forward_proxy_rows": int(len(splits["tail_forward_proxy"])),
        "candidate_rules_tested": int(len(metrics)),
        "review_gate_pass_count": int((metrics["review_gate"] == "PASS_REVIEW_QUEUE").sum()) if not metrics.empty else 0,
        "selected_rule_ids": selected["rule_id"].tolist() if not selected.empty else [],
        "joined_research_dataset": joined_path,
        "candidate_metrics": candidate_metrics_path,
        "selected_for_stage118": selected_path,
        "selection_thresholds": thresholds_path,
        "feature_coverage": coverage_path,
        "split_paths": split_paths,
        "next": [
            "If review_gate_pass_count > 0, run Stage118 hard audit / overlap review before any observer update.",
            "If no rule passes, use candidate_metrics and feature_coverage to design the next thesis scan.",
            "Do not touch MT5, EA, broker, paper-order, or live-order surfaces from Stage117 outputs.",
        ],
    }
    summary_path = write_json(summary, report_dir / "stage117_segmented_macro_cot_dollar_discovery_summary.json")
    summary["summary_json"] = summary_path

    report = [
        f"# {STAGE}",
        "",
        f"Generated UTC: {summary['generated_utc']}",
        "",
        f"Status: `{STATUS}`",
        f"Decision: `{DECISION}`",
        "",
        "## Interpretation",
        "",
        "Stage117 performs historical segmented discovery using Stage115 macro/COT data and Stage116 validated dollar-pressure/SPDR candidates. It is a data-only research stage and does not promote, trade, touch MT5, or modify the EA.",
        "",
        "## Key counts",
        "",
        f"- Joined rows: `{summary['joined_rows']}`",
        f"- Selection rows: `{summary['selection_rows']}`",
        f"- Validation rows: `{summary['validation_rows']}`",
        f"- Tail-forward-proxy rows: `{summary['tail_forward_proxy_rows']}`",
        f"- Candidate rules tested: `{summary['candidate_rules_tested']}`",
        f"- Review-gate pass count: `{summary['review_gate_pass_count']}`",
        "",
        "## Selected rule IDs",
        "",
        "```text",
        "\n".join(summary["selected_rule_ids"]) if summary["selected_rule_ids"] else "NONE",
        "```",
        "",
        "## Outputs",
        "",
        f"- Candidate metrics: `{candidate_metrics_path}`",
        f"- Selected for Stage118: `{selected_path}`",
        f"- Joined research dataset: `{joined_path}`",
        f"- Feature coverage: `{coverage_path}`",
        "",
        "## Hard blocks",
        "",
        "\n".join(f"- `{x}`" for x in HARD_BLOCKS),
        "",
    ]
    report_path = report_dir / "stage117_segmented_macro_cot_dollar_discovery_report.md"
    report_path.write_text("\n".join(report), encoding="utf-8")
    summary["report_md"] = str(report_path)
    write_json(summary, report_dir / "stage117_segmented_macro_cot_dollar_discovery_summary.json")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=STAGE)
    parser.add_argument("--root", default=".", help="Project root")
    parser.add_argument("--inbox", default=None, help="Manual inbox path")
    parser.add_argument("--horizon-hours", type=int, default=120, help="Forward horizon; currently fixed to 120 for outputs")
    args = parser.parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    inbox = Path(args.inbox).expanduser().resolve() if args.inbox else None
    run(root=root, inbox=inbox, horizon_hours=args.horizon_hours)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
