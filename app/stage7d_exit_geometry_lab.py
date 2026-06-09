#!/usr/bin/env python3
"""
Stage 7D — Exit Geometry Lab

Purpose:
- Use candidate entries from Stage 7B.
- Test a small, pre-defined set of exit geometries.
- Determine whether weak Stage 7B results were caused by bad TP/SL/time-exit design
  rather than completely weak entries.

Important:
- This is NOT wide parameter optimization.
- This is a constrained exit-geometry diagnosis.
- No session/side/filter mining.
- No EA modification.
- No order authorization.

Inputs:
- SQLite M1 broker-feed bars from Stage 6A/6B.
- Stage 7B trade candidates CSV.

Outputs:
- Stage 7D report, summary CSV, and trade-level CSV.

Hard rules:
- Research only.
- Read-only DB.
- No demo/paper/live.
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
from typing import Dict, List, Optional, Sequence, Tuple


TOOL_VERSION = "v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_TRADES = Path("data/reports/stage7b_strategy_redesign_lab/stage7b_strategy_trades.csv")
DEFAULT_OUT_DIR = Path("data/reports/stage7d_exit_geometry_lab")

BASE_COST_USD = 0.35


@dataclass
class M1Bar:
    t: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass
class CandidateEntry:
    family: str
    design: str
    guard_variant: str
    direction: str
    session: str
    entry_utc: datetime
    entry_price: float
    reason: str
    regime_note: str
    macro_labels: str


@dataclass
class Geometry:
    name: str
    tp_usd: float
    sl_usd: float
    horizon_hours: int


@dataclass
class GeometryTrade:
    family: str
    design: str
    guard_variant: str
    geometry: str
    direction: str
    session: str
    entry_utc: str
    entry_price: float
    tp_usd: float
    sl_usd: float
    horizon_hours: int
    exit_utc: str
    exit_price: float
    exit_reason: str
    gross_usd_x1: float
    net_x1: float
    net_x3: float
    net_x4: float
    year: int
    reason: str
    regime_note: str
    macro_labels: str


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
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M"):
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


def connect_ro(db: Path) -> sqlite3.Connection:
    if not db.exists():
        raise FileNotFoundError(f"DB not found: {db}")
    conn = sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True)
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
    out: List[M1Bar] = []
    for r in rows:
        t = parse_time(r["utc_time"])
        if t is None:
            continue
        out.append(M1Bar(t=t, open=float(r["open"]), high=float(r["high"]), low=float(r["low"]), close=float(r["close"])))
    return out


def load_entries(path: Path) -> List[CandidateEntry]:
    if not path.exists():
        raise FileNotFoundError(f"Stage 7B trades CSV not found: {path}. Run Stage 7B first.")
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    rows = list(csv.DictReader(text.splitlines()))
    entries = []
    seen = set()
    for r in rows:
        entry_t = parse_time(r.get("entry_utc"))
        if entry_t is None:
            continue
        key = (r.get("family"), r.get("design"), r.get("guard_variant"), r.get("direction"), entry_t.isoformat())
        if key in seen:
            continue
        seen.add(key)
        entries.append(CandidateEntry(
            family=r.get("family", ""),
            design=r.get("design", ""),
            guard_variant=r.get("guard_variant", ""),
            direction=r.get("direction", "").strip().lower(),
            session=r.get("session", ""),
            entry_utc=entry_t,
            entry_price=safe_float(r.get("entry_price")),
            reason=r.get("reason", ""),
            regime_note=r.get("regime_note", ""),
            macro_labels=r.get("macro_labels", ""),
        ))
    return entries


def default_geometries() -> List[Geometry]:
    # Constrained, pre-defined diagnostic set. Do not expand into a broad optimizer.
    return [
        Geometry("tp10_sl8_h3", 10.0, 8.0, 3),
        Geometry("tp12_sl8_h3", 12.0, 8.0, 3),
        Geometry("tp12_sl10_h6", 12.0, 10.0, 6),
        Geometry("tp15_sl10_h6", 15.0, 10.0, 6),
        Geometry("tp15_sl12_h6", 15.0, 12.0, 6),
        Geometry("tp18_sl12_h12", 18.0, 12.0, 12),
        Geometry("tp18_sl15_h12", 18.0, 15.0, 12),
        Geometry("tp24_sl15_h12_control", 24.0, 15.0, 12),
    ]


def resolve_entry(entry: CandidateEntry, geom: Geometry, m1: Sequence[M1Bar], times: Sequence[datetime]) -> Optional[GeometryTrade]:
    if entry.direction not in {"long", "short"}:
        return None
    si = bisect.bisect_left(times, entry.entry_utc)
    ei = bisect.bisect_left(times, entry.entry_utc + timedelta(hours=geom.horizon_hours))
    if si >= len(m1) or si >= ei:
        return None

    # Use original Stage7B entry_price for comparability; if missing, use M1 open.
    entry_price = entry.entry_price if entry.entry_price > 0 else m1[si].open

    if entry.direction == "long":
        tp_price = entry_price + geom.tp_usd
        sl_price = entry_price - geom.sl_usd
    else:
        tp_price = entry_price - geom.tp_usd
        sl_price = entry_price + geom.sl_usd

    exit_t = None
    exit_price = None
    reason = None

    for b in m1[si:ei]:
        if entry.direction == "long":
            hit_tp = b.high >= tp_price
            hit_sl = b.low <= sl_price
        else:
            hit_tp = b.low <= tp_price
            hit_sl = b.high >= sl_price

        if hit_tp and hit_sl:
            exit_t = b.t
            exit_price = sl_price
            reason = "ambiguous_tp_sl_same_m1_bar_conservative_sl"
            break
        if hit_sl:
            exit_t = b.t
            exit_price = sl_price
            reason = "stop_loss"
            break
        if hit_tp:
            exit_t = b.t
            exit_price = tp_price
            reason = "take_profit"
            break

    if exit_t is None:
        last = m1[ei - 1]
        exit_t = last.t
        exit_price = last.close
        reason = "time_exit"

    gross = (exit_price - entry_price) if entry.direction == "long" else (entry_price - exit_price)

    return GeometryTrade(
        family=entry.family,
        design=entry.design,
        guard_variant=entry.guard_variant,
        geometry=geom.name,
        direction=entry.direction,
        session=entry.session,
        entry_utc=entry.entry_utc.isoformat(),
        entry_price=round(entry_price, 6),
        tp_usd=geom.tp_usd,
        sl_usd=geom.sl_usd,
        horizon_hours=geom.horizon_hours,
        exit_utc=exit_t.isoformat(),
        exit_price=round(exit_price, 6),
        exit_reason=reason,
        gross_usd_x1=round(gross, 6),
        net_x1=round(gross - BASE_COST_USD, 6),
        net_x3=round(gross - 3 * BASE_COST_USD, 6),
        net_x4=round(gross - 4 * BASE_COST_USD, 6),
        year=entry.entry_utc.year,
        reason=entry.reason,
        regime_note=entry.regime_note,
        macro_labels=entry.macro_labels,
    )


def max_drawdown(vals: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    dd = 0.0
    for v in vals:
        equity += v
        peak = max(peak, equity)
        dd = min(dd, equity - peak)
    return round(dd, 6)


def pf(vals: Sequence[float]) -> float:
    wins = sum(v for v in vals if v > 0)
    losses = abs(sum(v for v in vals if v < 0))
    if losses == 0:
        return 999.0 if wins > 0 else 0.0
    return round(wins / losses, 6)


def summarize_group(trades: List[GeometryTrade]) -> dict:
    if not trades:
        return {}
    n1 = [t.net_x1 for t in trades]
    n3 = [t.net_x3 for t in trades]
    n4 = [t.net_x4 for t in trades]

    by_year: Dict[int, float] = {}
    by_session: Dict[str, float] = {}
    by_reason: Dict[str, int] = {}

    for t in trades:
        by_year[t.year] = by_year.get(t.year, 0.0) + t.net_x4
        by_session[t.session] = by_session.get(t.session, 0.0) + t.net_x4
        by_reason[t.exit_reason] = by_reason.get(t.exit_reason, 0) + 1

    total_years = len(by_year)
    positive_years = sum(1 for x in by_year.values() if x > 0)
    total_sessions = len(by_session)
    positive_sessions = sum(1 for x in by_session.values() if x > 0)

    s = {
        "family": trades[0].family,
        "design": trades[0].design,
        "guard_variant": trades[0].guard_variant,
        "geometry": trades[0].geometry,
        "trades": len(trades),
        "total_x1": round(sum(n1), 6),
        "total_x3": round(sum(n3), 6),
        "total_x4": round(sum(n4), 6),
        "pf_x1": pf(n1),
        "pf_x3": pf(n3),
        "pf_x4": pf(n4),
        "median_x1": round(median(n1), 6),
        "median_x4": round(median(n4), 6),
        "win_rate_x1": round(sum(1 for v in n1 if v > 0) / len(n1), 6),
        "win_rate_x4": round(sum(1 for v in n4 if v > 0) / len(n4), 6),
        "max_dd_x1": max_drawdown(n1),
        "max_dd_x4": max_drawdown(n4),
        "positive_years": positive_years,
        "total_years": total_years,
        "positive_sessions": positive_sessions,
        "total_sessions": total_sessions,
        "by_year_x4": {str(k): round(v, 6) for k, v in sorted(by_year.items())},
        "by_session_x4": {k: round(v, 6) for k, v in sorted(by_session.items())},
        "exit_reasons": by_reason,
    }
    s["decision"] = decide(s)
    s["score"] = score(s)
    return s


def decide(s: dict) -> str:
    if s["trades"] < 80:
        return "KILL_TOO_FEW_TRADES"
    if s["total_x4"] <= 0:
        return "KILL_COST_STRESS_X4_NEGATIVE"
    if s["pf_x4"] < 1.08:
        return "KILL_LOW_PF_X4"
    if s["median_x4"] < -3.0:
        return "KILL_BAD_MEDIAN_X4"
    if s["max_dd_x1"] < -550:
        return "KILL_DRAWDOWN_TOO_HIGH"
    if s["positive_years"] < 2:
        return "KILL_YEAR_FRAGILE"
    if s["positive_sessions"] < 2:
        return "KILL_SESSION_CONCENTRATED"
    if s["pf_x4"] >= 1.12 and s["total_x4"] > 250 and s["positive_years"] >= 3 and s["median_x4"] >= -2.0:
        return "PROMISING_FOR_STAGE7E_RESEARCH_ONLY"
    return "WATCHLIST_EXIT_GEOMETRY_RESEARCH_ONLY"


def score(s: dict) -> float:
    return round(
        10.0 * max(0.0, s["pf_x4"] - 1.0)
        + 0.0015 * s["total_x4"]
        + 0.35 * s["positive_years"]
        + 0.15 * s["positive_sessions"]
        - 0.0015 * abs(min(0.0, s["max_dd_x1"]))
        + 0.015 * max(-10.0, s["median_x4"]),
        6,
    )


def run(entries: List[CandidateEntry], m1: List[M1Bar], geometries: List[Geometry]) -> Tuple[List[GeometryTrade], List[dict]]:
    times = [b.t for b in m1]
    all_trades: List[GeometryTrade] = []
    for entry in entries:
        for geom in geometries:
            t = resolve_entry(entry, geom, m1, times)
            if t is not None:
                all_trades.append(t)

    groups: Dict[Tuple[str, str, str, str], List[GeometryTrade]] = {}
    for t in all_trades:
        groups.setdefault((t.family, t.design, t.guard_variant, t.geometry), []).append(t)

    summaries = [summarize_group(v) for k, v in sorted(groups.items())]
    summaries.sort(
        key=lambda s: (
            s["decision"].startswith("PROMISING"),
            s["decision"].startswith("WATCHLIST"),
            s["score"],
            s["pf_x4"],
            s["total_x4"],
        ),
        reverse=True,
    )
    return all_trades, summaries


def write_outputs(out_dir: Path, payload: dict, trades: List[GeometryTrade], summaries: List[dict]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload["summaries"] = summaries
    (out_dir / "stage7d_exit_geometry_lab.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    if trades:
        with (out_dir / "stage7d_exit_geometry_trades.csv").open("w", newline="", encoding="utf-8") as f:
            cols = list(asdict(trades[0]).keys())
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for t in trades:
                w.writerow(asdict(t))

    cols = [
        "family", "design", "guard_variant", "geometry", "decision", "score", "trades",
        "total_x1", "total_x3", "total_x4", "pf_x1", "pf_x3", "pf_x4",
        "median_x1", "median_x4", "win_rate_x1", "win_rate_x4",
        "max_dd_x1", "max_dd_x4", "positive_years", "total_years", "positive_sessions", "total_sessions",
    ]
    with (out_dir / "stage7d_exit_geometry_summaries.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for s in summaries:
            w.writerow({c: s.get(c) for c in cols})

    lines = [
        "# Stage 7D Exit Geometry Lab",
        "",
        f"Generated UTC: `{payload['generated_utc']}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: research only. This does not authorize demo, paper, or live orders.",
        "",
        "## Inputs",
        f"- db: `{payload['db_path']}`",
        f"- trades_csv: `{payload['trades_csv']}`",
        f"- m1_rows: `{payload['m1_rows']}`",
        f"- entries_loaded: `{payload['entries_loaded']}`",
        f"- geometries: `{payload['geometries']}`",
        "",
        "## Ranking",
        "| Family | Design | Guard | Geometry | Decision | Score | Trades | Total x4 | PF x4 | Median x4 | DD x1 | Pos years | Pos sessions |",
        "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in summaries:
        lines.append(
            f"| {s['family']} | {s['design']} | {s['guard_variant']} | {s['geometry']} | {s['decision']} | "
            f"{s['score']} | {s['trades']} | {s['total_x4']} | {s['pf_x4']} | {s['median_x4']} | "
            f"{s['max_dd_x1']} | {s['positive_years']}/{s['total_years']} | {s['positive_sessions']}/{s['total_sessions']} |"
        )

    lines += [
        "",
        "## Interpretation",
        "- This is a constrained exit-geometry test, not parameter optimization.",
        "- If no geometry reaches WATCHLIST/PROMISING, entries are not commercially sufficient in this mechanical form.",
        "- If one geometry improves x4 cost performance and robustness, it becomes a Stage 7E validation candidate only.",
        "",
        "## Decision",
        "- Do not modify EA from Stage 7D alone.",
        "- Do not use session/side filters to rescue weak geometries.",
        "- Candidate must pass Stage 7E robustness before any locked strategy proposal.",
    ]
    (out_dir / "stage7d_exit_geometry_lab.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--trades-csv", default=str(DEFAULT_TRADES))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = p.parse_args()

    conn = connect_ro(Path(args.db))
    m1 = load_m1(conn)
    conn.close()
    entries = load_entries(Path(args.trades_csv))
    geometries = default_geometries()
    trades, summaries = run(entries, m1, geometries)

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": now_iso(),
        "db_path": str(Path(args.db)),
        "trades_csv": str(Path(args.trades_csv)),
        "m1_rows": len(m1),
        "entries_loaded": len(entries),
        "geometries": [asdict(g) for g in geometries],
    }
    write_outputs(Path(args.out_dir), payload, trades, summaries)

    print("Stage 7D exit geometry lab: DONE")
    print(f"entries_loaded={len(entries)} geometries={len(geometries)} trades_simulated={len(trades)}")
    print(f"Report: {Path(args.out_dir) / 'stage7d_exit_geometry_lab.md'}")
    print(f"Summary CSV: {Path(args.out_dir) / 'stage7d_exit_geometry_summaries.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
