#!/usr/bin/env python3
"""
Stage27A — DB-first outcome-surface discovery.

Purpose
-------
After Stage26A/B/C/D rejected structured continuation, reversal, and mirror/anti-signal
families, Stage27A stops mutating those entry rules and instead maps simple, knowable-at-entry
regime/direction outcome surfaces. The goal is to find robust seeds for later exact rule design,
not to authorize any trading.

Hard rules
----------
- Research/shadow discovery only.
- No EA, paper, live, or order authorization.
- Candles are DB-first from SQLite through the validated Stage25C loader.
- AMarkets CSV market fallback is intentionally disabled.
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
except Exception:  # reported clearly at runtime
    load_bars_from_db_stage25c = None


STAGE = "stage27a_db_first_outcome_surface_discovery"
REPORT_DIR = Path("data/reports") / STAGE
DEFAULT_DB_PATH = Path(os.environ.get("STAGE27A_DB_PATH", "data/local/xauusd_local_store.sqlite"))
ROUNDTRIP_COST_X1 = float(os.environ.get("STAGE27A_ROUNDTRIP_COST_X1", "0.35"))
MAX_RUNTIME_SECONDS = int(os.environ.get("STAGE27A_MAX_RUNTIME_SECONDS", "180"))
MAX_EXACT = int(os.environ.get("STAGE27A_MAX_EXACT", "16"))
MAX_EXACT_PER_FAMILY = int(os.environ.get("STAGE27A_MAX_EXACT_PER_FAMILY", "4"))
MIN_EVENTS = int(os.environ.get("STAGE27A_MIN_EVENTS", "45"))
BOOT_N = int(os.environ.get("STAGE27A_BOOT_N", "120"))
RNG_SEED = int(os.environ.get("STAGE27A_RNG_SEED", "27001"))


class Stage27AError(RuntimeError):
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
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False, default=str)
    return str(v)


def markdown_table(df: pd.DataFrame, cols: Sequence[str], n: int = 30) -> str:
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
    if arr.size < 30:
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


def resample_ohlc(df: pd.DataFrame, rule: str, label: str = "right") -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close"])
    x = df.copy()
    x["timestamp"] = pd.to_datetime(x["timestamp"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        x[c] = pd.to_numeric(x[c], errors="coerce")
    x = x.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp")
    out = x.set_index("timestamp").resample(rule, label=label, closed=label).agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last")
    )
    return out.dropna().reset_index()


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
    out["date"] = out["timestamp"].dt.floor("D")
    out["hour"] = out["timestamp"].dt.hour
    out["minute"] = out["timestamp"].dt.minute
    return out


def normalize_bars(m1: pd.DataFrame, h1: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    m1x = m1.copy()
    m1x["timestamp"] = pd.to_datetime(m1x["timestamp"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        m1x[c] = pd.to_numeric(m1x[c], errors="coerce")
    m1x = m1x.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp").reset_index(drop=True)
    if m1x.empty:
        raise Stage27AError("No M1 OHLC candles found after Stage25C DB loader. CSV fallback is intentionally disabled.")

    h1x = h1.copy() if h1 is not None and not h1.empty else resample_ohlc(m1x, "1h", label="left")
    h1x["timestamp"] = pd.to_datetime(h1x["timestamp"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        h1x[c] = pd.to_numeric(h1x[c], errors="coerce")
    h1x = h1x.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp").reset_index(drop=True)

    m15x = resample_ohlc(m1x, "15min", label="right")
    meta = {
        "m1_rows_stage27a": int(len(m1x)),
        "m1_span_stage27a": f"{m1x['timestamp'].min()} → {m1x['timestamp'].max()}",
        "h1_rows_stage27a": int(len(h1x)),
        "h1_span_stage27a": f"{h1x['timestamp'].min()} → {h1x['timestamp'].max()}" if not h1x.empty else "",
        "m15_rows_stage27a": int(len(m15x)),
        "m15_span_stage27a": f"{m15x['timestamp'].min()} → {m15x['timestamp'].max()}" if not m15x.empty else "",
    }
    return m1x, h1x, m15x, meta


def prepare_features(m15: pd.DataFrame, h1: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    m = add_atr(m15, 32)
    h = add_atr(h1, 20)
    h["sma20"] = h["close"].rolling(20, min_periods=10).mean()
    h["sma50"] = h["close"].rolling(50, min_periods=20).mean()
    h["h1_bias"] = np.where(h["sma20"] > h["sma50"], 1, np.where(h["sma20"] < h["sma50"], -1, 0))

    m["date"] = m["timestamp"].dt.floor("D")
    sessions: List[pd.DataFrame] = []
    for name, start_h, end_h in [("asia", 0, 7), ("london", 7, 13)]:
        s = m[(m["hour"] >= start_h) & (m["hour"] < end_h)].copy()
        if s.empty:
            continue
        agg = s.groupby("date").agg(
            **{
                f"{name}_open": ("open", "first"),
                f"{name}_high": ("high", "max"),
                f"{name}_low": ("low", "min"),
                f"{name}_close": ("close", "last"),
                f"{name}_atr": ("atr", "median"),
            }
        ).reset_index()
        agg[f"{name}_range"] = agg[f"{name}_high"] - agg[f"{name}_low"]
        agg[f"{name}_eff"] = (agg[f"{name}_close"] - agg[f"{name}_open"]).abs() / agg[f"{name}_range"].replace(0, np.nan)
        agg[f"{name}_dir"] = np.where(agg[f"{name}_close"] >= agg[f"{name}_open"], 1, -1)
        sessions.append(agg)

    daily = m.groupby("date").agg(day_open=("open", "first"), day_high=("high", "max"), day_low=("low", "min"), day_close=("close", "last"), day_atr=("atr", "median")).reset_index()
    daily["prior_high"] = daily["day_high"].shift(1)
    daily["prior_low"] = daily["day_low"].shift(1)
    daily["prior_close"] = daily["day_close"].shift(1)
    daily["prior_range"] = daily["day_high"].shift(1) - daily["day_low"].shift(1)
    daily["prior_dir"] = np.where(daily["prior_close"] >= daily["day_open"].shift(1), 1, -1)
    for s in sessions:
        daily = daily.merge(s, on="date", how="left")
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
    after = day[day["hour"] >= entry_hour]
    if not after.empty:
        return after.iloc[0]
    return None


def daily_for(daily: pd.DataFrame, d: pd.Timestamp) -> Optional[pd.Series]:
    rows = daily[daily["date"] == d]
    if rows.empty:
        return None
    return rows.iloc[0]


def event_row(c: Candidate, entry_bar: pd.Series, direction: int, reason: str) -> Dict[str, Any]:
    return {
        "timestamp": entry_bar["timestamp"],
        "direction": int(direction),
        "entry_price": float(entry_bar["close"]),
        "atr": float(entry_bar.get("atr", np.nan)),
        "tp_atr": float(c.params.get("tp_atr", 0.8)),
        "sl_atr": float(c.params.get("sl_atr", 0.8)),
        "horizon_min": int(c.params.get("horizon_min", 120)),
        "reason": reason,
    }


def events_for_candidate(m15: pd.DataFrame, h1: pd.DataFrame, daily: pd.DataFrame, c: Candidate) -> pd.DataFrame:
    p = c.params
    rows: List[Dict[str, Any]] = []
    entry_hour = int(p.get("entry_hour", 13))
    min_atr_mult = float(p.get("min_atr_mult", 0.4))
    max_atr_mult = float(p.get("max_atr_mult", 999))

    for d, day in m15.groupby("date"):
        entry = first_entry_bar(day, entry_hour)
        if entry is None:
            continue
        atr = float(entry.get("atr", np.nan))
        if not math.isfinite(atr) or atr <= 0:
            continue
        dr = daily_for(daily, pd.Timestamp(d))
        if dr is None:
            continue
        price = float(entry["close"])
        ts = pd.Timestamp(entry["timestamp"])
        h1_bias = latest_h1_bias(h1, ts)
        london_dir = int(dr.get("london_dir", 0)) if pd.notna(dr.get("london_dir", np.nan)) else 0
        asia_dir = int(dr.get("asia_dir", 0)) if pd.notna(dr.get("asia_dir", np.nan)) else 0
        london_range_atr = float(dr.get("london_range", np.nan)) / atr if math.isfinite(float(dr.get("london_range", np.nan))) else np.nan
        asia_range_atr = float(dr.get("asia_range", np.nan)) / atr if math.isfinite(float(dr.get("asia_range", np.nan))) else np.nan
        day_open = float(dr.get("day_open", np.nan))
        prior_high = float(dr.get("prior_high", np.nan))
        prior_low = float(dr.get("prior_low", np.nan))
        prior_close = float(dr.get("prior_close", np.nan))
        prior_dir = int(dr.get("prior_dir", 0)) if pd.notna(dr.get("prior_dir", np.nan)) else 0

        fam = c.family
        if fam == "hour_h1_bias_surface_v1":
            if h1_bias == 0:
                continue
            direction = h1_bias if p.get("mode") == "follow" else -h1_bias
            rows.append(event_row(c, entry, direction, f"h1_bias={h1_bias};mode={p.get('mode')};hour={entry_hour}"))

        elif fam == "london_direction_surface_v1":
            if london_dir == 0 or not math.isfinite(london_range_atr):
                continue
            if london_range_atr < min_atr_mult or london_range_atr > max_atr_mult:
                continue
            direction = london_dir if p.get("mode") == "follow" else -london_dir
            rows.append(event_row(c, entry, direction, f"london_dir={london_dir};london_range_atr={london_range_atr:.2f};mode={p.get('mode')}"))

        elif fam == "day_open_extension_surface_v1":
            if not math.isfinite(day_open):
                continue
            ext = (price - day_open) / atr
            if abs(ext) < min_atr_mult or abs(ext) > max_atr_mult:
                continue
            base_dir = 1 if ext > 0 else -1
            direction = base_dir if p.get("mode") == "follow" else -base_dir
            rows.append(event_row(c, entry, direction, f"day_open_ext={ext:.2f};mode={p.get('mode')}"))

        elif fam == "prior_day_location_surface_v1":
            if not all(math.isfinite(x) for x in [prior_high, prior_low, prior_close]):
                continue
            above = (price - prior_high) / atr
            below = (prior_low - price) / atr
            if above >= min_atr_mult:
                base_dir = 1
                loc = "above_prior_high"
                mag = above
            elif below >= min_atr_mult:
                base_dir = -1
                loc = "below_prior_low"
                mag = below
            else:
                continue
            if mag > max_atr_mult:
                continue
            direction = base_dir if p.get("mode") == "follow" else -base_dir
            rows.append(event_row(c, entry, direction, f"{loc};mag_atr={mag:.2f};mode={p.get('mode')};prior_dir={prior_dir}"))

        elif fam == "asia_london_alignment_surface_v1":
            if asia_dir == 0 or london_dir == 0:
                continue
            aligned = asia_dir == london_dir
            if bool(p.get("aligned")) != aligned:
                continue
            if not math.isfinite(asia_range_atr) or asia_range_atr < float(p.get("asia_min_atr", 0.25)):
                continue
            base_dir = london_dir
            direction = base_dir if p.get("mode") == "follow" else -base_dir
            rows.append(event_row(c, entry, direction, f"asia_dir={asia_dir};london_dir={london_dir};aligned={aligned};mode={p.get('mode')}"))

    out = pd.DataFrame(rows)
    if not out.empty:
        out["family"] = c.family
        out["candidate"] = c.name
    return out


def generate_candidates() -> List[Candidate]:
    candidates: List[Candidate] = []
    for hour in [11, 13, 15]:
        for mode in ["follow", "fade"]:
            for horizon in [180]:
                candidates.append(Candidate("hour_h1_bias_surface_v1", f"h1_bias_{mode}_h{hour}_hz{horizon}_tp08_sl08", {"entry_hour": hour, "mode": mode, "horizon_min": horizon, "tp_atr": 0.8, "sl_atr": 0.8}))
    for hour in [12, 13]:
        for mode in ["follow", "fade"]:
            for min_mult in [0.8, 1.1]:
                candidates.append(Candidate("london_direction_surface_v1", f"london_{mode}_h{hour}_min{min_mult}_tp08_sl08", {"entry_hour": hour, "mode": mode, "min_atr_mult": min_mult, "max_atr_mult": 4.0, "horizon_min": 180, "tp_atr": 0.8, "sl_atr": 0.8}))
    for hour in [9, 13, 15]:
        for mode in ["follow", "fade"]:
            for min_mult in [0.9, 1.3]:
                candidates.append(Candidate("day_open_extension_surface_v1", f"day_open_ext_{mode}_h{hour}_min{min_mult}_tp08_sl08", {"entry_hour": hour, "mode": mode, "min_atr_mult": min_mult, "max_atr_mult": 5.0, "horizon_min": 180, "tp_atr": 0.8, "sl_atr": 0.8}))
    for hour in [12, 13]:
        for mode in ["follow", "fade"]:
            for min_mult in [0.25, 0.5]:
                candidates.append(Candidate("prior_day_location_surface_v1", f"prior_ext_{mode}_h{hour}_min{min_mult}_tp08_sl08", {"entry_hour": hour, "mode": mode, "min_atr_mult": min_mult, "max_atr_mult": 4.0, "horizon_min": 180, "tp_atr": 0.8, "sl_atr": 0.8}))
    for hour in [12, 13]:
        for mode in ["follow", "fade"]:
            for aligned in [True, False]:
                candidates.append(Candidate("asia_london_alignment_surface_v1", f"asia_london_{'aligned' if aligned else 'diverge'}_{mode}_h{hour}_tp08_sl08", {"entry_hour": hour, "mode": mode, "aligned": aligned, "asia_min_atr": 0.25, "horizon_min": 180, "tp_atr": 0.8, "sl_atr": 0.8}))
    return candidates


def replay_m1(m1: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame()
    m = m1[["timestamp", "open", "high", "low", "close"]].copy().sort_values("timestamp").reset_index(drop=True)

    # Use integer nanosecond timestamps for searchsorted.
    # This avoids repeated NumPy warnings like:
    #   UserWarning: no explicit representation of timezones available for np.datetime64
    # when converting timezone-aware pandas Timestamp objects inside the replay loop.
    ts_values = pd.to_datetime(m["timestamp"], utc=True, errors="coerce").astype("int64").to_numpy()

    rows: List[Dict[str, Any]] = []
    for _, ev in events.iterrows():
        ts = pd.Timestamp(ev["timestamp"])
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        idx = int(np.searchsorted(ts_values, ts.value, side="left"))
        if idx >= len(m):
            continue
        direction = int(ev["direction"])
        entry_price = float(ev["entry_price"])
        atr = float(ev["atr"])
        if not math.isfinite(atr) or atr <= 0:
            continue
        tp = entry_price + direction * float(ev["tp_atr"]) * atr
        sl = entry_price - direction * float(ev["sl_atr"]) * atr
        end_ts = ts + pd.Timedelta(minutes=int(ev["horizon_min"]))
        end_idx = int(np.searchsorted(ts_values, end_ts.value, side="right"))
        future = m.iloc[idx:end_idx]
        if future.empty:
            continue
        exit_price = float(future.iloc[-1]["close"])
        exit_ts = future.iloc[-1]["timestamp"]
        exit_reason = "horizon"
        for _, bar in future.iterrows():
            hi = float(bar["high"])
            lo = float(bar["low"])
            if direction == 1:
                hit_tp = hi >= tp
                hit_sl = lo <= sl
            else:
                hit_tp = lo <= tp
                hit_sl = hi >= sl
            if hit_tp and hit_sl:
                # Conservative tie-break: adverse move first.
                exit_price = sl
                exit_ts = bar["timestamp"]
                exit_reason = "both_hit_assume_sl_first"
                break
            if hit_sl:
                exit_price = sl
                exit_ts = bar["timestamp"]
                exit_reason = "sl"
                break
            if hit_tp:
                exit_price = tp
                exit_ts = bar["timestamp"]
                exit_reason = "tp"
                break
        gross = (exit_price - entry_price) * direction
        row = ev.to_dict()
        row.update({"exit_time": exit_ts, "exit_price": exit_price, "exit_reason": exit_reason, "gross": gross})
        for mult in [1, 4, 6]:
            row[f"net_x{mult}"] = gross - ROUNDTRIP_COST_X1 * mult
        rows.append(row)
    return pd.DataFrame(rows)


def metrics(df: pd.DataFrame) -> Dict[str, Any]:
    if df is None or df.empty:
        return {"events": 0, "pf_x1": 0.0, "pf_x4": 0.0, "pf_x6": 0.0, "boot_pf_p05_x4": 0.0, "median_x4": 0.0, "total_x4": 0.0, "win_rate_x4": 0.0}
    return {
        "events": int(len(df)),
        "pf_x1": profit_factor(df["net_x1"]),
        "pf_x4": profit_factor(df["net_x4"]),
        "pf_x6": profit_factor(df["net_x6"]),
        "boot_pf_p05_x4": bootstrap_pf_p05(df["net_x4"].tolist()),
        "median_x4": float(pd.to_numeric(df["net_x4"], errors="coerce").median()),
        "total_x4": float(pd.to_numeric(df["net_x4"], errors="coerce").sum()),
        "win_rate_x4": float((pd.to_numeric(df["net_x4"], errors="coerce") > 0).mean()),
    }


def evaluate_candidate(m1: pd.DataFrame, m15: pd.DataFrame, h1: pd.DataFrame, daily: pd.DataFrame, c: Candidate) -> Tuple[Dict[str, Any], pd.DataFrame]:
    events = events_for_candidate(m15, h1, daily, c)
    if len(events) < MIN_EVENTS:
        base = {"family": c.family, "name": c.name, "events": int(len(events)), "decision": "STAGE27A_REJECT_MIN_EVENTS"}
        return base, pd.DataFrame()
    trades = replay_m1(m1, events)
    m = metrics(trades)
    decision = "STAGE27A_REJECT"
    if (
        m["events"] >= MIN_EVENTS
        and m["pf_x4"] >= 1.35
        and m["pf_x6"] >= 1.05
        and m["boot_pf_p05_x4"] >= 1.05
        and m["total_x4"] > 0
        and m["win_rate_x4"] >= 0.47
    ):
        decision = "STAGE27A_PROMOTION_REVIEW_RESEARCH_ONLY"
    elif m["events"] >= MIN_EVENTS and m["pf_x4"] >= 1.05 and m["total_x4"] > 0:
        decision = "STAGE27A_WATCHLIST_ONLY"
    out = {"decision": decision, "family": c.family, "name": c.name, **m}
    if not trades.empty:
        trades["candidate"] = c.name
        trades["family"] = c.family
    return out, trades


def select_family_balanced(results: pd.DataFrame) -> pd.DataFrame:
    valid = results[~results["decision"].eq("STAGE27A_REJECT_MIN_EVENTS")].copy()
    if valid.empty:
        return valid
    valid["rank_score"] = (
        valid["pf_x4"].replace(np.inf, 10).clip(upper=10) * 1.5
        + valid["pf_x6"].replace(np.inf, 10).clip(upper=10)
        + valid["boot_pf_p05_x4"].replace(np.inf, 10).clip(upper=10)
        + np.sign(valid["total_x4"]) * 0.25
    )
    picks: List[pd.DataFrame] = []
    for _, g in valid.sort_values("rank_score", ascending=False).groupby("family", sort=False):
        picks.append(g.head(MAX_EXACT_PER_FAMILY))
    selected = pd.concat(picks, ignore_index=True) if picks else pd.DataFrame()
    selected = selected.sort_values("rank_score", ascending=False).head(MAX_EXACT)
    return selected


def family_coverage(results: pd.DataFrame) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame()
    rows = []
    for fam, g in results.groupby("family"):
        pass_min = g[~g["decision"].eq("STAGE27A_REJECT_MIN_EVENTS")]
        rows.append({
            "family": fam,
            "candidates_tested": int(len(g)),
            "passing_min_events": int(len(pass_min)),
            "best_pf_x4": float(pass_min["pf_x4"].max()) if not pass_min.empty else 0.0,
            "best_pf_x6": float(pass_min["pf_x6"].max()) if not pass_min.empty else 0.0,
            "best_total_x4": float(pass_min["total_x4"].max()) if not pass_min.empty else 0.0,
        })
    return pd.DataFrame(rows).sort_values("best_pf_x4", ascending=False)


def write_error_report(exc: Exception) -> None:
    ensure_report_dir()
    payload = {"decision": "STAGE27A_ERROR_DIAGNOSTIC_ONLY", "error": f"{type(exc).__name__}: {exc}"}
    (REPORT_DIR / f"{STAGE}.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    md = [
        "# Stage27A DB-First Outcome-Surface Discovery",
        "",
        "## Decision",
        "",
        "```text",
        "STAGE27A_ERROR_DIAGNOSTIC_ONLY",
        "```",
        "",
        "## Error",
        "",
        "```text",
        f"{type(exc).__name__}: {exc}",
        "```",
        "",
        "- DB-first is enabled.",
        "- CSV market fallback is intentionally disabled.",
        "- Stage18A, Stage23D, and Stage25D remain unchanged.",
    ]
    (REPORT_DIR / f"{STAGE}.md").write_text("\n".join(md), encoding="utf-8")


def run() -> Dict[str, Any]:
    ensure_report_dir()
    start = time.time()
    if load_bars_from_db_stage25c is None:
        raise Stage27AError("Could not import Stage25C DB loader. Apply Stage25C patch first; CSV fallback is intentionally disabled.")
    m1_raw, h1_raw, db_meta, schema_diag = load_bars_from_db_stage25c(DEFAULT_DB_PATH)
    m1, h1, m15, norm_meta = normalize_bars(m1_raw, h1_raw)
    m15f, h1f, daily = prepare_features(m15, h1)

    candidates = generate_candidates()
    rows: List[Dict[str, Any]] = []
    trade_frames: List[pd.DataFrame] = []
    timed_out = False
    for c in candidates:
        if time.time() - start > MAX_RUNTIME_SECONDS:
            timed_out = True
            break
        r, t = evaluate_candidate(m1, m15f, h1f, daily, c)
        rows.append(r)
        if t is not None and not t.empty:
            trade_frames.append(t)

    results = pd.DataFrame(rows)
    if not results.empty:
        results = results.sort_values(["decision", "pf_x4", "pf_x6", "total_x4"], ascending=[True, False, False, False])
        results["_rank_decision"] = np.select(
            [results["decision"].str.contains("PROMOTION"), results["decision"].str.contains("WATCHLIST")],
            [0, 1],
            default=2,
        )
        results = results.sort_values(["_rank_decision", "pf_x4", "pf_x6", "total_x4"], ascending=[True, False, False, False]).drop(columns=["_rank_decision"])
    selected = select_family_balanced(results) if not results.empty else pd.DataFrame()
    cov = family_coverage(results)
    trades = pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame()

    promo_count = int(results["decision"].str.contains("PROMOTION").sum()) if not results.empty else 0
    watch_count = int(results["decision"].str.contains("WATCHLIST").sum()) if not results.empty else 0
    decision = "STAGE27A_NO_PROMOTION_KEEP_DISCOVERY_OPEN"
    if promo_count > 0:
        decision = "STAGE27A_HAS_PROMOTION_REVIEW_RESEARCH_ONLY"
    elif watch_count > 0:
        decision = "STAGE27A_HAS_WATCHLIST_ONLY_KEEP_DISCOVERY_OPEN"

    results.to_csv(REPORT_DIR / "stage27a_surface_candidates.csv", index=False)
    selected.to_csv(REPORT_DIR / "stage27a_family_balanced_top.csv", index=False)
    cov.to_csv(REPORT_DIR / "stage27a_family_coverage.csv", index=False)
    if trades.empty:
        pd.DataFrame().to_csv(REPORT_DIR / "stage27a_exact_trades.csv", index=False)
    else:
        trades.to_csv(REPORT_DIR / "stage27a_exact_trades.csv", index=False)
    try:
        schema_diag.to_csv(REPORT_DIR / "stage27a_db_schema_diagnostic.csv", index=False)
    except Exception:
        pd.DataFrame().to_csv(REPORT_DIR / "stage27a_db_schema_diagnostic.csv", index=False)

    payload = {
        "decision": decision,
        "db_meta": db_meta,
        "norm_meta": norm_meta,
        "counts": {
            "candidates_tested": int(len(results)),
            "candidates_passing_min_events": int((~results["decision"].eq("STAGE27A_REJECT_MIN_EVENTS")).sum()) if not results.empty else 0,
            "promotion_review_candidates": promo_count,
            "watchlist_only_candidates": watch_count,
            "timed_out": bool(timed_out),
            "runtime_seconds": round(time.time() - start, 2),
        },
    }
    (REPORT_DIR / f"{STAGE}.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    md: List[str] = []
    md += [
        "# Stage27A DB-First Outcome-Surface Discovery",
        "",
        f"Generated UTC: `{pd.Timestamp.utcnow().isoformat()}`",
        "",
        "## Decision",
        "",
        "```text",
        decision,
        "```",
        "",
        "## Scope guardrails",
        "",
        "- Research/shadow discovery only.",
        "- Stage18A v2 remains the active operational forward-shadow runner.",
        "- Stage23D and Stage25D remain separate DB-first trackers.",
        "- No EA change, no automatic trading, no paper/live/order authorization.",
        "- Candles are DB-first from SQLite via the validated Stage25C loader; AMarkets CSV market fallback is disabled.",
        "",
        "## DB source of truth",
        "",
        f"- db_path: `{db_meta.get('db_path', DEFAULT_DB_PATH)}`",
        f"- candle_table: `{db_meta.get('candle_table', '')}`",
        "- db_first: `True`",
        "- csv_fallback_enabled: `False`",
        f"- m1_rows: `{norm_meta['m1_rows_stage27a']}` | span: `{norm_meta['m1_span_stage27a']}`",
        f"- h1_rows: `{norm_meta['h1_rows_stage27a']}` | span: `{norm_meta['h1_span_stage27a']}`",
        f"- m15_rows: `{norm_meta['m15_rows_stage27a']}` | span: `{norm_meta['m15_span_stage27a']}`",
        "",
        "## Discovery surface families",
        "",
        "1. `hour_h1_bias_surface_v1` — fixed-hour follow/fade of H1 bias.",
        "2. `london_direction_surface_v1` — follow/fade London direction conditioned on London range size known before/at entry.",
        "3. `day_open_extension_surface_v1` — follow/fade extension away from day open known at entry.",
        "4. `prior_day_location_surface_v1` — follow/fade position outside prior-day high/low.",
        "5. `asia_london_alignment_surface_v1` — follow/fade Asia/London directional alignment.",
        "",
        "## Counts",
        "",
        f"- candidates_tested: `{payload['counts']['candidates_tested']}`",
        f"- candidates_passing_min_events: `{payload['counts']['candidates_passing_min_events']}`",
        f"- promotion_review_candidates: `{promo_count}`",
        f"- watchlist_only_candidates: `{watch_count}`",
        f"- timed_out: `{timed_out}`",
        f"- runtime_seconds: `{payload['counts']['runtime_seconds']}`",
        "",
        "## Family coverage diagnostics",
        markdown_table(cov, ["family", "candidates_tested", "passing_min_events", "best_pf_x4", "best_pf_x6", "best_total_x4"], 20),
        "",
        "## Top candidate diagnostics",
        markdown_table(results, ["decision", "family", "name", "events", "pf_x1", "pf_x4", "pf_x6", "boot_pf_p05_x4", "median_x4", "total_x4", "win_rate_x4"], 30),
        "",
        "## Family-balanced top seeds",
        markdown_table(selected, ["decision", "family", "name", "events", "pf_x1", "pf_x4", "pf_x6", "boot_pf_p05_x4", "median_x4", "total_x4", "win_rate_x4", "rank_score"], 24),
        "",
        "## Interpretation",
        "",
        "- Stage27A is not another mutation of Stage26A/B/C entries; it maps simple outcome surfaces to identify whether any broad time/regime/direction asymmetry exists.",
        "- A promotion-review result here is still research-only and would require a dedicated validation stage and separate forward-shadow tracker.",
        "- If no surface candidate survives, discovery should pivot toward no-trade/regime gating around the already stronger Stage23/25 lineage rather than inventing more raw entries.",
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
        "",
        f"- `data/reports/{STAGE}/{STAGE}.json`",
        f"- `data/reports/{STAGE}/{STAGE}.md`",
        f"- `data/reports/{STAGE}/stage27a_surface_candidates.csv`",
        f"- `data/reports/{STAGE}/stage27a_family_balanced_top.csv`",
        f"- `data/reports/{STAGE}/stage27a_exact_trades.csv`",
        f"- `data/reports/{STAGE}/stage27a_family_coverage.csv`",
        f"- `data/reports/{STAGE}/stage27a_db_schema_diagnostic.csv`",
    ]
    (REPORT_DIR / f"{STAGE}.md").write_text("\n".join(md), encoding="utf-8")
    return payload


def main() -> None:
    try:
        run()
    except Exception as exc:
        write_error_report(exc)
        raise


if __name__ == "__main__":
    main()
