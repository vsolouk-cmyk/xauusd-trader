#!/usr/bin/env python3
"""
Stage45B3A_NEWS_CALENDAR_SEMANTIC_REDUCTION

Purpose:
  Separate scheduled high-impact macro blackout events from numeric shock/backfill
  context events. This stage repairs the news-calendar design blocker reported by
  Stage45B3 without creating signals, shortlists, candidate rescues, or promotion.

Inputs:
  - data/external/news_calendar.csv
  - data/local/xauusd_local_store.sqlite (bars table, for blackout coverage)
  - reports/stage45b3/stage45b3_external_context_baseline_design_precheck_summary.json

Outputs:
  - reports/stage45b3a/stage45b3a_news_calendar_semantic_reduction_summary.json
  - reports/stage45b3a/stage45b3a_news_calendar_semantic_reduction.md
  - reports/stage45b3a/stage45b3a_semantic_reduction_profile.csv
  - reports/stage45b3a/stage45b3a_category_source_profile.csv
  - reports/stage45b3a/stage45b3a_selected_scheduled_macro_events.csv
  - reports/stage45b3a/stage45b3a_excluded_context_events.csv
  - reports/stage45b3a/stage45b3a_scheduled_macro_blackout_windows.csv

If --apply-canonical is used:
  - data/external/news_calendar_mixed_pre_stage45b3a.csv
  - data/external/news_calendar.csv                       (reduced scheduled macro)
  - data/external/news_shock_context_events.csv           (excluded context/shock rows)
  - data/external/news_blackout_windows.csv               (scheduled macro blackout windows)

All gates remain NO_GO.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

STAGE = "Stage45B3A_NEWS_CALENDAR_SEMANTIC_REDUCTION"

REQUIRED_NEWS_COLUMNS = [
    "timestamp",
    "event",
    "currency",
    "impact",
    "category",
    "actual",
    "forecast",
    "previous",
    "source",
]

SCHEDULED_MACRO_KEYWORDS = [
    "fomc",
    "federal reserve",
    "fed funds",
    "rate decision",
    "interest rate decision",
    "monetary policy",
    "press conference",
    "cpi",
    "consumer price",
    "inflation",
    "core cpi",
    "pce",
    "core pce",
    "personal consumption",
    "nfp",
    "nonfarm",
    "payroll",
    "employment",
    "unemployment",
    "average hourly",
    "earnings",
    "jobs",
    "jobless",
    "initial claims",
    "ism",
    "pmi",
    "retail sales",
    "gdp",
]

SCHEDULED_CATEGORY_KEYWORDS = [
    "fomc",
    "cpi",
    "pce",
    "nfp",
    "payroll",
    "employment",
    "unemployment",
    "jobs",
    "rate_decision",
    "rate",
    "inflation",
    "retail_sales",
    "ism",
    "pmi",
    "gdp",
]

EXCLUDED_SOURCE_KEYWORDS = [
    "fred_numeric_backfill",
    "gdelt:",
]

EXCLUDED_CATEGORY_KEYWORDS = [
    "shock",
    "central_bank_gold_demand",
    "oil_supply",
]


def now_iso() -> str:
    return pd.Timestamp.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_float(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if x is None:
            return default
        if isinstance(x, float) and math.isnan(x):
            return default
        return float(x)
    except Exception:
        return default


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path), "error": "missing"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"exists": True, "path": str(path), "error": str(exc)}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    rename = {}
    for col in df.columns:
        c = str(col).strip()
        cl = c.lower().strip().replace(" ", "_")
        if cl in {"datetime", "date", "event_time_utc", "time", "timestamp"}:
            rename[col] = "timestamp"
        elif cl in {"title", "name", "event_name", "event"}:
            rename[col] = "event"
        elif cl in {"importance", "initial_importance", "impact"}:
            rename[col] = "impact"
        elif cl in {"event_class", "category", "class"}:
            rename[col] = "category"
        elif cl in {"source_name", "source", "source_kind"}:
            rename[col] = "source"
        elif cl in {"ccy", "currency"}:
            rename[col] = "currency"
        elif cl in {"actual", "forecast", "previous"}:
            rename[col] = cl
    return df.rename(columns=rename)


def load_news(path: Path) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    meta: Dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        meta.update({"schema_ok": False, "error": "missing", "row_count": 0})
        return pd.DataFrame(columns=REQUIRED_NEWS_COLUMNS), meta
    try:
        raw = pd.read_csv(path)
        df = normalize_columns(raw)
        for c in REQUIRED_NEWS_COLUMNS:
            if c not in df.columns:
                df[c] = ""
        df = df[REQUIRED_NEWS_COLUMNS].copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        df["event"] = df["event"].fillna("").astype(str)
        for c in ["currency", "impact", "category", "actual", "forecast", "previous", "source"]:
            df[c] = df[c].fillna("").astype(str)
        df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        meta.update(
            {
                "schema_ok": bool(len(df) > 0 and df["event"].str.len().gt(0).any()),
                "row_count": int(len(df)),
                "valid_timestamp_count": int(df["timestamp"].notna().sum()),
                "start": df["timestamp"].min().isoformat() if len(df) else None,
                "end": df["timestamp"].max().isoformat() if len(df) else None,
                "columns": list(df.columns),
                "error": None,
            }
        )
        return df, meta
    except Exception as exc:
        meta.update({"schema_ok": False, "error": str(exc), "row_count": 0})
        return pd.DataFrame(columns=REQUIRED_NEWS_COLUMNS), meta


def text_contains_any(series: pd.Series, keywords: Iterable[str]) -> pd.Series:
    text = series.fillna("").astype(str).str.lower()
    mask = pd.Series(False, index=series.index)
    for kw in keywords:
        mask = mask | text.str.contains(kw, regex=False, na=False)
    return mask


def classify_events(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    combined = (
        out["event"].fillna("").astype(str)
        + " "
        + out["category"].fillna("").astype(str)
        + " "
        + out["source"].fillna("").astype(str)
    )
    event_macro = text_contains_any(combined, SCHEDULED_MACRO_KEYWORDS)
    cat_macro = text_contains_any(out["category"], SCHEDULED_CATEGORY_KEYWORDS)
    excluded_source = text_contains_any(out["source"], EXCLUDED_SOURCE_KEYWORDS)
    excluded_category = text_contains_any(out["category"], EXCLUDED_CATEGORY_KEYWORDS)
    scheduled_seed = out["source"].fillna("").astype(str).str.lower().str.contains("scheduled_seed", regex=False, na=False)
    high_impact = out["impact"].fillna("").astype(str).str.lower().isin(["high", "3", "1.0", "1", "true"])
    currency_ok = out["currency"].fillna("").astype(str).str.upper().isin(["", "USD", "US", "UNKNOWN"])

    scheduled_macro = currency_ok & (scheduled_seed | event_macro | cat_macro) & (~excluded_source) & (~excluded_category)

    # If an event is explicitly scheduled_seed, allow it even if category naming is compact like fomc_statement.
    scheduled_macro = scheduled_macro | (scheduled_seed & currency_ok & (event_macro | cat_macro))

    out["semantic_group"] = np.where(
        scheduled_macro,
        "scheduled_macro_blackout",
        np.where(excluded_source | excluded_category, "numeric_or_news_context_not_blackout", "other_not_blackout"),
    )
    out["is_scheduled_macro_blackout"] = scheduled_macro.astype(bool)
    out["is_numeric_or_news_context"] = (~scheduled_macro).astype(bool)
    out["semantic_reason"] = np.where(
        scheduled_macro,
        "scheduled_macro_us_event",
        np.where(excluded_source, "excluded_source_numeric_backfill_or_gdelt", np.where(excluded_category, "excluded_category_shock_or_gold_demand", "not_scheduled_macro")),
    )
    out["impact"] = np.where(out["impact"].fillna("").astype(str).str.len() == 0, "high", out["impact"])
    out["currency"] = np.where(out["currency"].fillna("").astype(str).str.len() == 0, "USD", out["currency"])
    return out


def infer_event_window(row: pd.Series, args: argparse.Namespace) -> Tuple[float, float, str]:
    txt = f"{row.get('event','')} {row.get('category','')}".lower()
    if any(k in txt for k in ["fomc", "rate decision", "fed funds", "press conference", "monetary policy"]):
        return float(args.fomc_pre_hours), float(args.fomc_post_hours), "fomc_or_rate_policy_window"
    if any(k in txt for k in ["cpi", "inflation", "pce", "consumer price"]):
        return float(args.inflation_pre_hours), float(args.inflation_post_hours), "inflation_window"
    if any(k in txt for k in ["nfp", "nonfarm", "payroll", "employment", "unemployment", "jobs", "hourly earnings", "jobless"]):
        return float(args.jobs_pre_hours), float(args.jobs_post_hours), "jobs_window"
    return float(args.default_pre_hours), float(args.default_post_hours), "default_scheduled_macro_window"


def build_windows(events: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for idx, row in events.reset_index(drop=True).iterrows():
        pre, post, rule = infer_event_window(row, args)
        ts = pd.Timestamp(row["timestamp"])
        rows.append(
            {
                "event_id": int(idx),
                "timestamp": ts.isoformat(),
                "window_start": (ts - pd.Timedelta(hours=pre)).isoformat(),
                "window_end": (ts + pd.Timedelta(hours=post)).isoformat(),
                "pre_hours": pre,
                "post_hours": post,
                "window_rule": rule,
                "event": row.get("event", ""),
                "currency": row.get("currency", "USD"),
                "impact": row.get("impact", "high"),
                "category": row.get("category", ""),
                "source": row.get("source", ""),
            }
        )
    return pd.DataFrame(rows)


def load_bars(repo_root: Path, db_path: str, table: str, source: str, symbol: str, timeframe: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    path = repo_root / db_path
    meta: Dict[str, Any] = {
        "db_path": str(path),
        "table": table,
        "requested_source": source,
        "requested_symbol": symbol,
        "requested_timeframe": timeframe,
        "exists": path.exists(),
    }
    if not path.exists():
        meta.update({"loaded_rows": 0, "error": "missing_db"})
        return pd.DataFrame(columns=["timestamp"]), meta
    try:
        con = sqlite3.connect(path)
        q = f"""
            SELECT utc_time, open, high, low, close, tick_volume, spread
            FROM {table}
            WHERE source=? AND symbol=? AND timeframe=?
            ORDER BY utc_time
        """
        df = pd.read_sql_query(q, con, params=(source, symbol, timeframe))
        con.close()
        df["timestamp"] = pd.to_datetime(df["utc_time"], utc=True, errors="coerce")
        df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        meta.update(
            {
                "loaded_rows": int(len(df)),
                "loaded_start": df["timestamp"].min().isoformat() if len(df) else None,
                "loaded_end": df["timestamp"].max().isoformat() if len(df) else None,
                "error": None,
            }
        )
        return df, meta
    except Exception as exc:
        meta.update({"loaded_rows": 0, "error": str(exc)})
        return pd.DataFrame(columns=["timestamp"]), meta


def estimate_tf_minutes(bar_ts: pd.Series) -> int:
    if len(bar_ts) < 3:
        return 15
    diffs = bar_ts.sort_values().diff().dropna().dt.total_seconds() / 60.0
    if len(diffs) == 0:
        return 15
    med = float(diffs.median())
    if not np.isfinite(med) or med <= 0:
        return 15
    return int(round(med))


def compute_blackout_overlap(bars: pd.DataFrame, windows: pd.DataFrame) -> Dict[str, Any]:
    if len(bars) == 0 or len(windows) == 0:
        return {
            "bars_in_blackout": 0,
            "bars_in_blackout_pct": 0.0,
            "events_with_at_least_one_bar": 0,
            "bars_per_event_profile": {"n": int(len(windows))},
            "bar_sample": pd.DataFrame(),
        }

    bar_start = pd.to_datetime(bars["timestamp"], utc=True, errors="coerce").dropna().sort_values().reset_index(drop=True)
    tf_minutes = estimate_tf_minutes(bar_start)
    bar_end = bar_start + pd.Timedelta(minutes=tf_minutes)
    starts_ns = bar_start.astype("int64").to_numpy()
    ends_ns = bar_end.astype("int64").to_numpy()

    mask = np.zeros(len(bar_start), dtype=bool)
    per_event: List[int] = []
    for _, row in windows.iterrows():
        ws = pd.to_datetime(row["window_start"], utc=True, errors="coerce")
        we = pd.to_datetime(row["window_end"], utc=True, errors="coerce")
        if pd.isna(ws) or pd.isna(we) or we <= ws:
            per_event.append(0)
            continue
        ws_ns = int(ws.value)
        we_ns = int(we.value)
        # Candidate bars start before window end, and end after window start.
        left = int(np.searchsorted(starts_ns, we_ns, side="left"))
        if left <= 0:
            per_event.append(0)
            continue
        candidate_idx = np.arange(0, left)
        hit = candidate_idx[ends_ns[:left] > ws_ns]
        if len(hit):
            mask[hit] = True
        per_event.append(int(len(hit)))

    bars_in = int(mask.sum())
    sample = pd.DataFrame({"timestamp": bar_start[mask].head(200).dt.strftime("%Y-%m-%dT%H:%M:%SZ")})
    arr = np.asarray(per_event, dtype=float)
    prof: Dict[str, Any] = {"n": int(len(arr))}
    if len(arr):
        for q, name in [(0, "min"), (0.1, "p10"), (0.5, "median"), (0.9, "p90"), (0.95, "p95"), (0.99, "p99"), (1, "max")]:
            prof[name] = float(np.quantile(arr, q))
        prof["mean"] = float(arr.mean())
    return {
        "bars_in_blackout": bars_in,
        "bars_in_blackout_pct": float(bars_in / len(bar_start)) if len(bar_start) else 0.0,
        "events_with_at_least_one_bar": int((arr > 0).sum()) if len(arr) else 0,
        "bars_per_event_profile": prof,
        "tf_minutes": tf_minutes,
        "bar_count": int(len(bar_start)),
        "bar_sample": sample,
    }


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def write_markdown(path: Path, summary: Dict[str, Any]) -> None:
    dec = summary["decision"]
    lines: List[str] = []
    lines.append(f"# {STAGE}\n")
    lines.append("## Decision\n")
    lines.append("```text")
    for k in ["promotion", "EA", "paper_live", "live", "status", "recommended_next_stage"]:
        lines.append(f"{k} = {dec.get(k)}")
    lines.append("```\n")
    lines.append("Stage45B3A reduces the news calendar semantics only. It does not create trading signals, shortlist candidates, or promote archived rows.\n")
    lines.append("## Semantic reduction\n")
    sr = summary.get("semantic_reduction", {})
    lines.append("| metric | value |")
    lines.append("| :-- | --: |")
    for k in ["input_event_count", "scheduled_macro_event_count", "excluded_context_event_count", "scheduled_macro_blackout_bars", "scheduled_macro_blackout_pct"]:
        lines.append(f"| {k} | {sr.get(k)} |")
    lines.append("\n## Event windows\n")
    lines.append("```json")
    lines.append(json.dumps(summary.get("event_window_settings", {}), indent=2, ensure_ascii=False))
    lines.append("```\n")
    lines.append("## Outputs\n")
    for k, v in summary.get("outputs", {}).items():
        lines.append(f"- `{k}`: `{v}`")
    lines.append("\n## Blockers and warnings\n")
    lines.append("```json")
    lines.append(json.dumps({"blockers": dec.get("blockers", []), "warnings": dec.get("warnings", [])}, indent=2, ensure_ascii=False))
    lines.append("```\n")
    lines.append("## Not allowed\n")
    for item in dec.get("not_allowed", []):
        lines.append(f"- `{item}`")
    lines.append("\n## Anti-overfit note\n")
    lines.append("Do not use this reduction to rescue Stage41/42/43 rows. If the precheck passes after reduction, the next action must still be a predefined external-context baseline design.\n")
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--db-path", default="data/local/xauusd_local_store.sqlite")
    ap.add_argument("--table", default="bars")
    ap.add_argument("--source", default="amarkets_mt5")
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--timeframe", default="M15")
    ap.add_argument("--news-path", default="data/external/news_calendar.csv")
    ap.add_argument("--stage45b3-summary", default="reports/stage45b3/stage45b3_external_context_baseline_design_precheck_summary.json")
    ap.add_argument("--outdir", default="reports/stage45b3a")
    ap.add_argument("--apply-canonical", action="store_true", help="Overwrite canonical news_calendar.csv with reduced scheduled macro calendar after writing backup.")
    ap.add_argument("--max-blackout-pct", type=float, default=0.25)
    ap.add_argument("--min-blackout-pct", type=float, default=0.0005)
    ap.add_argument("--fomc-pre-hours", type=float, default=4.0)
    ap.add_argument("--fomc-post-hours", type=float, default=8.0)
    ap.add_argument("--inflation-pre-hours", type=float, default=2.0)
    ap.add_argument("--inflation-post-hours", type=float, default=4.0)
    ap.add_argument("--jobs-pre-hours", type=float, default=2.0)
    ap.add_argument("--jobs-post-hours", type=float, default=4.0)
    ap.add_argument("--default-pre-hours", type=float, default=1.0)
    ap.add_argument("--default-post-hours", type=float, default=2.0)
    ap.add_argument("--print-summary", action="store_true")
    args = ap.parse_args(argv)

    repo_root = Path(args.repo_root).expanduser().resolve()
    outdir = repo_root / args.outdir
    ensure_dir(outdir)
    data_external = repo_root / "data" / "external"
    ensure_dir(data_external)

    stage45b3 = read_json(repo_root / args.stage45b3_summary)
    news_path = repo_root / args.news_path
    news, news_meta = load_news(news_path)
    bars, bar_meta = load_bars(repo_root, args.db_path, args.table, args.source, args.symbol, args.timeframe)

    classified = classify_events(news)
    selected = classified[classified["is_scheduled_macro_blackout"]].copy().sort_values("timestamp").reset_index(drop=True)
    excluded = classified[~classified["is_scheduled_macro_blackout"]].copy().sort_values("timestamp").reset_index(drop=True)
    windows = build_windows(selected, args)
    overlap = compute_blackout_overlap(bars, windows)

    # Report files.
    selected_report = outdir / "stage45b3a_selected_scheduled_macro_events.csv"
    excluded_report = outdir / "stage45b3a_excluded_context_events.csv"
    windows_report = outdir / "stage45b3a_scheduled_macro_blackout_windows.csv"
    sample_report = outdir / "stage45b3a_blackout_bar_sample.csv"
    profile_report = outdir / "stage45b3a_semantic_reduction_profile.csv"
    category_source_report = outdir / "stage45b3a_category_source_profile.csv"

    selected.to_csv(selected_report, index=False)
    excluded.to_csv(excluded_report, index=False)
    windows.to_csv(windows_report, index=False)
    overlap.get("bar_sample", pd.DataFrame()).to_csv(sample_report, index=False)

    category_counts = classified.groupby(["semantic_group", "category", "source"], dropna=False).size().reset_index(name="n").sort_values("n", ascending=False)
    category_counts.to_csv(category_source_report, index=False)

    profile_rows = [
        {"metric": "input_event_count", "value": int(len(classified)), "note": "Rows in input canonical news calendar before semantic reduction."},
        {"metric": "scheduled_macro_event_count", "value": int(len(selected)), "note": "Rows retained for scheduled macro blackout."},
        {"metric": "excluded_context_event_count", "value": int(len(excluded)), "note": "Rows moved to context/shock file, not blackout."},
        {"metric": "scheduled_macro_blackout_bars", "value": int(overlap.get("bars_in_blackout", 0)), "note": "M15 bars inside reduced scheduled macro windows."},
        {"metric": "scheduled_macro_blackout_pct", "value": float(overlap.get("bars_in_blackout_pct", 0.0)), "note": "Share of M15 bars inside reduced scheduled macro windows."},
    ]
    pd.DataFrame(profile_rows).to_csv(profile_report, index=False)

    blockers: List[str] = []
    warnings: List[str] = []
    if not news_meta.get("schema_ok"):
        blockers.append("news_calendar_schema_invalid")
    if len(selected) == 0:
        blockers.append("scheduled_macro_calendar_empty_after_reduction")
    pct = float(overlap.get("bars_in_blackout_pct", 0.0) or 0.0)
    bars_in = int(overlap.get("bars_in_blackout", 0) or 0)
    if bars_in <= 0:
        blockers.append("scheduled_macro_blackout_windows_do_not_cover_any_bars")
    elif pct < args.min_blackout_pct:
        warnings.append("scheduled_macro_blackout_coverage_very_small")
    if pct > args.max_blackout_pct:
        blockers.append("scheduled_macro_blackout_coverage_still_too_broad")
    if len(excluded) > 0:
        warnings.append("numeric_or_news_context_events_separated_from_blackout")
    if not bool(args.apply_canonical):
        warnings.append("canonical_files_not_applied_run_with_apply_canonical_to_repair_repo")

    canonical_outputs: Dict[str, str] = {}
    if args.apply_canonical and not blockers:
        backup = data_external / "news_calendar_mixed_pre_stage45b3a.csv"
        shock_path = data_external / "news_shock_context_events.csv"
        reduced_path = data_external / "news_calendar.csv"
        blackout_path = data_external / "news_blackout_windows.csv"
        scheduled_path = data_external / "news_calendar_scheduled_macro.csv"
        # Preserve mixed source once, then overwrite canonical with reduced scheduled macro.
        if not backup.exists():
            news.to_csv(backup, index=False)
        selected[REQUIRED_NEWS_COLUMNS].to_csv(scheduled_path, index=False)
        selected[REQUIRED_NEWS_COLUMNS].to_csv(reduced_path, index=False)
        excluded.to_csv(shock_path, index=False)
        windows.to_csv(blackout_path, index=False)
        canonical_outputs = {
            "backup_mixed_news_calendar": str(backup.relative_to(repo_root)),
            "reduced_canonical_news_calendar": str(reduced_path.relative_to(repo_root)),
            "scheduled_macro_news_calendar": str(scheduled_path.relative_to(repo_root)),
            "shock_context_events": str(shock_path.relative_to(repo_root)),
            "canonical_blackout_windows": str(blackout_path.relative_to(repo_root)),
        }

    status = "NEWS_CALENDAR_SEMANTIC_REDUCTION_READY_NO_PROMOTION" if not blockers else "NEWS_CALENDAR_SEMANTIC_REDUCTION_BLOCKED_NO_PROMOTION"
    next_stage = "Stage45B3_RERUN_EXTERNAL_CONTEXT_BASELINE_DESIGN_PRECHECK" if not blockers else "Stage45B3A_CONTINUE_NEWS_CALENDAR_SEMANTIC_REDUCTION"

    summary: Dict[str, Any] = {
        "stage": STAGE,
        "settings": {
            "repo_root": str(repo_root),
            "db_path": args.db_path,
            "table": args.table,
            "source": args.source,
            "symbol": args.symbol,
            "timeframe": args.timeframe,
            "news_path": args.news_path,
            "stage45b3_summary": args.stage45b3_summary,
            "outdir": args.outdir,
            "apply_canonical": bool(args.apply_canonical),
            "min_blackout_pct": args.min_blackout_pct,
            "max_blackout_pct": args.max_blackout_pct,
        },
        "stage45b3_reference": {
            "exists": bool(stage45b3.get("stage") or stage45b3.get("decision")),
            "status": stage45b3.get("decision", {}).get("status") if isinstance(stage45b3.get("decision"), dict) else stage45b3.get("status"),
            "recommended_next_stage": stage45b3.get("decision", {}).get("recommended_next_stage") if isinstance(stage45b3.get("decision"), dict) else stage45b3.get("recommended_next_stage"),
            "blockers": stage45b3.get("decision", {}).get("blockers", []) if isinstance(stage45b3.get("decision"), dict) else [],
        },
        "bar_load_meta": bar_meta,
        "news_calendar_meta": news_meta,
        "event_window_settings": {
            "fomc_pre_hours": args.fomc_pre_hours,
            "fomc_post_hours": args.fomc_post_hours,
            "inflation_pre_hours": args.inflation_pre_hours,
            "inflation_post_hours": args.inflation_post_hours,
            "jobs_pre_hours": args.jobs_pre_hours,
            "jobs_post_hours": args.jobs_post_hours,
            "default_pre_hours": args.default_pre_hours,
            "default_post_hours": args.default_post_hours,
        },
        "semantic_reduction": {
            "input_event_count": int(len(classified)),
            "scheduled_macro_event_count": int(len(selected)),
            "excluded_context_event_count": int(len(excluded)),
            "scheduled_macro_blackout_bars": int(bars_in),
            "scheduled_macro_blackout_pct": pct,
            "events_with_at_least_one_bar": int(overlap.get("events_with_at_least_one_bar", 0) or 0),
            "bars_per_event_profile": overlap.get("bars_per_event_profile", {}),
            "tf_minutes": overlap.get("tf_minutes"),
            "bar_count": overlap.get("bar_count"),
        },
        "canonical_outputs": canonical_outputs,
        "outputs": {
            "summary_json": str((outdir / "stage45b3a_news_calendar_semantic_reduction_summary.json").relative_to(repo_root)),
            "markdown": str((outdir / "stage45b3a_news_calendar_semantic_reduction.md").relative_to(repo_root)),
            "semantic_reduction_profile_csv": str(profile_report.relative_to(repo_root)),
            "category_source_profile_csv": str(category_source_report.relative_to(repo_root)),
            "selected_scheduled_macro_events_csv": str(selected_report.relative_to(repo_root)),
            "excluded_context_events_csv": str(excluded_report.relative_to(repo_root)),
            "scheduled_macro_blackout_windows_csv": str(windows_report.relative_to(repo_root)),
            "blackout_bar_sample_csv": str(sample_report.relative_to(repo_root)),
        },
        "decision": {
            "status": status,
            "promotion": "NO_GO",
            "EA": "NO_GO",
            "paper_live": "NO_GO",
            "live": "NO_GO",
            "blockers": blockers,
            "warnings": warnings,
            "recommended_next_stage": next_stage,
            "rationale": [
                "Stage45B3A separates scheduled macro blackout events from numeric shock/backfill context labels.",
                "Numeric shock/backfill rows are preserved as context events but are not treated as no-trade blackout windows.",
                "This stage does not create signals, rescue archived candidates, or authorize EA/paper/live.",
            ],
            "not_allowed": [
                "candidate_rescue_from_stage41_42_43",
                "post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets",
                "EA_paper_live_live_from_archived_rows",
                "ML_before_robust_cost_aware_baseline",
                "new_blind_megascan_before_news_semantic_reduction_precheck_is_clean",
            ],
        },
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "next_allowed_step": next_stage,
    }

    summary_path = outdir / "stage45b3a_news_calendar_semantic_reduction_summary.json"
    md_path = outdir / "stage45b3a_news_calendar_semantic_reduction.md"
    write_json(summary_path, summary)
    write_markdown(md_path, summary)

    if args.print_summary:
        print(
            json.dumps(
                {
                    "stage": STAGE,
                    "status": status,
                    "scheduled_macro_event_count": int(len(selected)),
                    "excluded_context_event_count": int(len(excluded)),
                    "scheduled_macro_blackout_bars": int(bars_in),
                    "scheduled_macro_blackout_pct": pct,
                    "blockers": blockers,
                    "warnings": warnings,
                    "next_allowed_step": next_stage,
                    "summary_path": str(summary_path),
                    "markdown_path": str(md_path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
