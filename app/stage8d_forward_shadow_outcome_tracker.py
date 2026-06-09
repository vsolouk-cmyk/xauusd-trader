#!/usr/bin/env python3
"""
Stage 8D — Forward Shadow Outcome Tracker

Reads Stage 8D EA v2 dry-run signals and resolves them against local AMarkets/MT5 M1 bars
stored in SQLite.

Strategy:
- xauusd_h4_up_compression_liquidity_long_v1
- long-only
- planned entry: next H1 open after signal close
- exit: earliest of:
  1. emergency stop 30 USD below entry
  2. time exit after 12 hours

Hard rules:
- Research/forward-shadow only.
- No orders.
- No EA modification.
- No demo/paper/live authorization.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import List, Optional, Sequence


TOOL_VERSION = "v1"
STRATEGY_ID = "xauusd_h4_up_compression_liquidity_long_v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_OUT_DIR = Path("data/reports/stage8d_forward_shadow_outcomes")
DEFAULT_SIGNALS = Path("~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/XAUUSD_DryRun_v2_regime_shadow_signals.csv").expanduser()
BASE_COST_USD = 0.35


@dataclass
class M1Bar:
    t: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass
class ShadowSignal:
    strategy_id: str
    logged_at_gmt: str
    symbol: str
    signal_closed_h1_utc: datetime
    planned_entry_utc: datetime
    session_utc: str
    h1_close: float
    h4_close: float
    h4_ema20: float
    h4_ema50: float
    h4_ema20_slope_5: float
    h1_range16: float
    compression_pct: float
    direction: str
    exit_model: str
    time_exit_hours: int
    emergency_stop_usd: float


@dataclass
class ShadowOutcome:
    strategy_id: str
    symbol: str
    signal_closed_h1_utc: str
    planned_entry_utc: str
    session_utc: str
    status: str
    reason: str
    entry_utc: str
    entry_price: float
    exit_utc: str
    exit_price: float
    gross_usd: float
    net_x1: float
    net_x4: float
    m1_bars_checked: int
    compression_pct: float
    h4_ema20_slope_5: float


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
    for fmt in ("%Y.%m.%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M"):
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
        return int(float(str(v).strip()))
    except Exception:
        return default


def connect_ro(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(f"DB not found: {path}")
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_m1(conn: sqlite3.Connection) -> List[M1Bar]:
    rows = conn.execute(
        """
        SELECT utc_time, open, high, low, close
        FROM bars
        WHERE source='amarkets_mt5' AND symbol='XAUUSD' AND timeframe='1m'
        ORDER BY utc_time ASC
        """
    ).fetchall()
    out = []
    for r in rows:
        t = parse_time(r["utc_time"])
        if t is None:
            continue
        out.append(M1Bar(t=t, open=float(r["open"]), high=float(r["high"]), low=float(r["low"]), close=float(r["close"])))
    return out


def load_signals(path: Path) -> List[ShadowSignal]:
    if not path.exists():
        return []
    rows = list(csv.DictReader(path.read_text(encoding="utf-8-sig", errors="replace").splitlines()))
    out = []
    seen = set()

    for r in rows:
        sid = (r.get("strategy_id") or "").strip()
        if sid != STRATEGY_ID:
            continue
        closed = parse_time(r.get("signal_closed_h1_utc"))
        entry = parse_time(r.get("planned_entry_utc"))
        if closed is None or entry is None:
            continue
        key = (sid, closed.isoformat(), (r.get("direction") or "long").strip())
        if key in seen:
            continue
        seen.add(key)
        out.append(ShadowSignal(
            strategy_id=sid,
            logged_at_gmt=r.get("logged_at_gmt", ""),
            symbol=r.get("symbol", "XAUUSD"),
            signal_closed_h1_utc=closed,
            planned_entry_utc=entry,
            session_utc=r.get("session_utc", ""),
            h1_close=safe_float(r.get("h1_close")),
            h4_close=safe_float(r.get("h4_close")),
            h4_ema20=safe_float(r.get("h4_ema20")),
            h4_ema50=safe_float(r.get("h4_ema50")),
            h4_ema20_slope_5=safe_float(r.get("h4_ema20_slope_5")),
            h1_range16=safe_float(r.get("h1_range16")),
            compression_pct=safe_float(r.get("compression_pct")),
            direction=(r.get("direction") or "long").strip(),
            exit_model=r.get("exit_model", ""),
            time_exit_hours=safe_int(r.get("time_exit_hours"), 12),
            emergency_stop_usd=safe_float(r.get("emergency_stop_usd"), 30.0),
        ))
    return sorted(out, key=lambda s: s.planned_entry_utc)


def resolve_signal(sig: ShadowSignal, m1: Sequence[M1Bar], times: Sequence[datetime]) -> ShadowOutcome:
    start = bisect.bisect_left(times, sig.planned_entry_utc)
    end_time = sig.planned_entry_utc + timedelta(hours=sig.time_exit_hours)
    end = bisect.bisect_left(times, end_time)

    if start >= len(m1):
        return ShadowOutcome(sig.strategy_id, sig.symbol, sig.signal_closed_h1_utc.isoformat(), sig.planned_entry_utc.isoformat(), sig.session_utc, "OPEN", "missing_m1_after_entry", "", 0, "", 0, 0, 0, 0, sig.compression_pct, sig.h4_ema20_slope_5)

    if end > len(m1):
        return ShadowOutcome(sig.strategy_id, sig.symbol, sig.signal_closed_h1_utc.isoformat(), sig.planned_entry_utc.isoformat(), sig.session_utc, "OPEN", "m1_not_complete_for_12h_horizon", m1[start].t.isoformat(), m1[start].open, "", 0, 0, 0, len(m1[start:]), sig.compression_pct, sig.h4_ema20_slope_5)

    path = m1[start:end]
    entry = path[0].open
    stop = entry - sig.emergency_stop_usd

    for b in path:
        if b.low <= stop:
            gross = stop - entry
            return ShadowOutcome(
                sig.strategy_id, sig.symbol, sig.signal_closed_h1_utc.isoformat(), sig.planned_entry_utc.isoformat(), sig.session_utc,
                "RESOLVED", "emergency_stop", path[0].t.isoformat(), round(entry, 6), b.t.isoformat(), round(stop, 6),
                round(gross, 6), round(gross - BASE_COST_USD, 6), round(gross - 4 * BASE_COST_USD, 6), len(path),
                sig.compression_pct, sig.h4_ema20_slope_5
            )

    last = path[-1]
    gross = last.close - entry
    return ShadowOutcome(
        sig.strategy_id, sig.symbol, sig.signal_closed_h1_utc.isoformat(), sig.planned_entry_utc.isoformat(), sig.session_utc,
        "RESOLVED", "time_exit_12h", path[0].t.isoformat(), round(entry, 6), last.t.isoformat(), round(last.close, 6),
        round(gross, 6), round(gross - BASE_COST_USD, 6), round(gross - 4 * BASE_COST_USD, 6), len(path),
        sig.compression_pct, sig.h4_ema20_slope_5
    )


def summarize(outcomes: List[ShadowOutcome]) -> dict:
    resolved = [o for o in outcomes if o.status == "RESOLVED"]
    nets = [o.net_x4 for o in resolved]
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x < 0]
    pf = 0.0
    if losses:
        pf = round(sum(wins) / abs(sum(losses)), 6) if wins else 0.0
    elif wins:
        pf = 999.0

    return {
        "total_signals": len(outcomes),
        "resolved": len(resolved),
        "open": len([o for o in outcomes if o.status != "RESOLVED"]),
        "total_net_x4": round(sum(nets), 6) if nets else 0.0,
        "median_net_x4": round(median(nets), 6) if nets else 0.0,
        "pf_x4": pf,
        "win_rate_x4": round(len(wins) / len(nets), 6) if nets else 0.0,
        "emergency_stops": len([o for o in resolved if o.reason == "emergency_stop"]),
        "time_exits": len([o for o in resolved if o.reason == "time_exit_12h"]),
    }


def write_outputs(out_dir: Path, signals_path: Path, db_path: Path, outcomes: List[ShadowOutcome]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize(outcomes)
    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": now_iso(),
        "strategy_id": STRATEGY_ID,
        "signals_csv": str(signals_path),
        "db_path": str(db_path),
        "summary": summary,
        "outcomes": [asdict(o) for o in outcomes],
    }
    (out_dir / "stage8d_forward_shadow_outcomes.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    with (out_dir / "stage8d_forward_shadow_outcomes.csv").open("w", newline="", encoding="utf-8") as f:
        if outcomes:
            cols = list(asdict(outcomes[0]).keys())
        else:
            cols = ["strategy_id", "symbol", "signal_closed_h1_utc", "planned_entry_utc", "status", "reason"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for o in outcomes:
            w.writerow(asdict(o))

    lines = [
        "# Stage 8D Forward Shadow Outcomes",
        "",
        f"Generated UTC: `{payload['generated_utc']}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: forward-shadow only. This does not authorize demo, paper, or live orders.",
        "",
        "## Inputs",
        f"- strategy_id: `{STRATEGY_ID}`",
        f"- signals_csv: `{signals_path}`",
        f"- db: `{db_path}`",
        "",
        "## Summary",
        f"- total_signals: `{summary['total_signals']}`",
        f"- resolved: `{summary['resolved']}`",
        f"- open: `{summary['open']}`",
        f"- total_net_x4: `{summary['total_net_x4']}`",
        f"- median_net_x4: `{summary['median_net_x4']}`",
        f"- pf_x4: `{summary['pf_x4']}`",
        f"- win_rate_x4: `{summary['win_rate_x4']}`",
        f"- emergency_stops: `{summary['emergency_stops']}`",
        f"- time_exits: `{summary['time_exits']}`",
        "",
        "## Recent outcomes",
        "| Signal closed UTC | Entry UTC | Session | Status | Reason | Entry | Exit UTC | Exit | Net x4 |",
        "|---|---|---|---|---|---:|---|---:|---:|",
    ]
    for o in outcomes[-20:]:
        lines.append(f"| {o.signal_closed_h1_utc} | {o.planned_entry_utc} | {o.session_utc} | {o.status} | {o.reason} | {o.entry_price} | {o.exit_utc} | {o.exit_price} | {o.net_x4} |")

    lines += [
        "",
        "## Decision",
        "- This report is live forward-shadow evidence only.",
        "- No orders are authorized.",
        "- Paper-order remains forbidden until sufficient independent forward-shadow outcomes pass strict thresholds.",
    ]
    (out_dir / "stage8d_forward_shadow_outcomes.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--signals-csv", default=str(DEFAULT_SIGNALS))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = p.parse_args()

    db_path = Path(args.db)
    sig_path = Path(args.signals_csv).expanduser()

    conn = connect_ro(db_path)
    m1 = load_m1(conn)
    conn.close()
    times = [b.t for b in m1]

    signals = load_signals(sig_path)
    outcomes = [resolve_signal(s, m1, times) for s in signals]
    write_outputs(Path(args.out_dir), sig_path, db_path, outcomes)

    print("Stage 8D forward shadow outcome tracker: DONE")
    print(f"signals={len(signals)} outcomes={len(outcomes)}")
    print(f"Report: {Path(args.out_dir) / 'stage8d_forward_shadow_outcomes.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
