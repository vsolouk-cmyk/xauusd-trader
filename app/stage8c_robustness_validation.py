#!/usr/bin/env python3
"""
Stage 8C — Robustness Validation for Stage 8B Thesis Candidates

Purpose:
- Validate Stage 8B promising candidates before any locked-strategy/EA proposal.
- Focus on non-overlap candidates as execution-realistic basis.
- Diagnose hidden risk in time_exit_12h candidates, especially absence of hard SL.
- Apply robustness checks:
  - year-by-year
  - half-split chronology
  - quarter/month stress
  - cost x1/x3/x4/x6
  - emergency stop replay on existing non-overlap candidate sequence
  - realized drawdown and worst-streak diagnostics

Hard rules:
- Research only.
- Reads Stage 8B trade CSV and local SQLite M1 bars.
- No EA modification.
- No order sending.
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
from typing import Dict, List, Optional, Sequence, Tuple


TOOL_VERSION = "v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_TRADES = Path("data/reports/stage8b_single_regime_thesis_lab/stage8b_single_regime_trades.csv")
DEFAULT_SUMMARIES = Path("data/reports/stage8b_single_regime_thesis_lab/stage8b_single_regime_summaries.csv")
DEFAULT_OUT_DIR = Path("data/reports/stage8c_robustness_validation")

BASE_COST_USD = 0.35


@dataclass
class M1Bar:
    t: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass
class Trade:
    thesis_id: str
    definition: str
    guard_variant: str
    geometry: str
    signal_utc: datetime
    entry_utc: datetime
    direction: str
    session: str
    entry_price: float
    exit_utc: datetime
    exit_price: float
    exit_reason: str
    gross_usd_x1: float
    net_x1: float
    net_x3: float
    net_x4: float
    year: int
    h1_trend: str
    h4_trend: str
    compression_bucket: str
    vol_bucket: str
    macro_labels: str


@dataclass
class StressTrade:
    key: str
    emergency_stop_usd: str
    thesis_id: str
    definition: str
    guard_variant: str
    geometry: str
    signal_utc: str
    entry_utc: str
    direction: str
    session: str
    entry_price: float
    exit_utc: str
    exit_price: float
    exit_reason: str
    gross: float
    net_x1: float
    net_x3: float
    net_x4: float
    net_x6: float
    year: int
    month: str
    quarter: str


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
    out: List[M1Bar] = []
    for r in rows:
        t = parse_time(r["utc_time"])
        if t is None:
            continue
        out.append(M1Bar(t=t, open=float(r["open"]), high=float(r["high"]), low=float(r["low"]), close=float(r["close"])))
    return out


def load_trades(path: Path) -> List[Trade]:
    if not path.exists():
        raise FileNotFoundError(f"Stage 8B trades CSV not found: {path}. Run Stage 8B first.")
    rows = list(csv.DictReader(path.read_text(encoding="utf-8-sig", errors="replace").splitlines()))
    out = []
    for r in rows:
        signal_t = parse_time(r.get("signal_utc"))
        entry_t = parse_time(r.get("entry_utc"))
        exit_t = parse_time(r.get("exit_utc"))
        if signal_t is None or entry_t is None or exit_t is None:
            continue
        out.append(Trade(
            thesis_id=r.get("thesis_id", ""),
            definition=r.get("definition", ""),
            guard_variant=r.get("guard_variant", ""),
            geometry=r.get("geometry", ""),
            signal_utc=signal_t,
            entry_utc=entry_t,
            direction=r.get("direction", "long"),
            session=r.get("session", ""),
            entry_price=safe_float(r.get("entry_price")),
            exit_utc=exit_t,
            exit_price=safe_float(r.get("exit_price")),
            exit_reason=r.get("exit_reason", ""),
            gross_usd_x1=safe_float(r.get("gross_usd_x1")),
            net_x1=safe_float(r.get("net_x1")),
            net_x3=safe_float(r.get("net_x3")),
            net_x4=safe_float(r.get("net_x4")),
            year=int(safe_float(r.get("year"), 0)),
            h1_trend=r.get("h1_trend", ""),
            h4_trend=r.get("h4_trend", ""),
            compression_bucket=r.get("compression_bucket", ""),
            vol_bucket=r.get("vol_bucket", ""),
            macro_labels=r.get("macro_labels", ""),
        ))
    return out


def load_promising_summary_keys(path: Path, only_nonoverlap: bool = True) -> List[Tuple[str, str, str]]:
    """
    Returns (definition, guard_variant, geometry) from Stage 8B summaries.
    """
    if not path.exists():
        return []
    rows = list(csv.DictReader(path.read_text(encoding="utf-8-sig", errors="replace").splitlines()))
    keys = []
    for r in rows:
        decision = r.get("decision", "")
        guard = r.get("guard_variant", "")
        if "PROMISING_FOR_STAGE8C" not in decision:
            continue
        if only_nonoverlap and "nonoverlap" not in guard:
            continue
        keys.append((r.get("definition", ""), guard, r.get("geometry", "")))
    # preserve order / unique
    out = []
    seen = set()
    for k in keys:
        if k not in seen:
            out.append(k)
            seen.add(k)
    return out


def quarter_key(t: datetime) -> str:
    q = (t.month - 1) // 3 + 1
    return f"{t.year}-Q{q}"


def month_key(t: datetime) -> str:
    return f"{t.year}-{t.month:02d}"


def net_with_cost(gross: float, cost_mult: int) -> float:
    return round(gross - BASE_COST_USD * cost_mult, 6)


def max_drawdown(vals: Sequence[float]) -> float:
    eq = 0.0
    peak = 0.0
    dd = 0.0
    for v in vals:
        eq += v
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return round(dd, 6)


def pf(vals: Sequence[float]) -> float:
    wins = sum(v for v in vals if v > 0)
    losses = abs(sum(v for v in vals if v < 0))
    if losses == 0:
        return 999.0 if wins > 0 else 0.0
    return round(wins / losses, 6)


def worst_losing_streak(vals: Sequence[float]) -> int:
    cur = 0
    worst = 0
    for v in vals:
        if v < 0:
            cur += 1
            worst = max(worst, cur)
        else:
            cur = 0
    return worst


def group_sum(vals: Sequence[StressTrade], attr: str, net_attr: str) -> Dict[str, dict]:
    out: Dict[str, List[float]] = {}
    for t in vals:
        k = getattr(t, attr)
        out.setdefault(k, []).append(getattr(t, net_attr))
    return {
        k: {
            "trades": len(v),
            "total": round(sum(v), 6),
            "median": round(median(v), 6) if v else 0.0,
            "pf": pf(v),
            "max_dd": max_drawdown(v),
        }
        for k, v in sorted(out.items())
    }


def first_stop_hit(entry: float, direction: str, path: Sequence[M1Bar], stop_usd: float) -> Optional[Tuple[datetime, float]]:
    if stop_usd <= 0:
        return None
    if direction == "long":
        stop = entry - stop_usd
        for b in path:
            if b.low <= stop:
                return b.t, stop
    else:
        stop = entry + stop_usd
        for b in path:
            if b.high >= stop:
                return b.t, stop
    return None


def stress_replay(trades: Sequence[Trade], m1: Sequence[M1Bar], emergency_stop: Optional[float]) -> List[StressTrade]:
    """
    Conservative replay on the already selected candidate sequence.
    It does not re-open additional trades if emergency stop closes earlier.
    This is intentional for robustness/risk diagnosis, not execution optimization.
    """
    times = [b.t for b in m1]
    out: List[StressTrade] = []

    for tr in trades:
        si = bisect.bisect_left(times, tr.entry_utc)
        ei = bisect.bisect_right(times, tr.exit_utc)
        if si >= len(m1) or si >= ei:
            continue
        path = m1[si:ei]
        exit_t = tr.exit_utc
        exit_price = tr.exit_price
        reason = tr.exit_reason

        if emergency_stop is not None:
            hit = first_stop_hit(tr.entry_price, tr.direction, path, emergency_stop)
            if hit is not None and hit[0] <= exit_t:
                exit_t, exit_price = hit
                reason = f"emergency_stop_{emergency_stop:g}"

        gross = exit_price - tr.entry_price if tr.direction == "long" else tr.entry_price - exit_price
        key = f"{tr.definition}|{tr.guard_variant}|{tr.geometry}"
        out.append(StressTrade(
            key=key,
            emergency_stop_usd="none" if emergency_stop is None else f"{emergency_stop:g}",
            thesis_id=tr.thesis_id,
            definition=tr.definition,
            guard_variant=tr.guard_variant,
            geometry=tr.geometry,
            signal_utc=tr.signal_utc.isoformat(),
            entry_utc=tr.entry_utc.isoformat(),
            direction=tr.direction,
            session=tr.session,
            entry_price=round(tr.entry_price, 6),
            exit_utc=exit_t.isoformat(),
            exit_price=round(exit_price, 6),
            exit_reason=reason,
            gross=round(gross, 6),
            net_x1=net_with_cost(gross, 1),
            net_x3=net_with_cost(gross, 3),
            net_x4=net_with_cost(gross, 4),
            net_x6=net_with_cost(gross, 6),
            year=exit_t.year,
            month=month_key(exit_t),
            quarter=quarter_key(exit_t),
        ))
    return out


def summarize_stress(trades: Sequence[StressTrade]) -> dict:
    if not trades:
        return {}
    n1 = [t.net_x1 for t in trades]
    n4 = [t.net_x4 for t in trades]
    n6 = [t.net_x6 for t in trades]

    by_year = group_sum(trades, "year", "net_x4")
    by_quarter = group_sum(trades, "quarter", "net_x4")
    by_month = group_sum(trades, "month", "net_x4")
    by_session = group_sum(trades, "session", "net_x4")

    positive_years = sum(1 for v in by_year.values() if v["total"] > 0)
    positive_quarters = sum(1 for v in by_quarter.values() if v["total"] > 0)
    positive_months = sum(1 for v in by_month.values() if v["total"] > 0)
    positive_sessions = sum(1 for v in by_session.values() if v["total"] > 0)

    s = {
        "key": trades[0].key,
        "definition": trades[0].definition,
        "guard_variant": trades[0].guard_variant,
        "geometry": trades[0].geometry,
        "emergency_stop_usd": trades[0].emergency_stop_usd,
        "trades": len(trades),
        "total_x1": round(sum(n1), 6),
        "total_x4": round(sum(n4), 6),
        "total_x6": round(sum(n6), 6),
        "pf_x1": pf(n1),
        "pf_x4": pf(n4),
        "pf_x6": pf(n6),
        "median_x1": round(median(n1), 6),
        "median_x4": round(median(n4), 6),
        "win_rate_x4": round(sum(1 for x in n4 if x > 0) / len(n4), 6),
        "max_dd_x1": max_drawdown(n1),
        "max_dd_x4": max_drawdown(n4),
        "worst_losing_streak_x4": worst_losing_streak(n4),
        "positive_years": positive_years,
        "total_years": len(by_year),
        "positive_quarters": positive_quarters,
        "total_quarters": len(by_quarter),
        "positive_months": positive_months,
        "total_months": len(by_month),
        "positive_sessions": positive_sessions,
        "total_sessions": len(by_session),
        "worst_year_x4": min((v["total"] for v in by_year.values()), default=0.0),
        "worst_quarter_x4": min((v["total"] for v in by_quarter.values()), default=0.0),
        "worst_month_x4": min((v["total"] for v in by_month.values()), default=0.0),
        "by_year_x4": by_year,
        "by_quarter_x4": by_quarter,
        "by_session_x4": by_session,
    }
    s["decision"] = decide(s)
    s["score"] = score(s)
    return s


def decide(s: dict) -> str:
    if s["trades"] < 120:
        return "KILL_TOO_FEW_TRADES"
    if s["total_x6"] <= 0:
        return "KILL_COST_X6_NEGATIVE"
    if s["pf_x4"] < 1.20:
        return "KILL_LOW_PF_X4"
    if s["median_x4"] <= 0:
        return "KILL_NONPOSITIVE_MEDIAN_X4"
    if s["max_dd_x1"] < -250:
        return "KILL_DRAWDOWN_TOO_HIGH"
    if s["positive_years"] < 4:
        return "KILL_YEAR_FRAGILE"
    if s["positive_quarters"] / max(1, s["total_quarters"]) < 0.55:
        return "KILL_QUARTER_FRAGILE"
    if s["worst_month_x4"] < -160:
        return "KILL_WORST_MONTH_TOO_DEEP"
    if s["positive_sessions"] < min(2, s["total_sessions"]):
        return "KILL_SESSION_FRAGILE"
    if s["pf_x4"] >= 1.45 and s["median_x4"] > 0.75 and s["max_dd_x1"] > -225 and s["positive_years"] >= 4:
        return "PASS_STAGE8C_RESEARCH_ONLY"
    return "WATCHLIST_STAGE8C_RESEARCH_ONLY"


def score(s: dict) -> float:
    return round(
        10.0 * max(0.0, s["pf_x4"] - 1.0)
        + 0.001 * s["total_x4"]
        + 0.7 * s["median_x4"]
        + 0.35 * s["positive_years"]
        + 0.04 * s["positive_quarters"]
        - 0.003 * abs(min(0, s["max_dd_x1"]))
        - 0.002 * abs(min(0, s["worst_month_x4"])),
        6,
    )


def run_validation(trades: List[Trade], selected_keys: List[Tuple[str, str, str]], m1: List[M1Bar], emergency_stops: Sequence[Optional[float]]) -> Tuple[List[StressTrade], List[dict]]:
    all_stress: List[StressTrade] = []
    summaries: List[dict] = []

    for definition, guard, geometry in selected_keys:
        selected = [
            t for t in trades
            if t.definition == definition and t.guard_variant == guard and t.geometry == geometry
        ]
        if not selected:
            continue
        selected = sorted(selected, key=lambda t: t.entry_utc)
        for stop in emergency_stops:
            stress = stress_replay(selected, m1, stop)
            all_stress.extend(stress)
            s = summarize_stress(stress)
            if s:
                summaries.append(s)

    summaries.sort(
        key=lambda s: (
            s["decision"] == "PASS_STAGE8C_RESEARCH_ONLY",
            s["decision"].startswith("WATCHLIST"),
            s["score"],
            s["pf_x4"],
            s["total_x4"],
        ),
        reverse=True,
    )
    return all_stress, summaries


def write_outputs(out_dir: Path, payload: dict, stress_trades: List[StressTrade], summaries: List[dict]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload["summaries"] = summaries
    (out_dir / "stage8c_robustness_validation.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    if stress_trades:
        with (out_dir / "stage8c_stress_trades.csv").open("w", newline="", encoding="utf-8") as f:
            cols = list(asdict(stress_trades[0]).keys())
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for t in stress_trades:
                w.writerow(asdict(t))

    cols = [
        "definition", "guard_variant", "geometry", "emergency_stop_usd",
        "decision", "score", "trades", "total_x1", "total_x4", "total_x6",
        "pf_x1", "pf_x4", "pf_x6", "median_x1", "median_x4", "win_rate_x4",
        "max_dd_x1", "max_dd_x4", "worst_losing_streak_x4",
        "positive_years", "total_years", "positive_quarters", "total_quarters",
        "positive_months", "total_months", "positive_sessions", "total_sessions",
        "worst_year_x4", "worst_quarter_x4", "worst_month_x4",
    ]
    with (out_dir / "stage8c_robustness_summaries.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for s in summaries:
            w.writerow({c: s.get(c) for c in cols})

    lines = [
        "# Stage 8C Robustness Validation",
        "",
        f"Generated UTC: `{payload['generated_utc']}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: research only. This does not authorize demo, paper, or live orders.",
        "",
        "## Inputs",
        f"- db: `{payload['db_path']}`",
        f"- trades_csv: `{payload['trades_csv']}`",
        f"- summaries_csv: `{payload['summaries_csv']}`",
        f"- m1_rows: `{payload['m1_rows']}`",
        f"- stage8b_trades_loaded: `{payload['stage8b_trades_loaded']}`",
        f"- selected_candidate_keys: `{payload['selected_candidate_keys']}`",
        f"- emergency_stops: `{payload['emergency_stops']}`",
        "",
        "## Ranking",
        "| Definition | Guard | Geometry | Emergency SL | Decision | Score | Trades | Total x4 | Total x6 | PF x4 | Median x4 | DD x1 | Pos years | Pos quarters | Worst month |",
        "|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for s in summaries:
        lines.append(
            f"| {s['definition']} | {s['guard_variant']} | {s['geometry']} | {s['emergency_stop_usd']} | "
            f"{s['decision']} | {s['score']} | {s['trades']} | {s['total_x4']} | {s['total_x6']} | "
            f"{s['pf_x4']} | {s['median_x4']} | {s['max_dd_x1']} | "
            f"{s['positive_years']}/{s['total_years']} | {s['positive_quarters']}/{s['total_quarters']} | {s['worst_month_x4']} |"
        )

    lines += [
        "",
        "## Interpretation",
        "- `PASS_STAGE8C_RESEARCH_ONLY`: candidate can move to Stage 8D forward-shadow design, not orders.",
        "- `WATCHLIST_STAGE8C_RESEARCH_ONLY`: promising but needs one focused risk-design revision.",
        "- `KILL_*`: do not rescue by filter mining.",
        "- `emergency_stop_usd=none` for `time_exit_12h` is diagnostic only, not a deployable risk model.",
        "",
        "## Decision",
        "- No EA change is allowed from Stage 8C alone.",
        "- Any future locked strategy must use non-overlap execution basis.",
        "- If the best candidate only passes without an emergency stop, Stage 8D must design an operational risk guard before EA changes.",
    ]
    (out_dir / "stage8c_robustness_validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--trades-csv", default=str(DEFAULT_TRADES))
    p.add_argument("--summaries-csv", default=str(DEFAULT_SUMMARIES))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--include-overlap", action="store_true", help="Include overlap candidates too. Default validates non-overlap only.")
    p.add_argument("--emergency-stops", default="none,20,25,30", help="Comma-separated emergency stop USD values; use none for no stop")
    args = p.parse_args()

    conn = connect_ro(Path(args.db))
    m1 = load_m1(conn)
    conn.close()

    trades = load_trades(Path(args.trades_csv))
    keys = load_promising_summary_keys(Path(args.summaries_csv), only_nonoverlap=(not args.include_overlap))
    if not keys:
        raise RuntimeError("No Stage 8B promising candidate keys found. Run Stage 8B first.")

    stops: List[Optional[float]] = []
    for x in args.emergency_stops.split(","):
        x = x.strip().lower()
        if not x:
            continue
        if x == "none":
            stops.append(None)
        else:
            stops.append(float(x))

    stress_trades, summaries = run_validation(trades, keys, m1, stops)
    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": now_iso(),
        "db_path": str(Path(args.db)),
        "trades_csv": str(Path(args.trades_csv)),
        "summaries_csv": str(Path(args.summaries_csv)),
        "m1_rows": len(m1),
        "stage8b_trades_loaded": len(trades),
        "selected_candidate_keys": [list(k) for k in keys],
        "emergency_stops": ["none" if s is None else s for s in stops],
    }
    write_outputs(Path(args.out_dir), payload, stress_trades, summaries)

    print("Stage 8C robustness validation: DONE")
    print(f"stage8b_trades_loaded={len(trades)} selected_candidates={len(keys)} stress_trades={len(stress_trades)}")
    print(f"Report: {Path(args.out_dir) / 'stage8c_robustness_validation.md'}")
    print(f"Summary CSV: {Path(args.out_dir) / 'stage8c_robustness_summaries.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
