#!/usr/bin/env python3
"""
Stage 8B — Single Regime Thesis Lab from SQLite

Purpose:
- Convert the strongest actionable Stage 8A discovery into ONE testable thesis.
- Avoid using year=2025 as a trading rule.
- Avoid losing-trade deletion and broad filter mining.

Stage 8A strongest actionable signals:
- Long side shows favorable 12h forward behavior.
- H4 uptrend long 12h was promising.
- Compression mid_high long 12h was promising.
- London-NY overlap / New York long 12h were promising.

Single thesis:
    XAUUSD H4-uptrend + compression-ready long continuation.

This lab tests only limited execution definitions of that single thesis:
- base: H4 up + compression mid_high
- liquidity_session: base + London-NY overlap/New York entry
- confirmed_h1: base + H1 trend up + close above EMA20
- confirmed_session: confirmed_h1 + London-NY overlap/New York entry

Exit geometries are constrained:
- time_exit_12h
- tp15_sl12_h12
- tp18_sl12_h12
- tp24_sl15_h12_control

Hard rules:
- Research only.
- Read-only SQLite.
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
DEFAULT_OUT_DIR = Path("data/reports/stage8b_single_regime_thesis_lab")
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
class Signal:
    thesis_id: str
    definition: str
    guard_variant: str
    signal_utc: datetime
    entry_utc: datetime
    direction: str
    session: str
    h1_trend: str
    h4_trend: str
    compression_bucket: str
    vol_bucket: str
    close_h1: float
    ema20_h1: float
    ema50_h1: float
    atr14: float
    macro_blocked: bool
    macro_labels: str


@dataclass
class Geometry:
    name: str
    tp_usd: float
    sl_usd: float
    horizon_hours: int
    time_exit_only: bool = False


@dataclass
class Trade:
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


def connect_ro(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite DB not found: {db_path}")
    conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_bars(conn: sqlite3.Connection, tf: str) -> List[Bar]:
    rows = conn.execute(
        """
        SELECT utc_time, open, high, low, close
        FROM bars
        WHERE source='amarkets_mt5' AND symbol='XAUUSD' AND timeframe=?
        ORDER BY utc_time ASC
        """,
        (tf,),
    ).fetchall()
    out: List[Bar] = []
    for r in rows:
        t = parse_time(r["utc_time"])
        if t is None:
            continue
        out.append(Bar(t=t, open=float(r["open"]), high=float(r["high"]), low=float(r["low"]), close=float(r["close"])))
    return out


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


def sma(vals: Sequence[float], w: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(vals)
    s = 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= w:
            s -= vals[i - w]
        if i >= w - 1:
            out[i] = s / w
    return out


def ema(vals: Sequence[float], w: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(vals)
    if not vals or w <= 1:
        return out
    a = 2.0 / (w + 1.0)
    e = None
    for i, v in enumerate(vals):
        e = v if e is None else a * v + (1 - a) * e
        if i >= w - 1:
            out[i] = e
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


def atr(bars: Sequence[Bar], w: int = 14) -> List[Optional[float]]:
    return sma(true_range(bars), w)


def rolling_range(bars: Sequence[Bar], w: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(bars)
    for i in range(w, len(bars)):
        out[i] = max(x.high for x in bars[i-w:i]) - min(x.low for x in bars[i-w:i])
    return out


def pct_rank(vals: Sequence[Optional[float]], lookback: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(vals)
    for i in range(lookback, len(vals)):
        if vals[i] is None:
            continue
        sample = [x for x in vals[i-lookback:i] if x is not None]
        if not sample:
            continue
        out[i] = sum(1 for x in sample if x <= vals[i]) / len(sample)
    return out


def bucket_pct(p: Optional[float]) -> str:
    if p is None:
        return "unknown"
    if p <= 0.20:
        return "low"
    if p <= 0.50:
        return "mid_low"
    if p <= 0.80:
        return "mid_high"
    return "high"


def trend_state(closes: Sequence[float], fast: int = 20, slow: int = 50) -> Tuple[List[str], List[Optional[float]], List[Optional[float]]]:
    efast = ema(closes, fast)
    eslow = ema(closes, slow)
    out = ["unknown"] * len(closes)
    for i in range(len(closes)):
        if i < slow + 5 or efast[i] is None or eslow[i] is None or efast[i-5] is None:
            continue
        slope = efast[i] - efast[i-5]
        if closes[i] > efast[i] > eslow[i] and slope > 0:
            out[i] = "up"
        elif closes[i] < efast[i] < eslow[i] and slope < 0:
            out[i] = "down"
        else:
            out[i] = "neutral"
    return out, efast, eslow


def floor_h4(t: datetime) -> datetime:
    return t.replace(hour=(t.hour // 4) * 4, minute=0, second=0, microsecond=0)


def resample_h4(h1: Sequence[Bar]) -> List[Bar]:
    groups: Dict[datetime, List[Bar]] = {}
    for b in h1:
        groups.setdefault(floor_h4(b.t), []).append(b)
    out = []
    for t in sorted(groups):
        bs = groups[t]
        if len(bs) >= 2:
            out.append(Bar(t=t, open=bs[0].open, high=max(x.high for x in bs), low=min(x.low for x in bs), close=bs[-1].close))
    return out


def map_h4_state(h1: Sequence[Bar], h4: Sequence[Bar]) -> Dict[datetime, str]:
    st, _, _ = trend_state([b.close for b in h4], 20, 50)
    times = [b.t for b in h4]
    out = {}
    for b in h1:
        idx = bisect.bisect_right(times, floor_h4(b.t)) - 1
        out[b.t] = st[idx] if 0 <= idx < len(st) else "unknown"
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
        t = parse_time(r.get("event_time_utc") or r.get("time_utc") or r.get("datetime_utc") or "")
        if t is None:
            continue
        before = int(safe_float(r.get("guard_before_min"), 60))
        after = int(safe_float(r.get("guard_after_min"), 180))
        out.append(EventWindow(
            start=t - timedelta(minutes=before),
            end=t + timedelta(minutes=after),
            label=(r.get("label") or "macro_event").strip(),
            impact=(r.get("impact") or "high").strip(),
            mode=(r.get("mode") or "block").strip(),
        ))
    return out


def parse_shock_windows(items: Sequence[str]) -> List[EventWindow]:
    out = []
    for item in items:
        parts = [x.strip() for x in item.split(",")]
        if len(parts) < 3:
            continue
        s = parse_time(parts[0])
        e = parse_time(parts[1])
        if s is None or e is None:
            continue
        out.append(EventWindow(start=s, end=e, label=parts[2], impact="shock", mode="block"))
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


def mk_signal(definition: str, guard: str, b: Bar, h1_tr: str, h4_tr: str, comp: str, vol: str, e20: float, e50: float, a14: float, windows: Sequence[EventWindow]) -> Signal:
    entry_t = b.t + timedelta(hours=1)
    blocked, labels = macro_info(b.t, entry_t, windows)
    return Signal(
        thesis_id="h4_up_compression_long_continuation_v1",
        definition=definition,
        guard_variant=guard,
        signal_utc=b.t,
        entry_utc=entry_t,
        direction="long",
        session=session_name(entry_t),
        h1_trend=h1_tr,
        h4_trend=h4_tr,
        compression_bucket=comp,
        vol_bucket=vol,
        close_h1=b.close,
        ema20_h1=e20,
        ema50_h1=e50,
        atr14=a14,
        macro_blocked=blocked,
        macro_labels=labels,
    )


def generate_signals(h1: List[Bar], windows: List[EventWindow], guard: str) -> List[Signal]:
    closes = [b.close for b in h1]
    h1_st, e20, e50 = trend_state(closes, 20, 50)
    h4_st = map_h4_state(h1, resample_h4(h1))
    a14 = atr(h1, 14)
    tr_pct = pct_rank([x for x in true_range(h1)], 240)
    rr_pct = pct_rank(rolling_range(h1, 16), 240)

    signals: List[Signal] = []
    for i, b in enumerate(h1):
        if i < 300 or e20[i] is None or e50[i] is None or a14[i] is None:
            continue
        comp = bucket_pct(rr_pct[i])
        vol = bucket_pct(tr_pct[i])
        h4 = h4_st.get(b.t, "unknown")
        h1trend = h1_st[i]
        entry_session = session_name(b.t + timedelta(hours=1))

        # One thesis: H4-uptrend + compression-ready long continuation.
        base = h4 == "up" and comp == "mid_high"
        if not base:
            continue

        # Definition 1: pure actionable regime from Stage 8A.
        signals.append(mk_signal("base_h4up_compression_mid_high", guard, b, h1trend, h4, comp, vol, e20[i], e50[i], a14[i], windows))

        # Definition 2: same thesis but only in liquid continuation windows.
        if entry_session in {"london_ny_overlap", "new_york"}:
            signals.append(mk_signal("liquidity_session", guard, b, h1trend, h4, comp, vol, e20[i], e50[i], a14[i], windows))

        # Definition 3: require H1 trend confirmation.
        confirmed = h1trend == "up" and b.close > e20[i] > e50[i]
        if confirmed:
            signals.append(mk_signal("confirmed_h1", guard, b, h1trend, h4, comp, vol, e20[i], e50[i], a14[i], windows))

        # Definition 4: confirmation + liquid session.
        if confirmed and entry_session in {"london_ny_overlap", "new_york"}:
            signals.append(mk_signal("confirmed_session", guard, b, h1trend, h4, comp, vol, e20[i], e50[i], a14[i], windows))

    return signals


def geometries() -> List[Geometry]:
    return [
        Geometry("time_exit_12h", 0.0, 0.0, 12, True),
        Geometry("tp15_sl12_h12", 15.0, 12.0, 12, False),
        Geometry("tp18_sl12_h12", 18.0, 12.0, 12, False),
        Geometry("tp24_sl15_h12_control", 24.0, 15.0, 12, False),
    ]


def resolve(signals: List[Signal], geom: Geometry, m1: List[Bar], macro_blocking: bool, non_overlap: bool) -> Tuple[List[Trade], int]:
    times = [b.t for b in m1]
    out: List[Trade] = []
    blocked = 0
    free_after: Optional[datetime] = None

    for s in sorted(signals, key=lambda x: x.entry_utc):
        if macro_blocking and s.macro_blocked:
            blocked += 1
            continue
        if non_overlap and free_after is not None and s.entry_utc < free_after:
            continue

        si = bisect.bisect_left(times, s.entry_utc)
        ei = bisect.bisect_left(times, s.entry_utc + timedelta(hours=geom.horizon_hours))
        if si >= len(m1) or si >= ei:
            continue

        entry = m1[si].open
        exit_t = None
        exit_price = None
        reason = None

        if geom.time_exit_only:
            last = m1[ei - 1]
            exit_t = last.t
            exit_price = last.close
            reason = "time_exit_only"
        else:
            tp = entry + geom.tp_usd
            sl = entry - geom.sl_usd
            for b in m1[si:ei]:
                hit_tp = b.high >= tp
                hit_sl = b.low <= sl
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
                last = m1[ei - 1]
                exit_t = last.t
                exit_price = last.close
                reason = "time_exit"

        gross = exit_price - entry
        out.append(Trade(
            thesis_id=s.thesis_id,
            definition=s.definition,
            guard_variant=s.guard_variant + ("_nonoverlap" if non_overlap else "_overlap"),
            geometry=geom.name,
            signal_utc=s.signal_utc.isoformat(),
            entry_utc=s.entry_utc.isoformat(),
            direction="long",
            session=s.session,
            entry_price=round(entry, 6),
            exit_utc=exit_t.isoformat(),
            exit_price=round(exit_price, 6),
            exit_reason=reason,
            gross_usd_x1=round(gross, 6),
            net_x1=round(gross - BASE_COST_USD, 6),
            net_x3=round(gross - 3 * BASE_COST_USD, 6),
            net_x4=round(gross - 4 * BASE_COST_USD, 6),
            year=s.entry_utc.year,
            h1_trend=s.h1_trend,
            h4_trend=s.h4_trend,
            compression_bucket=s.compression_bucket,
            vol_bucket=s.vol_bucket,
            macro_labels=s.macro_labels,
        ))
        free_after = exit_t

    return out, blocked


def max_dd(vals: Sequence[float]) -> float:
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


def summarize_group(trades: List[Trade], raw_signals: int, macro_blocked: int) -> dict:
    if not trades:
        return {}
    n1 = [t.net_x1 for t in trades]
    n3 = [t.net_x3 for t in trades]
    n4 = [t.net_x4 for t in trades]
    by_year: Dict[int, float] = {}
    by_session: Dict[str, float] = {}
    exits: Dict[str, int] = {}
    for t in trades:
        by_year[t.year] = by_year.get(t.year, 0.0) + t.net_x4
        by_session[t.session] = by_session.get(t.session, 0.0) + t.net_x4
        exits[t.exit_reason] = exits.get(t.exit_reason, 0) + 1

    s = {
        "thesis_id": trades[0].thesis_id,
        "definition": trades[0].definition,
        "guard_variant": trades[0].guard_variant,
        "geometry": trades[0].geometry,
        "raw_signals": raw_signals,
        "macro_blocked_signals": macro_blocked,
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
        "max_dd_x1": max_dd(n1),
        "max_dd_x4": max_dd(n4),
        "positive_years": sum(1 for v in by_year.values() if v > 0),
        "total_years": len(by_year),
        "positive_sessions": sum(1 for v in by_session.values() if v > 0),
        "total_sessions": len(by_session),
        "by_year_x4": {str(k): round(v, 6) for k, v in sorted(by_year.items())},
        "by_session_x4": {k: round(v, 6) for k, v in sorted(by_session.items())},
        "exit_reasons": exits,
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
    if s["max_dd_x1"] < -450:
        return "KILL_DRAWDOWN_TOO_HIGH"
    if s["positive_years"] < 2:
        return "KILL_YEAR_FRAGILE"
    if s["positive_sessions"] < 2:
        return "KILL_SESSION_CONCENTRATED"
    if s["pf_x4"] >= 1.15 and s["total_x4"] > 150 and s["positive_years"] >= 3 and s["median_x4"] >= -1.5:
        return "PROMISING_FOR_STAGE8C_RESEARCH_ONLY"
    return "WATCHLIST_THESIS_RESEARCH_ONLY"


def score(s: dict) -> float:
    return round(
        10.0 * max(0.0, s["pf_x4"] - 1.0)
        + 0.0015 * s["total_x4"]
        + 0.35 * s["positive_years"]
        + 0.15 * s["positive_sessions"]
        - 0.002 * abs(min(0.0, s["max_dd_x1"]))
        + 0.02 * max(-10.0, s["median_x4"]),
        6,
    )


def run_lab(h1: List[Bar], m1: List[Bar], windows: List[EventWindow]) -> Tuple[List[Trade], List[dict]]:
    all_trades: List[Trade] = []
    summaries: List[dict] = []
    geoms = geometries()

    for guard, macro_block in [("unguarded", False), ("macro_blocked", True)]:
        raw_signals = generate_signals(h1, windows, guard)
        for definition in sorted(set(s.definition for s in raw_signals)):
            dsigs = [s for s in raw_signals if s.definition == definition]
            for non_overlap in (False, True):
                for geom in geoms:
                    trades, blocked = resolve(dsigs, geom, m1, macro_block, non_overlap)
                    all_trades.extend(trades)
                    if trades:
                        summaries.append(summarize_group(trades, len(dsigs), blocked))

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


def write_outputs(out_dir: Path, payload: dict, trades: List[Trade], summaries: List[dict]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload["summaries"] = summaries
    (out_dir / "stage8b_single_regime_thesis_lab.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    if trades:
        with (out_dir / "stage8b_single_regime_trades.csv").open("w", newline="", encoding="utf-8") as f:
            cols = list(asdict(trades[0]).keys())
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for t in trades:
                w.writerow(asdict(t))

    cols = [
        "thesis_id", "definition", "guard_variant", "geometry", "decision", "score",
        "raw_signals", "macro_blocked_signals", "trades",
        "total_x1", "total_x3", "total_x4", "pf_x1", "pf_x3", "pf_x4",
        "median_x1", "median_x4", "win_rate_x1", "win_rate_x4",
        "max_dd_x1", "max_dd_x4", "positive_years", "total_years", "positive_sessions", "total_sessions",
    ]
    with (out_dir / "stage8b_single_regime_summaries.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for s in summaries:
            w.writerow({c: s.get(c) for c in cols})

    lines = [
        "# Stage 8B Single Regime Thesis Lab",
        "",
        f"Generated UTC: `{payload['generated_utc']}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: research only. This does not authorize demo, paper, or live orders.",
        "",
        "## Thesis",
        "- thesis_id: `h4_up_compression_long_continuation_v1`",
        "- Rationale: Stage 8A showed favorable long forward distribution in H4 uptrend, mid/high compression, London-NY/New York, and 12h horizon.",
        "- Explicitly not used as rule: `year=2025`.",
        "",
        "## Inputs",
        f"- db: `{payload['db_path']}`",
        f"- h1_rows: `{payload['h1_rows']}`",
        f"- m1_rows: `{payload['m1_rows']}`",
        f"- macro_windows: `{payload['macro_windows']}`",
        f"- trades_simulated: `{len(trades)}`",
        "",
        "## Ranking",
        "| Definition | Guard | Geometry | Decision | Score | Signals | Trades | Total x4 | PF x4 | Median x4 | DD x1 | Pos years | Pos sessions |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in summaries[:80]:
        lines.append(
            f"| {s['definition']} | {s['guard_variant']} | {s['geometry']} | {s['decision']} | {s['score']} | "
            f"{s['raw_signals']} | {s['trades']} | {s['total_x4']} | {s['pf_x4']} | {s['median_x4']} | "
            f"{s['max_dd_x1']} | {s['positive_years']}/{s['total_years']} | {s['positive_sessions']}/{s['total_sessions']} |"
        )

    lines += [
        "",
        "## Decision rules",
        "- `PROMISING_FOR_STAGE8C_RESEARCH_ONLY`: one thesis definition deserves deeper robustness validation.",
        "- `WATCHLIST_THESIS_RESEARCH_ONLY`: not tradable; can be refined once, not repeatedly filter-mined.",
        "- `KILL_*`: stop this thesis definition.",
        "",
        "## Interpretation",
        "- This is the first actual strategy-thesis step after regime discovery.",
        "- If all definitions fail, price-only mechanical development should pause or pivot to macro/discretionary-assisted workflow.",
        "- No EA change is allowed from Stage 8B alone.",
    ]
    (out_dir / "stage8b_single_regime_thesis_lab.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--macro-events-csv", default=str(DEFAULT_MACRO_EVENTS))
    p.add_argument("--shock-window", action="append", default=[], help="START_UTC,END_UTC,LABEL")
    args = p.parse_args()

    conn = connect_ro(Path(args.db))
    h1 = load_bars(conn, "1h")
    m1 = load_bars(conn, "1m")
    conn.close()

    if not h1 or not m1:
        raise RuntimeError("Missing H1/M1 bars. Run Stage 6B first.")

    windows = read_macro_events(Path(args.macro_events_csv))
    windows.extend(parse_shock_windows(args.shock_window))

    trades, summaries = run_lab(h1, m1, windows)
    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": now_iso(),
        "db_path": str(Path(args.db)),
        "h1_rows": len(h1),
        "m1_rows": len(m1),
        "macro_windows": len(windows),
        "macro_windows_preview": [{"start": w.start.isoformat(), "end": w.end.isoformat(), "label": w.label, "impact": w.impact, "mode": w.mode} for w in windows[:20]],
    }
    write_outputs(Path(args.out_dir), payload, trades, summaries)

    print("Stage 8B single regime thesis lab: DONE")
    print(f"H1 rows={len(h1)} M1 rows={len(m1)} macro_windows={len(windows)} trades_simulated={len(trades)}")
    print(f"Report: {Path(args.out_dir) / 'stage8b_single_regime_thesis_lab.md'}")
    print(f"Summary CSV: {Path(args.out_dir) / 'stage8b_single_regime_summaries.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
