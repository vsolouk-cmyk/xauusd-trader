#!/usr/bin/env python3
"""Stage92 - thesis-first intraday/session residual discovery for XAUUSD.

This stage is intentionally research-only. It scans a small locked set of
session hypotheses using local AMarkets intraday CSVs and current macro
portfolio masks. It does not write MT5 files, does not alter EAs, and cannot
create orders.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

STAGE = "Stage92_INTRADAY_SESSION_RESIDUAL_THESIS_DISCOVERY"
NO_ORDER_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE92",
    "NO_THRESHOLD_TUNING_FROM_STAGE92_DISCOVERY",
    "NO_DIRECT_MT5_OR_EA_CHANGE_FROM_STAGE92",
]

DEFAULT_CONFIG = {
    "macro_dataset": "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
    "downloads_dir": "~/Downloads",
    "intraday_files": {
        "m15": [
            "~/Downloads/amarkets_xauusd_15m.csv",
            "~/Downloads/amarkets_xauusd_m15.csv",
            "~/Downloads/*xauusd*15*.csv",
            "~/Downloads/*XAUUSD*15*.csv",
        ],
        "m5": [
            "~/Downloads/amarkets_xauusd_5m.csv",
            "~/Downloads/amarkets_xauusd_m5.csv",
            "~/Downloads/*xauusd*5m*.csv",
            "~/Downloads/*XAUUSD*5m*.csv",
        ],
        "h1": [
            "~/Downloads/amarkets_xauusd_h1.csv",
            "~/Downloads/amarkets_xauusd_1h.csv",
            "~/Downloads/*xauusd*h1*.csv",
            "~/Downloads/*XAUUSD*h1*.csv",
        ],
    },
    "preferred_timeframe": "m15",
    "cost_bps_total_reference": 20.0,
    "asof_date": "2024-01-01",
    "candidate_top_n": 8,
    "constraints": {
        "min_total_entries": 20,
        "min_total_mean_net_bps": 0.0,
        "min_total_win_rate": 0.50,
        "max_abs_worst_loss_bps": 900.0,
        "min_locked_forward_entries": 3,
        "min_locked_forward_mean_bps": -25.0,
        "min_final_holdout_entries": 3,
        "min_final_holdout_mean_bps": 0.0,
        "min_post_asof_entries": 2,
        "min_post_asof_mean_bps": 0.0,
        "min_residual_entry_share": 0.50,
        "max_year_entry_share": 0.35,
        "max_missing_required_feature_rows": 0,
    },
}

TIME_COL_CANDIDATES = [
    "utc_time",
    "time_utc",
    "datetime_utc",
    "datetime",
    "timestamp",
    "time",
    "date",
    "Date",
    "Time",
    "<DATE>",
    "<TIME>",
    "Gmt time",
    "Gmt Time",
]
PRICE_ALIASES = {
    "open": ["open", "Open", "OPEN", "o", "<OPEN>"],
    "high": ["high", "High", "HIGH", "h", "<HIGH>"],
    "low": ["low", "Low", "LOW", "l", "<LOW>"],
    "close": ["close", "Close", "CLOSE", "c", "<CLOSE>"],
    "volume": ["volume", "Volume", "VOL", "tick_volume", "TickVolume", "<TICKVOL>", "<VOL>"],
    "spread": ["spread", "Spread", "SPREAD", "<SPREAD>"],
}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def expand_path(path: str, root: Path) -> Path:
    p = Path(os.path.expanduser(path))
    if not p.is_absolute():
        p = root / p
    return p


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_config(path: Optional[str]) -> Dict[str, Any]:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if path:
        with open(os.path.expanduser(path), "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
        cfg = merge_dict(cfg, user_cfg)
    return cfg


def merge_dict(base: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in update.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge_dict(out[k], v)
        else:
            out[k] = v
    return out


def sniff_delimiter(path: Path) -> str:
    with path.open("r", encoding="utf-8-sig", errors="ignore") as f:
        sample = f.read(4096)
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except Exception:
        return ","


def first_existing_globs(patterns: Sequence[str], root: Path) -> List[Path]:
    matches: List[Path] = []
    for pat in patterns:
        p = expand_path(pat, root)
        if any(ch in str(p) for ch in "*?["):
            matches.extend(sorted(p.parent.glob(p.name)))
        elif p.exists():
            matches.append(p)
    # unique, prefer largest/latest by row-ish file size
    seen = set()
    uniq = []
    for m in matches:
        rp = str(m.resolve())
        if rp not in seen and m.is_file():
            seen.add(rp)
            uniq.append(m)
    return sorted(uniq, key=lambda x: x.stat().st_size if x.exists() else 0, reverse=True)


def find_col(columns: Iterable[str], candidates: Sequence[str]) -> Optional[str]:
    cols = list(columns)
    lower_map = {str(c).strip().lower(): c for c in cols}
    for cand in candidates:
        if cand in cols:
            return cand
        lc = cand.strip().lower()
        if lc in lower_map:
            return lower_map[lc]
    return None


def normalize_intraday_csv(path: Path, sample_only: bool = False) -> pd.DataFrame:
    delim = sniff_delimiter(path)
    nrows = 250000 if sample_only else None
    df = pd.read_csv(path, sep=delim, encoding="utf-8-sig", low_memory=False, nrows=nrows)
    if df.empty:
        raise ValueError(f"empty csv: {path}")
    # strip BOM/spaces
    df.columns = [str(c).strip().replace("\ufeff", "") for c in df.columns]
    # Broker exports may have separate date/time columns, including MT5-style
    # headers such as <DATE> and <TIME>. Prefer combining those over treating
    # <DATE> alone as the full timestamp.
    date_like = None
    time_like = None
    for c in df.columns:
        cs = str(c).strip().lower().replace("<", "").replace(">", "")
        if cs == "date" or cs.endswith("date"):
            date_like = c
        if cs == "time" or cs.endswith("time"):
            time_like = c
    if date_like is not None and time_like is not None and date_like != time_like:
        dt = df[date_like].astype(str).str.replace(".", "-", regex=False) + " " + df[time_like].astype(str)
    else:
        time_col = find_col(df.columns, TIME_COL_CANDIDATES)
        if time_col is None:
            # Some broker exports have separate date/time as first two columns.
            if len(df.columns) >= 2 and re.search("date", df.columns[0], re.I) and re.search("time", df.columns[1], re.I):
                dt = df[df.columns[0]].astype(str).str.replace(".", "-", regex=False) + " " + df[df.columns[1]].astype(str)
            else:
                raise ValueError(f"could not infer datetime column in {path}; columns={list(df.columns)[:20]}")
        else:
            dt = df[time_col]
    out = pd.DataFrame()
    out["utc_time"] = pd.to_datetime(dt, errors="coerce", utc=True)
    for target, aliases in PRICE_ALIASES.items():
        col = find_col(df.columns, aliases)
        if col is not None:
            out[target] = pd.to_numeric(df[col], errors="coerce")
    required = ["open", "high", "low", "close"]
    missing = [c for c in required if c not in out.columns]
    if missing:
        raise ValueError(f"missing OHLC columns {missing} in {path}; columns={list(df.columns)[:20]}")
    out = out.dropna(subset=["utc_time", "open", "high", "low", "close"]).copy()
    out = out.sort_values("utc_time").drop_duplicates("utc_time")
    out["date"] = out["utc_time"].dt.date.astype(str)
    out["hour"] = out["utc_time"].dt.hour
    out["minute"] = out["utc_time"].dt.minute
    return out


def infer_timeframe_from_median_delta(df: pd.DataFrame) -> str:
    if len(df) < 3:
        return "unknown"
    deltas = df["utc_time"].diff().dropna().dt.total_seconds() / 60.0
    if deltas.empty:
        return "unknown"
    med = float(deltas.median())
    if med <= 1.5:
        return "m1"
    if 4 <= med <= 6:
        return "m5"
    if 13 <= med <= 17:
        return "m15"
    if 28 <= med <= 32:
        return "m30"
    if 55 <= med <= 65:
        return "h1"
    return f"m{int(round(med))}"


def load_preferred_intraday(root: Path, cfg: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any], List[Dict[str, Any]]]:
    inventories: List[Dict[str, Any]] = []
    best: Optional[Tuple[pd.DataFrame, Dict[str, Any]]] = None
    preferred = cfg.get("preferred_timeframe", "m15")
    order = [preferred, "m15", "m5", "h1", "m1"]
    seen_tfs = []
    for tf in order:
        if tf in seen_tfs:
            continue
        seen_tfs.append(tf)
        patterns = cfg.get("intraday_files", {}).get(tf, [])
        for path in first_existing_globs(patterns, root):
            rec: Dict[str, Any] = {"timeframe_hint": tf, "path": str(path), "exists": path.exists(), "read_ok": False}
            try:
                df = normalize_intraday_csv(path, sample_only=False)
                inferred = infer_timeframe_from_median_delta(df)
                rec.update({
                    "read_ok": True,
                    "rows": int(len(df)),
                    "inferred_timeframe": inferred,
                    "min_utc": df["utc_time"].min().isoformat(),
                    "max_utc": df["utc_time"].max().isoformat(),
                    "has_spread": "spread" in df.columns and bool(df["spread"].notna().any()),
                    "sha256": sha256_file(path),
                })
                inventories.append(rec)
                if inferred in {"m15", "m5"} or tf == preferred:
                    best = (df, rec)
                    return best[0], best[1], inventories
                if best is None:
                    best = (df, rec)
            except Exception as e:
                rec.update({"read_error": str(e)[:500]})
                inventories.append(rec)
    if best is None:
        raise FileNotFoundError("No readable intraday CSV found. Check configs/stage92_intraday_session_residual_thesis_discovery.json")
    return best[0], best[1], inventories


def load_macro(root: Path, cfg: Dict[str, Any]) -> pd.DataFrame:
    path = expand_path(cfg["macro_dataset"], root)
    if not path.exists():
        raise FileNotFoundError(f"macro dataset not found: {path}")
    df = pd.read_csv(path, low_memory=False)
    if "feature_date_utc" not in df.columns:
        raise ValueError("macro dataset missing feature_date_utc")
    df["feature_date_utc"] = pd.to_datetime(df["feature_date_utc"], errors="coerce", utc=True)
    df = df.dropna(subset=["feature_date_utc"]).sort_values("feature_date_utc").copy()
    df["date"] = df["feature_date_utc"].dt.date.astype(str)
    # numeric conversion guarded
    for c in df.columns:
        if c in {"date", "feature_date_utc", "sample_available_after_utc", "available_after_utc", "source"}:
            continue
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if "dxy_ret_120d" not in df.columns and "dxy" in df.columns:
        df["dxy_ret_120d"] = df["dxy"].pct_change(120)
    if "real_yield_change_120d" not in df.columns and "real_yield" in df.columns:
        df["real_yield_change_120d"] = df["real_yield"].diff(120)
    return df


def gt(s: pd.Series, x: float) -> pd.Series:
    return s.astype(float) > x


def lt(s: pd.Series, x: float) -> pd.Series:
    return s.astype(float) < x


def build_current_portfolio_active(macro: pd.DataFrame) -> pd.DataFrame:
    out = macro[["date"]].copy()
    # Missing columns produce all-false masks, never accidental true.
    def col(name: str) -> pd.Series:
        return macro[name] if name in macro.columns else pd.Series([math.nan] * len(macro), index=macro.index)
    k06 = gt(col("gold_sma20_over_50"), 0) & gt(col("dxy_ret_20d"), 0) & lt(col("real_yield_change_20d"), 0)
    k03 = gt(col("vix_change_20d"), 0) & lt(col("real_yield_change_20d"), 0)
    k07 = gt(col("gold_sma20_over_50"), 0) & lt(col("dxy_sma20_over_50"), 0)
    s8314 = lt(col("real_yield_change_120d"), 0) & lt(col("gold_sma20_over_50"), 0)
    s8313 = lt(col("dxy_ret_120d"), 0) & lt(col("gold_sma20_over_50"), 0)
    out["current_portfolio_active"] = (k06 | k03 | k07 | s8314 | s8313).fillna(False)
    out["k06_active"] = k06.fillna(False)
    return out


def first(series: pd.Series) -> float:
    return float(series.iloc[0]) if len(series) else math.nan


def last(series: pd.Series) -> float:
    return float(series.iloc[-1]) if len(series) else math.nan


def build_daily_session_features(intra: pd.DataFrame, macro: pd.DataFrame) -> pd.DataFrame:
    df = intra.copy()
    # Use UTC sessions. Conservative, deterministic, no broker timezone assumption.
    asia = df[(df["hour"] >= 0) & (df["hour"] < 7)]
    london = df[(df["hour"] >= 7) & (df["hour"] < 12)]
    ny = df[(df["hour"] >= 13) & (df["hour"] < 18)]
    day = df[(df["hour"] >= 0) & (df["hour"] < 22)]

    def agg_session(x: pd.DataFrame, prefix: str) -> pd.DataFrame:
        if x.empty:
            return pd.DataFrame(columns=["date"])
        g = x.groupby("date", sort=True)
        return pd.DataFrame({
            "date": g.size().index,
            f"{prefix}_open": g["open"].first().values,
            f"{prefix}_high": g["high"].max().values,
            f"{prefix}_low": g["low"].min().values,
            f"{prefix}_close": g["close"].last().values,
            f"{prefix}_bars": g.size().values,
        })

    features = agg_session(day, "day")
    for s, p in [(asia, "asia"), (london, "london"), (ny, "ny")]:
        features = features.merge(agg_session(s, p), on="date", how="left")
    for p in ["asia", "london", "ny", "day"]:
        if f"{p}_open" in features.columns and f"{p}_close" in features.columns:
            features[f"{p}_ret_bps"] = (features[f"{p}_close"] / features[f"{p}_open"] - 1.0) * 10000.0
        if f"{p}_high" in features.columns and f"{p}_low" in features.columns and f"{p}_close" in features.columns:
            features[f"{p}_range_bps"] = (features[f"{p}_high"] - features[f"{p}_low"]) / features[f"{p}_close"] * 10000.0
    features = features.sort_values("date").reset_index(drop=True)
    # outcomes from daily closes; entry approximations are session closes.
    features["next_day_close"] = features["day_close"].shift(-1)
    features["next_2d_close"] = features["day_close"].shift(-2)
    features["next_3d_close"] = features["day_close"].shift(-3)
    # Rolling quantiles shifted one day to avoid same-day lookahead threshold fitting.
    for c in ["asia_range_bps", "london_ret_bps", "day_ret_bps"]:
        if c in features.columns:
            features[f"{c}_q25_252d"] = features[c].rolling(252, min_periods=60).quantile(0.25).shift(1)
            features[f"{c}_q35_252d"] = features[c].rolling(252, min_periods=60).quantile(0.35).shift(1)
            features[f"{c}_q65_252d"] = features[c].rolling(252, min_periods=60).quantile(0.65).shift(1)
            features[f"{c}_q75_252d"] = features[c].rolling(252, min_periods=60).quantile(0.75).shift(1)
    # Breakout/reclaim features.
    features["london_breakout_up"] = (features.get("london_high") > features.get("asia_high")) & (features.get("london_close") > features.get("asia_high"))
    features["london_breakdown"] = (features.get("london_low") < features.get("asia_low"))
    features["ny_reclaim_asia_low"] = features.get("ny_close") > features.get("asia_low")
    features["ny_reclaim_asia_mid"] = features.get("ny_close") > ((features.get("asia_high") + features.get("asia_low")) / 2.0)

    pf = build_current_portfolio_active(macro)
    features = features.merge(pf, on="date", how="left")
    features["current_portfolio_active"] = features["current_portfolio_active"].fillna(False)
    # Join select macro filters for session thesis context.
    macro_cols = [c for c in ["date", "vix_change_20d", "real_yield_change_20d", "dxy_ret_20d", "gold_sma20_over_50"] if c in macro.columns]
    features = features.merge(macro[macro_cols], on="date", how="left", suffixes=("", "_macro"))
    return features


@dataclass
class CandidateRule:
    rule_id: str
    label: str
    bucket: str
    horizon_days: int
    entry_col: str
    exit_col: str
    condition_text: str


def candidate_rules() -> List[CandidateRule]:
    return [
        CandidateRule(
            "I92_01_ASIA_COMPRESSED_LONDON_BREAKOUT_H1D",
            "ASIA_COMPRESSED_LONDON_BREAKOUT",
            "session_breakout",
            1,
            "london_close",
            "next_day_close",
            "current_portfolio_inactive AND asia_range_bps<=rolling_q35 AND london_breakout_up",
        ),
        CandidateRule(
            "I92_02_ASIA_COMPRESSED_NY_RECLAIM_H1D",
            "ASIA_COMPRESSED_BREAKDOWN_NY_RECLAIM",
            "session_reclaim",
            1,
            "ny_close",
            "next_day_close",
            "current_portfolio_inactive AND asia_range_bps<=rolling_q35 AND london_breakdown AND ny_reclaim_asia_low",
        ),
        CandidateRule(
            "I92_03_LONDON_SELL_NY_RECLAIM_H1D",
            "LONDON_SELLOFF_NY_RECLAIM",
            "session_reversal",
            1,
            "ny_close",
            "next_day_close",
            "current_portfolio_inactive AND london_ret_bps<=rolling_q25 AND ny_ret_bps>0",
        ),
        CandidateRule(
            "I92_04_LONDON_SELL_NEXT2D_REVERSAL",
            "LONDON_SELLOFF_NEXT2D_REVERSAL",
            "session_reversal",
            2,
            "day_close",
            "next_2d_close",
            "current_portfolio_inactive AND london_ret_bps<=rolling_q25 AND day_ret_bps<0",
        ),
        CandidateRule(
            "I92_05_RISKOFF_INTRADAY_PULLBACK_H1D",
            "RISKOFF_INTRADAY_PULLBACK",
            "riskoff_session",
            1,
            "day_close",
            "next_day_close",
            "current_portfolio_inactive AND vix_change_20d>0 AND day_ret_bps<=rolling_q25",
        ),
        CandidateRule(
            "I92_06_DXY_UP_INTRADAY_RECLAIM_H1D",
            "DXY_UP_INTRADAY_RECLAIM",
            "headwind_absorption",
            1,
            "ny_close",
            "next_day_close",
            "current_portfolio_inactive AND dxy_ret_20d>0 AND london_breakdown AND ny_reclaim_asia_mid",
        ),
        CandidateRule(
            "I92_07_REALYIELD_UP_SESSION_RECLAIM_H1D",
            "REALYIELD_UP_SESSION_RECLAIM",
            "headwind_absorption",
            1,
            "ny_close",
            "next_day_close",
            "current_portfolio_inactive AND real_yield_change_20d>0 AND london_breakdown AND ny_reclaim_asia_mid",
        ),
        CandidateRule(
            "I92_08_LOW_RANGE_DAY_NEXT2D_CONTINUATION",
            "LOW_RANGE_DAY_NEXT2D_CONTINUATION",
            "volatility_compression",
            2,
            "day_close",
            "next_2d_close",
            "current_portfolio_inactive AND asia_range_bps<=rolling_q25 AND day_ret_bps>0",
        ),
    ]


def build_mask(df: pd.DataFrame, rule: CandidateRule) -> pd.Series:
    inactive = ~df["current_portfolio_active"].fillna(False).astype(bool)
    q35 = df.get("asia_range_bps_q35_252d", pd.Series([math.nan] * len(df), index=df.index))
    q25_asia = df.get("asia_range_bps_q25_252d", pd.Series([math.nan] * len(df), index=df.index))
    q25_london = df.get("london_ret_bps_q25_252d", pd.Series([math.nan] * len(df), index=df.index))
    q25_day = df.get("day_ret_bps_q25_252d", pd.Series([math.nan] * len(df), index=df.index))
    if rule.rule_id.endswith("BREAKOUT_H1D"):
        return inactive & (df["asia_range_bps"] <= q35) & df["london_breakout_up"].fillna(False)
    if rule.rule_id.endswith("NY_RECLAIM_H1D") and "ASIA_COMPRESSED" in rule.rule_id:
        return inactive & (df["asia_range_bps"] <= q35) & df["london_breakdown"].fillna(False) & df["ny_reclaim_asia_low"].fillna(False)
    if rule.rule_id == "I92_03_LONDON_SELL_NY_RECLAIM_H1D":
        return inactive & (df["london_ret_bps"] <= q25_london) & (df["ny_ret_bps"] > 0)
    if rule.rule_id == "I92_04_LONDON_SELL_NEXT2D_REVERSAL":
        return inactive & (df["london_ret_bps"] <= q25_london) & (df["day_ret_bps"] < 0)
    if rule.rule_id == "I92_05_RISKOFF_INTRADAY_PULLBACK_H1D":
        return inactive & (df.get("vix_change_20d", 0) > 0) & (df["day_ret_bps"] <= q25_day)
    if rule.rule_id == "I92_06_DXY_UP_INTRADAY_RECLAIM_H1D":
        return inactive & (df.get("dxy_ret_20d", 0) > 0) & df["london_breakdown"].fillna(False) & df["ny_reclaim_asia_mid"].fillna(False)
    if rule.rule_id == "I92_07_REALYIELD_UP_SESSION_RECLAIM_H1D":
        return inactive & (df.get("real_yield_change_20d", 0) > 0) & df["london_breakdown"].fillna(False) & df["ny_reclaim_asia_mid"].fillna(False)
    if rule.rule_id == "I92_08_LOW_RANGE_DAY_NEXT2D_CONTINUATION":
        return inactive & (df["asia_range_bps"] <= q25_asia) & (df["day_ret_bps"] > 0)
    return pd.Series([False] * len(df), index=df.index)


def period_name(date: pd.Timestamp) -> str:
    y = date.year
    if y <= 2014:
        return "TRAIN_DISCOVERY"
    if y <= 2018:
        return "VALIDATION_SELECTION"
    if y <= 2022:
        return "LOCKED_HISTORICAL_FORWARD"
    return "FINAL_STATISTICAL_HOLDOUT"


def metrics_for_returns(ret: pd.Series) -> Dict[str, Any]:
    ret = pd.to_numeric(ret, errors="coerce").dropna()
    if ret.empty:
        return {
            "entries": 0,
            "mean_net_bps": None,
            "median_net_bps": None,
            "win_rate": None,
            "min_net_bps": None,
            "max_net_bps": None,
            "total_net_bps": 0.0,
        }
    return {
        "entries": int(len(ret)),
        "mean_net_bps": round(float(ret.mean()), 4),
        "median_net_bps": round(float(ret.median()), 4),
        "win_rate": round(float((ret > 0).mean()), 4),
        "min_net_bps": round(float(ret.min()), 4),
        "max_net_bps": round(float(ret.max()), 4),
        "total_net_bps": round(float(ret.sum()), 4),
    }


def evaluate_rule(df: pd.DataFrame, rule: CandidateRule, cfg: Dict[str, Any]) -> Tuple[Dict[str, Any], pd.DataFrame]:
    cost = float(cfg.get("cost_bps_total_reference", 20.0))
    mask = build_mask(df, rule)
    needed = [rule.entry_col, rule.exit_col]
    for c in ["date", "current_portfolio_active", "asia_range_bps", "london_ret_bps", "day_ret_bps"] + needed:
        if c not in df.columns:
            df[c] = math.nan
    ev = df[mask].copy()
    ev = ev.dropna(subset=needed)
    ev["entry_price"] = pd.to_numeric(ev[rule.entry_col], errors="coerce")
    ev["exit_price"] = pd.to_numeric(ev[rule.exit_col], errors="coerce")
    ev = ev.dropna(subset=["entry_price", "exit_price"])
    ev = ev[ev["entry_price"] > 0].copy()
    ev["gross_return_bps"] = (ev["exit_price"] / ev["entry_price"] - 1.0) * 10000.0
    ev["net_return_bps"] = ev["gross_return_bps"] - cost
    ev["rule_id"] = rule.rule_id
    ev["label"] = rule.label
    ev["period"] = pd.to_datetime(ev["date"], utc=True).map(period_name)
    ev["year"] = pd.to_datetime(ev["date"], utc=True).dt.year
    ev["residual_entry"] = True  # mask already requires inactive current portfolio

    total = metrics_for_returns(ev["net_return_bps"] if not ev.empty else pd.Series(dtype=float))
    period_metrics: Dict[str, Dict[str, Any]] = {}
    for p in ["TRAIN_DISCOVERY", "VALIDATION_SELECTION", "LOCKED_HISTORICAL_FORWARD", "FINAL_STATISTICAL_HOLDOUT"]:
        period_metrics[p] = metrics_for_returns(ev.loc[ev["period"] == p, "net_return_bps"] if not ev.empty else pd.Series(dtype=float))
    asof = pd.Timestamp(cfg.get("asof_date", "2024-01-01"), tz="UTC")
    ev_dt = pd.to_datetime(ev["date"], utc=True) if not ev.empty else pd.Series(dtype="datetime64[ns, UTC]")
    post_asof = metrics_for_returns(ev.loc[ev_dt >= asof, "net_return_bps"] if not ev.empty else pd.Series(dtype=float))

    if not ev.empty:
        year_counts = ev["year"].value_counts()
        max_year_entry_share = float(year_counts.max() / len(ev))
        max_entry_year = int(year_counts.idxmax())
    else:
        max_year_entry_share = 0.0
        max_entry_year = None

    residual_share = 1.0 if len(ev) else 0.0
    missing_required_feature_rows = int(mask.isna().sum()) if hasattr(mask, "isna") else 0
    constraints = cfg.get("constraints", {})
    fail_reasons: List[str] = []
    if total["entries"] < constraints.get("min_total_entries", 20):
        fail_reasons.append("TOTAL_ENTRIES_TOO_LOW")
    if (total["mean_net_bps"] is None) or total["mean_net_bps"] < constraints.get("min_total_mean_net_bps", 0.0):
        fail_reasons.append("TOTAL_MEAN_TOO_LOW")
    if (total["win_rate"] is None) or total["win_rate"] < constraints.get("min_total_win_rate", 0.50):
        fail_reasons.append("WIN_RATE_TOO_LOW")
    if total["min_net_bps"] is None or abs(total["min_net_bps"]) > constraints.get("max_abs_worst_loss_bps", 900.0):
        fail_reasons.append("WORST_LOSS_TOO_LARGE")
    locked = period_metrics["LOCKED_HISTORICAL_FORWARD"]
    if locked["entries"] < constraints.get("min_locked_forward_entries", 3):
        fail_reasons.append("LOCKED_FORWARD_ENTRIES_TOO_LOW")
    if locked["mean_net_bps"] is None or locked["mean_net_bps"] < constraints.get("min_locked_forward_mean_bps", -25.0):
        fail_reasons.append("LOCKED_FORWARD_MEAN_TOO_LOW")
    final = period_metrics["FINAL_STATISTICAL_HOLDOUT"]
    if final["entries"] < constraints.get("min_final_holdout_entries", 3):
        fail_reasons.append("FINAL_HOLDOUT_ENTRIES_TOO_LOW")
    if final["mean_net_bps"] is None or final["mean_net_bps"] < constraints.get("min_final_holdout_mean_bps", 0.0):
        fail_reasons.append("FINAL_HOLDOUT_MEAN_TOO_LOW")
    if post_asof["entries"] < constraints.get("min_post_asof_entries", 2):
        fail_reasons.append("POST_ASOF_ENTRIES_TOO_LOW")
    if post_asof["mean_net_bps"] is None or post_asof["mean_net_bps"] < constraints.get("min_post_asof_mean_bps", 0.0):
        fail_reasons.append("POST_ASOF_MEAN_TOO_LOW")
    if residual_share < constraints.get("min_residual_entry_share", 0.5):
        fail_reasons.append("RESIDUAL_ENTRY_SHARE_TOO_LOW")
    if max_year_entry_share > constraints.get("max_year_entry_share", 0.35):
        fail_reasons.append("YEAR_CONCENTRATION_TOO_HIGH")
    if missing_required_feature_rows > constraints.get("max_missing_required_feature_rows", 0):
        fail_reasons.append("MISSING_REQUIRED_FEATURE_ROWS")

    # Score rewards final/post-asof quality and enough entries but penalizes downside.
    score = 0.0
    if total["mean_net_bps"] is not None:
        score += total["mean_net_bps"] * 2.0
    if final["mean_net_bps"] is not None:
        score += final["mean_net_bps"] * 1.5
    if post_asof["mean_net_bps"] is not None:
        score += post_asof["mean_net_bps"] * 1.5
    score += min(total["entries"], 80) * 5.0
    if total["min_net_bps"] is not None:
        score += total["min_net_bps"] * 0.2

    rec: Dict[str, Any] = {
        "rule_id": rule.rule_id,
        "label": rule.label,
        "bucket": rule.bucket,
        "horizon_days": rule.horizon_days,
        "condition_text": rule.condition_text,
        "entry_col": rule.entry_col,
        "exit_col": rule.exit_col,
        "total_entries": total["entries"],
        "total_mean_net_bps": total["mean_net_bps"],
        "total_median_net_bps": total["median_net_bps"],
        "total_win_rate": total["win_rate"],
        "total_min_net_bps": total["min_net_bps"],
        "total_max_net_bps": total["max_net_bps"],
        "total_total_net_bps": total["total_net_bps"],
        "train_entries": period_metrics["TRAIN_DISCOVERY"]["entries"],
        "train_mean_net_bps": period_metrics["TRAIN_DISCOVERY"]["mean_net_bps"],
        "validation_entries": period_metrics["VALIDATION_SELECTION"]["entries"],
        "validation_mean_net_bps": period_metrics["VALIDATION_SELECTION"]["mean_net_bps"],
        "locked_forward_entries": locked["entries"],
        "locked_forward_mean_net_bps": locked["mean_net_bps"],
        "final_holdout_entries": final["entries"],
        "final_holdout_mean_net_bps": final["mean_net_bps"],
        "post_asof_entries": post_asof["entries"],
        "post_asof_mean_net_bps": post_asof["mean_net_bps"],
        "max_entry_year": max_entry_year,
        "max_year_entry_share": round(max_year_entry_share, 4),
        "residual_entry_share": round(residual_share, 4),
        "missing_required_feature_rows": missing_required_feature_rows,
        "pass_discovery_candidate": len(fail_reasons) == 0,
        "fail_reasons": "|".join(fail_reasons),
        "discovery_score": round(float(score), 4),
    }
    cols = [
        "rule_id", "label", "date", "period", "year", "entry_price", "exit_price",
        "gross_return_bps", "net_return_bps", "asia_range_bps", "london_ret_bps", "ny_ret_bps", "day_ret_bps",
    ]
    return rec, ev[[c for c in cols if c in ev.columns]].copy()


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    cols: List[str] = []
    for r in rows:
        for k in r.keys():
            if k not in cols:
                cols.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def render_report(summary: Dict[str, Any], shortlist: List[Dict[str, Any]]) -> str:
    lines = [
        "# Stage92 Intraday Session Residual Thesis Discovery",
        "",
        "## Decision",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- classification: `{summary['classification']}`",
        f"- disposition: `{summary['disposition']}`",
        "",
        "## Principle",
        "Thesis-first intraday/session discovery only on residual days where the current unified macro observer portfolio is inactive. No orders, no EA change, no MT5 change.",
        "",
        "## Intraday data",
        f"- source file: `{summary['intraday_data']['selected_path']}`",
        f"- inferred timeframe: `{summary['intraday_data']['inferred_timeframe']}`",
        f"- rows: `{summary['intraday_data']['rows']}`",
        f"- min/max UTC: `{summary['intraday_data']['min_utc']}` → `{summary['intraday_data']['max_utc']}`",
        "",
        "## Shortlist",
    ]
    if shortlist:
        for r in shortlist:
            lines.append(
                f"- `{r['rule_id']}`: {r['label']} score=`{r['discovery_score']}` entries=`{r['total_entries']}` mean=`{r['total_mean_net_bps']}` final=`{r['final_holdout_mean_net_bps']}` post_asof=`{r['post_asof_mean_net_bps']}` fail=`{r['fail_reasons']}`"
            )
    else:
        lines.append("- none")
    lines.extend(["", "## Hard blocks"])
    for b in NO_ORDER_BLOCKS:
        lines.append(f"- `{b}`")
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    out_dir = Path(args.out).expanduser()
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = load_config(args.config)

    macro = load_macro(root, cfg)
    intra, selected_inv, inventory = load_preferred_intraday(root, cfg)
    features = build_daily_session_features(intra, macro)
    rules = candidate_rules()
    metrics: List[Dict[str, Any]] = []
    all_events: List[pd.DataFrame] = []
    for rule in rules:
        rec, ev = evaluate_rule(features, rule, cfg)
        metrics.append(rec)
        if not ev.empty:
            all_events.append(ev)
    metrics = sorted(metrics, key=lambda r: (bool(r["pass_discovery_candidate"]), r["discovery_score"]), reverse=True)
    shortlist = [r for r in metrics if r["pass_discovery_candidate"]][: int(cfg.get("candidate_top_n", 8))]

    decision = "STAGE92_INTRADAY_SESSION_SHORTLIST_READY_FOR_HARD_AUDIT_NO_ORDER" if shortlist else "NO_INTRADAY_SESSION_THESIS_SHORTLIST_NO_ORDER"
    classification = "S92_INTRADAY_SESSION_SHORTLIST_READY" if shortlist else "S92_NO_INTRADAY_SESSION_SHORTLIST"
    disposition = "INTRADAY_SESSION_THESIS_SHORTLIST_READY_FOR_STAGE93" if shortlist else "NO_INTRADAY_SESSION_THESIS_SHORTLIST"

    metrics_csv = out_dir / "stage92_intraday_session_candidate_metrics.csv"
    shortlist_csv = out_dir / "stage92_intraday_session_shortlist.csv"
    inventory_csv = out_dir / "stage92_intraday_file_inventory.csv"
    entry_returns_csv = out_dir / "stage92_intraday_session_entry_returns.csv"
    summary_json = out_dir / "stage92_intraday_session_residual_thesis_discovery_summary.json"
    report_md = out_dir / "stage92_intraday_session_residual_thesis_discovery_report.md"

    write_csv(metrics_csv, metrics)
    write_csv(shortlist_csv, shortlist)
    write_csv(inventory_csv, inventory)
    if all_events:
        pd.concat(all_events, ignore_index=True).to_csv(entry_returns_csv, index=False)
    else:
        entry_returns_csv.write_text("", encoding="utf-8")

    selected_path = selected_inv.get("path")
    summary: Dict[str, Any] = {
        "stage": STAGE,
        "root": str(root),
        "config": str(Path(args.config).expanduser().resolve()) if args.config else None,
        "generated_utc": now_utc(),
        "status": "STAGE92_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "principle": "Thesis-first intraday/session residual discovery using local AMarkets/SQLite-ready intraday data. No orders and no MT5/EA change.",
        "macro_dataset": {
            "path": str(expand_path(cfg["macro_dataset"], root)),
            "rows": int(len(macro)),
            "min_date": str(macro["date"].min()),
            "max_date": str(macro["date"].max()),
        },
        "intraday_data": {
            "selected_path": selected_path,
            "inferred_timeframe": selected_inv.get("inferred_timeframe"),
            "rows": selected_inv.get("rows"),
            "min_utc": selected_inv.get("min_utc"),
            "max_utc": selected_inv.get("max_utc"),
            "has_spread": selected_inv.get("has_spread"),
            "sha256": selected_inv.get("sha256"),
        },
        "feature_days": int(len(features)),
        "current_portfolio_active_days_in_session_panel": int(features["current_portfolio_active"].sum()),
        "current_portfolio_inactive_days_in_session_panel": int((~features["current_portfolio_active"].astype(bool)).sum()),
        "candidate_count": len(metrics),
        "pass_candidate_count": int(sum(1 for r in metrics if r["pass_discovery_candidate"])),
        "shortlist_count": len(shortlist),
        "shortlist_rule_ids": [r["rule_id"] for r in shortlist],
        "shortlist": shortlist,
        "constraints": cfg.get("constraints", {}),
        "hard_blocks": NO_ORDER_BLOCKS,
        "outputs": {
            "summary_json": str(summary_json),
            "report_md": str(report_md),
            "candidate_metrics_csv": str(metrics_csv),
            "shortlist_csv": str(shortlist_csv),
            "entry_returns_csv": str(entry_returns_csv),
            "file_inventory_csv": str(inventory_csv),
        },
    }
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    report_md.write_text(render_report(summary, shortlist), encoding="utf-8")
    print(json.dumps({
        "stage": STAGE,
        "status": summary["status"],
        "decision": decision,
        "shortlist_count": len(shortlist),
        "summary_json": str(summary_json),
        "report_md": str(report_md),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
