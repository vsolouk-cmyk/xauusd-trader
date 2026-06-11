#!/usr/bin/env python3
"""
Stage 21B — Trend Pullback Continuation Short Exact M1 Replay

Purpose:
- Stage21A lite discovery promoted one M15-proxy candidate:
    trend_pullback_continuation_short_trend5_pull0.5_new_york_only_h8
- Stage21B validates it with exact M1 path replay.
- This is validation only, not a forward collector.

Candidate:
- family: trend_pullback_continuation_short
- side: SHORT
- H1 trend filter:
    sma20_slope5 < 0
    h1_close_minus_sma20 <= -5.0
- M15 pullback/rejection:
    high >= ema20_m15 - 0.5
    close < ema20_m15
- session:
    New York only, broker-time buckets
- entry:
    next M15 open
- exit:
    time exit after 8 M15 bars = 120 minutes
- cooldown:
    4 M15 bars
- cost:
    0.35 USD default

Hard rules:
- Research validation only.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import pandas as pd


TOOL_VERSION = "v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_OUT_DIR = Path("data/reports/stage21b_trend_pullback_short_exact_replay")

warnings.filterwarnings(
    "ignore",
    message="Converting to PeriodArray/Index representation will drop timezone information.",
    category=UserWarning,
)

VARIANT = "trend_pullback_continuation_short_trend5_pull0.5_new_york_only_h8"
FAMILY = "trend_pullback_continuation_short"
SIDE = "SHORT"
TREND_DIST = 5.0
PULLBACK = 0.5
HORIZON_BARS = 8
HORIZON_MINUTES = 120
COOLDOWN_BARS = 4


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(db: Path) -> sqlite3.Connection:
    if not db.exists():
        raise FileNotFoundError(f"DB not found: {db}")
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn


def load_m1(conn: sqlite3.Connection) -> pd.DataFrame:
    rows = conn.execute(
        """
        SELECT utc_time, open, high, low, close
        FROM bars
        WHERE source='amarkets_mt5' AND symbol='XAUUSD' AND timeframe='1m'
        ORDER BY utc_time
        """
    ).fetchall()
    if not rows:
        raise RuntimeError("No AMarkets MT5 M1 bars found.")
    df = pd.DataFrame([dict(r) for r in rows])
    df["utc_time"] = pd.to_datetime(df["utc_time"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return (
        df.dropna(subset=["utc_time", "open", "high", "low", "close"])
        .sort_values("utc_time")
        .drop_duplicates("utc_time")
        .set_index("utc_time")
    )


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    return df.resample(rule, label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()


def period_no_tz(series: pd.Series, freq: str) -> pd.Series:
    dt = pd.to_datetime(series, utc=True, errors="coerce")
    return dt.dt.tz_localize(None).dt.to_period(freq)


def add_context(m15: pd.DataFrame, h1: pd.DataFrame) -> pd.DataFrame:
    base = m15.copy()
    base["date"] = base.index.strftime("%Y-%m-%d")
    base["hour"] = base.index.hour
    base["minute"] = base.index.minute
    base["session"] = "other"
    base.loc[(base["hour"] >= 0) & (base["hour"] < 7), "session"] = "asia"
    base.loc[(base["hour"] >= 7) & (base["hour"] < 12), "session"] = "london"
    base.loc[(base["hour"] >= 12) & (base["hour"] < 17), "session"] = "new_york"
    base.loc[(base["hour"] >= 17) & (base["hour"] < 22), "session"] = "late_us"

    x = base.reset_index()
    if "utc_time" in x.columns:
        x = x.rename(columns={"utc_time": "dt"})
    else:
        x = x.rename(columns={x.columns[0]: "dt"})

    # M15 EMA context
    x["ema20_m15"] = x["close"].ewm(span=20, min_periods=20).mean()
    x["ema50_m15"] = x["close"].ewm(span=50, min_periods=50).mean()
    x["m15_range"] = x["high"] - x["low"]

    # H1 trend context
    h = h1.copy()
    h["h1_range"] = h["high"] - h["low"]
    h["sma20_h1"] = h["close"].rolling(20, min_periods=20).mean()
    h["sma50_h1"] = h["close"].rolling(50, min_periods=50).mean()
    h["sma20_slope5"] = h["sma20_h1"] - h["sma20_h1"].shift(5)
    h["h1_close_minus_sma20"] = h["close"] - h["sma20_h1"]
    h["h1_close_minus_sma50"] = h["close"] - h["sma50_h1"]

    hr = h[[
        "h1_range", "sma20_h1", "sma50_h1", "sma20_slope5",
        "h1_close_minus_sma20", "h1_close_minus_sma50"
    ]].reset_index()
    hr = hr.rename(columns={hr.columns[0]: "ctx_dt"})

    out = pd.merge_asof(
        x.sort_values("dt"),
        hr.sort_values("ctx_dt"),
        left_on="dt",
        right_on="ctx_dt",
        direction="backward",
    ).drop(columns=["ctx_dt"])
    return out.sort_values("dt").reset_index(drop=True)


def signal_mask(x: pd.DataFrame) -> pd.Series:
    trend = (
        x["sma20_h1"].notna()
        & x["sma50_h1"].notna()
        & (x["sma20_slope5"] < 0)
        & (x["h1_close_minus_sma20"] <= -TREND_DIST)
    )
    pullback_reject = (
        x["ema20_m15"].notna()
        & (x["high"] >= x["ema20_m15"] - PULLBACK)
        & (x["close"] < x["ema20_m15"])
    )
    return (x["session"].eq("new_york") & trend & pullback_reject).fillna(False)


def apply_spacing(indices: Sequence[int], horizon_bars: int, cooldown_bars: int) -> List[int]:
    chosen = []
    next_allowed = -1
    for i in indices:
        if i < next_allowed:
            continue
        chosen.append(int(i))
        next_allowed = int(i) + int(horizon_bars) + int(cooldown_bars)
    return chosen


def get_entry_price(m15: pd.DataFrame, entry_dt: pd.Timestamp) -> Tuple[float, str]:
    if entry_dt in m15.index:
        return float(m15.loc[entry_dt]["open"]), "m15_exact_open"
    pos = m15.index.searchsorted(entry_dt)
    if pos < len(m15):
        return float(m15.iloc[pos]["open"]), "m15_next_open"
    return float("nan"), "entry_after_available_data"


def replay_exact_m1(ctx: pd.DataFrame, m15: pd.DataFrame, m1: pd.DataFrame, cost_usd: float) -> pd.DataFrame:
    mask = signal_mask(ctx)
    idxs = apply_spacing(ctx.index[mask].tolist(), HORIZON_BARS, COOLDOWN_BARS)
    rows = []

    for i in idxs:
        entry_i = i + 1
        if entry_i >= len(ctx):
            continue
        signal_dt = pd.to_datetime(ctx.iloc[i]["dt"], utc=True)
        entry_dt = pd.to_datetime(ctx.iloc[entry_i]["dt"], utc=True)
        exit_dt = entry_dt + pd.Timedelta(minutes=HORIZON_MINUTES)
        entry_price, src = get_entry_price(m15, entry_dt)
        if pd.isna(entry_price):
            continue
        path = m1[(m1.index > entry_dt) & (m1.index <= exit_dt)]
        if path.empty:
            continue

        exit_price = float(path.iloc[-1]["close"])
        gross = float(entry_price) - exit_price  # SHORT
        mfe = float(entry_price) - float(path["low"].min())
        mae = float(path["high"].max()) - float(entry_price)

        rows.append({
            "variant": VARIANT,
            "family": FAMILY,
            "side": SIDE,
            "trend_dist": TREND_DIST,
            "pullback": PULLBACK,
            "horizon_bars": HORIZON_BARS,
            "horizon_minutes": HORIZON_MINUTES,
            "cooldown_bars": COOLDOWN_BARS,
            "signal_dt": signal_dt,
            "entry_dt": entry_dt,
            "exit_dt": exit_dt,
            "entry_price": round(float(entry_price), 6),
            "entry_price_source": src,
            "exit_price": round(exit_price, 6),
            "gross_ret": round(gross, 6),
            "net_x1": round(gross - cost_usd, 6),
            "net_x2": round(gross - 2 * cost_usd, 6),
            "net_x4": round(gross - 4 * cost_usd, 6),
            "mfe": round(mfe, 6),
            "mae": round(mae, 6),
            "session": str(ctx.iloc[i].get("session", "")),
            "hour": int(ctx.iloc[i].get("hour", -1)),
            "ema20_m15": float(ctx.iloc[i].get("ema20_m15")) if pd.notna(ctx.iloc[i].get("ema20_m15")) else float("nan"),
            "sma20_h1": float(ctx.iloc[i].get("sma20_h1")) if pd.notna(ctx.iloc[i].get("sma20_h1")) else float("nan"),
            "sma20_slope5": float(ctx.iloc[i].get("sma20_slope5")) if pd.notna(ctx.iloc[i].get("sma20_slope5")) else float("nan"),
            "h1_close_minus_sma20": float(ctx.iloc[i].get("h1_close_minus_sma20")) if pd.notna(ctx.iloc[i].get("h1_close_minus_sma20")) else float("nan"),
            "signal_close": float(ctx.iloc[i].get("close")),
            "signal_high": float(ctx.iloc[i].get("high")),
        })

    out = pd.DataFrame(rows)
    if not out.empty:
        for c in ["signal_dt", "entry_dt", "exit_dt"]:
            out[c] = pd.to_datetime(out[c], utc=True, errors="coerce")
        out = out.sort_values("entry_dt").reset_index(drop=True)
    return out


def profit_factor(vals: Sequence[float]) -> float:
    vals = [float(v) for v in vals]
    wins = sum(v for v in vals if v > 0)
    losses = abs(sum(v for v in vals if v < 0))
    if losses == 0:
        return 999.0 if wins > 0 else 0.0
    return round(wins / losses, 6)


def max_dd(vals: Sequence[float]) -> float:
    eq = peak = 0.0
    dd = 0.0
    for v in vals:
        eq += float(v)
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return round(dd, 6)


def metrics(df: pd.DataFrame, col: str = "net_x1") -> Dict:
    if df.empty or col not in df.columns:
        return {
            "events": 0, "total": 0.0, "avg": 0.0, "median": 0.0, "wr": 0.0,
            "pf": 0.0, "dd": 0.0, "pos_years": 0, "years": 0,
            "pos_quarters": 0, "quarters": 0, "months": 0,
        }
    x = df.sort_values("entry_dt").copy()
    vals = pd.to_numeric(x[col], errors="coerce").dropna().astype(float).tolist()
    if not vals:
        return {
            "events": 0, "total": 0.0, "avg": 0.0, "median": 0.0, "wr": 0.0,
            "pf": 0.0, "dd": 0.0, "pos_years": 0, "years": 0,
            "pos_quarters": 0, "quarters": 0, "months": 0,
        }
    s = pd.Series(vals)
    years = x.groupby(x["entry_dt"].dt.year)[col].sum()
    quarters = x.groupby(period_no_tz(x["entry_dt"], "Q").astype(str))[col].sum()
    return {
        "events": int(len(vals)),
        "total": round(float(s.sum()), 6),
        "avg": round(float(s.mean()), 6),
        "median": round(float(s.median()), 6),
        "wr": round(float((s > 0).mean()), 6),
        "pf": profit_factor(vals),
        "dd": max_dd(vals),
        "pos_years": int((years > 0).sum()),
        "years": int(len(years)),
        "pos_quarters": int((quarters > 0).sum()),
        "quarters": int(len(quarters)),
        "months": int(period_no_tz(x["entry_dt"], "M").nunique()),
    }


def split_metrics(df: pd.DataFrame, frac: float, col: str = "net_x1") -> Dict:
    x = df.sort_values("entry_dt").reset_index(drop=True)
    cut = int(len(x) * frac)
    return {"frac": frac, "train": metrics(x.iloc[:cut], col), "test": metrics(x.iloc[cut:], col)}


def bootstrap(df: pd.DataFrame, col: str = "net_x1", n: int = 300, seed: int = 21) -> Dict:
    if df.empty:
        return {
            "n": n, "total_p05": 0.0, "total_p50": 0.0, "pf_p05": 0.0,
            "pf_p50": 0.0, "median_p05": 0.0, "prob_total_gt_0": 0.0,
            "prob_pf_gt_1": 0.0, "prob_median_gt_0": 0.0,
        }
    x = df.sort_values("entry_dt").reset_index(drop=True)
    totals, pfs, meds = [], [], []
    for i in range(n):
        s = x.sample(n=len(x), replace=True, random_state=seed + i)
        vals = pd.to_numeric(s[col], errors="coerce").dropna().astype(float).tolist()
        totals.append(sum(vals))
        pfs.append(profit_factor(vals))
        meds.append(float(pd.Series(vals).median()) if vals else 0.0)
    ts, ps, ms = pd.Series(totals), pd.Series(pfs), pd.Series(meds)
    return {
        "n": int(n),
        "total_p05": round(float(ts.quantile(0.05)), 6),
        "total_p50": round(float(ts.quantile(0.50)), 6),
        "pf_p05": round(float(ps.quantile(0.05)), 6),
        "pf_p50": round(float(ps.quantile(0.50)), 6),
        "median_p05": round(float(ms.quantile(0.05)), 6),
        "prob_total_gt_0": round(float((ts > 0).mean()), 6),
        "prob_pf_gt_1": round(float((ps > 1).mean()), 6),
        "prob_median_gt_0": round(float((ms > 0).mean()), 6),
    }


def period_table(trades: pd.DataFrame, period: str) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    x = trades.copy()
    if period == "year":
        x["period"] = x["entry_dt"].dt.year.astype(str)
    elif period == "quarter":
        x["period"] = period_no_tz(x["entry_dt"], "Q").astype(str)
    elif period == "month":
        x["period"] = period_no_tz(x["entry_dt"], "M").astype(str)
    else:
        raise ValueError(period)
    rows = []
    for p, g in x.groupby("period"):
        row = {"period": p}
        row.update(metrics(g, "net_x1"))
        rows.append(row)
    return pd.DataFrame(rows).sort_values("period")


def decide(m1: Dict, m2: Dict, m4: Dict, s80: Dict, s70: Dict, y2026: Dict, boot: Dict) -> Tuple[str, List[str]]:
    if m1["events"] < 80:
        return "EXACT_REPLAY_REJECT_TOO_FEW_EVENTS", ["Exact M1 event count < 80."]

    promote = (
        m1["events"] >= 120
        and m1["total"] > 0
        and m1["pf"] >= 1.15
        and m1["median"] > 0
        and m2["total"] > 0
        and m2["pf"] >= 1.08
        and m4["pf"] >= 1.00
        and s80["test"]["events"] >= 20
        and s80["test"]["total"] > 0
        and s80["test"]["pf"] >= 1.05
        and s70["test"]["total"] > 0
        and (y2026["events"] < 15 or (y2026["total"] > 0 and y2026["pf"] >= 1.00))
        and m1["pos_years"] >= max(3, round(m1["years"] * 0.55))
        and boot["prob_total_gt_0"] >= 0.90
        and boot["pf_p05"] >= 1.00
    )
    if promote:
        return "EXACT_REPLAY_PROMOTE_TO_FORWARD_SHADOW_DESIGN", ["Candidate survived exact M1 replay, cost stress, splits, 2026, year breadth, and bootstrap."]

    watch = (
        m1["events"] >= 80
        and m1["total"] > 0
        and m1["pf"] >= 1.05
        and s80["test"]["events"] >= 15
        and s80["test"]["total"] > 0
        and boot["prob_total_gt_0"] >= 0.75
    )
    if watch:
        return "EXACT_REPLAY_KEEP_WATCHLIST_ONLY", ["Exact M1 replay is positive but not strong enough for forward-shadow design."]

    return "EXACT_REPLAY_REJECT_WEAK", ["Exact M1 replay does not preserve enough robust edge."]


def run(db: Path, out_dir: Path, cost_usd: float, bootstrap_n: int) -> int:
    generated = now_iso()
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = connect(db)
    try:
        m1 = load_m1(conn)
    finally:
        conn.close()

    m15 = resample_ohlc(m1, "15min")
    h1 = resample_ohlc(m1, "1h")
    ctx = add_context(m15, h1)
    trades = replay_exact_m1(ctx, m15, m1, cost_usd=cost_usd)

    mx1 = metrics(trades, "net_x1")
    mx2 = metrics(trades, "net_x2")
    mx4 = metrics(trades, "net_x4")
    s70 = split_metrics(trades, 0.70, "net_x1")
    s80 = split_metrics(trades, 0.80, "net_x1")
    y2026 = metrics(trades[trades["entry_dt"].dt.year == 2026], "net_x1") if not trades.empty else metrics(trades)
    boot = bootstrap(trades, "net_x1", bootstrap_n)

    final_decision, reasons = decide(mx1, mx2, mx4, s80, s70, y2026, boot)

    by_year = period_table(trades, "year")
    by_quarter = period_table(trades, "quarter")
    by_month = period_table(trades, "month")

    trades_csv = out_dir / "stage21b_exact_trades.csv"
    by_year_csv = out_dir / "stage21b_exact_by_year.csv"
    by_quarter_csv = out_dir / "stage21b_exact_by_quarter.csv"
    by_month_csv = out_dir / "stage21b_exact_by_month.csv"
    json_path = out_dir / "stage21b_trend_pullback_short_exact_replay.json"
    md_path = out_dir / "stage21b_trend_pullback_short_exact_replay.md"

    trades.to_csv(trades_csv, index=False)
    by_year.to_csv(by_year_csv, index=False)
    by_quarter.to_csv(by_quarter_csv, index=False)
    by_month.to_csv(by_month_csv, index=False)

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "candidate": {
            "variant": VARIANT,
            "family": FAMILY,
            "side": SIDE,
            "trend_dist": TREND_DIST,
            "pullback": PULLBACK,
            "horizon_bars": HORIZON_BARS,
            "horizon_minutes": HORIZON_MINUTES,
            "cooldown_bars": COOLDOWN_BARS,
            "cost_usd": float(cost_usd),
        },
        "source": {
            "m1_rows": int(len(m1)),
            "m15_rows": int(len(m15)),
            "h1_rows": int(len(h1)),
            "m1_first": m1.index.min().isoformat(),
            "m1_last": m1.index.max().isoformat(),
        },
        "metrics": {
            "net_x1": mx1,
            "net_x2": mx2,
            "net_x4": mx4,
            "split70": s70,
            "split80": s80,
            "year2026": y2026,
            "bootstrap": boot,
        },
        "final_decision": final_decision,
        "reasons": reasons,
        "authorization_flags": {
            "trade_authorization": False,
            "ea_change_authorization": False,
            "paper_order_authorization": False,
            "live_order_authorization": False,
            "automatic_trading": False,
        },
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    lines = [
        "# Stage 21B Trend Pullback Continuation Short Exact M1 Replay",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: research validation only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Candidate",
        f"- variant: `{VARIANT}`",
        f"- family: `{FAMILY}`",
        f"- side: `{SIDE}`",
        f"- condition: `H1 downtrend + New York-only M15 pullback/rejection below EMA20`",
        f"- trend_dist: `{TREND_DIST}`",
        f"- pullback: `{PULLBACK}`",
        f"- horizon_bars: `{HORIZON_BARS}`",
        f"- horizon_minutes: `{HORIZON_MINUTES}`",
        f"- cooldown_bars: `{COOLDOWN_BARS}`",
        f"- cost_usd: `{cost_usd}`",
        "",
        "## Source",
        f"- db: `{db}`",
        f"- m1_rows: `{len(m1)}`",
        f"- m15_rows: `{len(m15)}`",
        f"- h1_rows: `{len(h1)}`",
        f"- m1_first: `{m1.index.min().isoformat()}`",
        f"- m1_last: `{m1.index.max().isoformat()}`",
        "",
        "## Final decision",
        f"- final_decision: `{final_decision}`",
        "",
        "## Reasons",
    ]
    for r in reasons:
        lines.append(f"- {r}")

    lines += [
        "",
        "## Exact M1 time-exit metrics",
        "| Cost model | Events | Total | Avg | Median | WR | PF | DD | Pos years | Years | Pos quarters | Quarters |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| net_x1 | {mx1['events']} | {mx1['total']} | {mx1['avg']} | {mx1['median']} | {mx1['wr']} | {mx1['pf']} | {mx1['dd']} | {mx1['pos_years']} | {mx1['years']} | {mx1['pos_quarters']} | {mx1['quarters']} |",
        f"| net_x2 | {mx2['events']} | {mx2['total']} | {mx2['avg']} | {mx2['median']} | {mx2['wr']} | {mx2['pf']} | {mx2['dd']} | {mx2['pos_years']} | {mx2['years']} | {mx2['pos_quarters']} | {mx2['quarters']} |",
        f"| net_x4 | {mx4['events']} | {mx4['total']} | {mx4['avg']} | {mx4['median']} | {mx4['wr']} | {mx4['pf']} | {mx4['dd']} | {mx4['pos_years']} | {mx4['years']} | {mx4['pos_quarters']} | {mx4['quarters']} |",
        "",
        "## Chronological splits",
        "| Split | Segment | Events | Total | Median | PF | DD |",
        "|---|---|---:|---:|---:|---:|---:|",
        f"| 70/30 | train | {s70['train']['events']} | {s70['train']['total']} | {s70['train']['median']} | {s70['train']['pf']} | {s70['train']['dd']} |",
        f"| 70/30 | test | {s70['test']['events']} | {s70['test']['total']} | {s70['test']['median']} | {s70['test']['pf']} | {s70['test']['dd']} |",
        f"| 80/20 | train | {s80['train']['events']} | {s80['train']['total']} | {s80['train']['median']} | {s80['train']['pf']} | {s80['train']['dd']} |",
        f"| 80/20 | test | {s80['test']['events']} | {s80['test']['total']} | {s80['test']['median']} | {s80['test']['pf']} | {s80['test']['dd']} |",
        "",
        "## 2026 segment",
        f"- events: `{y2026['events']}`",
        f"- total: `{y2026['total']}`",
        f"- median: `{y2026['median']}`",
        f"- pf: `{y2026['pf']}`",
        f"- dd: `{y2026['dd']}`",
        "",
        "## Bootstrap",
        f"- n: `{boot['n']}`",
        f"- total_p05: `{boot['total_p05']}`",
        f"- total_p50: `{boot['total_p50']}`",
        f"- pf_p05: `{boot['pf_p05']}`",
        f"- pf_p50: `{boot['pf_p50']}`",
        f"- median_p05: `{boot['median_p05']}`",
        f"- prob_total_gt_0: `{boot['prob_total_gt_0']}`",
        f"- prob_pf_gt_1: `{boot['prob_pf_gt_1']}`",
        f"- prob_median_gt_0: `{boot['prob_median_gt_0']}`",
        "",
        "## Interpretation",
        "- Stage21B is exact historical validation, not forward proof.",
        "- Promotion here only allows later forward-shadow collector design.",
        "- Do not add this candidate to Stage18A unless the final decision is promotion.",
        "- No paper/live/order escalation is authorized.",
        "",
        "## Output files",
        f"- trades_csv: `{trades_csv}`",
        f"- by_year_csv: `{by_year_csv}`",
        f"- by_quarter_csv: `{by_quarter_csv}`",
        f"- by_month_csv: `{by_month_csv}`",
        f"- json: `{json_path}`",
        f"- md: `{md_path}`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 21B trend pullback short exact M1 replay: DONE")
    print(f"final_decision={final_decision}")
    print(f"events={mx1['events']} total={mx1['total']} pf={mx1['pf']} median={mx1['median']}")
    print(f"Report: {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--cost-usd", type=float, default=0.35)
    p.add_argument("--bootstrap-n", type=int, default=300)
    args = p.parse_args()
    return run(
        db=Path(args.db),
        out_dir=Path(args.out_dir),
        cost_usd=float(args.cost_usd),
        bootstrap_n=int(args.bootstrap_n),
    )


if __name__ == "__main__":
    raise SystemExit(main())
