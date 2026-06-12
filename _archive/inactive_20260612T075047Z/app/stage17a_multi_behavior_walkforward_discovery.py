#!/usr/bin/env python3
"""
Stage 17A — Multi-Behavior Walk-Forward Discovery

Purpose:
- Expand research beyond the single Stage16 sweep/reclaim branch.
- Test multiple behavior families in parallel using existing AMarkets MT5 data.
- Use strict chronological train/test checks, cost stress, 2026 segment, frequency,
  and non-overlap execution logic.
- Produce a ranked candidate inventory:
    1) PROMOTE_STAGE17B_EXACT_REPLAY
    2) WATCHLIST_ONLY
    3) REJECT

Important:
- Stage17A is a broad discovery/inventory lab.
- It is NOT forward proof.
- It is NOT an EA/paper/live/order signal.
- Top candidates must go to Stage17B exact M1 replay and then independent shadow.

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
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd


TOOL_VERSION = "v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_OUT_DIR = Path("data/reports/stage17a_multi_behavior_walkforward_discovery")


@dataclass(frozen=True)
class SetupSpec:
    behavior: str
    side: str
    horizon_bars: int
    cooldown_bars: int
    condition_name: str


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(db: Path) -> sqlite3.Connection:
    if not db.exists():
        raise FileNotFoundError(f"DB not found: {db}")
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn


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
    return (
        df.dropna(subset=["utc_time", "open", "high", "low", "close"])
        .sort_values("utc_time")
        .drop_duplicates("utc_time")
        .set_index("utc_time")
    )


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    if df.empty:
        return df
    return df.resample(rule, label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()


def load_intraday(conn: sqlite3.Connection) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, str]:
    m1 = load_bars(conn, "1m")
    if len(m1) > 1000:
        m15 = resample_ohlc(m1, "15min")
        h1 = resample_ohlc(m1, "1h")
        return m15, h1, m1, "m1_to_m15_h1"
    m5 = load_bars(conn, "5m")
    if len(m5) > 1000:
        m15 = resample_ohlc(m5, "15min")
        h1 = resample_ohlc(m5, "1h")
        return m15, h1, pd.DataFrame(), "m5_to_m15_h1"
    m15 = load_bars(conn, "15m")
    if len(m15) > 1000:
        h1 = resample_ohlc(m15, "1h")
        return m15, h1, pd.DataFrame(), "m15_to_h1"
    h1 = load_bars(conn, "1h")
    if len(h1) > 1000:
        return h1, h1, pd.DataFrame(), "h1_fallback"
    raise RuntimeError("No usable AMarkets bars found.")


def add_context(m15: pd.DataFrame, h1: pd.DataFrame) -> pd.DataFrame:
    x = m15.copy()
    x["bar_index"] = range(len(x))
    x["date"] = x.index.strftime("%Y-%m-%d")
    x["hour"] = x.index.hour
    x["minute"] = x.index.minute
    x["session"] = "other"
    x.loc[(x["hour"] >= 0) & (x["hour"] < 7), "session"] = "asia"
    x.loc[(x["hour"] >= 7) & (x["hour"] < 12), "session"] = "london"
    x.loc[(x["hour"] >= 12) & (x["hour"] < 17), "session"] = "new_york"
    x.loc[(x["hour"] >= 17) & (x["hour"] < 22), "session"] = "late_us"

    daily = resample_ohlc(m15, "1D")
    prev_rows = []
    days = list(daily.index.strftime("%Y-%m-%d"))
    for i, day in enumerate(days):
        if i == 0:
            continue
        prev = daily.iloc[i - 1]
        prev_rows.append({
            "date": day,
            "pdh": float(prev["high"]),
            "pdl": float(prev["low"]),
            "prev_range": float(prev["high"] - prev["low"]),
            "prev_mid": float((prev["high"] + prev["low"]) / 2.0),
        })
    prev_df = pd.DataFrame(prev_rows)
    x = x.reset_index().rename(columns={"utc_time": "dt"})
    if "dt" not in x.columns:
        x = x.rename(columns={x.columns[0]: "dt"})
    x = x.merge(prev_df, on="date", how="left")

    # Asia range by day, from 00:00 through 06:59 UTC.
    asia = x[(x["hour"] >= 0) & (x["hour"] < 7)].groupby("date").agg(
        asia_high=("high", "max"),
        asia_low=("low", "min"),
        asia_open=("open", "first"),
        asia_close=("close", "last"),
    )
    asia["asia_range"] = asia["asia_high"] - asia["asia_low"]
    x = x.merge(asia.reset_index(), on="date", how="left")

    # H1/H4 context.
    h = h1.copy()
    h["h1_range"] = h["high"] - h["low"]
    h["atr14_h1"] = h["h1_range"].rolling(14, min_periods=5).mean()
    h["compression6"] = h["h1_range"].rolling(6, min_periods=4).mean() / h["atr14_h1"]
    h["h1_sma20"] = h["close"].rolling(20, min_periods=10).mean()
    h["h1_slope3"] = h["h1_sma20"] - h["h1_sma20"].shift(3)
    h4 = resample_ohlc(h1, "4h")
    h4["h4_sma20"] = h4["close"].rolling(20, min_periods=10).mean()
    h4["h4_slope3"] = h4["h4_sma20"] - h4["h4_sma20"].shift(3)
    h4["h4_up"] = h4["close"] > h4["h4_sma20"]
    h4["h4_down"] = h4["close"] < h4["h4_sma20"]

    x = pd.merge_asof(
        x.sort_values("dt"),
        h[["h1_range", "atr14_h1", "compression6", "h1_sma20", "h1_slope3"]].reset_index().rename(columns={"utc_time": "ctx_dt"}),
        left_on="dt",
        right_on="ctx_dt",
        direction="backward",
    ).drop(columns=["ctx_dt"])

    x = pd.merge_asof(
        x.sort_values("dt"),
        h4[["h4_sma20", "h4_slope3", "h4_up", "h4_down"]].reset_index().rename(columns={"utc_time": "h4_dt"}),
        left_on="dt",
        right_on="h4_dt",
        direction="backward",
    ).drop(columns=["h4_dt"])

    return x.sort_values("dt").reset_index(drop=True)


def build_candidate_masks(x: pd.DataFrame, buffer: float) -> Dict[str, pd.Series]:
    masks: Dict[str, pd.Series] = {}
    valid_prev = x["pdh"].notna() & x["pdl"].notna()
    valid_asia = x["asia_high"].notna() & x["asia_low"].notna()
    active_london_ny = x["session"].isin(["london", "new_york"])
    active_ny_late = x["session"].isin(["new_york", "late_us"])

    sweep_low_depth = x["pdl"] - x["low"]
    sweep_high_depth = x["high"] - x["pdh"]
    low_reclaim = x["close"] - x["pdl"]
    high_reclaim = x["pdh"] - x["close"]

    masks["pdl_sweep_reclaim_long_loose"] = valid_prev & active_london_ny & (x["low"] < x["pdl"] - buffer) & (x["close"] > x["pdl"]) & (sweep_low_depth >= 1.0) & (low_reclaim.between(0, 3.0))
    masks["pdl_sweep_reclaim_long_controlled"] = valid_prev & active_london_ny & (x["low"] < x["pdl"] - buffer) & (x["close"] > x["pdl"]) & (sweep_low_depth >= 1.62) & (low_reclaim.between(0, 1.55))
    masks["pdh_sweep_reject_short_loose"] = valid_prev & active_london_ny & (x["high"] > x["pdh"] + buffer) & (x["close"] < x["pdh"]) & (sweep_high_depth >= 1.0) & (high_reclaim.between(0, 3.0))
    masks["pdh_sweep_reject_short_controlled"] = valid_prev & active_london_ny & (x["high"] > x["pdh"] + buffer) & (x["close"] < x["pdh"]) & (sweep_high_depth >= 1.62) & (high_reclaim.between(0, 1.55))

    masks["pdh_breakout_continuation_long"] = valid_prev & active_london_ny & (x["high"] > x["pdh"] + buffer) & (x["close"] > x["pdh"] + 0.8)
    masks["pdl_breakdown_continuation_short"] = valid_prev & active_london_ny & (x["low"] < x["pdl"] - buffer) & (x["close"] < x["pdl"] - 0.8)

    masks["asia_high_breakout_long"] = valid_asia & active_london_ny & (x["close"] > x["asia_high"] + 0.8) & (x["asia_range"].between(4.0, 35.0))
    masks["asia_low_breakdown_short"] = valid_asia & active_london_ny & (x["close"] < x["asia_low"] - 0.8) & (x["asia_range"].between(4.0, 35.0))
    masks["asia_low_fakeout_reclaim_long"] = valid_asia & active_london_ny & (x["low"] < x["asia_low"] - buffer) & (x["close"] > x["asia_low"]) & ((x["asia_low"] - x["low"]) >= 1.0)
    masks["asia_high_fakeout_reject_short"] = valid_asia & active_london_ny & (x["high"] > x["asia_high"] + buffer) & (x["close"] < x["asia_high"]) & ((x["high"] - x["asia_high"]) >= 1.0)

    # Compression breakout/continuation.
    comp = x["compression6"].notna() & (x["compression6"] < 0.75)
    masks["compressed_range_up_break_long"] = comp & active_london_ny & (x["close"] > x["high"].rolling(12, min_periods=8).max().shift(1))
    masks["compressed_range_down_break_short"] = comp & active_london_ny & (x["close"] < x["low"].rolling(12, min_periods=8).min().shift(1))

    # H4 trend pullback/rejection around H4 SMA20.
    masks["h4_up_sma_reclaim_long"] = active_ny_late & (x["h4_up"].fillna(False)) & (x["low"] < x["h4_sma20"]) & (x["close"] > x["h4_sma20"]) & (x["h4_slope3"] > 0)
    masks["h4_down_sma_reject_short"] = active_ny_late & (x["h4_down"].fillna(False)) & (x["high"] > x["h4_sma20"]) & (x["close"] < x["h4_sma20"]) & (x["h4_slope3"] < 0)

    return {k: v.fillna(False) for k, v in masks.items()}


def side_for_behavior(name: str) -> str:
    return "SHORT" if name.endswith("_short") or "_short_" in name or "short" in name else "LONG"


def apply_spacing(indices: Sequence[int], horizon_bars: int, cooldown_bars: int) -> List[int]:
    chosen = []
    next_allowed = -1
    for i in indices:
        if i < next_allowed:
            continue
        chosen.append(int(i))
        # Non-overlap until the trade exits, plus small cooldown.
        next_allowed = int(i) + int(horizon_bars) + int(cooldown_bars)
    return chosen


def replay_signals(x: pd.DataFrame, behavior: str, mask: pd.Series, horizon_bars: int, cooldown_bars: int, cost_usd: float) -> pd.DataFrame:
    side = side_for_behavior(behavior)
    idxs = x.index[mask].tolist()
    idxs = apply_spacing(idxs, horizon_bars=horizon_bars, cooldown_bars=cooldown_bars)
    rows = []
    n = len(x)
    for i in idxs:
        entry_i = i + 1
        exit_i = entry_i + horizon_bars
        if entry_i >= n or exit_i >= n:
            continue
        entry = float(x.iloc[entry_i]["open"])
        exitp = float(x.iloc[exit_i]["close"])
        gross = exitp - entry if side == "LONG" else entry - exitp
        path = x.iloc[entry_i:exit_i + 1]
        if side == "LONG":
            mfe = float(path["high"].max()) - entry
            mae = entry - float(path["low"].min())
        else:
            mfe = entry - float(path["low"].min())
            mae = float(path["high"].max()) - entry
        rows.append({
            "behavior": behavior,
            "side": side,
            "condition_name": behavior,
            "horizon_bars": horizon_bars,
            "cooldown_bars": cooldown_bars,
            "signal_dt": x.iloc[i]["dt"],
            "entry_dt": x.iloc[entry_i]["dt"],
            "exit_dt": x.iloc[exit_i]["dt"],
            "entry_price": round(entry, 6),
            "exit_price": round(exitp, 6),
            "gross_ret": round(gross, 6),
            "net_x1": round(gross - cost_usd, 6),
            "net_x2": round(gross - 2 * cost_usd, 6),
            "net_x4": round(gross - 4 * cost_usd, 6),
            "mfe": round(mfe, 6),
            "mae": round(mae, 6),
            "session": x.iloc[i].get("session", ""),
            "hour": int(x.iloc[i].get("hour", -1)),
            "pdh": x.iloc[i].get("pdh", float("nan")),
            "pdl": x.iloc[i].get("pdl", float("nan")),
            "asia_range": x.iloc[i].get("asia_range", float("nan")),
            "compression6": x.iloc[i].get("compression6", float("nan")),
            "h4_up": bool(x.iloc[i].get("h4_up", False)),
            "h4_down": bool(x.iloc[i].get("h4_down", False)),
        })
    return pd.DataFrame(rows)


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
    months = x["entry_dt"].dt.to_period("M").nunique()
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
        "months": int(months),
    }


def split_metrics(df: pd.DataFrame, frac: float = 0.80, col: str = "net_x1") -> Dict:
    x = df.sort_values("entry_dt").reset_index(drop=True)
    cut = int(len(x) * frac)
    return {"train": metrics(x.iloc[:cut], col), "test": metrics(x.iloc[cut:], col), "frac": float(frac)}


def year_table(df: pd.DataFrame, col: str = "net_x1") -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    rows = []
    x = df.copy()
    x["year"] = x["entry_dt"].dt.year
    for y, g in x.groupby("year"):
        m = metrics(g, col)
        m["year"] = int(y)
        rows.append(m)
    return pd.DataFrame(rows).sort_values("year")


def decide_candidate(all_m: Dict, x2_m: Dict, x4_m: Dict, split80: Dict, seg2026: Dict) -> Tuple[str, List[str], float]:
    reasons = []
    score = 0.0

    if all_m["events"] < 40:
        return "REJECT_TOO_FEW_EVENTS", ["events < 40"], -999.0

    # scoring
    score += min(10, all_m["pf"] * 3)
    score += min(10, max(0, all_m["median"]) * 1.5)
    score += min(10, max(0, split80["test"]["pf"]) * 2)
    score += min(5, max(0, x2_m["total"]) / 100.0)
    score += min(5, max(0, seg2026["total"]) / 50.0)
    score -= min(10, abs(min(0, all_m["dd"])) / 100.0)

    promote = (
        all_m["events"] >= 80
        and all_m["total"] > 0
        and all_m["pf"] >= 1.15
        and all_m["median"] > 0
        and x2_m["total"] > 0
        and x4_m["pf"] >= 1.00
        and split80["test"]["events"] >= 15
        and split80["test"]["total"] > 0
        and split80["test"]["pf"] >= 1.10
        and all_m["pos_years"] >= max(3, round(all_m["years"] * 0.60))
        and (seg2026["events"] < 10 or seg2026["pf"] >= 1.00)
    )
    if promote:
        reasons.append("Passed frequency, cost, 80/20 test, year breadth, and 2026 checks.")
        return "PROMOTE_STAGE17B_EXACT_REPLAY", reasons, round(score, 6)

    watch = (
        all_m["events"] >= 60
        and all_m["total"] > 0
        and all_m["pf"] >= 1.08
        and split80["test"]["events"] >= 10
        and split80["test"]["total"] > 0
        and split80["test"]["pf"] >= 1.00
    )
    if watch:
        reasons.append("Positive but not strong enough for promotion.")
        return "WATCHLIST_ONLY", reasons, round(score, 6)

    reasons.append("Failed strict promotion/watchlist checks.")
    return "REJECT", reasons, round(score, 6)


def evaluate_behavior(trades: pd.DataFrame, behavior: str, horizon: int, cooldown: int) -> Dict:
    all_m = metrics(trades, "net_x1")
    x2_m = metrics(trades, "net_x2")
    x4_m = metrics(trades, "net_x4")
    s80 = split_metrics(trades, 0.80, "net_x1")
    s70 = split_metrics(trades, 0.70, "net_x1")
    seg2026 = metrics(trades[trades["entry_dt"].dt.year == 2026], "net_x1") if not trades.empty else metrics(trades)
    decision, reasons, score = decide_candidate(all_m, x2_m, x4_m, s80, seg2026)
    freq_per_month = round(all_m["events"] / max(1, all_m["months"]), 6)
    return {
        "behavior": behavior,
        "side": side_for_behavior(behavior),
        "horizon_bars": int(horizon),
        "horizon_minutes": int(horizon * 15),
        "cooldown_bars": int(cooldown),
        "decision": decision,
        "score": score,
        "reasons": "; ".join(reasons),
        "events": all_m["events"],
        "freq_per_month": freq_per_month,
        "total_x1": all_m["total"],
        "avg_x1": all_m["avg"],
        "median_x1": all_m["median"],
        "wr_x1": all_m["wr"],
        "pf_x1": all_m["pf"],
        "dd_x1": all_m["dd"],
        "total_x2": x2_m["total"],
        "pf_x2": x2_m["pf"],
        "total_x4": x4_m["total"],
        "pf_x4": x4_m["pf"],
        "train80_events": s80["train"]["events"],
        "train80_total": s80["train"]["total"],
        "train80_pf": s80["train"]["pf"],
        "test20_events": s80["test"]["events"],
        "test20_total": s80["test"]["total"],
        "test20_median": s80["test"]["median"],
        "test20_pf": s80["test"]["pf"],
        "test30_events": s70["test"]["events"],
        "test30_total": s70["test"]["total"],
        "test30_pf": s70["test"]["pf"],
        "events_2026": seg2026["events"],
        "total_2026": seg2026["total"],
        "median_2026": seg2026["median"],
        "pf_2026": seg2026["pf"],
        "pos_years": all_m["pos_years"],
        "years": all_m["years"],
    }


def run(db: Path, out_dir: Path, cost_usd: float, buffer_usd: float, max_rows: int) -> int:
    generated = now_iso()
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = connect(db)
    try:
        m15, h1, m1, source = load_intraday(conn)
    finally:
        conn.close()

    if max_rows > 0 and len(m15) > max_rows:
        m15 = m15.tail(max_rows).copy()
        h1 = h1[h1.index >= m15.index.min() - pd.Timedelta(days=10)].copy()

    x = add_context(m15, h1)
    masks = build_candidate_masks(x, buffer=buffer_usd)
    horizons = [4, 8, 16, 32]
    cooldowns = [0, 4]

    summary_rows = []
    trades_parts = []
    year_parts = []
    for behavior, mask in masks.items():
        for horizon in horizons:
            for cooldown in cooldowns:
                tr = replay_signals(x, behavior, mask, horizon_bars=horizon, cooldown_bars=cooldown, cost_usd=cost_usd)
                if tr.empty:
                    continue
                tag = f"{behavior}_h{horizon}_cool{cooldown}"
                tr["variant"] = tag
                trades_parts.append(tr)
                row = evaluate_behavior(tr, behavior, horizon, cooldown)
                row["variant"] = tag
                summary_rows.append(row)
                yt = year_table(tr, "net_x1")
                if not yt.empty:
                    yt["variant"] = tag
                    yt["behavior"] = behavior
                    yt["horizon_bars"] = horizon
                    yt["cooldown_bars"] = cooldown
                    year_parts.append(yt)

    summary = pd.DataFrame(summary_rows)
    all_trades = pd.concat(trades_parts, ignore_index=True) if trades_parts else pd.DataFrame()
    years = pd.concat(year_parts, ignore_index=True) if year_parts else pd.DataFrame()

    if not summary.empty:
        summary = summary.sort_values(["decision", "score", "pf_x1", "test20_pf"], ascending=[True, False, False, False])
        # Custom order
        order = {"PROMOTE_STAGE17B_EXACT_REPLAY": 0, "WATCHLIST_ONLY": 1, "REJECT": 2, "REJECT_TOO_FEW_EVENTS": 3}
        summary["_order"] = summary["decision"].map(order).fillna(9)
        summary = summary.sort_values(["_order", "score", "pf_x1", "events"], ascending=[True, False, False, False]).drop(columns=["_order"])

    summary_csv = out_dir / "stage17a_behavior_summary.csv"
    trades_csv = out_dir / "stage17a_all_behavior_trades.csv"
    years_csv = out_dir / "stage17a_year_breakdown.csv"
    top_csv = out_dir / "stage17a_promoted_candidates.csv"
    json_path = out_dir / "stage17a_multi_behavior_walkforward_discovery.json"
    md_path = out_dir / "stage17a_multi_behavior_walkforward_discovery.md"

    summary.to_csv(summary_csv, index=False)
    all_trades.to_csv(trades_csv, index=False)
    years.to_csv(years_csv, index=False)
    promoted = summary[summary["decision"].eq("PROMOTE_STAGE17B_EXACT_REPLAY")].copy() if not summary.empty else pd.DataFrame()
    watch = summary[summary["decision"].eq("WATCHLIST_ONLY")].copy() if not summary.empty else pd.DataFrame()
    promoted.to_csv(top_csv, index=False)

    final_decision = "MULTI_BEHAVIOR_CANDIDATES_FOUND" if len(promoted) else ("WATCHLIST_BEHAVIORS_FOUND" if len(watch) else "NO_BEHAVIOR_CANDIDATES_FOUND")
    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "inputs": {
            "db": str(db),
            "cost_usd": float(cost_usd),
            "buffer_usd": float(buffer_usd),
            "max_rows": int(max_rows),
        },
        "source": {
            "intraday_source": source,
            "m15_rows": int(len(m15)),
            "h1_rows": int(len(h1)),
            "m15_first": m15.index.min().isoformat() if not m15.empty else None,
            "m15_last": m15.index.max().isoformat() if not m15.empty else None,
            "behaviors_tested": int(len(masks)),
            "variants_tested": int(len(summary)),
        },
        "final_decision": final_decision,
        "counts": {
            "promoted": int(len(promoted)),
            "watchlist": int(len(watch)),
            "rejected": int((summary["decision"].str.startswith("REJECT")).sum()) if not summary.empty else 0,
        },
        "top_promoted": promoted.head(20).to_dict(orient="records") if not promoted.empty else [],
        "top_watchlist": watch.head(20).to_dict(orient="records") if not watch.empty else [],
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
        "# Stage 17A Multi-Behavior Walk-Forward Discovery",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: research discovery only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Purpose",
        "- Keep Stage16 true-forward collection running.",
        "- Expand discovery to multiple independent behavior families.",
        "- Promote only behavior variants that pass strict historical walk-forward checks.",
        "",
        "## Inputs",
        f"- db: `{db}`",
        f"- intraday_source: `{source}`",
        f"- m15_rows: `{len(m15)}`",
        f"- h1_rows: `{len(h1)}`",
        f"- m15_first: `{m15.index.min().isoformat() if not m15.empty else None}`",
        f"- m15_last: `{m15.index.max().isoformat() if not m15.empty else None}`",
        f"- cost_usd: `{cost_usd}`",
        f"- buffer_usd: `{buffer_usd}`",
        "",
        "## Final decision",
        f"- final_decision: `{final_decision}`",
        "",
        "## Counts",
        f"- behaviors_tested: `{len(masks)}`",
        f"- variants_tested: `{len(summary)}`",
        f"- promoted_to_stage17b: `{len(promoted)}`",
        f"- watchlist_only: `{len(watch)}`",
        "",
        "## Top promoted candidates",
        "| Rank | Variant | Side | Events | Freq/mo | PF x1 | Median x1 | Total x1 | PF x2 | PF x4 | Test20 events | Test20 total | Test20 PF | 2026 total | 2026 PF | Score |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    if not promoted.empty:
        for i, r in enumerate(promoted.head(30).to_dict(orient="records"), 1):
            lines.append(
                f"| {i} | `{r['variant']}` | {r['side']} | {r['events']} | {r['freq_per_month']} | {r['pf_x1']} | {r['median_x1']} | {r['total_x1']} | {r['pf_x2']} | {r['pf_x4']} | {r['test20_events']} | {r['test20_total']} | {r['test20_pf']} | {r['total_2026']} | {r['pf_2026']} | {r['score']} |"
            )
    else:
        lines.append("| 0 | none | none | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |")

    lines += [
        "",
        "## Top watchlist candidates",
        "| Rank | Variant | Side | Decision | Events | PF x1 | Median x1 | Test20 PF | 2026 PF | Reason |",
        "|---:|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    if not watch.empty:
        for i, r in enumerate(watch.head(20).to_dict(orient="records"), 1):
            lines.append(
                f"| {i} | `{r['variant']}` | {r['side']} | {r['decision']} | {r['events']} | {r['pf_x1']} | {r['median_x1']} | {r['test20_pf']} | {r['pf_2026']} | {r['reasons']} |"
            )
    else:
        lines.append("| 0 | none | none | none | 0 | 0 | 0 | 0 | 0 | none |")

    lines += [
        "",
        "## Behavior families tested",
    ]
    for b in sorted(masks.keys()):
        lines.append(f"- `{b}`")

    lines += [
        "",
        "## Interpretation",
        "- Stage17A is a broad historical discovery lab.",
        "- Promoted candidates are not tradable yet; they require Stage17B exact M1 replay/robustness.",
        "- Watchlist candidates can be revisited but should not enter forward shadow directly.",
        "- Stage16 true-forward collector should continue in parallel.",
        "- No paper/live/order authorization is granted.",
        "",
        "## Output files",
        f"- summary_csv: `{summary_csv}`",
        f"- promoted_csv: `{top_csv}`",
        f"- trades_csv: `{trades_csv}`",
        f"- years_csv: `{years_csv}`",
        f"- json: `{json_path}`",
        f"- md: `{md_path}`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 17A multi-behavior walk-forward discovery: DONE")
    print(f"final_decision={final_decision}")
    print(f"behaviors_tested={len(masks)} variants_tested={len(summary)} promoted={len(promoted)} watchlist={len(watch)}")
    print(f"Report: {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--cost-usd", type=float, default=0.35)
    p.add_argument("--buffer-usd", type=float, default=0.2)
    p.add_argument("--max-rows", type=int, default=0, help="Optional tail limit for faster debugging. Default 0 = all.")
    args = p.parse_args()
    return run(
        db=Path(args.db),
        out_dir=Path(args.out_dir),
        cost_usd=float(args.cost_usd),
        buffer_usd=float(args.buffer_usd),
        max_rows=int(args.max_rows),
    )


if __name__ == "__main__":
    raise SystemExit(main())
