#!/usr/bin/env python3
"""
Stage 10C — Numeric Shock Event Backfill

Purpose:
- Create historical testable event rows from imported FRED numeric macro data.
- Avoid waiting for rare v2 signals or future calendar events.
- Generate Stage 10A-compatible events from realized shocks:
  real-yield shock, USD shock, oil shock, nominal-rate shock.
- Merge generated events with existing Stage 10A event file.

Inputs:
- data/local/xauusd_local_store.sqlite
  table macro_numeric_observations
- existing data/config/stage10a_news_events.csv if present

Outputs:
- data/macro/events/stage10c_numeric_shock_events.csv
- data/config/stage10a_news_events.csv
- data/reports/stage10c_numeric_shock_event_backfill/stage10c_numeric_shock_event_backfill.md
- SQLite:
  numeric_shock_events
  numeric_shock_event_runs

Hard rules:
- Historical event backfill only.
- No trading signal.
- No EA change.
- No demo/paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import date, datetime, time, timezone, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


TOOL_VERSION = "v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_OUT_EVENTS = Path("data/config/stage10a_news_events.csv")
DEFAULT_EVENTS_DIR = Path("data/macro/events")
DEFAULT_REPORT_DIR = Path("data/reports/stage10c_numeric_shock_event_backfill")

HEADER = [
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


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_hash(s: str, n: int = 12) -> str:
    return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()[:n]


def parse_date(s: str) -> Optional[date]:
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def event_time_for_day(d: date, series_id: str) -> datetime:
    """
    FRED daily observations are date-based, not intraday release timestamps.
    For market series shocks (rates/USD/oil), use 13:30 UTC as a neutral event
    anchor inside US macro/liquidity hours. This is only a historical proxy.
    """
    if series_id in {"DFII10", "DGS10", "DGS2", "DTWEXBGS", "DCOILWTICO", "DCOILBRENTEU"}:
        return datetime.combine(d, time(13, 30), tzinfo=timezone.utc)
    return datetime.combine(d, time(13, 30), tzinfo=timezone.utc)


def read_existing_events(path: Path) -> List[dict]:
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


def connect_db(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(f"DB not found: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def load_series(conn: sqlite3.Connection) -> Dict[str, List[Tuple[date, float]]]:
    rows = conn.execute("""
        SELECT series_id, obs_date, value
        FROM macro_numeric_observations
        WHERE value IS NOT NULL
          AND series_id IN ('DFII10', 'DGS10', 'DGS2', 'DTWEXBGS', 'DCOILWTICO', 'DCOILBRENTEU')
        ORDER BY series_id ASC, obs_date ASC
    """).fetchall()
    out: Dict[str, List[Tuple[date, float]]] = {}
    for r in rows:
        d = parse_date(r["obs_date"])
        if d is None:
            continue
        out.setdefault(r["series_id"], []).append((d, float(r["value"])))
    return out


def pct_change(now: float, prev: float) -> Optional[float]:
    if prev == 0:
        return None
    return 100.0 * (now - prev) / abs(prev)


def diff(now: float, prev: float) -> float:
    return now - prev


def classify_shock(series_id: str, value: float, d1: Optional[float], d5: Optional[float]) -> Optional[Tuple[str, str, int, float, str]]:
    """
    Returns (event_class, event_channel, expected_gold_direction, initial_importance, reason)
    expected direction is intentionally conservative.
    """
    if d1 is None and d5 is None:
        return None

    if series_id == "DFII10":
        # real yield in percentage points
        x1 = d1 or 0.0
        x5 = d5 or 0.0
        strength = max(abs(x1), abs(x5))
        if strength >= 0.25:
            imp = 2.0
        elif strength >= 0.12:
            imp = 1.2
        else:
            return None
        expected = -1 if (x1 > 0 or x5 > 0) else 1
        reason = f"DFII10 real-yield shock d1={round(x1,4)} d5={round(x5,4)} value={value}"
        return "real_yield_shock", "real_yield_fed_path", expected, imp, reason

    if series_id in {"DGS10", "DGS2"}:
        x1 = d1 or 0.0
        x5 = d5 or 0.0
        strength = max(abs(x1), abs(x5))
        if strength >= 0.30:
            imp = 1.5
        elif strength >= 0.18:
            imp = 1.0
        else:
            return None
        expected = -1 if (x1 > 0 or x5 > 0) else 1
        cls = "nominal_yield_shock" if series_id == "DGS10" else "front_end_yield_shock"
        reason = f"{series_id} nominal yield shock d1={round(x1,4)} d5={round(x5,4)} value={value}"
        return cls, "real_yield_fed_path", expected, imp, reason

    if series_id == "DTWEXBGS":
        x1 = d1 or 0.0
        x5 = d5 or 0.0
        strength = max(abs(x1), abs(x5))
        if strength >= 1.5:
            imp = 1.5
        elif strength >= 0.8:
            imp = 1.0
        else:
            return None
        expected = -1 if (x1 > 0 or x5 > 0) else 1
        reason = f"Broad USD shock pct d1={round(x1,4)} d5={round(x5,4)} value={value}"
        return "usd_shock", "usd_pressure", expected, imp, reason

    if series_id in {"DCOILWTICO", "DCOILBRENTEU"}:
        x1 = d1 or 0.0
        x5 = d5 or 0.0
        strength = max(abs(x1), abs(x5))
        if strength >= 10.0:
            imp = 1.8
        elif strength >= 5.0:
            imp = 1.2
        else:
            return None
        # Oil is directionally mixed for gold: safe-haven/inflation/Fed channels can conflict.
        expected = 0
        reason = f"{series_id} oil shock pct d1={round(x1,4)} d5={round(x5,4)} value={value}"
        return "oil_supply_shock", "oil_inflation_pressure", expected, imp, reason

    return None


def generate_shock_events(series: Dict[str, List[Tuple[date, float]]], max_events: int = 500) -> List[EventRow]:
    events: List[EventRow] = []

    for sid, vals in series.items():
        vals = sorted(vals, key=lambda x: x[0])
        by_date = {d: v for d, v in vals}
        dates = [d for d, _ in vals]

        for i, (d, value) in enumerate(vals):
            if i < 5:
                continue
            prev1 = vals[i - 1][1] if i >= 1 else None
            # Find approximately 5 observations back, not calendar days.
            prev5 = vals[i - 5][1] if i >= 5 else None

            if sid in {"DFII10", "DGS10", "DGS2"}:
                d1 = diff(value, prev1) if prev1 is not None else None
                d5 = diff(value, prev5) if prev5 is not None else None
            else:
                d1 = pct_change(value, prev1) if prev1 is not None else None
                d5 = pct_change(value, prev5) if prev5 is not None else None

            cls = classify_shock(sid, value, d1, d5)
            if cls is None:
                continue
            event_class, channel, expected, importance, reason = cls
            t = event_time_for_day(d, sid)
            direction_txt = "supportive" if expected == 1 else "hostile" if expected == -1 else "mixed"
            title = f"{sid} {event_class} {direction_txt} on {d.isoformat()}"
            eid = f"numeric_{sid.lower()}_{d.strftime('%Y%m%d')}_{stable_hash(reason, 8)}"
            events.append(EventRow(
                event_id=eid,
                event_time_utc=t.isoformat(),
                event_end_utc=t.isoformat(),
                title=title,
                event_class=event_class,
                event_channel=channel,
                expected_gold_direction=expected,
                initial_importance=importance,
                confidence=0.65,
                source_name="fred_numeric_backfill",
                source_url_or_note=f"source_series={sid}",
                manual_tags=f"numeric_shock;{sid}",
                notes=reason + "; timestamp is a daily-shock proxy, not original news release time",
            ))

    # Remove same-day duplicate oil events if WTI and Brent both fire: keep stronger importance, then WTI first.
    dedup: Dict[Tuple[str, str, str], EventRow] = {}
    for e in events:
        day = e.event_time_utc[:10]
        key = (day, e.event_class, e.event_channel)
        old = dedup.get(key)
        if old is None or e.initial_importance > old.initial_importance:
            dedup[key] = e

    events = sorted(dedup.values(), key=lambda e: (e.event_time_utc, e.event_class, e.event_id))
    if max_events and len(events) > max_events:
        # Keep most important, then restore chronological order.
        events = sorted(events, key=lambda e: (e.initial_importance, e.event_time_utc), reverse=True)[:max_events]
        events = sorted(events, key=lambda e: (e.event_time_utc, e.event_class, e.event_id))
    return events


def event_key_from_dict(row: dict) -> str:
    title = (row.get("title") or "").strip().lower()
    day = (row.get("event_time_utc") or "")[:10]
    source = (row.get("source_url_or_note") or row.get("event_id") or "").strip().lower()
    return stable_hash(day + "|" + title + "|" + source)


def merge_existing_and_generated(existing: Sequence[dict], generated: Sequence[EventRow]) -> List[dict]:
    merged: Dict[str, dict] = {}
    for row in existing:
        title = (row.get("title") or "").strip()
        if not title or title.upper().startswith("EXAMPLE"):
            continue
        normalized = {h: row.get(h, "") for h in HEADER}
        merged[event_key_from_dict(normalized)] = normalized

    for e in generated:
        row = asdict(e)
        normalized = {h: row.get(h, "") for h in HEADER}
        merged[event_key_from_dict(normalized)] = normalized

    return sorted(merged.values(), key=lambda r: (r.get("event_time_utc", ""), r.get("event_class", ""), r.get("event_id", "")))


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS numeric_shock_events (
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
            generated_utc TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS numeric_shock_event_runs (
            run_id TEXT PRIMARY KEY,
            tool_version TEXT,
            generated_events INTEGER,
            merged_events INTEGER,
            generated_utc TEXT
        )
    """)
    conn.commit()


def upsert_shock_events(conn: sqlite3.Connection, events: Sequence[EventRow], merged_count: int) -> None:
    gen = now_iso()
    for e in events:
        conn.execute("""
            INSERT OR REPLACE INTO numeric_shock_events (
                event_id, event_time_utc, event_end_utc, title, event_class, event_channel,
                expected_gold_direction, initial_importance, confidence, source_name,
                source_url_or_note, manual_tags, notes, generated_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            e.event_id, e.event_time_utc, e.event_end_utc, e.title, e.event_class, e.event_channel,
            e.expected_gold_direction, e.initial_importance, e.confidence, e.source_name,
            e.source_url_or_note, e.manual_tags, e.notes, gen
        ))
    conn.execute("""
        INSERT OR REPLACE INTO numeric_shock_event_runs (
            run_id, tool_version, generated_events, merged_events, generated_utc
        )
        VALUES (?, ?, ?, ?, ?)
    """, (f"stage10c_numeric_shock_{gen}", TOOL_VERSION, len(events), merged_count, gen))
    conn.commit()


def write_report(report_dir: Path, payload: dict, generated: Sequence[EventRow], merged: Sequence[dict]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "stage10c_numeric_shock_event_backfill.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    by_class: Dict[str, int] = {}
    by_channel: Dict[str, int] = {}
    by_expected: Dict[str, int] = {}
    for e in generated:
        by_class[e.event_class] = by_class.get(e.event_class, 0) + 1
        by_channel[e.event_channel] = by_channel.get(e.event_channel, 0) + 1
        by_expected[str(e.expected_gold_direction)] = by_expected.get(str(e.expected_gold_direction), 0) + 1

    lines = [
        "# Stage 10C Numeric Shock Event Backfill",
        "",
        f"Generated UTC: `{payload['generated_utc']}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: historical event backfill only. This does not authorize demo, paper, or live orders.",
        "",
        "## Status",
        f"- db: `{payload['db_path']}`",
        f"- generated_numeric_shocks: `{len(generated)}`",
        f"- existing_events_before_merge: `{payload['existing_events_before_merge']}`",
        f"- merged_stage10a_events: `{len(merged)}`",
        f"- out_events_csv: `{payload['out_events_csv']}`",
        f"- shock_events_csv: `{payload['shock_events_csv']}`",
        "",
        "## Generated shocks by class",
        "| Event class | Events |",
        "|---|---:|",
    ]
    if by_class:
        for k, v in sorted(by_class.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"| {k} | {v} |")
    else:
        lines.append("| none | 0 |")

    lines += [
        "",
        "## Generated shocks by channel",
        "| Channel | Events |",
        "|---|---:|",
    ]
    if by_channel:
        for k, v in sorted(by_channel.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"| {k} | {v} |")
    else:
        lines.append("| none | 0 |")

    lines += [
        "",
        "## Expected gold direction",
        "| Direction | Meaning | Events |",
        "|---:|---|---:|",
        f"| 1 | initially supportive | {by_expected.get('1', 0)} |",
        f"| -1 | initially hostile | {by_expected.get('-1', 0)} |",
        f"| 0 | mixed / impact-only | {by_expected.get('0', 0)} |",
        "",
        "## Recent generated shocks preview",
        "| Time UTC | Class | Channel | Expected | Importance | Title |",
        "|---|---|---|---:|---:|---|",
    ]

    for e in list(generated)[-40:]:
        lines.append(
            f"| {e.event_time_utc} | {e.event_class} | {e.event_channel} | {e.expected_gold_direction} | "
            f"{e.initial_importance} | {e.title.replace('|','/')[:140]} |"
        )
    if not generated:
        lines.append("| none | none | none | 0 | 0 | none |")

    lines += [
        "",
        "## Interpretation",
        "- These are numeric shock proxies derived from FRED observations, not original news timestamps.",
        "- They are useful for historical event-reaction testing when news APIs are unavailable.",
        "- Stage 10A must measure actual XAUUSD reaction and decide whether each class is relevant/noisy.",
        "",
        "## Decision",
        "- No EA change.",
        "- No automatic news trading.",
        "- Run Stage 10A next on the merged event file.",
    ]

    (report_dir / "stage10c_numeric_shock_event_backfill.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(db_path: Path, out_events_path: Path, events_dir: Path, report_dir: Path, max_events: int) -> int:
    events_dir.mkdir(parents=True, exist_ok=True)
    generated_utc = now_iso()

    conn = connect_db(db_path)
    series = load_series(conn)
    generated = generate_shock_events(series, max_events=max_events)

    existing = read_existing_events(out_events_path)
    merged = merge_existing_and_generated(existing, generated)

    ensure_tables(conn)
    upsert_shock_events(conn, generated, len(merged))
    conn.close()

    shock_csv = events_dir / "stage10c_numeric_shock_events.csv"
    write_csv(shock_csv, [asdict(e) for e in generated])
    write_csv(out_events_path, merged, HEADER)

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated_utc,
        "db_path": str(db_path),
        "out_events_csv": str(out_events_path),
        "shock_events_csv": str(shock_csv),
        "existing_events_before_merge": len(existing),
        "generated_numeric_shocks": len(generated),
        "merged_stage10a_events": len(merged),
        "series_loaded": {sid: len(vals) for sid, vals in series.items()},
        "max_events": max_events,
    }
    write_report(report_dir, payload, generated, merged)

    print("Stage 10C numeric shock event backfill: DONE")
    print(f"generated_numeric_shocks={len(generated)} merged_stage10a_events={len(merged)}")
    print(f"Report: {report_dir / 'stage10c_numeric_shock_event_backfill.md'}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--out-events", default=str(DEFAULT_OUT_EVENTS))
    p.add_argument("--events-dir", default=str(DEFAULT_EVENTS_DIR))
    p.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    p.add_argument("--max-events", type=int, default=500)
    args = p.parse_args()
    return run(Path(args.db), Path(args.out_events), Path(args.events_dir), Path(args.report_dir), args.max_events)


if __name__ == "__main__":
    raise SystemExit(main())
