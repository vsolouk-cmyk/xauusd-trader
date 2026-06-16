#!/usr/bin/env python3
"""
Stage 18C — Near-Miss Refinement Lab

Purpose:
- Stage18B found 10 exact-positive watchlist candidates but no promotion.
- This stage does NOT forward-shadow them directly.
- It refines only the strongest near-miss families to see whether a more robust
  variant can satisfy promotion criteria.

Families refined:
1) pdl_sweep_reclaim_long_controlled
   - Previous-day low sweep + reclaim long
   - Main weakness in Stage18B: cost x4 fragility / not enough robustness

2) asia_high_breakout_long
   - Asia high breakout continuation long
   - Main weakness in Stage18B: cost x4 fragility but high frequency and strong test

Hard rules:
- Research refinement only.
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
from typing import Dict, Iterable, List, Sequence, Tuple

import pandas as pd


TOOL_VERSION = "v2_timezone_warning_fix"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_OUT_DIR = Path("data/reports/stage18c_near_miss_refinement_lab")

warnings.filterwarnings(
    "ignore",
    message="Converting to PeriodArray/Index representation will drop timezone information.",
    category=UserWarning,
)


def period_no_tz(series: pd.Series, freq: str) -> pd.Series:
    """Convert tz-aware datetimes to Period without noisy pandas timezone warning."""
    dt = pd.to_datetime(series, utc=True, errors="coerce")
    # Convert to timezone-naive timestamp intentionally before to_period.
    return dt.dt.tz_localize(None).dt.to_period(freq)



@dataclass(frozen=True)
class Variant:
    family: str
    name: str
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


def add_context(m15: pd.DataFrame) -> pd.DataFrame:
    x = m15.copy()
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
    return base.sort_values("dt").reset_index(drop=True)


def session_mask(x: pd.DataFrame, session_set: str) -> pd.Series:
    if session_set == "london_new_york":
        return x["session"].isin(["london", "new_york"])
    if session_set == "london_only":
        return x["session"].eq("london")
    if session_set == "new_york_only":
        return x["session"].eq("new_york")
    if session_set == "ny_late":
        return x["session"].isin(["new_york", "late_us"])
    return pd.Series(False, index=x.index)


def apply_spacing(indices: Sequence[int], horizon_bars: int, cooldown_bars: int) -> List[int]:
    chosen: List[int] = []
    next_allowed = -1
    for i in indices:
        if i < next_allowed:
            continue
        chosen.append(int(i))
        next_allowed = int(i) + int(horizon_bars) + int(cooldown_bars)
    return chosen


def build_variants(fast: bool = False) -> List[Variant]:
    variants: List[Variant] = []

    # Keep grid intentionally focused to reduce overfitting and runtime.
    pdl_sweep_mins = [1.25, 1.62, 2.0, 2.5, 3.0]
    pdl_reclaim_maxs = [1.0, 1.55, 2.0, 3.0]
    pdl_sessions = ["london_new_york", "new_york_only"]
    pdl_horizons = [3, 4, 6, 8]
    pdl_cooldowns = [0, 4]

    asia_close_aboves = [0.8, 1.2, 1.6, 2.0]
    asia_ranges = [(4.0, 35.0), (4.0, 25.0), (6.0, 30.0), (8.0, 35.0)]
    asia_sessions = ["london_new_york", "london_only", "new_york_only"]
    asia_horizons = [24, 32, 48]
    asia_cooldowns = [0, 4]

    if fast:
        pdl_sweep_mins = [1.62, 2.0, 2.5]
        pdl_reclaim_maxs = [1.0, 1.55]
        pdl_horizons = [4, 6]
        asia_close_aboves = [0.8, 1.2]
        asia_ranges = [(4.0, 35.0), (6.0, 30.0)]
        asia_horizons = [32]

    for sweep_min in pdl_sweep_mins:
        for reclaim_max in pdl_reclaim_maxs:
            for sess in pdl_sessions:
                for h in pdl_horizons:
                    for cool in pdl_cooldowns:
                        name = f"pdl_sweep_reclaim_long_sweep{sweep_min:g}_reclaim{reclaim_max:g}_{sess}_h{h}_cool{cool}"
                        variants.append(Variant(
                            family="pdl_sweep_reclaim_refined",
                            name=name,
                            side="LONG",
                            horizon_bars=h,
                            cooldown_bars=cool,
                            params={
                                "sweep_min": sweep_min,
                                "reclaim_min": 0.0,
                                "reclaim_max": reclaim_max,
                                "session_set": sess,
                            },
                        ))

    for close_above in asia_close_aboves:
        for rmin, rmax in asia_ranges:
            for sess in asia_sessions:
                for h in asia_horizons:
                    for cool in asia_cooldowns:
                        name = f"asia_high_breakout_long_close{close_above:g}_range{rmin:g}-{rmax:g}_{sess}_h{h}_cool{cool}"
                        variants.append(Variant(
                            family="asia_high_breakout_refined",
                            name=name,
                            side="LONG",
                            horizon_bars=h,
                            cooldown_bars=cool,
                            params={
                                "close_above": close_above,
                                "asia_range_min": rmin,
                                "asia_range_max": rmax,
                                "session_set": sess,
                            },
                        ))

    return variants


def mask_for_variant(x: pd.DataFrame, v: Variant, buffer_usd: float) -> pd.Series:
    sess = session_mask(x, str(v.params.get("session_set", "london_new_york")))

    if v.family == "pdl_sweep_reclaim_refined":
        sweep_depth = x["pdl"] - x["low"]
        reclaim = x["close"] - x["pdl"]
        return (
            x["pdl"].notna()
            & sess
            & (x["low"] < x["pdl"] - buffer_usd)
            & (x["close"] > x["pdl"])
            & (sweep_depth >= float(v.params["sweep_min"]))
            & (reclaim >= float(v.params["reclaim_min"]))
            & (reclaim <= float(v.params["reclaim_max"]))
        ).fillna(False)

    if v.family == "asia_high_breakout_refined":
        return (
            x["asia_high"].notna()
            & sess
            & (x["asia_range"].between(float(v.params["asia_range_min"]), float(v.params["asia_range_max"])))
            & (x["high"] > x["asia_high"] + buffer_usd)
            & (x["close"] > x["asia_high"] + float(v.params["close_above"]))
        ).fillna(False)

    return pd.Series(False, index=x.index)


def entry_price_from_m15(m15: pd.DataFrame, entry_dt: pd.Timestamp) -> Tuple[float, str]:
    if entry_dt in m15.index:
        return float(m15.loc[entry_dt]["open"]), "m15_exact_open"
    pos = m15.index.searchsorted(entry_dt)
    if pos < len(m15):
        return float(m15.iloc[pos]["open"]), "m15_next_open"
    return float("nan"), "entry_after_available_data"


def replay_variant(v: Variant, x: pd.DataFrame, m15: pd.DataFrame, m1: pd.DataFrame, mask: pd.Series, cost_usd: float) -> pd.DataFrame:
    idxs = apply_spacing(x.index[mask].tolist(), v.horizon_bars, v.cooldown_bars)
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
        gross = exit_price - entry_price
        mfe = float(path["high"].max()) - entry_price
        mae = entry_price - float(path["low"].min())

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


def bootstrap(df: pd.DataFrame, col: str = "net_x1", n: int = 200, seed: int = 183) -> Dict:
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


def decide(m1: Dict, m2: Dict, m4: Dict, s80: Dict, s70: Dict, y2026: Dict, boot: Dict) -> Tuple[str, List[str], float]:
    score = 0.0
    score += min(10, m1["pf"] * 3)
    score += min(10, max(0, m1["median"]) * 1.5)
    score += min(10, max(0, s80["test"]["pf"]) * 2)
    score += min(5, max(0, y2026["total"]) / 50.0)
    score += min(5, max(0, boot.get("prob_total_gt_0", 0)) * 5)
    score -= min(10, abs(min(0, m1["dd"])) / 120.0)

    if m1["events"] < 80:
        return "REJECT_TOO_FEW_EVENTS", ["events < 80"], -999.0

    promote = (
        m1["events"] >= 100
        and m1["total"] > 0
        and m1["pf"] >= 1.15
        and m1["median"] > 0
        and m2["pf"] >= 1.08
        and m2["total"] > 0
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
        return "PROMOTE_FORWARD_SHADOW_DESIGN_CANDIDATE", ["Refined variant passed strict robustness criteria."], round(score, 6)

    watch = (
        m1["events"] >= 100
        and m1["total"] > 0
        and m1["pf"] >= 1.08
        and s80["test"]["events"] >= 15
        and s80["test"]["total"] > 0
        and boot.get("prob_total_gt_0", 0) >= 0.75
    )
    if watch:
        return "KEEP_REFINED_WATCHLIST", ["Positive but still not robust enough for promotion."], round(score, 6)

    return "REJECT_REFINED_VARIANT", ["Refinement did not preserve enough robust edge."], round(score, 6)


def evaluate_variant(v: Variant, trades: pd.DataFrame, bootstrap_n: int) -> Dict:
    m1 = metrics(trades, "net_x1")
    m2 = metrics(trades, "net_x2")
    m4 = metrics(trades, "net_x4")
    s70 = split_metrics(trades, 0.70, "net_x1")
    s80 = split_metrics(trades, 0.80, "net_x1")
    y2026 = metrics(trades[trades["entry_dt"].dt.year == 2026], "net_x1") if not trades.empty else metrics(trades)
    boot = bootstrap(trades, "net_x1", bootstrap_n)
    decision, reasons, score = decide(m1, m2, m4, s80, s70, y2026, boot)
    freq_per_month = round(m1["events"] / max(1, m1["months"]), 6)
    return {
        "variant": v.name,
        "family": v.family,
        "side": v.side,
        "horizon_bars": v.horizon_bars,
        "horizon_minutes": v.horizon_bars * 15,
        "cooldown_bars": v.cooldown_bars,
        "params_json": json.dumps(v.params, sort_keys=True),
        "decision": decision,
        "score": score,
        "reasons": "; ".join(reasons),
        "events": m1["events"],
        "freq_per_month": freq_per_month,
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


def run(db: Path, out_dir: Path, cost_usd: float, buffer_usd: float, bootstrap_n: int, fast: bool, top_n_trades: int) -> int:
    generated = now_iso()
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = connect(db)
    try:
        m1 = load_m1(conn)
    finally:
        conn.close()

    m15 = resample_ohlc(m1, "15min")
    x = add_context(m15)
    variants = build_variants(fast=fast)

    summary_rows = []
    trade_parts = []
    for v in variants:
        mask = mask_for_variant(x, v, buffer_usd=buffer_usd)
        trades = replay_variant(v, x, m15, m1, mask, cost_usd=cost_usd)
        summary_rows.append(evaluate_variant(v, trades, bootstrap_n=bootstrap_n))
        if not trades.empty:
            trade_parts.append(trades)

    summary = pd.DataFrame(summary_rows)
    order = {
        "PROMOTE_FORWARD_SHADOW_DESIGN_CANDIDATE": 0,
        "KEEP_REFINED_WATCHLIST": 1,
        "REJECT_REFINED_VARIANT": 2,
        "REJECT_TOO_FEW_EVENTS": 3,
    }
    summary["_order"] = summary["decision"].map(order).fillna(9)
    summary = summary.sort_values(["_order", "score", "pf_x1", "events"], ascending=[True, False, False, False]).drop(columns=["_order"])

    all_trades = pd.concat(trade_parts, ignore_index=True) if trade_parts else pd.DataFrame()
    promoted = summary[summary["decision"].eq("PROMOTE_FORWARD_SHADOW_DESIGN_CANDIDATE")].copy()
    refined_watch = summary[summary["decision"].eq("KEEP_REFINED_WATCHLIST")].copy()

    # Keep all trades by default can be large; filter to promoted/watch top variants if requested.
    if top_n_trades > 0 and not all_trades.empty:
        keep_variants = summary.head(top_n_trades)["variant"].tolist()
        all_trades_out = all_trades[all_trades["variant"].isin(keep_variants)].copy()
    else:
        all_trades_out = all_trades

    final_decision = "REFINED_PROMOTIONS_FOUND" if len(promoted) else ("REFINED_WATCHLIST_ONLY" if len(refined_watch) else "NO_REFINED_VARIANTS_SURVIVED")

    summary_csv = out_dir / "stage18c_refinement_summary.csv"
    promoted_csv = out_dir / "stage18c_refined_promoted_candidates.csv"
    trades_csv = out_dir / "stage18c_refinement_trades.csv"
    json_path = out_dir / "stage18c_near_miss_refinement_lab.json"
    md_path = out_dir / "stage18c_near_miss_refinement_lab.md"

    summary.to_csv(summary_csv, index=False)
    promoted.to_csv(promoted_csv, index=False)
    all_trades_out.to_csv(trades_csv, index=False)

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "inputs": {
            "db": str(db),
            "cost_usd": float(cost_usd),
            "buffer_usd": float(buffer_usd),
            "bootstrap_n": int(bootstrap_n),
            "fast": bool(fast),
            "top_n_trades": int(top_n_trades),
        },
        "source": {
            "m1_rows": int(len(m1)),
            "m15_rows": int(len(m15)),
            "m1_first": m1.index.min().isoformat(),
            "m1_last": m1.index.max().isoformat(),
            "variants_tested": int(len(summary)),
        },
        "final_decision": final_decision,
        "counts": {
            "promoted": int(len(promoted)),
            "refined_watchlist": int(len(refined_watch)),
            "variants_tested": int(len(summary)),
        },
        "promoted": promoted.to_dict(orient="records"),
        "top_refined_watchlist": refined_watch.head(20).to_dict(orient="records"),
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
        "# Stage 18C Near-Miss Refinement Lab",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: research refinement only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Purpose",
        "- Refine the strongest Stage18B near-miss families.",
        "- Do not forward-shadow watchlist candidates directly.",
        "- Search for stricter variants that survive cost x4, chronological splits, 2026, and bootstrap.",
        "",
        "## Inputs",
        f"- db: `{db}`",
        f"- m1_rows: `{len(m1)}`",
        f"- m15_rows: `{len(m15)}`",
        f"- m1_first: `{m1.index.min().isoformat()}`",
        f"- m1_last: `{m1.index.max().isoformat()}`",
        f"- cost_usd: `{cost_usd}`",
        f"- buffer_usd: `{buffer_usd}`",
        f"- variants_tested: `{len(summary)}`",
        f"- fast: `{fast}`",
        "",
        "## Final decision",
        f"- final_decision: `{final_decision}`",
        "",
        "## Counts",
        f"- promoted: `{len(promoted)}`",
        f"- refined_watchlist: `{len(refined_watch)}`",
        "",
        "## Top refined variants",
        "| Rank | Variant | Family | Decision | Events | Freq/mo | PF x1 | Median x1 | Total x1 | PF x2 | PF x4 | Test20 events | Test20 total | Test20 PF | 2026 total | 2026 PF | Boot PF p05 | Score |",
        "|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for i, r in enumerate(summary.head(30).to_dict(orient="records"), 1):
        lines.append(
            f"| {i} | `{r['variant']}` | `{r['family']}` | `{r['decision']}` | {r['events']} | {r['freq_per_month']} | {r['pf_x1']} | {r['median_x1']} | {r['total_x1']} | {r['pf_x2']} | {r['pf_x4']} | {r['test20_events']} | {r['test20_total']} | {r['test20_pf']} | {r['total_2026']} | {r['pf_2026']} | {r['boot_pf_p05']} | {r['score']} |"
        )

    lines += [
        "",
        "## Promoted refined candidates",
    ]
    if not promoted.empty:
        for r in promoted.to_dict(orient="records"):
            lines.append(f"- `{r['variant']}` — {r['reasons']}")
    else:
        lines.append("- none")

    lines += [
        "",
        "## Interpretation",
        "- `REFINED_PROMOTIONS_FOUND` means only that a candidate can go to forward-shadow design, not paper/live.",
        "- `REFINED_WATCHLIST_ONLY` means positive but still insufficient for adding to Stage18A.",
        "- If no refined promotion appears, keep Stage18A running and move discovery to new families.",
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

    print("Stage 18C near-miss refinement lab: DONE")
    print(f"final_decision={final_decision}")
    print(f"promoted={len(promoted)} refined_watchlist={len(refined_watch)} variants_tested={len(summary)}")
    print(f"Report: {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--cost-usd", type=float, default=0.35)
    p.add_argument("--buffer-usd", type=float, default=0.2)
    p.add_argument("--bootstrap-n", type=int, default=200)
    p.add_argument("--fast", action="store_true")
    p.add_argument("--top-n-trades", type=int, default=30, help="Write trades only for top-N variants. Use 0 for all.")
    args = p.parse_args()

    return run(
        db=Path(args.db),
        out_dir=Path(args.out_dir),
        cost_usd=float(args.cost_usd),
        buffer_usd=float(args.buffer_usd),
        bootstrap_n=int(args.bootstrap_n),
        fast=bool(args.fast),
        top_n_trades=int(args.top_n_trades),
    )


if __name__ == "__main__":
    raise SystemExit(main())
