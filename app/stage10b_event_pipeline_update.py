#!/usr/bin/env python3
"""
Stage 10B — Event Pipeline Update v2

Purpose:
- Build the unified Stage 10A event file from:
  1) scheduled calendar events
  2) manual/curated override events
  3) GDELT shock/news candidates
- Make GDELT access rate-limit aware after probe results:
  - fewer default queries
  - delay between queries
  - retry/backoff for HTTP 429
  - per-query status CSV
- Write workflow run metadata into the report artifact.

Outputs:
- data/config/stage10a_news_events.csv
- data/macro/events/stage10b_scheduled_events_normalized.csv
- data/macro/events/stage10b_detected_shock_events.csv
- data/macro/events/stage10b_unified_news_events.csv
- data/reports/stage10b_event_pipeline_update/stage10b_event_pipeline_update.md
- data/reports/stage10b_event_pipeline_update/stage10b_gdelt_query_status.csv
- data/reports/stage10b_event_pipeline_update/workflow_run_metadata.json
- data/reports/stage10b_event_pipeline_update/workflow_run_metadata.md
- SQLite:
  event_pipeline_staging
  event_pipeline_runs

Hard rules:
- Data/event collection only.
- No trading signal.
- No EA change.
- No demo/paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sqlite3
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


TOOL_VERSION = "v2_rate_limit_metadata"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_SCHEDULED = Path("data/config/stage9b_scheduled_events_seed.csv")
DEFAULT_MANUAL = Path("data/config/stage10a_news_events_manual.csv")
DEFAULT_OUT_EVENTS = Path("data/config/stage10a_news_events.csv")
DEFAULT_EVENTS_DIR = Path("data/macro/events")
DEFAULT_REPORT_DIR = Path("data/reports/stage10b_event_pipeline_update")

STAGE10A_HEADER = [
    "event_id", "event_time_utc", "event_end_utc", "title", "event_class", "event_channel",
    "expected_gold_direction", "initial_importance", "confidence", "source_name",
    "source_url_or_note", "manual_tags", "notes"
]


@dataclass
class EventRow:
    event_id: str
    event_time_utc: str
    event_end_utc: str
    title: str
    event_class: str
    event_channel: str
    expected_gold_direction: int
    initial_importance: float
    confidence: float
    source_name: str
    source_url_or_note: str
    manual_tags: str
    notes: str
    source_kind: str
    dedupe_key: str


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def workflow_metadata() -> Dict[str, str]:
    keys = [
        "GITHUB_WORKFLOW",
        "GITHUB_RUN_ID",
        "GITHUB_RUN_NUMBER",
        "GITHUB_RUN_ATTEMPT",
        "GITHUB_JOB",
        "GITHUB_REF",
        "GITHUB_SHA",
        "GITHUB_REPOSITORY",
        "GITHUB_ACTOR",
        "GITHUB_EVENT_NAME",
        "RUNNER_OS",
    ]
    out = {k: os.environ.get(k, "") for k in keys}
    out["generated_utc"] = now_iso()
    out["tool_version"] = TOOL_VERSION
    return out


def parse_time(v: str) -> Optional[datetime]:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return None


def stable_hash(s: str, n: int = 14) -> str:
    return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()[:n]


def safe_float(v, default=0.0) -> float:
    try:
        if v is None or str(v).strip() == "":
            return default
        return float(str(v).strip())
    except Exception:
        return default


def safe_int(v, default=0) -> int:
    try:
        if v is None or str(v).strip() == "":
            return default
        return int(float(str(v).strip()))
    except Exception:
        return default


def dedupe_key(title: str, t: str, url: str = "") -> str:
    base = (url or title or "").strip().lower()
    day = (t or "")[:10]
    return stable_hash(day + "|" + base)


def normalize_title(s: str) -> str:
    return " ".join((s or "").replace("\n", " ").split()).strip()


def read_csv(path: Path) -> List[dict]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        return []
    return list(csv.DictReader(text.splitlines()))


def write_csv(path: Path, rows: Sequence[dict], header: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if header is None:
        header = list(rows[0].keys()) if rows else ["empty"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def event_to_stage10a_dict(e: EventRow) -> dict:
    d = asdict(e)
    return {k: d[k] for k in STAGE10A_HEADER}


def event_to_full_dict(e: EventRow) -> dict:
    return asdict(e)


def classify_scheduled(label: str, category: str) -> Tuple[str, str, int]:
    text = f"{label} {category}".lower()
    if "fomc" in text or "federal reserve" in text or "fed" in text:
        return "fomc_statement", "real_yield_fed_path", 0
    if "cpi" in text or "inflation" in text:
        return "cpi_surprise", "real_yield_fed_path", 0
    if "ppi" in text:
        return "ppi_surprise", "real_yield_fed_path", 0
    if "nfp" in text or "payroll" in text or "jobs" in text:
        return "nfp_surprise", "real_yield_fed_path", 0
    return "scheduled_macro_event", "mixed_macro", 0


def impact_to_importance(impact: str) -> float:
    s = (impact or "").lower()
    if s == "high":
        return 2.0
    if s == "medium":
        return 1.0
    if s == "low":
        return 0.5
    return 1.0


def normalize_scheduled(path: Path) -> List[EventRow]:
    rows = read_csv(path)
    out: List[EventRow] = []
    for r in rows:
        label = normalize_title(r.get("label") or r.get("title") or "")
        if not label or label.upper().startswith("EXAMPLE"):
            continue
        t = parse_time(r.get("event_time_utc") or "")
        if t is None:
            continue
        end = parse_time(r.get("event_end_utc") or "") or t
        event_class, channel, expected = classify_scheduled(label, r.get("category", ""))
        event_id = (r.get("event_id") or f"scheduled_{stable_hash(label + t.isoformat())}").strip()
        urlnote = (r.get("source_note") or r.get("source_url_or_note") or "").strip()
        out.append(EventRow(
            event_id=event_id,
            event_time_utc=t.isoformat(),
            event_end_utc=end.isoformat(),
            title=label,
            event_class=event_class,
            event_channel=channel,
            expected_gold_direction=expected,
            initial_importance=impact_to_importance(r.get("impact", "")),
            confidence=1.0,
            source_name="scheduled_seed",
            source_url_or_note=urlnote,
            manual_tags="scheduled;calendar",
            notes="Normalized from scheduled event seed",
            source_kind="scheduled",
            dedupe_key=dedupe_key(label, t.isoformat(), event_id),
        ))
    return out


def normalize_manual(path: Path) -> List[EventRow]:
    rows = read_csv(path)
    out: List[EventRow] = []
    for r in rows:
        title = normalize_title(r.get("title") or "")
        if not title or title.upper().startswith("EXAMPLE"):
            continue
        t = parse_time(r.get("event_time_utc") or "")
        if t is None:
            continue
        end = parse_time(r.get("event_end_utc") or "") or t
        event_id = (r.get("event_id") or f"manual_{stable_hash(title + t.isoformat())}").strip()
        url = (r.get("source_url_or_note") or "").strip()
        out.append(EventRow(
            event_id=event_id,
            event_time_utc=t.isoformat(),
            event_end_utc=end.isoformat(),
            title=title,
            event_class=(r.get("event_class") or "manual_event").strip(),
            event_channel=(r.get("event_channel") or "mixed_macro").strip(),
            expected_gold_direction=safe_int(r.get("expected_gold_direction"), 0),
            initial_importance=safe_float(r.get("initial_importance"), 1.0),
            confidence=max(0.0, min(1.0, safe_float(r.get("confidence"), 0.7))),
            source_name=(r.get("source_name") or "manual").strip(),
            source_url_or_note=url,
            manual_tags=(r.get("manual_tags") or "manual").strip(),
            notes=(r.get("notes") or "").strip(),
            source_kind="manual",
            dedupe_key=dedupe_key(title, t.isoformat(), url),
        ))
    return out


def classify_news(title: str) -> Tuple[str, str, int, float, str]:
    text = title.lower()

    if any(w in text for w in ["ceasefire", "truce", "peace", "de-escalat", "deal", "talks"]):
        return "geopolitical_deescalation", "safe_haven", -1, 1.5, "keyword_deescalation"
    if any(w in text for w in ["attack", "strike", "missile", "war", "escalat", "conflict", "retaliat", "drone"]):
        return "geopolitical_escalation", "safe_haven", 1, 1.5, "keyword_escalation"
    if any(w in text for w in ["oil", "brent", "wti", "hormuz", "opec", "supply disruption", "tanker"]):
        return "oil_supply_shock", "oil_inflation_pressure", 0, 1.2, "keyword_oil"
    if any(w in text for w in ["hawkish", "rate hike", "higher for longer", "inflation hot", "yields rise", "fed warns"]):
        return "fed_speech_hawkish", "real_yield_fed_path", -1, 1.2, "keyword_fed_hawkish"
    if any(w in text for w in ["dovish", "rate cut", "cuts", "inflation cool", "yields fall", "fed easing"]):
        return "fed_speech_dovish", "real_yield_fed_path", 1, 1.2, "keyword_fed_dovish"
    if any(w in text for w in ["dollar rises", "dollar strengthens", "strong dollar", "dxy rises"]):
        return "usd_shock", "usd_pressure", -1, 1.0, "keyword_usd_strong"
    if any(w in text for w in ["dollar falls", "dollar weakens", "weak dollar", "dxy falls"]):
        return "usd_shock", "usd_pressure", 1, 1.0, "keyword_usd_weak"
    if any(w in text for w in ["central bank", "gold reserves", "gold buying", "purchases gold", "net gold purchases"]):
        return "central_bank_gold_demand", "central_bank_demand", 1, 1.0, "keyword_central_bank_gold"
    if any(w in text for w in ["gold etf", "etf inflows", "etf outflows"]):
        return "etf_flow", "physical_demand", 0, 0.8, "keyword_etf"
    if any(w in text for w in ["jewellery", "physical demand", "gold demand", "china demand", "india demand"]):
        return "physical_demand", "physical_demand", 0, 0.8, "keyword_physical_demand"

    return "market_news", "mixed_macro", 0, 0.5, "keyword_general"


def build_ssl_context(ssl_mode: str):
    mode = (ssl_mode or "default").lower()
    if mode == "insecure":
        return ssl._create_unverified_context()
    if mode == "certifi":
        try:
            import certifi  # type: ignore
            return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            return None
    return None


def fetch_json(url: str, timeout: int, ssl_mode: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "xauusd-trader-stage10b/2.0"})
    ctx = build_ssl_context(ssl_mode)
    if ctx is None:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))


def gdelt_queries(query_mode: str) -> List[str]:
    if query_mode == "smoke":
        return ["XAUUSD"]

    # Default is based on the probe: these worked in GitHub.
    rate_safe = [
        "XAUUSD",
        "gold federal reserve",
        "gold central bank",
    ]
    if query_mode == "rate_safe":
        return rate_safe

    # Extended mode is for manual testing only; more likely to trigger 429.
    extended = rate_safe + [
        "gold dollar",
        "gold yields",
        "gold Iran Israel",
        "gold oil",
    ]
    return extended


def gdelt_fetch_once(query: str, timespan: str, max_records: int, timeout: int, ssl_mode: str) -> Tuple[dict, str]:
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": str(max_records),
        "timespan": timespan,
        "sort": "HybridRel",
    }
    url = "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(params)
    data = fetch_json(url, timeout=timeout, ssl_mode=ssl_mode)
    return data, url


def parse_gdelt_time(value: str) -> datetime:
    t = parse_time(value)
    if t is not None:
        return t
    try:
        return datetime.strptime(str(value), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc).replace(microsecond=0)


def fetch_gdelt(timespan: str, max_records: int, ssl_mode: str, timeout: int, retries: int, query_mode: str, query_delay: float) -> Tuple[List[EventRow], List[str], List[dict]]:
    warnings: List[str] = []
    query_status: List[dict] = []
    events: List[EventRow] = []
    seen_urls = set()

    queries = gdelt_queries(query_mode)

    for qi, q in enumerate(queries):
        if qi > 0 and query_delay > 0:
            time.sleep(query_delay)

        data = None
        url = ""
        last_error = ""
        http_status = ""
        rate_limited = False

        for attempt in range(1, retries + 2):
            try:
                data, url = gdelt_fetch_once(q, timespan, max_records, timeout, ssl_mode)
                last_error = ""
                http_status = "ok"
                break
            except urllib.error.HTTPError as e:
                http_status = str(e.code)
                last_error = f"HTTPError: HTTP Error {e.code}: {e.reason}"
                if e.code == 429:
                    rate_limited = True
                    # Longer backoff for 429.
                    if attempt <= retries:
                        time.sleep(15 * attempt)
                        continue
                if attempt <= retries:
                    time.sleep(min(8, 2 * attempt))
            except Exception as e:
                http_status = "error"
                last_error = f"{type(e).__name__}: {e}"
                if attempt <= retries:
                    time.sleep(min(8, 2 * attempt))

        if data is None:
            warnings.append(f"GDELT fetch failed query={q}: {last_error}")
            query_status.append({
                "query": q,
                "status": "rate_limited" if rate_limited else "error",
                "http_status": http_status,
                "articles": 0,
                "error": last_error,
                "url": url,
            })
            continue

        articles = data.get("articles", []) if isinstance(data, dict) else []
        query_status.append({
            "query": q,
            "status": "ok",
            "http_status": http_status,
            "articles": len(articles),
            "error": "",
            "url": url,
        })

        for a in articles:
            title = normalize_title(a.get("title") or "")
            article_url = (a.get("url") or "").strip()
            if not title or not article_url or article_url in seen_urls:
                continue
            seen_urls.add(article_url)

            t = parse_gdelt_time(a.get("seendate") or a.get("seenDate") or "")
            event_class, channel, expected, importance, tag = classify_news(title)
            eid = f"gdelt_{stable_hash(article_url)}"
            domain = (a.get("domain") or "").strip()
            source_name = f"gdelt:{domain}" if domain else "gdelt"

            events.append(EventRow(
                event_id=eid,
                event_time_utc=t.isoformat(),
                event_end_utc=t.isoformat(),
                title=title,
                event_class=event_class,
                event_channel=channel,
                expected_gold_direction=expected,
                initial_importance=importance,
                confidence=0.45,
                source_name=source_name,
                source_url_or_note=article_url,
                manual_tags=f"gdelt;{tag};query_mode={query_mode}",
                notes="Auto-detected news candidate; requires Stage 10A/10D validation before trust",
                source_kind="gdelt",
                dedupe_key=dedupe_key(title, t.isoformat(), article_url),
            ))

    return events, warnings, query_status


def merge_events(scheduled: Sequence[EventRow], manual: Sequence[EventRow], shocks: Sequence[EventRow]) -> List[EventRow]:
    merged: Dict[str, EventRow] = {}
    # Manual last to override dedupe collision.
    for e in list(scheduled) + list(shocks) + list(manual):
        merged[e.dedupe_key] = e
    return sorted(merged.values(), key=lambda e: (e.event_time_utc, e.source_kind, e.event_id))


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS event_pipeline_staging (
            event_id TEXT PRIMARY KEY,
            event_time_utc TEXT,
            event_end_utc TEXT,
            title TEXT,
            event_class TEXT,
            event_channel TEXT,
            expected_gold_direction INTEGER,
            initial_importance REAL,
            confidence REAL,
            source_name TEXT,
            source_url_or_note TEXT,
            manual_tags TEXT,
            notes TEXT,
            source_kind TEXT,
            dedupe_key TEXT,
            imported_utc TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS event_pipeline_runs (
            run_id TEXT PRIMARY KEY,
            tool_version TEXT,
            status TEXT,
            scheduled_count INTEGER,
            manual_count INTEGER,
            shock_count INTEGER,
            unified_count INTEGER,
            generated_utc TEXT,
            warnings TEXT
        )
    """)
    conn.commit()


def upsert_staging(conn: sqlite3.Connection, events: Sequence[EventRow]) -> None:
    gen = now_iso()
    for e in events:
        conn.execute("""
            INSERT OR REPLACE INTO event_pipeline_staging (
                event_id, event_time_utc, event_end_utc, title, event_class, event_channel,
                expected_gold_direction, initial_importance, confidence, source_name,
                source_url_or_note, manual_tags, notes, source_kind, dedupe_key, imported_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            e.event_id, e.event_time_utc, e.event_end_utc, e.title, e.event_class, e.event_channel,
            e.expected_gold_direction, e.initial_importance, e.confidence, e.source_name,
            e.source_url_or_note, e.manual_tags, e.notes, e.source_kind, e.dedupe_key, gen
        ))
    conn.commit()


def insert_run(conn: sqlite3.Connection, status: str, scheduled_count: int, manual_count: int, shock_count: int, unified_count: int, warnings: Sequence[str]) -> None:
    gen = now_iso()
    run_id = f"stage10b_event_pipeline_{gen}"
    conn.execute("""
        INSERT OR REPLACE INTO event_pipeline_runs (
            run_id, tool_version, status, scheduled_count, manual_count, shock_count,
            unified_count, generated_utc, warnings
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_id, TOOL_VERSION, status, scheduled_count, manual_count, shock_count, unified_count, gen, "\n".join(warnings[:80])
    ))
    conn.commit()


def write_workflow_metadata(report_dir: Path, meta: Dict[str, str]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "workflow_run_metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# Workflow Run Metadata",
        "",
        f"- generated_utc: `{meta.get('generated_utc','')}`",
        f"- tool_version: `{meta.get('tool_version','')}`",
        f"- GITHUB_WORKFLOW: `{meta.get('GITHUB_WORKFLOW','')}`",
        f"- GITHUB_RUN_ID: `{meta.get('GITHUB_RUN_ID','')}`",
        f"- GITHUB_RUN_NUMBER: `{meta.get('GITHUB_RUN_NUMBER','')}`",
        f"- GITHUB_RUN_ATTEMPT: `{meta.get('GITHUB_RUN_ATTEMPT','')}`",
        f"- GITHUB_JOB: `{meta.get('GITHUB_JOB','')}`",
        f"- GITHUB_REF: `{meta.get('GITHUB_REF','')}`",
        f"- GITHUB_SHA: `{meta.get('GITHUB_SHA','')}`",
        f"- GITHUB_REPOSITORY: `{meta.get('GITHUB_REPOSITORY','')}`",
        f"- GITHUB_ACTOR: `{meta.get('GITHUB_ACTOR','')}`",
        f"- GITHUB_EVENT_NAME: `{meta.get('GITHUB_EVENT_NAME','')}`",
        f"- RUNNER_OS: `{meta.get('RUNNER_OS','')}`",
    ]
    (report_dir / "workflow_run_metadata.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_report(report_dir: Path, payload: dict, warnings: Sequence[str], unified: Sequence[EventRow], query_status: Sequence[dict], meta: Dict[str, str]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "stage10b_event_pipeline_update.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    write_csv(report_dir / "stage10b_gdelt_query_status.csv", list(query_status), ["query", "status", "http_status", "articles", "error", "url"])
    write_workflow_metadata(report_dir, meta)

    counts_by_kind: Dict[str, int] = {}
    counts_by_class: Dict[str, int] = {}
    for e in unified:
        counts_by_kind[e.source_kind] = counts_by_kind.get(e.source_kind, 0) + 1
        counts_by_class[e.event_class] = counts_by_class.get(e.event_class, 0) + 1

    lines = [
        "# Stage 10B Event Pipeline Update",
        "",
        f"Generated UTC: `{payload['generated_utc']}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: data/event collection only. This does not authorize demo, paper, or live orders.",
        "",
        "## Workflow metadata",
        f"- workflow: `{meta.get('GITHUB_WORKFLOW','')}`",
        f"- run_id: `{meta.get('GITHUB_RUN_ID','')}`",
        f"- run_number: `{meta.get('GITHUB_RUN_NUMBER','')}`",
        f"- run_attempt: `{meta.get('GITHUB_RUN_ATTEMPT','')}`",
        f"- sha: `{meta.get('GITHUB_SHA','')}`",
        "",
        "## Status",
        f"- status: `{payload['status']}`",
        f"- scheduled_count: `{payload['scheduled_count']}`",
        f"- manual_count: `{payload['manual_count']}`",
        f"- shock_count: `{payload['shock_count']}`",
        f"- unified_count: `{payload['unified_count']}`",
        f"- gdelt_enabled: `{payload['gdelt_enabled']}`",
        f"- gdelt_query_mode: `{payload['gdelt_query_mode']}`",
        f"- timespan: `{payload['gdelt_timespan']}`",
        f"- query_delay_sec: `{payload['gdelt_query_delay']}`",
        "",
        "## GDELT query status",
        "| Query | Status | HTTP | Articles | Error |",
        "|---|---|---|---:|---|",
    ]

    if query_status:
        for q in query_status:
            err = str(q.get("error", "")).replace("|", "/")[:160]
            lines.append(f"| {q.get('query','')} | {q.get('status','')} | {q.get('http_status','')} | {q.get('articles',0)} | {err} |")
    else:
        lines.append("| none | none | none | 0 | not run |")

    lines += [
        "",
        "## Counts by source kind",
        "| Source kind | Events |",
        "|---|---:|",
    ]
    for k, v in sorted(counts_by_kind.items()):
        lines.append(f"| {k} | {v} |")
    if not counts_by_kind:
        lines.append("| none | 0 |")

    lines += [
        "",
        "## Counts by event class",
        "| Event class | Events |",
        "|---|---:|",
    ]
    for k, v in sorted(counts_by_class.items(), key=lambda kv: (-kv[1], kv[0]))[:40]:
        lines.append(f"| {k} | {v} |")
    if not counts_by_class:
        lines.append("| none | 0 |")

    lines += [
        "",
        "## Recent / detected events preview",
        "| Time UTC | Source | Class | Channel | Expected | Title |",
        "|---|---|---|---|---:|---|",
    ]
    for e in list(unified)[-30:]:
        title = e.title.replace("|", "/")[:140]
        lines.append(f"| {e.event_time_utc} | {e.source_kind} | {e.event_class} | {e.event_channel} | {e.expected_gold_direction} | {title} |")
    if not unified:
        lines.append("| none | none | none | none | 0 | none |")

    if warnings:
        lines += ["", "## Warnings"]
        for w in warnings[:40]:
            lines.append(f"- `{w}`")

    lines += [
        "",
        "## Outputs",
        f"- unified Stage 10A CSV: `{payload['out_events_csv']}`",
        f"- detected shock CSV: `{payload['detected_shock_csv']}`",
        f"- scheduled normalized CSV: `{payload['scheduled_normalized_csv']}`",
        f"- unified full CSV: `{payload['unified_full_csv']}`",
        f"- GDELT query status CSV: `{report_dir / 'stage10b_gdelt_query_status.csv'}`",
        f"- workflow metadata JSON: `{report_dir / 'workflow_run_metadata.json'}`",
        f"- workflow metadata MD: `{report_dir / 'workflow_run_metadata.md'}`",
        "",
        "## Decision",
        "- No EA change.",
        "- No automatic news trading.",
        "- Run Stage 10A/10D after copying the artifact into local repo.",
    ]

    (report_dir / "stage10b_event_pipeline_update.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(
    db_path: Path,
    scheduled_path: Path,
    manual_path: Path,
    out_events_path: Path,
    events_dir: Path,
    report_dir: Path,
    fetch_gdelt_enabled: bool,
    gdelt_timespan: str,
    gdelt_max_records: int,
    ssl_mode: str,
    gdelt_timeout: int,
    gdelt_retries: int,
    gdelt_query_mode: str,
    gdelt_query_delay: float,
) -> int:
    warnings: List[str] = []
    query_status: List[dict] = []
    generated = now_iso()
    meta = workflow_metadata()

    scheduled = normalize_scheduled(scheduled_path)
    manual = normalize_manual(manual_path)

    shocks: List[EventRow] = []
    if fetch_gdelt_enabled:
        shocks, gdelt_warnings, query_status = fetch_gdelt(
            gdelt_timespan,
            gdelt_max_records,
            ssl_mode,
            gdelt_timeout,
            gdelt_retries,
            gdelt_query_mode,
            gdelt_query_delay,
        )
        warnings.extend(gdelt_warnings)
    else:
        warnings.append("GDELT fetch disabled; only scheduled/manual events used.")

    unified = merge_events(scheduled, manual, shocks)

    events_dir.mkdir(parents=True, exist_ok=True)
    write_csv(events_dir / "stage10b_scheduled_events_normalized.csv", [event_to_full_dict(e) for e in scheduled])
    write_csv(events_dir / "stage10b_detected_shock_events.csv", [event_to_full_dict(e) for e in shocks])
    write_csv(events_dir / "stage10b_unified_news_events.csv", [event_to_full_dict(e) for e in unified])
    write_csv(out_events_path, [event_to_stage10a_dict(e) for e in unified], STAGE10A_HEADER)

    if not fetch_gdelt_enabled:
        status = "ok_no_gdelt"
    elif shocks:
        status = "ok"
    else:
        status = "partial_no_gdelt_shocks"

    db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        conn = sqlite3.connect(db_path)
        ensure_tables(conn)
        upsert_staging(conn, unified)
        insert_run(conn, status, len(scheduled), len(manual), len(shocks), len(unified), warnings)
        conn.close()
    except Exception as e:
        status = "db_error"
        warnings.append(f"DB write failed: {type(e).__name__}: {e}")

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "status": status,
        "db_path": str(db_path),
        "scheduled_path": str(scheduled_path),
        "manual_path": str(manual_path),
        "out_events_csv": str(out_events_path),
        "detected_shock_csv": str(events_dir / "stage10b_detected_shock_events.csv"),
        "scheduled_normalized_csv": str(events_dir / "stage10b_scheduled_events_normalized.csv"),
        "unified_full_csv": str(events_dir / "stage10b_unified_news_events.csv"),
        "scheduled_count": len(scheduled),
        "manual_count": len(manual),
        "shock_count": len(shocks),
        "unified_count": len(unified),
        "gdelt_enabled": fetch_gdelt_enabled,
        "gdelt_timespan": gdelt_timespan,
        "gdelt_max_records": gdelt_max_records,
        "gdelt_timeout": gdelt_timeout,
        "gdelt_retries": gdelt_retries,
        "gdelt_query_mode": gdelt_query_mode,
        "gdelt_query_delay": gdelt_query_delay,
        "gdelt_query_status": query_status,
        "workflow_metadata": meta,
        "warnings": warnings,
    }

    write_report(report_dir, payload, warnings, unified, query_status, meta)
    print("Stage 10B event pipeline update: DONE")
    print(f"status={status} scheduled={len(scheduled)} manual={len(manual)} shocks={len(shocks)} unified={len(unified)}")
    print(f"workflow_run_number={meta.get('GITHUB_RUN_NUMBER','')}")
    print(f"Report: {report_dir / 'stage10b_event_pipeline_update.md'}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--scheduled", default=str(DEFAULT_SCHEDULED))
    p.add_argument("--manual", default=str(DEFAULT_MANUAL))
    p.add_argument("--out-events", default=str(DEFAULT_OUT_EVENTS))
    p.add_argument("--events-dir", default=str(DEFAULT_EVENTS_DIR))
    p.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    p.add_argument("--no-gdelt", action="store_true")
    p.add_argument("--gdelt-timespan", default="7d")
    p.add_argument("--gdelt-max-records", type=int, default=10)
    p.add_argument("--gdelt-query-mode", default="rate_safe", choices=["rate_safe", "extended", "smoke"])
    p.add_argument("--gdelt-timeout", type=int, default=60)
    p.add_argument("--gdelt-retries", type=int, default=2)
    p.add_argument("--gdelt-query-delay", type=float, default=20.0)
    p.add_argument("--ssl-mode", default=os.environ.get("EVENT_PIPELINE_SSL_MODE", "default"), choices=["default", "certifi", "insecure"])
    args = p.parse_args()

    return run(
        Path(args.db),
        Path(args.scheduled),
        Path(args.manual),
        Path(args.out_events),
        Path(args.events_dir),
        Path(args.report_dir),
        not args.no_gdelt,
        args.gdelt_timespan,
        args.gdelt_max_records,
        args.ssl_mode,
        args.gdelt_timeout,
        args.gdelt_retries,
        args.gdelt_query_mode,
        args.gdelt_query_delay,
    )


if __name__ == "__main__":
    raise SystemExit(main())
