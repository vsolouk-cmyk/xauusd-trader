#!/usr/bin/env python3
"""
Stage45B2A external context alignment repair - loaderfix/searchsorted implementation.

Purpose:
- Repair news blackout alignment counting after Stage45B2 showed zero bars in blackout.
- Use robust UTC pandas timestamps and numpy.searchsorted over M15 bar timestamps.
- Write canonical data/external/news_blackout_windows.csv only when a selected variant is created.

This script is diagnostic/plumbing only. It does not create trading signals, shortlist
candidates, or authorize promotion/paper/live/live.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sqlite3
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

STAGE = "Stage45B2A_EXTERNAL_CONTEXT_ALIGNMENT_REPAIR"
NO_GO = "NO_GO"

MACRO_KEYWORDS = [
    "cpi", "inflation", "pce", "fomc", "fed", "rate", "rates", "nfp",
    "nonfarm", "payroll", "employment", "unemployment", "jobs", "earnings",
    "retail sales", "ism", "pmi", "gdp", "yield", "real_yield", "dgs",
    "dollar", "usd", "ppi", "consumer price", "personal consumption",
    "front_end_yield", "nominal_yield", "real yield", "federal reserve",
]
CENTRAL_BANK_GOLD_KEYWORDS = [
    "central_bank_gold", "central bank gold", "gold demand", "wgc", "world gold council",
]

TIMEFRAME_ALIASES = {
    "m1": 1, "1m": 1, "1min": 1,
    "m5": 5, "5m": 5, "5min": 5,
    "m15": 15, "15m": 15, "15min": 15,
    "h1": 60, "1h": 60, "60m": 60,
}

TS_CANDIDATES = ["utc_time", "timestamp", "time", "datetime", "date", "source_time"]
OHLC = ["open", "high", "low", "close"]


def json_default(obj: Any) -> Any:
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        if math.isnan(float(obj)):
            return None
        return float(obj)
    if isinstance(obj, (pd.Timestamp,)):
        if pd.isna(obj):
            return None
        return obj.isoformat()
    if isinstance(obj, (Path,)):
        return str(obj)
    return str(obj)


def profile_numeric(values: Iterable[float]) -> Dict[str, Any]:
    arr = pd.to_numeric(pd.Series(list(values)), errors="coerce").dropna().to_numpy(dtype=float)
    if arr.size == 0:
        return {"n": 0}
    return {
        "n": int(arr.size),
        "min": float(np.min(arr)),
        "p10": float(np.percentile(arr, 10)),
        "median": float(np.percentile(arr, 50)),
        "p90": float(np.percentile(arr, 90)),
        "p95": float(np.percentile(arr, 95)),
        "p99": float(np.percentile(arr, 99)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
    }


def ensure_utc(series: pd.Series) -> pd.Series:
    # Robust parse: accepts Z, +00:00, naive dates; coerces invalid values.
    return pd.to_datetime(series, errors="coerce", utc=True)


def ns_array(ts: pd.Series) -> np.ndarray:
    # pandas datetime64[ns, UTC] -> int64 ns. Nat becomes min int, so drop before call.
    return ts.astype("int64").to_numpy(dtype=np.int64)


def normalize_tf(v: Any) -> str:
    s = str(v).strip().lower().replace(" ", "")
    if s in ("m15", "15m", "15min"):
        return "M15"
    if s in ("h1", "1h", "60m"):
        return "H1"
    if s in ("m5", "5m", "5min"):
        return "M5"
    if s in ("m1", "1m", "1min"):
        return "M1"
    return str(v).strip()


def tf_minutes(tf: str) -> int:
    return TIMEFRAME_ALIASES.get(str(tf).strip().lower(), 15)


def detect_column(columns: List[str], candidates: List[str]) -> Optional[str]:
    cmap = {str(c).strip().lower(): c for c in columns}
    for cand in candidates:
        if cand.lower() in cmap:
            return cmap[cand.lower()]
    return None


def load_bars(repo_root: Path, db_path: str, table: str, source: str, symbol: str, timeframe: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    path = repo_root / db_path
    meta: Dict[str, Any] = {
        "db_path": str(path), "table": table, "requested_source": source,
        "requested_symbol": symbol, "requested_timeframe": timeframe,
    }
    if not path.exists():
        meta["error"] = "db_missing"
        return pd.DataFrame(), meta

    con = sqlite3.connect(str(path))
    try:
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]
        meta["columns"] = cols
        ts_col = detect_column(cols, TS_CANDIDATES)
        if not ts_col:
            meta["error"] = "timestamp_column_missing"
            return pd.DataFrame(), meta

        q = f"SELECT * FROM {table}"
        df = pd.read_sql_query(q, con)
    finally:
        con.close()

    meta["pre_filter_rows"] = int(len(df))
    for col in ["source", "symbol"]:
        if col not in df.columns:
            meta["error"] = f"{col}_column_missing"
            return pd.DataFrame(), meta
    if "timeframe" not in df.columns:
        meta["error"] = "timeframe_column_missing"
        return pd.DataFrame(), meta

    req_tf_norm = normalize_tf(timeframe)
    mask = (
        df["source"].astype(str).str.strip().str.casefold().eq(source.strip().casefold())
        & df["symbol"].astype(str).str.strip().str.casefold().eq(symbol.strip().casefold())
        & df["timeframe"].map(normalize_tf).eq(req_tf_norm)
    )
    df = df.loc[mask].copy()
    meta["post_filter_rows_before_clean"] = int(len(df))

    df["timestamp"] = ensure_utc(df[ts_col])
    for c in OHLC:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["timestamp", "open", "high", "low", "close"] if all(c in df.columns for c in OHLC) else ["timestamp"])
    df = df.sort_values("timestamp").drop_duplicates("timestamp")
    meta["loaded_rows"] = int(len(df))
    meta["loaded_start"] = df["timestamp"].min().isoformat() if len(df) else None
    meta["loaded_end"] = df["timestamp"].max().isoformat() if len(df) else None
    meta["timestamp_column"] = ts_col
    return df, meta


def load_news(repo_root: Path, news_path: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    path = repo_root / news_path
    meta: Dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        meta.update({"schema_ok": False, "row_count": 0, "error": "missing"})
        return pd.DataFrame(), meta

    df = pd.read_csv(path)
    cols = list(df.columns)
    ts_col = detect_column(cols, ["timestamp", "event_time_utc", "datetime", "date", "time"])
    ev_col = detect_column(cols, ["event", "title", "name"])
    cur_col = detect_column(cols, ["currency"])
    impact_col = detect_column(cols, ["impact", "importance", "initial_importance"])
    cat_col = detect_column(cols, ["category", "event_class", "event_channel"])
    src_col = detect_column(cols, ["source", "source_name", "source_kind"])

    meta.update({
        "columns": cols,
        "timestamp_column": ts_col,
        "event_column": ev_col,
        "currency_column": cur_col,
        "impact_column": impact_col,
        "category_column": cat_col,
        "source_column": src_col,
        "schema_ok": bool(ts_col and ev_col),
    })
    if not ts_col or not ev_col:
        meta.update({"row_count": int(len(df)), "error": "missing_timestamp_or_event"})
        return pd.DataFrame(), meta

    out = pd.DataFrame()
    out["timestamp"] = ensure_utc(df[ts_col])
    out["event"] = df[ev_col].astype(str).fillna("")
    out["currency"] = df[cur_col].astype(str).fillna("") if cur_col else ""
    out["impact"] = df[impact_col].astype(str).fillna("") if impact_col else ""
    out["category"] = df[cat_col].astype(str).fillna("") if cat_col else ""
    out["source"] = df[src_col].astype(str).fillna("") if src_col else ""
    out = out.dropna(subset=["timestamp"])
    out = out[out["event"].astype(str).str.len() > 0]
    out = out.sort_values("timestamp").drop_duplicates(["timestamp", "event"])

    text = (out["event"].astype(str) + " " + out["category"].astype(str) + " " + out["source"].astype(str)).str.lower()
    macro_mask = pd.Series(False, index=out.index)
    for kw in MACRO_KEYWORDS:
        macro_mask = macro_mask | text.str.contains(kw, regex=False, na=False)
    cb_gold_mask = pd.Series(False, index=out.index)
    for kw in CENTRAL_BANK_GOLD_KEYWORDS:
        cb_gold_mask = cb_gold_mask | text.str.contains(kw, regex=False, na=False)
    currency_text = out["currency"].astype(str).str.upper().fillna("")
    usd_or_unknown = currency_text.eq("USD") | currency_text.eq("") | currency_text.eq("NAN")

    out["macro_semantic"] = macro_mask.astype(bool)
    out["central_bank_gold_only"] = cb_gold_mask.astype(bool)
    out["usd_or_unknown"] = usd_or_unknown.astype(bool)

    meta.update({
        "row_count": int(len(out)),
        "valid_timestamp_count": int(out["timestamp"].notna().sum()),
        "start": out["timestamp"].min().isoformat() if len(out) else None,
        "end": out["timestamp"].max().isoformat() if len(out) else None,
        "macro_semantic_hits": int(out["macro_semantic"].sum()),
        "central_bank_gold_only_hits": int(out["central_bank_gold_only"].sum()),
        "usd_or_unknown_rows": int(out["usd_or_unknown"].sum()),
        "error": None,
    })
    return out, meta


def build_windows(events: pd.DataFrame, pre_hours: float, post_hours: float) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame(columns=["window_start", "window_end", "event_timestamp", "event", "category", "currency", "impact", "source"])
    out = pd.DataFrame()
    out["window_start"] = events["timestamp"] - pd.to_timedelta(float(pre_hours), unit="h")
    out["window_end"] = events["timestamp"] + pd.to_timedelta(float(post_hours), unit="h")
    out["event_timestamp"] = events["timestamp"]
    for c in ["event", "category", "currency", "impact", "source"]:
        out[c] = events[c].values if c in events.columns else ""
    return out.sort_values("window_start").reset_index(drop=True)


def overlap_profile(bars: pd.DataFrame, windows: pd.DataFrame, tf_min: int) -> Tuple[Dict[str, Any], pd.DataFrame, pd.DataFrame]:
    if bars.empty or windows.empty:
        return {
            "event_count": int(len(windows)), "bars_in_blackout": 0, "bars_in_blackout_pct": 0.0,
            "events_with_at_least_one_bar": 0, "bars_per_event_profile": {"n": int(len(windows))},
            "debug": "empty_bars_or_windows",
        }, windows.assign(bars_in_window=0), pd.DataFrame()

    bar_ts = bars["timestamp"].dropna().sort_values().reset_index(drop=True)
    bar_ns = ns_array(bar_ts)
    bar_end_ns = bar_ns + int(tf_min * 60 * 1_000_000_000)

    w = windows.dropna(subset=["window_start", "window_end"]).copy().reset_index(drop=True)
    w_start_ns = ns_array(w["window_start"])
    w_end_ns = ns_array(w["window_end"])

    blackout_mask = np.zeros(len(bar_ns), dtype=bool)
    counts: List[int] = []
    # A bar overlaps window if bar_start < window_end AND bar_end > window_start.
    # Since bar_end is monotonic with bar_start, search bounds can be on starts:
    # candidates with start < w_end and start >= w_start - tf_delta.
    tf_delta_ns = int(tf_min * 60 * 1_000_000_000)
    for s_ns, e_ns in zip(w_start_ns, w_end_ns):
        left = np.searchsorted(bar_ns, s_ns - tf_delta_ns, side="right")
        right = np.searchsorted(bar_ns, e_ns, side="left")
        if right > left:
            idx = np.arange(left, right)
            overlap = (bar_ns[idx] < e_ns) & (bar_end_ns[idx] > s_ns)
            actual_idx = idx[overlap]
            blackout_mask[actual_idx] = True
            counts.append(int(actual_idx.size))
        else:
            counts.append(0)

    w["bars_in_window"] = counts
    sample_cols = ["timestamp", "open", "high", "low", "close"]
    bar_sample = bars.loc[blackout_mask, [c for c in sample_cols if c in bars.columns]].head(500).copy()

    total_bars = len(bars)
    bars_in = int(blackout_mask.sum())
    profile = {
        "event_count": int(len(w)),
        "bars_in_blackout": bars_in,
        "bars_in_blackout_pct": float(bars_in / total_bars * 100.0) if total_bars else 0.0,
        "events_with_at_least_one_bar": int((pd.Series(counts) > 0).sum()),
        "bars_per_event_profile": profile_numeric(counts),
        "debug": {
            "bar_count": int(total_bars),
            "bar_start_min": bar_ts.min().isoformat() if len(bar_ts) else None,
            "bar_start_max": bar_ts.max().isoformat() if len(bar_ts) else None,
            "window_start_min": w["window_start"].min().isoformat() if len(w) else None,
            "window_end_max": w["window_end"].max().isoformat() if len(w) else None,
            "tf_minutes": int(tf_min),
            "method": "numpy_searchsorted_bar_interval_overlap_ns",
        },
    }
    return profile, w, bar_sample


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[c]):
            out[c] = out[c].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    out.to_csv(path, index=False)


def build_summary(args: argparse.Namespace) -> Dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    outdir = repo_root / args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    bars, bar_meta = load_bars(repo_root, args.db_path, args.table, args.source, args.symbol, args.timeframe)
    news, news_meta = load_news(repo_root, args.news_path)
    tf_min = tf_minutes(args.timeframe)

    variants: Dict[str, pd.DataFrame] = {
        "all_events": news,
        "macro_semantic_only": news[news.get("macro_semantic", pd.Series(False, index=news.index)).astype(bool)] if not news.empty else news,
        "macro_usd_or_unknown": news[
            news.get("macro_semantic", pd.Series(False, index=news.index)).astype(bool)
            & news.get("usd_or_unknown", pd.Series(False, index=news.index)).astype(bool)
        ] if not news.empty else news,
    }

    profiles: Dict[str, Any] = {}
    windows_by_variant: Dict[str, pd.DataFrame] = {}
    samples_by_variant: Dict[str, pd.DataFrame] = {}
    for name, ev in variants.items():
        win = build_windows(ev, args.news_pre_hours, args.news_post_hours)
        prof, w_with_counts, sample = overlap_profile(bars, win, tf_min)
        windows_path = outdir / f"stage45b2a_news_blackout_windows_{name}.csv"
        write_csv(w_with_counts, windows_path)
        prof["windows_csv"] = str(windows_path)
        profiles[name] = prof
        windows_by_variant[name] = w_with_counts
        samples_by_variant[name] = sample

    # Prefer macro_usd_or_unknown, then macro_semantic_only, then all_events if selected has zero events.
    selected = "macro_usd_or_unknown"
    if len(windows_by_variant[selected]) == 0 and len(windows_by_variant["macro_semantic_only"]):
        selected = "macro_semantic_only"
    if len(windows_by_variant[selected]) == 0 and len(windows_by_variant["all_events"]):
        selected = "all_events"

    canonical = repo_root / args.blackout_windows_path
    write_csv(windows_by_variant[selected], canonical)

    profile_rows = []
    for k, p in profiles.items():
        profile_rows.append({
            "variant": k,
            "event_count": p.get("event_count"),
            "bars_in_blackout": p.get("bars_in_blackout"),
            "bars_in_blackout_pct": p.get("bars_in_blackout_pct"),
            "events_with_at_least_one_bar": p.get("events_with_at_least_one_bar"),
            "bars_per_event_median": p.get("bars_per_event_profile", {}).get("median"),
            "windows_csv": p.get("windows_csv"),
        })
    profile_csv = outdir / "stage45b2a_blackout_repair_profile.csv"
    pd.DataFrame(profile_rows).to_csv(profile_csv, index=False)

    sample_csv = outdir / "stage45b2a_blackout_bar_sample.csv"
    write_csv(samples_by_variant[selected], sample_csv)

    selected_bars = int(profiles[selected].get("bars_in_blackout", 0))
    blockers: List[str] = []
    warnings: List[str] = []
    if not news_meta.get("schema_ok"):
        blockers.append("news_calendar_schema_invalid")
    if selected_bars <= 0:
        blockers.append("news_blackout_windows_still_do_not_cover_any_bars")
    # FRED numeric backfill categories are not scheduled macro calendar, but are still external context events.
    if news_meta.get("macro_semantic_hits", 0) and news_meta.get("macro_semantic_hits", 0) < news_meta.get("row_count", 0):
        warnings.append("news_calendar_contains_mixed_semantics_review_recommended")

    status = "EXTERNAL_CONTEXT_ALIGNMENT_REPAIR_READY_NO_PROMOTION" if not blockers else "EXTERNAL_CONTEXT_ALIGNMENT_REPAIR_BLOCKED_NO_PROMOTION"
    next_step = "Stage45B3_EXTERNAL_CONTEXT_BASELINE_DESIGN_PRECHECK" if not blockers else "Stage45B2A_CONTINUE_EXTERNAL_CONTEXT_ALIGNMENT_REPAIR"

    summary = {
        "stage": STAGE,
        "settings": {
            "repo_root": str(repo_root),
            "db_path": args.db_path,
            "table": args.table,
            "source": args.source,
            "symbol": args.symbol,
            "timeframe": args.timeframe,
            "news_path": args.news_path,
            "outdir": args.outdir,
            "blackout_windows_path": args.blackout_windows_path,
            "news_blackout_window_hours": {"pre": args.news_pre_hours, "post": args.news_post_hours},
            "overlap_method": "numpy_searchsorted_bar_interval_overlap_ns_loaderfix2",
        },
        "bar_load_meta": bar_meta,
        "news_calendar_meta": news_meta,
        "blackout_repair_profiles": profiles,
        "selected_blackout_variant": selected,
        "selected_bars_in_blackout": selected_bars,
        "canonical_blackout_windows_path": args.blackout_windows_path,
        "profile_csv": str(profile_csv),
        "bar_sample_csv": str(sample_csv),
        "decision": {
            "status": status,
            "promotion": NO_GO,
            "EA": NO_GO,
            "paper_live": NO_GO,
            "live": NO_GO,
            "blockers": blockers,
            "warnings": warnings,
            "recommended_next_stage": next_step,
            "rationale": [
                "Stage45B2A loaderfix2 uses UTC interval overlap over sorted bar timestamps.",
                "This stage only repairs alignment diagnostics and blackout-window materialization.",
                "It does not create signals, rescue archived candidates, or authorize EA/paper/live.",
            ],
            "not_allowed": [
                "candidate_rescue_from_stage41_42_43",
                "post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets",
                "EA_paper_live_live_from_archived_rows",
                "ML_before_robust_cost_aware_baseline",
                "new_blind_megascan_before_external_context_alignment_repair_is_clean",
            ],
        },
        "promotion": NO_GO,
        "EA": NO_GO,
        "paper_live": NO_GO,
        "live": NO_GO,
        "next_allowed_step": next_step,
    }

    summary_path = outdir / "stage45b2a_external_context_alignment_repair_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=json_default), encoding="utf-8")

    md_path = outdir / "stage45b2a_external_context_alignment_repair.md"
    md_path.write_text(render_markdown(summary), encoding="utf-8")

    if args.print_summary:
        print(json.dumps({
            "stage": STAGE,
            "status": status,
            "selected_blackout_variant": selected,
            "selected_bars_in_blackout": selected_bars,
            "blockers": blockers,
            "next_allowed_step": next_step,
            "summary_path": str(summary_path),
            "markdown_path": str(md_path),
        }, indent=2, ensure_ascii=False))

    return summary


def render_markdown(s: Dict[str, Any]) -> str:
    lines: List[str] = []
    d = s["decision"]
    lines.append(f"# {STAGE}")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    lines.append(f"promotion = {s['promotion']}")
    lines.append(f"EA = {s['EA']}")
    lines.append(f"paper_live = {s['paper_live']}")
    lines.append(f"live = {s['live']}")
    lines.append(f"status = {d['status']}")
    lines.append(f"recommended_next_stage = {d['recommended_next_stage']}")
    lines.append("```")
    lines.append("")
    lines.append("Stage45B2A repairs only external-context/news-blackout alignment diagnostics. It does not create trading signals, shortlist candidates, or promote archived rows.")
    lines.append("")
    lines.append("## News calendar meta")
    lines.append("")
    nm = s.get("news_calendar_meta", {})
    lines.append("```json")
    lines.append(json.dumps({k: nm.get(k) for k in ["exists", "schema_ok", "row_count", "start", "end", "macro_semantic_hits", "central_bank_gold_only_hits", "usd_or_unknown_rows"]}, indent=2, ensure_ascii=False, default=json_default))
    lines.append("```")
    lines.append("")
    lines.append("## Blackout repair profiles")
    lines.append("")
    lines.append("| variant | event_count | bars_in_blackout | bars_in_blackout_pct | events_with_bar | median_bars_per_event |")
    lines.append("| :-- | --: | --: | --: | --: | --: |")
    for k, p in s.get("blackout_repair_profiles", {}).items():
        bpe = p.get("bars_per_event_profile", {})
        lines.append(f"| {k} | {p.get('event_count', 0)} | {p.get('bars_in_blackout', 0)} | {p.get('bars_in_blackout_pct', 0):.3f}% | {p.get('events_with_at_least_one_bar', 0)} | {bpe.get('median', '')} |")
    lines.append("")
    lines.append("## Selected repaired blackout windows")
    lines.append("")
    lines.append("```text")
    lines.append(f"selected_blackout_variant = {s.get('selected_blackout_variant')}")
    lines.append(f"selected_bars_in_blackout = {s.get('selected_bars_in_blackout')}")
    lines.append(f"canonical_blackout_windows_path = {s.get('canonical_blackout_windows_path')}")
    lines.append("```")
    lines.append("")
    lines.append("## Blockers and warnings")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps({"blockers": d.get("blockers", []), "warnings": d.get("warnings", [])}, indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")
    lines.append("## Not allowed")
    lines.append("")
    for x in d.get("not_allowed", []):
        lines.append(f"- `{x}`")
    lines.append("")
    lines.append("## Anti-overfit note")
    lines.append("")
    lines.append("Do not use this repair step to rescue Stage41/42/43 rows. If alignment repair is clean, the next valid step is a predefined external-context baseline design precheck, not a post-hoc candidate rescue pass.")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--db-path", default="data/local/xauusd_local_store.sqlite")
    ap.add_argument("--table", default="bars")
    ap.add_argument("--source", default="amarkets_mt5")
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--timeframe", default="M15")
    ap.add_argument("--news-path", default="data/external/news_calendar.csv")
    ap.add_argument("--outdir", default="reports/stage45b2a")
    ap.add_argument("--blackout-windows-path", default="data/external/news_blackout_windows.csv")
    ap.add_argument("--news-pre-hours", type=float, default=2.0)
    ap.add_argument("--news-post-hours", type=float, default=2.0)
    ap.add_argument("--print-summary", action="store_true")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    build_summary(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
