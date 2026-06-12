#!/usr/bin/env python3
"""
Stage 14A v2 — Fast Liquidity / Session / Sweep Behavior Discovery

v2 fixes:
- Avoid repeated df.index.strftime filtering inside day loops.
- Precomputes per-day slices.
- Adds progress and optional --max-days.
- Keeps behavioral-discovery scope; no classic indicator grid.

Hard rules:
- Research only.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import pandas as pd


TOOL_VERSION = "v2_fast"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_EVENTS = Path("data/config/stage10a_news_events.csv")
DEFAULT_OUT_DIR = Path("data/reports/stage14a_liquidity_session_behavior_discovery")


@dataclass(frozen=True)
class Event:
    mechanism: str
    side: str
    event_utc: pd.Timestamp
    ref_level: float
    context: str


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(db: Path) -> sqlite3.Connection:
    if not db.exists():
        raise FileNotFoundError(f"DB not found: {db}")
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    return c


def load_bars(conn: sqlite3.Connection, tf: str) -> pd.DataFrame:
    rows = conn.execute(
        """
        SELECT utc_time, open, high, low, close
        FROM bars
        WHERE source='amarkets_mt5' AND symbol='XAUUSD' AND timeframe=?
        ORDER BY utc_time
        """,
        (tf,),
    ).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([dict(r) for r in rows])
    df["utc_time"] = pd.to_datetime(df["utc_time"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["utc_time", "open", "high", "low", "close"]).sort_values("utc_time").drop_duplicates("utc_time")
    return df.set_index("utc_time")


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    if df.empty:
        return df
    return df.resample(rule, label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()


def load_intraday(conn: sqlite3.Connection) -> Tuple[pd.DataFrame, str]:
    # Prefer M15 derived from M1/M5, but never run discovery directly on M1.
    m1 = load_bars(conn, "1m")
    if len(m1) > 1000:
        return resample_ohlc(m1, "15min"), "m1_to_m15"
    m5 = load_bars(conn, "5m")
    if len(m5) > 1000:
        return resample_ohlc(m5, "15min"), "m5_to_m15"
    m15 = load_bars(conn, "15m")
    if len(m15) > 500:
        return m15, "m15"
    h1 = load_bars(conn, "1h")
    if len(h1) > 500:
        return h1, "h1_fallback"
    raise RuntimeError("No usable 1m/5m/15m/h1 bars found.")


def load_h4(conn: sqlite3.Connection, intraday: pd.DataFrame) -> pd.DataFrame:
    h4 = load_bars(conn, "4h")
    if len(h4) > 100:
        return h4
    h1 = load_bars(conn, "1h")
    if len(h1) > 100:
        return resample_ohlc(h1, "4h")
    return resample_ohlc(intraday, "4h")


def atr(df: pd.DataFrame, n: int = 96) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat(
        [(df["high"] - df["low"]).abs(), (df["high"] - pc).abs(), (df["low"] - pc).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(n, min_periods=max(10, n // 4)).mean()


def add_day_hour(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    x["_day"] = x.index.strftime("%Y-%m-%d")
    x["_hour"] = x.index.hour
    return x


def build_day_cache(df: pd.DataFrame, max_days: int = 0) -> Dict[str, pd.DataFrame]:
    days = sorted(set(df["_day"]))
    if max_days and max_days > 0:
        days = days[-max_days:]
    return {d: df[df["_day"] == d] for d in days}


def session(day_df: pd.DataFrame, h1: int, h2: int) -> pd.DataFrame:
    return day_df[(day_df["_hour"] >= h1) & (day_df["_hour"] <= h2)]


def mechanism_asia_london(day_cache: Dict[str, pd.DataFrame], buf: float) -> List[Event]:
    out: List[Event] = []
    for day, x in day_cache.items():
        asia = session(x, 0, 6)
        lon = session(x, 7, 11)
        if len(asia) < 4 or lon.empty:
            continue
        ah, al = float(asia.high.max()), float(asia.low.min())
        for ts, r in lon.iterrows():
            if float(r.high) > ah + buf and float(r.close) < ah:
                out.append(Event("asia_high_sweep_london_rejection", "SHORT", ts, ah, f"asia_high={ah:.2f};asia_low={al:.2f}"))
                break
            if float(r.low) < al - buf and float(r.close) > al:
                out.append(Event("asia_low_sweep_london_rejection", "LONG", ts, al, f"asia_high={ah:.2f};asia_low={al:.2f}"))
                break
    return out


def mechanism_london_ny(day_cache: Dict[str, pd.DataFrame], buf: float) -> List[Event]:
    out: List[Event] = []
    for day, x in day_cache.items():
        lon = session(x, 7, 12)
        ny = session(x, 13, 20)
        if len(lon) < 4 or ny.empty:
            continue
        lh, ll = float(lon.high.max()), float(lon.low.min())
        for ts, r in ny.iterrows():
            if float(r.high) > lh + buf and float(r.close) < lh:
                out.append(Event("london_high_sweep_ny_rejection", "SHORT", ts, lh, f"london_high={lh:.2f};london_low={ll:.2f}"))
                break
            if float(r.low) < ll - buf and float(r.close) > ll:
                out.append(Event("london_low_sweep_ny_rejection", "LONG", ts, ll, f"london_high={lh:.2f};london_low={ll:.2f}"))
                break
    return out


def mechanism_prev_day_sweep(day_cache: Dict[str, pd.DataFrame], daily: pd.DataFrame, buf: float) -> List[Event]:
    out: List[Event] = []
    daily_days = list(daily.index.strftime("%Y-%m-%d"))
    for day, x in day_cache.items():
        if day not in daily_days:
            continue
        i = daily_days.index(day)
        if i <= 0:
            continue
        prev = daily.iloc[i - 1]
        pdh, pdl = float(prev.high), float(prev.low)
        x2 = x[x["_hour"] >= 2]
        got_h = got_l = False
        for ts, r in x2.iterrows():
            if not got_h and float(r.high) > pdh + buf and float(r.close) < pdh:
                out.append(Event("prev_day_high_sweep_rejection", "SHORT", ts, pdh, f"pdh={pdh:.2f};pdl={pdl:.2f}"))
                got_h = True
            if not got_l and float(r.low) < pdl - buf and float(r.close) > pdl:
                out.append(Event("prev_day_low_sweep_rejection", "LONG", ts, pdl, f"pdh={pdh:.2f};pdl={pdl:.2f}"))
                got_l = True
            if got_h and got_l:
                break
    return out


def load_event_times(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        x = pd.read_csv(path)
    except Exception:
        return pd.DataFrame()
    ts_col = None
    for c in ["event_time_utc", "timestamp_utc", "time_utc", "datetime_utc", "date_utc"]:
        if c in x.columns:
            ts_col = c
            break
    if ts_col is None:
        return pd.DataFrame()
    x["event_dt"] = pd.to_datetime(x[ts_col], utc=True, errors="coerce")
    return x.dropna(subset=["event_dt"]).sort_values("event_dt")


def mechanism_news_failure(df: pd.DataFrame, events_path: Path) -> List[Event]:
    ev = load_event_times(events_path)
    if ev.empty:
        return []
    out: List[Event] = []
    idx = df.index
    for _, row in ev.iterrows():
        pos = idx.searchsorted(row.event_dt)
        if pos <= 0 or pos + 4 >= len(df):
            continue
        b0 = df.iloc[pos]
        up_first = float(b0.close) >= float(b0.open)
        nxt = df.iloc[pos + 1 : pos + 5]
        klass = str(row.get("event_class", "event"))
        if up_first:
            fail = nxt[nxt.close < float(b0.open)]
            if not fail.empty:
                ts = fail.index[0]
                out.append(Event("news_first_spike_up_failure", "SHORT", ts, float(b0.open), f"class={klass};event={row.event_dt.isoformat()}"))
        else:
            fail = nxt[nxt.close > float(b0.open)]
            if not fail.empty:
                ts = fail.index[0]
                out.append(Event("news_first_spike_down_failure", "LONG", ts, float(b0.open), f"class={klass};event={row.event_dt.isoformat()}"))
    return out


def mechanism_h4_failed_break(df: pd.DataFrame, h4: pd.DataFrame, buf: float) -> List[Event]:
    out: List[Event] = []
    prev = h4[["high", "low"]].shift(1).reindex(df.index, method="ffill")
    last_high_block = None
    last_low_block = None
    for ts, r in df.iterrows():
        ph = prev.at[ts, "high"]
        pl = prev.at[ts, "low"]
        if pd.isna(ph) or pd.isna(pl):
            continue
        ph, pl = float(ph), float(pl)
        block = ts.floor("4h")
        if block != last_high_block and float(r.high) > ph + buf and float(r.close) < ph:
            out.append(Event("failed_break_above_prior_h4_high", "SHORT", ts, ph, f"prior_h4_high={ph:.2f};prior_h4_low={pl:.2f}"))
            last_high_block = block
        if block != last_low_block and float(r.low) < pl - buf and float(r.close) > pl:
            out.append(Event("failed_break_below_prior_h4_low", "LONG", ts, pl, f"prior_h4_high={ph:.2f};prior_h4_low={pl:.2f}"))
            last_low_block = block
    return out


def evaluate(df: pd.DataFrame, events: List[Event], horizons: Sequence[int]) -> pd.DataFrame:
    rows = []
    idx = df.index
    for e in events:
        pos = idx.searchsorted(e.event_utc)
        entry_i = pos + 1
        if entry_i >= len(df):
            continue
        entry = float(df.iloc[entry_i].open)
        mult = 1.0 if e.side == "LONG" else -1.0
        max_h = max(horizons)
        end_i = min(entry_i + max_h, len(df) - 1)
        win = df.iloc[entry_i : end_i + 1]
        mfe = float(win.high.max()) - entry if e.side == "LONG" else entry - float(win.low.min())
        mae = entry - float(win.low.min()) if e.side == "LONG" else float(win.high.max()) - entry
        for h in horizons:
            out_i = entry_i + h
            if out_i >= len(df):
                continue
            exit_p = float(df.iloc[out_i].close)
            ret = (exit_p - entry) * mult
            rows.append(
                {
                    "mechanism": e.mechanism,
                    "side": e.side,
                    "event_utc": e.event_utc.isoformat(),
                    "entry_utc": idx[entry_i].isoformat(),
                    "exit_utc": idx[out_i].isoformat(),
                    "horizon_bars": int(h),
                    "entry_price": round(entry, 6),
                    "exit_price": round(exit_p, 6),
                    "ret_usd": round(ret, 6),
                    "win": int(ret > 0),
                    "mfe_max_h": round(mfe, 6),
                    "mae_max_h": round(mae, 6),
                    "ref_level": round(float(e.ref_level), 6),
                    "context": e.context,
                }
            )
    return pd.DataFrame(rows)


def profit_factor(vals: Sequence[float]) -> float:
    wins = sum(v for v in vals if v > 0)
    losses = abs(sum(v for v in vals if v < 0))
    if losses == 0:
        return 999.0 if wins > 0 else 0.0
    return round(wins / losses, 6)


def max_dd(vals: Sequence[float]) -> float:
    eq = peak = 0.0
    dd = 0.0
    for v in vals:
        eq += v
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return round(dd, 6)


def summarize(results: pd.DataFrame) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame()
    rows = []
    for (mech, side, h), g in results.groupby(["mechanism", "side", "horizon_bars"]):
        vals = g.sort_values("entry_utc").ret_usd.astype(float).tolist()
        yrs = pd.to_datetime(g.entry_utc, utc=True).dt.year
        by_year = g.assign(year=yrs).groupby("year").ret_usd.sum()
        rows.append(
            {
                "mechanism": mech,
                "side": side,
                "horizon_bars": int(h),
                "events": int(len(g)),
                "total_ret": round(sum(vals), 6),
                "avg_ret": round(float(pd.Series(vals).mean()), 6),
                "median_ret": round(float(pd.Series(vals).median()), 6),
                "win_rate": round(float((pd.Series(vals) > 0).mean()), 6),
                "pf": profit_factor(vals),
                "max_dd": max_dd(vals),
                "avg_mfe": round(float(g.mfe_max_h.mean()), 6),
                "avg_mae": round(float(g.mae_max_h.mean()), 6),
                "pos_years": int((by_year > 0).sum()),
                "years": int(len(by_year)),
            }
        )
    s = pd.DataFrame(rows)
    min_pos_years = (s.years * 0.55).round().astype(int).clip(lower=1)
    s["candidate_flag"] = (
        (s.events >= 40)
        & (s.pf >= 1.20)
        & (s.median_ret > 0)
        & (s.win_rate >= 0.52)
        & (s.pos_years >= min_pos_years)
    )
    return s.sort_values(["candidate_flag", "pf", "median_ret", "events"], ascending=[False, False, False, False])


def decision(summary: pd.DataFrame) -> str:
    if summary.empty:
        return "INCONCLUSIVE_NO_EVENTS"
    if int(summary.candidate_flag.sum()) > 0:
        return "MECHANISM_CANDIDATE_FOUND"
    if int(summary.events.sum()) >= 300:
        return "NO_MECHANISM_FOUND_FOR_TESTED_HYPOTHESES"
    return "INCONCLUSIVE_INSUFFICIENT_EVENTS"


def run(db: Path, out_dir: Path, events_path: Path, buffer_usd: float, max_days: int, progress: bool) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = now_iso()
    conn = connect(db)
    intraday, source = load_intraday(conn)
    h4 = load_h4(conn, intraday)
    conn.close()

    intraday = add_day_hour(intraday)
    if max_days and max_days > 0:
        cutoff_days = sorted(set(intraday["_day"]))[-max_days:]
        intraday = intraday[intraday["_day"].isin(cutoff_days)]
        h4 = h4[h4.index >= intraday.index.min() - pd.Timedelta(days=7)]

    if buffer_usd <= 0:
        a = atr(intraday, 96).dropna()
        buffer_usd = max(0.2, float(a.median()) * 0.05) if not a.empty else 0.2

    if progress:
        print(f"Stage14A v2: source={source} rows={len(intraday)} h4_rows={len(h4)} days={intraday['_day'].nunique()} buffer={buffer_usd:.4f}")
        print("Stage14A v2: building day cache...")

    day_cache = build_day_cache(intraday, 0)
    daily = resample_ohlc(intraday.drop(columns=["_day", "_hour"]), "1D")

    groups: Dict[str, List[Event]] = {}

    if progress: print("Stage14A v2: asia/london sweep...")
    groups["asia_london"] = mechanism_asia_london(day_cache, buffer_usd)

    if progress: print("Stage14A v2: london/ny sweep...")
    groups["london_ny"] = mechanism_london_ny(day_cache, buffer_usd)

    if progress: print("Stage14A v2: previous-day sweep...")
    groups["prev_day_sweep"] = mechanism_prev_day_sweep(day_cache, daily, buffer_usd)

    if progress: print("Stage14A v2: news first-spike failure...")
    groups["news_spike_failure"] = mechanism_news_failure(intraday, events_path)

    if progress: print("Stage14A v2: h4 failed breakout...")
    groups["failed_h4_breakout"] = mechanism_h4_failed_break(intraday, h4, buffer_usd)

    all_events = [e for evs in groups.values() for e in evs]

    if progress: print(f"Stage14A v2: evaluating outcomes for {len(all_events)} events...")
    results = evaluate(intraday, all_events, [4, 12, 24])
    summary = summarize(results)
    dec = decision(summary)

    events_df = pd.DataFrame([e.__dict__ for e in all_events])
    events_csv = out_dir / "stage14a_mechanism_events.csv"
    outcomes_csv = out_dir / "stage14a_mechanism_outcomes.csv"
    summary_csv = out_dir / "stage14a_mechanism_summary.csv"
    json_path = out_dir / "stage14a_liquidity_session_behavior_discovery.json"
    md_path = out_dir / "stage14a_liquidity_session_behavior_discovery.md"

    events_df.to_csv(events_csv, index=False)
    results.to_csv(outcomes_csv, index=False)
    summary.to_csv(summary_csv, index=False)

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "db": str(db),
        "intraday_source": source,
        "intraday_rows": int(len(intraday)),
        "h4_rows": int(len(h4)),
        "days": int(intraday["_day"].nunique()),
        "events_path": str(events_path),
        "buffer_usd": round(float(buffer_usd), 6),
        "max_days": int(max_days),
        "mechanism_counts": {k: len(v) for k, v in groups.items()},
        "events_total": int(len(all_events)),
        "outcome_rows": int(len(results)),
        "decision": dec,
        "candidate_count": int(summary.candidate_flag.sum()) if not summary.empty else 0,
        "top": summary.head(10).to_dict(orient="records") if not summary.empty else [],
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    lines = [
        "# Stage 14A Liquidity / Session / Sweep Behavior Discovery",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: research only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Inputs",
        f"- db: `{db}`",
        f"- intraday_source: `{source}`",
        f"- intraday_rows: `{len(intraday)}`",
        f"- days: `{intraday['_day'].nunique()}`",
        f"- h4_rows: `{len(h4)}`",
        f"- events_path: `{events_path}`",
        f"- buffer_usd: `{round(float(buffer_usd), 6)}`",
        f"- max_days: `{max_days}`",
        "",
        "## Decision",
        f"- decision: `{dec}`",
        f"- candidate_count: `{payload['candidate_count']}`",
        "",
        "## Mechanism event counts",
        "| Mechanism group | Events |",
        "|---|---:|",
    ]
    for k, v in payload["mechanism_counts"].items():
        lines.append(f"| {k} | {v} |")

    lines += [
        "",
        "## Top mechanism summaries",
        "| Rank | Mechanism | Side | Horizon bars | Events | Total | Avg | Median | WR | PF | DD | Pos years | Candidate |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    if not summary.empty:
        for i, r in enumerate(summary.head(15).to_dict(orient="records"), 1):
            lines.append(
                f"| {i} | {r['mechanism']} | {r['side']} | {r['horizon_bars']} | {r['events']} | "
                f"{r['total_ret']} | {r['avg_ret']} | {r['median_ret']} | {r['win_rate']} | {r['pf']} | "
                f"{r['max_dd']} | {r['pos_years']}/{r['years']} | {r['candidate_flag']} |"
            )
    else:
        lines.append("| 0 | none | none | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | False |")

    lines += [
        "",
        "## Interpretation rules",
        "- `MECHANISM_CANDIDATE_FOUND` means a behavior deserves focused robustness/replay study.",
        "- `NO_MECHANISM_FOUND_FOR_TESTED_HYPOTHESES` does not mean XAUUSD has no behavior; it means these tested hypotheses did not capture one.",
        "- `INCONCLUSIVE_*` means event extraction or sample size is insufficient.",
        "- Do not convert any candidate directly to EA/paper/live.",
        "",
        "## Output files",
        f"- events_csv: `{events_csv}`",
        f"- outcomes_csv: `{outcomes_csv}`",
        f"- summary_csv: `{summary_csv}`",
        f"- json: `{json_path}`",
        f"- md: `{md_path}`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 14A liquidity/session behavior discovery: DONE")
    print(f"decision={dec} events_total={len(all_events)} candidates={payload['candidate_count']} intraday_source={source}")
    print(f"Report: {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--events", default=str(DEFAULT_EVENTS))
    p.add_argument("--buffer-usd", type=float, default=0.0)
    p.add_argument("--max-days", type=int, default=0, help="Optional: test only latest N days for quick smoke/debug.")
    p.add_argument("--no-progress", action="store_true")
    args = p.parse_args()
    return run(Path(args.db), Path(args.out_dir), Path(args.events), args.buffer_usd, args.max_days, not args.no_progress)


if __name__ == "__main__":
    raise SystemExit(main())
