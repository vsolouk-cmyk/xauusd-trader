#!/usr/bin/env python3
"""
Stage 7A — Strategy Thesis Lab from SQLite

Purpose:
- Stop pure filter-mining.
- Test a small set of thesis-driven XAUUSD strategy families from the local SQLite store.
- Compare each thesis with and without macro/event blocking.
- Keep AMarkets/MT5 data as the execution-grade source of truth.

Strategy families in v1:
1. baseline_sma_distance_v1_control
2. trend_pullback_continuation
3. asia_range_breakout
4. volatility_compression_breakout
5. range_mean_reversion

Macro/event guard:
- Optional CSV: data/config/macro_events.csv
- Optional --shock-window START,END,LABEL arguments
- Each thesis is evaluated in two variants:
  - unguarded
  - macro_blocked

Hard rules:
- Research only.
- Read-only DB access.
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
DEFAULT_OUT_DIR = Path("data/reports/stage7a_strategy_thesis_lab")
DEFAULT_MACRO_EVENTS = Path("data/config/macro_events.csv")
ROUNDTRIP_COST_USD = 0.35


@dataclass
class Bar:
    t: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass
class EventWindow:
    start: datetime
    end: datetime
    label: str
    impact: str
    mode: str


@dataclass
class Signal:
    thesis: str
    variant: str
    signal_utc: datetime
    entry_utc: datetime
    direction: str
    session: str
    entry_model: str
    tp_usd: float
    sl_usd: float
    time_exit_h1_bars: int
    reason: str
    close_h1: float
    atr14: float
    macro_blocked: bool
    macro_labels: str


@dataclass
class Trade:
    thesis: str
    variant: str
    signal_utc: str
    entry_utc: str
    direction: str
    session: str
    entry_price: float
    tp_price: float
    sl_price: float
    exit_utc: str
    exit_price: float
    exit_reason: str
    net_usd_x1: float
    macro_labels: str
    year: int


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_time(value: str) -> Optional[datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y.%m.%d %H:%M:%S",
        "%Y.%m.%d %H:%M",
        "%Y-%m-%d",
        "%Y.%m.%d",
    ):
        try:
            candidate = s.replace("Z", "+0000") if fmt.endswith("%z") else s
            dt = datetime.strptime(candidate, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def safe_float(v, default: float = 0.0) -> float:
    try:
        if v is None or str(v).strip() == "":
            return default
        return float(v)
    except Exception:
        return default


def session_name(t: datetime) -> str:
    h = t.hour
    if 0 <= h < 7:
        return "asia"
    if 7 <= h < 13:
        return "london"
    if 13 <= h < 17:
        return "london_ny_overlap"
    if 17 <= h < 22:
        return "new_york"
    return "other"


def connect_ro(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite DB not found: {db_path}")
    conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_bars(conn: sqlite3.Connection, timeframe: str, source: str = "amarkets_mt5") -> List[Bar]:
    rows = conn.execute(
        """
        SELECT utc_time, open, high, low, close
        FROM bars
        WHERE source=? AND symbol='XAUUSD' AND timeframe=?
        ORDER BY utc_time ASC
        """,
        (source, timeframe),
    ).fetchall()
    out: List[Bar] = []
    for r in rows:
        t = parse_time(r["utc_time"])
        if t is None:
            continue
        out.append(Bar(t=t, open=float(r["open"]), high=float(r["high"]), low=float(r["low"]), close=float(r["close"])))
    return out


def sma(values: Sequence[float], window: int) -> List[Optional[float]]:
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


def true_range(bars: Sequence[Bar]) -> List[float]:
    trs: List[float] = []
    prev_close = None
    for b in bars:
        if prev_close is None:
            tr = b.high - b.low
        else:
            tr = max(b.high - b.low, abs(b.high - prev_close), abs(b.low - prev_close))
        trs.append(tr)
        prev_close = b.close
    return trs


def rolling_atr(bars: Sequence[Bar], window: int = 14) -> List[Optional[float]]:
    return sma(true_range(bars), window)


def rolling_high(bars: Sequence[Bar], window: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(bars)
    for i in range(len(bars)):
        if i >= window:
            out[i] = max(b.high for b in bars[i-window:i])
    return out


def rolling_low(bars: Sequence[Bar], window: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(bars)
    for i in range(len(bars)):
        if i >= window:
            out[i] = min(b.low for b in bars[i-window:i])
    return out


def percentile_rank(values: Sequence[float], lookback: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    for i in range(len(values)):
        if i < lookback:
            continue
        sample = values[i-lookback:i]
        if not sample:
            continue
        below = sum(1 for x in sample if x <= values[i])
        out[i] = below / len(sample)
    return out


def read_macro_events(path: Path) -> List[EventWindow]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        return []
    rows = list(csv.DictReader(text.splitlines()))
    out: List[EventWindow] = []
    for r in rows:
        event_time = parse_time(r.get("event_time_utc") or r.get("time_utc") or r.get("datetime_utc") or "")
        if event_time is None:
            continue
        before = int(safe_float(r.get("guard_before_min"), 60))
        after = int(safe_float(r.get("guard_after_min"), 180))
        out.append(EventWindow(
            start=event_time - timedelta(minutes=before),
            end=event_time + timedelta(minutes=after),
            label=(r.get("label") or r.get("event") or "macro_event").strip(),
            impact=(r.get("impact") or "high").strip(),
            mode=(r.get("mode") or "block").strip(),
        ))
    return out


def parse_shock_windows(items: Sequence[str]) -> List[EventWindow]:
    out: List[EventWindow] = []
    for item in items:
        parts = [p.strip() for p in item.split(",")]
        if len(parts) < 3:
            continue
        start = parse_time(parts[0])
        end = parse_time(parts[1])
        label = parts[2]
        if start is None or end is None:
            continue
        out.append(EventWindow(start=start, end=end, label=label, impact="shock", mode="block"))
    return out


def macro_labels_for(t: datetime, entry: datetime, windows: Sequence[EventWindow]) -> Tuple[bool, str]:
    labels: List[str] = []
    blocked = False
    for w in windows:
        if (w.start <= t <= w.end) or (w.start <= entry <= w.end):
            labels.append(f"{w.label}:{w.impact}:{w.mode}")
            if w.mode.lower() == "block":
                blocked = True
    return blocked, ";".join(labels)


def make_signal(thesis: str, variant: str, b: Bar, direction: str, tp: float, sl: float, atr: float, reason: str, windows: Sequence[EventWindow]) -> Signal:
    entry = b.t + timedelta(hours=1)
    blocked, labels = macro_labels_for(b.t, entry, windows)
    return Signal(
        thesis=thesis,
        variant=variant,
        signal_utc=b.t,
        entry_utc=entry,
        direction=direction,
        session=session_name(entry),
        entry_model="next_h1_open",
        tp_usd=round(tp, 6),
        sl_usd=round(sl, 6),
        time_exit_h1_bars=12,
        reason=reason,
        close_h1=b.close,
        atr14=round(atr, 6),
        macro_blocked=blocked,
        macro_labels=labels,
    )


def generate_baseline(bars: Sequence[Bar], windows: Sequence[EventWindow], variant: str) -> List[Signal]:
    closes = [b.close for b in bars]
    s10 = sma(closes, 10)
    atr = rolling_atr(bars, 14)
    signals: List[Signal] = []
    for i, b in enumerate(bars):
        if i < 50 or s10[i] is None or atr[i] is None:
            continue
        if b.close - s10[i] >= 10.0:
            signals.append(make_signal("baseline_sma_distance_v1_control", variant, b, "long", 24.0, 15.0, atr[i], "close_minus_sma10_ge_10", windows))
    return signals


def generate_trend_pullback(bars: Sequence[Bar], windows: Sequence[EventWindow], variant: str) -> List[Signal]:
    closes = [b.close for b in bars]
    s20 = sma(closes, 20)
    s50 = sma(closes, 50)
    atr = rolling_atr(bars, 14)
    signals: List[Signal] = []
    for i, b in enumerate(bars):
        if i < 60 or s20[i] is None or s50[i] is None or atr[i] is None:
            continue
        prev = bars[i-1]
        trend_up = b.close > s50[i] and s20[i] > s50[i]
        pulled_back = min(prev.low, b.low) <= s20[i] + 0.25 * atr[i]
        recovered = b.close > s20[i] and b.close > prev.high
        not_extended = (b.close - s20[i]) <= 1.2 * atr[i]
        if trend_up and pulled_back and recovered and not_extended:
            sl = max(10.0, 1.05 * atr[i])
            tp = max(18.0, 1.65 * sl)
            signals.append(make_signal("trend_pullback_continuation", variant, b, "long", tp, sl, atr[i], "trend_up_pullback_recovery", windows))
    return signals


def asia_range_for_day(bars: Sequence[Bar]) -> Dict[str, Tuple[float, float]]:
    day_ranges: Dict[str, List[Bar]] = {}
    for b in bars:
        if 0 <= b.t.hour < 7:
            day_ranges.setdefault(b.t.date().isoformat(), []).append(b)
    out: Dict[str, Tuple[float, float]] = {}
    for day, bs in day_ranges.items():
        if len(bs) >= 4:
            out[day] = (max(x.high for x in bs), min(x.low for x in bs))
    return out


def generate_asia_range_breakout(bars: Sequence[Bar], windows: Sequence[EventWindow], variant: str) -> List[Signal]:
    ranges = asia_range_for_day(bars)
    atr = rolling_atr(bars, 14)
    signals: List[Signal] = []
    for i, b in enumerate(bars):
        if i < 30 or atr[i] is None:
            continue
        if not (7 <= b.t.hour < 20):
            continue
        day = b.t.date().isoformat()
        if day not in ranges:
            continue
        ah, al = ranges[day]
        width = ah - al
        if width <= 0 or width > 3.0 * atr[i]:
            continue
        prev = bars[i-1]
        buffer = max(1.0, 0.12 * atr[i])
        if prev.close <= ah and b.close > ah + buffer:
            sl = max(10.0, min(24.0, 0.60 * width + 0.35 * atr[i]))
            tp = max(18.0, 1.60 * sl)
            signals.append(make_signal("asia_range_breakout", variant, b, "long", tp, sl, atr[i], "break_above_asia_range", windows))
        elif prev.close >= al and b.close < al - buffer:
            sl = max(10.0, min(24.0, 0.60 * width + 0.35 * atr[i]))
            tp = max(18.0, 1.60 * sl)
            signals.append(make_signal("asia_range_breakout", variant, b, "short", tp, sl, atr[i], "break_below_asia_range", windows))
    return signals


def generate_vol_compression_breakout(bars: Sequence[Bar], windows: Sequence[EventWindow], variant: str) -> List[Signal]:
    atr = rolling_atr(bars, 14)
    rh = rolling_high(bars, 12)
    rl = rolling_low(bars, 12)
    ranges: List[float] = []
    for i in range(len(bars)):
        ranges.append(0.0 if rh[i] is None or rl[i] is None else rh[i] - rl[i])
    pr = percentile_rank(ranges, 240)
    signals: List[Signal] = []
    for i, b in enumerate(bars):
        if i < 260 or atr[i] is None or rh[i] is None or rl[i] is None or pr[i] is None:
            continue
        if pr[i] > 0.25:
            continue
        prev = bars[i-1]
        buffer = max(1.0, 0.10 * atr[i])
        if prev.close <= rh[i] and b.close > rh[i] + buffer:
            sl = max(10.0, 1.05 * atr[i])
            tp = max(18.0, 1.80 * sl)
            signals.append(make_signal("volatility_compression_breakout", variant, b, "long", tp, sl, atr[i], "low_range_percentile_breakout_up", windows))
        elif prev.close >= rl[i] and b.close < rl[i] - buffer:
            sl = max(10.0, 1.05 * atr[i])
            tp = max(18.0, 1.80 * sl)
            signals.append(make_signal("volatility_compression_breakout", variant, b, "short", tp, sl, atr[i], "low_range_percentile_breakout_down", windows))
    return signals


def generate_range_mean_reversion(bars: Sequence[Bar], windows: Sequence[EventWindow], variant: str) -> List[Signal]:
    closes = [b.close for b in bars]
    s20 = sma(closes, 20)
    s50 = sma(closes, 50)
    atr = rolling_atr(bars, 14)
    signals: List[Signal] = []
    for i, b in enumerate(bars):
        if i < 60 or s20[i] is None or s50[i] is None or atr[i] is None:
            continue
        weak_trend = abs(s20[i] - s50[i]) <= 0.45 * atr[i]
        if not weak_trend:
            continue
        dist = b.close - s20[i]
        if dist >= 1.35 * atr[i]:
            sl = max(10.0, 0.95 * atr[i])
            tp = max(12.0, 1.15 * atr[i])
            signals.append(make_signal("range_mean_reversion", variant, b, "short", tp, sl, atr[i], "weak_trend_overextended_above_sma20", windows))
        elif dist <= -1.35 * atr[i]:
            sl = max(10.0, 0.95 * atr[i])
            tp = max(12.0, 1.15 * atr[i])
            signals.append(make_signal("range_mean_reversion", variant, b, "long", tp, sl, atr[i], "weak_trend_overextended_below_sma20", windows))
    return signals


def resolve_signals(signals: Sequence[Signal], m1: Sequence[Bar], cost: float, macro_blocking: bool = False) -> Tuple[List[Trade], int]:
    times = [b.t for b in m1]
    trades: List[Trade] = []
    blocked_count = 0
    current_free_time: Optional[datetime] = None

    for s in sorted(signals, key=lambda x: x.entry_utc):
        if macro_blocking and s.macro_blocked:
            blocked_count += 1
            continue
        if current_free_time is not None and s.entry_utc < current_free_time:
            continue
        start_idx = bisect.bisect_left(times, s.entry_utc)
        end_time = s.entry_utc + timedelta(hours=s.time_exit_h1_bars)
        end_idx = bisect.bisect_left(times, end_time)
        if start_idx >= len(m1) or start_idx >= end_idx:
            continue

        entry = m1[start_idx].open
        if s.direction == "long":
            tp = entry + s.tp_usd
            sl = entry - s.sl_usd
        else:
            tp = entry - s.tp_usd
            sl = entry + s.sl_usd

        exit_t = None
        exit_price = None
        reason = None
        for b in m1[start_idx:end_idx]:
            if s.direction == "long":
                hit_tp = b.high >= tp
                hit_sl = b.low <= sl
            else:
                hit_tp = b.low <= tp
                hit_sl = b.high >= sl
            if hit_tp and hit_sl:
                exit_t, exit_price, reason = b.t, sl, "ambiguous_tp_sl_same_m1_bar_conservative_sl"
                break
            if hit_sl:
                exit_t, exit_price, reason = b.t, sl, "stop_loss"
                break
            if hit_tp:
                exit_t, exit_price, reason = b.t, tp, "take_profit"
                break
        if exit_t is None:
            last = m1[end_idx - 1]
            exit_t, exit_price, reason = last.t, last.close, "time_exit"

        net = (exit_price - entry) - cost if s.direction == "long" else (entry - exit_price) - cost
        trades.append(Trade(
            thesis=s.thesis,
            variant=s.variant,
            signal_utc=s.signal_utc.isoformat(),
            entry_utc=s.entry_utc.isoformat(),
            direction=s.direction,
            session=s.session,
            entry_price=round(entry, 6),
            tp_price=round(tp, 6),
            sl_price=round(sl, 6),
            exit_utc=exit_t.isoformat(),
            exit_price=round(exit_price, 6),
            exit_reason=reason,
            net_usd_x1=round(net, 6),
            macro_labels=s.macro_labels,
            year=s.entry_utc.year,
        ))
        current_free_time = exit_t
    return trades, blocked_count


def max_drawdown(vals: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for v in vals:
        equity += v
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return round(max_dd, 6)


def summarize_trades(thesis: str, variant: str, trades: List[Trade], raw_signals: int, macro_blocked: int) -> dict:
    nets = [t.net_usd_x1 for t in trades]
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = round(gross_win / gross_loss, 6) if gross_loss > 0 else (999.0 if gross_win > 0 else 0.0)
    by_session: Dict[str, dict] = {}
    by_year: Dict[int, dict] = {}
    for t in trades:
        s = by_session.setdefault(t.session, {"trades": 0, "total": 0.0})
        s["trades"] += 1
        s["total"] += t.net_usd_x1
        y = by_year.setdefault(t.year, {"trades": 0, "total": 0.0})
        y["trades"] += 1
        y["total"] += t.net_usd_x1
    return {
        "thesis": thesis,
        "variant": variant,
        "raw_signals": raw_signals,
        "macro_blocked_signals": macro_blocked,
        "trades": len(trades),
        "total_net": round(sum(nets), 6) if nets else 0.0,
        "avg_net": round(sum(nets) / len(nets), 6) if nets else 0.0,
        "median_net": round(median(nets), 6) if nets else 0.0,
        "win_rate": round(len(wins) / len(nets), 6) if nets else 0.0,
        "profit_factor": pf,
        "max_drawdown": max_drawdown(nets),
        "by_session": {k: {"trades": v["trades"], "total": round(v["total"], 6)} for k, v in sorted(by_session.items())},
        "by_year": {str(k): {"trades": v["trades"], "total": round(v["total"], 6)} for k, v in sorted(by_year.items())},
    }


def kill_switch_label(summary: dict) -> str:
    trades = summary["trades"]
    total = summary["total_net"]
    pf = summary["profit_factor"]
    med = summary["median_net"]
    dd = summary["max_drawdown"]
    if trades < 60:
        return "KILL_TOO_FEW_TRADES"
    if total <= 0:
        return "KILL_NEGATIVE_TOTAL"
    if pf < 1.08:
        return "KILL_LOW_PF"
    if med < -5:
        return "KILL_BAD_MEDIAN"
    if dd < -600:
        return "KILL_DRAWDOWN_TOO_HIGH"
    year_totals = [v["total"] for v in summary["by_year"].values()]
    positive_years = sum(1 for x in year_totals if x > 0)
    if positive_years < 2:
        return "WARN_YEAR_CONCENTRATION"
    return "PROMISING_RESEARCH_ONLY"


def run_lab(h1: List[Bar], m1: List[Bar], windows: List[EventWindow], cost: float) -> Tuple[List[dict], List[Trade]]:
    generators = [
        generate_baseline,
        generate_trend_pullback,
        generate_asia_range_breakout,
        generate_vol_compression_breakout,
        generate_range_mean_reversion,
    ]
    summaries: List[dict] = []
    all_trades: List[Trade] = []
    for gen in generators:
        sigs = gen(h1, windows, "unguarded")
        trades, _ = resolve_signals(sigs, m1, cost, macro_blocking=False)
        thesis = trades[0].thesis if trades else (sigs[0].thesis if sigs else gen.__name__.replace("generate_", ""))
        su = summarize_trades(thesis, "unguarded", trades, len(sigs), 0)
        su["decision"] = kill_switch_label(su)
        summaries.append(su)
        all_trades.extend(trades)

        sigs_g = gen(h1, windows, "macro_blocked")
        trades_g, blocked = resolve_signals(sigs_g, m1, cost, macro_blocking=True)
        thesis_g = trades_g[0].thesis if trades_g else (sigs_g[0].thesis if sigs_g else gen.__name__.replace("generate_", ""))
        sg = summarize_trades(thesis_g, "macro_blocked", trades_g, len(sigs_g), blocked)
        sg["decision"] = kill_switch_label(sg)
        summaries.append(sg)
        all_trades.extend(trades_g)
    return summaries, all_trades


def write_outputs(out_dir: Path, payload: dict, summaries: List[dict], trades: List[Trade]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "stage7a_strategy_thesis_lab.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    with (out_dir / "stage7a_strategy_summaries.csv").open("w", newline="", encoding="utf-8") as f:
        cols = ["thesis", "variant", "decision", "raw_signals", "macro_blocked_signals", "trades", "total_net", "avg_net", "median_net", "win_rate", "profit_factor", "max_drawdown"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for s in summaries:
            w.writerow({c: s.get(c) for c in cols})
    if trades:
        with (out_dir / "stage7a_strategy_trades.csv").open("w", newline="", encoding="utf-8") as f:
            cols = list(asdict(trades[0]).keys())
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for t in trades:
                w.writerow(asdict(t))

    ranked = sorted(summaries, key=lambda x: (x["decision"].startswith("PROMISING"), x["profit_factor"], x["total_net"]), reverse=True)
    lines = [
        "# Stage 7A Strategy Thesis Lab",
        "",
        f"Generated UTC: `{payload['generated_utc']}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: research only. This does not authorize demo, paper, or live orders.",
        "",
        "## Inputs",
        f"- db: `{payload['db_path']}`",
        f"- h1_rows: `{payload['h1_rows']}`",
        f"- m1_rows: `{payload['m1_rows']}`",
        f"- macro_event_windows: `{payload['macro_event_windows']}`",
        f"- roundtrip_cost_usd: `{payload['roundtrip_cost_usd']}`",
        "",
        "## Thesis ranking",
        "| Thesis | Variant | Decision | Raw signals | Macro blocked | Trades | Total | PF | Median | Win rate | Max DD |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in ranked:
        lines.append(
            f"| {s['thesis']} | {s['variant']} | {s['decision']} | {s['raw_signals']} | {s['macro_blocked_signals']} | "
            f"{s['trades']} | {s['total_net']} | {s['profit_factor']} | {s['median_net']} | {s['win_rate']} | {s['max_drawdown']} |"
        )
    lines += [
        "",
        "## Interpretation rules",
        "- `PROMISING_RESEARCH_ONLY` means worth deeper validation, not tradable.",
        "- `KILL_*` means do not tune filters around this version; either redesign the thesis or discard it.",
        "- Compare `unguarded` vs `macro_blocked`. Macro guard is useful only if it improves robustness, not merely because it reduces trades.",
        "",
        "## Macro/event guard",
    ]
    if payload["macro_windows_preview"]:
        for w in payload["macro_windows_preview"]:
            lines.append(f"- `{w['start']}` → `{w['end']}` | {w['label']} | {w['impact']} | {w['mode']}")
    else:
        lines.append("- No macro/event windows loaded. Guarded and unguarded variants may be identical.")
    lines += [
        "",
        "## Decision",
        "- Do not lock no_asia or any other filter from Stage 7A alone.",
        "- Use Stage 7A to choose which thesis family deserves Stage 7B deeper validation.",
        "- Current v1 dry-run can continue only as evidence collection.",
    ]
    (out_dir / "stage7a_strategy_thesis_lab.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    ap.add_argument("--macro-events-csv", default=str(DEFAULT_MACRO_EVENTS))
    ap.add_argument("--shock-window", action="append", default=[], help="Format: START_UTC,END_UTC,LABEL")
    ap.add_argument("--roundtrip-cost-usd", type=float, default=ROUNDTRIP_COST_USD)
    args = ap.parse_args()
    db_path = Path(args.db)
    conn = connect_ro(db_path)
    h1 = load_bars(conn, "1h")
    m1 = load_bars(conn, "1m")
    conn.close()
    if not h1 or not m1:
        raise RuntimeError("Missing amarkets_mt5 H1/M1 bars in SQLite. Run Stage 6B first.")
    windows = read_macro_events(Path(args.macro_events_csv))
    windows.extend(parse_shock_windows(args.shock_window))
    summaries, trades = run_lab(h1, m1, windows, args.roundtrip_cost_usd)
    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": now_iso(),
        "db_path": str(db_path),
        "h1_rows": len(h1),
        "m1_rows": len(m1),
        "macro_event_windows": len(windows),
        "macro_windows_preview": [{**asdict(w), "start": w.start.isoformat(), "end": w.end.isoformat()} for w in windows[:20]],
        "roundtrip_cost_usd": args.roundtrip_cost_usd,
        "summaries": summaries,
    }
    write_outputs(Path(args.out_dir), payload, summaries, trades)
    print("Stage 7A strategy thesis lab: DONE")
    print(f"H1 rows={len(h1)} M1 rows={len(m1)} macro_windows={len(windows)}")
    print(f"Report: {Path(args.out_dir) / 'stage7a_strategy_thesis_lab.md'}")
    print(f"Summary CSV: {Path(args.out_dir) / 'stage7a_strategy_summaries.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
