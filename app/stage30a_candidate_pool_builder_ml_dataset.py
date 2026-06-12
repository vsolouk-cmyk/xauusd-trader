#!/usr/bin/env python3
"""
Stage30A — Candidate Pool Builder + ML-ready Meta Dataset for XAUUSD research.

Purpose
-------
Build one normalized, ML-ready meta-dataset from prior discovery/validation artifacts.
This stage does NOT create a new entry rule, tracker, EA, order, paper trade, or live trade.

Design principles
-----------------
- DB-first sanity/enrichment through the validated Stage25C SQLite loader when available.
- Existing trade CSVs are research artifacts only, not market-data fallback.
- Only forward-safe feature columns are exported into the ML feature matrix.
- Leak-prone columns such as exit/tp/sl/future full-day/early-NY fields are excluded from features.
- Output is a dataset and diagnostics so Stage30B can run ML-lite classifiers/rankers.
"""
from __future__ import annotations

import json
import math
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

ROOT = Path.cwd()
REPORT_DIR = ROOT / "data" / "reports" / "stage30a_candidate_pool_builder_ml_dataset"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(os.getenv("XAUUSD_DB_PATH", "data/local/xauusd_local_store.sqlite"))
MIN_POOL_EVENTS = int(os.getenv("STAGE30A_MIN_POOL_EVENTS", "250"))
MIN_FEATURE_NON_NULL_RATIO = float(os.getenv("STAGE30A_MIN_FEATURE_NON_NULL_RATIO", "0.25"))
ROUND_DIGITS = 6

# Paths are intentionally broad but loaded only if they look like trade/outcome artifacts.
DEFAULT_PATTERNS = [
    "data/reports/**/stage*_exact_trades*.csv",
    "data/reports/**/*exact*trades*.csv",
    "data/reports/**/*normalized_lineage_trades*.csv",
    "data/reports/**/*enriched*trades*.csv",
    "data/reports/**/*forward_shadow_ledger*.csv",
    "data/reports/**/*meta_gate_forward_shadow_ledger*.csv",
]
EXTRA_ARTIFACTS_ENV = "STAGE30A_EXTRA_ARTIFACTS"  # os.pathsep separated list

TIME_COLS = [
    "entry_ts_norm", "entry_time", "entry_ts", "timestamp", "signal_time", "time", "date", "datetime",
]
CANDIDATE_COLS = ["candidate", "candidate_name", "name", "variant", "strategy", "strategy_name", "gate_name"]
FAMILY_COLS = ["family", "source_family", "strategy_family"]
DIRECTION_COLS = ["direction", "dir", "side", "signal_direction"]

NET_ALIASES = {
    "net_x1": ["net_x1", "x1", "ret_x1", "pnl_x1", "net_ret_x1", "net_return_x1"],
    "net_x4": ["net_x4", "x4", "ret_x4", "pnl_x4", "net_ret_x4", "net_return_x4"],
    "net_x6": ["net_x6", "x6", "ret_x6", "pnl_x6", "net_ret_x6", "net_return_x6"],
}

# Forward-safe features. Absolute price levels are intentionally excluded.
NUMERIC_FEATURES = [
    "prior_day_range",
    "asia_range",
    "asia_eff",
    "london_range",
    "london_eff",
    "h1_range",
    "h1_atr20",
    "h1_atr20_pct_rank_250",
]
CATEGORICAL_FEATURES = [
    "direction_num",
    "prior_day_aligned",
    "london_aligned",
    "entry_hour",
    "dow",
    "month",
]
ML_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES

LEAK_PRONE_NAME_PATTERNS = [
    "exit", "tp", "sl", "outcome", "result", "future", "after_", "mfe", "mae",
    "early_ny", "day_high", "day_low", "day_close", "day_range", "close_after",
]


def _norm_col(c: Any) -> str:
    return str(c).strip().lower().replace("<", "").replace(">", "").replace(" ", "_").replace("-", "_")


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        f = float(x)
        if math.isnan(f):
            return default
        if math.isinf(f):
            return float("inf") if f > 0 else float("-inf")
        return round(f, ROUND_DIGITS)
    except Exception:
        return default


def _fmt(x: Any) -> str:
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass
    if isinstance(x, float):
        if math.isinf(x):
            return "inf" if x > 0 else "-inf"
        if math.isnan(x):
            return ""
        return str(round(x, 4))
    if isinstance(x, (dict, list, tuple)):
        return json.dumps(x, ensure_ascii=False, default=str)
    return str(x)


def markdown_table(df: pd.DataFrame, columns: Sequence[str], max_rows: int = 30) -> str:
    if df is None or df.empty:
        return "No rows."
    cols = [c for c in columns if c in df.columns]
    if not cols:
        return "No rows."
    show = df.loc[:, cols].head(max_rows).copy()
    header = "| " + " | ".join(show.columns) + " |"
    sep = "| " + " | ".join(["---"] * len(show.columns)) + " |"
    rows = ["| " + " | ".join(_fmt(row[c]) for c in show.columns) + " |" for _, row in show.iterrows()]
    return "\n".join([header, sep] + rows)


def profit_factor(values: Iterable[float]) -> float:
    arr = pd.to_numeric(pd.Series(list(values)), errors="coerce").dropna().to_numpy(dtype=float)
    if arr.size == 0:
        return 0.0
    gains = float(arr[arr > 0].sum())
    losses = float((-arr[arr < 0]).sum())
    if losses <= 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


@dataclass
class MetricSnapshot:
    events: int
    pf_x1: float
    pf_x4: float
    pf_x6: float
    total_x4: float
    win_rate_x4: float
    median_x4: float
    years_positive_x4: int
    year_count: int


def metric_snapshot(df: pd.DataFrame) -> MetricSnapshot:
    if df is None or df.empty:
        return MetricSnapshot(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0)
    x1 = pd.to_numeric(df.get("net_x1", pd.Series(dtype=float)), errors="coerce")
    x4 = pd.to_numeric(df.get("net_x4", pd.Series(dtype=float)), errors="coerce")
    x6 = pd.to_numeric(df.get("net_x6", pd.Series(dtype=float)), errors="coerce")
    years_positive = 0
    year_count = 0
    if "year" in df.columns:
        yearly = df.groupby("year")["net_x4"].sum(numeric_only=True)
        year_count = int(len(yearly))
        years_positive = int((yearly > 0).sum())
    return MetricSnapshot(
        events=int(len(df)),
        pf_x1=_safe_float(profit_factor(x1)),
        pf_x4=_safe_float(profit_factor(x4)),
        pf_x6=_safe_float(profit_factor(x6)),
        total_x4=_safe_float(float(x4.sum()) if len(x4.dropna()) else 0.0),
        win_rate_x4=_safe_float(float((x4 > 0).mean()) if len(x4.dropna()) else 0.0),
        median_x4=_safe_float(float(x4.median()) if len(x4.dropna()) else 0.0),
        years_positive_x4=years_positive,
        year_count=year_count,
    )


def discover_artifacts() -> List[Path]:
    paths: List[Path] = []
    for pattern in DEFAULT_PATTERNS:
        paths.extend(ROOT.glob(pattern))
    extra = os.getenv(EXTRA_ARTIFACTS_ENV, "").strip()
    if extra:
        for item in extra.split(os.pathsep):
            if item.strip():
                paths.append(Path(item.strip()))
    # Deduplicate, keep only existing files, skip Stage30 outputs to avoid self-ingestion.
    unique: List[Path] = []
    seen: set[str] = set()
    for p in paths:
        p = p if p.is_absolute() else ROOT / p
        if not p.exists() or not p.is_file():
            continue
        rel = str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)
        if "stage30a_candidate_pool_builder_ml_dataset" in rel:
            continue
        if rel not in seen:
            seen.add(rel)
            unique.append(p)
    return sorted(unique, key=lambda x: str(x))


def _pick_col(df: pd.DataFrame, aliases: Sequence[str]) -> Optional[str]:
    norm_to_col = {_norm_col(c): c for c in df.columns}
    for a in aliases:
        if _norm_col(a) in norm_to_col:
            return norm_to_col[_norm_col(a)]
    return None


def _find_net_col(df: pd.DataFrame, target: str) -> Optional[str]:
    c = _pick_col(df, NET_ALIASES[target])
    if c:
        return c
    # Soft fallback: look for target suffix contained in column name.
    for col in df.columns:
        n = _norm_col(col)
        if target in n:
            return col
    return None


def _infer_stage_from_path(path: Path) -> str:
    text = str(path).lower()
    m = re.search(r"stage\d+[a-z]?", text)
    return m.group(0).upper() if m else "UNKNOWN"


def _normalize_direction(v: Any) -> float:
    s = str(v).strip().lower()
    if s in {"1", "+1", "long", "buy", "bull", "up"}:
        return 1.0
    if s in {"-1", "short", "sell", "bear", "down"}:
        return -1.0
    try:
        f = float(v)
        return 1.0 if f > 0 else (-1.0 if f < 0 else 0.0)
    except Exception:
        return 0.0


def load_candidate_artifact(path: Path) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    manifest: Dict[str, Any] = {
        "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "status": "skipped",
        "rows_raw": 0,
        "rows_loaded": 0,
        "reason": "",
    }
    try:
        raw = pd.read_csv(path)
    except Exception as exc:
        manifest.update({"status": "error", "reason": f"read_csv: {exc}"})
        return pd.DataFrame(), manifest
    manifest["rows_raw"] = int(len(raw))
    if raw.empty:
        manifest["reason"] = "empty_csv"
        return pd.DataFrame(), manifest

    net_cols = {target: _find_net_col(raw, target) for target in NET_ALIASES}
    if not net_cols["net_x4"]:
        manifest["reason"] = "missing_net_x4_like_column"
        return pd.DataFrame(), manifest

    out = pd.DataFrame(index=raw.index)
    for target, col in net_cols.items():
        if col:
            out[target] = pd.to_numeric(raw[col], errors="coerce")
        else:
            # if only x4 is available, x1/x6 stay NaN; Stage30B can still use x4 labels.
            out[target] = np.nan

    time_col = _pick_col(raw, TIME_COLS)
    if time_col:
        out["entry_ts_norm"] = pd.to_datetime(raw[time_col], utc=True, errors="coerce")
    else:
        out["entry_ts_norm"] = pd.NaT

    cand_col = _pick_col(raw, CANDIDATE_COLS)
    fam_col = _pick_col(raw, FAMILY_COLS)
    dir_col = _pick_col(raw, DIRECTION_COLS)
    out["candidate_name"] = raw[cand_col].astype(str) if cand_col else path.stem
    out["family"] = raw[fam_col].astype(str) if fam_col else _infer_stage_from_path(path)
    out["direction_num"] = raw[dir_col].map(_normalize_direction) if dir_col else 0.0

    out["source_file"] = manifest["path"]
    out["source_stage"] = _infer_stage_from_path(path)

    # Copy only allowed forward-safe feature candidates if present.
    for feat in NUMERIC_FEATURES:
        if feat in {"h1_range", "h1_atr20", "h1_atr20_pct_rank_250"}:
            continue
        col = _pick_col(raw, [feat])
        if col:
            out[feat] = pd.to_numeric(raw[col], errors="coerce")

    for feat in ["prior_day_aligned", "london_aligned", "entry_hour", "dow", "month"]:
        col = _pick_col(raw, [feat])
        if col:
            if feat in {"prior_day_aligned", "london_aligned"}:
                vals = raw[col]
                if vals.dtype == bool:
                    out[feat] = vals.astype(float)
                else:
                    s = vals.astype(str).str.lower().str.strip()
                    out[feat] = np.where(s.isin(["true", "1", "yes", "long", "short"]), 1.0, 0.0)
            else:
                out[feat] = pd.to_numeric(raw[col], errors="coerce")

    # Derive calendar fields from entry time if missing.
    if out["entry_ts_norm"].notna().any():
        ts = out["entry_ts_norm"]
        if "year" not in out.columns:
            out["year"] = ts.dt.year
        if "month" not in out.columns:
            out["month"] = ts.dt.month
        if "dow" not in out.columns:
            out["dow"] = ts.dt.dayofweek
        if "entry_hour" not in out.columns:
            out["entry_hour"] = ts.dt.hour
    else:
        if "year" not in out.columns:
            out["year"] = np.nan

    # Keep rows with an x4 outcome. If timestamp is missing, keep it but mark as not time-valid.
    before = len(out)
    out = out.dropna(subset=["net_x4"]).copy()
    manifest.update({
        "status": "loaded" if not out.empty else "skipped",
        "rows_loaded": int(len(out)),
        "reason": "loaded" if not out.empty else "no_rows_after_net_x4_dropna",
        "time_column": time_col or "none",
        "candidate_column": cand_col or "none",
        "family_column": fam_col or "none",
        "direction_column": dir_col or "none",
        "net_x1_column": net_cols["net_x1"] or "none",
        "net_x4_column": net_cols["net_x4"] or "none",
        "net_x6_column": net_cols["net_x6"] or "none",
        "rows_dropped_missing_net_x4": int(before - len(out)),
    })
    return out.reset_index(drop=True), manifest


def load_db_bars() -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Dict[str, Any], Optional[pd.DataFrame]]:
    meta = {
        "loader_mode": "reused:app.stage25c_deduped_filter_validation.load_bars_from_db",
        "db_path": str(DB_PATH),
        "db_first": True,
        "csv_fallback_enabled": False,
    }
    try:
        from app.stage25c_deduped_filter_validation import load_bars_from_db  # type: ignore
        m1, h1, loader_meta, schema = load_bars_from_db(DB_PATH)
        meta.update(loader_meta)
        meta.update({"m1_rows_stage30a": int(len(m1)), "h1_rows_stage30a": int(len(h1))})
        return m1, h1, meta, schema
    except Exception as exc:
        meta["db_meta_warning"] = f"{type(exc).__name__}: {exc}"
        return None, None, meta, None


def build_daily_session_features(m1: pd.DataFrame) -> pd.DataFrame:
    df = m1.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["timestamp", "open", "high", "low", "close"])
    df["date"] = df["timestamp"].dt.floor("D")
    df["hour"] = df["timestamp"].dt.hour
    daily = df.groupby("date", as_index=False).agg(
        day_open=("open", "first"), day_high=("high", "max"), day_low=("low", "min"), day_close=("close", "last")
    )
    daily["day_range_raw"] = daily["day_high"] - daily["day_low"]
    daily["prior_day_range_db"] = daily["day_range_raw"].shift(1)
    daily["prior_day_direction_db"] = np.where(daily["day_close"].shift(1) >= daily["day_open"].shift(1), 1.0, -1.0)

    def session(name: str, start_hour: int, end_hour: int) -> pd.DataFrame:
        s = df.loc[(df["hour"] >= start_hour) & (df["hour"] < end_hour)].copy()
        if s.empty:
            return pd.DataFrame({"date": []})
        out = s.groupby("date", as_index=False).agg(
            **{
                f"{name}_open": ("open", "first"),
                f"{name}_high": ("high", "max"),
                f"{name}_low": ("low", "min"),
                f"{name}_close": ("close", "last"),
            }
        )
        out[f"{name}_range_db"] = out[f"{name}_high"] - out[f"{name}_low"]
        rng = out[f"{name}_range_db"].replace(0, np.nan)
        out[f"{name}_eff_db"] = (out[f"{name}_close"] - out[f"{name}_open"]).abs() / rng
        out[f"{name}_direction_db"] = np.where(out[f"{name}_close"] >= out[f"{name}_open"], 1.0, -1.0)
        return out

    features = daily[["date", "prior_day_range_db", "prior_day_direction_db"]].copy()
    for name, start, end in [("asia", 0, 7), ("london", 7, 13)]:
        keep = ["date", f"{name}_range_db", f"{name}_eff_db", f"{name}_direction_db"]
        features = features.merge(session(name, start, end)[keep], on="date", how="left")
    return features


def enrich_pool_from_db(pool: pd.DataFrame, m1: Optional[pd.DataFrame], h1: Optional[pd.DataFrame]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    out = pool.copy()
    enrich_meta: Dict[str, Any] = {"db_session_enrichment": False, "h1_enrichment": False}
    if "entry_ts_norm" not in out.columns or out["entry_ts_norm"].isna().all():
        return out, enrich_meta

    if m1 is not None and not m1.empty:
        try:
            session_features = build_daily_session_features(m1)
            out["date"] = pd.to_datetime(out["entry_ts_norm"], utc=True, errors="coerce").dt.floor("D")
            out = out.merge(session_features, on="date", how="left")
            fill_map = {
                "prior_day_range": "prior_day_range_db",
                "asia_range": "asia_range_db",
                "asia_eff": "asia_eff_db",
                "london_range": "london_range_db",
                "london_eff": "london_eff_db",
            }
            for target, dbcol in fill_map.items():
                if target not in out.columns:
                    out[target] = out[dbcol]
                else:
                    out[target] = pd.to_numeric(out[target], errors="coerce").fillna(pd.to_numeric(out[dbcol], errors="coerce"))
            # Alignment fields require direction.
            if "prior_day_aligned" not in out.columns:
                out["prior_day_aligned"] = np.where(out["direction_num"] == out["prior_day_direction_db"], 1.0, 0.0)
            else:
                out["prior_day_aligned"] = pd.to_numeric(out["prior_day_aligned"], errors="coerce").fillna(
                    np.where(out["direction_num"] == out["prior_day_direction_db"], 1.0, 0.0)
                )
            if "london_aligned" not in out.columns:
                out["london_aligned"] = np.where(out["direction_num"] == out["london_direction_db"], 1.0, 0.0)
            else:
                out["london_aligned"] = pd.to_numeric(out["london_aligned"], errors="coerce").fillna(
                    np.where(out["direction_num"] == out["london_direction_db"], 1.0, 0.0)
                )
            enrich_meta["db_session_enrichment"] = True
        except Exception as exc:
            enrich_meta["db_session_enrichment_warning"] = f"{type(exc).__name__}: {exc}"

    if h1 is not None and not h1.empty:
        try:
            h = h1.copy().sort_values("timestamp")
            h["timestamp"] = pd.to_datetime(h["timestamp"], utc=True, errors="coerce")
            for c in ["high", "low"]:
                h[c] = pd.to_numeric(h[c], errors="coerce")
            h["h1_range_calc"] = h["high"] - h["low"]
            h["h1_atr20_calc"] = h["h1_range_calc"].rolling(20, min_periods=20).mean()
            h["h1_atr20_pct_rank_250_calc"] = h["h1_atr20_calc"].rolling(250, min_periods=50).rank(pct=True)
            h["bar_end"] = h["timestamp"] + pd.Timedelta(hours=1)
            h_valid = h.dropna(subset=["bar_end"]).reset_index(drop=True)
            bar_ends = h_valid["bar_end"].astype("int64").to_numpy()
            event_times = pd.to_datetime(out["entry_ts_norm"], utc=True, errors="coerce").astype("int64").to_numpy()
            idx = np.searchsorted(bar_ends, event_times, side="right") - 1
            valid = idx >= 0
            h1_range = np.full(len(out), np.nan)
            h1_atr = np.full(len(out), np.nan)
            h1_rank = np.full(len(out), np.nan)
            if valid.any():
                h1_range[valid] = h_valid.iloc[idx[valid]]["h1_range_calc"].to_numpy(dtype=float)
                h1_atr[valid] = h_valid.iloc[idx[valid]]["h1_atr20_calc"].to_numpy(dtype=float)
                h1_rank[valid] = h_valid.iloc[idx[valid]]["h1_atr20_pct_rank_250_calc"].to_numpy(dtype=float)
            for target, values in [("h1_range", h1_range), ("h1_atr20", h1_atr), ("h1_atr20_pct_rank_250", h1_rank)]:
                if target not in out.columns:
                    out[target] = values
                else:
                    out[target] = pd.to_numeric(out[target], errors="coerce").fillna(pd.Series(values, index=out.index))
            enrich_meta["h1_enrichment"] = True
        except Exception as exc:
            enrich_meta["h1_enrichment_warning"] = f"{type(exc).__name__}: {exc}"

    return out, enrich_meta


def finalize_ml_dataset(pool: pd.DataFrame) -> pd.DataFrame:
    df = pool.copy()
    # Calendar fallback.
    if "entry_ts_norm" in df.columns and df["entry_ts_norm"].notna().any():
        ts = pd.to_datetime(df["entry_ts_norm"], utc=True, errors="coerce")
        for col, vals in [("year", ts.dt.year), ("month", ts.dt.month), ("dow", ts.dt.dayofweek), ("entry_hour", ts.dt.hour)]:
            if col not in df.columns:
                df[col] = vals
            else:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(vals)

    for c in ML_FEATURES:
        if c not in df.columns:
            df[c] = np.nan
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Labels.
    df["label_win_x4"] = (pd.to_numeric(df["net_x4"], errors="coerce") > 0).astype(int)
    df["label_win_x6"] = (pd.to_numeric(df["net_x6"], errors="coerce") > 0).astype(int) if "net_x6" in df.columns else 0
    q75 = pd.to_numeric(df["net_x4"], errors="coerce").quantile(0.75)
    q25 = pd.to_numeric(df["net_x4"], errors="coerce").quantile(0.25)
    df["label_strong_win_x4"] = (pd.to_numeric(df["net_x4"], errors="coerce") >= q75).astype(int)
    df["label_bad_loss_x4"] = (pd.to_numeric(df["net_x4"], errors="coerce") <= q25).astype(int)
    df["sample_weight_abs_net_x4"] = pd.to_numeric(df["net_x4"], errors="coerce").abs().fillna(0.0)

    # Stable id and deduplication. Keep distinct source/candidate rows, then create event-level dedup flag.
    time_str = df.get("entry_ts_norm", pd.Series([pd.NaT] * len(df))).astype(str)
    dir_str = df.get("direction_num", pd.Series([0] * len(df))).astype(str)
    cand_str = df.get("candidate_name", pd.Series([""] * len(df))).astype(str)
    df["event_key"] = time_str + "|" + dir_str + "|" + cand_str
    before = len(df)
    df = df.drop_duplicates(subset=["source_file", "event_key", "net_x4"], keep="first").reset_index(drop=True)
    df["dedup_removed_stage30a"] = before - len(df)

    # Do not export raw leak-prone columns as ML features; keep only controlled metadata + outcomes + whitelist features.
    ordered = [
        "event_key", "entry_ts_norm", "source_stage", "source_file", "family", "candidate_name",
        "net_x1", "net_x4", "net_x6",
        "label_win_x4", "label_win_x6", "label_strong_win_x4", "label_bad_loss_x4", "sample_weight_abs_net_x4",
    ] + ML_FEATURES + ["year"]
    cols = [c for c in ordered if c in df.columns]
    return df.loc[:, cols].copy()


def feature_quality_report(df: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    base = metric_snapshot(df)
    for feat in ML_FEATURES:
        if feat not in df.columns:
            continue
        x = pd.to_numeric(df[feat], errors="coerce")
        non_null_ratio = float(x.notna().mean()) if len(x) else 0.0
        if non_null_ratio < MIN_FEATURE_NON_NULL_RATIO:
            rows.append({"feature": feat, "status": "low_coverage", "non_null_ratio": round(non_null_ratio, 4)})
            continue
        if feat in {"direction_num", "prior_day_aligned", "london_aligned", "entry_hour", "dow", "month"}:
            for val, sub in df.loc[x.notna()].groupby(feat):
                if len(sub) < 15:
                    continue
                m = metric_snapshot(sub)
                rows.append({
                    "feature": feat,
                    "gate": f"{feat}=={_fmt(val)}",
                    "status": "categorical_bucket",
                    "retained_events": m.events,
                    "retained_ratio": round(m.events / max(1, len(df)), 4),
                    "pf_x4": m.pf_x4,
                    "pf_x6": m.pf_x6,
                    "total_x4": m.total_x4,
                    "win_rate_x4": m.win_rate_x4,
                    "lift_pf_x4": _safe_float(m.pf_x4 - base.pf_x4 if math.isfinite(m.pf_x4) and math.isfinite(base.pf_x4) else 0.0),
                    "non_null_ratio": round(non_null_ratio, 4),
                })
        else:
            for q in [0.25, 0.35, 0.40, 0.50, 0.60, 0.65, 0.75]:
                threshold = x.quantile(q)
                for side in ["ge", "le"]:
                    mask = x >= threshold if side == "ge" else x <= threshold
                    sub = df.loc[mask.fillna(False)]
                    if len(sub) < 25:
                        continue
                    m = metric_snapshot(sub)
                    rows.append({
                        "feature": feat,
                        "gate": f"{feat}_{side}_q{int(q*100)}",
                        "threshold": _safe_float(threshold),
                        "status": "numeric_quantile",
                        "retained_events": m.events,
                        "retained_ratio": round(m.events / max(1, len(df)), 4),
                        "pf_x4": m.pf_x4,
                        "pf_x6": m.pf_x6,
                        "total_x4": m.total_x4,
                        "win_rate_x4": m.win_rate_x4,
                        "lift_pf_x4": _safe_float(m.pf_x4 - base.pf_x4 if math.isfinite(m.pf_x4) and math.isfinite(base.pf_x4) else 0.0),
                        "non_null_ratio": round(non_null_ratio, 4),
                    })
    out = pd.DataFrame(rows)
    if not out.empty:
        out["rank_score"] = (
            pd.to_numeric(out.get("lift_pf_x4", 0), errors="coerce").fillna(0)
            + 0.25 * pd.to_numeric(out.get("pf_x6", 0), errors="coerce").replace([np.inf, -np.inf], 20).fillna(0)
            + 0.002 * pd.to_numeric(out.get("total_x4", 0), errors="coerce").fillna(0)
        )
        out = out.sort_values(["rank_score", "retained_events"], ascending=[False, False]).reset_index(drop=True)
    return out


def family_contribution(df: pd.DataFrame) -> pd.DataFrame:
    group_cols = ["source_stage", "family"]
    rows: List[Dict[str, Any]] = []
    for keys, sub in df.groupby(group_cols, dropna=False):
        m = metric_snapshot(sub)
        rows.append({
            "source_stage": keys[0],
            "family": keys[1],
            **asdict(m),
            "candidate_count": int(sub["candidate_name"].nunique()) if "candidate_name" in sub.columns else 0,
            "source_file_count": int(sub["source_file"].nunique()) if "source_file" in sub.columns else 0,
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["events", "pf_x4", "total_x4"], ascending=[False, False, False]).reset_index(drop=True)
    return out


def write_outputs(
    dataset: pd.DataFrame,
    manifest: pd.DataFrame,
    feature_quality: pd.DataFrame,
    family_df: pd.DataFrame,
    db_meta: Dict[str, Any],
    enrich_meta: Dict[str, Any],
) -> Dict[str, Any]:
    base = metric_snapshot(dataset)
    feature_cols_ready = [c for c in ML_FEATURES if c in dataset.columns and dataset[c].notna().mean() >= MIN_FEATURE_NON_NULL_RATIO]
    decision = (
        "STAGE30A_ML_META_DATASET_READY_FOR_STAGE30B_REVIEW_ONLY"
        if len(dataset) >= MIN_POOL_EVENTS and len(feature_cols_ready) >= 5
        else "STAGE30A_META_DATASET_BUILT_NEEDS_MORE_POOL_OR_FEATURE_COVERAGE"
    )
    summary = {
        "decision": decision,
        "scope_guardrails": {
            "research_shadow_only": True,
            "no_ea_change": True,
            "no_automatic_trading": True,
            "no_paper_live_order_authorization": True,
            "db_first": True,
            "csv_market_fallback_enabled": False,
            "trade_artifacts_are_research_artifacts_only": True,
        },
        "db_source_of_truth": db_meta,
        "enrichment": enrich_meta,
        "counts": {
            "artifact_count_discovered": int(len(manifest)),
            "artifact_count_loaded": int((manifest["status"] == "loaded").sum()) if not manifest.empty and "status" in manifest.columns else 0,
            "ml_dataset_rows": int(len(dataset)),
            "feature_cols_ready": feature_cols_ready,
            "feature_cols_ready_count": int(len(feature_cols_ready)),
            "min_pool_events": MIN_POOL_EVENTS,
        },
        "base_metrics": asdict(base),
    }

    dataset_path = REPORT_DIR / "stage30a_ml_meta_dataset.csv"
    feature_path = REPORT_DIR / "stage30a_feature_quality_report.csv"
    family_path = REPORT_DIR / "stage30a_candidate_family_contribution.csv"
    manifest_path = REPORT_DIR / "stage30a_artifact_manifest.csv"
    json_path = REPORT_DIR / "stage30a_candidate_pool_builder_ml_dataset.json"
    md_path = REPORT_DIR / "stage30a_candidate_pool_builder_ml_dataset.md"

    dataset.to_csv(dataset_path, index=False)
    feature_quality.to_csv(feature_path, index=False)
    family_df.to_csv(family_path, index=False)
    manifest.to_csv(manifest_path, index=False)
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    top_feature_cols = ["feature", "gate", "status", "retained_events", "retained_ratio", "pf_x4", "pf_x6", "total_x4", "win_rate_x4", "rank_score"]
    family_cols = ["source_stage", "family", "events", "pf_x4", "pf_x6", "total_x4", "win_rate_x4", "candidate_count", "source_file_count"]
    manifest_cols = ["status", "path", "rows_raw", "rows_loaded", "reason", "source_stage"]

    md = f"""# Stage30A Candidate Pool Builder + ML-ready Meta Dataset

Generated UTC: `{pd.Timestamp.utcnow().isoformat()}`

## Decision

```text
{decision}
```

## Scope guardrails

- Research/shadow dataset building only.
- No EA change, no automatic trading, no paper/live/order authorization.
- DB candle access is DB-first through Stage25C loader when available.
- Existing CSV trade artifacts are research artifacts only, not market-data fallback.
- Exported ML features are restricted to a forward-safe whitelist.

## DB source of truth

```json
{json.dumps(db_meta, indent=2, ensure_ascii=False, default=str)}
```

## Enrichment diagnostics

```json
{json.dumps(enrich_meta, indent=2, ensure_ascii=False, default=str)}
```

## Counts

- artifact_count_discovered: `{summary['counts']['artifact_count_discovered']}`
- artifact_count_loaded: `{summary['counts']['artifact_count_loaded']}`
- ml_dataset_rows: `{summary['counts']['ml_dataset_rows']}`
- feature_cols_ready_count: `{summary['counts']['feature_cols_ready_count']}`
- feature_cols_ready: `{', '.join(feature_cols_ready)}`
- min_pool_events: `{MIN_POOL_EVENTS}`

## Base dataset metrics

```json
{json.dumps(asdict(base), indent=2, ensure_ascii=False)}
```

## Top feature quality diagnostics

{markdown_table(feature_quality, top_feature_cols, max_rows=30)}

## Candidate family contribution

{markdown_table(family_df, family_cols, max_rows=40)}

## Artifact manifest sample

{markdown_table(manifest, manifest_cols, max_rows=40)}

## Interpretation

- Stage30A does not decide a tradable strategy. It creates the ML-ready dataset for Stage30B.
- If `ml_dataset_rows` is low, Stage30B should stay ML-lite and avoid high-capacity models.
- If enough rows and feature coverage exist, the next stage can run simple, auditable classifiers/rankers.
- Any model result from Stage30B remains research-only and requires validation plus forward-shadow tracking.

## Operational reminder

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.run_active_shadow_suite
python3 -m app.stage30a_candidate_pool_builder_ml_dataset
```

## Output files

- `{json_path}`
- `{md_path}`
- `{dataset_path}`
- `{feature_path}`
- `{family_path}`
- `{manifest_path}`
"""
    md_path.write_text(md, encoding="utf-8")
    return summary


def main() -> None:
    artifacts = discover_artifacts()
    frames: List[pd.DataFrame] = []
    manifests: List[Dict[str, Any]] = []
    for path in artifacts:
        frame, manifest = load_candidate_artifact(path)
        manifests.append(manifest)
        if not frame.empty:
            frames.append(frame)

    manifest_df = pd.DataFrame(manifests)
    if not frames:
        db_m1, db_h1, db_meta, _schema = load_db_bars()
        empty = pd.DataFrame()
        write_outputs(empty, manifest_df, pd.DataFrame(), pd.DataFrame(), db_meta, {"warning": "no_trade_artifacts_loaded"})
        return

    pool = pd.concat(frames, ignore_index=True, sort=False)
    m1, h1, db_meta, _schema = load_db_bars()
    enriched, enrich_meta = enrich_pool_from_db(pool, m1, h1)
    dataset = finalize_ml_dataset(enriched)
    fqr = feature_quality_report(dataset)
    fam = family_contribution(dataset)
    write_outputs(dataset, manifest_df, fqr, fam, db_meta, enrich_meta)


if __name__ == "__main__":
    main()
