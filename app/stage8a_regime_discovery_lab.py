#!/usr/bin/env python3
"""
Stage 8A — Regime Discovery Lab from SQLite

Purpose:
- Stop testing fixed entry rules after Stage 7D killed current thesis set.
- Discover where XAUUSD shows favorable forward movement distribution.
- Analyze market regimes before designing the next strategy.

This is NOT a trading strategy.
It is a regime discovery / opportunity map.

It answers:
- Which regimes have favorable long/short forward distribution?
- Is edge concentrated in trend, compression, shock, session, volatility, or year?
- Are MFE/MAE and close returns supportive enough to justify a new thesis?

Features:
- H1 bars from local SQLite broker feed.
- M1 forward path for MFE/MAE.
- Price-derived regimes:
  - H4 trend state
  - H1 trend state
  - volatility percentile
  - range compression percentile
  - impulse/shock candle flag
  - session
  - year
- Optional macro windows from data/config/macro_events.csv and CLI shock windows.

Hard rules:
- Read-only SQLite.
- Research only.
- No EA change.
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
DEFAULT_OUT_DIR = Path("data/reports/stage8a_regime_discovery_lab")
DEFAULT_MACRO_EVENTS = Path("data/config/macro_events.csv")


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
class Probe:
    probe_utc: str
    session: str
    year: int
    h1_trend: str
    h4_trend: str
    vol_bucket: str
    compression_bucket: str
    impulse_bucket: str
    macro_bucket: str
    direction: str
    horizon_hours: int
    entry_price: float
    mfe_usd: float
    mae_usd: float
    close_move_usd: float
    hit_plus_10: bool
    hit_plus_15: bool
    hit_plus_24: bool
    hit_minus_10: bool
    hit_minus_15: bool
    first_hit_15_15: str
    first_hit_24_15: str


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


def connect_ro(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(f"DB not found: {path}")
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
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
    out = []
    for r in rows:
        t = parse_time(r["utc_time"])
        if t is None:
            continue
        out.append(Bar(t=t, open=float(r["open"]), high=float(r["high"]), low=float(r["low"]), close=float(r["close"])))
    return out


def sma(vals: Sequence[float], w: int) -> List[Optional[float]]:
    out = [None] * len(vals)
    s = 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= w:
            s -= vals[i-w]
        if i >= w - 1:
            out[i] = s / w
    return out


def ema(vals: Sequence[float], w: int) -> List[Optional[float]]:
    out = [None] * len(vals)
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
    out = [None] * len(bars)
    for i in range(w, len(bars)):
        hh = max(b.high for b in bars[i-w:i])
        ll = min(b.low for b in bars[i-w:i])
        out[i] = hh - ll
    return out


def pct_rank(vals: Sequence[Optional[float]], lookback: int) -> List[Optional[float]]:
    out = [None] * len(vals)
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


def trend_state(closes: Sequence[float], fast: int = 20, slow: int = 50) -> List[str]:
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
    return out


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


def map_h4_trend(h1: Sequence[Bar], h4: Sequence[Bar]) -> Dict[datetime, str]:
    h4_state = trend_state([b.close for b in h4], 20, 50)
    h4_times = [b.t for b in h4]
    out = {}
    for b in h1:
        idx = bisect.bisect_right(h4_times, floor_h4(b.t)) - 1
        out[b.t] = h4_state[idx] if 0 <= idx < len(h4_state) else "unknown"
    return out


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


def macro_bucket(t: datetime, windows: Sequence[EventWindow]) -> str:
    labels = []
    for w in windows:
        if w.start <= t <= w.end:
            labels.append(w.impact)
    if not labels:
        return "normal"
    if "shock" in labels:
        return "shock"
    if "high" in labels:
        return "macro_high"
    return "macro_other"


def first_hit(path: Sequence[Bar], direction: str, entry: float, plus: float, minus: float) -> str:
    if direction == "long":
        tp = entry + plus
        sl = entry - minus
        for b in path:
            hit_tp = b.high >= tp
            hit_sl = b.low <= sl
            if hit_tp and hit_sl:
                return "ambiguous_sl"
            if hit_sl:
                return "sl_first"
            if hit_tp:
                return "tp_first"
    else:
        tp = entry - plus
        sl = entry + minus
        for b in path:
            hit_tp = b.low <= tp
            hit_sl = b.high >= sl
            if hit_tp and hit_sl:
                return "ambiguous_sl"
            if hit_sl:
                return "sl_first"
            if hit_tp:
                return "tp_first"
    return "none"


def probe_forward(b: Bar, direction: str, h: int, m1: Sequence[Bar], m1_times: Sequence[datetime]) -> Optional[Tuple[float, float, float, bool, bool, bool, bool, bool, str, str]]:
    entry_t = b.t + timedelta(hours=1)
    si = bisect.bisect_left(m1_times, entry_t)
    ei = bisect.bisect_left(m1_times, entry_t + timedelta(hours=h))
    if si >= len(m1) or si >= ei:
        return None
    entry = m1[si].open
    path = m1[si:ei]
    if direction == "long":
        mfe = max(x.high for x in path) - entry
        mae = min(x.low for x in path) - entry
        close_move = path[-1].close - entry
        hp10 = any(x.high >= entry + 10 for x in path)
        hp15 = any(x.high >= entry + 15 for x in path)
        hp24 = any(x.high >= entry + 24 for x in path)
        hm10 = any(x.low <= entry - 10 for x in path)
        hm15 = any(x.low <= entry - 15 for x in path)
    else:
        mfe = entry - min(x.low for x in path)
        mae = entry - max(x.high for x in path)
        close_move = entry - path[-1].close
        hp10 = any(x.low <= entry - 10 for x in path)
        hp15 = any(x.low <= entry - 15 for x in path)
        hp24 = any(x.low <= entry - 24 for x in path)
        hm10 = any(x.high >= entry + 10 for x in path)
        hm15 = any(x.high >= entry + 15 for x in path)
    return (
        round(entry, 6),
        round(mfe, 6),
        round(mae, 6),
        round(close_move, 6),
        hp10,
        hp15,
        hp24,
        hm10,
        hm15,
        first_hit(path, direction, entry, 15, 15),
        first_hit(path, direction, entry, 24, 15),
    )


def generate_probes(h1: List[Bar], m1: List[Bar], windows: List[EventWindow], horizons: Sequence[int], stride: int) -> List[Probe]:
    closes = [b.close for b in h1]
    h1_tr = trend_state(closes, 20, 50)
    h4 = resample_h4(h1)
    h4_tr_map = map_h4_trend(h1, h4)
    atr14 = atr(h1, 14)
    tr = true_range(h1)
    tr_pct = pct_rank([x for x in tr], 240)
    rng16 = rolling_range(h1, 16)
    rng_pct = pct_rank(rng16, 240)
    m1_times = [b.t for b in m1]

    probes: List[Probe] = []
    start = max(300, 80)
    for i in range(start, len(h1), stride):
        b = h1[i]
        if atr14[i] is None:
            continue
        impulse = "normal"
        if tr[i] >= 1.8 * atr14[i]:
            impulse = "shock_impulse"
        elif tr[i] >= 1.2 * atr14[i]:
            impulse = "expanded"

        for h in horizons:
            for direction in ("long", "short"):
                r = probe_forward(b, direction, h, m1, m1_times)
                if r is None:
                    continue
                entry, mfe, mae, close_move, hp10, hp15, hp24, hm10, hm15, fh15, fh24 = r
                probes.append(Probe(
                    probe_utc=b.t.isoformat(),
                    session=session_name(b.t + timedelta(hours=1)),
                    year=b.t.year,
                    h1_trend=h1_tr[i],
                    h4_trend=h4_tr_map.get(b.t, "unknown"),
                    vol_bucket=bucket_pct(tr_pct[i]),
                    compression_bucket=bucket_pct(rng_pct[i]),
                    impulse_bucket=impulse,
                    macro_bucket=macro_bucket(b.t, windows),
                    direction=direction,
                    horizon_hours=h,
                    entry_price=entry,
                    mfe_usd=mfe,
                    mae_usd=mae,
                    close_move_usd=close_move,
                    hit_plus_10=hp10,
                    hit_plus_15=hp15,
                    hit_plus_24=hp24,
                    hit_minus_10=hm10,
                    hit_minus_15=hm15,
                    first_hit_15_15=fh15,
                    first_hit_24_15=fh24,
                ))
    return probes


def rate(vals: Sequence[bool]) -> float:
    if not vals:
        return 0.0
    return round(sum(1 for v in vals if v) / len(vals), 6)


def summarize_group(rows: List[Probe], group_name: str, group_value: str) -> dict:
    closes = [r.close_move_usd for r in rows]
    mfes = [r.mfe_usd for r in rows]
    maes = [r.mae_usd for r in rows]
    tp15 = [r.first_hit_15_15 == "tp_first" for r in rows]
    sl15 = [r.first_hit_15_15 in {"sl_first", "ambiguous_sl"} for r in rows]
    tp24 = [r.first_hit_24_15 == "tp_first" for r in rows]
    sl24 = [r.first_hit_24_15 in {"sl_first", "ambiguous_sl"} for r in rows]
    out = {
        "group_name": group_name,
        "group_value": group_value,
        "direction": rows[0].direction,
        "horizon_hours": rows[0].horizon_hours,
        "samples": len(rows),
        "median_close_move": round(median(closes), 6) if closes else 0.0,
        "avg_close_move": round(sum(closes) / len(closes), 6) if closes else 0.0,
        "median_mfe": round(median(mfes), 6) if mfes else 0.0,
        "median_mae": round(median(maes), 6) if maes else 0.0,
        "hit_plus_10_rate": rate([r.hit_plus_10 for r in rows]),
        "hit_plus_15_rate": rate([r.hit_plus_15 for r in rows]),
        "hit_plus_24_rate": rate([r.hit_plus_24 for r in rows]),
        "hit_minus_10_rate": rate([r.hit_minus_10 for r in rows]),
        "hit_minus_15_rate": rate([r.hit_minus_15 for r in rows]),
        "tp15_first_rate": rate(tp15),
        "sl15_first_rate": rate(sl15),
        "tp24_first_rate": rate(tp24),
        "sl24_first_rate": rate(sl24),
    }
    out["edge_score"] = round(
        out["avg_close_move"]
        + 5.0 * (out["tp15_first_rate"] - out["sl15_first_rate"])
        + 2.0 * (out["hit_plus_15_rate"] - out["hit_minus_15_rate"]),
        6,
    )
    out["diagnosis"] = diagnose(out)
    return out


def diagnose(s: dict) -> str:
    if s["samples"] < 100:
        return "IGNORE_TOO_FEW_SAMPLES"
    if s["edge_score"] > 1.0 and s["tp15_first_rate"] > s["sl15_first_rate"] and s["avg_close_move"] > 0:
        return "PROMISING_REGIME_RESEARCH_ONLY"
    if s["edge_score"] > 0.3:
        return "WATCHLIST_REGIME"
    if s["edge_score"] < -0.5:
        return "AVOID_OR_REVERSE_CANDIDATE"
    return "NO_CLEAR_FORWARD_EDGE"


def summarize_all(probes: List[Probe]) -> List[dict]:
    summaries: List[dict] = []
    group_fields = [
        "session", "year", "h1_trend", "h4_trend", "vol_bucket", "compression_bucket",
        "impulse_bucket", "macro_bucket",
    ]
    for field in group_fields:
        groups: Dict[Tuple[str, str, int, str], List[Probe]] = {}
        for r in probes:
            key = (field, str(getattr(r, field)), r.horizon_hours, r.direction)
            groups.setdefault(key, []).append(r)
        for (gname, gval, h, d), rows in groups.items():
            summaries.append(summarize_group(rows, gname, gval))
    summaries.sort(key=lambda s: (s["diagnosis"].startswith("PROMISING"), s["edge_score"], s["samples"]), reverse=True)
    return summaries


def write_outputs(out_dir: Path, payload: dict, probes: List[Probe], summaries: List[dict]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload["top_summaries"] = summaries[:100]
    (out_dir / "stage8a_regime_discovery_lab.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    with (out_dir / "stage8a_regime_summaries.csv").open("w", newline="", encoding="utf-8") as f:
        cols = [
            "group_name", "group_value", "direction", "horizon_hours", "diagnosis", "edge_score", "samples",
            "avg_close_move", "median_close_move", "median_mfe", "median_mae",
            "hit_plus_10_rate", "hit_plus_15_rate", "hit_plus_24_rate",
            "hit_minus_10_rate", "hit_minus_15_rate", "tp15_first_rate", "sl15_first_rate",
            "tp24_first_rate", "sl24_first_rate",
        ]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for s in summaries:
            w.writerow({c: s.get(c) for c in cols})

    # Keep probe CSV optional-size manageable by writing all; stride default reduces count.
    if probes:
        with (out_dir / "stage8a_regime_probes.csv").open("w", newline="", encoding="utf-8") as f:
            cols = list(asdict(probes[0]).keys())
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for p in probes:
                w.writerow(asdict(p))

    lines = [
        "# Stage 8A Regime Discovery Lab",
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
        f"- horizons: `{payload['horizons']}`",
        f"- stride_h1: `{payload['stride_h1']}`",
        f"- macro_windows: `{payload['macro_windows']}`",
        f"- probes: `{payload['probes']}`",
        "",
        "## Top regime/opportunity map",
        "| Group | Value | Direction | H | Diagnosis | Edge score | Samples | Avg close | MFE med | MAE med | TP15 first | SL15 first |",
        "|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in summaries[:60]:
        lines.append(
            f"| {s['group_name']} | {s['group_value']} | {s['direction']} | {s['horizon_hours']} | {s['diagnosis']} | "
            f"{s['edge_score']} | {s['samples']} | {s['avg_close_move']} | {s['median_mfe']} | {s['median_mae']} | "
            f"{s['tp15_first_rate']} | {s['sl15_first_rate']} |"
        )

    lines += [
        "",
        "## Interpretation",
        "- `PROMISING_REGIME_RESEARCH_ONLY`: regime has favorable forward distribution; it is not yet a strategy.",
        "- `WATCHLIST_REGIME`: worth deeper slicing, but not enough for entry rules.",
        "- `AVOID_OR_REVERSE_CANDIDATE`: forward behavior is negative for that direction.",
        "- This stage helps design the next thesis from distribution, not from losing-trade deletion.",
        "",
        "## Decision",
        "- If no promising regimes appear, mechanical price-only strategy should be paused.",
        "- If promising regimes appear, Stage 8B must build one thesis from the strongest regime only.",
        "- No EA or order workflow changes are allowed from Stage 8A alone.",
    ]
    (out_dir / "stage8a_regime_discovery_lab.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--macro-events-csv", default=str(DEFAULT_MACRO_EVENTS))
    p.add_argument("--shock-window", action="append", default=[], help="START_UTC,END_UTC,LABEL")
    p.add_argument("--horizons", default="3,6,12")
    p.add_argument("--stride-h1", type=int, default=3, help="Probe every Nth H1 bar to avoid over-weighting adjacent bars")
    args = p.parse_args()

    horizons = [int(x.strip()) for x in args.horizons.split(",") if x.strip()]
    conn = connect_ro(Path(args.db))
    h1 = load_bars(conn, "1h")
    m1 = load_bars(conn, "1m")
    conn.close()

    if not h1 or not m1:
        raise RuntimeError("Missing H1/M1 bars. Run Stage 6B first.")

    windows = read_macro_events(Path(args.macro_events_csv))
    windows.extend(parse_shock_windows(args.shock_window))

    probes = generate_probes(h1, m1, windows, horizons, max(1, args.stride_h1))
    summaries = summarize_all(probes)

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": now_iso(),
        "db_path": str(Path(args.db)),
        "h1_rows": len(h1),
        "m1_rows": len(m1),
        "horizons": horizons,
        "stride_h1": args.stride_h1,
        "macro_windows": len(windows),
        "probes": len(probes),
        "macro_windows_preview": [{"start": w.start.isoformat(), "end": w.end.isoformat(), "label": w.label, "impact": w.impact, "mode": w.mode} for w in windows[:20]],
    }
    write_outputs(Path(args.out_dir), payload, probes, summaries)

    print("Stage 8A regime discovery lab: DONE")
    print(f"H1 rows={len(h1)} M1 rows={len(m1)} probes={len(probes)} macro_windows={len(windows)}")
    print(f"Report: {Path(args.out_dir) / 'stage8a_regime_discovery_lab.md'}")
    print(f"Summary CSV: {Path(args.out_dir) / 'stage8a_regime_summaries.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
