#!/usr/bin/env python3
"""
Stage45B3B_SCHEDULED_MACRO_CALENDAR_ACQUISITION

Acquire/build a scheduled US macro calendar suitable for news blackout design.
This is a data-acquisition/repair step only: no signals, no candidate rescue,
no EA/paper/live authorization.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import shutil
import sqlite3
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

try:
    import numpy as np
    import pandas as pd
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"Missing dependency: {exc}. Install pandas/numpy first.")

STAGE = "Stage45B3B_SCHEDULED_MACRO_CALENDAR_ACQUISITION"
NO_GO = {
    "promotion": "NO_GO",
    "EA": "NO_GO",
    "paper_live": "NO_GO",
    "live": "NO_GO",
}

BLS_YEAR_URL = "https://www.bls.gov/schedule/{year}/home.htm"
FED_FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"

MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}
MONTH_RE = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t|tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
DATE_RE = re.compile(rf"({MONTH_RE})\s+(\d{{1,2}}),\s*(\d{{4}})", re.I)
TIME_RE = re.compile(r"(\d{1,2})\s*:\s*(\d{2})\s*(AM|PM)", re.I)
FOMC_RANGE_RE = re.compile(rf"({MONTH_RE})\s+(\d{{1,2}})(?:\s*-\s*(\d{{1,2}}))?", re.I)

SCHEDULED_KEYWORDS = {
    "cpi": ["consumer price index", "cpi"],
    "employment": ["employment situation", "nonfarm", "payroll", "jobs report"],
}


class SimpleTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_cell = False
        self.in_row = False
        self.current_cell: list[str] = []
        self.current_row: list[str] = []
        self.rows: list[list[str]] = []
        self.text_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t == "tr":
            self.in_row = True
            self.current_row = []
        if t in ("td", "th"):
            self.in_cell = True
            self.current_cell = []

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in ("td", "th") and self.in_cell:
            cell = " ".join("".join(self.current_cell).split())
            self.current_row.append(html.unescape(cell))
            self.in_cell = False
            self.current_cell = []
        if t == "tr" and self.in_row:
            if any(c.strip() for c in self.current_row):
                self.rows.append(self.current_row[:])
            self.in_row = False
            self.current_row = []

    def handle_data(self, data: str) -> None:
        if data:
            self.text_chunks.append(data)
        if self.in_cell:
            self.current_cell.append(data)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_url(url: str, timeout: float = 30.0) -> tuple[str | None, str | None]:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "xauusd-research-stage45b3b/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        return raw.decode("utf-8", errors="replace"), None
    except Exception as exc:
        return None, repr(exc)


def parse_month_name(s: str) -> int | None:
    key = s.lower().replace(".", "")
    return MONTHS.get(key)


def parse_date_from_text(text: str) -> datetime | None:
    m = DATE_RE.search(text)
    if not m:
        return None
    mon = parse_month_name(m.group(1))
    if mon is None:
        return None
    day = int(m.group(2))
    year = int(m.group(3))
    return datetime(year, mon, day)


def parse_time_from_text(text: str, default_hour: int = 8, default_minute: int = 30) -> tuple[int, int, str]:
    m = TIME_RE.search(text)
    if not m:
        return default_hour, default_minute, "default"
    hour = int(m.group(1))
    minute = int(m.group(2))
    ampm = m.group(3).upper()
    if ampm == "PM" and hour != 12:
        hour += 12
    if ampm == "AM" and hour == 12:
        hour = 0
    return hour, minute, "parsed"


def local_et_to_utc_iso(year: int, month: int, day: int, hour: int, minute: int) -> str:
    if ZoneInfo is None:
        # Fallback: assume Eastern daylight for Apr-Oct, EST otherwise.
        offset_hours = -4 if 3 <= month <= 11 else -5
        dt = datetime(year, month, day, hour, minute, tzinfo=timezone(timedelta(hours=offset_hours)))
    else:
        dt = datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("America/New_York"))
    return dt.astimezone(timezone.utc).isoformat()


def classify_bls_release(text: str) -> tuple[str | None, str | None, str | None]:
    low = text.lower()
    if "consumer price index" in low or re.search(r"\bcpi\b", low):
        return "scheduled_cpi_release", "US CPI Release", "inflation"
    if "employment situation" in low:
        return "scheduled_employment_situation_release", "US Employment Situation / NFP Release", "jobs"
    return None, None, None


def parse_bls_year(year: int, timeout: float = 30.0) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    url = BLS_YEAR_URL.format(year=year)
    text, err = fetch_url(url, timeout=timeout)
    meta = {"year": year, "url": url, "fetched": text is not None, "error": err, "rows_seen": 0, "events": 0}
    if text is None:
        return [], meta
    parser = SimpleTableParser()
    parser.feed(text)
    events: list[dict[str, Any]] = []
    meta["rows_seen"] = len(parser.rows)
    for row in parser.rows:
        joined = " | ".join(row)
        category, title, family = classify_bls_release(joined)
        if not category:
            continue
        d = parse_date_from_text(joined)
        if d is None:
            continue
        hour, minute, time_source = parse_time_from_text(joined, 8, 30)
        ts = local_et_to_utc_iso(d.year, d.month, d.day, hour, minute)
        events.append({
            "timestamp": ts,
            "event": title,
            "currency": "USD",
            "impact": "high",
            "category": category,
            "actual": "",
            "forecast": "",
            "previous": "",
            "source": "official_bls_schedule",
            "source_url": url,
            "source_family": family,
            "time_source": time_source,
            "raw_row": joined,
        })
    meta["events"] = len(events)
    return events, meta


def strip_html_text(text: str) -> str:
    parser = SimpleTableParser()
    parser.feed(text)
    return " ".join(" ".join(parser.text_chunks).split())


def parse_fomc_calendar(years: list[int], timeout: float = 30.0) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    text, err = fetch_url(FED_FOMC_URL, timeout=timeout)
    meta = {"url": FED_FOMC_URL, "fetched": text is not None, "error": err, "events": 0, "method": "best_effort_html_text"}
    if text is None:
        return [], meta
    plain = strip_html_text(text)
    events: list[dict[str, Any]] = []
    # Split around year tokens and parse nearby meeting month/day ranges.
    for year in years:
        # Find local segment from this year to next year token where possible.
        idx = plain.find(str(year))
        if idx < 0:
            continue
        next_positions = [plain.find(str(y), idx + 4) for y in years if y > year and plain.find(str(y), idx + 4) >= 0]
        end = min(next_positions) if next_positions else min(len(plain), idx + 3500)
        seg = plain[idx:end]
        for m in FOMC_RANGE_RE.finditer(seg):
            month = parse_month_name(m.group(1))
            if month is None:
                continue
            start_day = int(m.group(2))
            end_day = int(m.group(3)) if m.group(3) else start_day
            # Avoid parsing unrelated prose dates by requiring meeting-context nearby.
            nearby = seg[max(0, m.start() - 80): min(len(seg), m.end() + 120)].lower()
            if not any(k in nearby for k in ["statement", "implementation note", "minutes", "press conference", "meeting"]):
                # The Fed page is noisy; keep only plausible meeting rows.
                continue
            try:
                ts = local_et_to_utc_iso(year, month, end_day, 14, 0)
            except Exception:
                continue
            events.append({
                "timestamp": ts,
                "event": "FOMC Statement / Rate Decision",
                "currency": "USD",
                "impact": "high",
                "category": "scheduled_fomc_statement",
                "actual": "",
                "forecast": "",
                "previous": "",
                "source": "official_federal_reserve_fomc_calendar_best_effort",
                "source_url": FED_FOMC_URL,
                "source_family": "fomc",
                "time_source": "default_14_00_new_york",
                "raw_row": m.group(0),
            })
    # Deduplicate and cap obvious false positives by exact timestamp/category.
    uniq: dict[tuple[str, str], dict[str, Any]] = {}
    for e in events:
        uniq[(e["timestamp"], e["category"])] = e
    events = sorted(uniq.values(), key=lambda x: x["timestamp"])
    meta["events"] = len(events)
    return events, meta


def load_manual_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"Manual events file not found: {path}")
    df = pd.read_csv(path)
    required = {"timestamp", "event"}
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"Manual events missing required columns: {missing}")
    for col in ["currency", "impact", "category", "actual", "forecast", "previous", "source"]:
        if col not in df.columns:
            df[col] = ""
    return df[["timestamp", "event", "currency", "impact", "category", "actual", "forecast", "previous", "source"]].to_dict("records")


def normalize_events(events: list[dict[str, Any]]) -> pd.DataFrame:
    if not events:
        return pd.DataFrame(columns=["timestamp", "event", "currency", "impact", "category", "actual", "forecast", "previous", "source", "source_url", "source_family", "time_source", "raw_row"])
    df = pd.DataFrame(events)
    for col in ["currency", "impact", "category", "actual", "forecast", "previous", "source", "source_url", "source_family", "time_source", "raw_row"]:
        if col not in df.columns:
            df[col] = ""
    ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.loc[ts.notna()].copy()
    df["timestamp"] = ts.loc[ts.notna()].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    df["currency"] = df["currency"].replace("", "USD").fillna("USD")
    df["impact"] = df["impact"].replace("", "high").fillna("high")
    df["source"] = df["source"].replace("", "manual_or_official_scheduled_macro").fillna("manual_or_official_scheduled_macro")
    df = df.sort_values(["timestamp", "event"]).drop_duplicates(["timestamp", "event", "category"])
    return df.reset_index(drop=True)


def load_bars(repo_root: Path, db_path: str, table: str, source: str, symbol: str, timeframe: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    path = repo_root / db_path
    meta: dict[str, Any] = {"db_path": str(path), "table": table, "exists": path.exists(), "loaded_rows": 0, "error": None}
    if not path.exists():
        meta["error"] = "missing_db"
        return pd.DataFrame(columns=["utc_time"]), meta
    try:
        con = sqlite3.connect(path)
        q = f"SELECT utc_time FROM {table} WHERE source=? AND symbol=? AND timeframe=? ORDER BY utc_time"
        df = pd.read_sql_query(q, con, params=(source, symbol, timeframe))
        con.close()
        ts = pd.to_datetime(df["utc_time"], utc=True, errors="coerce")
        df = df.loc[ts.notna()].copy()
        df["utc_time"] = ts.loc[ts.notna()]
        meta["loaded_rows"] = int(len(df))
        if len(df):
            meta["loaded_start"] = df["utc_time"].min().isoformat()
            meta["loaded_end"] = df["utc_time"].max().isoformat()
        return df, meta
    except Exception as exc:
        meta["error"] = repr(exc)
        return pd.DataFrame(columns=["utc_time"]), meta


def window_hours_for_category(category: str) -> tuple[float, float]:
    c = str(category).lower()
    if "fomc" in c or "rate" in c:
        return 4.0, 8.0
    if "cpi" in c or "inflation" in c or "pce" in c:
        return 2.0, 4.0
    if "employment" in c or "nfp" in c or "jobs" in c:
        return 2.0, 4.0
    return 1.0, 2.0


def build_windows(events_df: pd.DataFrame) -> pd.DataFrame:
    if events_df.empty:
        return pd.DataFrame(columns=["window_start", "window_end", "timestamp", "event", "currency", "impact", "category", "source"])
    ts = pd.to_datetime(events_df["timestamp"], utc=True, errors="coerce")
    rows = []
    for i, row in events_df.loc[ts.notna()].iterrows():
        event_ts = pd.Timestamp(ts.loc[i])
        pre, post = window_hours_for_category(str(row.get("category", "")))
        rows.append({
            "window_start": (event_ts - pd.Timedelta(hours=pre)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "window_end": (event_ts + pd.Timedelta(hours=post)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "timestamp": event_ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "event": row.get("event", ""),
            "currency": row.get("currency", "USD"),
            "impact": row.get("impact", "high"),
            "category": row.get("category", "scheduled_macro"),
            "source": row.get("source", ""),
        })
    return pd.DataFrame(rows)


def compute_overlap(bars: pd.DataFrame, windows: pd.DataFrame, tf_minutes: int = 15) -> dict[str, Any]:
    if bars.empty or windows.empty:
        return {
            "bars_in_blackout": 0,
            "bars_in_blackout_pct": 0.0,
            "events_with_at_least_one_bar": 0,
            "bars_per_event_profile": {"n": int(len(windows))},
        }
    bar_start = pd.to_datetime(bars["utc_time"], utc=True, errors="coerce").dropna().sort_values()
    bar_end = bar_start + pd.Timedelta(minutes=tf_minutes)
    bs = bar_start.astype("int64").to_numpy()
    be = bar_end.astype("int64").to_numpy()
    mask = np.zeros(len(bs), dtype=bool)
    per_event: list[int] = []
    events_with = 0
    wstart = pd.to_datetime(windows["window_start"], utc=True, errors="coerce")
    wend = pd.to_datetime(windows["window_end"], utc=True, errors="coerce")
    for ws, we in zip(wstart, wend):
        if pd.isna(ws) or pd.isna(we) or we <= ws:
            per_event.append(0)
            continue
        ws_i = pd.Timestamp(ws).value
        we_i = pd.Timestamp(we).value
        # bars overlap window if bar_start < window_end and bar_end > window_start
        left = np.searchsorted(bs, we_i, side="left")
        # mark candidate slice up to left; then filter by bar_end > ws
        if left <= 0:
            per_event.append(0)
            continue
        candidate = np.arange(0, left)
        hit_idx = candidate[be[:left] > ws_i]
        if len(hit_idx):
            mask[hit_idx] = True
            events_with += 1
        per_event.append(int(len(hit_idx)))
    total = int(mask.sum())
    return {
        "bars_in_blackout": total,
        "bars_in_blackout_pct": float(total / len(bs)) if len(bs) else 0.0,
        "events_with_at_least_one_bar": events_with,
        "bars_per_event_profile": profile(per_event),
    }


def profile(values: Iterable[Any]) -> dict[str, Any]:
    arr = pd.to_numeric(pd.Series(list(values)), errors="coerce").dropna().astype(float)
    if arr.empty:
        return {"n": 0}
    return {
        "n": int(arr.size),
        "min": float(arr.min()),
        "p10": float(arr.quantile(0.10)),
        "median": float(arr.quantile(0.50)),
        "p90": float(arr.quantile(0.90)),
        "p95": float(arr.quantile(0.95)),
        "p99": float(arr.quantile(0.99)),
        "max": float(arr.max()),
        "mean": float(arr.mean()),
    }


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    dec = summary["decision"]
    acq = summary.get("acquisition", {})
    overlap = summary.get("blackout_overlap", {})
    lines = [
        f"# {STAGE}",
        "",
        "## Decision",
        "",
        "```text",
        f"promotion = {dec['promotion']}",
        f"EA = {dec['EA']}",
        f"paper_live = {dec['paper_live']}",
        f"live = {dec['live']}",
        f"status = {dec['status']}",
        f"recommended_next_stage = {dec['recommended_next_stage']}",
        "```",
        "",
        "This stage acquires or builds a scheduled US macro calendar. It does not create trading signals, shortlist candidates, or promote archived rows.",
        "",
        "## Acquisition summary",
        "",
        f"- BLS events: `{acq.get('bls_event_count', 0)}`",
        f"- FOMC events: `{acq.get('fomc_event_count', 0)}`",
        f"- Manual events: `{acq.get('manual_event_count', 0)}`",
        f"- Final scheduled event count: `{summary.get('scheduled_event_count', 0)}`",
        "",
        "## Blackout overlap",
        "",
        f"- bars_in_blackout: `{overlap.get('bars_in_blackout', 0)}`",
        f"- bars_in_blackout_pct: `{overlap.get('bars_in_blackout_pct', 0.0):.4%}`",
        f"- events_with_at_least_one_bar: `{overlap.get('events_with_at_least_one_bar', 0)}`",
        "",
        "## Blockers and warnings",
        "",
        "```json",
        json.dumps({"blockers": dec.get("blockers", []), "warnings": dec.get("warnings", [])}, indent=2),
        "```",
        "",
        "## Not allowed",
        "",
        "- `candidate_rescue_from_stage41_42_43`",
        "- `post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets`",
        "- `EA_paper_live_live_from_archived_rows`",
        "- `ML_before_robust_cost_aware_baseline`",
        "- `new_blind_megascan_before_scheduled_macro_calendar_is_ready`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--years", nargs="*", type=int, default=[2022, 2023, 2024, 2025, 2026])
    ap.add_argument("--db-path", default="data/local/xauusd_local_store.sqlite")
    ap.add_argument("--table", default="bars")
    ap.add_argument("--source", default="amarkets_mt5")
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--timeframe", default="M15")
    ap.add_argument("--outdir", default="reports/stage45b3b")
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--manual-events-csv", default=None)
    ap.add_argument("--skip-download", action="store_true")
    ap.add_argument("--skip-fomc", action="store_true")
    ap.add_argument("--apply-canonical", action="store_true")
    ap.add_argument("--min-blackout-pct", type=float, default=0.0005)
    ap.add_argument("--max-blackout-pct", type=float, default=0.25)
    ap.add_argument("--print-summary", action="store_true")
    args = ap.parse_args(argv)

    repo = Path(args.repo_root).resolve()
    outdir = repo / args.outdir
    outdir.mkdir(parents=True, exist_ok=True)
    (repo / "data/external").mkdir(parents=True, exist_ok=True)

    all_events: list[dict[str, Any]] = []
    bls_meta: list[dict[str, Any]] = []
    fomc_meta: dict[str, Any] = {"skipped": bool(args.skip_fomc)}
    manual_count = 0

    if args.manual_events_csv:
        manual_events = load_manual_events(repo / args.manual_events_csv)
        manual_count = len(manual_events)
        all_events.extend(manual_events)

    if not args.skip_download:
        for year in args.years:
            ev, meta = parse_bls_year(year, timeout=args.timeout)
            bls_meta.append(meta)
            all_events.extend(ev)
        if not args.skip_fomc:
            ev, fomc_meta = parse_fomc_calendar(args.years, timeout=args.timeout)
            all_events.extend(ev)

    events_df = normalize_events(all_events)
    windows_df = build_windows(events_df)
    bars_df, bar_meta = load_bars(repo, args.db_path, args.table, args.source, args.symbol, args.timeframe)
    overlap = compute_overlap(bars_df, windows_df, tf_minutes=15)

    scheduled_path = repo / "data/external/news_calendar_scheduled_macro_official.csv"
    windows_path = repo / "data/external/news_blackout_windows_scheduled_macro.csv"
    events_df.to_csv(scheduled_path, index=False)
    windows_df.to_csv(windows_path, index=False)

    canonical_outputs: dict[str, str] = {}
    if args.apply_canonical and not events_df.empty:
        canonical_calendar = repo / "data/external/news_calendar.csv"
        backup = repo / "data/external/news_calendar_pre_stage45b3b_mixed.csv"
        if canonical_calendar.exists() and not backup.exists():
            shutil.copy2(canonical_calendar, backup)
            canonical_outputs["backup_calendar"] = str(backup.relative_to(repo))
        keep_cols = ["timestamp", "event", "currency", "impact", "category", "actual", "forecast", "previous", "source"]
        events_df[keep_cols].to_csv(canonical_calendar, index=False)
        windows_df.to_csv(repo / "data/external/news_blackout_windows.csv", index=False)
        canonical_outputs["news_calendar"] = "data/external/news_calendar.csv"
        canonical_outputs["news_blackout_windows"] = "data/external/news_blackout_windows.csv"

    blockers: list[str] = []
    warnings: list[str] = []
    pct = float(overlap.get("bars_in_blackout_pct", 0.0))
    if events_df.empty:
        blockers.append("scheduled_macro_calendar_empty")
    if int(overlap.get("bars_in_blackout", 0)) <= 0:
        blockers.append("scheduled_macro_blackout_windows_do_not_cover_any_bars")
    if pct < args.min_blackout_pct and int(overlap.get("bars_in_blackout", 0)) > 0:
        blockers.append("scheduled_macro_blackout_coverage_too_small")
    if pct > args.max_blackout_pct:
        blockers.append("scheduled_macro_blackout_coverage_too_broad")
    if fomc_meta.get("error"):
        warnings.append("fomc_calendar_fetch_or_parse_warning")
    if any(m.get("error") for m in bls_meta):
        warnings.append("one_or_more_bls_year_pages_failed")

    status = "SCHEDULED_MACRO_CALENDAR_READY_NO_PROMOTION" if not blockers else "SCHEDULED_MACRO_CALENDAR_BLOCKED_NO_PROMOTION"
    next_stage = "Stage45B3A_NEWS_CALENDAR_SEMANTIC_REDUCTION_RERUN" if not blockers else "Stage45B3B_CONTINUE_SCHEDULED_MACRO_CALENDAR_ACQUISITION"

    summary = {
        "stage": STAGE,
        "settings": {
            "repo_root": str(repo),
            "years": args.years,
            "db_path": args.db_path,
            "table": args.table,
            "source": args.source,
            "symbol": args.symbol,
            "timeframe": args.timeframe,
            "apply_canonical": bool(args.apply_canonical),
            "skip_download": bool(args.skip_download),
            "skip_fomc": bool(args.skip_fomc),
            "min_blackout_pct": args.min_blackout_pct,
            "max_blackout_pct": args.max_blackout_pct,
        },
        "acquisition": {
            "bls_meta": bls_meta,
            "fomc_meta": fomc_meta,
            "bls_event_count": int(sum(m.get("events", 0) for m in bls_meta)),
            "fomc_event_count": int(fomc_meta.get("events", 0) or 0),
            "manual_event_count": int(manual_count),
            "fetched_utc": utc_now_iso(),
        },
        "bar_load_meta": bar_meta,
        "scheduled_event_count": int(len(events_df)),
        "scheduled_event_category_counts": events_df["category"].value_counts().head(20).to_dict() if not events_df.empty and "category" in events_df.columns else {},
        "blackout_overlap": overlap,
        "outputs": {
            "summary_json": str((outdir / "stage45b3b_scheduled_macro_calendar_acquisition_summary.json").relative_to(repo)),
            "markdown": str((outdir / "stage45b3b_scheduled_macro_calendar_acquisition.md").relative_to(repo)),
            "scheduled_events_csv": str(scheduled_path.relative_to(repo)),
            "scheduled_blackout_windows_csv": str(windows_path.relative_to(repo)),
        },
        "canonical_outputs": canonical_outputs,
        "decision": {
            "status": status,
            **NO_GO,
            "blockers": blockers,
            "warnings": warnings,
            "recommended_next_stage": next_stage,
            "rationale": [
                "Stage45B3B builds a scheduled macro calendar from official/manual sources.",
                "Numeric shock/backfill context labels remain separate from no-trade blackout windows.",
                "This stage does not create signals, rescue archived candidates, or authorize EA/paper/live.",
            ],
            "not_allowed": [
                "candidate_rescue_from_stage41_42_43",
                "post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets",
                "EA_paper_live_live_from_archived_rows",
                "ML_before_robust_cost_aware_baseline",
                "new_blind_megascan_before_scheduled_macro_calendar_is_ready",
            ],
        },
        **NO_GO,
        "next_allowed_step": next_stage,
    }

    summary_path = outdir / "stage45b3b_scheduled_macro_calendar_acquisition_summary.json"
    md_path = outdir / "stage45b3b_scheduled_macro_calendar_acquisition.md"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(summary, md_path)
    # convenience report CSVs
    events_df.to_csv(outdir / "stage45b3b_scheduled_macro_events.csv", index=False)
    windows_df.to_csv(outdir / "stage45b3b_scheduled_macro_blackout_windows.csv", index=False)
    pd.DataFrame(bls_meta).to_csv(outdir / "stage45b3b_source_fetch_profile.csv", index=False)

    if args.print_summary:
        print(json.dumps({
            "stage": STAGE,
            "status": status,
            "scheduled_event_count": int(len(events_df)),
            "bars_in_blackout": int(overlap.get("bars_in_blackout", 0)),
            "bars_in_blackout_pct": float(overlap.get("bars_in_blackout_pct", 0.0)),
            "blockers": blockers,
            "warnings": warnings,
            "next_allowed_step": next_stage,
            "summary_path": str(summary_path),
            "markdown_path": str(md_path),
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
