#!/usr/bin/env python3
"""
Stage24C Remaining Behavior Discovery

Research/shadow-only. No EA, no paper/live/order authorization.

Controlled proxy-then-exact discovery over a fresh remaining XAUUSD behavior cluster:
1) previous-day expansion exhaustion reversal
2) NY opening-range failed breakout reversal
3) London midpoint-hold continuation

Design goals:
- CSV-first data load from AMarkets M1/H1 exports.
- M15 proxy over capped candidate set.
- M1 exact replay only for top, family-balanced candidates.
- Runtime capped; exact time reserved.
- Standalone module: does not modify Stage18A v2 or Stage23D.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "data" / "reports" / "stage24c_remaining_behavior_discovery"

DEFAULT_M1_PATHS = [
    Path.home() / "Downloads" / "amarkets_xauusd_1m.csv",
    ROOT / "data" / "amarkets_xauusd_1m.csv",
]
DEFAULT_H1_PATHS = [
    Path.home() / "Downloads" / "amarkets_xauusd_1h.csv",
    ROOT / "data" / "amarkets_xauusd_1h.csv",
]

ROUNDTRIP_COST_X1 = float(os.getenv("STAGE24C_ROUNDTRIP_COST_X1", "0.35"))
MAX_RUNTIME_SECONDS = int(os.getenv("STAGE24C_MAX_RUNTIME_SECONDS", "180"))
EXACT_RESERVED_SECONDS = int(os.getenv("STAGE24C_EXACT_RESERVED_SECONDS", "45"))
MAX_CANDIDATES_TOTAL = int(os.getenv("STAGE24C_MAX_CANDIDATES_TOTAL", "84"))
MAX_EXACT = int(os.getenv("STAGE24C_MAX_EXACT", "12"))
MAX_EXACT_PER_FAMILY = int(os.getenv("STAGE24C_MAX_EXACT_PER_FAMILY", "4"))
MIN_PROXY_EVENTS = int(os.getenv("STAGE24C_MIN_PROXY_EVENTS", "35"))
BOOT_SAMPLES = int(os.getenv("STAGE24C_BOOT_SAMPLES", "80"))


@dataclass(frozen=True)
class Candidate:
    family: str
    name: str
    params: Dict[str, Any]


@dataclass
class Event:
    candidate: str
    family: str
    direction: int
    entry_time: pd.Timestamp
    entry_price: float
    atr: float
    tp_atr: float
    sl_atr: float
    horizon_min: int
    meta: Dict[str, Any]


def _env_path(name: str) -> Optional[Path]:
    v = os.getenv(name)
    return Path(v).expanduser() if v else None


def _first_existing(paths: Iterable[Path]) -> Optional[Path]:
    for p in paths:
        if p and p.exists():
            return p
    return None


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    original_cols = list(df.columns)
    cols = {c: str(c).strip().lower().replace("<", "").replace(">", "") for c in df.columns}
    df = df.rename(columns=cols)

    # MT5 can export DATE + TIME separately.
    date_col = next((c for c in df.columns if c in {"date", "day"}), None)
    time_col = next((c for c in df.columns if c in {"time", "timestamp", "datetime"}), None)

    if date_col and time_col and date_col != time_col:
        dt = pd.to_datetime(df[date_col].astype(str) + " " + df[time_col].astype(str), errors="coerce", utc=True)
    elif time_col:
        dt = pd.to_datetime(df[time_col], errors="coerce", utc=True)
    elif "datetime" in df.columns:
        dt = pd.to_datetime(df["datetime"], errors="coerce", utc=True)
    else:
        # Last-resort: first column is usually timestamp.
        dt = pd.to_datetime(df.iloc[:, 0], errors="coerce", utc=True)

    col_map = {}
    synonyms = {
        "open": ["open", "o"],
        "high": ["high", "h"],
        "low": ["low", "l"],
        "close": ["close", "c", "last"],
    }
    for target, names in synonyms.items():
        for n in names:
            if n in df.columns:
                col_map[target] = n
                break
    missing = [k for k in ["open", "high", "low", "close"] if k not in col_map]
    if missing:
        raise ValueError(f"Cannot identify OHLC columns {missing}. Original columns: {original_cols}")

    out = pd.DataFrame(
        {
            "time": dt,
            "open": pd.to_numeric(df[col_map["open"]], errors="coerce"),
            "high": pd.to_numeric(df[col_map["high"]], errors="coerce"),
            "low": pd.to_numeric(df[col_map["low"]], errors="coerce"),
            "close": pd.to_numeric(df[col_map["close"]], errors="coerce"),
        }
    )
    out = out.dropna(subset=["time", "open", "high", "low", "close"])
    out = out.drop_duplicates("time").sort_values("time").reset_index(drop=True)
    return out


def read_ohlc_csv(path: Path) -> pd.DataFrame:
    # sep=None handles comma/semicolon/tab in most MT5 exports.
    try:
        df = pd.read_csv(path, sep=None, engine="python")
    except Exception:
        df = pd.read_csv(path)
    return _normalise_columns(df)


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    x = df.set_index("time")
    out = x.resample(rule, label="left", closed="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
    )
    out = out.dropna().reset_index()
    return out


def load_data() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, str, str, str]:
    m1_override = _env_path("STAGE24C_M1_CSV")
    h1_override = _env_path("STAGE24C_H1_CSV")
    m1_path = _first_existing([m1_override] if m1_override else DEFAULT_M1_PATHS)
    h1_path = _first_existing([h1_override] if h1_override else DEFAULT_H1_PATHS)
    if not m1_path:
        raise FileNotFoundError("M1 CSV not found. Set STAGE24C_M1_CSV or place amarkets_xauusd_1m.csv in ~/Downloads.")

    m1 = read_ohlc_csv(m1_path)
    if h1_path:
        h1 = read_ohlc_csv(h1_path)
    else:
        h1 = resample_ohlc(m1, "1h")
    m15 = resample_ohlc(m1, "15min")
    return m1, h1, m15, str(m1_path), str(h1_path) if h1_path else "resampled_from_m1", "csv_first"


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["date"] = out["time"].dt.date
    out["hour"] = out["time"].dt.hour
    out["minute"] = out["time"].dt.minute
    return out


def h1_daily_atr(h1: pd.DataFrame) -> pd.DataFrame:
    x = add_time_features(h1)
    x["tr_proxy"] = x["high"] - x["low"]
    daily = x.groupby("date", as_index=False).agg(
        day_high=("high", "max"),
        day_low=("low", "min"),
        day_open=("open", "first"),
        day_close=("close", "last"),
        atr_h1_mean=("tr_proxy", "mean"),
    )
    daily["day_range"] = daily["day_high"] - daily["day_low"]
    daily["atr"] = daily["atr_h1_mean"].rolling(14, min_periods=5).mean().shift(1)
    # If early history has no 14-day rolling value, use expanding prior mean.
    daily["atr"] = daily["atr"].fillna(daily["atr_h1_mean"].expanding(min_periods=3).mean().shift(1))
    daily["prev_high"] = daily["day_high"].shift(1)
    daily["prev_low"] = daily["day_low"].shift(1)
    daily["prev_range"] = daily["day_range"].shift(1)
    daily["prev2_range"] = daily["day_range"].shift(2)
    return daily


def candidate_grid() -> List[Candidate]:
    cands: List[Candidate] = []

    # Family 1: previous-day expansion exhaustion reversal.
    # Hypothesis: after an over-expanded previous day, a strong intraday extension into NY is more likely to mean-revert.
    for prev_expansion_atr in [1.20, 1.50]:
        for extension_atr in [0.45, 0.70]:
            for confirm_atr in [0.00, 0.10]:
                for entry_hour in [13, 15]:
                    for horizon_min in [90, 180]:
                        for tp_atr, sl_atr in [(0.6, 0.65), (0.8, 0.8)]:
                            name = f"prev_exp_exhaust_rev_px{prev_expansion_atr}_ext{extension_atr}_cf{confirm_atr}_h{horizon_min}_e{entry_hour}_tp{tp_atr}_sl{sl_atr}"
                            cands.append(Candidate("prev_day_expansion_exhaustion_reversal", name, dict(
                                prev_expansion_atr=prev_expansion_atr,
                                extension_atr=extension_atr,
                                confirm_atr=confirm_atr,
                                entry_hour=entry_hour,
                                horizon_min=horizon_min,
                                tp_atr=tp_atr,
                                sl_atr=sl_atr,
                            )))

    # Family 2: NY opening-range failed breakout reversal.
    # Hypothesis: if NY sweeps the London range and closes back inside, fade the failed break.
    for sweep_atr in [0.05, 0.15]:
        for reclaim_atr in [0.00, 0.05]:
            for entry_hour in [14, 15, 16]:
                for horizon_min in [90, 180]:
                    for tp_atr, sl_atr in [(0.6, 0.65)]:
                        name = f"ny_failed_or_rev_sw{sweep_atr}_rec{reclaim_atr}_h{horizon_min}_e{entry_hour}_tp{tp_atr}_sl{sl_atr}"
                        cands.append(Candidate("ny_opening_range_failed_breakout_reversal", name, dict(
                            sweep_atr=sweep_atr,
                            reclaim_atr=reclaim_atr,
                            entry_hour=entry_hour,
                            horizon_min=horizon_min,
                            tp_atr=tp_atr,
                            sl_atr=sl_atr,
                        )))

    # Family 3: London midpoint-hold continuation.
    # Hypothesis: when London establishes direction and NY holds above/below the London midpoint, continuation may persist.
    for london_move_atr in [0.60, 0.90]:
        for pullback_atr_max in [0.25, 0.45]:
            for mid_margin_atr in [0.00, 0.10]:
                for entry_hour in [13, 15]:
                    for horizon_min in [90, 180]:
                        for tp_atr, sl_atr in [(0.6, 0.65)]:
                            name = f"london_mid_hold_cont_lm{london_move_atr}_pb{pullback_atr_max}_mg{mid_margin_atr}_h{horizon_min}_e{entry_hour}_tp{tp_atr}_sl{sl_atr}"
                            cands.append(Candidate("london_midpoint_hold_continuation", name, dict(
                                london_move_atr=london_move_atr,
                                pullback_atr_max=pullback_atr_max,
                                mid_margin_atr=mid_margin_atr,
                                entry_hour=entry_hour,
                                horizon_min=horizon_min,
                                tp_atr=tp_atr,
                                sl_atr=sl_atr,
                            )))

    return cands[:MAX_CANDIDATES_TOTAL]


def _bar_at_or_before(day: pd.DataFrame, hour: int, minute: int = 0) -> Optional[pd.Series]:
    subset = day[(day["hour"] == hour) & (day["minute"] == minute)]
    if subset.empty:
        subset = day[(day["hour"] == hour)]
    if subset.empty:
        return None
    return subset.iloc[-1]


def generate_events_for_candidate(m15: pd.DataFrame, daily: pd.DataFrame, cand: Candidate) -> List[Event]:
    x = add_time_features(m15)
    daily_idx = daily.set_index("date")
    events: List[Event] = []

    for date, day in x.groupby("date", sort=True):
        if date not in daily_idx.index:
            continue
        d = daily_idx.loc[date]
        atr = float(d.get("atr", np.nan))
        if not np.isfinite(atr) or atr <= 0:
            continue

        p = cand.params
        entry_hour = int(p["entry_hour"])
        entry_bar = _bar_at_or_before(day, entry_hour, 0)
        if entry_bar is None:
            continue

        direction: Optional[int] = None
        meta: Dict[str, Any] = {}

        if cand.family == "prev_day_expansion_exhaustion_reversal":
            prev_range = float(d.get("prev_range", np.nan))
            day_open = float(d.get("day_open", np.nan))
            if not all(np.isfinite(v) for v in [prev_range, day_open]):
                continue
            if prev_range < float(p["prev_expansion_atr"]) * atr:
                continue
            extension = float(entry_bar["close"] - day_open)
            if abs(extension) < float(p["extension_atr"]) * atr:
                continue
            direction = -1 if extension > 0 else 1
            confirm_move = float(entry_bar["close"] - entry_bar["open"])
            if float(p["confirm_atr"]) > 0 and direction * confirm_move < float(p["confirm_atr"]) * atr:
                continue
            meta = {"prev_range": prev_range, "day_open": day_open, "extension": extension, "confirm_move": confirm_move}

        elif cand.family == "ny_opening_range_failed_breakout_reversal":
            london = day[(day["hour"] >= 7) & (day["hour"] < entry_hour)]
            recent = day[(day["hour"] >= max(7, entry_hour - 1)) & (day["hour"] <= entry_hour)]
            if london.empty or recent.empty:
                continue
            range_high = float(london["high"].max())
            range_low = float(london["low"].min())
            recent_high = float(recent["high"].max())
            recent_low = float(recent["low"].min())
            close = float(entry_bar["close"])
            sweep = float(p["sweep_atr"]) * atr
            reclaim = float(p["reclaim_atr"]) * atr
            if recent_high >= range_high + sweep and close <= range_high - reclaim:
                direction = -1
            elif recent_low <= range_low - sweep and close >= range_low + reclaim:
                direction = 1
            else:
                continue
            meta = {"range_high": range_high, "range_low": range_low, "recent_high": recent_high, "recent_low": recent_low}

        elif cand.family == "london_midpoint_hold_continuation":
            london = day[(day["hour"] >= 7) & (day["hour"] < entry_hour)]
            if london.empty:
                continue
            london_open = float(london.iloc[0]["open"])
            london_close = float(london.iloc[-1]["close"])
            london_high = float(london["high"].max())
            london_low = float(london["low"].min())
            london_move = london_close - london_open
            if abs(london_move) < float(p["london_move_atr"]) * atr:
                continue
            mid = (london_high + london_low) / 2.0
            close = float(entry_bar["close"])
            direction = 1 if london_move > 0 else -1
            margin = float(p["mid_margin_atr"]) * atr
            if direction > 0:
                if close < mid + margin:
                    continue
                pullback = london_high - close
            else:
                if close > mid - margin:
                    continue
                pullback = close - london_low
            if pullback > float(p["pullback_atr_max"]) * atr:
                continue
            meta = {"london_move": london_move, "london_high": london_high, "london_low": london_low, "mid": mid, "pullback": pullback}

        if direction is None:
            continue
        events.append(Event(
            candidate=cand.name,
            family=cand.family,
            direction=int(direction),
            entry_time=pd.Timestamp(entry_bar["time"]),
            entry_price=float(entry_bar["close"]),
            atr=atr,
            tp_atr=float(p["tp_atr"]),
            sl_atr=float(p["sl_atr"]),
            horizon_min=int(p["horizon_min"]),
            meta=meta,
        ))
    return events


def replay_events(events: List[Event], bars: pd.DataFrame, bar_rule_min: int) -> pd.DataFrame:
    if not events:
        return pd.DataFrame()
    b = bars[["time", "open", "high", "low", "close"]].copy().sort_values("time").reset_index(drop=True)
    times = b["time"].to_numpy(dtype="datetime64[ns]")
    highs = b["high"].to_numpy(float)
    lows = b["low"].to_numpy(float)
    closes = b["close"].to_numpy(float)

    rows: List[Dict[str, Any]] = []
    for ev in events:
        start = np.searchsorted(times, np.datetime64(ev.entry_time.to_datetime64()), side="right")
        end_time = ev.entry_time + pd.Timedelta(minutes=ev.horizon_min)
        end = np.searchsorted(times, np.datetime64(end_time.to_datetime64()), side="right")
        if start >= len(times) or end <= start:
            continue
        tp_price = ev.entry_price + ev.direction * ev.tp_atr * ev.atr
        sl_price = ev.entry_price - ev.direction * ev.sl_atr * ev.atr
        exit_price = closes[min(end - 1, len(closes) - 1)]
        exit_reason = "horizon_close"
        exit_time = pd.Timestamp(times[min(end - 1, len(times) - 1)])

        for i in range(start, min(end, len(times))):
            if ev.direction > 0:
                hit_tp = highs[i] >= tp_price
                hit_sl = lows[i] <= sl_price
            else:
                hit_tp = lows[i] <= tp_price
                hit_sl = highs[i] >= sl_price
            if hit_tp and hit_sl:
                # Conservative ambiguity handling: SL first if both touched inside one candle.
                exit_price = sl_price
                exit_reason = "sl_conservative"
                exit_time = pd.Timestamp(times[i])
                break
            if hit_sl:
                exit_price = sl_price
                exit_reason = "sl"
                exit_time = pd.Timestamp(times[i])
                break
            if hit_tp:
                exit_price = tp_price
                exit_reason = "tp"
                exit_time = pd.Timestamp(times[i])
                break

        gross = ev.direction * (float(exit_price) - ev.entry_price)
        row = {
            "candidate": ev.candidate,
            "family": ev.family,
            "direction": "long" if ev.direction > 0 else "short",
            "entry_time": ev.entry_time.isoformat(),
            "exit_time": exit_time.isoformat(),
            "entry_price": ev.entry_price,
            "exit_price": float(exit_price),
            "atr": ev.atr,
            "tp_atr": ev.tp_atr,
            "sl_atr": ev.sl_atr,
            "horizon_min": ev.horizon_min,
            "gross": gross,
            "net_x1": gross - ROUNDTRIP_COST_X1,
            "net_x4": gross - 4.0 * ROUNDTRIP_COST_X1,
            "net_x6": gross - 6.0 * ROUNDTRIP_COST_X1,
            "exit_reason": exit_reason,
        }
        row.update({f"meta_{k}": v for k, v in ev.meta.items()})
        rows.append(row)
    return pd.DataFrame(rows)


def pf(values: np.ndarray) -> float:
    if len(values) == 0:
        return 0.0
    gains = values[values > 0].sum()
    losses = -values[values < 0].sum()
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)


def bootstrap_pf_p05(values: np.ndarray, n: int = BOOT_SAMPLES) -> float:
    if len(values) < 20:
        return 0.0
    rng = np.random.default_rng(24024)
    pfs: List[float] = []
    for _ in range(n):
        sample = rng.choice(values, size=len(values), replace=True)
        pfs.append(pf(sample))
    finite = np.array([x for x in pfs if np.isfinite(x)], dtype=float)
    if len(finite) == 0:
        return float("inf")
    return float(np.percentile(finite, 5))


def summarize_trades(df: pd.DataFrame, cand: Candidate, source: str) -> Dict[str, Any]:
    if df.empty:
        return {
            "source": source,
            "family": cand.family,
            "name": cand.name,
            "events": 0,
            "pf_x1": 0.0,
            "pf_x4": 0.0,
            "pf_x6": 0.0,
            "test20_pf_x1": 0.0,
            "pf_2026_x1": 0.0,
            "boot_pf_p05_x1": 0.0,
            "median_x1": 0.0,
            "total_x1": 0.0,
            "rank_score": 0.0,
        }
    vals1 = df["net_x1"].to_numpy(float)
    vals4 = df["net_x4"].to_numpy(float)
    vals6 = df["net_x6"].to_numpy(float)
    test20 = df.tail(max(1, int(math.ceil(len(df) * 0.2))))
    years = pd.to_datetime(df["entry_time"], utc=True).dt.year
    y2026 = df[years == 2026]
    pf_x1 = pf(vals1)
    pf_x4 = pf(vals4)
    boot = bootstrap_pf_p05(vals1)
    test20_pf = pf(test20["net_x1"].to_numpy(float)) if not test20.empty else 0.0
    y2026_pf = pf(y2026["net_x1"].to_numpy(float)) if not y2026.empty else 0.0
    median_x1 = float(np.median(vals1)) if len(vals1) else 0.0
    total_x1 = float(np.sum(vals1)) if len(vals1) else 0.0
    # Rank favours cost-aware PF, lower-tail robustness, recency, and non-trivial median.
    score = (
        min(pf_x1 if np.isfinite(pf_x1) else 10.0, 10.0)
        + 1.6 * min(pf_x4 if np.isfinite(pf_x4) else 10.0, 10.0)
        + 1.3 * min(boot if np.isfinite(boot) else 10.0, 10.0)
        + 0.7 * min(test20_pf if np.isfinite(test20_pf) else 10.0, 10.0)
        + 0.05 * min(len(df), 250)
        + 0.2 * max(min(median_x1, 5.0), -5.0)
    )
    return {
        "source": source,
        "family": cand.family,
        "name": cand.name,
        "events": int(len(df)),
        "pf_x1": round(float(pf_x1), 4) if np.isfinite(pf_x1) else float("inf"),
        "pf_x4": round(float(pf_x4), 4) if np.isfinite(pf_x4) else float("inf"),
        "pf_x6": round(float(pf(vals6)), 4) if np.isfinite(pf(vals6)) else float("inf"),
        "test20_pf_x1": round(float(test20_pf), 4) if np.isfinite(test20_pf) else float("inf"),
        "pf_2026_x1": round(float(y2026_pf), 4) if np.isfinite(y2026_pf) else float("inf"),
        "boot_pf_p05_x1": round(float(boot), 4) if np.isfinite(boot) else float("inf"),
        "median_x1": round(float(median_x1), 4),
        "total_x1": round(float(total_x1), 4),
        "rank_score": round(float(score), 4),
    }


def run_proxy_grid(m15: pd.DataFrame, daily: pd.DataFrame, candidates: List[Candidate], deadline: float) -> Tuple[pd.DataFrame, Dict[str, List[Event]], bool]:
    rows: List[Dict[str, Any]] = []
    event_cache: Dict[str, List[Event]] = {}
    timed_out = False
    for cand in candidates:
        if time.monotonic() > deadline:
            timed_out = True
            break
        events = generate_events_for_candidate(m15, daily, cand)
        event_cache[cand.name] = events
        if len(events) < MIN_PROXY_EVENTS:
            continue
        trades = replay_events(events, m15, 15)
        row = summarize_trades(trades, cand, "M15_PROXY")
        if row["events"] >= MIN_PROXY_EVENTS:
            rows.append(row)
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["rank_score", "pf_x4", "events"], ascending=[False, False, False]).reset_index(drop=True)
    return df, event_cache, timed_out


def select_exact_candidates(proxy_df: pd.DataFrame, candidates: List[Candidate]) -> List[Candidate]:
    if proxy_df.empty:
        return []
    cand_by_name = {c.name: c for c in candidates}
    selected: List[Candidate] = []
    fam_counts: Dict[str, int] = {}
    for _, row in proxy_df.iterrows():
        name = row["name"]
        cand = cand_by_name.get(name)
        if cand is None:
            continue
        if fam_counts.get(cand.family, 0) >= MAX_EXACT_PER_FAMILY:
            continue
        selected.append(cand)
        fam_counts[cand.family] = fam_counts.get(cand.family, 0) + 1
        if len(selected) >= MAX_EXACT:
            break
    return selected


def decision_for_exact(row: Dict[str, Any]) -> str:
    if row["events"] >= 50 and row["pf_x4"] >= 1.25 and row["boot_pf_p05_x1"] >= 1.0 and row["test20_pf_x1"] >= 1.0 and row["total_x1"] > 0:
        return "STAGE24C_PROMOTION_CANDIDATE_REVIEW_ONLY"
    if row["events"] >= 50 and row["pf_x1"] >= 1.10 and row["total_x1"] > 0:
        return "STAGE24C_KEEP_WATCHLIST_ONLY"
    return "STAGE24C_REJECT"


def run_exact_replay(m1: pd.DataFrame, event_cache: Dict[str, List[Event]], selected: List[Candidate], deadline: float) -> Tuple[pd.DataFrame, pd.DataFrame, bool]:
    rows: List[Dict[str, Any]] = []
    trades_all: List[pd.DataFrame] = []
    timed_out = False
    for cand in selected:
        if time.monotonic() > deadline:
            timed_out = True
            break
        events = event_cache.get(cand.name) or []
        if len(events) < MIN_PROXY_EVENTS:
            continue
        trades = replay_events(events, m1, 1)
        if trades.empty:
            continue
        trades_all.append(trades)
        row = summarize_trades(trades, cand, "M1_EXACT")
        row["decision"] = decision_for_exact(row)
        rows.append(row)
    exact_df = pd.DataFrame(rows)
    if not exact_df.empty:
        exact_df = exact_df.sort_values(["decision", "rank_score", "pf_x4"], ascending=[True, False, False]).reset_index(drop=True)
    trades_df = pd.concat(trades_all, ignore_index=True) if trades_all else pd.DataFrame()
    return exact_df, trades_df, timed_out


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        if np.isinf(v):
            return "inf"
        return f"{v:.4f}".rstrip("0").rstrip(".")
    return str(v)


def markdown_table(df: pd.DataFrame, cols: List[str], limit: int) -> str:
    if df.empty:
        return "No rows."
    show = df[cols].head(limit)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in show.iterrows():
        lines.append("| " + " | ".join(_fmt(row[c]) for c in cols) + " |")
    return "\n".join(lines)


def render_markdown(report: Dict[str, Any], proxy_df: pd.DataFrame, exact_df: pd.DataFrame) -> str:
    lines: List[str] = []
    lines.append("# Stage24C Remaining Behavior Discovery")
    lines.append("")
    lines.append(f"Generated UTC: {pd.Timestamp.utcnow().isoformat()}")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("```text")
    lines.append(report["decision"])
    lines.append("```")
    lines.append("")
    lines.append("## Scope guardrails")
    lines.append("")
    lines.append("- Research/shadow only.")
    lines.append("- Stage18A v2 remains the active operational forward-shadow runner.")
    lines.append("- Stage23D remains a separate forward-shadow candidate tracker.")
    lines.append("- No EA change, no automatic trading, no paper/live/order authorization.")
    lines.append("- This module does not add candidates to Stage18A.")
    lines.append("")
    lines.append("## Data")
    lines.append("")
    for k in ["m1_rows", "m1_span", "h1_rows", "h1_span", "m15_proxy_rows", "m15_span", "roundtrip_cost_x1", "exact_replay_cap", "runtime_cap_seconds", "candidate_cap", "data_load_mode"]:
        lines.append(f"- {k}: {report[k]}")
    lines.append("")
    lines.append("## Discovery families")
    lines.append("")
    lines.append("1. `prev_day_expansion_exhaustion_reversal` — previous-day expansion followed by intraday extension/exhaustion reversal.")
    lines.append("2. `ny_opening_range_failed_breakout_reversal` — NY sweep of London range followed by reclaim/failure.")
    lines.append("3. `london_midpoint_hold_continuation` — London directional move that holds above/below midpoint into NY.")
    lines.append("")
    lines.append("## Counts")
    lines.append("")
    for k in ["proxy_candidates_tested", "proxy_candidates_passing_min_events", "exact_replayed", "promotion_review_candidates", "watchlist_only_candidates", "proxy_timed_out", "exact_timed_out"]:
        lines.append(f"- {k}: {report[k]}")
    lines.append("")
    lines.append("## Top exact M1 results")
    lines.append("")
    if exact_df.empty:
        lines.append("No exact candidates were replayed.")
    else:
        cols = ["decision", "family", "name", "events", "pf_x1", "pf_x4", "pf_x6", "test20_pf_x1", "pf_2026_x1", "boot_pf_p05_x1", "median_x1", "total_x1"]
        lines.append(markdown_table(exact_df, cols, 20))
    lines.append("")
    lines.append("## Top M15 proxy results")
    lines.append("")
    if proxy_df.empty:
        lines.append("No proxy candidates passed minimum events.")
    else:
        cols = ["family", "name", "events", "pf_x1", "pf_x4", "pf_x6", "test20_pf_x1", "boot_pf_p05_x1", "median_x1", "rank_score"]
        lines.append(markdown_table(proxy_df, cols, 20))
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("- Promotion-review here is still research-only.")
    lines.append("- A candidate cannot enter Stage18A from this module without separate validation and forward-shadow tracking.")
    lines.append("- If no promotion appears, close Stage24C and continue with a new behavior cluster rather than widening this grid indefinitely.")
    lines.append("")
    lines.append("## Operational reminder")
    lines.append("")
    lines.append("```bash")
    lines.append("cd ~/Desktop/xauusd-trader")
    lines.append("python3 -m app.stage18a_unified_shadow_ops_cycle")
    lines.append("cat data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.md")
    lines.append("")
    lines.append("python3 -m app.stage23d_forward_shadow_candidate")
    lines.append("cat data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_candidate.md")
    lines.append("```")
    lines.append("")
    lines.append("## Output files")
    lines.append("")
    lines.append("- `data/reports/stage24c_remaining_behavior_discovery/stage24c_remaining_behavior_discovery.json`")
    lines.append("- `data/reports/stage24c_remaining_behavior_discovery/stage24c_remaining_behavior_discovery.md`")
    lines.append("- `data/reports/stage24c_remaining_behavior_discovery/stage24c_proxy_candidates.csv`")
    lines.append("- `data/reports/stage24c_remaining_behavior_discovery/stage24c_exact_candidates.csv`")
    lines.append("- `data/reports/stage24c_remaining_behavior_discovery/stage24c_exact_trades.csv`")
    return "\n".join(lines) + "\n"


def json_safe(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_safe(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        if np.isinf(obj):
            return "inf"
        if np.isnan(obj):
            return None
        return float(obj)
    if isinstance(obj, float):
        if math.isinf(obj):
            return "inf"
        if math.isnan(obj):
            return None
    return obj


def main() -> None:
    t0 = time.monotonic()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    m1, h1, m15, m1_path, h1_path, load_mode = load_data()
    daily = h1_daily_atr(h1)
    candidates = candidate_grid()
    proxy_deadline = t0 + max(10, MAX_RUNTIME_SECONDS - EXACT_RESERVED_SECONDS)
    exact_deadline = t0 + MAX_RUNTIME_SECONDS

    proxy_df, event_cache, proxy_timed_out = run_proxy_grid(m15, daily, candidates, proxy_deadline)
    selected = select_exact_candidates(proxy_df, candidates)
    exact_df, trades_df, exact_timed_out = run_exact_replay(m1, event_cache, selected, exact_deadline)

    promotion_count = 0 if exact_df.empty else int((exact_df["decision"] == "STAGE24C_PROMOTION_CANDIDATE_REVIEW_ONLY").sum())
    watchlist_count = 0 if exact_df.empty else int((exact_df["decision"] == "STAGE24C_KEEP_WATCHLIST_ONLY").sum())
    if promotion_count > 0:
        decision = "STAGE24C_HAS_PROMOTION_REVIEW_CANDIDATE_RESEARCH_ONLY"
    elif watchlist_count > 0:
        decision = "STAGE24C_WATCHLIST_ONLY_KEEP_DISCOVERY_OPEN"
    else:
        decision = "STAGE24C_NO_PROMOTION_KEEP_DISCOVERY_OPEN"

    report = {
        "decision": decision,
        "m1_rows": int(len(m1)),
        "m1_span": f"{m1['time'].min()} → {m1['time'].max()}",
        "h1_rows": int(len(h1)),
        "h1_span": f"{h1['time'].min()} → {h1['time'].max()}",
        "m15_proxy_rows": int(len(m15)),
        "m15_span": f"{m15['time'].min()} → {m15['time'].max()}",
        "roundtrip_cost_x1": ROUNDTRIP_COST_X1,
        "exact_replay_cap": f"{MAX_EXACT} total / {MAX_EXACT_PER_FAMILY} per family",
        "runtime_cap_seconds": MAX_RUNTIME_SECONDS,
        "candidate_cap": MAX_CANDIDATES_TOTAL,
        "data_load_mode": load_mode,
        "m1_path": m1_path,
        "h1_path": h1_path,
        "proxy_candidates_tested": len(candidates),
        "proxy_candidates_passing_min_events": 0 if proxy_df.empty else int(len(proxy_df)),
        "exact_replayed": 0 if exact_df.empty else int(len(exact_df)),
        "promotion_review_candidates": promotion_count,
        "watchlist_only_candidates": watchlist_count,
        "proxy_timed_out": bool(proxy_timed_out),
        "exact_timed_out": bool(exact_timed_out),
        "elapsed_seconds": round(time.monotonic() - t0, 3),
        "candidates": [asdict(c) for c in candidates],
    }

    proxy_df.to_csv(REPORT_DIR / "stage24c_proxy_candidates.csv", index=False)
    exact_df.to_csv(REPORT_DIR / "stage24c_exact_candidates.csv", index=False)
    trades_df.to_csv(REPORT_DIR / "stage24c_exact_trades.csv", index=False)
    (REPORT_DIR / "stage24c_remaining_behavior_discovery.json").write_text(json.dumps(json_safe(report), indent=2), encoding="utf-8")
    (REPORT_DIR / "stage24c_remaining_behavior_discovery.md").write_text(render_markdown(report, proxy_df, exact_df), encoding="utf-8")
    print(f"Decision: {decision}")
    print(f"Report: {REPORT_DIR / 'stage24c_remaining_behavior_discovery.md'}")


if __name__ == "__main__":
    main()
