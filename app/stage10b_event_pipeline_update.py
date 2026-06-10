#!/usr/bin/env python3
"""
Stage 10B — Event Pipeline Update

Purpose:
- Remove manual-only event entry.
- Collect/normalize/merge:
  1) Scheduled calendar events
  2) Manual/curated events
  3) Shock/news events from GDELT DOC API
- Write unified Stage 10A event CSV.
- Store event staging data in local SQLite.

Inputs:
- data/config/stage9b_scheduled_events_seed.csv
- data/config/stage10a_news_events_manual.csv
- optional GDELT fetch

Outputs:
- data/config/stage10a_news_events.csv
- data/macro/events/stage10b_scheduled_events_normalized.csv
- data/macro/events/stage10b_detected_shock_events.csv
- data/macro/events/stage10b_unified_news_events.csv
- data/reports/stage10b_event_pipeline_update/stage10b_event_pipeline_update.md
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
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


TOOL_VERSION = "v1"
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


def stable_hash(s: str, n: int = 14) -> str:
    return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()[:n]


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

    escalation_words = ["attack", "strike", "missile", "war", "escalat", "invasion", "conflict", "retaliat", "drone"]
    deescalation_words = ["ceasefire", "truce", "peace", "de-escalat", "deal", "talks", "halt attacks"]
    oil_words = ["oil", "brent", "wti", "hormuz", "opec", "supply disruption", "tanker"]
    fed_hawkish_words = ["hawkish", "rate hike", "higher for longer", "inflation hot", "yields rise", "fed warns"]
    fed_dovish_words = ["dovish", "rate cut", "cuts", "inflation cool", "yields fall", "fed easing"]
    usd_strong_words = ["dollar rises", "dollar strengthens", "strong dollar", "dxy rises"]
    usd_weak_words = ["dollar falls", "dollar weakens", "weak dollar", "dxy falls"]
    cb_words = ["central bank", "gold reserves", "gold buying", "purchases gold"]
    etf_words = ["gold etf", "etf inflows", "etf outflows"]
    demand_words = ["jewellery", "physical demand", "gold demand", "china demand", "india demand"]

    def has(words):
        return any(w in text for w in words)

    if has(deescalation_words):
        return "geopolitical_deescalation", "safe_haven", -1, 1.5, "keyword_deescalation"
    if has(escalation_words):
        return "geopolitical_escalation", "safe_haven", 1, 1.5, "keyword_escalation"
    if has(oil_words):
        return "oil_supply_shock", "oil_inflation_pressure", 0, 1.2, "keyword_oil"
    if has(fed_hawkish_words):
        return "fed_speech_hawkish", "real_yield_fed_path", -1, 1.2, "keyword_fed_hawkish"
    if has(fed_dovish_words):
        return "fed_speech_dovish", "real_yield_fed_path", 1, 1.2, "keyword_fed_dovish"
    if has(usd_strong_words):
        return "usd_shock", "usd_pressure", -1, 1.0, "keyword_usd_strong"
    if has(usd_weak_words):
        return "usd_shock", "usd_pressure", 1, 1.0, "keyword_usd_weak"
    if has(cb_words):
        return "central_bank_gold_demand", "central_bank_demand", 1, 1.0, "keyword_central_bank_gold"
    if has(etf_words):
        return "etf_flow", "physical_demand", 0, 0.8, "keyword_etf"
    if has(demand_words):
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


def fetch_json(url: str, timeout: int = 25, ssl_mode: str = "default") -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "xauusd-trader-stage10b/1.0"})
    ctx = build_ssl_context(ssl_mode)
    if ctx is None:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_gdelt(timespan: str, max_records: int, ssl_mode: str) -> Tuple[List[EventRow], List[str]]:
    warnings: List[str] = []
    events: List[EventRow] = []

    queries = [
        '("gold" OR "XAUUSD") ("Federal Reserve" OR Fed OR inflation OR yields OR dollar)',
        '("gold" OR "XAUUSD") (Iran OR Israel OR "Middle East" OR oil OR Hormuz OR ceasefire OR sanctions)',
        '("gold" OR "XAUUSD") ("central bank" OR ETF OR demand OR reserves)',
    ]

    seen_urls = set()

    for q in queries:
        params = {
            "query": q,
            "mode": "ArtList",
            "format": "json",
            "maxrecords": str(max_records),
            "timespan": timespan,
            "sort": "HybridRel",
        }
        url = "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(params)
        try:
            data = fetch_json(url, ssl_mode=ssl_mode)
        except Exception as e:
            warnings.append(f"GDELT fetch failed for query={q}: {type(e).__name__}: {e}")
            continue

        articles = data.get("articles", []) if isinstance(data, dict) else []
        for a in articles:
            title = normalize_title(a.get("title") or "")
            article_url = (a.get("url") or "").strip()
            if not title or not article_url or article_url in seen_urls:
                continue
            seen_urls.add(article_url)

            seen = a.get("seendate") or a.get("seenDate") or ""
            t = parse_time(seen)
            if t is None:
                # GDELT seendate is often YYYYMMDDTHHMMSSZ
                s = str(seen)
                try:
                    t = datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                except Exception:
                    t = datetime.now(timezone.utc).replace(microsecond=0)

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
                manual_tags=f"gdelt;{tag}",
                notes="Auto-detected news candidate; requires later event-impact validation",
                source_kind="gdelt",
                dedupe_key=dedupe_key(title, t.isoformat(), article_url),
            ))

    return events, warnings


def merge_events(scheduled: Sequence[EventRow], manual: Sequence[EventRow], shocks: Sequence[EventRow]) -> List[EventRow]:
    """
    Precedence:
    - scheduled first
    - shocks second
    - manual last, because manual should override dedupe collisions
    """
    merged: Dict[str, EventRow] = {}
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
        run_id, TOOL_VERSION, status, scheduled_count, manual_count, shock_count, unified_count, gen, "\n".join(warnings[:50])
    ))
    conn.commit()


def write_report(report_dir: Path, payload: dict, warnings: Sequence[str], unified: Sequence[EventRow], weights_hint: dict) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "stage10b_event_pipeline_update.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

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
        "## Status",
        f"- status: `{payload['status']}`",
        f"- scheduled_count: `{payload['scheduled_count']}`",
        f"- manual_count: `{payload['manual_count']}`",
        f"- shock_count: `{payload['shock_count']}`",
        f"- unified_count: `{payload['unified_count']}`",
        f"- gdelt_enabled: `{payload['gdelt_enabled']}`",
        f"- timespan: `{payload['gdelt_timespan']}`",
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
        for w in warnings[:30]:
            lines.append(f"- `{w}`")

    lines += [
        "",
        "## Outputs",
        f"- unified Stage 10A CSV: `{payload['out_events_csv']}`",
        f"- detected shock CSV: `{payload['detected_shock_csv']}`",
        f"- scheduled normalized CSV: `{payload['scheduled_normalized_csv']}`",
        f"- unified full CSV: `{payload['unified_full_csv']}`",
        "",
        "## Interpretation",
        "- Scheduled events are known calendar risks.",
        "- GDELT shock events are candidates, not truth.",
        "- Stage 10A must measure actual XAUUSD reaction before any event class is trusted.",
        "- Manual file is reserved for corrections/curation and overrides dedupe collisions.",
        "",
        "## Decision",
        "- No EA change.",
        "- No automatic news trading.",
        "- Next step is running Stage 10A on the unified event file.",
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
) -> int:
    warnings: List[str] = []
    generated = now_iso()

    scheduled = normalize_scheduled(scheduled_path)
    manual = normalize_manual(manual_path)

    shocks: List[EventRow] = []
    if fetch_gdelt_enabled:
        shocks, gdelt_warnings = fetch_gdelt(gdelt_timespan, gdelt_max_records, ssl_mode)
        warnings.extend(gdelt_warnings)
    else:
        warnings.append("GDELT fetch disabled; only scheduled/manual events used.")

    unified = merge_events(scheduled, manual, shocks)

    events_dir.mkdir(parents=True, exist_ok=True)
    write_csv(events_dir / "stage10b_scheduled_events_normalized.csv", [event_to_full_dict(e) for e in scheduled])
    write_csv(events_dir / "stage10b_detected_shock_events.csv", [event_to_full_dict(e) for e in shocks])
    write_csv(events_dir / "stage10b_unified_news_events.csv", [event_to_full_dict(e) for e in unified])
    write_csv(out_events_path, [event_to_stage10a_dict(e) for e in unified], STAGE10A_HEADER)

    status = "ok"
    if fetch_gdelt_enabled and warnings and not shocks:
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
        "warnings": warnings,
    }

    write_report(report_dir, payload, warnings, unified, {})
    print("Stage 10B event pipeline update: DONE")
    print(f"status={status} scheduled={len(scheduled)} manual={len(manual)} shocks={len(shocks)} unified={len(unified)}")
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
    p.add_argument("--gdelt-timespan", default="48h")
    p.add_argument("--gdelt-max-records", type=int, default=40)
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
    )


if __name__ == "__main__":
    raise SystemExit(main())
