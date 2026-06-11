#!/usr/bin/env python3
"""
Stage26C — DB-first failure/reversal behavior discovery.

Purpose
-------
Continue discovery after Stage26B showed weak continuation-style families. Stage26C
switches to failure/reversal behavior: failed Asia breakout, London impulse failure,
prior-day extreme failure, and day-open drive failure.

Hard rules
----------
- Research/shadow discovery only.
- No EA, paper, live, or order authorization.
- Candles are DB-first from SQLite via the already validated Stage25C loader.
- AMarkets CSV fallback is intentionally disabled.
- Stage18A, Stage23D, and Stage25D are not modified.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

try:
    from app.stage25c_deduped_filter_validation import load_bars_from_db as load_bars_from_db_stage25c
except Exception:  # pragma: no cover - reported clearly at runtime
    load_bars_from_db_stage25c = None


STAGE = "stage26c_db_first_failure_reversal_discovery"
REPORT_DIR = Path("data/reports") / STAGE
DEFAULT_DB_PATH = Path(os.environ.get("STAGE26C_DB_PATH", "data/local/xauusd_local_store.sqlite"))
ROUNDTRIP_COST_X1 = float(os.environ.get("STAGE26C_ROUNDTRIP_COST_X1", "0.35"))
MAX_RUNTIME_SECONDS = int(os.environ.get("STAGE26C_MAX_RUNTIME_SECONDS", "180"))
EXACT_RESERVED_SECONDS = int(os.environ.get("STAGE26C_EXACT_RESERVED_SECONDS", "55"))
MAX_EXACT = int(os.environ.get("STAGE26C_MAX_EXACT", "12"))
MAX_EXACT_PER_FAMILY = int(os.environ.get("STAGE26C_MAX_EXACT_PER_FAMILY", "3"))
MIN_EVENTS = int(os.environ.get("STAGE26C_MIN_EVENTS", "45"))
BOOT_N = int(os.environ.get("STAGE26C_BOOT_N", "120"))
RNG_SEED = int(os.environ.get("STAGE26C_RNG_SEED", "26003"))


class Stage26CError(RuntimeError):
    pass


@dataclass(frozen=True)
class Candidate:
    family: str
    name: str
    params: Dict[str, Any]


def ensure_report_dir() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)


def fmt(v: Any) -> str:
    if isinstance(v, (float, np.floating)):
        if math.isinf(float(v)):
            return "inf"
        if math.isnan(float(v)):
            return ""
        return f"{float(v):.4f}".rstrip("0").rstrip(".")
    return str(v)


def markdown_table(df: pd.DataFrame, cols: Sequence[str], n: int = 24) -> str:
    if df is None or df.empty:
        return "No rows."
    available = [c for c in cols if c in df.columns]
    if not available:
        return "No rows."
    show = df.loc[:, available].head(n).copy()
    lines = ["| " + " | ".join(available) + " |", "| " + " | ".join(["---"] * len(available)) + " |"]
    for _, row in show.iterrows():
        lines.append("| " + " | ".join(fmt(row[c]) for c in available) + " |")
    return "\n".join(lines)


def profit_factor(values: Iterable[float]) -> float:
    arr = np.asarray([float(v) for v in values if pd.notna(v)], dtype=float)
    if arr.size == 0:
        return 0.0
    gains = arr[arr > 0].sum()
    losses = arr[arr < 0].sum()
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / abs(losses))


def bootstrap_pf_p05(values: Sequence[float], n: int = BOOT_N) -> float:
    arr = np.asarray([float(v) for v in values if pd.notna(v)], dtype=float)
    if arr.size < 20:
        return 0.0
    rng = np.random.default_rng(RNG_SEED)
    pfs: List[float] = []
    for _ in range(n):
        sample = rng.choice(arr, size=arr.size, replace=True)
        pfs.append(profit_factor(sample))
    finite = np.asarray([x for x in pfs if math.isfinite(x)], dtype=float)
    if finite.size == 0:
        return float("inf") if pfs and all(math.isinf(x) for x in pfs) else 0.0
    return float(np.percentile(finite, 5))


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close"])
    x = df.copy()
    x["timestamp"] = pd.to_datetime(x["timestamp"], utc=True, errors="coerce")
    x = x.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp")
    out = x.set_index("timestamp").resample(rule, label="right", closed="right").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last")
    )
    out = out.dropna().reset_index()
    return out


def add_atr(df: pd.DataFrame, period: int = 32) -> pd.DataFrame:
    out = df.copy().sort_values("timestamp").reset_index(drop=True)
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    for c in ("open", "high", "low", "close"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=["timestamp", "open", "high", "low", "close"]).reset_index(drop=True)
    prev_close = out["close"].shift(1)
    tr = pd.concat(
        [
            (out["high"] - out["low"]).abs(),
            (out["high"] - prev_close).abs(),
            (out["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["atr"] = tr.rolling(period, min_periods=max(5, period // 3)).mean()
    out["date"] = out["timestamp"].dt.date
    out["hour"] = out["timestamp"].dt.hour
    out["minute"] = out["timestamp"].dt.minute
    return out


def prepare_features(m15: pd.DataFrame, h1: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    m = add_atr(m15, 32)
    h = add_atr(h1, 20)
    h["sma20"] = h["close"].rolling(20, min_periods=10).mean()
    h["sma50"] = h["close"].rolling(50, min_periods=20).mean()
    h["h1_bias"] = np.where(h["sma20"] > h["sma50"], 1, np.where(h["sma20"] < h["sma50"], -1, 0))
    daily = m.groupby("date").agg(
        day_open=("open", "first"),
        day_high=("high", "max"),
        day_low=("low", "min"),
        day_close=("close", "last"),
        day_atr=("atr", "median"),
    ).reset_index()
    daily["prev_high"] = daily["day_high"].shift(1)
    daily["prev_low"] = daily["day_low"].shift(1)
    daily["prev_close"] = daily["day_close"].shift(1)
    daily["prev_range"] = daily["day_high"].shift(1) - daily["day_low"].shift(1)
    daily["prev_range_q70"] = daily["prev_range"].rolling(250, min_periods=80).quantile(0.70)
    return m, h, daily


def latest_h1_bias(h1: pd.DataFrame, ts: pd.Timestamp) -> int:
    h = h1[h1["timestamp"] <= ts]
    if h.empty:
        return 0
    try:
        return int(h.iloc[-1].get("h1_bias", 0))
    except Exception:
        return 0


def first_entry_bar(day: pd.DataFrame, entry_hour: int) -> Optional[pd.Series]:
    exact = day[(day["hour"] == entry_hour) & (day["minute"] == 0)]
    if not exact.empty:
        return exact.iloc[0]
    after = day[(day["hour"] >= entry_hour)]
    if not after.empty:
        return after.iloc[0]
    return None


def daily_row(daily: pd.DataFrame, d: Any) -> Optional[pd.Series]:
    rows = daily[daily["date"] == d]
    if rows.empty:
        return None
    return rows.iloc[0]


def add_event(rows: List[Dict[str, Any]], cand: Candidate, entry_bar: pd.Series, direction: int, atr: float, reason: str) -> None:
    if not atr or not math.isfinite(atr) or atr <= 0:
        return
    rows.append(
        {
            "timestamp": entry_bar["timestamp"],
            "direction": int(direction),
            "entry_price": float(entry_bar["close"]),
            "atr": float(atr),
            "tp_atr": float(cand.params.get("tp_atr", 0.8)),
            "sl_atr": float(cand.params.get("sl_atr", 0.8)),
            "horizon_min": int(cand.params.get("horizon_min", 90)),
            "reason": reason,
        }
    )


def events_for_candidate(m15: pd.DataFrame, h1: pd.DataFrame, daily: pd.DataFrame, cand: Candidate) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    p = cand.params
    entry_hour = int(p.get("entry_hour", 13))
    break_atr = float(p.get("break_atr", 0.25))
    reclaim_atr = float(p.get("reclaim_atr", 0.0))
    impulse_atr = float(p.get("impulse_atr", 0.8))
    ext_atr = float(p.get("ext_atr", 0.8))
    require_bias_against = bool(p.get("require_bias_against", False))
    dates = sorted(m15["date"].dropna().unique().tolist())

    for d in dates:
        day = m15[m15["date"] == d]
        if day.empty:
            continue
        entry = first_entry_bar(day, entry_hour)
        if entry is None:
            continue
        entry_ts = pd.Timestamp(entry["timestamp"])
        visible = day[day["timestamp"] <= entry_ts]
        asia = visible[(visible["hour"] >= 0) & (visible["hour"] < 7)]
        london = visible[(visible["hour"] >= 7) & (visible["timestamp"] <= entry_ts)]
        if asia.empty or london.empty or len(visible) < 20:
            continue
        atr = float(entry.get("atr", np.nan))
        if not math.isfinite(atr) or atr <= 0:
            atr = float(visible["atr"].dropna().tail(20).median()) if not visible["atr"].dropna().empty else 0.0
        if not math.isfinite(atr) or atr <= 0:
            continue
        close = float(entry["close"])
        bias = latest_h1_bias(h1, entry_ts)
        dr = daily_row(daily, d)
        asia_high = float(asia["high"].max())
        asia_low = float(asia["low"].min())
        london_open = float(london.iloc[0]["open"])
        london_high = float(london["high"].max())
        london_low = float(london["low"].min())
        london_mid = (london_high + london_low) / 2.0

        fam = cand.family
        if fam == "failed_asia_breakout_reversal_v1":
            broke_high = london_high > asia_high + break_atr * atr
            broke_low = london_low < asia_low - break_atr * atr
            if broke_high and not broke_low and close < asia_high - reclaim_atr * atr:
                if (not require_bias_against) or bias <= 0:
                    add_event(rows, cand, entry, -1, atr, "failed_asia_high_break")
            elif broke_low and not broke_high and close > asia_low + reclaim_atr * atr:
                if (not require_bias_against) or bias >= 0:
                    add_event(rows, cand, entry, 1, atr, "failed_asia_low_break")

        elif fam == "london_impulse_failure_reversal_v1":
            fail_level = str(p.get("fail_level", "mid"))
            up_impulse = (london_high - london_open) >= impulse_atr * atr
            down_impulse = (london_open - london_low) >= impulse_atr * atr
            upper_fail = london_mid if fail_level == "mid" else london_open
            lower_fail = london_mid if fail_level == "mid" else london_open
            if up_impulse and not down_impulse and close < upper_fail - reclaim_atr * atr:
                if (not require_bias_against) or bias <= 0:
                    add_event(rows, cand, entry, -1, atr, "london_up_impulse_failed")
            elif down_impulse and not up_impulse and close > lower_fail + reclaim_atr * atr:
                if (not require_bias_against) or bias >= 0:
                    add_event(rows, cand, entry, 1, atr, "london_down_impulse_failed")

        elif fam == "prior_day_extreme_failure_reversal_v1":
            if dr is None:
                continue
            pdh = float(dr.get("prev_high", np.nan))
            pdl = float(dr.get("prev_low", np.nan))
            if not (math.isfinite(pdh) and math.isfinite(pdl)):
                continue
            broke_pdh = london_high > pdh + break_atr * atr
            broke_pdl = london_low < pdl - break_atr * atr
            if broke_pdh and not broke_pdl and close < pdh - reclaim_atr * atr:
                if (not require_bias_against) or bias <= 0:
                    add_event(rows, cand, entry, -1, atr, "failed_prior_day_high_break")
            elif broke_pdl and not broke_pdh and close > pdl + reclaim_atr * atr:
                if (not require_bias_against) or bias >= 0:
                    add_event(rows, cand, entry, 1, atr, "failed_prior_day_low_break")

        elif fam == "day_open_drive_failure_reversal_v1":
            if dr is None:
                continue
            day_open = float(dr.get("day_open", np.nan))
            prev_range = float(dr.get("prev_range", np.nan))
            prev_range_q70 = float(dr.get("prev_range_q70", np.nan))
            if not math.isfinite(day_open):
                continue
            # Optional high-volatility prior-day gate: only trade after expanded prior ranges.
            if bool(p.get("prior_expansion_gate", False)):
                if not (math.isfinite(prev_range) and math.isfinite(prev_range_q70) and prev_range >= prev_range_q70):
                    continue
            drove_up = (london_high - day_open) >= ext_atr * atr
            drove_down = (day_open - london_low) >= ext_atr * atr
            if drove_up and not drove_down and close < day_open - reclaim_atr * atr:
                if (not require_bias_against) or bias <= 0:
                    add_event(rows, cand, entry, -1, atr, "day_open_up_drive_failed")
            elif drove_down and not drove_up and close > day_open + reclaim_atr * atr:
                if (not require_bias_against) or bias >= 0:
                    add_event(rows, cand, entry, 1, atr, "day_open_down_drive_failed")

    if not rows:
        return pd.DataFrame(columns=["timestamp", "direction", "entry_price", "atr", "tp_atr", "sl_atr", "horizon_min", "reason"])
    out = pd.DataFrame(rows).drop_duplicates(["timestamp", "direction", "reason"]).sort_values("timestamp").reset_index(drop=True)
    return out


def evaluate_candidate(price_df: pd.DataFrame, events: pd.DataFrame) -> Dict[str, Any]:
    if events is None or events.empty:
        return {
            "events": 0,
            "pf_x1": 0.0,
            "pf_x4": 0.0,
            "pf_x6": 0.0,
            "total_x4": 0.0,
            "median_x4": 0.0,
            "win_rate_x4": 0.0,
            "boot_pf_p05_x4": 0.0,
            "trades": pd.DataFrame(),
        }
    px = price_df.copy().sort_values("timestamp").reset_index(drop=True)
    px["timestamp"] = pd.to_datetime(px["timestamp"], utc=True, errors="coerce")
    rows: List[Dict[str, Any]] = []
    for _, ev in events.iterrows():
        entry_ts = pd.Timestamp(ev["timestamp"])
        horizon = int(ev.get("horizon_min", 90))
        end_ts = entry_ts + pd.Timedelta(minutes=horizon)
        future = px[(px["timestamp"] > entry_ts) & (px["timestamp"] <= end_ts)]
        if future.empty:
            continue
        direction = int(ev["direction"])
        entry = float(ev["entry_price"])
        atr = float(ev["atr"])
        tp_dist = max(0.01, float(ev.get("tp_atr", 0.8)) * atr)
        sl_dist = max(0.01, float(ev.get("sl_atr", 0.8)) * atr)
        if direction > 0:
            tp_level = entry + tp_dist
            sl_level = entry - sl_dist
        else:
            tp_level = entry - tp_dist
            sl_level = entry + sl_dist
        exit_price = float(future.iloc[-1]["close"])
        exit_ts = future.iloc[-1]["timestamp"]
        exit_reason = "horizon_close"
        for _, bar in future.iterrows():
            high = float(bar["high"])
            low = float(bar["low"])
            if direction > 0:
                hit_tp = high >= tp_level
                hit_sl = low <= sl_level
                # Conservative tie-break: if both TP and SL are inside the same M1 candle, count SL first.
                if hit_sl:
                    exit_price = sl_level
                    exit_ts = bar["timestamp"]
                    exit_reason = "sl"
                    break
                if hit_tp:
                    exit_price = tp_level
                    exit_ts = bar["timestamp"]
                    exit_reason = "tp"
                    break
            else:
                hit_tp = low <= tp_level
                hit_sl = high >= sl_level
                if hit_sl:
                    exit_price = sl_level
                    exit_ts = bar["timestamp"]
                    exit_reason = "sl"
                    break
                if hit_tp:
                    exit_price = tp_level
                    exit_ts = bar["timestamp"]
                    exit_reason = "tp"
                    break
        gross = direction * (exit_price - entry)
        rows.append(
            {
                "timestamp": entry_ts,
                "direction": direction,
                "entry_price": entry,
                "exit_ts": exit_ts,
                "exit_price": exit_price,
                "exit_reason": exit_reason,
                "gross": gross,
                "reason": ev.get("reason", ""),
                "horizon_min": horizon,
                "tp_atr": float(ev.get("tp_atr", 0.8)),
                "sl_atr": float(ev.get("sl_atr", 0.8)),
            }
        )
    trades = pd.DataFrame(rows)
    if trades.empty:
        return {
            "events": 0,
            "pf_x1": 0.0,
            "pf_x4": 0.0,
            "pf_x6": 0.0,
            "total_x4": 0.0,
            "median_x4": 0.0,
            "win_rate_x4": 0.0,
            "boot_pf_p05_x4": 0.0,
            "trades": trades,
        }
    trades["net_x1"] = trades["gross"] - ROUNDTRIP_COST_X1
    trades["net_x4"] = trades["gross"] - 4 * ROUNDTRIP_COST_X1
    trades["net_x6"] = trades["gross"] - 6 * ROUNDTRIP_COST_X1
    return {
        "events": int(len(trades)),
        "pf_x1": profit_factor(trades["net_x1"]),
        "pf_x4": profit_factor(trades["net_x4"]),
        "pf_x6": profit_factor(trades["net_x6"]),
        "total_x4": float(trades["net_x4"].sum()),
        "median_x4": float(trades["net_x4"].median()),
        "win_rate_x4": float((trades["net_x4"] > 0).mean()),
        "boot_pf_p05_x4": bootstrap_pf_p05(trades["net_x4"].tolist()),
        "trades": trades,
    }


def generate_candidates() -> List[Candidate]:
    candidates: List[Candidate] = []
    tp_sl_pairs = [(0.8, 0.8), (0.7, 0.9)]
    # Failed Asia range breakout / reclaim.
    for break_atr in [0.15, 0.30, 0.50]:
        for reclaim_atr in [0.0, 0.10]:
            for entry_hour in [11, 12, 13]:
                tp, sl = tp_sl_pairs[0]
                name = f"fail_asia_br_b{break_atr}_r{reclaim_atr}_e{entry_hour}_tp{tp}_sl{sl}"
                candidates.append(Candidate("failed_asia_breakout_reversal_v1", name, dict(break_atr=break_atr, reclaim_atr=reclaim_atr, entry_hour=entry_hour, horizon_min=90, tp_atr=tp, sl_atr=sl)))
    # London impulse failure.
    for impulse_atr in [0.7, 1.0, 1.3]:
        for fail_level in ["mid", "open"]:
            for entry_hour in [12, 13]:
                tp, sl = tp_sl_pairs[0]
                name = f"london_impulse_fail_i{impulse_atr}_{fail_level}_e{entry_hour}_tp{tp}_sl{sl}"
                candidates.append(Candidate("london_impulse_failure_reversal_v1", name, dict(impulse_atr=impulse_atr, fail_level=fail_level, reclaim_atr=0.0, entry_hour=entry_hour, horizon_min=90, tp_atr=tp, sl_atr=sl)))
    # Failed prior day extreme break.
    for break_atr in [0.0, 0.20, 0.40]:
        for reclaim_atr in [0.0, 0.10]:
            for entry_hour in [11, 12, 13]:
                tp, sl = tp_sl_pairs[1]
                name = f"pd_extreme_fail_b{break_atr}_r{reclaim_atr}_e{entry_hour}_tp{tp}_sl{sl}"
                candidates.append(Candidate("prior_day_extreme_failure_reversal_v1", name, dict(break_atr=break_atr, reclaim_atr=reclaim_atr, entry_hour=entry_hour, horizon_min=120, tp_atr=tp, sl_atr=sl)))
    # Day open drive failure, optionally only after prior-day expansion.
    for ext_atr in [0.7, 1.0, 1.3]:
        for gate in [False, True]:
            for entry_hour in [12, 13]:
                tp, sl = tp_sl_pairs[0]
                g = "exp" if gate else "all"
                name = f"day_open_drive_fail_x{ext_atr}_{g}_e{entry_hour}_tp{tp}_sl{sl}"
                candidates.append(Candidate("day_open_drive_failure_reversal_v1", name, dict(ext_atr=ext_atr, reclaim_atr=0.0, prior_expansion_gate=gate, entry_hour=entry_hour, horizon_min=90, tp_atr=tp, sl_atr=sl)))
    return candidates


def rank_score(row: Dict[str, Any]) -> float:
    events = int(row.get("events", 0) or 0)
    if events < MIN_EVENTS:
        return -1e9
    freq_pen = max(0.0, (events - 280) / 180.0)
    return float(3.0 * min(float(row.get("pf_x4", 0.0)), 5.0) + 1.5 * min(float(row.get("pf_x6", 0.0)), 4.0) + min(float(row.get("boot_pf_p05_x4", 0.0)), 3.0) - freq_pen)


def decision_for(row: pd.Series) -> str:
    events = int(row.get("events", 0) or 0)
    pf4 = float(row.get("pf_x4", 0.0) or 0.0)
    pf6 = float(row.get("pf_x6", 0.0) or 0.0)
    boot = float(row.get("boot_pf_p05_x4", 0.0) or 0.0)
    total = float(row.get("total_x4", 0.0) or 0.0)
    if events >= 50 and pf4 >= 1.35 and pf6 >= 1.05 and boot >= 0.95 and total > 0:
        return "STAGE26C_PROMOTION_CANDIDATE_REVIEW_ONLY"
    if events >= 45 and pf4 >= 1.05 and total > 0:
        return "STAGE26C_KEEP_WATCHLIST_ONLY"
    return "STAGE26C_REJECT"


def select_family_balanced(proxy_df: pd.DataFrame) -> pd.DataFrame:
    if proxy_df.empty:
        return proxy_df
    picks: List[pd.DataFrame] = []
    for fam in sorted(proxy_df["family"].dropna().unique().tolist()):
        g = proxy_df[(proxy_df["family"] == fam) & (proxy_df["events"] >= MIN_EVENTS)].sort_values("rank_score", ascending=False)
        if not g.empty:
            picks.append(g.head(MAX_EXACT_PER_FAMILY))
    if not picks:
        return proxy_df.head(0)
    return pd.concat(picks, ignore_index=True).sort_values("rank_score", ascending=False).head(MAX_EXACT).reset_index(drop=True)


def family_coverage(candidates: Sequence[Candidate], proxy_df: pd.DataFrame, exact_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for fam in sorted({c.family for c in candidates}):
        p = proxy_df[proxy_df["family"] == fam] if not proxy_df.empty else pd.DataFrame()
        e = exact_df[exact_df["family"] == fam] if not exact_df.empty else pd.DataFrame()
        rows.append(
            {
                "family": fam,
                "proxy_tested": int(len(p)),
                "proxy_passing_min_events": int((p["events"] >= MIN_EVENTS).sum()) if not p.empty and "events" in p else 0,
                "exact_replayed": int(len(e)),
                "best_proxy_pf_x4": float(p["pf_x4"].max()) if not p.empty and "pf_x4" in p else 0.0,
                "best_exact_pf_x4": float(e["pf_x4"].max()) if not e.empty and "pf_x4" in e else 0.0,
            }
        )
    return pd.DataFrame(rows)


def sort_results(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    order = {"STAGE26C_PROMOTION_CANDIDATE_REVIEW_ONLY": 0, "STAGE26C_KEEP_WATCHLIST_ONLY": 1, "STAGE26C_REJECT": 2}
    out["decision_order"] = out["decision"].map(order).fillna(9)
    out = out.sort_values(["decision_order", "pf_x4", "pf_x6", "total_x4"], ascending=[True, False, False, False])
    return out.drop(columns=["decision_order"])


def run() -> Dict[str, Any]:
    ensure_report_dir()
    t0 = time.time()
    exact_deadline = t0 + max(30, MAX_RUNTIME_SECONDS - EXACT_RESERVED_SECONDS)
    if load_bars_from_db_stage25c is None:
        raise Stage26CError(
            "Stage26C could not import the validated Stage25C DB loader. Apply Stage25C before Stage26C. "
            "CSV fallback is intentionally disabled."
        )
    try:
        m1, h1, db_meta, schema_diag = load_bars_from_db_stage25c(DEFAULT_DB_PATH)
    except Exception as exc:
        raise Stage26CError(f"Stage26C DB-first load failed via Stage25C schema introspection: {exc}") from exc
    if isinstance(schema_diag, pd.DataFrame):
        schema_diag.to_csv(REPORT_DIR / "stage26c_db_schema_diagnostic.csv", index=False)
    if m1 is None or m1.empty:
        raise Stage26CError("No M1 OHLC candles found in SQLite DB via Stage25C schema introspection. CSV fallback is intentionally disabled.")
    if h1 is None or h1.empty:
        h1 = resample_ohlc(m1, "1h")
        h1_mode = "derived_from_m1_resample"
    else:
        h1_mode = str(db_meta.get("h1_mode", "db_schema_introspection"))
    m15 = resample_ohlc(m1, "15min")
    m15f, h1f, daily = prepare_features(m15, h1)
    candidates = generate_candidates()

    proxy_rows: List[Dict[str, Any]] = []
    event_cache: Dict[str, pd.DataFrame] = {}
    proxy_timed_out = False
    for cand in candidates:
        if time.time() > exact_deadline:
            proxy_timed_out = True
            break
        ev = events_for_candidate(m15f, h1f, daily, cand)
        event_cache[cand.name] = ev
        # M15 proxy: intentionally coarse, used only for ranking/family coverage.
        m = evaluate_candidate(m15f, ev)
        row = {"family": cand.family, "name": cand.name, **{k: v for k, v in m.items() if k != "trades"}}
        row["rank_score"] = rank_score(row)
        row["decision"] = decision_for(pd.Series(row))
        proxy_rows.append(row)
    proxy_df = pd.DataFrame(proxy_rows)
    if not proxy_df.empty:
        proxy_df = proxy_df.sort_values("rank_score", ascending=False).reset_index(drop=True)

    exact_seed = select_family_balanced(proxy_df)
    exact_rows: List[Dict[str, Any]] = []
    all_trades: List[pd.DataFrame] = []
    exact_timed_out = False
    for _, seed in exact_seed.iterrows():
        if time.time() > t0 + MAX_RUNTIME_SECONDS:
            exact_timed_out = True
            break
        name = str(seed["name"])
        ev = event_cache.get(name, pd.DataFrame())
        m = evaluate_candidate(m1, ev)
        row = {"family": str(seed["family"]), "name": name, **{k: v for k, v in m.items() if k != "trades"}}
        row["rank_score"] = rank_score(row)
        row["decision"] = decision_for(pd.Series(row))
        exact_rows.append(row)
        trades = m.get("trades")
        if isinstance(trades, pd.DataFrame) and not trades.empty:
            t = trades.copy()
            t["candidate"] = name
            t["family"] = str(seed["family"])
            all_trades.append(t)

    exact_df = sort_results(pd.DataFrame(exact_rows))
    proxy_out = sort_results(proxy_df) if not proxy_df.empty else pd.DataFrame()
    cov = family_coverage(candidates, proxy_df, exact_df)

    promotion = int((exact_df["decision"] == "STAGE26C_PROMOTION_CANDIDATE_REVIEW_ONLY").sum()) if not exact_df.empty else 0
    watch = int((exact_df["decision"] == "STAGE26C_KEEP_WATCHLIST_ONLY").sum()) if not exact_df.empty else 0
    if promotion > 0:
        decision = "STAGE26C_HAS_PROMOTION_REVIEW_CANDIDATE_RESEARCH_ONLY"
    elif watch > 0:
        decision = "STAGE26C_HAS_WATCHLIST_ONLY_CANDIDATE_RESEARCH_ONLY"
    else:
        decision = "STAGE26C_NO_PROMOTION_KEEP_DISCOVERY_OPEN"

    proxy_out.to_csv(REPORT_DIR / "stage26c_proxy_candidates.csv", index=False)
    exact_df.to_csv(REPORT_DIR / "stage26c_exact_candidates.csv", index=False)
    cov.to_csv(REPORT_DIR / "stage26c_family_coverage.csv", index=False)
    if all_trades:
        pd.concat(all_trades, ignore_index=True).to_csv(REPORT_DIR / "stage26c_exact_trades.csv", index=False)
    else:
        pd.DataFrame().to_csv(REPORT_DIR / "stage26c_exact_trades.csv", index=False)

    result: Dict[str, Any] = {
        "generated_utc": pd.Timestamp.utcnow().isoformat(),
        "decision": decision,
        "db": {
            "db_path": str(DEFAULT_DB_PATH),
            "candle_table": str(db_meta.get("candle_table") or db_meta.get("table") or "bars"),
            "db_first": True,
            "csv_fallback_enabled": False,
            "m1_rows": int(len(m1)),
            "m1_span": f"{m1['timestamp'].min()} → {m1['timestamp'].max()}",
            "h1_rows": int(len(h1)),
            "h1_span": f"{h1['timestamp'].min()} → {h1['timestamp'].max()}",
            "h1_mode": h1_mode,
            "m15_rows": int(len(m15)),
            "m15_span": f"{m15['timestamp'].min()} → {m15['timestamp'].max()}",
        },
        "counts": {
            "proxy_candidates_tested": int(len(proxy_df)),
            "proxy_candidates_passing_min_events": int((proxy_df["events"] >= MIN_EVENTS).sum()) if not proxy_df.empty else 0,
            "exact_replayed": int(len(exact_df)),
            "promotion_review_candidates": promotion,
            "watchlist_only_candidates": watch,
            "proxy_timed_out": bool(proxy_timed_out),
            "exact_timed_out": bool(exact_timed_out),
            "runtime_seconds": round(float(time.time() - t0), 2),
        },
        "families": [
            {"family": "failed_asia_breakout_reversal_v1", "description": "Asia range break that fails/reclaims before entry; fade the failed breakout."},
            {"family": "london_impulse_failure_reversal_v1", "description": "Strong London impulse that fails back through midpoint/open before entry."},
            {"family": "prior_day_extreme_failure_reversal_v1", "description": "Prior-day high/low break that fails back inside the prior extreme."},
            {"family": "day_open_drive_failure_reversal_v1", "description": "Drive away from day open that fails back through day open."},
        ],
    }

    with open(REPORT_DIR / f"{STAGE}.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)
    write_markdown(result, proxy_out, exact_df, cov)
    return result


def write_markdown(result: Dict[str, Any], proxy_df: pd.DataFrame, exact_df: pd.DataFrame, cov: pd.DataFrame) -> None:
    cols = ["decision", "family", "name", "events", "pf_x1", "pf_x4", "pf_x6", "boot_pf_p05_x4", "median_x4", "total_x4", "win_rate_x4"]
    proxy_cols = ["decision", "family", "name", "events", "pf_x1", "pf_x4", "pf_x6", "boot_pf_p05_x4", "median_x4", "rank_score"]
    cov_cols = ["family", "proxy_tested", "proxy_passing_min_events", "exact_replayed", "best_proxy_pf_x4", "best_exact_pf_x4"]
    db = result["db"]
    counts = result["counts"]
    lines = [
        "# Stage26C DB-First Failure/Reversal Discovery",
        "",
        f"Generated UTC: `{result['generated_utc']}`",
        "",
        "## Decision",
        "",
        "```text",
        str(result["decision"]),
        "```",
        "",
        "## Scope guardrails",
        "",
        "- Research/shadow discovery only.",
        "- Stage18A v2 remains the active operational forward-shadow runner.",
        "- Stage23D and Stage25D remain separate DB-first trackers.",
        "- No EA change, no automatic trading, no paper/live/order authorization.",
        "- Candles are DB-first from SQLite via the validated Stage25C loader; AMarkets CSV fallback is disabled.",
        "",
        "## DB source of truth",
        f"- db_path: `{db['db_path']}`",
        f"- candle_table: `{db['candle_table']}`",
        f"- db_first: `{db['db_first']}`",
        f"- csv_fallback_enabled: `{db['csv_fallback_enabled']}`",
        f"- m1_rows: `{db['m1_rows']}` | span: `{db['m1_span']}`",
        f"- h1_rows: `{db['h1_rows']}` | span: `{db['h1_span']}`",
        f"- h1_mode: `{db['h1_mode']}`",
        f"- m15_rows: `{db['m15_rows']}` | span: `{db['m15_span']}`",
        "",
        "## Discovery families",
    ]
    for i, fam in enumerate(result["families"], start=1):
        lines.append(f"{i}. `{fam['family']}` — {fam['description']}")
    lines.extend(
        [
            "",
            "## Counts",
            f"- proxy_candidates_tested: `{counts['proxy_candidates_tested']}`",
            f"- proxy_candidates_passing_min_events: `{counts['proxy_candidates_passing_min_events']}`",
            f"- exact_replayed: `{counts['exact_replayed']}`",
            f"- promotion_review_candidates: `{counts['promotion_review_candidates']}`",
            f"- watchlist_only_candidates: `{counts['watchlist_only_candidates']}`",
            f"- proxy_timed_out: `{counts['proxy_timed_out']}`",
            f"- exact_timed_out: `{counts['exact_timed_out']}`",
            f"- runtime_seconds: `{counts['runtime_seconds']}`",
            "",
            "## Family coverage diagnostics",
            markdown_table(cov, cov_cols, 20),
            "",
            "## Top exact M1 results",
            markdown_table(exact_df, cols, 24),
            "",
            "## Top M15 proxy results",
            markdown_table(proxy_df, proxy_cols, 24),
            "",
            "## Interpretation",
            "",
            "- Stage26C is a DB-first discovery branch focused on failed-continuation/reversal behavior after Stage26B rejected continuation-style families.",
            "- Conditions use only information knowable at the chosen entry bar; no full future early-NY window is used at entry.",
            "- Exact replay is selected per family first, then globally capped, to keep discovery coverage broad.",
            "- A promotion-review result here remains research-only and requires separate validation and forward-shadow tracking.",
            "",
            "## Operational reminder",
            "",
            "```bash",
            "cd ~/Desktop/xauusd-trader",
            "python3 -m app.stage18a_unified_shadow_ops_cycle",
            "python3 -m app.stage23d_forward_shadow_candidate",
            "python3 -m app.stage25d_db_first_filtered_forward_shadow",
            "```",
            "",
            "## Output files",
            f"- `data/reports/{STAGE}/{STAGE}.json`",
            f"- `data/reports/{STAGE}/{STAGE}.md`",
            f"- `data/reports/{STAGE}/stage26c_proxy_candidates.csv`",
            f"- `data/reports/{STAGE}/stage26c_exact_candidates.csv`",
            f"- `data/reports/{STAGE}/stage26c_exact_trades.csv`",
            f"- `data/reports/{STAGE}/stage26c_family_coverage.csv`",
            f"- `data/reports/{STAGE}/stage26c_db_schema_diagnostic.csv`",
            "",
        ]
    )
    with open(REPORT_DIR / f"{STAGE}.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_error_report(exc: Exception) -> None:
    ensure_report_dir()
    lines = [
        "# Stage26C DB-First Failure/Reversal Discovery",
        "",
        "## Decision",
        "",
        "```text",
        "STAGE26C_ERROR_DIAGNOSTIC_ONLY",
        "```",
        "",
        "## Error",
        "",
        "```text",
        f"{type(exc).__name__}: {exc}",
        "```",
        "",
        "- DB-first is enabled.",
        "- CSV fallback is intentionally disabled.",
        "- Stage18A, Stage23D, and Stage25D remain unchanged.",
    ]
    with open(REPORT_DIR / f"{STAGE}.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> None:
    try:
        run()
    except Exception as exc:
        write_error_report(exc)
        raise


if __name__ == "__main__":
    main()
