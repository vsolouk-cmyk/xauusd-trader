#!/usr/bin/env python3
"""
Stage45B2_EXTERNAL_CONTEXT_ALIGNMENT_AUDIT

Alignment/coverage/quality audit for external context data before any external-context baseline scan.
This script does not create signals, shortlist candidates, or promote archived rows.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

STAGE = "Stage45B2_EXTERNAL_CONTEXT_ALIGNMENT_AUDIT"
NO_GO = "NO_GO"

TIMEFRAME_ALIASES = {
    "m1": "M1", "1m": "M1", "1min": "M1", "1minute": "M1",
    "m5": "M5", "5m": "M5", "5min": "M5", "5minute": "M5",
    "m15": "M15", "15m": "M15", "15min": "M15", "15minute": "M15",
    "h1": "H1", "1h": "H1", "60m": "H1", "60min": "H1",
}

TS_ALIASES = ["utc_time", "timestamp", "time", "datetime", "date", "source_time"]
OHLC = ["open", "high", "low", "close"]

P0_PATHS = {
    "dxy": Path("data/external/dxy.csv"),
    "us10y_yield": Path("data/external/us10y_yield.csv"),
    "cme_gc_reference": Path("data/reference/cme_gc.csv"),
    "news_calendar": Path("data/external/news_calendar.csv"),
}
OPTIONAL_PATHS = {
    "real_yield": Path("data/external/real_yield.csv"),
    "us02y_yield": Path("data/external/us02y_yield.csv"),
}

MACRO_CATEGORY_KEYWORDS = [
    "cpi", "inflation", "pce", "fomc", "fed", "rate", "rates", "yield", "real_yield",
    "front_end", "nfp", "nonfarm", "payroll", "employment", "jobs", "unemployment",
    "retail", "ism", "pmi", "gdp", "treasury", "dgs", "dfii", "economic",
]
CENTRAL_BANK_GOLD_KEYWORDS = [
    "central_bank_gold", "central bank gold", "gold demand", "world gold council", "wgc",
]


def compact(s: Any) -> str:
    return "".join(str(s).strip().casefold().split())


def normalize_tf(v: Any) -> str:
    return TIMEFRAME_ALIASES.get(compact(v), str(v).strip())


def pct(n: float, d: float) -> Optional[float]:
    if d == 0 or not np.isfinite(d):
        return None
    return float(n / d)


def q_profile(values: Iterable[Any]) -> Dict[str, Any]:
    s = pd.to_numeric(pd.Series(list(values)), errors="coerce").dropna()
    if s.empty:
        return {"n": 0}
    return {
        "n": int(len(s)),
        "min": float(s.min()),
        "p10": float(s.quantile(0.10)),
        "median": float(s.median()),
        "p90": float(s.quantile(0.90)),
        "p95": float(s.quantile(0.95)),
        "p99": float(s.quantile(0.99)),
        "max": float(s.max()),
        "mean": float(s.mean()),
    }


def read_csv_safe(path: Path) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    try:
        if not path.exists():
            return None, "missing"
        return pd.read_csv(path), None
    except Exception as exc:  # pragma: no cover - diagnostic path
        return None, f"read_error: {type(exc).__name__}: {exc}"


def detect_col(columns: Iterable[str], aliases: Iterable[str]) -> Optional[str]:
    cmap = {compact(c): c for c in columns}
    for a in aliases:
        if compact(a) in cmap:
            return cmap[compact(a)]
    return None


def detect_ohlc(columns: Iterable[str]) -> Dict[str, Optional[str]]:
    cmap = {compact(c): c for c in columns}
    out: Dict[str, Optional[str]] = {}
    for k in OHLC:
        out[k] = cmap.get(k)
    return out


def ensure_utc(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce", utc=True)


def table_columns(con: sqlite3.Connection, table: str) -> List[str]:
    return [r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]


def load_bars(
    db_path: Path,
    table: str,
    source: str,
    symbol: str,
    timeframe: str,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    meta: Dict[str, Any] = {
        "db_path": str(db_path),
        "table": table,
        "requested_source": source,
        "requested_symbol": symbol,
        "requested_timeframe": timeframe,
    }
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    with sqlite3.connect(str(db_path)) as con:
        cols = table_columns(con, table)
        meta["columns"] = cols
        ts_col = detect_col(cols, TS_ALIASES)
        ohlc_cols = detect_ohlc(cols)
        source_col = detect_col(cols, ["source"])
        symbol_col = detect_col(cols, ["symbol"])
        tf_col = detect_col(cols, ["timeframe", "tf", "interval"])
        missing = [k for k, v in {"timestamp": ts_col, **ohlc_cols}.items() if v is None]
        if missing:
            raise ValueError(f"Missing required bar columns: {missing}; columns={cols}")

        select_cols = [ts_col] + [ohlc_cols[k] for k in OHLC]
        for c in [source_col, symbol_col, tf_col]:
            if c and c not in select_cols:
                select_cols.append(c)
        quoted = ", ".join([f'"{c}"' for c in select_cols])
        df = pd.read_sql_query(f"SELECT {quoted} FROM {table}", con)

    rename = {ts_col: "timestamp"}
    for k in OHLC:
        rename[ohlc_cols[k]] = k  # type: ignore[index]
    if source_col:
        rename[source_col] = "source"
    if symbol_col:
        rename[symbol_col] = "symbol"
    if tf_col:
        rename[tf_col] = "timeframe"
    df = df.rename(columns=rename)

    pre = len(df)
    if "source" in df.columns:
        df = df[df["source"].map(compact) == compact(source)]
    if "symbol" in df.columns:
        df = df[df["symbol"].map(compact) == compact(symbol)]
    if "timeframe" in df.columns:
        req_tf = normalize_tf(timeframe)
        df = df[df["timeframe"].map(normalize_tf) == req_tf]
    after_filter = len(df)

    df["timestamp"] = ensure_utc(df["timestamp"])
    for c in OHLC:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["timestamp", *OHLC]).sort_values("timestamp").drop_duplicates("timestamp")
    meta.update({
        "pre_filter_rows": int(pre),
        "post_filter_rows_before_clean": int(after_filter),
        "loaded_rows": int(len(df)),
        "loaded_start": df["timestamp"].min().isoformat() if not df.empty else None,
        "loaded_end": df["timestamp"].max().isoformat() if not df.empty else None,
    })
    if df.empty:
        raise ValueError("No bars loaded after filtering/cleaning")
    return df, meta


def aggregate_daily_bars(bars: pd.DataFrame) -> pd.DataFrame:
    df = bars.copy()
    df["date"] = df["timestamp"].dt.floor("D")
    g = df.groupby("date", sort=True)
    daily = pd.DataFrame({
        "timestamp": g["date"].first(),
        "open": g["open"].first(),
        "high": g["high"].max(),
        "low": g["low"].min(),
        "close": g["close"].last(),
        "bar_count": g.size(),
    }).reset_index(drop=True)
    daily["date"] = daily["timestamp"].dt.date.astype(str)
    daily["ret_bps"] = daily["close"].pct_change() * 10000.0
    return daily


def normalize_daily_value(path: Path, key: str, value_aliases: List[str]) -> Dict[str, Any]:
    df, err = read_csv_safe(path)
    out: Dict[str, Any] = {
        "key": key,
        "path": str(path),
        "exists": path.exists(),
        "schema_ok": False,
        "row_count": 0,
        "timestamp_column": None,
        "value_column": None,
        "start": None,
        "end": None,
        "columns": [],
        "numeric_profile": {},
        "error": err,
    }
    if df is None:
        return out
    out["columns"] = list(df.columns)
    ts_col = detect_col(df.columns, ["timestamp", "date", "datetime", "time"])
    val_col = detect_col(df.columns, value_aliases)
    out["timestamp_column"] = ts_col
    out["value_column"] = val_col
    if ts_col is None or val_col is None:
        out["error"] = "missing_timestamp_or_value_column"
        return out
    x = df[[ts_col, val_col]].copy()
    x.columns = ["timestamp", "value"]
    x["timestamp"] = ensure_utc(x["timestamp"])
    x["value"] = pd.to_numeric(x["value"], errors="coerce")
    x = x.dropna(subset=["timestamp", "value"]).sort_values("timestamp").drop_duplicates("timestamp")
    out["row_count"] = int(len(x))
    out["schema_ok"] = bool(len(x) >= 10)
    out["start"] = x["timestamp"].min().isoformat() if not x.empty else None
    out["end"] = x["timestamp"].max().isoformat() if not x.empty else None
    out["numeric_profile"] = q_profile(x["value"])
    out["_data"] = x
    return out


def audit_context_coverage(daily_bars: pd.DataFrame, series_meta: Dict[str, Any], safe_lag_days: int = 1) -> Dict[str, Any]:
    data = series_meta.get("_data")
    out: Dict[str, Any] = {k: v for k, v in series_meta.items() if not k.startswith("_")}
    out.update({
        "safe_lag_days": safe_lag_days,
        "bar_date_count": int(len(daily_bars)),
        "same_day_coverage_pct": None,
        "safe_lag_coverage_pct": None,
        "staleness_days_profile": {"n": 0},
    })
    if data is None or len(data) == 0 or daily_bars.empty:
        return out

    ext = data.copy()
    ext["date"] = ext["timestamp"].dt.floor("D")
    ext = ext.sort_values("date").drop_duplicates("date", keep="last")

    bars = daily_bars[["timestamp", "date"]].copy()
    bars["timestamp"] = ensure_utc(bars["timestamp"])
    bars["date_ts"] = bars["timestamp"].dt.floor("D")

    same = bars.merge(ext[["date", "value"]], left_on="date_ts", right_on="date", how="left")
    out["same_day_coverage_pct"] = pct(float(same["value"].notna().sum()), float(len(same)))

    # Safe no-lookahead daily context: use latest external date <= bar_date - safe_lag_days.
    targets = bars[["date_ts"]].copy()
    targets["target_date"] = targets["date_ts"] - pd.Timedelta(days=safe_lag_days)
    left = targets.sort_values("target_date")
    right = ext.rename(columns={"date": "ext_date"})[["ext_date", "value"]].sort_values("ext_date")
    aligned = pd.merge_asof(left, right, left_on="target_date", right_on="ext_date", direction="backward")
    out["safe_lag_coverage_pct"] = pct(float(aligned["value"].notna().sum()), float(len(aligned)))
    stale = (aligned["target_date"] - aligned["ext_date"]).dt.days
    out["staleness_days_profile"] = q_profile(stale.dropna())
    return out


def audit_cme_reference(daily_bars: pd.DataFrame, cme_meta: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {k: v for k, v in cme_meta.items() if not k.startswith("_")}
    out.update({
        "overlap_rows": 0,
        "overlap_pct_of_bar_days": None,
        "close_diff_bps_profile": {"n": 0},
        "return_corr": None,
        "return_sign_agreement_pct": None,
        "same_day_return_rows": 0,
    })
    data = cme_meta.get("_data")
    if data is None or len(data) == 0 or daily_bars.empty:
        return out
    cme = data.copy()
    cme["date"] = cme["timestamp"].dt.date.astype(str)
    cme = cme.rename(columns={"value": "cme_close"})
    mt5 = daily_bars[["date", "close", "ret_bps"]].rename(columns={"close": "mt5_close", "ret_bps": "mt5_ret_bps"})
    joined = mt5.merge(cme[["date", "cme_close"]], on="date", how="inner")
    joined["cme_ret_bps"] = joined["cme_close"].pct_change() * 10000.0
    joined["close_diff_bps"] = (joined["mt5_close"] - joined["cme_close"]).abs() / joined["mt5_close"].replace(0, np.nan) * 10000.0
    ret = joined.dropna(subset=["mt5_ret_bps", "cme_ret_bps"])
    out["overlap_rows"] = int(len(joined))
    out["overlap_pct_of_bar_days"] = pct(float(len(joined)), float(len(mt5)))
    out["close_diff_bps_profile"] = q_profile(joined["close_diff_bps"])
    out["same_day_return_rows"] = int(len(ret))
    if len(ret) >= 30:
        out["return_corr"] = float(ret["mt5_ret_bps"].corr(ret["cme_ret_bps"]))
        out["return_sign_agreement_pct"] = pct(float((np.sign(ret["mt5_ret_bps"]) == np.sign(ret["cme_ret_bps"])).sum()), float(len(ret)))
    return out


def load_cme_reference(path: Path) -> Dict[str, Any]:
    df, err = read_csv_safe(path)
    out: Dict[str, Any] = {
        "key": "cme_gc_reference",
        "path": str(path),
        "exists": path.exists(),
        "schema_ok": False,
        "required_ok": False,
        "row_count": 0,
        "timestamp_column": None,
        "start": None,
        "end": None,
        "columns": [],
        "numeric_profiles": {},
        "error": err,
    }
    if df is None:
        return out
    out["columns"] = list(df.columns)
    ts_col = detect_col(df.columns, ["timestamp", "date", "datetime", "time"])
    ohlc_cols = detect_ohlc(df.columns)
    out["timestamp_column"] = ts_col
    missing = [k for k, v in {"timestamp": ts_col, **ohlc_cols}.items() if v is None]
    if missing:
        out["error"] = f"missing_required_columns: {missing}"
        return out
    x = df[[ts_col] + [ohlc_cols[k] for k in OHLC]].copy()  # type: ignore[list-item]
    x.columns = ["timestamp", *OHLC]
    x["timestamp"] = ensure_utc(x["timestamp"])
    for c in OHLC:
        x[c] = pd.to_numeric(x[c], errors="coerce")
    x = x.dropna(subset=["timestamp", *OHLC]).sort_values("timestamp").drop_duplicates("timestamp")
    out["row_count"] = int(len(x))
    out["schema_ok"] = bool(len(x) >= 100)
    out["required_ok"] = out["schema_ok"]
    out["start"] = x["timestamp"].min().isoformat() if not x.empty else None
    out["end"] = x["timestamp"].max().isoformat() if not x.empty else None
    out["numeric_profiles"] = {c: q_profile(x[c]) for c in OHLC}
    out["_data"] = x[["timestamp", "close"]].rename(columns={"close": "value"})
    return out


def audit_news_calendar(path: Path, bars: pd.DataFrame, pre_hours: float, post_hours: float) -> Dict[str, Any]:
    df, err = read_csv_safe(path)
    out: Dict[str, Any] = {
        "key": "news_calendar",
        "path": str(path),
        "exists": path.exists(),
        "schema_ok": False,
        "blackout_ready": False,
        "row_count": 0,
        "timestamp_column": None,
        "event_column": None,
        "currency_column": None,
        "impact_column": None,
        "category_column": None,
        "start": None,
        "end": None,
        "columns": [],
        "macro_semantic_hits": 0,
        "central_bank_gold_only_hits": 0,
        "usd_or_unknown_rows": 0,
        "blackout_window": {"pre_hours": pre_hours, "post_hours": post_hours},
        "bars_in_blackout": 0,
        "bars_in_blackout_pct": None,
        "event_category_counts_top20": [],
        "event_source_counts_top20": [],
        "decision_reason": None,
        "error": err,
    }
    if df is None:
        out["decision_reason"] = "missing"
        return out
    out["columns"] = list(df.columns)
    ts_col = detect_col(df.columns, ["timestamp", "event_time_utc", "datetime", "date", "time"])
    event_col = detect_col(df.columns, ["event", "title", "name"])
    currency_col = detect_col(df.columns, ["currency", "ccy"])
    impact_col = detect_col(df.columns, ["impact", "importance", "initial_importance"])
    category_col = detect_col(df.columns, ["category", "event_class", "event_channel", "manual_tags"])
    out.update({
        "timestamp_column": ts_col,
        "event_column": event_col,
        "currency_column": currency_col,
        "impact_column": impact_col,
        "category_column": category_col,
    })
    if ts_col is None or event_col is None:
        out["decision_reason"] = "missing_timestamp_or_event"
        return out

    x = df.copy()
    x["_ts"] = ensure_utc(x[ts_col])
    x["_event"] = x[event_col].fillna("").astype(str)
    if currency_col:
        x["_currency"] = x[currency_col].fillna("").astype(str).str.upper()
    else:
        x["_currency"] = "USD"
    if impact_col:
        x["_impact"] = x[impact_col].fillna("").astype(str).str.lower()
    else:
        x["_impact"] = "high"
    if category_col:
        x["_category"] = x[category_col].fillna("").astype(str)
    else:
        x["_category"] = ""
    if "source" in x.columns:
        x["_source"] = x["source"].fillna("").astype(str)
    elif "source_name" in x.columns:
        x["_source"] = x["source_name"].fillna("").astype(str)
    else:
        x["_source"] = ""

    x = x.dropna(subset=["_ts"])
    out["row_count"] = int(len(x))
    out["start"] = x["_ts"].min().isoformat() if not x.empty else None
    out["end"] = x["_ts"].max().isoformat() if not x.empty else None
    out["schema_ok"] = bool(len(x) >= 10)
    out["usd_or_unknown_rows"] = int(((x["_currency"].isin(["USD", "", "US"])) | x["_currency"].isna()).sum())

    semantic_text = (x["_event"] + " " + x["_category"] + " " + x["_source"]).str.casefold()
    macro_mask = semantic_text.apply(lambda s: any(k in s for k in MACRO_CATEGORY_KEYWORDS))
    cb_gold_mask = semantic_text.apply(lambda s: any(k in s for k in CENTRAL_BANK_GOLD_KEYWORDS))
    out["macro_semantic_hits"] = int(macro_mask.sum())
    out["central_bank_gold_only_hits"] = int((cb_gold_mask & ~macro_mask).sum())
    out["event_category_counts_top20"] = [
        {"category": str(k), "n": int(v)}
        for k, v in x["_category"].value_counts().head(20).items()
    ]
    out["event_source_counts_top20"] = [
        {"source": str(k), "n": int(v)}
        for k, v in x["_source"].value_counts().head(20).items()
    ]

    # Blackout coverage on intraday bars.
    if not bars.empty and len(x) > 0:
        bar_ns = bars["timestamp"].sort_values().astype("int64").to_numpy()
        hit = np.zeros(len(bar_ns), dtype=bool)
        pre = pd.Timedelta(hours=pre_hours)
        post = pd.Timedelta(hours=post_hours)
        for ts in x["_ts"]:
            lo = int((ts - pre).value)
            hi = int((ts + post).value)
            a = int(np.searchsorted(bar_ns, lo, side="left"))
            b = int(np.searchsorted(bar_ns, hi, side="right"))
            if b > a:
                hit[a:b] = True
        out["bars_in_blackout"] = int(hit.sum())
        out["bars_in_blackout_pct"] = pct(float(hit.sum()), float(len(hit)))

    # More nuanced than Stage45B1B: numeric shock calendars such as DGS2/DFII10 are macro context.
    macro_hit_ratio = pct(float(out["macro_semantic_hits"]), float(max(1, len(x)))) or 0.0
    if not out["schema_ok"]:
        out["decision_reason"] = "too_few_rows_or_invalid_timestamps"
    elif out["bars_in_blackout"] <= 0:
        out["decision_reason"] = "schema_ok_but_no_bars_in_blackout_window"
    elif out["macro_semantic_hits"] >= 10 or macro_hit_ratio >= 0.05:
        out["blackout_ready"] = True
        out["decision_reason"] = "macro_blackout_alignment_ready"
    else:
        out["decision_reason"] = "schema_ok_but_macro_semantics_need_review"
    return out


def build_summary(args: argparse.Namespace) -> Dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    db_path = repo_root / args.db_path
    outdir = repo_root / args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    bars, bar_meta = load_bars(
        db_path=db_path,
        table=args.table,
        source=args.source,
        symbol=args.symbol,
        timeframe=args.timeframe,
    )
    daily = aggregate_daily_bars(bars)

    dxy = normalize_daily_value(repo_root / P0_PATHS["dxy"], "dxy", ["close", "value", "dxy"])
    us10y = normalize_daily_value(repo_root / P0_PATHS["us10y_yield"], "us10y_yield", ["yield", "close", "value"])
    real_yield = normalize_daily_value(repo_root / OPTIONAL_PATHS["real_yield"], "real_yield", ["yield", "close", "value"])
    us02y = normalize_daily_value(repo_root / OPTIONAL_PATHS["us02y_yield"], "us02y_yield", ["yield", "close", "value"])
    cme = load_cme_reference(repo_root / P0_PATHS["cme_gc_reference"])
    news = audit_news_calendar(repo_root / P0_PATHS["news_calendar"], bars, args.news_pre_hours, args.news_post_hours)

    context_coverage = {
        "dxy": audit_context_coverage(daily, dxy, safe_lag_days=args.daily_safe_lag_days),
        "us10y_yield": audit_context_coverage(daily, us10y, safe_lag_days=args.daily_safe_lag_days),
        "real_yield_optional": audit_context_coverage(daily, real_yield, safe_lag_days=args.daily_safe_lag_days),
        "us02y_yield_optional": audit_context_coverage(daily, us02y, safe_lag_days=args.daily_safe_lag_days),
    }
    cme_audit = audit_cme_reference(daily, cme)

    blockers: List[str] = []
    warnings: List[str] = []

    p0_schema_ok = []
    p0_missing = []
    for key, meta in [("dxy", dxy), ("us10y_yield", us10y), ("cme_gc_reference", cme), ("news_calendar", news)]:
        ok = bool(meta.get("schema_ok") or (key == "news_calendar" and news.get("schema_ok")))
        if ok:
            p0_schema_ok.append(key)
        else:
            p0_missing.append(key)
            blockers.append(f"{key}_schema_not_ready")

    for key in ["dxy", "us10y_yield"]:
        cov = context_coverage[key].get("safe_lag_coverage_pct")
        if cov is None or cov < args.min_daily_context_coverage:
            blockers.append(f"{key}_safe_lag_coverage_below_{args.min_daily_context_coverage}")

    cme_overlap = cme_audit.get("overlap_pct_of_bar_days")
    if cme_overlap is None or cme_overlap < args.min_cme_overlap:
        blockers.append(f"cme_overlap_below_{args.min_cme_overlap}")
    corr = cme_audit.get("return_corr")
    if corr is not None and corr < args.min_cme_return_corr:
        warnings.append(f"cme_return_corr_below_{args.min_cme_return_corr}")
    elif corr is None:
        warnings.append("cme_return_corr_unavailable")

    if not news.get("blackout_ready"):
        warnings.append("news_calendar_schema_ok_but_semantic_blackout_review_recommended")
    if (news.get("bars_in_blackout_pct") or 0.0) <= 0:
        blockers.append("news_blackout_windows_do_not_cover_any_bars")

    if blockers:
        recommended = "Stage45B2A_EXTERNAL_CONTEXT_ALIGNMENT_REPAIR"
        status = "EXTERNAL_CONTEXT_ALIGNMENT_AUDIT_BLOCKED_NO_PROMOTION"
    else:
        recommended = "Stage45B3_PREDEFINED_EXTERNAL_CONTEXT_BASELINE_DESIGN"
        status = "EXTERNAL_CONTEXT_ALIGNMENT_AUDIT_READY_NO_PROMOTION"

    summary = {
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
            "news_blackout_window_hours": {"pre": args.news_pre_hours, "post": args.news_post_hours},
        },
        "bar_load_meta": bar_meta,
        "daily_bar_profile": {
            "rows": int(len(daily)),
            "start": daily["timestamp"].min().isoformat() if not daily.empty else None,
            "end": daily["timestamp"].max().isoformat() if not daily.empty else None,
            "bar_count_profile": q_profile(daily["bar_count"]),
            "daily_ret_bps_profile": q_profile(daily["ret_bps"].dropna()),
        },
        "p0_schema_ok_keys": p0_schema_ok,
        "p0_missing_or_invalid_keys": p0_missing,
        "context_coverage": context_coverage,
        "cme_reference_alignment": cme_audit,
        "news_calendar_alignment": news,
        "decision": {
            "status": status,
            "promotion": NO_GO,
            "EA": NO_GO,
            "paper_live": NO_GO,
            "live": NO_GO,
            "blockers": blockers,
            "warnings": warnings,
            "recommended_next_stage": recommended,
            "rationale": [
                "P0 external context is evaluated for timestamp coverage, no-lookahead daily alignment, reference-feed overlap, and news blackout coverage.",
                "This stage does not create signals, rescue Stage41/42/43 candidates, or authorize EA/paper/live.",
                "If alignment is ready, the next stage may design a predefined external-context baseline; otherwise repair alignment first.",
            ],
            "not_allowed": [
                "candidate_rescue_from_stage41_42_43",
                "post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets",
                "EA_paper_live_live_from_archived_rows",
                "ML_before_robust_cost_aware_baseline",
                "new_candle_only_blind_megascan_before_external_context_alignment_is_audited",
            ],
        },
        "promotion": NO_GO,
        "EA": NO_GO,
        "paper_live": NO_GO,
        "live": NO_GO,
        "next_allowed_step": recommended,
    }

    # Remove internal dataframes before JSON output.
    def strip_internal(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: strip_internal(v) for k, v in obj.items() if not k.startswith("_")}
        if isinstance(obj, list):
            return [strip_internal(x) for x in obj]
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        return obj

    summary = strip_internal(summary)

    summary_path = outdir / "stage45b2_external_context_alignment_audit_summary.json"
    md_path = outdir / "stage45b2_external_context_alignment_audit.md"
    coverage_path = outdir / "stage45b2_context_coverage.csv"
    cme_path = outdir / "stage45b2_cme_alignment_profile.csv"
    news_path = outdir / "stage45b2_news_blackout_profile.csv"

    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(summary, md_path)
    write_csvs(summary, coverage_path, cme_path, news_path)

    if args.print_summary:
        print(json.dumps({
            "stage": STAGE,
            "status": summary["decision"]["status"],
            "p0_schema_ok_keys": summary["p0_schema_ok_keys"],
            "p0_missing_or_invalid_keys": summary["p0_missing_or_invalid_keys"],
            "blockers": summary["decision"]["blockers"],
            "warnings": summary["decision"]["warnings"],
            "next_allowed_step": summary["next_allowed_step"],
            "summary_path": str(summary_path),
            "markdown_path": str(md_path),
        }, indent=2, ensure_ascii=False))
    return summary


def write_markdown(summary: Dict[str, Any], path: Path) -> None:
    d = summary["decision"]
    lines: List[str] = []
    lines.append(f"# {STAGE}\n")
    lines.append("## Decision\n")
    lines.append("```text")
    lines.append(f"promotion = {summary['promotion']}")
    lines.append(f"EA = {summary['EA']}")
    lines.append(f"paper_live = {summary['paper_live']}")
    lines.append(f"live = {summary['live']}")
    lines.append(f"status = {d['status']}")
    lines.append(f"recommended_next_stage = {d['recommended_next_stage']}")
    lines.append("```\n")
    lines.append("Stage45B2 audits external context alignment only. It does not create signals, shortlist candidates, or promote archived rows.\n")

    lines.append("## P0 schema readiness\n")
    lines.append("| key | status |")
    lines.append("| :-- | :-- |")
    for key in ["dxy", "us10y_yield", "cme_gc_reference", "news_calendar"]:
        status = "READY" if key in summary["p0_schema_ok_keys"] else "MISSING_OR_INVALID"
        lines.append(f"| {key} | {status} |")
    lines.append("")

    lines.append("## Daily context coverage\n")
    lines.append("| key | rows | start | end | same_day_coverage | safe_lag_coverage | staleness_median_days |")
    lines.append("| :-- | --: | :-- | :-- | --: | --: | --: |")
    for key, v in summary["context_coverage"].items():
        stale = v.get("staleness_days_profile", {})
        lines.append(
            f"| {key} | {v.get('row_count', 0)} | {v.get('start') or ''} | {v.get('end') or ''} | "
            f"{fmt_pct(v.get('same_day_coverage_pct'))} | {fmt_pct(v.get('safe_lag_coverage_pct'))} | {fmt_num(stale.get('median'))} |"
        )
    lines.append("")

    cme = summary["cme_reference_alignment"]
    lines.append("## CME/GC reference alignment\n")
    lines.append("```json")
    lines.append(json.dumps({
        "schema_ok": cme.get("schema_ok"),
        "row_count": cme.get("row_count"),
        "start": cme.get("start"),
        "end": cme.get("end"),
        "overlap_rows": cme.get("overlap_rows"),
        "overlap_pct_of_bar_days": cme.get("overlap_pct_of_bar_days"),
        "return_corr": cme.get("return_corr"),
        "return_sign_agreement_pct": cme.get("return_sign_agreement_pct"),
        "close_diff_bps_profile": cme.get("close_diff_bps_profile"),
    }, indent=2, ensure_ascii=False))
    lines.append("```\n")

    news = summary["news_calendar_alignment"]
    lines.append("## News calendar blackout alignment\n")
    lines.append("```json")
    lines.append(json.dumps({
        "schema_ok": news.get("schema_ok"),
        "blackout_ready": news.get("blackout_ready"),
        "row_count": news.get("row_count"),
        "start": news.get("start"),
        "end": news.get("end"),
        "macro_semantic_hits": news.get("macro_semantic_hits"),
        "central_bank_gold_only_hits": news.get("central_bank_gold_only_hits"),
        "bars_in_blackout": news.get("bars_in_blackout"),
        "bars_in_blackout_pct": news.get("bars_in_blackout_pct"),
        "decision_reason": news.get("decision_reason"),
    }, indent=2, ensure_ascii=False))
    lines.append("```\n")

    lines.append("## Blockers and warnings\n")
    lines.append("```json")
    lines.append(json.dumps({"blockers": d.get("blockers", []), "warnings": d.get("warnings", [])}, indent=2, ensure_ascii=False))
    lines.append("```\n")

    lines.append("## Not allowed\n")
    for x in d.get("not_allowed", []):
        lines.append(f"- `{x}`")
    lines.append("\n## Anti-overfit note\n")
    lines.append("Do not use this audit to rescue Stage41/42/43 rows. If alignment passes, the next valid action is a predefined external-context baseline design, not a post-hoc candidate rescue pass.\n")
    path.write_text("\n".join(lines), encoding="utf-8")


def fmt_pct(v: Any) -> str:
    return "" if v is None else f"{float(v) * 100:.2f}%"


def fmt_num(v: Any) -> str:
    return "" if v is None else f"{float(v):.3f}"


def write_csvs(summary: Dict[str, Any], coverage_path: Path, cme_path: Path, news_path: Path) -> None:
    rows = []
    for key, v in summary["context_coverage"].items():
        stale = v.get("staleness_days_profile", {})
        rows.append({
            "key": key,
            "path": v.get("path"),
            "schema_ok": v.get("schema_ok"),
            "row_count": v.get("row_count"),
            "start": v.get("start"),
            "end": v.get("end"),
            "same_day_coverage_pct": v.get("same_day_coverage_pct"),
            "safe_lag_coverage_pct": v.get("safe_lag_coverage_pct"),
            "staleness_median_days": stale.get("median"),
            "staleness_p90_days": stale.get("p90"),
        })
    pd.DataFrame(rows).to_csv(coverage_path, index=False)

    cme = summary["cme_reference_alignment"]
    pd.DataFrame([{k: v for k, v in cme.items() if not isinstance(v, (dict, list))}]).to_csv(cme_path, index=False)

    news = summary["news_calendar_alignment"]
    pd.DataFrame([{k: v for k, v in news.items() if not isinstance(v, (dict, list))}]).to_csv(news_path, index=False)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=STAGE)
    p.add_argument("--repo-root", default=".")
    p.add_argument("--db-path", default="data/local/xauusd_local_store.sqlite")
    p.add_argument("--table", default="bars")
    p.add_argument("--source", default="amarkets_mt5")
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--timeframe", default="M15")
    p.add_argument("--outdir", default="reports/stage45b2")
    p.add_argument("--daily-safe-lag-days", type=int, default=1)
    p.add_argument("--news-pre-hours", type=float, default=2.0)
    p.add_argument("--news-post-hours", type=float, default=2.0)
    p.add_argument("--min-daily-context-coverage", type=float, default=0.85)
    p.add_argument("--min-cme-overlap", type=float, default=0.70)
    p.add_argument("--min-cme-return-corr", type=float, default=0.80)
    p.add_argument("--print-summary", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    build_summary(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
