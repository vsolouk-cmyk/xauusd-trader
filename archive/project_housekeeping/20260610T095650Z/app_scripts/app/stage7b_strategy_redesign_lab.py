#!/usr/bin/env python3
"""
Stage 7B — Strategy Redesign Lab from SQLite

Purpose:
- Move beyond filter-mining.
- Test a few pre-defined, thesis-driven XAUUSD strategy designs.
- Compare macro-guarded and unguarded variants.
- Apply cost stress x1/x3/x4, year robustness, median, and drawdown kill-switches.

Important:
- This is a redesign lab, not a live/paper/demo system.
- It reads the local SQLite evidence store.
- It does not modify the EA.
- It does not authorize orders.

Strategy families in v1:
1. h4_trend_h1_pullback_continuation
2. asia_range_breakout_retest
3. compression_expansion_confirmed
4. regime_reversal_after_failed_break
5. baseline_sma_distance_v1_control

Macro/event guard:
- Reads data/config/macro_events.csv if present.
- Accepts --shock-window START,END,LABEL.
- Every design is tested as unguarded and macro_blocked.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


TOOL_VERSION = "v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_OUT_DIR = Path("data/reports/stage7b_strategy_redesign_lab")
DEFAULT_MACRO_EVENTS = Path("data/config/macro_events.csv")
BASE_COST_USD = 0.35


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
class DesignSignal:
    family: str
    design: str
    guard_variant: str
    signal_utc: datetime
    entry_utc: datetime
    direction: str
    session: str
    tp_usd: float
    sl_usd: float
    time_exit_h1_bars: int
    reason: str
    atr14: float
    regime_note: str
    macro_blocked: bool
    macro_labels: str


@dataclass
class DesignTrade:
    family: str
    design: str
    guard_variant: str
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
    gross_usd_x1: float
    net_x1: float
    net_x3: float
    net_x4: float
    macro_labels: str
    year: int
    reason: str
    regime_note: str


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_time(value: str) -> Optional[datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    fmts = (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y.%m.%d %H:%M:%S",
        "%Y.%m.%d %H:%M",
        "%Y-%m-%d",
        "%Y.%m.%d",
    )
    for fmt in fmts:
        try:
            dt = datetime.strptime(s.replace("Z", "+0000") if fmt.endswith("%z") else s, fmt)
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
    out = []
    for r in rows:
        t = parse_time(r["utc_time"])
        if t is None:
            continue
        out.append(Bar(t=t, open=float(r["open"]), high=float(r["high"]), low=float(r["low"]), close=float(r["close"])))
    return out


def ema(values: Sequence[float], window: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    if not values or window <= 1:
        return out
    alpha = 2.0 / (window + 1.0)
    e = None
    for i, v in enumerate(values):
        if e is None:
            e = v
        else:
            e = alpha * v + (1 - alpha) * e
        if i >= window - 1:
            out[i] = e
    return out


def sma(values: Sequence[float], window: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= window:
            s -= values[i - window]
        if i >= window - 1:
            out[i] = s / window
    return out


def true_range(bars: Sequence[Bar]) -> List[float]:
    out = []
    prev = None
    for b in bars:
        if prev is None:
            tr = b.high - b.low
        else:
            tr = max(b.high - b.low, abs(b.high - prev), abs(b.low - prev))
        out.append(tr)
        prev = b.close
    return out


def atr(bars: Sequence[Bar], window: int = 14) -> List[Optional[float]]:
    return sma(true_range(bars), window)


def rolling_high(bars: Sequence[Bar], window: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(bars)
    for i in range(window, len(bars)):
        out[i] = max(b.high for b in bars[i-window:i])
    return out


def rolling_low(bars: Sequence[Bar], window: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(bars)
    for i in range(window, len(bars)):
        out[i] = min(b.low for b in bars[i-window:i])
    return out


def percentile_rank(values: Sequence[float], lookback: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    for i in range(lookback, len(values)):
        sample = values[i-lookback:i]
        if not sample:
            continue
        out[i] = sum(1 for x in sample if x <= values[i]) / len(sample)
    return out


def floor_to_h4(t: datetime) -> datetime:
    return t.replace(hour=(t.hour // 4) * 4, minute=0, second=0, microsecond=0)


def resample_h4(h1: Sequence[Bar]) -> List[Bar]:
    groups: Dict[datetime, List[Bar]] = {}
    for b in h1:
        groups.setdefault(floor_to_h4(b.t), []).append(b)
    out = []
    for t in sorted(groups):
        bs = groups[t]
        if len(bs) < 2:
            continue
        out.append(Bar(t=t, open=bs[0].open, high=max(x.high for x in bs), low=min(x.low for x in bs), close=bs[-1].close))
    return out


def map_h4_state_to_h1(h1: Sequence[Bar], h4: Sequence[Bar]) -> Dict[datetime, dict]:
    closes = [b.close for b in h4]
    e20 = ema(closes, 20)
    e50 = ema(closes, 50)
    h4_times = [b.t for b in h4]
    state: Dict[datetime, dict] = {}
    for b in h1:
        idx = bisect.bisect_right(h4_times, floor_to_h4(b.t)) - 1
        if idx < 60 or idx >= len(h4) or e20[idx] is None or e50[idx] is None:
            state[b.t] = {"trend": "unknown", "ema20": None, "ema50": None}
            continue
        slope = e20[idx] - e20[idx-5] if idx >= 5 and e20[idx-5] is not None else 0.0
        if h4[idx].close > e20[idx] > e50[idx] and slope > 0:
            trend = "up"
        elif h4[idx].close < e20[idx] < e50[idx] and slope < 0:
            trend = "down"
        else:
            trend = "neutral"
        state[b.t] = {"trend": trend, "ema20": e20[idx], "ema50": e50[idx]}
    return state


def read_macro_events(path: Path) -> List[EventWindow]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        return []
    rows = list(csv.DictReader(text.splitlines()))
    out = []
    for r in rows:
        t = parse_time(r.get("event_time_utc") or r.get("time_utc") or r.get("datetime_utc") or "")
        if t is None:
            continue
        before = int(safe_float(r.get("guard_before_min"), 60))
        after = int(safe_float(r.get("guard_after_min"), 180))
        out.append(EventWindow(
            start=t - timedelta(minutes=before),
            end=t + timedelta(minutes=after),
            label=(r.get("label") or r.get("event") or "macro_event").strip(),
            impact=(r.get("impact") or "high").strip(),
            mode=(r.get("mode") or "block").strip(),
        ))
    return out


def parse_shock_windows(items: Sequence[str]) -> List[EventWindow]:
    out = []
    for item in items:
        parts = [p.strip() for p in item.split(",")]
        if len(parts) < 3:
            continue
        start = parse_time(parts[0])
        end = parse_time(parts[1])
        if start is None or end is None:
            continue
        out.append(EventWindow(start=start, end=end, label=parts[2], impact="shock", mode="block"))
    return out


def macro_info(signal_t: datetime, entry_t: datetime, windows: Sequence[EventWindow]) -> Tuple[bool, str]:
    labels = []
    blocked = False
    for w in windows:
        if (w.start <= signal_t <= w.end) or (w.start <= entry_t <= w.end):
            labels.append(f"{w.label}:{w.impact}:{w.mode}")
            if w.mode.lower() == "block":
                blocked = True
    return blocked, ";".join(labels)


def mk_signal(family: str, design: str, guard_variant: str, b: Bar, direction: str, tp: float, sl: float, exit_h: int, reason: str, atr14: float, regime_note: str, windows: Sequence[EventWindow]) -> DesignSignal:
    entry = b.t + timedelta(hours=1)
    blocked, labels = macro_info(b.t, entry, windows)
    return DesignSignal(
        family=family,
        design=design,
        guard_variant=guard_variant,
        signal_utc=b.t,
        entry_utc=entry,
        direction=direction,
        session=session_name(entry),
        tp_usd=round(tp, 6),
        sl_usd=round(sl, 6),
        time_exit_h1_bars=exit_h,
        reason=reason,
        atr14=round(atr14, 6),
        regime_note=regime_note,
        macro_blocked=blocked,
        macro_labels=labels,
    )


def gen_baseline(h1: Sequence[Bar], h4_state: Dict[datetime, dict], windows: Sequence[EventWindow], guard_variant: str) -> List[DesignSignal]:
    closes = [b.close for b in h1]
    s10 = sma(closes, 10)
    a14 = atr(h1, 14)
    out = []
    for i, b in enumerate(h1):
        if i < 50 or s10[i] is None or a14[i] is None:
            continue
        if b.close - s10[i] >= 10:
            out.append(mk_signal("baseline_sma_distance_v1_control", "control_v1_long", guard_variant, b, "long", 24.0, 15.0, 12, "close_minus_sma10_ge_10", a14[i], "baseline_control", windows))
    return out


def gen_h4_trend_pullback(h1: Sequence[Bar], h4_state: Dict[datetime, dict], windows: Sequence[EventWindow], guard_variant: str) -> List[DesignSignal]:
    closes = [b.close for b in h1]
    e20 = ema(closes, 20)
    e50 = ema(closes, 50)
    a14 = atr(h1, 14)
    out = []
    for i, b in enumerate(h1):
        if i < 80 or e20[i] is None or e50[i] is None or a14[i] is None:
            continue
        st = h4_state.get(b.t, {})
        prev = h1[i-1]
        # Long: H4 trend up; H1 pulls near EMA20; recovers without being too extended.
        if st.get("trend") == "up":
            pullback = min(prev.low, b.low) <= e20[i] + 0.20 * a14[i]
            recover = b.close > e20[i] and b.close > prev.high
            not_chase = 0 <= (b.close - e20[i]) <= 0.95 * a14[i]
            if pullback and recover and not_chase:
                sl = max(9.0, min(22.0, 1.00 * a14[i]))
                tp = max(16.0, 1.75 * sl)
                out.append(mk_signal("h4_trend_h1_pullback_continuation", "balanced_pullback", guard_variant, b, "long", tp, sl, 10, "h4_up_h1_pullback_recovery", a14[i], "h4_up", windows))
        # Short symmetrical.
        if st.get("trend") == "down":
            pullback = max(prev.high, b.high) >= e20[i] - 0.20 * a14[i]
            recover = b.close < e20[i] and b.close < prev.low
            not_chase = 0 <= (e20[i] - b.close) <= 0.95 * a14[i]
            if pullback and recover and not_chase:
                sl = max(9.0, min(22.0, 1.00 * a14[i]))
                tp = max(16.0, 1.75 * sl)
                out.append(mk_signal("h4_trend_h1_pullback_continuation", "balanced_pullback", guard_variant, b, "short", tp, sl, 10, "h4_down_h1_pullback_recovery", a14[i], "h4_down", windows))
    return out


def asia_ranges(h1: Sequence[Bar]) -> Dict[str, Tuple[float, float]]:
    days: Dict[str, List[Bar]] = {}
    for b in h1:
        if 0 <= b.t.hour < 7:
            days.setdefault(b.t.date().isoformat(), []).append(b)
    out = {}
    for d, bs in days.items():
        if len(bs) >= 5:
            out[d] = (max(x.high for x in bs), min(x.low for x in bs))
    return out


def gen_asia_breakout_retest(h1: Sequence[Bar], h4_state: Dict[datetime, dict], windows: Sequence[EventWindow], guard_variant: str) -> List[DesignSignal]:
    ranges = asia_ranges(h1)
    a14 = atr(h1, 14)
    out = []
    # Track per-day breakout state.
    state: Dict[str, Dict[str, int]] = {}
    for i, b in enumerate(h1):
        if i < 30 or a14[i] is None:
            continue
        day = b.t.date().isoformat()
        if day not in ranges:
            continue
        ah, al = ranges[day]
        width = ah - al
        if width <= 4 or width > 3.2 * a14[i]:
            continue
        buffer = max(0.8, 0.08 * a14[i])
        st = state.setdefault(day, {"up_break_i": -9999, "down_break_i": -9999})

        # Detect breakout.
        if b.close > ah + buffer:
            st["up_break_i"] = i
        if b.close < al - buffer:
            st["down_break_i"] = i

        # Trade retest after breakout, not first chase. London to NY only.
        if not (7 <= b.t.hour < 20):
            continue
        prev = h1[i-1]
        if 1 <= i - st["up_break_i"] <= 4:
            retest = b.low <= ah + 0.25 * a14[i]
            continuation = b.close > max(prev.high, ah + buffer)
            if retest and continuation:
                sl = max(9.0, min(22.0, 0.50 * width + 0.25 * a14[i]))
                tp = max(16.0, 1.70 * sl)
                out.append(mk_signal("asia_range_breakout_retest", "retest_continuation", guard_variant, b, "long", tp, sl, 8, "asia_high_break_retest_continue", a14[i], f"asia_width={round(width,2)}", windows))
                st["up_break_i"] = -9999
        if 1 <= i - st["down_break_i"] <= 4:
            retest = b.high >= al - 0.25 * a14[i]
            continuation = b.close < min(prev.low, al - buffer)
            if retest and continuation:
                sl = max(9.0, min(22.0, 0.50 * width + 0.25 * a14[i]))
                tp = max(16.0, 1.70 * sl)
                out.append(mk_signal("asia_range_breakout_retest", "retest_continuation", guard_variant, b, "short", tp, sl, 8, "asia_low_break_retest_continue", a14[i], f"asia_width={round(width,2)}", windows))
                st["down_break_i"] = -9999
    return out


def gen_compression_expansion(h1: Sequence[Bar], h4_state: Dict[datetime, dict], windows: Sequence[EventWindow], guard_variant: str) -> List[DesignSignal]:
    a14 = atr(h1, 14)
    rh = rolling_high(h1, 16)
    rl = rolling_low(h1, 16)
    tr = true_range(h1)
    compression_range = []
    for i in range(len(h1)):
        if rh[i] is None or rl[i] is None:
            compression_range.append(0.0)
        else:
            compression_range.append(rh[i] - rl[i])
    pr = percentile_rank(compression_range, 240)
    out = []
    for i, b in enumerate(h1):
        if i < 280 or a14[i] is None or rh[i] is None or rl[i] is None or pr[i] is None:
            continue
        if pr[i] > 0.18:
            continue
        expansion = tr[i] >= 1.15 * a14[i]
        if not expansion:
            continue
        buffer = max(0.9, 0.10 * a14[i])
        prev = h1[i-1]
        if prev.close <= rh[i] and b.close > rh[i] + buffer:
            sl = max(9.0, min(24.0, 1.05 * a14[i]))
            tp = max(16.0, 1.90 * sl)
            out.append(mk_signal("compression_expansion_confirmed", "range16_pct18_expansion", guard_variant, b, "long", tp, sl, 8, "compression_breakout_up_with_tr_expansion", a14[i], f"range_pct={round(pr[i],3)}", windows))
        elif prev.close >= rl[i] and b.close < rl[i] - buffer:
            sl = max(9.0, min(24.0, 1.05 * a14[i]))
            tp = max(16.0, 1.90 * sl)
            out.append(mk_signal("compression_expansion_confirmed", "range16_pct18_expansion", guard_variant, b, "short", tp, sl, 8, "compression_breakout_down_with_tr_expansion", a14[i], f"range_pct={round(pr[i],3)}", windows))
    return out


def gen_failed_break_reversal(h1: Sequence[Bar], h4_state: Dict[datetime, dict], windows: Sequence[EventWindow], guard_variant: str) -> List[DesignSignal]:
    a14 = atr(h1, 14)
    rh = rolling_high(h1, 24)
    rl = rolling_low(h1, 24)
    closes = [b.close for b in h1]
    e20 = ema(closes, 20)
    e50 = ema(closes, 50)
    out = []
    for i, b in enumerate(h1):
        if i < 80 or a14[i] is None or rh[i] is None or rl[i] is None or e20[i] is None or e50[i] is None:
            continue
        weak_regime = abs(e20[i] - e50[i]) <= 0.40 * a14[i]
        if not weak_regime:
            continue
        prev = h1[i-1]
        # Failed break above range then close back inside = short.
        if prev.high > rh[i] and b.close < rh[i] - 0.15 * a14[i] and b.close < prev.low:
            sl = max(8.0, min(18.0, 0.90 * a14[i]))
            tp = max(12.0, 1.45 * sl)
            out.append(mk_signal("regime_reversal_after_failed_break", "failed_range_break", guard_variant, b, "short", tp, sl, 6, "failed_break_above_range", a14[i], "weak_trend_range", windows))
        # Failed break below range then close back inside = long.
        if prev.low < rl[i] and b.close > rl[i] + 0.15 * a14[i] and b.close > prev.high:
            sl = max(8.0, min(18.0, 0.90 * a14[i]))
            tp = max(12.0, 1.45 * sl)
            out.append(mk_signal("regime_reversal_after_failed_break", "failed_range_break", guard_variant, b, "long", tp, sl, 6, "failed_break_below_range", a14[i], "weak_trend_range", windows))
    return out


def resolve(signals: Sequence[DesignSignal], m1: Sequence[Bar], macro_blocking: bool) -> Tuple[List[DesignTrade], int]:
    times = [b.t for b in m1]
    trades: List[DesignTrade] = []
    blocked = 0
    free_after: Optional[datetime] = None

    for s in sorted(signals, key=lambda x: x.entry_utc):
        if macro_blocking and s.macro_blocked:
            blocked += 1
            continue
        if free_after is not None and s.entry_utc < free_after:
            continue
        si = bisect.bisect_left(times, s.entry_utc)
        ei = bisect.bisect_left(times, s.entry_utc + timedelta(hours=s.time_exit_h1_bars))
        if si >= len(m1) or si >= ei:
            continue
        entry = m1[si].open
        if s.direction == "long":
            tp = entry + s.tp_usd
            sl = entry - s.sl_usd
        else:
            tp = entry - s.tp_usd
            sl = entry + s.sl_usd

        exit_t = None
        exit_price = None
        reason = None

        for b in m1[si:ei]:
            if s.direction == "long":
                hit_tp = b.high >= tp
                hit_sl = b.low <= sl
            else:
                hit_tp = b.low <= tp
                hit_sl = b.high >= sl
            if hit_tp and hit_sl:
                exit_t = b.t
                exit_price = sl
                reason = "ambiguous_tp_sl_same_m1_bar_conservative_sl"
                break
            if hit_sl:
                exit_t = b.t
                exit_price = sl
                reason = "stop_loss"
                break
            if hit_tp:
                exit_t = b.t
                exit_price = tp
                reason = "take_profit"
                break
        if exit_t is None:
            last = m1[ei-1]
            exit_t = last.t
            exit_price = last.close
            reason = "time_exit"

        gross = (exit_price - entry) if s.direction == "long" else (entry - exit_price)
        trades.append(DesignTrade(
            family=s.family,
            design=s.design,
            guard_variant=s.guard_variant,
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
            gross_usd_x1=round(gross, 6),
            net_x1=round(gross - BASE_COST_USD, 6),
            net_x3=round(gross - 3 * BASE_COST_USD, 6),
            net_x4=round(gross - 4 * BASE_COST_USD, 6),
            macro_labels=s.macro_labels,
            year=s.entry_utc.year,
            reason=s.reason,
            regime_note=s.regime_note,
        ))
        free_after = exit_t
    return trades, blocked


def max_drawdown(vals: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    dd = 0.0
    for v in vals:
        equity += v
        peak = max(peak, equity)
        dd = min(dd, equity - peak)
    return round(dd, 6)


def summarize(family: str, design: str, guard: str, raw_signals: int, blocked: int, trades: List[DesignTrade]) -> dict:
    nets1 = [t.net_x1 for t in trades]
    nets3 = [t.net_x3 for t in trades]
    nets4 = [t.net_x4 for t in trades]

    def pf(vals):
        wins = sum(x for x in vals if x > 0)
        losses = abs(sum(x for x in vals if x < 0))
        if losses == 0:
            return 999.0 if wins > 0 else 0.0
        return round(wins / losses, 6)

    by_year: Dict[int, float] = {}
    by_session: Dict[str, float] = {}
    for t in trades:
        by_year[t.year] = by_year.get(t.year, 0.0) + t.net_x1
        by_session[t.session] = by_session.get(t.session, 0.0) + t.net_x1

    positive_years = sum(1 for v in by_year.values() if v > 0)
    total_years = len(by_year)

    out = {
        "family": family,
        "design": design,
        "guard_variant": guard,
        "raw_signals": raw_signals,
        "macro_blocked_signals": blocked,
        "trades": len(trades),
        "total_x1": round(sum(nets1), 6) if nets1 else 0.0,
        "total_x3": round(sum(nets3), 6) if nets3 else 0.0,
        "total_x4": round(sum(nets4), 6) if nets4 else 0.0,
        "pf_x1": pf(nets1),
        "pf_x3": pf(nets3),
        "pf_x4": pf(nets4),
        "median_x1": round(median(nets1), 6) if nets1 else 0.0,
        "median_x4": round(median(nets4), 6) if nets4 else 0.0,
        "win_rate_x1": round(sum(1 for x in nets1 if x > 0) / len(nets1), 6) if nets1 else 0.0,
        "max_dd_x1": max_drawdown(nets1),
        "max_dd_x4": max_drawdown(nets4),
        "positive_years": positive_years,
        "total_years": total_years,
        "by_year": {str(k): round(v, 6) for k, v in sorted(by_year.items())},
        "by_session": {str(k): round(v, 6) for k, v in sorted(by_session.items())},
    }
    out["decision"] = decide(out)
    out["score"] = score(out)
    return out


def decide(s: dict) -> str:
    if s["trades"] < 80:
        return "KILL_TOO_FEW_TRADES"
    if s["total_x4"] <= 0:
        return "KILL_COST_STRESS_X4_NEGATIVE"
    if s["pf_x4"] < 1.08:
        return "KILL_LOW_PF_X4"
    if s["median_x4"] < -4.0:
        return "KILL_BAD_MEDIAN_X4"
    if s["max_dd_x1"] < -550:
        return "KILL_DRAWDOWN_TOO_HIGH"
    if s["positive_years"] < 2:
        return "KILL_YEAR_FRAGILE"
    if s["trades"] >= 150 and s["pf_x4"] >= 1.12 and s["median_x4"] >= -2.5 and s["positive_years"] >= 3:
        return "PROMISING_FOR_STAGE7C_RESEARCH_ONLY"
    return "WATCHLIST_REDESIGN_NEEDED"


def score(s: dict) -> float:
    return round(
        10.0 * max(0, s["pf_x4"] - 1.0)
        + 0.002 * s["total_x4"]
        + 0.5 * s["positive_years"]
        - 0.002 * abs(min(0, s["max_dd_x1"]))
        + 0.01 * max(-10, s["median_x4"]),
        6,
    )


def run_designs(h1: List[Bar], m1: List[Bar], windows: List[EventWindow]) -> Tuple[List[dict], List[DesignTrade]]:
    h4 = resample_h4(h1)
    h4_state = map_h4_state_to_h1(h1, h4)
    gens = [
        gen_baseline,
        gen_h4_trend_pullback,
        gen_asia_breakout_retest,
        gen_compression_expansion,
        gen_failed_break_reversal,
    ]
    summaries = []
    all_trades: List[DesignTrade] = []

    for gen in gens:
        for guard_variant, macro_blocking in (("unguarded", False), ("macro_blocked", True)):
            signals = gen(h1, h4_state, windows, guard_variant)
            trades, blocked = resolve(signals, m1, macro_blocking=macro_blocking)
            if trades:
                family = trades[0].family
                design = trades[0].design
            elif signals:
                family = signals[0].family
                design = signals[0].design
            else:
                family = gen.__name__.replace("gen_", "")
                design = "no_signals"
            summaries.append(summarize(family, design, guard_variant, len(signals), blocked, trades))
            all_trades.extend(trades)
    return summaries, all_trades


def write_outputs(out_dir: Path, payload: dict, summaries: List[dict], trades: List[DesignTrade]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload["summaries"] = summaries
    (out_dir / "stage7b_strategy_redesign_lab.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    cols = [
        "family", "design", "guard_variant", "decision", "score", "raw_signals", "macro_blocked_signals", "trades",
        "total_x1", "total_x3", "total_x4", "pf_x1", "pf_x3", "pf_x4",
        "median_x1", "median_x4", "win_rate_x1", "max_dd_x1", "max_dd_x4", "positive_years", "total_years",
    ]
    with (out_dir / "stage7b_strategy_summaries.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for s in summaries:
            w.writerow({c: s.get(c) for c in cols})

    if trades:
        with (out_dir / "stage7b_strategy_trades.csv").open("w", newline="", encoding="utf-8") as f:
            tcols = list(asdict(trades[0]).keys())
            w = csv.DictWriter(f, fieldnames=tcols)
            w.writeheader()
            for t in trades:
                w.writerow(asdict(t))

    ranked = sorted(summaries, key=lambda s: (s["decision"].startswith("PROMISING"), s["score"], s["pf_x4"], s["total_x4"]), reverse=True)

    lines = [
        "# Stage 7B Strategy Redesign Lab",
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
        f"- macro_windows: `{payload['macro_windows']}`",
        f"- base_cost_usd: `{BASE_COST_USD}`",
        "",
        "## Ranking",
        "| Family | Design | Guard | Decision | Score | Trades | Total x1 | Total x4 | PF x4 | Median x4 | DD x1 | Pos years |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in ranked:
        lines.append(
            f"| {s['family']} | {s['design']} | {s['guard_variant']} | {s['decision']} | {s['score']} | "
            f"{s['trades']} | {s['total_x1']} | {s['total_x4']} | {s['pf_x4']} | {s['median_x4']} | {s['max_dd_x1']} | {s['positive_years']}/{s['total_years']} |"
        )

    lines += [
        "",
        "## Macro windows",
    ]
    if payload["macro_windows_preview"]:
        for w in payload["macro_windows_preview"]:
            lines.append(f"- `{w['start']}` → `{w['end']}` | {w['label']} | {w['impact']} | {w['mode']}")
    else:
        lines.append("- None loaded. Macro-blocked variants may match unguarded variants.")

    lines += [
        "",
        "## Decision rules",
        "- `PROMISING_FOR_STAGE7C_RESEARCH_ONLY`: candidate for deeper validation only, not tradable.",
        "- `WATCHLIST_REDESIGN_NEEDED`: not dead, but thesis or execution logic needs redesign.",
        "- `KILL_*`: do not rescue with filter mining.",
        "",
        "## Interpretation",
        "- If all families are killed, the current mechanical-thesis set is insufficient.",
        "- If only macro-blocked improves a family meaningfully, Stage 7C must validate the guard separately.",
        "- No EA change is allowed from this report alone.",
    ]
    (out_dir / "stage7b_strategy_redesign_lab.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--macro-events-csv", default=str(DEFAULT_MACRO_EVENTS))
    p.add_argument("--shock-window", action="append", default=[], help="Format: START_UTC,END_UTC,LABEL")
    args = p.parse_args()

    conn = connect_ro(Path(args.db))
    h1 = load_bars(conn, "1h")
    m1 = load_bars(conn, "1m")
    conn.close()
    if not h1 or not m1:
        raise RuntimeError("Missing H1/M1 amarkets_mt5 bars in SQLite. Run Stage 6B first.")

    windows = read_macro_events(Path(args.macro_events_csv))
    windows.extend(parse_shock_windows(args.shock_window))

    summaries, trades = run_designs(h1, m1, windows)
    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": now_iso(),
        "db_path": str(Path(args.db)),
        "h1_rows": len(h1),
        "m1_rows": len(m1),
        "macro_windows": len(windows),
        "macro_windows_preview": [{"start": w.start.isoformat(), "end": w.end.isoformat(), "label": w.label, "impact": w.impact, "mode": w.mode} for w in windows[:25]],
    }
    write_outputs(Path(args.out_dir), payload, summaries, trades)

    print("Stage 7B strategy redesign lab: DONE")
    print(f"H1 rows={len(h1)} M1 rows={len(m1)} macro_windows={len(windows)}")
    print(f"Report: {Path(args.out_dir) / 'stage7b_strategy_redesign_lab.md'}")
    print(f"Summary CSV: {Path(args.out_dir) / 'stage7b_strategy_summaries.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
