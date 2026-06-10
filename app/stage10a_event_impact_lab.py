#!/usr/bin/env python3
"""
Stage 10A — Event / News Impact Lab

Purpose:
- Convert manually curated news/macro/geopolitical events into testable records.
- Measure realized XAUUSD reaction after each event.
- Build adaptive event-class weights based on actual market response, not opinion.
- Identify which event categories are high/low/no impact.

Inputs:
- data/config/stage10a_news_events.csv
- data/local/xauusd_local_store.sqlite
  bars table with AMarkets MT5 XAUUSD H1 data
  optional macro_daily_regime

Outputs:
- data/reports/stage10a_event_impact_lab/stage10a_event_impact_lab.md
- data/reports/stage10a_event_impact_lab/stage10a_events_annotated.csv
- data/reports/stage10a_event_impact_lab/stage10a_event_class_weights.csv
- data/reports/stage10a_event_impact_lab/stage10a_event_impact_lab.json
- SQLite tables:
  news_events
  news_event_reactions
  news_event_class_weights

Hard rules:
- Research only.
- No trading signal.
- No EA change.
- No demo/paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from statistics import median, mean
from typing import Dict, List, Optional, Sequence, Tuple


TOOL_VERSION = "v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_EVENTS_CSV = Path("data/config/stage10a_news_events.csv")
DEFAULT_OUT_DIR = Path("data/reports/stage10a_event_impact_lab")
HORIZONS_H = [1, 4, 12, 24]


@dataclass
class Bar:
    utc_time: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass
class NewsEvent:
    event_id: str
    event_time_utc: datetime
    event_end_utc: datetime
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


@dataclass
class EventReaction:
    event_id: str
    event_time_utc: str
    title: str
    event_class: str
    event_channel: str
    source_name: str
    expected_gold_direction: int
    initial_importance: float
    confidence: float
    macro_regime_numeric: str
    macro_score_long_gold: Optional[float]
    anchor_bar_utc: str
    anchor_price: float
    ret_1h: Optional[float]
    ret_4h: Optional[float]
    ret_12h: Optional[float]
    ret_24h: Optional[float]
    mfe_12h: Optional[float]
    mae_12h: Optional[float]
    abs_impact_4h: Optional[float]
    abs_impact_12h: Optional[float]
    normalized_impact_4h: Optional[float]
    normalized_impact_12h: Optional[float]
    realized_direction_4h: int
    realized_direction_12h: int
    direction_match_4h: Optional[int]
    direction_match_12h: Optional[int]
    impact_bucket_12h: str
    adaptive_score: float
    verdict: str


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


def safe_float(v, default: float = 0.0) -> float:
    try:
        if v is None or str(v).strip() == "":
            return default
        return float(str(v).strip())
    except Exception:
        return default


def safe_int(v, default: int = 0) -> int:
    try:
        if v is None or str(v).strip() == "":
            return default
        return int(float(str(v).strip()))
    except Exception:
        return default


def sign(v: Optional[float], flat_threshold: float = 0.15) -> int:
    if v is None:
        return 0
    if v > flat_threshold:
        return 1
    if v < -flat_threshold:
        return -1
    return 0


def direction_match(expected: int, realized: int) -> Optional[int]:
    if expected == 0 or realized == 0:
        return None
    return 1 if expected == realized else 0


def read_events(path: Path) -> List[NewsEvent]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        return []
    rows = list(csv.DictReader(text.splitlines()))
    out: List[NewsEvent] = []
    for idx, r in enumerate(rows, start=1):
        title = (r.get("title") or "").strip()
        if not title or title.upper().startswith("EXAMPLE"):
            continue
        t = parse_time(r.get("event_time_utc") or "")
        if t is None:
            continue
        end = parse_time(r.get("event_end_utc") or "")
        if end is None:
            end = t
        event_id = (r.get("event_id") or f"event_{idx}_{t.strftime('%Y%m%d%H%M')}").strip()
        out.append(NewsEvent(
            event_id=event_id,
            event_time_utc=t,
            event_end_utc=end,
            title=title,
            event_class=(r.get("event_class") or "unknown").strip(),
            event_channel=(r.get("event_channel") or "unknown").strip(),
            expected_gold_direction=safe_int(r.get("expected_gold_direction"), 0),
            initial_importance=safe_float(r.get("initial_importance"), 1.0),
            confidence=max(0.0, min(1.0, safe_float(r.get("confidence"), 0.5))),
            source_name=(r.get("source_name") or "").strip(),
            source_url_or_note=(r.get("source_url_or_note") or "").strip(),
            manual_tags=(r.get("manual_tags") or "").strip(),
            notes=(r.get("notes") or "").strip(),
        ))
    return out


def connect_db(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(f"DB not found: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def load_h1_bars(conn: sqlite3.Connection) -> List[Bar]:
    rows = conn.execute("""
        SELECT utc_time, open, high, low, close
        FROM bars
        WHERE source='amarkets_mt5' AND symbol='XAUUSD' AND timeframe='1h'
        ORDER BY utc_time ASC
    """).fetchall()
    out = []
    for r in rows:
        t = parse_time(r["utc_time"])
        if t is None:
            continue
        out.append(Bar(t, float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])))
    return out


def load_macro_regimes(conn: sqlite3.Connection) -> Dict[str, dict]:
    try:
        rows = conn.execute("""
            SELECT obs_date, macro_regime, macro_score_long_gold
            FROM macro_daily_regime
            ORDER BY obs_date ASC
        """).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["obs_date"]: {"macro_regime": r["macro_regime"], "macro_score_long_gold": r["macro_score_long_gold"]} for r in rows}


def rolling_baseline_abs_move(bars: Sequence[Bar], idx: int, lookback: int = 120) -> float:
    lo = max(1, idx - lookback)
    vals = []
    for i in range(lo, idx):
        vals.append(abs(bars[i].close - bars[i - 1].close))
    vals = [v for v in vals if v > 0]
    if not vals:
        return 1.0
    return max(0.25, median(vals))


def first_bar_at_or_after(bars: Sequence[Bar], t: datetime) -> Optional[int]:
    lo, hi = 0, len(bars) - 1
    ans = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if bars[mid].utc_time >= t:
            ans = mid
            hi = mid - 1
        else:
            lo = mid + 1
    return ans


def bar_at_horizon(bars: Sequence[Bar], idx: int, hours: int) -> Optional[int]:
    target = bars[idx].utc_time + timedelta(hours=hours)
    j = first_bar_at_or_after(bars, target)
    if j is None or j >= len(bars):
        return None
    return j


def reaction_for_event(event: NewsEvent, bars: Sequence[Bar], macro: Dict[str, dict]) -> Optional[EventReaction]:
    idx = first_bar_at_or_after(bars, event.event_time_utc)
    if idx is None:
        return None
    anchor = bars[idx]
    anchor_price = anchor.open

    rets: Dict[int, Optional[float]] = {}
    for h in HORIZONS_H:
        j = bar_at_horizon(bars, idx, h)
        rets[h] = None if j is None else round(bars[j].close - anchor_price, 6)

    j12 = bar_at_horizon(bars, idx, 12)
    mfe_12 = None
    mae_12 = None
    if j12 is not None:
        window = bars[idx:j12 + 1]
        mfe_12 = round(max(b.high for b in window) - anchor_price, 6)
        mae_12 = round(min(b.low for b in window) - anchor_price, 6)

    base = rolling_baseline_abs_move(bars, idx)
    abs4 = None if rets[4] is None else abs(rets[4])
    abs12 = None if rets[12] is None else abs(rets[12])
    norm4 = None if abs4 is None else round(abs4 / base, 6)
    norm12 = None if abs12 is None else round(abs12 / base, 6)

    realized4 = sign(rets[4])
    realized12 = sign(rets[12])

    m = macro.get(event.event_time_utc.date().isoformat(), {})
    macro_regime = m.get("macro_regime", "unknown")
    macro_score = m.get("macro_score_long_gold", None)

    dm4 = direction_match(event.expected_gold_direction, realized4)
    dm12 = direction_match(event.expected_gold_direction, realized12)

    if norm12 is None:
        bucket = "unresolved"
    elif norm12 >= 4.0:
        bucket = "high_impact"
    elif norm12 >= 2.0:
        bucket = "medium_impact"
    elif norm12 >= 0.75:
        bucket = "low_impact"
    else:
        bucket = "noisy_or_no_impact"

    impact_component = min(3.0, norm12 or norm4 or 0.0)
    if event.expected_gold_direction == 0:
        direction_component = 0.5
    elif dm12 == 1:
        direction_component = 1.0
    elif dm4 == 1:
        direction_component = 0.7
    elif dm12 == 0:
        direction_component = -0.5
    else:
        direction_component = 0.0

    adaptive = round(event.initial_importance * event.confidence * impact_component * direction_component, 6)

    if bucket in ("high_impact", "medium_impact") and (dm12 == 1 or event.expected_gold_direction == 0):
        verdict = "candidate_relevant"
    elif bucket in ("high_impact", "medium_impact") and dm12 == 0:
        verdict = "impactful_but_direction_wrong"
    elif bucket == "low_impact":
        verdict = "low_impact_monitor"
    elif bucket == "noisy_or_no_impact":
        verdict = "likely_noise"
    else:
        verdict = "unresolved"

    return EventReaction(
        event_id=event.event_id,
        event_time_utc=event.event_time_utc.isoformat(),
        title=event.title,
        event_class=event.event_class,
        event_channel=event.event_channel,
        source_name=event.source_name,
        expected_gold_direction=event.expected_gold_direction,
        initial_importance=event.initial_importance,
        confidence=event.confidence,
        macro_regime_numeric=macro_regime,
        macro_score_long_gold=macro_score,
        anchor_bar_utc=anchor.utc_time.isoformat(),
        anchor_price=round(anchor_price, 6),
        ret_1h=rets[1],
        ret_4h=rets[4],
        ret_12h=rets[12],
        ret_24h=rets[24],
        mfe_12h=mfe_12,
        mae_12h=mae_12,
        abs_impact_4h=None if abs4 is None else round(abs4, 6),
        abs_impact_12h=None if abs12 is None else round(abs12, 6),
        normalized_impact_4h=norm4,
        normalized_impact_12h=norm12,
        realized_direction_4h=realized4,
        realized_direction_12h=realized12,
        direction_match_4h=dm4,
        direction_match_12h=dm12,
        impact_bucket_12h=bucket,
        adaptive_score=adaptive,
        verdict=verdict,
    )


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS news_events (
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
            imported_utc TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS news_event_reactions (
            event_id TEXT PRIMARY KEY,
            event_time_utc TEXT,
            title TEXT,
            event_class TEXT,
            event_channel TEXT,
            source_name TEXT,
            expected_gold_direction INTEGER,
            initial_importance REAL,
            confidence REAL,
            macro_regime_numeric TEXT,
            macro_score_long_gold REAL,
            anchor_bar_utc TEXT,
            anchor_price REAL,
            ret_1h REAL,
            ret_4h REAL,
            ret_12h REAL,
            ret_24h REAL,
            mfe_12h REAL,
            mae_12h REAL,
            abs_impact_4h REAL,
            abs_impact_12h REAL,
            normalized_impact_4h REAL,
            normalized_impact_12h REAL,
            realized_direction_4h INTEGER,
            realized_direction_12h INTEGER,
            direction_match_4h INTEGER,
            direction_match_12h INTEGER,
            impact_bucket_12h TEXT,
            adaptive_score REAL,
            verdict TEXT,
            generated_utc TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS news_event_class_weights (
            event_class TEXT,
            event_channel TEXT,
            events INTEGER,
            avg_adaptive_score REAL,
            avg_abs_impact_12h REAL,
            avg_norm_impact_12h REAL,
            direction_accuracy_12h REAL,
            candidate_relevant_count INTEGER,
            likely_noise_count INTEGER,
            recommended_weight REAL,
            generated_utc TEXT,
            PRIMARY KEY (event_class, event_channel)
        )
    """)
    conn.commit()


def upsert_events(conn: sqlite3.Connection, events: Sequence[NewsEvent]) -> None:
    gen = now_iso()
    for e in events:
        conn.execute("""
            INSERT OR REPLACE INTO news_events (
                event_id, event_time_utc, event_end_utc, title, event_class, event_channel,
                expected_gold_direction, initial_importance, confidence, source_name,
                source_url_or_note, manual_tags, notes, imported_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            e.event_id, e.event_time_utc.isoformat(), e.event_end_utc.isoformat(), e.title, e.event_class, e.event_channel,
            e.expected_gold_direction, e.initial_importance, e.confidence, e.source_name,
            e.source_url_or_note, e.manual_tags, e.notes, gen,
        ))
    conn.commit()


def upsert_reactions(conn: sqlite3.Connection, reactions: Sequence[EventReaction]) -> None:
    gen = now_iso()
    for r in reactions:
        d = asdict(r)
        conn.execute("""
            INSERT OR REPLACE INTO news_event_reactions (
                event_id, event_time_utc, title, event_class, event_channel, source_name,
                expected_gold_direction, initial_importance, confidence, macro_regime_numeric, macro_score_long_gold,
                anchor_bar_utc, anchor_price, ret_1h, ret_4h, ret_12h, ret_24h,
                mfe_12h, mae_12h, abs_impact_4h, abs_impact_12h, normalized_impact_4h, normalized_impact_12h,
                realized_direction_4h, realized_direction_12h, direction_match_4h, direction_match_12h,
                impact_bucket_12h, adaptive_score, verdict, generated_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            d["event_id"], d["event_time_utc"], d["title"], d["event_class"], d["event_channel"], d["source_name"],
            d["expected_gold_direction"], d["initial_importance"], d["confidence"], d["macro_regime_numeric"], d["macro_score_long_gold"],
            d["anchor_bar_utc"], d["anchor_price"], d["ret_1h"], d["ret_4h"], d["ret_12h"], d["ret_24h"],
            d["mfe_12h"], d["mae_12h"], d["abs_impact_4h"], d["abs_impact_12h"], d["normalized_impact_4h"], d["normalized_impact_12h"],
            d["realized_direction_4h"], d["realized_direction_12h"], d["direction_match_4h"], d["direction_match_12h"],
            d["impact_bucket_12h"], d["adaptive_score"], d["verdict"], gen,
        ))
    conn.commit()


def compute_class_weights(reactions: Sequence[EventReaction]) -> List[dict]:
    groups: Dict[Tuple[str, str], List[EventReaction]] = {}
    for r in reactions:
        groups.setdefault((r.event_class, r.event_channel), []).append(r)

    rows: List[dict] = []
    for (cls, channel), rs in sorted(groups.items()):
        impacts = [r.abs_impact_12h for r in rs if r.abs_impact_12h is not None]
        norms = [r.normalized_impact_12h for r in rs if r.normalized_impact_12h is not None]
        adaptive = [r.adaptive_score for r in rs]
        matches = [r.direction_match_12h for r in rs if r.direction_match_12h is not None]
        relevant = sum(1 for r in rs if r.verdict == "candidate_relevant")
        noise = sum(1 for r in rs if r.verdict == "likely_noise")

        avg_norm = mean(norms) if norms else 0.0
        direction_acc = mean(matches) if matches else None
        avg_adaptive = mean(adaptive) if adaptive else 0.0

        sample = len(rs)
        reliability = min(1.0, sample / 8.0)
        dir_factor = 0.75 if direction_acc is None else max(0.25, direction_acc)
        weight = (0.5 + min(2.5, avg_norm) / 2.5) * reliability * dir_factor
        if avg_adaptive < 0:
            weight *= 0.5
        weight = round(max(0.0, min(2.0, weight)), 6)

        rows.append({
            "event_class": cls,
            "event_channel": channel,
            "events": sample,
            "avg_adaptive_score": round(avg_adaptive, 6),
            "avg_abs_impact_12h": round(mean(impacts), 6) if impacts else 0.0,
            "avg_norm_impact_12h": round(avg_norm, 6),
            "direction_accuracy_12h": "" if direction_acc is None else round(direction_acc, 6),
            "candidate_relevant_count": relevant,
            "likely_noise_count": noise,
            "recommended_weight": weight,
        })

    rows.sort(key=lambda r: (r["recommended_weight"], r["events"]), reverse=True)
    return rows


def upsert_weights(conn: sqlite3.Connection, weights: Sequence[dict]) -> None:
    gen = now_iso()
    for r in weights:
        conn.execute("""
            INSERT OR REPLACE INTO news_event_class_weights (
                event_class, event_channel, events, avg_adaptive_score, avg_abs_impact_12h,
                avg_norm_impact_12h, direction_accuracy_12h, candidate_relevant_count,
                likely_noise_count, recommended_weight, generated_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r["event_class"], r["event_channel"], r["events"], r["avg_adaptive_score"], r["avg_abs_impact_12h"],
            r["avg_norm_impact_12h"], None if r["direction_accuracy_12h"] == "" else r["direction_accuracy_12h"],
            r["candidate_relevant_count"], r["likely_noise_count"], r["recommended_weight"], gen,
        ))
    conn.commit()


def write_csv(path: Path, rows: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = list(rows[0].keys()) if rows else ["empty"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def run(db_path: Path, events_csv: Path, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = now_iso()

    events = read_events(events_csv)
    conn = connect_db(db_path)
    ensure_tables(conn)
    bars = load_h1_bars(conn)
    macro = load_macro_regimes(conn)

    reactions: List[EventReaction] = []
    for e in events:
        r = reaction_for_event(e, bars, macro)
        if r is not None:
            reactions.append(r)

    weights = compute_class_weights(reactions)
    upsert_events(conn, events)
    upsert_reactions(conn, reactions)
    upsert_weights(conn, weights)
    conn.close()

    write_csv(out_dir / "stage10a_events_annotated.csv", [asdict(r) for r in reactions])
    write_csv(out_dir / "stage10a_event_class_weights.csv", weights)

    verdict_counts: Dict[str, int] = {}
    bucket_counts: Dict[str, int] = {}
    for r in reactions:
        verdict_counts[r.verdict] = verdict_counts.get(r.verdict, 0) + 1
        bucket_counts[r.impact_bucket_12h] = bucket_counts.get(r.impact_bucket_12h, 0) + 1

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "db_path": str(db_path),
        "events_csv": str(events_csv),
        "events_loaded": len(events),
        "h1_bars": len(bars),
        "reactions_resolved": len(reactions),
        "class_weight_rows": len(weights),
        "verdict_counts": verdict_counts,
        "bucket_counts": bucket_counts,
        "top_weights": weights[:20],
    }
    (out_dir / "stage10a_event_impact_lab.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Stage 10A Event / News Impact Lab",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: research only. This does not authorize demo, paper, or live orders.",
        "",
        "## Inputs",
        f"- db: `{db_path}`",
        f"- events_csv: `{events_csv}`",
        f"- events_loaded: `{len(events)}`",
        f"- h1_bars: `{len(bars)}`",
        f"- reactions_resolved: `{len(reactions)}`",
        f"- class_weight_rows: `{len(weights)}`",
        "",
        "## Impact buckets",
        "| Bucket | Events |",
        "|---|---:|",
    ]
    if bucket_counts:
        for k, v in sorted(bucket_counts.items()):
            lines.append(f"| {k} | {v} |")
    else:
        lines.append("| none | 0 |")

    lines += [
        "",
        "## Verdict counts",
        "| Verdict | Events |",
        "|---|---:|",
    ]
    if verdict_counts:
        for k, v in sorted(verdict_counts.items()):
            lines.append(f"| {k} | {v} |")
    else:
        lines.append("| none | 0 |")

    lines += [
        "",
        "## Adaptive event-class weights",
        "| Event class | Channel | Events | Avg norm impact 12h | Direction acc 12h | Relevant | Noise | Recommended weight |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    if weights:
        for r in weights[:50]:
            lines.append(
                f"| {r['event_class']} | {r['event_channel']} | {r['events']} | {r['avg_norm_impact_12h']} | "
                f"{r['direction_accuracy_12h']} | {r['candidate_relevant_count']} | {r['likely_noise_count']} | {r['recommended_weight']} |"
            )
    else:
        lines.append("| none | none | 0 | 0 |  | 0 | 0 | 0 |")

    lines += [
        "",
        "## Interpretation",
        "- `high_impact` and `medium_impact` event classes become candidates for future reporting/guard logic.",
        "- `likely_noise` classes should not be used in trading decisions.",
        "- `impactful_but_direction_wrong` means the event moves gold but our initial direction model is wrong.",
        "- `recommended_weight` is conservative and sample-size capped; small samples cannot create strong weights.",
        "",
        "## Commercialization relevance",
        "- This stage can accelerate the project because it does not wait for rare v2 technical signals.",
        "- It turns news evaluation into measured event-reaction data.",
        "- It can later support a semi-discretionary dashboard: technical regime + macro numeric + event risk.",
        "",
        "## Decision",
        "- No EA change.",
        "- No automatic news trading.",
        "- Next valid step is filling curated event rows and rerunning this lab.",
    ]

    if not events:
        lines += [
            "",
            "## Warning",
            "- No events were loaded. Copy the template to `data/config/stage10a_news_events.csv` and fill real events.",
        ]

    (out_dir / "stage10a_event_impact_lab.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 10A event impact lab: DONE")
    print(f"events_loaded={len(events)} reactions_resolved={len(reactions)} class_weights={len(weights)}")
    print(f"Report: {out_dir / 'stage10a_event_impact_lab.md'}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--events-csv", default=str(DEFAULT_EVENTS_CSV))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = p.parse_args()
    return run(Path(args.db), Path(args.events_csv), Path(args.out_dir))


if __name__ == "__main__":
    raise SystemExit(main())
