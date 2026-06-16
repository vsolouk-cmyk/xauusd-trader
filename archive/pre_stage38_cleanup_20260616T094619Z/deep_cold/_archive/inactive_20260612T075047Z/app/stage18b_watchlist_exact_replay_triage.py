#!/usr/bin/env python3
"""
Stage 18B — Watchlist Exact M1 Replay Triage

Purpose:
- Continue behavior discovery after Stage17A.
- Exact-replay the Stage17A WATCHLIST_ONLY candidates using AMarkets MT5 M1 path.
- Promote only candidates that survive exact path, cost stress, chronological splits,
  2026 segment, and year breadth.
- Do not create forward collectors here. Promoted candidates go to a later
  Stage18C/Stage19 forward-shadow design.

Active context:
- Stage18A keeps current Stage16C and Stage17D shadow candidates running.
- Stage18B is discovery-only, parallel to the active shadow ops cycle.

Hard rules:
- Research discovery/triage only.
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


TOOL_VERSION = "v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_OUT_DIR = Path("data/reports/stage18b_watchlist_exact_replay_triage")


@dataclass(frozen=True)
class Variant:
    name: str
    behavior: str
    side: str
    horizon_bars: int
    cooldown_bars: int


WATCHLIST_VARIANTS = [
    Variant("asia_high_breakout_long_h32_cool0", "asia_high_breakout_long", "LONG", 32, 0),
    Variant("asia_high_breakout_long_h32_cool4", "asia_high_breakout_long", "LONG", 32, 4),
    Variant("pdl_sweep_reclaim_long_controlled_h4_cool0", "pdl_sweep_reclaim_long_controlled", "LONG", 4, 0),
    Variant("pdl_sweep_reclaim_long_controlled_h4_cool4", "pdl_sweep_reclaim_long_controlled", "LONG", 4, 4),
    Variant("pdl_sweep_reclaim_long_controlled_h8_cool0", "pdl_sweep_reclaim_long_controlled", "LONG", 8, 0),
    Variant("pdl_sweep_reclaim_long_controlled_h8_cool4", "pdl_sweep_reclaim_long_controlled", "LONG", 8, 4),
    Variant("asia_low_breakdown_short_h32_cool0", "asia_low_breakdown_short", "SHORT", 32, 0),
    Variant("asia_low_breakdown_short_h32_cool4", "asia_low_breakdown_short", "SHORT", 32, 4),
    Variant("pdl_breakdown_continuation_short_h32_cool0", "pdl_breakdown_continuation_short", "SHORT", 32, 0),
    Variant("compressed_range_up_break_long_h8_cool0", "compressed_range_up_break_long", "LONG", 8, 0),
    Variant("compressed_range_up_break_long_h8_cool4", "compressed_range_up_break_long", "LONG", 8, 4),
    Variant("pdh_breakout_continuation_long_h32_cool0", "pdh_breakout_continuation_long", "LONG", 32, 0),
]


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


def add_context(m15: pd.DataFrame, h1: pd.DataFrame) -> pd.DataFrame:
    x = m15.copy()
    x["date"] = x.index.strftime("%Y-%m-%d")
    x["hour"] = x.index.hour
    x["minute"] = x.index.minute
    x["session"] = "other"
    # Broker bar time buckets, same convention as Stage17A/17D.
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

    base = x.reset_index()
    if "utc_time" in base.columns:
        base = base.rename(columns={"utc_time": "dt"})
    else:
        base = base.rename(columns={base.columns[0]: "dt"})
    base = base.merge(prev_df, on="date", how="left")

    asia = base[(base["hour"] >= 0) & (base["hour"] < 7)].groupby("date").agg(
        asia_high=("high", "max"),
        asia_low=("low", "min"),
        asia_open=("open", "first"),
        asia_close=("close", "last"),
    )
    asia["asia_range"] = asia["asia_high"] - asia["asia_low"]
    base = base.merge(asia.reset_index(), on="date", how="left")

    h = h1.copy()
    h["h1_range"] = h["high"] - h["low"]
    h["atr14_h1"] = h["h1_range"].rolling(14, min_periods=5).mean()
    h["compression6"] = h["h1_range"].rolling(6, min_periods=4).mean() / h["atr14_h1"]

    base = pd.merge_asof(
        base.sort_values("dt"),
        h[["h1_range", "atr14_h1", "compression6"]].reset_index().rename(columns={"utc_time": "ctx_dt"}),
        left_on="dt",
        right_on="ctx_dt",
        direction="backward",
    ).drop(columns=["ctx_dt"])

    return base.sort_values("dt").reset_index(drop=True)


def masks_for_context(x: pd.DataFrame, buffer_usd: float) -> Dict[str, pd.Series]:
    valid_prev = x["pdh"].notna() & x["pdl"].notna()
    valid_asia = x["asia_high"].notna() & x["asia_low"].notna()
    active_london_ny = x["session"].isin(["london", "new_york"])

    sweep_low_depth = x["pdl"] - x["low"]
    low_reclaim = x["close"] - x["pdl"]

    comp = x["compression6"].notna() & (x["compression6"] < 0.75)
    rolling_high = x["high"].rolling(12, min_periods=8).max().shift(1)

    return {
        "asia_high_breakout_long": (
            valid_asia
            & active_london_ny
            & (x["close"] > x["asia_high"] + 0.8)
            & (x["asia_range"].between(4.0, 35.0))
        ).fillna(False),
        "asia_low_breakdown_short": (
            valid_asia
            & active_london_ny
            & (x["close"] < x["asia_low"] - 0.8)
            & (x["asia_range"].between(4.0, 35.0))
        ).fillna(False),
        "pdl_sweep_reclaim_long_controlled": (
            valid_prev
            & active_london_ny
            & (x["low"] < x["pdl"] - buffer_usd)
            & (x["close"] > x["pdl"])
            & (sweep_low_depth >= 1.62)
            & (low_reclaim.between(0, 1.55))
        ).fillna(False),
        "pdl_breakdown_continuation_short": (
            valid_prev
            & active_london_ny
            & (x["low"] < x["pdl"] - buffer_usd)
            & (x["close"] < x["pdl"] - 0.8)
        ).fillna(False),
        "compressed_range_up_break_long": (
            comp
            & active_london_ny
            & (x["close"] > rolling_high)
        ).fillna(False),
        "pdh_breakout_continuation_long": (
            valid_prev
            & active_london_ny
            & (x["high"] > x["pdh"] + buffer_usd)
            & (x["close"] > x["pdh"] + 0.8)
        ).fillna(False),
    }


def apply_spacing(indices: Sequence[int], horizon_bars: int, cooldown_bars: int) -> List[int]:
    chosen: List[int] = []
    next_allowed = -1
    for i in indices:
        if i < next_allowed:
            continue
        chosen.append(int(i))
        next_allowed = int(i) + int(horizon_bars) + int(cooldown_bars)
    return chosen


def entry_price_from_m15(m15: pd.DataFrame, entry_dt: pd.Timestamp) -> Tuple[float, str]:
    if entry_dt in m15.index:
        return float(m15.loc[entry_dt]["open"]), "m15_exact_open"
    pos = m15.index.searchsorted(entry_dt)
    if pos < len(m15):
        return float(m15.iloc[pos]["open"]), "m15_next_open"
    return float("nan"), "entry_after_available_data"


def replay_variant(
    v: Variant,
    x: pd.DataFrame,
    m15: pd.DataFrame,
    m1: pd.DataFrame,
    mask: pd.Series,
    cost_usd: float,
) -> pd.DataFrame:
    idxs = x.index[mask].tolist()
    idxs = apply_spacing(idxs, v.horizon_bars, v.cooldown_bars)

    rows = []
    for i in idxs:
        entry_i = i + 1
        if entry_i >= len(x):
            continue
        signal_dt = pd.to_datetime(x.iloc[i]["dt"], utc=True)
        entry_dt = pd.to_datetime(x.iloc[entry_i]["dt"], utc=True)
        exit_dt = entry_dt + pd.Timedelta(minutes=15 * v.horizon_bars)
        entry_price, src = entry_price_from_m15(m15, entry_dt)
        if pd.isna(entry_price):
            continue

        path = m1[(m1.index > entry_dt) & (m1.index <= exit_dt)]
        if path.empty:
            continue

        exit_price = float(path.iloc[-1]["close"])
        if v.side == "LONG":
            gross = exit_price - entry_price
            mfe = float(path["high"].max()) - entry_price
            mae = entry_price - float(path["low"].min())
        else:
            gross = entry_price - exit_price
            mfe = entry_price - float(path["low"].min())
            mae = float(path["high"].max()) - entry_price

        rows.append({
            "variant": v.name,
            "behavior": v.behavior,
            "side": v.side,
            "horizon_bars": v.horizon_bars,
            "horizon_minutes": v.horizon_bars * 15,
            "cooldown_bars": v.cooldown_bars,
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
            "session": str(x.iloc[i].get("session", "")),
            "hour": int(x.iloc[i].get("hour", -1)),
            "pdh": float(x.iloc[i].get("pdh")) if pd.notna(x.iloc[i].get("pdh")) else float("nan"),
            "pdl": float(x.iloc[i].get("pdl")) if pd.notna(x.iloc[i].get("pdl")) else float("nan"),
            "asia_range": float(x.iloc[i].get("asia_range")) if pd.notna(x.iloc[i].get("asia_range")) else float("nan"),
            "compression6": float(x.iloc[i].get("compression6")) if pd.notna(x.iloc[i].get("compression6")) else float("nan"),
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
        return {"events": 0, "total": 0.0, "avg": 0.0, "median": 0.0, "wr": 0.0, "pf": 0.0, "dd": 0.0, "pos_years": 0, "years": 0, "pos_quarters": 0, "quarters": 0, "months": 0}
    x = df.sort_values("entry_dt").copy()
    vals = pd.to_numeric(x[col], errors="coerce").dropna().astype(float).tolist()
    if not vals:
        return {"events": 0, "total": 0.0, "avg": 0.0, "median": 0.0, "wr": 0.0, "pf": 0.0, "dd": 0.0, "pos_years": 0, "years": 0, "pos_quarters": 0, "quarters": 0, "months": 0}
    s = pd.Series(vals)
    years = x.groupby(x["entry_dt"].dt.year)[col].sum()
    quarters = x.groupby(x["entry_dt"].dt.to_period("Q").astype(str))[col].sum()
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
        "months": int(x["entry_dt"].dt.to_period("M").nunique()),
    }


def split_metrics(df: pd.DataFrame, frac: float, col: str = "net_x1") -> Dict:
    x = df.sort_values("entry_dt").reset_index(drop=True)
    cut = int(len(x) * frac)
    return {"frac": frac, "train": metrics(x.iloc[:cut], col), "test": metrics(x.iloc[cut:], col)}


def bootstrap(df: pd.DataFrame, col: str = "net_x1", n: int = 300, seed: int = 18) -> Dict:
    if df.empty:
        return {"n": n, "total_p05": 0.0, "pf_p05": 0.0, "prob_total_gt_0": 0.0, "prob_pf_gt_1": 0.0, "prob_median_gt_0": 0.0}
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


def decide(v: Variant, m1: Dict, m2: Dict, m4: Dict, s80: Dict, s70: Dict, y2026: Dict, boot: Dict) -> Tuple[str, List[str], float]:
    reasons: List[str] = []
    score = 0.0

    if m1["events"] < 80:
        return "REJECT_TOO_FEW_EXACT_EVENTS", ["Exact M1 event count < 80."], -999.0

    score += min(10, m1["pf"] * 3)
    score += min(10, max(0, m1["median"]) * 1.5)
    score += min(10, max(0, s80["test"]["pf"]) * 2)
    score += min(5, max(0, y2026["total"]) / 50.0)
    score += min(5, max(0, boot.get("prob_total_gt_0", 0)) * 5)
    score -= min(10, abs(min(0, m1["dd"])) / 120.0)

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
        and s80["test"]["pf"] >= 1.08
        and s70["test"]["total"] > 0
        and s70["test"]["pf"] >= 1.05
        and (y2026["events"] < 15 or (y2026["total"] > 0 and y2026["pf"] >= 1.00))
        and m1["pos_years"] >= max(3, round(m1["years"] * 0.60))
        and boot.get("prob_total_gt_0", 0) >= 0.90
        and boot.get("pf_p05", 0) >= 1.00
    )
    if promote:
        return "PROMOTE_STAGE18C_FORWARD_SHADOW_DESIGN", ["Exact replay survives costs, splits, 2026, year breadth, and bootstrap."], round(score, 6)

    watch = (
        m1["events"] >= 100
        and m1["total"] > 0
        and m1["pf"] >= 1.08
        and s80["test"]["events"] >= 15
        and s80["test"]["total"] > 0
        and s80["test"]["pf"] >= 1.00
        and boot.get("prob_total_gt_0", 0) >= 0.75
    )
    if watch:
        return "KEEP_WATCHLIST_EXACT_REPLAY_POSITIVE", ["Positive exact replay but not strong enough for forward-shadow design."], round(score, 6)

    return "REJECT_EXACT_REPLAY_WEAK", ["Exact replay does not preserve enough robust edge."], round(score, 6)


def evaluate_variant(v: Variant, trades: pd.DataFrame, bootstrap_n: int) -> Dict:
    m1 = metrics(trades, "net_x1")
    m2 = metrics(trades, "net_x2")
    m4 = metrics(trades, "net_x4")
    s70 = split_metrics(trades, 0.70, "net_x1")
    s80 = split_metrics(trades, 0.80, "net_x1")
    y2026 = metrics(trades[trades["entry_dt"].dt.year == 2026], "net_x1") if not trades.empty else metrics(trades)
    boot = bootstrap(trades, "net_x1", n=bootstrap_n)
    decision, reasons, score = decide(v, m1, m2, m4, s80, s70, y2026, boot)
    freq_per_month = round(m1["events"] / max(1, m1["months"]), 6)
    return {
        "variant": v.name,
        "behavior": v.behavior,
        "side": v.side,
        "horizon_bars": v.horizon_bars,
        "horizon_minutes": v.horizon_bars * 15,
        "cooldown_bars": v.cooldown_bars,
        "decision": decision,
        "score": score,
        "reasons": "; ".join(reasons),
        "events": m1["events"],
        "freq_per_month": freq_per_month,
        "total_x1": m1["total"],
        "avg_x1": m1["avg"],
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
        "test20_median": s80["test"]["median"],
        "test20_pf": s80["test"]["pf"],
        "test30_events": s70["test"]["events"],
        "test30_total": s70["test"]["total"],
        "test30_pf": s70["test"]["pf"],
        "events_2026": y2026["events"],
        "total_2026": y2026["total"],
        "median_2026": y2026["median"],
        "pf_2026": y2026["pf"],
        "pos_years": m1["pos_years"],
        "years": m1["years"],
        "pos_quarters": m1["pos_quarters"],
        "quarters": m1["quarters"],
        "boot_total_p05": boot["total_p05"],
        "boot_pf_p05": boot["pf_p05"],
        "boot_prob_total_gt_0": boot["prob_total_gt_0"],
        "boot_prob_pf_gt_1": boot["prob_pf_gt_1"],
    }


def period_table(all_trades: pd.DataFrame, period: str, col: str = "net_x1") -> pd.DataFrame:
    if all_trades.empty:
        return pd.DataFrame()
    x = all_trades.copy()
    if period == "year":
        x["period"] = x["entry_dt"].dt.year.astype(str)
    elif period == "quarter":
        x["period"] = x["entry_dt"].dt.to_period("Q").astype(str)
    else:
        raise ValueError(period)

    rows = []
    for (variant, p), g in x.groupby(["variant", "period"]):
        row = {"variant": variant, "period": p}
        row.update(metrics(g, col))
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["variant", "period"])


def run(db: Path, out_dir: Path, cost_usd: float, buffer_usd: float, bootstrap_n: int) -> int:
    generated = now_iso()
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = connect(db)
    try:
        m1 = load_m1(conn)
    finally:
        conn.close()

    m15 = resample_ohlc(m1, "15min")
    h1 = resample_ohlc(m1, "1h")
    x = add_context(m15, h1)
    masks = masks_for_context(x, buffer_usd=buffer_usd)

    summaries = []
    parts = []
    for v in WATCHLIST_VARIANTS:
        mask = masks.get(v.behavior, pd.Series(False, index=x.index))
        tr = replay_variant(v, x, m15, m1, mask, cost_usd=cost_usd)
        if not tr.empty:
            parts.append(tr)
        summaries.append(evaluate_variant(v, tr, bootstrap_n=bootstrap_n))

    summary = pd.DataFrame(summaries)
    order = {
        "PROMOTE_STAGE18C_FORWARD_SHADOW_DESIGN": 0,
        "KEEP_WATCHLIST_EXACT_REPLAY_POSITIVE": 1,
        "REJECT_EXACT_REPLAY_WEAK": 2,
        "REJECT_TOO_FEW_EXACT_EVENTS": 3,
    }
    summary["_order"] = summary["decision"].map(order).fillna(9)
    summary = summary.sort_values(["_order", "score", "pf_x1", "events"], ascending=[True, False, False, False]).drop(columns=["_order"])

    all_trades = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    by_year = period_table(all_trades, "year")
    by_quarter = period_table(all_trades, "quarter")

    promoted = summary[summary["decision"].eq("PROMOTE_STAGE18C_FORWARD_SHADOW_DESIGN")].copy()
    exact_watch = summary[summary["decision"].eq("KEEP_WATCHLIST_EXACT_REPLAY_POSITIVE")].copy()

    final_decision = "EXACT_WATCHLIST_PROMOTIONS_FOUND" if len(promoted) else ("EXACT_WATCHLIST_POSITIVE_ONLY" if len(exact_watch) else "NO_WATCHLIST_SURVIVED_EXACT_REPLAY")

    summary_csv = out_dir / "stage18b_watchlist_exact_summary.csv"
    trades_csv = out_dir / "stage18b_watchlist_exact_trades.csv"
    by_year_csv = out_dir / "stage18b_watchlist_exact_by_year.csv"
    by_quarter_csv = out_dir / "stage18b_watchlist_exact_by_quarter.csv"
    promoted_csv = out_dir / "stage18b_promoted_candidates.csv"
    json_path = out_dir / "stage18b_watchlist_exact_replay_triage.json"
    md_path = out_dir / "stage18b_watchlist_exact_replay_triage.md"

    summary.to_csv(summary_csv, index=False)
    all_trades.to_csv(trades_csv, index=False)
    by_year.to_csv(by_year_csv, index=False)
    by_quarter.to_csv(by_quarter_csv, index=False)
    promoted.to_csv(promoted_csv, index=False)

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "inputs": {
            "db": str(db),
            "cost_usd": float(cost_usd),
            "buffer_usd": float(buffer_usd),
            "bootstrap_n": int(bootstrap_n),
        },
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
            "promoted": int(len(promoted)),
            "exact_watchlist_positive": int(len(exact_watch)),
            "rejected": int(summary["decision"].str.startswith("REJECT").sum()),
        },
        "promoted": promoted.to_dict(orient="records"),
        "exact_watchlist_positive": exact_watch.head(20).to_dict(orient="records"),
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
        "# Stage 18B Watchlist Exact M1 Replay Triage",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: research discovery/triage only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Purpose",
        "- Continue discovery while Stage18A keeps active shadow candidates running.",
        "- Exact-replay Stage17A watchlist candidates using AMarkets M1 path.",
        "- Promote only candidates that survive costs, splits, 2026, year breadth, and bootstrap.",
        "",
        "## Inputs",
        f"- db: `{db}`",
        f"- m1_rows: `{len(m1)}`",
        f"- m15_rows: `{len(m15)}`",
        f"- h1_rows: `{len(h1)}`",
        f"- m1_first: `{m1.index.min().isoformat()}`",
        f"- m1_last: `{m1.index.max().isoformat()}`",
        f"- cost_usd: `{cost_usd}`",
        f"- buffer_usd: `{buffer_usd}`",
        "",
        "## Final decision",
        f"- final_decision: `{final_decision}`",
        "",
        "## Counts",
        f"- variants_tested: `{len(summary)}`",
        f"- promoted_to_stage18c: `{len(promoted)}`",
        f"- exact_watchlist_positive: `{len(exact_watch)}`",
        "",
        "## Candidate ranking",
        "| Rank | Variant | Side | Decision | Events | Freq/mo | PF x1 | Median x1 | Total x1 | PF x2 | PF x4 | Test20 events | Test20 total | Test20 PF | 2026 total | 2026 PF | Boot PF p05 | Score |",
        "|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for i, r in enumerate(summary.to_dict(orient="records"), 1):
        lines.append(
            f"| {i} | `{r['variant']}` | {r['side']} | `{r['decision']}` | {r['events']} | {r['freq_per_month']} | {r['pf_x1']} | {r['median_x1']} | {r['total_x1']} | {r['pf_x2']} | {r['pf_x4']} | {r['test20_events']} | {r['test20_total']} | {r['test20_pf']} | {r['total_2026']} | {r['pf_2026']} | {r['boot_pf_p05']} | {r['score']} |"
        )

    lines += [
        "",
        "## Promoted candidates",
    ]
    if not promoted.empty:
        for r in promoted.to_dict(orient="records"):
            lines.append(f"- `{r['variant']}` — {r['reasons']}")
    else:
        lines.append("- none")

    lines += [
        "",
        "## Interpretation",
        "- Stage18B is exact historical replay triage, not forward proof.",
        "- Promoted candidates should go to Stage18C/Stage19 forward-shadow design.",
        "- Positive-but-not-promoted candidates remain research watchlist only.",
        "- Current Stage16C/Stage17D shadow collection should continue through Stage18A.",
        "- No paper/live/order escalation is authorized.",
        "",
        "## Output files",
        f"- summary_csv: `{summary_csv}`",
        f"- promoted_csv: `{promoted_csv}`",
        f"- trades_csv: `{trades_csv}`",
        f"- by_year_csv: `{by_year_csv}`",
        f"- by_quarter_csv: `{by_quarter_csv}`",
        f"- json: `{json_path}`",
        f"- md: `{md_path}`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 18B watchlist exact M1 replay triage: DONE")
    print(f"final_decision={final_decision}")
    print(f"promoted={len(promoted)} exact_watchlist_positive={len(exact_watch)}")
    print(f"Report: {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--cost-usd", type=float, default=0.35)
    p.add_argument("--buffer-usd", type=float, default=0.2)
    p.add_argument("--bootstrap-n", type=int, default=300)
    args = p.parse_args()
    return run(
        db=Path(args.db),
        out_dir=Path(args.out_dir),
        cost_usd=float(args.cost_usd),
        buffer_usd=float(args.buffer_usd),
        bootstrap_n=int(args.bootstrap_n),
    )


if __name__ == "__main__":
    raise SystemExit(main())
