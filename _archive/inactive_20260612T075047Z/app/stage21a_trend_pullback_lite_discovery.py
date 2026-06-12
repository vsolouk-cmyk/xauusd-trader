#!/usr/bin/env python3
"""
Stage 21A — Trend Pullback and Exhaustion Lite Discovery

Purpose:
- Continue discovery after Stage20A did not produce a forward-shadow promotion.
- Avoid repeating heavy exhaustive grids.
- Explore less-redundant behavior families:
    1) H1 trend pullback continuation long/short
    2) M15 impulse exhaustion reversal long/short
    3) NY open continuation after London trend
- Use fast M15 proxy replay first.
- Promote only promising candidates to a later exact M1 replay.

Hard rules:
- Research discovery only.
- M15 proxy replay only.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence

import pandas as pd


TOOL_VERSION = "v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_OUT_DIR = Path("data/reports/stage21a_trend_pullback_lite_discovery")

warnings.filterwarnings(
    "ignore",
    message="Converting to PeriodArray/Index representation will drop timezone information.",
    category=UserWarning,
)


@dataclass(frozen=True)
class Variant:
    name: str
    family: str
    side: str
    horizon_bars: int
    cooldown_bars: int
    params: Dict


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
    x = m15.copy()
    x["date"] = x.index.strftime("%Y-%m-%d")
    x["hour"] = x.index.hour
    x["minute"] = x.index.minute
    x["session"] = "other"
    x.loc[(x["hour"] >= 0) & (x["hour"] < 7), "session"] = "asia"
    x.loc[(x["hour"] >= 7) & (x["hour"] < 12), "session"] = "london"
    x.loc[(x["hour"] >= 12) & (x["hour"] < 17), "session"] = "new_york"
    x.loc[(x["hour"] >= 17) & (x["hour"] < 22), "session"] = "late_us"

    base = x.reset_index()
    if "utc_time" in base.columns:
        base = base.rename(columns={"utc_time": "dt"})
    else:
        base = base.rename(columns={base.columns[0]: "dt"})

    # M15 local features
    base["m15_range"] = base["high"] - base["low"]
    base["m15_body"] = base["close"] - base["open"]
    base["m15_body_abs"] = base["m15_body"].abs()
    base["m15_atr32"] = base["m15_range"].rolling(32, min_periods=16).mean()
    base["ema20_m15"] = base["close"].ewm(span=20, min_periods=20).mean()
    base["ema50_m15"] = base["close"].ewm(span=50, min_periods=50).mean()
    base["ret4"] = base["close"] - base["close"].shift(4)
    base["ret8"] = base["close"] - base["close"].shift(8)
    base["rolling_high12"] = base["high"].rolling(12, min_periods=8).max().shift(1)
    base["rolling_low12"] = base["low"].rolling(12, min_periods=8).min().shift(1)

    # London summary
    london = base[(base["hour"] >= 7) & (base["hour"] < 12)].groupby("date").agg(
        london_high=("high", "max"),
        london_low=("low", "min"),
        london_open=("open", "first"),
        london_close=("close", "last"),
    )
    london["london_range"] = london["london_high"] - london["london_low"]
    london["london_bias"] = london["london_close"] - london["london_open"]
    base = base.merge(london.reset_index(), on="date", how="left")

    h = h1.copy()
    h["h1_range"] = h["high"] - h["low"]
    h["atr14_h1"] = h["h1_range"].rolling(14, min_periods=5).mean()
    h["sma20_h1"] = h["close"].rolling(20, min_periods=20).mean()
    h["sma50_h1"] = h["close"].rolling(50, min_periods=50).mean()
    h["sma20_slope5"] = h["sma20_h1"] - h["sma20_h1"].shift(5)
    h["h1_close_minus_sma20"] = h["close"] - h["sma20_h1"]
    h["h1_close_minus_sma50"] = h["close"] - h["sma50_h1"]

    hr = h[["h1_range", "atr14_h1", "sma20_h1", "sma50_h1", "sma20_slope5", "h1_close_minus_sma20", "h1_close_minus_sma50"]].reset_index()
    hr = hr.rename(columns={hr.columns[0]: "ctx_dt"})

    base = pd.merge_asof(
        base.sort_values("dt"),
        hr.sort_values("ctx_dt"),
        left_on="dt",
        right_on="ctx_dt",
        direction="backward",
    ).drop(columns=["ctx_dt"])

    return base.sort_values("dt").reset_index(drop=True)


def build_variants(fast: bool = False) -> List[Variant]:
    variants: List[Variant] = []

    trend_distances = [0.0, 2.0, 5.0] if not fast else [2.0]
    pullback_bands = [0.5, 1.5, 3.0] if not fast else [1.5]
    horizons = [4, 8, 16] if not fast else [8]
    sessions = ["london_new_york", "new_york_only"] if not fast else ["london_new_york"]

    for side in ["LONG", "SHORT"]:
        for trend_dist in trend_distances:
            for pullback in pullback_bands:
                for h in horizons:
                    for sess in sessions:
                        fam = f"trend_pullback_continuation_{side.lower()}"
                        variants.append(Variant(
                            name=f"{fam}_trend{trend_dist:g}_pull{pullback:g}_{sess}_h{h}",
                            family=fam,
                            side=side,
                            horizon_bars=h,
                            cooldown_bars=4,
                            params={"trend_dist": trend_dist, "pullback": pullback, "session_set": sess},
                        ))

    # Impulse exhaustion reversal: large short-term move and reversal close.
    impulse_mults = [1.5, 2.0, 2.5] if not fast else [2.0]
    reject_bars = [4, 8] if not fast else [4]
    for side in ["LONG", "SHORT"]:
        for mult in impulse_mults:
            for lookback in reject_bars:
                for h in [4, 8, 16] if not fast else [8]:
                    fam = f"m15_impulse_exhaustion_reversal_{side.lower()}"
                    variants.append(Variant(
                        name=f"{fam}_imp{mult:g}_lb{lookback}_h{h}",
                        family=fam,
                        side=side,
                        horizon_bars=h,
                        cooldown_bars=4,
                        params={"impulse_mult": mult, "lookback": lookback, "session_set": "london_new_york"},
                    ))

    # NY open continuation after strong London trend.
    for side in ["LONG", "SHORT"]:
        for bias_min in ([2.0, 4.0, 6.0] if not fast else [4.0]):
            for h in ([4, 8, 16, 24] if not fast else [8]):
                fam = f"ny_open_london_trend_continuation_{side.lower()}"
                variants.append(Variant(
                    name=f"{fam}_bias{bias_min:g}_h{h}",
                    family=fam,
                    side=side,
                    horizon_bars=h,
                    cooldown_bars=4,
                    params={"bias_min": bias_min, "session_set": "new_york_only"},
                ))

    return variants


def session_mask(x: pd.DataFrame, session_set: str) -> pd.Series:
    if session_set == "london_new_york":
        return x["session"].isin(["london", "new_york"])
    if session_set == "new_york_only":
        return x["session"].eq("new_york")
    if session_set == "london_only":
        return x["session"].eq("london")
    return pd.Series(False, index=x.index)


def mask_for_variant(x: pd.DataFrame, v: Variant) -> pd.Series:
    p = v.params
    sess = session_mask(x, str(p.get("session_set", "london_new_york")))

    if v.family == "trend_pullback_continuation_long":
        trend = (
            x["sma20_h1"].notna()
            & x["sma50_h1"].notna()
            & (x["sma20_slope5"] > 0)
            & (x["h1_close_minus_sma20"] >= float(p["trend_dist"]))
        )
        pull = (x["low"] <= x["ema20_m15"] + float(p["pullback"])) & (x["close"] > x["ema20_m15"])
        return (sess & trend & pull).fillna(False)

    if v.family == "trend_pullback_continuation_short":
        trend = (
            x["sma20_h1"].notna()
            & x["sma50_h1"].notna()
            & (x["sma20_slope5"] < 0)
            & (x["h1_close_minus_sma20"] <= -float(p["trend_dist"]))
        )
        pull = (x["high"] >= x["ema20_m15"] - float(p["pullback"])) & (x["close"] < x["ema20_m15"])
        return (sess & trend & pull).fillna(False)

    if v.family == "m15_impulse_exhaustion_reversal_long":
        lookback = int(p["lookback"])
        impulse = x["close"].shift(lookback) - x["close"]
        reversal = x["close"] > x["open"]
        return (sess & x["m15_atr32"].notna() & (impulse >= float(p["impulse_mult"]) * x["m15_atr32"]) & reversal).fillna(False)

    if v.family == "m15_impulse_exhaustion_reversal_short":
        lookback = int(p["lookback"])
        impulse = x["close"] - x["close"].shift(lookback)
        reversal = x["close"] < x["open"]
        return (sess & x["m15_atr32"].notna() & (impulse >= float(p["impulse_mult"]) * x["m15_atr32"]) & reversal).fillna(False)

    if v.family == "ny_open_london_trend_continuation_long":
        return (
            x["session"].eq("new_york")
            & x["london_high"].notna()
            & (x["london_bias"] >= float(p["bias_min"]))
            & (x["close"] > x["london_high"])
        ).fillna(False)

    if v.family == "ny_open_london_trend_continuation_short":
        return (
            x["session"].eq("new_york")
            & x["london_low"].notna()
            & (x["london_bias"] <= -float(p["bias_min"]))
            & (x["close"] < x["london_low"])
        ).fillna(False)

    return pd.Series(False, index=x.index)


def apply_spacing(indices: Sequence[int], horizon_bars: int, cooldown_bars: int) -> List[int]:
    chosen = []
    next_allowed = -1
    for i in indices:
        if i < next_allowed:
            continue
        chosen.append(int(i))
        next_allowed = int(i) + int(horizon_bars) + int(cooldown_bars)
    return chosen


def replay_m15_proxy(v: Variant, x: pd.DataFrame, cost_usd: float) -> pd.DataFrame:
    mask = mask_for_variant(x, v)
    idxs = apply_spacing(x.index[mask].tolist(), v.horizon_bars, v.cooldown_bars)
    rows = []
    for i in idxs:
        entry_i = i + 1
        exit_i = entry_i + v.horizon_bars
        if entry_i >= len(x) or exit_i >= len(x):
            continue

        signal_dt = pd.to_datetime(x.iloc[i]["dt"], utc=True)
        entry_dt = pd.to_datetime(x.iloc[entry_i]["dt"], utc=True)
        exit_dt = pd.to_datetime(x.iloc[exit_i]["dt"], utc=True)
        entry_price = float(x.iloc[entry_i]["open"])
        exit_price = float(x.iloc[exit_i]["close"])
        gross = exit_price - entry_price if v.side == "LONG" else entry_price - exit_price

        rows.append({
            "variant": v.name,
            "family": v.family,
            "side": v.side,
            "horizon_bars": v.horizon_bars,
            "horizon_minutes": v.horizon_bars * 15,
            "cooldown_bars": v.cooldown_bars,
            "params_json": json.dumps(v.params, sort_keys=True),
            "signal_dt": signal_dt,
            "entry_dt": entry_dt,
            "exit_dt": exit_dt,
            "entry_price": round(entry_price, 6),
            "exit_price": round(exit_price, 6),
            "gross_ret": round(gross, 6),
            "net_x1": round(gross - cost_usd, 6),
            "net_x2": round(gross - 2 * cost_usd, 6),
            "net_x4": round(gross - 4 * cost_usd, 6),
            "session": str(x.iloc[i].get("session", "")),
            "hour": int(x.iloc[i].get("hour", -1)),
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
        return {"events": 0, "total": 0.0, "avg": 0.0, "median": 0.0, "wr": 0.0, "pf": 0.0, "dd": 0.0, "pos_years": 0, "years": 0, "months": 0}
    x = df.sort_values("entry_dt").copy()
    vals = pd.to_numeric(x[col], errors="coerce").dropna().astype(float).tolist()
    if not vals:
        return {"events": 0, "total": 0.0, "avg": 0.0, "median": 0.0, "wr": 0.0, "pf": 0.0, "dd": 0.0, "pos_years": 0, "years": 0, "months": 0}
    s = pd.Series(vals)
    years = x.groupby(x["entry_dt"].dt.year)[col].sum()
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
        "months": int(period_no_tz(x["entry_dt"], "M").nunique()),
    }


def split_metrics(df: pd.DataFrame, frac: float, col: str = "net_x1") -> Dict:
    x = df.sort_values("entry_dt").reset_index(drop=True)
    cut = int(len(x) * frac)
    return {"frac": frac, "train": metrics(x.iloc[:cut], col), "test": metrics(x.iloc[cut:], col)}


def evaluate(v: Variant, trades: pd.DataFrame) -> Dict:
    m1 = metrics(trades, "net_x1")
    m2 = metrics(trades, "net_x2")
    m4 = metrics(trades, "net_x4")
    s70 = split_metrics(trades, 0.70, "net_x1")
    s80 = split_metrics(trades, 0.80, "net_x1")
    y2026 = metrics(trades[trades["entry_dt"].dt.year == 2026], "net_x1") if not trades.empty else metrics(trades)

    score = 0.0
    score += min(8, m1["pf"] * 2.5)
    score += min(5, max(0, m1["median"]) * 1.2)
    score += min(6, max(0, s80["test"]["pf"]) * 1.5)
    score += min(4, max(0, y2026["total"]) / 80.0)
    score -= min(6, abs(min(0, m1["dd"])) / 200.0)

    decision = "REJECT_LITE_WEAK"
    if (
        m1["events"] >= 120
        and m1["total"] > 0
        and m1["pf"] >= 1.12
        and m1["median"] > 0
        and m2["total"] > 0
        and m4["pf"] >= 0.95
        and s80["test"]["events"] >= 20
        and s80["test"]["total"] > 0
        and s80["test"]["pf"] >= 1.05
        and s70["test"]["total"] > 0
        and (y2026["events"] < 15 or y2026["total"] > 0)
        and m1["pos_years"] >= max(3, round(m1["years"] * 0.55))
    ):
        decision = "PROMOTE_STAGE21B_EXACT_REPLAY"
    elif (
        m1["events"] >= 80
        and m1["total"] > 0
        and m1["pf"] >= 1.05
        and s80["test"]["events"] >= 15
        and s80["test"]["total"] > 0
    ):
        decision = "KEEP_LITE_WATCHLIST"

    return {
        "variant": v.name,
        "family": v.family,
        "side": v.side,
        "horizon_bars": v.horizon_bars,
        "horizon_minutes": v.horizon_bars * 15,
        "cooldown_bars": v.cooldown_bars,
        "params_json": json.dumps(v.params, sort_keys=True),
        "decision": decision,
        "score": round(score, 6),
        "events": m1["events"],
        "freq_per_month": round(m1["events"] / max(1, m1["months"]), 6),
        "total_x1": m1["total"],
        "median_x1": m1["median"],
        "wr_x1": m1["wr"],
        "pf_x1": m1["pf"],
        "dd_x1": m1["dd"],
        "total_x2": m2["total"],
        "pf_x2": m2["pf"],
        "total_x4": m4["total"],
        "pf_x4": m4["pf"],
        "test20_events": s80["test"]["events"],
        "test20_total": s80["test"]["total"],
        "test20_pf": s80["test"]["pf"],
        "test30_events": s70["test"]["events"],
        "test30_total": s70["test"]["total"],
        "test30_pf": s70["test"]["pf"],
        "events_2026": y2026["events"],
        "total_2026": y2026["total"],
        "pf_2026": y2026["pf"],
        "pos_years": m1["pos_years"],
        "years": m1["years"],
    }


def run(db: Path, out_dir: Path, cost_usd: float, fast: bool, top_n_trades: int) -> int:
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
    variants = build_variants(fast=fast)

    summary_rows = []
    trade_parts = []
    for v in variants:
        trades = replay_m15_proxy(v, ctx, cost_usd=cost_usd)
        summary_rows.append(evaluate(v, trades))
        if not trades.empty:
            trade_parts.append(trades)

    summary = pd.DataFrame(summary_rows)
    order = {"PROMOTE_STAGE21B_EXACT_REPLAY": 0, "KEEP_LITE_WATCHLIST": 1, "REJECT_LITE_WEAK": 2}
    summary["_order"] = summary["decision"].map(order).fillna(9)
    summary = summary.sort_values(["_order", "score", "pf_x1", "events"], ascending=[True, False, False, False]).drop(columns=["_order"])

    all_trades = pd.concat(trade_parts, ignore_index=True) if trade_parts else pd.DataFrame()
    promoted = summary[summary["decision"].eq("PROMOTE_STAGE21B_EXACT_REPLAY")].copy()
    watch = summary[summary["decision"].eq("KEEP_LITE_WATCHLIST")].copy()

    if top_n_trades > 0 and not all_trades.empty:
        keep = summary.head(top_n_trades)["variant"].tolist()
        trades_out = all_trades[all_trades["variant"].isin(keep)].copy()
    else:
        trades_out = all_trades

    final_decision = "TREND_PULLBACK_CANDIDATES_FOR_EXACT_REPLAY" if len(promoted) else ("TREND_PULLBACK_WATCHLIST_ONLY" if len(watch) else "NO_TREND_PULLBACK_CANDIDATES")

    summary_csv = out_dir / "stage21a_trend_pullback_lite_summary.csv"
    promoted_csv = out_dir / "stage21a_promote_to_exact_replay.csv"
    trades_csv = out_dir / "stage21a_trend_pullback_lite_trades.csv"
    json_path = out_dir / "stage21a_trend_pullback_lite_discovery.json"
    md_path = out_dir / "stage21a_trend_pullback_lite_discovery.md"

    summary.to_csv(summary_csv, index=False)
    promoted.to_csv(promoted_csv, index=False)
    trades_out.to_csv(trades_csv, index=False)

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "inputs": {"db": str(db), "cost_usd": float(cost_usd), "fast": bool(fast), "top_n_trades": int(top_n_trades)},
        "source": {
            "m1_rows": int(len(m1)),
            "m15_rows": int(len(m15)),
            "h1_rows": int(len(h1)),
            "m1_first": m1.index.min().isoformat(),
            "m1_last": m1.index.max().isoformat(),
            "variants_tested": int(len(summary)),
        },
        "final_decision": final_decision,
        "counts": {
            "promoted_to_stage21b": int(len(promoted)),
            "lite_watchlist": int(len(watch)),
            "variants_tested": int(len(summary)),
        },
        "promoted": promoted.to_dict(orient="records"),
        "watchlist": watch.head(20).to_dict(orient="records"),
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
        "# Stage 21A Trend Pullback and Exhaustion Lite Discovery",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: research discovery only. M15 proxy replay only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Purpose",
        "- Continue discovery after Stage20A produced watchlist-only results.",
        "- Use fast M15 proxy replay, not exact execution replay.",
        "- Explore trend pullback, impulse exhaustion, and NY continuation families.",
        "",
        "## Inputs",
        f"- db: `{db}`",
        f"- m1_rows: `{len(m1)}`",
        f"- m15_rows: `{len(m15)}`",
        f"- h1_rows: `{len(h1)}`",
        f"- m1_first: `{m1.index.min().isoformat()}`",
        f"- m1_last: `{m1.index.max().isoformat()}`",
        f"- cost_usd: `{cost_usd}`",
        f"- variants_tested: `{len(summary)}`",
        f"- fast: `{fast}`",
        "",
        "## Final decision",
        f"- final_decision: `{final_decision}`",
        "",
        "## Counts",
        f"- promoted_to_stage21b: `{len(promoted)}`",
        f"- lite_watchlist: `{len(watch)}`",
        "",
        "## Top variants",
        "| Rank | Variant | Family | Side | Decision | Events | Freq/mo | PF x1 | Median x1 | Total x1 | PF x4 | Test20 events | Test20 total | Test20 PF | 2026 total | 2026 PF | Score |",
        "|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for i, r in enumerate(summary.head(30).to_dict(orient="records"), 1):
        lines.append(
            f"| {i} | `{r['variant']}` | `{r['family']}` | {r['side']} | `{r['decision']}` | {r['events']} | {r['freq_per_month']} | {r['pf_x1']} | {r['median_x1']} | {r['total_x1']} | {r['pf_x4']} | {r['test20_events']} | {r['test20_total']} | {r['test20_pf']} | {r['total_2026']} | {r['pf_2026']} | {r['score']} |"
        )

    lines += ["", "## Promoted to exact replay"]
    if not promoted.empty:
        for r in promoted.to_dict(orient="records"):
            lines.append(f"- `{r['variant']}` ({r['family']}, {r['side']})")
    else:
        lines.append("- none")

    lines += [
        "",
        "## Interpretation",
        "- Stage21A is M15 proxy discovery only, not exact M1 replay.",
        "- Promoted candidates must go to Stage21B exact M1 replay before any forward-shadow design.",
        "- Do not add Stage21A candidates to Stage18A directly.",
        "- Continue Stage18A v2 separately for active forward-shadow tracking.",
        "- No paper/live/order escalation is authorized.",
        "",
        "## Output files",
        f"- summary_csv: `{summary_csv}`",
        f"- promoted_csv: `{promoted_csv}`",
        f"- trades_csv: `{trades_csv}`",
        f"- json: `{json_path}`",
        f"- md: `{md_path}`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 21A trend pullback lite discovery: DONE")
    print(f"final_decision={final_decision}")
    print(f"promoted_to_stage21b={len(promoted)} lite_watchlist={len(watch)} variants_tested={len(summary)}")
    print(f"Report: {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--cost-usd", type=float, default=0.35)
    p.add_argument("--fast", action="store_true")
    p.add_argument("--top-n-trades", type=int, default=30)
    args = p.parse_args()

    return run(
        db=Path(args.db),
        out_dir=Path(args.out_dir),
        cost_usd=float(args.cost_usd),
        fast=bool(args.fast),
        top_n_trades=int(args.top_n_trades),
    )


if __name__ == "__main__":
    raise SystemExit(main())
