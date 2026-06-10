#!/usr/bin/env python3
"""
Stage 9A — Macro/Fundamental Feature Store

Structured macro/event layer for XAUUSD research.
Research only. No orders. No EA changes. No demo/paper/live authorization.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Dict, List, Optional, Sequence, Tuple

TOOL_VERSION = "v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_EVENTS = Path("data/config/stage9a_macro_events.csv")
DEFAULT_OUT_DIR = Path("data/reports/stage9a_macro_feature_store")
DEFAULT_STAGE8B_TRADES = Path("data/reports/stage8b_single_regime_thesis_lab/stage8b_single_regime_trades.csv")
DEFAULT_STAGE8D_SIGNALS = Path("~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/XAUUSD_DryRun_v2_regime_shadow_signals.csv").expanduser()

@dataclass
class MacroEvent:
    event_id: str
    event_time_utc: datetime
    event_end_utc: datetime
    label: str
    category: str
    impact: str
    guard_before_min: int
    guard_after_min: int
    mode: str
    event_gold_bias: float
    safe_haven_score: float
    real_yield_pressure: float
    usd_pressure: float
    oil_inflation_pressure: float
    growth_fear_score: float
    central_bank_demand_score: float
    confidence: float
    source_note: str

    @property
    def window_start(self) -> datetime:
        return self.event_time_utc - timedelta(minutes=self.guard_before_min)

    @property
    def window_end(self) -> datetime:
        return self.event_end_utc + timedelta(minutes=self.guard_after_min)

    @property
    def score(self) -> float:
        raw = (
            self.event_gold_bias
            + self.safe_haven_score
            + self.growth_fear_score
            + self.central_bank_demand_score
            - self.real_yield_pressure
            - self.usd_pressure
            - self.oil_inflation_pressure
        )
        return raw * self.confidence


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


def regime(score: float, block: bool = False) -> str:
    if score >= 2.0:
        base = "supportive"
    elif score <= -2.0:
        base = "hostile"
    elif abs(score) >= 0.75:
        base = "mixed"
    else:
        base = "neutral"
    return f"event_risk_{base}" if block else base


def floor_hour(t: datetime) -> datetime:
    return t.replace(minute=0, second=0, microsecond=0)


def connect(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(f"SQLite DB not found: {path}. Run Stage 6B first.")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""
    CREATE TABLE IF NOT EXISTS macro_events (
        event_id TEXT PRIMARY KEY,
        event_time_utc TEXT,
        event_end_utc TEXT,
        window_start_utc TEXT,
        window_end_utc TEXT,
        label TEXT,
        category TEXT,
        impact TEXT,
        guard_before_min INTEGER,
        guard_after_min INTEGER,
        mode TEXT,
        event_gold_bias REAL,
        safe_haven_score REAL,
        real_yield_pressure REAL,
        usd_pressure REAL,
        oil_inflation_pressure REAL,
        growth_fear_score REAL,
        central_bank_demand_score REAL,
        confidence REAL,
        macro_score REAL,
        macro_regime TEXT,
        source_note TEXT,
        imported_utc TEXT
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS macro_context_h1 (
        utc_time TEXT PRIMARY KEY,
        macro_score REAL,
        macro_regime TEXT,
        active_event_count INTEGER,
        active_event_ids TEXT,
        active_labels TEXT,
        has_block_event INTEGER,
        generated_utc TEXT
    )
    """)
    conn.commit()


def load_h1_times(conn: sqlite3.Connection) -> List[datetime]:
    rows = conn.execute("""
        SELECT utc_time FROM bars
        WHERE source='amarkets_mt5' AND symbol='XAUUSD' AND timeframe='1h'
        ORDER BY utc_time ASC
    """).fetchall()
    out = []
    for r in rows:
        t = parse_time(r["utc_time"])
        if t is not None:
            out.append(t)
    return out


def read_events(path: Path) -> List[MacroEvent]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        return []
    out: List[MacroEvent] = []
    for i, r in enumerate(csv.DictReader(text.splitlines()), start=1):
        label = (r.get("label") or "").strip()
        if not label or label.upper().startswith("EXAMPLE"):
            continue
        t = parse_time(r.get("event_time_utc") or "")
        if t is None:
            continue
        end = parse_time(r.get("event_end_utc") or "") or t
        eid = (r.get("event_id") or f"event_{i}_{t:%Y%m%d%H%M}").strip()
        out.append(MacroEvent(
            event_id=eid,
            event_time_utc=t,
            event_end_utc=end,
            label=label,
            category=(r.get("category") or "macro").strip(),
            impact=(r.get("impact") or "medium").strip(),
            guard_before_min=safe_int(r.get("guard_before_min"), 120),
            guard_after_min=safe_int(r.get("guard_after_min"), 240),
            mode=(r.get("mode") or "score").strip(),
            event_gold_bias=safe_float(r.get("event_gold_bias")),
            safe_haven_score=safe_float(r.get("safe_haven_score")),
            real_yield_pressure=safe_float(r.get("real_yield_pressure")),
            usd_pressure=safe_float(r.get("usd_pressure")),
            oil_inflation_pressure=safe_float(r.get("oil_inflation_pressure")),
            growth_fear_score=safe_float(r.get("growth_fear_score")),
            central_bank_demand_score=safe_float(r.get("central_bank_demand_score")),
            confidence=max(0.0, min(1.0, safe_float(r.get("confidence"), 1.0))),
            source_note=(r.get("source_note") or "").strip(),
        ))
    return out


def upsert_events(conn: sqlite3.Connection, events: Sequence[MacroEvent]) -> None:
    imported = now_iso()
    for e in events:
        conn.execute("""
        INSERT INTO macro_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_id) DO UPDATE SET
            event_time_utc=excluded.event_time_utc,
            event_end_utc=excluded.event_end_utc,
            window_start_utc=excluded.window_start_utc,
            window_end_utc=excluded.window_end_utc,
            label=excluded.label,
            category=excluded.category,
            impact=excluded.impact,
            guard_before_min=excluded.guard_before_min,
            guard_after_min=excluded.guard_after_min,
            mode=excluded.mode,
            event_gold_bias=excluded.event_gold_bias,
            safe_haven_score=excluded.safe_haven_score,
            real_yield_pressure=excluded.real_yield_pressure,
            usd_pressure=excluded.usd_pressure,
            oil_inflation_pressure=excluded.oil_inflation_pressure,
            growth_fear_score=excluded.growth_fear_score,
            central_bank_demand_score=excluded.central_bank_demand_score,
            confidence=excluded.confidence,
            macro_score=excluded.macro_score,
            macro_regime=excluded.macro_regime,
            source_note=excluded.source_note,
            imported_utc=excluded.imported_utc
        """, (
            e.event_id, e.event_time_utc.isoformat(), e.event_end_utc.isoformat(),
            e.window_start.isoformat(), e.window_end.isoformat(), e.label, e.category, e.impact,
            e.guard_before_min, e.guard_after_min, e.mode, e.event_gold_bias, e.safe_haven_score,
            e.real_yield_pressure, e.usd_pressure, e.oil_inflation_pressure, e.growth_fear_score,
            e.central_bank_demand_score, e.confidence, round(e.score, 6), regime(e.score, e.mode.lower()=="block"),
            e.source_note, imported
        ))
    conn.commit()


def build_context(h1_times: Sequence[datetime], events: Sequence[MacroEvent]) -> List[dict]:
    rows = []
    for t in h1_times:
        active = [e for e in events if e.window_start <= t <= e.window_end]
        score = round(sum(e.score for e in active), 6)
        block = any(e.mode.lower() == "block" for e in active)
        rows.append({
            "utc_time": t.isoformat(),
            "macro_score": score,
            "macro_regime": regime(score, block),
            "active_event_count": len(active),
            "active_event_ids": ";".join(e.event_id for e in active),
            "active_labels": ";".join(e.label for e in active),
            "has_block_event": int(block),
        })
    return rows


def upsert_context(conn: sqlite3.Connection, rows: Sequence[dict]) -> None:
    gen = now_iso()
    for r in rows:
        conn.execute("""
        INSERT INTO macro_context_h1 VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(utc_time) DO UPDATE SET
            macro_score=excluded.macro_score,
            macro_regime=excluded.macro_regime,
            active_event_count=excluded.active_event_count,
            active_event_ids=excluded.active_event_ids,
            active_labels=excluded.active_labels,
            has_block_event=excluded.has_block_event,
            generated_utc=excluded.generated_utc
        """, (r["utc_time"], r["macro_score"], r["macro_regime"], r["active_event_count"], r["active_event_ids"], r["active_labels"], r["has_block_event"], gen))
    conn.commit()


def read_csv(path: Path) -> List[dict]:
    if not path.exists():
        return []
    return list(csv.DictReader(path.read_text(encoding="utf-8-sig", errors="replace").splitlines()))


def annotate_rows(rows: Sequence[dict], time_col_candidates: Sequence[str], ctx: Dict[str, dict]) -> List[dict]:
    out = []
    for r in rows:
        t = None
        for col in time_col_candidates:
            t = parse_time(r.get(col, ""))
            if t is not None:
                break
        if t is None:
            continue
        c = ctx.get(floor_hour(t).isoformat())
        rr = dict(r)
        if c is None:
            rr.update({"macro_score": 0.0, "macro_regime": "unknown", "macro_labels": ""})
        else:
            rr.update({"macro_score": c["macro_score"], "macro_regime": c["macro_regime"], "macro_labels": c["active_labels"]})
        out.append(rr)
    return out


def summarize_stage8b(rows: Sequence[dict]) -> List[dict]:
    groups: Dict[str, List[float]] = {}
    for r in rows:
        groups.setdefault(r.get("macro_regime", "unknown"), []).append(safe_float(r.get("net_x4")))
    out = []
    for k, vals in groups.items():
        wins = [v for v in vals if v > 0]
        losses = [v for v in vals if v < 0]
        pf = 999.0 if wins and not losses else (round(sum(wins)/abs(sum(losses)), 6) if wins and losses else 0.0)
        out.append({
            "macro_regime": k,
            "trades": len(vals),
            "total_net_x4": round(sum(vals), 6),
            "median_net_x4": round(median(vals), 6) if vals else 0.0,
            "pf_x4": pf,
            "win_rate_x4": round(len(wins)/len(vals), 6) if vals else 0.0,
        })
    return sorted(out, key=lambda r: r["total_net_x4"], reverse=True)


def write_csv(path: Path, rows: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = list(rows[0].keys()) if rows else ["empty"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--events-csv", default=str(DEFAULT_EVENTS))
    p.add_argument("--stage8b-trades", default=str(DEFAULT_STAGE8B_TRADES))
    p.add_argument("--stage8d-signals", default=str(DEFAULT_STAGE8D_SIGNALS))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = p.parse_args()

    db = Path(args.db)
    events_csv = Path(args.events_csv)
    out_dir = Path(args.out_dir)

    conn = connect(db)
    ensure_tables(conn)
    h1_times = load_h1_times(conn)
    events = read_events(events_csv)
    upsert_events(conn, events)
    context_rows = build_context(h1_times, events)
    upsert_context(conn, context_rows)
    conn.close()

    ctx = {r["utc_time"]: r for r in context_rows}
    stage8b = annotate_rows(read_csv(Path(args.stage8b_trades)), ["entry_utc", "signal_utc"], ctx)
    stage8b_summary = summarize_stage8b(stage8b)
    stage8d = annotate_rows(read_csv(Path(args.stage8d_signals).expanduser()), ["planned_entry_utc", "signal_closed_h1_utc"], ctx)

    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "stage9a_macro_events_loaded.csv", [
        {
            "event_id": e.event_id,
            "event_time_utc": e.event_time_utc.isoformat(),
            "event_end_utc": e.event_end_utc.isoformat(),
            "window_start_utc": e.window_start.isoformat(),
            "window_end_utc": e.window_end.isoformat(),
            "label": e.label,
            "category": e.category,
            "impact": e.impact,
            "mode": e.mode,
            "macro_score": round(e.score, 6),
            "macro_regime": regime(e.score, e.mode.lower()=="block"),
            "source_note": e.source_note,
        } for e in events
    ])
    write_csv(out_dir / "stage9a_macro_context_h1.csv", context_rows)
    write_csv(out_dir / "stage9a_stage8b_trades_annotated.csv", stage8b)
    write_csv(out_dir / "stage9a_stage8b_macro_summary.csv", stage8b_summary)
    write_csv(out_dir / "stage9a_stage8d_signals_annotated.csv", stage8d)

    coverage: Dict[str, int] = {}
    for r in context_rows:
        coverage[r["macro_regime"]] = coverage.get(r["macro_regime"], 0) + 1

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": now_iso(),
        "db_path": str(db),
        "events_csv": str(events_csv),
        "h1_rows": len(h1_times),
        "events_loaded": len(events),
        "contexts_generated": len(context_rows),
        "stage8b_trades_annotated": len(stage8b),
        "stage8d_signals_annotated": len(stage8d),
        "coverage": coverage,
        "stage8b_macro_summary": stage8b_summary,
    }
    (out_dir / "stage9a_macro_feature_store.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Stage 9A Macro/Fundamental Feature Store",
        "",
        f"Generated UTC: `{payload['generated_utc']}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: research only. This does not authorize demo, paper, or live orders.",
        "",
        "## Inputs",
        f"- db: `{db}`",
        f"- events_csv: `{events_csv}`",
        f"- h1_rows: `{len(h1_times)}`",
        f"- events_loaded: `{len(events)}`",
        f"- stage8b_trades_annotated: `{len(stage8b)}`",
        f"- stage8d_signals_annotated: `{len(stage8d)}`",
        "",
        "## Macro regime coverage",
        "| Macro regime | H1 rows |",
        "|---|---:|",
    ]
    for k, v in sorted(coverage.items()):
        lines.append(f"| {k} | {v} |")
    lines += [
        "",
        "## Stage 8B × Macro summary",
        "| Macro regime | Trades | Total net x4 | Median net x4 | PF x4 | Win rate x4 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in stage8b_summary or [{"macro_regime":"none", "trades":0, "total_net_x4":0, "median_net_x4":0, "pf_x4":0, "win_rate_x4":0}]:
        lines.append(f"| {r['macro_regime']} | {r['trades']} | {r['total_net_x4']} | {r['median_net_x4']} | {r['pf_x4']} | {r['win_rate_x4']} |")
    lines += [
        "",
        "## Scoring model",
        "```text",
        "score = event_gold_bias + safe_haven_score + growth_fear_score + central_bank_demand_score",
        "        - real_yield_pressure - usd_pressure - oil_inflation_pressure",
        "```",
        "",
        "## Decision",
        "- Stage 9A only creates the macro feature layer.",
        "- Stage 9B must test technical candidate behavior under supportive/hostile/mixed/event-risk regimes.",
        "- No EA/order workflow change is allowed from Stage 9A.",
    ]
    if not events:
        lines += ["", "## Warning", "- No real macro events loaded. Copy the template and fill `data/config/stage9a_macro_events.csv`."]
    (out_dir / "stage9a_macro_feature_store.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 9A macro feature store: DONE")
    print(f"h1_rows={len(h1_times)} events_loaded={len(events)} contexts={len(context_rows)}")
    print(f"Report: {out_dir / 'stage9a_macro_feature_store.md'}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
