#!/usr/bin/env python3
"""
Stage 17B — Exact M1 Replay for PDH Breakout Continuation Long

Promoted Stage17A candidate:
- variant: pdh_breakout_continuation_long_h32_cool4
- side: LONG
- signal: current M15 bar breaks above previous-day high and closes above PDH + 0.8
- active sessions: London / New York
- horizon: 32 M15 bars = 8 hours
- cooldown: 4 M15 bars = 1 hour
- entry: next M15 open
- exit: 8h time exit by default
- source: AMarkets MT5 M1 exact path

Purpose:
- Validate the Stage17A promoted candidate with exact M1 path.
- Confirm cost stress, chronological splits, year/2026 performance, bootstrap,
  and basic TP/SL geometry.
- Produce a decision for whether this behavior can enter research-only
  forward-shadow design.

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
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import pandas as pd


TOOL_VERSION = "v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_OUT_DIR = Path("data/reports/stage17b_pdh_breakout_exact_replay")


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


def previous_day_levels(m15: pd.DataFrame) -> pd.DataFrame:
    daily = resample_ohlc(m15, "1D")
    rows = []
    days = list(daily.index.strftime("%Y-%m-%d"))
    for i, day in enumerate(days):
        if i == 0:
            continue
        prev = daily.iloc[i - 1]
        rows.append({
            "date": day,
            "pdh": float(prev["high"]),
            "pdl": float(prev["low"]),
            "prev_range": float(prev["high"] - prev["low"]),
            "prev_mid": float((prev["high"] + prev["low"]) / 2.0),
        })
    return pd.DataFrame(rows)


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

    prev = previous_day_levels(m15)
    x = x.reset_index()
    if "utc_time" in x.columns:
        x = x.rename(columns={"utc_time": "signal_dt"})
    else:
        x = x.rename(columns={x.columns[0]: "signal_dt"})
    x = x.merge(prev, on="date", how="left")
    return x.sort_values("signal_dt").reset_index(drop=True)


def apply_spacing(indices: Sequence[int], horizon_bars: int, cooldown_bars: int) -> List[int]:
    chosen: List[int] = []
    next_allowed = -1
    for i in indices:
        if i < next_allowed:
            continue
        chosen.append(int(i))
        next_allowed = int(i) + int(horizon_bars) + int(cooldown_bars)
    return chosen


def detect_signals(x: pd.DataFrame, buffer_usd: float, close_above_pdh: float, horizon_bars: int, cooldown_bars: int) -> pd.DataFrame:
    valid_prev = x["pdh"].notna()
    session_ok = x["session"].isin(["london", "new_york"])
    cond = (
        valid_prev
        & session_ok
        & (x["high"] > x["pdh"] + buffer_usd)
        & (x["close"] > x["pdh"] + close_above_pdh)
    )
    idxs = apply_spacing(x.index[cond].tolist(), horizon_bars=horizon_bars, cooldown_bars=cooldown_bars)
    rows = []
    for i in idxs:
        entry_i = i + 1
        exit_i = entry_i + horizon_bars
        if entry_i >= len(x) or exit_i >= len(x):
            continue
        rows.append({
            "signal_i": int(i),
            "entry_i": int(entry_i),
            "exit_i": int(exit_i),
            "signal_dt": x.iloc[i]["signal_dt"],
            "entry_dt": x.iloc[entry_i]["signal_dt"],
            "exit_target_dt": x.iloc[exit_i]["signal_dt"],
            "session": x.iloc[i]["session"],
            "hour": int(x.iloc[i]["hour"]),
            "signal_open": float(x.iloc[i]["open"]),
            "signal_high": float(x.iloc[i]["high"]),
            "signal_low": float(x.iloc[i]["low"]),
            "signal_close": float(x.iloc[i]["close"]),
            "pdh": float(x.iloc[i]["pdh"]),
            "pdl": float(x.iloc[i]["pdl"]),
            "prev_range": float(x.iloc[i]["prev_range"]),
            "break_above_pdh": round(float(x.iloc[i]["high"] - x.iloc[i]["pdh"]), 6),
            "close_above_pdh": round(float(x.iloc[i]["close"] - x.iloc[i]["pdh"]), 6),
            "variant": "pdh_breakout_continuation_long_h32_cool4",
            "side": "LONG",
        })
    out = pd.DataFrame(rows)
    for c in ["signal_dt", "entry_dt", "exit_target_dt"]:
        if c in out.columns:
            out[c] = pd.to_datetime(out[c], utc=True)
    return out


def entry_price_from_m15(m15: pd.DataFrame, entry_dt: pd.Timestamp) -> Tuple[float, str]:
    if entry_dt in m15.index:
        return float(m15.loc[entry_dt]["open"]), "m15_exact_open"
    pos = m15.index.searchsorted(entry_dt)
    if pos < len(m15):
        return float(m15.iloc[pos]["open"]), "m15_next_open"
    return float("nan"), "entry_after_available_data"


def replay_one(row: pd.Series, m1: pd.DataFrame, m15: pd.DataFrame, cost_usd: float) -> Dict:
    entry_dt = pd.to_datetime(row["entry_dt"], utc=True)
    exit_dt = pd.to_datetime(row["exit_target_dt"], utc=True)
    entry, entry_src = entry_price_from_m15(m15, entry_dt)

    if pd.isna(entry):
        return {
            **row.to_dict(),
            "status": "entry_unavailable",
            "entry_price": float("nan"),
            "entry_price_source": entry_src,
            "exit_price": float("nan"),
            "gross_ret": float("nan"),
            "net_x1": float("nan"),
            "net_x2": float("nan"),
            "net_x4": float("nan"),
            "mfe": float("nan"),
            "mae": float("nan"),
            "minutes_observed": 0,
        }

    path = m1[(m1.index > entry_dt) & (m1.index <= exit_dt)]
    if path.empty:
        return {
            **row.to_dict(),
            "status": "missing_m1_path",
            "entry_price": round(entry, 6),
            "entry_price_source": entry_src,
            "exit_price": float("nan"),
            "gross_ret": float("nan"),
            "net_x1": float("nan"),
            "net_x2": float("nan"),
            "net_x4": float("nan"),
            "mfe": float("nan"),
            "mae": float("nan"),
            "minutes_observed": 0,
        }

    exit_price = float(path.iloc[-1]["close"])
    gross = exit_price - entry
    mfe = float(path["high"].max()) - entry
    mae = entry - float(path["low"].min())
    return {
        **row.to_dict(),
        "status": "closed_time_exit",
        "entry_price": round(entry, 6),
        "entry_price_source": entry_src,
        "exit_price": round(exit_price, 6),
        "gross_ret": round(gross, 6),
        "net_x1": round(gross - cost_usd, 6),
        "net_x2": round(gross - 2 * cost_usd, 6),
        "net_x4": round(gross - 4 * cost_usd, 6),
        "mfe": round(mfe, 6),
        "mae": round(mae, 6),
        "minutes_observed": int(round((path.index.max() - entry_dt) / pd.Timedelta(minutes=1))),
    }


def replay_signals(signals: pd.DataFrame, m1: pd.DataFrame, m15: pd.DataFrame, cost_usd: float) -> pd.DataFrame:
    if signals.empty:
        return pd.DataFrame()
    rows = [replay_one(row, m1, m15, cost_usd) for _, row in signals.iterrows()]
    out = pd.DataFrame(rows)
    for c in ["signal_dt", "entry_dt", "exit_target_dt"]:
        out[c] = pd.to_datetime(out[c], utc=True, errors="coerce")
    return out.sort_values("entry_dt").reset_index(drop=True)


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
    return {"frac": float(frac), "train": metrics(x.iloc[:cut], col), "test": metrics(x.iloc[cut:], col)}


def period_table(df: pd.DataFrame, period: str, col: str = "net_x1") -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    x = df.copy()
    if period == "year":
        x["period"] = x["entry_dt"].dt.year.astype(str)
    elif period == "quarter":
        x["period"] = x["entry_dt"].dt.to_period("Q").astype(str)
    elif period == "month":
        x["period"] = x["entry_dt"].dt.to_period("M").astype(str)
    elif period == "session":
        x["period"] = x["session"].astype(str)
    elif period == "hour":
        x["period"] = x["hour"].astype(str)
    else:
        raise ValueError(period)
    rows = []
    for p, g in x.groupby("period"):
        r = {"period": p}
        r.update(metrics(g, col))
        rows.append(r)
    return pd.DataFrame(rows).sort_values("period")


def bootstrap(df: pd.DataFrame, col: str = "net_x1", n: int = 500, seed: int = 17) -> Dict:
    if df.empty:
        return {}
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
        "total_p95": round(float(ts.quantile(0.95)), 6),
        "pf_p05": round(float(ps.quantile(0.05)), 6),
        "pf_p50": round(float(ps.quantile(0.50)), 6),
        "median_p05": round(float(ms.quantile(0.05)), 6),
        "median_p50": round(float(ms.quantile(0.50)), 6),
        "prob_total_gt_0": round(float((ts > 0).mean()), 6),
        "prob_pf_gt_1": round(float((ps > 1).mean()), 6),
        "prob_median_gt_0": round(float((ms > 0).mean()), 6),
    }


def geometry_one(row: pd.Series, m1: pd.DataFrame, tp: float, sl: float) -> Dict:
    entry_dt = pd.to_datetime(row["entry_dt"], utc=True)
    exit_dt = pd.to_datetime(row["exit_target_dt"], utc=True)
    entry = float(row["entry_price"])
    path = m1[(m1.index > entry_dt) & (m1.index <= exit_dt)]
    if path.empty or pd.isna(entry):
        return {"reason": "missing_path", "ret": float("nan"), "ambiguous": 0}

    tp_price = entry + tp
    sl_price = entry - sl
    for _, b in path.iterrows():
        hit_tp = float(b["high"]) >= tp_price
        hit_sl = float(b["low"]) <= sl_price
        if hit_tp and hit_sl:
            return {"reason": "ambiguous_same_m1_sl_first", "ret": -sl, "ambiguous": 1}
        if hit_sl:
            return {"reason": "sl", "ret": -sl, "ambiguous": 0}
        if hit_tp:
            return {"reason": "tp", "ret": tp, "ambiguous": 0}
    return {"reason": "time_exit", "ret": float(row["gross_ret"]), "ambiguous": 0}


def geometry_summary(replay: pd.DataFrame, m1: pd.DataFrame, cost_usd: float) -> pd.DataFrame:
    geoms = [
        ("time_exit_8h", 0.0, 0.0),
        ("tp20_sl15", 20.0, 15.0),
        ("tp24_sl15", 24.0, 15.0),
        ("tp30_sl20", 30.0, 20.0),
        ("tp40_sl25", 40.0, 25.0),
        ("tp50_sl30", 50.0, 30.0),
    ]
    rows = []
    for name, tp, sl in geoms:
        x = replay.copy()
        if name == "time_exit_8h":
            x["geom_ret"] = x["gross_ret"]
            x["geom_reason"] = "time_exit"
            x["ambiguous"] = 0
        else:
            outs = [geometry_one(r, m1, tp, sl) for _, r in x.iterrows()]
            x["geom_ret"] = [o["ret"] for o in outs]
            x["geom_reason"] = [o["reason"] for o in outs]
            x["ambiguous"] = [o["ambiguous"] for o in outs]
        x["geom_net_x1"] = pd.to_numeric(x["geom_ret"], errors="coerce") - cost_usd
        m = metrics(x, "geom_net_x1")
        vc = x["geom_reason"].value_counts().to_dict()
        rows.append({
            "geometry": name,
            "tp": tp,
            "sl": sl,
            **m,
            "tp_count": int(vc.get("tp", 0)),
            "sl_count": int(vc.get("sl", 0) + vc.get("ambiguous_same_m1_sl_first", 0)),
            "time_exit_count": int(vc.get("time_exit", 0)),
            "ambiguous_count": int(x["ambiguous"].sum()),
        })
    return pd.DataFrame(rows).sort_values(["pf", "median", "total"], ascending=[False, False, False])


def decide(replay: pd.DataFrame, base: Dict, x2: Dict, x4: Dict, splits: List[Dict], y2026: Dict, boot: Dict) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    if base["events"] < 200:
        return "REJECT_EXACT_REPLAY_TOO_FEW_EVENTS", ["Exact replay event count is too low for this breakout behavior."]
    if not (base["total"] > 0 and base["pf"] >= 1.15 and base["median"] > 0):
        return "REJECT_EXACT_REPLAY_WEAK", ["Exact replay does not preserve positive edge after cost x1."]
    if not (x2["total"] > 0 and x2["pf"] >= 1.08):
        return "COST_FRAGILE_EXACT_REPLAY", ["Cost x2 stress is not strong enough."]
    if not (x4["pf"] >= 1.00):
        return "COST_X4_FRAGILE_EXACT_REPLAY", ["Cost x4 stress falls below breakeven PF."]
    for sp in splits:
        test = sp["test"]
        if not (test["events"] >= 30 and test["total"] > 0 and test["pf"] >= 1.05):
            return "SPLIT_FRAGILE_EXACT_REPLAY", [f"Chronological split {sp['frac']} test segment fails."]
    if base["pos_years"] < max(3, round(base["years"] * 0.60)):
        return "YEAR_FRAGILE_EXACT_REPLAY", ["Year distribution is too narrow."]
    if y2026["events"] >= 20 and not (y2026["total"] > 0 and y2026["pf"] >= 1.00):
        return "CURRENT_2026_FRAGILE_EXACT_REPLAY", ["2026 segment does not preserve positive behavior."]
    if boot and (boot.get("prob_total_gt_0", 0) < 0.95 or boot.get("pf_p05", 0) < 1.0):
        return "BOOTSTRAP_FRAGILE_EXACT_REPLAY", ["Bootstrap lower tail is not strong enough."]

    reasons.append("Exact M1 replay preserves Stage17A breakout-continuation edge.")
    reasons.append("Allowed next step is research-only forward-shadow design for this behavior.")
    return "EXACT_REPLAY_PROMOTE_TO_FORWARD_SHADOW_DESIGN", reasons


def run(
    db: Path,
    out_dir: Path,
    cost_usd: float,
    buffer_usd: float,
    close_above_pdh: float,
    horizon_bars: int,
    cooldown_bars: int,
    bootstrap_n: int,
) -> int:
    generated = now_iso()
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = connect(db)
    try:
        m1 = load_m1(conn)
    finally:
        conn.close()

    m15 = resample_ohlc(m1, "15min")
    ctx = add_context(m15)
    signals = detect_signals(
        ctx,
        buffer_usd=buffer_usd,
        close_above_pdh=close_above_pdh,
        horizon_bars=horizon_bars,
        cooldown_bars=cooldown_bars,
    )
    replay = replay_signals(signals, m1, m15, cost_usd)
    closed = replay[replay["status"].eq("closed_time_exit")].copy() if not replay.empty else pd.DataFrame()

    base = metrics(closed, "net_x1")
    x2 = metrics(closed, "net_x2")
    x4 = metrics(closed, "net_x4")
    splits = [split_metrics(closed, 0.70, "net_x1"), split_metrics(closed, 0.80, "net_x1")]
    y2026 = metrics(closed[closed["entry_dt"].dt.year == 2026], "net_x1") if not closed.empty else metrics(pd.DataFrame())
    boot = bootstrap(closed, "net_x1", bootstrap_n)
    geom = geometry_summary(closed, m1, cost_usd) if not closed.empty else pd.DataFrame()
    by_year = period_table(closed, "year", "net_x1")
    by_quarter = period_table(closed, "quarter", "net_x1")
    by_session = period_table(closed, "session", "net_x1")
    by_hour = period_table(closed, "hour", "net_x1")

    final_decision, reasons = decide(closed, base, x2, x4, splits, y2026, boot)

    trades_csv = out_dir / "stage17b_exact_replay_trades.csv"
    signals_csv = out_dir / "stage17b_detected_signals.csv"
    geometry_csv = out_dir / "stage17b_geometry_summary.csv"
    year_csv = out_dir / "stage17b_by_year.csv"
    quarter_csv = out_dir / "stage17b_by_quarter.csv"
    session_csv = out_dir / "stage17b_by_session.csv"
    hour_csv = out_dir / "stage17b_by_hour.csv"
    json_path = out_dir / "stage17b_pdh_breakout_exact_replay.json"
    md_path = out_dir / "stage17b_pdh_breakout_exact_replay.md"

    signals.to_csv(signals_csv, index=False)
    closed.to_csv(trades_csv, index=False)
    geom.to_csv(geometry_csv, index=False)
    by_year.to_csv(year_csv, index=False)
    by_quarter.to_csv(quarter_csv, index=False)
    by_session.to_csv(session_csv, index=False)
    by_hour.to_csv(hour_csv, index=False)

    split_rows = []
    for sp in splits:
        for seg in ["train", "test"]:
            row = {"frac": sp["frac"], "segment": seg}
            row.update(sp[seg])
            split_rows.append(row)

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "candidate": {
            "variant": "pdh_breakout_continuation_long_h32_cool4",
            "side": "LONG",
            "horizon_bars": int(horizon_bars),
            "horizon_minutes": int(horizon_bars * 15),
            "cooldown_bars": int(cooldown_bars),
            "buffer_usd": float(buffer_usd),
            "close_above_pdh": float(close_above_pdh),
            "cost_usd": float(cost_usd),
        },
        "source": {
            "m1_rows": int(len(m1)),
            "m15_rows": int(len(m15)),
            "m1_first": m1.index.min().isoformat(),
            "m1_last": m1.index.max().isoformat(),
        },
        "final_decision": final_decision,
        "reasons": reasons,
        "metrics": {
            "net_x1": base,
            "net_x2": x2,
            "net_x4": x4,
            "y2026": y2026,
        },
        "splits": splits,
        "bootstrap": boot,
        "geometry_summary": geom.to_dict(orient="records"),
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
        "# Stage 17B PDH Breakout Continuation Exact Replay",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: research validation only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Candidate",
        "- variant: `pdh_breakout_continuation_long_h32_cool4`",
        "- side: `LONG`",
        "- behavior: `previous-day high breakout continuation`",
        f"- horizon_bars: `{horizon_bars}`",
        f"- horizon_minutes: `{horizon_bars * 15}`",
        f"- cooldown_bars: `{cooldown_bars}`",
        f"- buffer_usd: `{buffer_usd}`",
        f"- close_above_pdh: `{close_above_pdh}`",
        f"- cost_usd: `{cost_usd}`",
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
        "## Exact M1 time-exit replay",
        "| Result set | Events | Total | Avg | Median | WR | PF | DD | Pos years | Pos quarters |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| net_x1 | {base['events']} | {base['total']} | {base['avg']} | {base['median']} | {base['wr']} | {base['pf']} | {base['dd']} | {base['pos_years']}/{base['years']} | {base['pos_quarters']}/{base['quarters']} |",
        f"| net_x2 | {x2['events']} | {x2['total']} | {x2['avg']} | {x2['median']} | {x2['wr']} | {x2['pf']} | {x2['dd']} | {x2['pos_years']}/{x2['years']} | {x2['pos_quarters']}/{x2['quarters']} |",
        f"| net_x4 | {x4['events']} | {x4['total']} | {x4['avg']} | {x4['median']} | {x4['wr']} | {x4['pf']} | {x4['dd']} | {x4['pos_years']}/{x4['years']} | {x4['pos_quarters']}/{x4['quarters']} |",
        "",
        "## Chronological splits",
        "| Split | Segment | Events | Total | Avg | Median | WR | PF | DD |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in split_rows:
        lines.append(
            f"| {r['frac']} | {r['segment']} | {r['events']} | {r['total']} | {r['avg']} | {r['median']} | {r['wr']} | {r['pf']} | {r['dd']} |"
        )

    lines += [
        "",
        "## 2026 segment",
        "| Events | Total | Avg | Median | WR | PF | DD |",
        "|---:|---:|---:|---:|---:|---:|---:|",
        f"| {y2026['events']} | {y2026['total']} | {y2026['avg']} | {y2026['median']} | {y2026['wr']} | {y2026['pf']} | {y2026['dd']} |",
        "",
        "## Limited geometry summary - M1 path, net x1",
        "| Geometry | Events | Total | Avg | Median | WR | PF | DD | TP | SL | Time exit | Ambiguous |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    if not geom.empty:
        for r in geom.to_dict(orient="records"):
            lines.append(
                f"| {r['geometry']} | {r['events']} | {r['total']} | {r['avg']} | {r['median']} | {r['wr']} | {r['pf']} | {r['dd']} | {r['tp_count']} | {r['sl_count']} | {r['time_exit_count']} | {r['ambiguous_count']} |"
            )
    else:
        lines.append("| none | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |")

    lines += [
        "",
        "## Year distribution - exact M1 net x1",
        "| Year | Events | Total | Avg | Median | WR | PF | DD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    if not by_year.empty:
        for r in by_year.to_dict(orient="records"):
            lines.append(
                f"| {r['period']} | {r['events']} | {r['total']} | {r['avg']} | {r['median']} | {r['wr']} | {r['pf']} | {r['dd']} |"
            )
    else:
        lines.append("| none | 0 | 0 | 0 | 0 | 0 | 0 | 0 |")

    lines += [
        "",
        "## Bootstrap - exact M1 net x1",
        "```json",
        json.dumps(boot, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Interpretation",
        "- `EXACT_REPLAY_PROMOTE_TO_FORWARD_SHADOW_DESIGN` permits only research-only shadow design for this behavior.",
        "- Any failure rejects or pauses this breakout candidate, not the broader XAUUSD project.",
        "- Stage16 true-forward collector should continue in parallel.",
        "- No EA/paper/live/order authorization is granted.",
        "",
        "## Output files",
        f"- signals_csv: `{signals_csv}`",
        f"- trades_csv: `{trades_csv}`",
        f"- geometry_csv: `{geometry_csv}`",
        f"- year_csv: `{year_csv}`",
        f"- quarter_csv: `{quarter_csv}`",
        f"- session_csv: `{session_csv}`",
        f"- hour_csv: `{hour_csv}`",
        f"- json: `{json_path}`",
        f"- md: `{md_path}`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 17B PDH breakout exact replay: DONE")
    print(f"final_decision={final_decision}")
    print(f"events={base['events']} total={base['total']} pf={base['pf']} median={base['median']}")
    print(f"2026_total={y2026['total']} 2026_pf={y2026['pf']}")
    print(f"Report: {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--cost-usd", type=float, default=0.35)
    p.add_argument("--buffer-usd", type=float, default=0.2)
    p.add_argument("--close-above-pdh", type=float, default=0.8)
    p.add_argument("--horizon-bars", type=int, default=32)
    p.add_argument("--cooldown-bars", type=int, default=4)
    p.add_argument("--bootstrap-n", type=int, default=500)
    args = p.parse_args()
    return run(
        db=Path(args.db),
        out_dir=Path(args.out_dir),
        cost_usd=float(args.cost_usd),
        buffer_usd=float(args.buffer_usd),
        close_above_pdh=float(args.close_above_pdh),
        horizon_bars=int(args.horizon_bars),
        cooldown_bars=int(args.cooldown_bars),
        bootstrap_n=int(args.bootstrap_n),
    )


if __name__ == "__main__":
    raise SystemExit(main())
