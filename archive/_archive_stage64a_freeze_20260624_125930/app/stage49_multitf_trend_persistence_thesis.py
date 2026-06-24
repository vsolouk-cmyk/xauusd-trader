#!/usr/bin/env python3
"""
Stage49 Broker-Real Multi-Timeframe Trend Persistence Thesis

A cost-aware, broker-real diagnostic thesis that is deliberately different from
Stage47/48 liquidity-sweep reversal. It tests whether H1 range-expansion bars,
confirmed by M15/M5 trend alignment and spread regime gates, have forward
persistence on AMarkets XAUUSD M5.

Diagnostic only: no EA, no paper-live, no live, no promotion.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


def parse_dt(s: str) -> Optional[datetime]:
    if not s:
        return None
    x = s.strip()
    if x.endswith("Z"):
        x = x[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(x)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_float(x) -> Optional[float]:
    if x is None:
        return None
    try:
        v = float(str(x).strip())
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def percentile(values: Sequence[float], q: float) -> Optional[float]:
    vals = sorted(v for v in values if v is not None and math.isfinite(v))
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    pos = (len(vals) - 1) * (q / 100.0)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return vals[lo]
    return vals[lo] * (hi - pos) + vals[hi] * (pos - lo)


def t_stat(vals: Sequence[float]) -> float:
    xs = [v for v in vals if math.isfinite(v)]
    if len(xs) < 2:
        return 0.0
    sd = pstdev(xs)
    if sd <= 1e-12:
        return 0.0
    return mean(xs) / (sd / math.sqrt(len(xs)))


def max_drawdown(vals: Sequence[float]) -> float:
    cum = 0.0
    peak = 0.0
    mdd = 0.0
    for v in vals:
        cum += v
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)
    return mdd


def infer_session(dt: datetime) -> str:
    h = dt.hour
    if 0 <= h < 7:
        return "asia"
    if 7 <= h < 12:
        return "london"
    if 12 <= h < 16:
        return "london_ny_overlap"
    if 16 <= h < 21:
        return "new_york"
    return "late_us"


@dataclass
class Bar:
    dt: datetime
    time_utc: str
    open: float
    high: float
    low: float
    close: float
    spread_points: Optional[float]
    spread_cost_bps: Optional[float]
    tick_volume: Optional[float]


@dataclass
class CandidateResult:
    candidate_id: str
    h1_range_window: int
    h1_range_percentile: float
    m15_sma_window: int
    m5_sma_window: int
    horizon_m5_bars: int
    max_spread_cost_bps: float
    trade_count: int
    is_trade_count: int
    oos_trade_count: int
    stress_mean_bps: float
    stress_median_bps: float
    stress_win_rate: float
    stress_t_stat: float
    stress_total_bps: float
    stress_max_drawdown_bps: float
    is_stress_mean_bps: float
    is_stress_win_rate: float
    oos_stress_mean_bps: float
    oos_stress_win_rate: float
    positive_year_count: int
    negative_year_count: int
    max_year_share: float
    decision: str
    notes: str


def load_bars_from_sqlite(db_path: Path, timeframe: str) -> List[Bar]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT time_utc, open, high, low, close, spread_points, spread_cost_bps, tick_volume
            FROM amarkets_bars
            WHERE timeframe = ?
            ORDER BY time_utc
            """,
            (timeframe,),
        ).fetchall()
    finally:
        conn.close()
    out: List[Bar] = []
    for r in rows:
        dt = parse_dt(r["time_utc"])
        if not dt:
            continue
        out.append(Bar(
            dt=dt,
            time_utc=iso(dt),
            open=float(r["open"]),
            high=float(r["high"]),
            low=float(r["low"]),
            close=float(r["close"]),
            spread_points=safe_float(r["spread_points"]),
            spread_cost_bps=safe_float(r["spread_cost_bps"]),
            tick_volume=safe_float(r["tick_volume"]),
        ))
    return out


def load_bars_from_csv(path: Path) -> List[Bar]:
    if not path.exists():
        return []
    out: List[Bar] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            dt = parse_dt(r.get("time_utc", ""))
            if not dt:
                continue
            o = safe_float(r.get("open")); h = safe_float(r.get("high")); l = safe_float(r.get("low")); c = safe_float(r.get("close"))
            if o is None or h is None or l is None or c is None:
                continue
            out.append(Bar(
                dt=dt, time_utc=iso(dt), open=o, high=h, low=l, close=c,
                spread_points=safe_float(r.get("spread_points")),
                spread_cost_bps=safe_float(r.get("spread_cost_bps")),
                tick_volume=safe_float(r.get("tick_volume")),
            ))
    return sorted(out, key=lambda b: b.dt)


def load_tf(root: Path, timeframe: str, db_path: Optional[Path]) -> List[Bar]:
    if db_path:
        bars = load_bars_from_sqlite(db_path, timeframe)
        if bars:
            return bars
    csv_path = root / "data" / "broker_normalized" / "amarkets" / f"amarkets_xauusd_{timeframe.lower()}_normalized.csv"
    return load_bars_from_csv(csv_path)


def rolling_sma(values: List[float], window: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    if window <= 0:
        return out
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= window:
            s -= values[i - window]
        if i >= window - 1:
            out[i] = s / window
    return out


def prior_percentile_rank(history: List[float], value: float) -> Optional[float]:
    vals = [x for x in history if math.isfinite(x)]
    if len(vals) < 20:
        return None
    le = sum(1 for x in vals if x <= value)
    return 100.0 * le / len(vals)


def build_index(bars: List[Bar]) -> Dict[str, int]:
    return {b.time_utc: i for i, b in enumerate(bars)}


def floor_to_minutes(dt: datetime, minutes: int) -> datetime:
    minute = (dt.minute // minutes) * minutes
    return dt.replace(minute=minute, second=0, microsecond=0)


def find_latest_index_leq(bars: List[Bar], target: datetime) -> Optional[int]:
    # Efficient enough for this diagnostic with monotonic pointer handled externally in evaluate.
    lo, hi = 0, len(bars) - 1
    ans = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if bars[mid].dt <= target:
            ans = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return ans


def load_cost_model(path: Path) -> Dict[str, float]:
    defaults = {"stress_cost_bps": 3.0, "recommended_cost_bps": 3.0, "extreme_cost_bps": 3.1}
    if not path.exists():
        return defaults
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return defaults
    return {
        "stress_cost_bps": float(data.get("stress_cost_bps", defaults["stress_cost_bps"])),
        "recommended_cost_bps": float(data.get("recommended_cost_bps", defaults["recommended_cost_bps"])),
        "extreme_cost_bps": float(data.get("extreme_cost_bps", defaults["extreme_cost_bps"])),
    }


def evaluate_candidate(
    *,
    m5: List[Bar],
    m15: List[Bar],
    h1: List[Bar],
    h1_range_window: int,
    h1_range_percentile: float,
    m15_sma_window: int,
    m5_sma_window: int,
    horizon_m5_bars: int,
    max_spread_cost_bps: float,
    stress_cost_bps: float,
) -> Tuple[CandidateResult, List[Dict[str, object]]]:
    m5_closes = [b.close for b in m5]
    m15_closes = [b.close for b in m15]
    m5_sma = rolling_sma(m5_closes, m5_sma_window)
    m15_sma = rolling_sma(m15_closes, m15_sma_window)
    h1_ranges_bps = [((b.high - b.low) / b.close) * 10000.0 if b.close else 0.0 for b in h1]

    events: List[Dict[str, object]] = []
    used_entry_times = set()

    for hi in range(max(h1_range_window, 5), len(h1) - 1):
        hbar = h1[hi]
        hist = h1_ranges_bps[max(0, hi - h1_range_window):hi]
        rank = prior_percentile_rank(hist, h1_ranges_bps[hi])
        if rank is None or rank < h1_range_percentile:
            continue
        direction = 1 if hbar.close > hbar.open else -1 if hbar.close < hbar.open else 0
        if direction == 0:
            continue
        # Enter at the first M5 bar after the H1 bar closes.
        entry_target = hbar.dt
        mi = find_latest_index_leq(m5, entry_target)
        if mi is None:
            continue
        # If m5[mi] is <= target, move to first strictly after H1 timestamp when possible.
        while mi < len(m5) and m5[mi].dt <= entry_target:
            mi += 1
        if mi <= 0 or mi + horizon_m5_bars >= len(m5):
            continue
        entry = m5[mi]
        if entry.time_utc in used_entry_times:
            continue
        used_entry_times.add(entry.time_utc)
        if entry.spread_cost_bps is None or entry.spread_cost_bps > max_spread_cost_bps:
            continue
        m15_idx = find_latest_index_leq(m15, entry.dt)
        if m15_idx is None or m15_idx <= 0 or m15_sma[m15_idx] is None or m5_sma[mi] is None:
            continue
        m15_aligned = m15[m15_idx].close > float(m15_sma[m15_idx]) if direction > 0 else m15[m15_idx].close < float(m15_sma[m15_idx])
        m5_aligned = entry.close > float(m5_sma[mi]) if direction > 0 else entry.close < float(m5_sma[mi])
        if not (m15_aligned and m5_aligned):
            continue
        exit_bar = m5[mi + horizon_m5_bars]
        gross_bps = direction * ((exit_bar.close - entry.close) / entry.close) * 10000.0
        # Use Stage48F stress cost as round-trip cost floor; entry spread gate remains separate.
        stress_net_bps = gross_bps - stress_cost_bps
        events.append({
            "candidate_id": "",
            "entry_time_utc": entry.time_utc,
            "exit_time_utc": exit_bar.time_utc,
            "direction": "LONG" if direction > 0 else "SHORT",
            "entry_price": entry.close,
            "exit_price": exit_bar.close,
            "gross_bps": gross_bps,
            "stress_cost_bps": stress_cost_bps,
            "stress_net_bps": stress_net_bps,
            "h1_time_utc": hbar.time_utc,
            "h1_range_bps": h1_ranges_bps[hi],
            "h1_range_percentile_rank": rank,
            "entry_spread_cost_bps": entry.spread_cost_bps,
            "session_utc": infer_session(entry.dt),
            "year": entry.dt.year,
        })

    cid = f"S49_MTF_H1W{h1_range_window}_P{int(h1_range_percentile)}_M15S{m15_sma_window}_M5S{m5_sma_window}_H{horizon_m5_bars}"
    for e in events:
        e["candidate_id"] = cid
    vals = [float(e["stress_net_bps"]) for e in events]
    split = int(len(events) * 0.8)
    is_vals = vals[:split]
    oos_vals = vals[split:]
    year_counts: Dict[int, int] = defaultdict(int)
    year_mean: Dict[int, List[float]] = defaultdict(list)
    for e in events:
        y = int(e["year"])
        year_counts[y] += 1
        year_mean[y].append(float(e["stress_net_bps"]))
    positive_year_count = sum(1 for xs in year_mean.values() if xs and mean(xs) > 0)
    negative_year_count = sum(1 for xs in year_mean.values() if xs and mean(xs) <= 0)
    max_year_share = max(year_counts.values()) / len(events) if events and year_counts else 0.0

    notes = []
    if len(events) < 300:
        notes.append("trade_count_lt_300")
    if len(oos_vals) < 50:
        notes.append("oos_trade_count_lt_50")
    if not vals or mean(vals) <= 0:
        notes.append("stress_mean_not_positive")
    if not oos_vals or mean(oos_vals) <= 0:
        notes.append("oos_stress_mean_not_positive")
    if oos_vals and (sum(1 for v in oos_vals if v > 0) / len(oos_vals)) < 0.52:
        notes.append("oos_stress_win_rate_lt_52pct")
    if max_year_share > 0.55:
        notes.append("year_concentration_gt_55pct")
    if positive_year_count < 2 and len(year_mean) >= 3:
        notes.append("positive_year_count_lt_2")
    decision = "DIAGNOSTIC_SURVIVOR_NEEDS_HARD_AUDIT" if not notes else "NO_PASS"

    result = CandidateResult(
        candidate_id=cid,
        h1_range_window=h1_range_window,
        h1_range_percentile=h1_range_percentile,
        m15_sma_window=m15_sma_window,
        m5_sma_window=m5_sma_window,
        horizon_m5_bars=horizon_m5_bars,
        max_spread_cost_bps=max_spread_cost_bps,
        trade_count=len(events),
        is_trade_count=len(is_vals),
        oos_trade_count=len(oos_vals),
        stress_mean_bps=mean(vals) if vals else 0.0,
        stress_median_bps=median(vals) if vals else 0.0,
        stress_win_rate=(sum(1 for v in vals if v > 0) / len(vals)) if vals else 0.0,
        stress_t_stat=t_stat(vals),
        stress_total_bps=sum(vals) if vals else 0.0,
        stress_max_drawdown_bps=max_drawdown(vals) if vals else 0.0,
        is_stress_mean_bps=mean(is_vals) if is_vals else 0.0,
        is_stress_win_rate=(sum(1 for v in is_vals if v > 0) / len(is_vals)) if is_vals else 0.0,
        oos_stress_mean_bps=mean(oos_vals) if oos_vals else 0.0,
        oos_stress_win_rate=(sum(1 for v in oos_vals if v > 0) / len(oos_vals)) if oos_vals else 0.0,
        positive_year_count=positive_year_count,
        negative_year_count=negative_year_count,
        max_year_share=max_year_share,
        decision=decision,
        notes=";".join(notes),
    )
    return result, events


def write_csv(path: Path, rows: List[Dict[str, object]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run Stage49 broker-real multi-timeframe trend persistence diagnostic thesis.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--db", default="data/broker_normalized/amarkets_multitf.sqlite")
    parser.add_argument("--cost-model", default="reports/stage48f/stage48f_cost_model.json")
    parser.add_argument("--out", default="reports/stage49_broker_multitf")
    parser.add_argument("--max-spread-cost-bps", type=float, default=None, help="Optional entry spread gate. Default uses extreme_cost_bps from cost model.")
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    out_dir = root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = root / args.db if not Path(args.db).is_absolute() else Path(args.db)
    cost_model = load_cost_model(root / args.cost_model if not Path(args.cost_model).is_absolute() else Path(args.cost_model))
    stress_cost_bps = float(cost_model["stress_cost_bps"])
    max_spread_cost_bps = float(args.max_spread_cost_bps) if args.max_spread_cost_bps is not None else float(cost_model["extreme_cost_bps"])

    m5 = load_tf(root, "M5", db_path)
    m15 = load_tf(root, "M15", db_path)
    h1 = load_tf(root, "H1", db_path)

    if not m5 or not m15 or not h1:
        summary = {
            "stage": "Stage49_BROKER_MULTITF_TREND_PERSISTENCE_THESIS",
            "status": "MISSING_REQUIRED_TIMEFRAMES_NO_PROMOTION",
            "promotion": "NO_GO", "EA": "NO_GO", "paper_live": "NO_GO", "live": "NO_GO",
            "required": ["M5", "M15", "H1"],
            "rows": {"M5": len(m5), "M15": len(m15), "H1": len(h1)},
            "next_allowed_step": "RUN_AMARKETS_MULTITF_IMPORTER_FIRST",
        }
        (out_dir / "stage49_multitf_trend_persistence_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        (out_dir / "stage49_multitf_trend_persistence_report.md").write_text(
            "# Stage49 Broker MultiTF Trend Persistence Thesis\n\n"
            f"- status: `{summary['status']}`\n"
            f"- rows: `{summary['rows']}`\n\n"
            "Run the AMarkets multi-timeframe importer first. No promotion is allowed.\n",
            encoding="utf-8",
        )
        print(json.dumps({"stage": summary["stage"], "status": summary["status"], "rows": summary["rows"], "out": str(out_dir)}))
        return 2

    grid = []
    for h1_window in [72, 120]:
        for perc in [75.0, 85.0]:
            for m15_sma in [20, 40]:
                for m5_sma in [20]:
                    for horizon in [12, 24, 48]:
                        grid.append((h1_window, perc, m15_sma, m5_sma, horizon))

    results: List[CandidateResult] = []
    all_events: List[Dict[str, object]] = []
    for h1_window, perc, m15_sma, m5_sma, horizon in grid:
        res, events = evaluate_candidate(
            m5=m5, m15=m15, h1=h1,
            h1_range_window=h1_window,
            h1_range_percentile=perc,
            m15_sma_window=m15_sma,
            m5_sma_window=m5_sma,
            horizon_m5_bars=horizon,
            max_spread_cost_bps=max_spread_cost_bps,
            stress_cost_bps=stress_cost_bps,
        )
        results.append(res)
        # Keep event output bounded but enough for audit.
        all_events.extend(events[:2000])

    results_sorted = sorted(results, key=lambda r: (r.decision != "DIAGNOSTIC_SURVIVOR_NEEDS_HARD_AUDIT", -r.oos_stress_mean_bps, -r.stress_mean_bps))
    survivor_count = sum(1 for r in results if r.decision == "DIAGNOSTIC_SURVIVOR_NEEDS_HARD_AUDIT")
    status = "MULTITF_THESIS_DIAGNOSTIC_SURVIVORS_NEED_AUDIT_NO_PROMOTION" if survivor_count else "MULTITF_THESIS_DIAGNOSTIC_COMPLETE_NO_PROMOTION"
    next_step = "HARD_AUDIT_SURVIVORS_NO_PROMOTION" if survivor_count else "ARCHIVE_OR_DESIGN_NEXT_NON_LIQUIDITY_THESIS_NO_PROMOTION"

    summary = {
        "stage": "Stage49_BROKER_MULTITF_TREND_PERSISTENCE_THESIS",
        "patch": "STAGE49_AMARKETS_IMPORTER_AND_MULTITF_TREND_PERSISTENCE_THESIS",
        "status": status,
        "promotion": "NO_GO", "EA": "NO_GO", "paper_live": "NO_GO", "live": "NO_GO",
        "next_allowed_step": next_step,
        "inputs": {"db": str(db_path), "cost_model": str(root / args.cost_model), "required_timeframes": ["M5", "M15", "H1"]},
        "rows": {"M5": len(m5), "M15": len(m15), "H1": len(h1)},
        "costs": {"stress_cost_bps": stress_cost_bps, "max_spread_cost_bps": max_spread_cost_bps},
        "grid_candidate_count": len(results),
        "diagnostic_survivor_count": survivor_count,
        "top_candidates": [asdict(r) for r in results_sorted[:10]],
    }
    (out_dir / "stage49_multitf_trend_persistence_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    write_csv(out_dir / "stage49_multitf_trend_persistence_candidates.csv", [asdict(r) for r in results_sorted], list(asdict(results_sorted[0]).keys()) if results_sorted else [])
    if all_events:
        event_fields = [
            "candidate_id", "entry_time_utc", "exit_time_utc", "direction", "entry_price", "exit_price",
            "gross_bps", "stress_cost_bps", "stress_net_bps", "h1_time_utc", "h1_range_bps",
            "h1_range_percentile_rank", "entry_spread_cost_bps", "session_utc", "year",
        ]
        write_csv(out_dir / "stage49_multitf_trend_persistence_event_sample.csv", all_events, event_fields)
    else:
        write_csv(out_dir / "stage49_multitf_trend_persistence_event_sample.csv", [], ["candidate_id"])

    lines = [
        "# Stage49 Broker-Real Multi-Timeframe Trend Persistence Thesis",
        "",
        f"- status: `{status}`",
        f"- next_allowed_step: `{next_step}`",
        "- promotion: `NO_GO`",
        "- EA: `NO_GO`",
        "- paper_live: `NO_GO`",
        "- live: `NO_GO`",
        "",
        "## Thesis",
        "",
        "H1 range-expansion bars may show short-horizon directional persistence when M15 and M5 are aligned with the same direction and entry spread is below the broker-real cost gate.",
        "This is not a liquidity-sweep reversal thesis and does not reuse the failed Stage47/48 rescue path.",
        "",
        "## Inputs",
        "",
        f"- M5 rows: `{len(m5)}`",
        f"- M15 rows: `{len(m15)}`",
        f"- H1 rows: `{len(h1)}`",
        f"- stress_cost_bps: `{stress_cost_bps:.4f}`",
        f"- max_spread_cost_bps: `{max_spread_cost_bps:.4f}`",
        "",
        "## Top candidates",
        "",
    ]
    for r in results_sorted[:10]:
        lines.append(
            f"- `{r.candidate_id}` trades=`{r.trade_count}` oos_trades=`{r.oos_trade_count}` stress_mean=`{r.stress_mean_bps:.4f}` oos_stress_mean=`{r.oos_stress_mean_bps:.4f}` decision=`{r.decision}` notes=`{r.notes}`"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "This is a cost-aware diagnostic only. Survivors, if any, require hard audit before any further consideration. No EA, paper-live, live trading, or promotion is authorized.",
    ]
    (out_dir / "stage49_multitf_trend_persistence_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "stage": summary["stage"],
        "status": status,
        "rows": summary["rows"],
        "grid_candidate_count": len(results),
        "diagnostic_survivor_count": survivor_count,
        "out": str(out_dir),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
