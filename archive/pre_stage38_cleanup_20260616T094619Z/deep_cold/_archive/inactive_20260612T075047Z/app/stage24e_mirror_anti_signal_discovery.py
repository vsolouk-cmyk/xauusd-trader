#!/usr/bin/env python3
"""
Stage24E Mirror / Anti-Signal Discovery

Research/shadow-only. No EA, no paper/live/order authorization.

Controlled proxy-then-exact discovery over mirror/anti-signal behavior clusters:
1) day-open extension continuation mirror
2) previous-day expansion continuation mirror
3) London range breakout-hold continuation mirror

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
REPORT_DIR = ROOT / "data" / "reports" / "stage24e_mirror_anti_signal_discovery"

DEFAULT_M1_PATHS = [
    Path.home() / "Downloads" / "amarkets_xauusd_1m.csv",
    ROOT / "data" / "amarkets_xauusd_1m.csv",
]
DEFAULT_H1_PATHS = [
    Path.home() / "Downloads" / "amarkets_xauusd_1h.csv",
    ROOT / "data" / "amarkets_xauusd_1h.csv",
]

ROUNDTRIP_COST_X1 = float(os.getenv("STAGE24E_ROUNDTRIP_COST_X1", "0.35"))
MAX_RUNTIME_SECONDS = int(os.getenv("STAGE24E_MAX_RUNTIME_SECONDS", "180"))
EXACT_RESERVED_SECONDS = int(os.getenv("STAGE24E_EXACT_RESERVED_SECONDS", "45"))
MAX_CANDIDATES_TOTAL = int(os.getenv("STAGE24E_MAX_CANDIDATES_TOTAL", "84"))
MAX_EXACT = int(os.getenv("STAGE24E_MAX_EXACT", "12"))
MAX_EXACT_PER_FAMILY = int(os.getenv("STAGE24E_MAX_EXACT_PER_FAMILY", "4"))
MIN_PROXY_EVENTS = int(os.getenv("STAGE24E_MIN_PROXY_EVENTS", "35"))
BOOT_SAMPLES = int(os.getenv("STAGE24E_BOOT_SAMPLES", "80"))


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
    m1_override = _env_path("STAGE24E_M1_CSV")
    h1_override = _env_path("STAGE24E_H1_CSV")
    m1_path = _first_existing([m1_override] if m1_override else DEFAULT_M1_PATHS)
    h1_path = _first_existing([h1_override] if h1_override else DEFAULT_H1_PATHS)
    if not m1_path:
        raise FileNotFoundError("M1 CSV not found. Set STAGE24E_M1_CSV or place amarkets_xauusd_1m.csv in ~/Downloads.")

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
    daily["prev2_high"] = daily["day_high"].shift(2)
    daily["prev2_low"] = daily["day_low"].shift(2)
    daily["prev_open"] = daily["day_open"].shift(1)
    daily["prev_close"] = daily["day_close"].shift(1)
    daily["prev_body"] = (daily["prev_close"] - daily["prev_open"]).abs()
    daily["prev_dir"] = np.sign(daily["prev_close"] - daily["prev_open"])
    return daily


def candidate_grid() -> List[Candidate]:
    cands: List[Candidate] = []

    # Family 1: day-open extension continuation mirror.
    # Mirror of rejected Stage24D day-open reclaim reversal: if reclaim/reversal fails,
    # does extension away from the daily open continue into NY?
    for extension_atr in [0.45, 0.70, 0.95]:
        for confirm_atr in [0.00, 0.05, 0.10]:
            for entry_hour in [14, 15, 16]:
                for horizon_min in [90, 180]:
                    for tp_atr, sl_atr in [(0.6, 0.65), (0.8, 0.8)]:
                        name = f"day_open_ext_cont_ext{extension_atr}_cf{confirm_atr}_h{horizon_min}_e{entry_hour}_tp{tp_atr}_sl{sl_atr}"
                        cands.append(Candidate("day_open_extension_continuation", name, dict(
                            extension_atr=extension_atr,
                            confirm_atr=confirm_atr,
                            entry_hour=entry_hour,
                            horizon_min=horizon_min,
                            tp_atr=tp_atr,
                            sl_atr=sl_atr,
                        )))

    # Family 2: previous-day expansion continuation mirror.
    # Mirror of rejected exhaustion-reversal logic: if yesterday expanded and had direction,
    # does same-direction NY continuation persist after current-day extension?
    for prev_range_atr_min in [1.00, 1.25, 1.50]:
        for current_ext_atr in [0.35, 0.55, 0.75]:
            for entry_hour in [13, 15]:
                for horizon_min in [90, 180]:
                    for tp_atr, sl_atr in [(0.6, 0.65), (0.8, 0.8)]:
                        name = f"prev_exp_cont_pr{prev_range_atr_min}_ext{current_ext_atr}_h{horizon_min}_e{entry_hour}_tp{tp_atr}_sl{sl_atr}"
                        cands.append(Candidate("prev_day_expansion_continuation", name, dict(
                            prev_range_atr_min=prev_range_atr_min,
                            current_ext_atr=current_ext_atr,
                            entry_hour=entry_hour,
                            horizon_min=horizon_min,
                            tp_atr=tp_atr,
                            sl_atr=sl_atr,
                        )))

    # Family 3: London range breakout-hold continuation mirror.
    # Mirror of stop-run/reclaim behavior: if NY breaks a London extreme and HOLDS outside,
    # test continuation instead of reclaim/fade.
    for london_range_atr_max in [0.70, 1.00, 1.40]:
        for break_atr in [0.05, 0.15, 0.25]:
            for hold_atr in [0.00, 0.05, 0.10]:
                for entry_hour in [15, 16]:
                    for horizon_min in [90, 180]:
                        for tp_atr, sl_atr in [(0.6, 0.65)]:
                            name = f"london_break_hold_cont_rng{london_range_atr_max}_br{break_atr}_hd{hold_atr}_h{horizon_min}_e{entry_hour}_tp{tp_atr}_sl{sl_atr}"
                            cands.append(Candidate("london_range_breakout_hold_continuation", name, dict(
                                london_range_atr_max=london_range_atr_max,
                                break_atr=break_atr,
                                hold_atr=hold_atr,
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

        if cand.family == "day_open_extension_continuation":
            day_open = float(d.get("day_open", np.nan))
            if not np.isfinite(day_open):
                continue
            prior = day[(day["hour"] >= 0) & (day["hour"] <= entry_hour)]
            if prior.empty:
                continue
            prior_high = float(prior["high"].max())
            prior_low = float(prior["low"].min())
            close = float(entry_bar["close"])
            extension = float(p["extension_atr"]) * atr
            confirm = float(p["confirm_atr"]) * atr
            if prior_high >= day_open + extension and close >= day_open + confirm:
                direction = 1
            elif prior_low <= day_open - extension and close <= day_open - confirm:
                direction = -1
            else:
                continue
            meta = {
                "day_open": day_open,
                "prior_high": prior_high,
                "prior_low": prior_low,
                "close": close,
            }

        elif cand.family == "prev_day_expansion_continuation":
            vals = [
                d.get("prev_range", np.nan), d.get("prev_open", np.nan),
                d.get("prev_close", np.nan), d.get("prev_dir", np.nan),
            ]
            if not all(np.isfinite(float(v)) for v in vals):
                continue
            prev_range, prev_open, prev_close, prev_dir = [float(v) for v in vals]
            if prev_range < float(p["prev_range_atr_min"]) * atr:
                continue
            if prev_dir == 0:
                continue
            current = day[(day["hour"] >= 0) & (day["hour"] <= entry_hour)]
            if current.empty:
                continue
            day_open = float(d.get("day_open", np.nan))
            close = float(entry_bar["close"])
            current_high = float(current["high"].max())
            current_low = float(current["low"].min())
            ext = float(p["current_ext_atr"]) * atr
            if prev_dir > 0 and current_high >= day_open + ext and close >= day_open:
                direction = 1
            elif prev_dir < 0 and current_low <= day_open - ext and close <= day_open:
                direction = -1
            else:
                continue
            meta = {
                "prev_open": prev_open,
                "prev_close": prev_close,
                "prev_range": prev_range,
                "prev_dir": prev_dir,
                "day_open": day_open,
                "current_high": current_high,
                "current_low": current_low,
                "close": close,
            }

        elif cand.family == "london_range_breakout_hold_continuation":
            london = day[(day["hour"] >= 7) & (day["hour"] < 13)]
            recent = day[(day["hour"] >= 13) & (day["hour"] <= entry_hour)]
            if london.empty or recent.empty:
                continue
            london_high = float(london["high"].max())
            london_low = float(london["low"].min())
            london_range = london_high - london_low
            if london_range > float(p["london_range_atr_max"]) * atr:
                continue
            close = float(entry_bar["close"])
            recent_high = float(recent["high"].max())
            recent_low = float(recent["low"].min())
            br = float(p["break_atr"]) * atr
            hold = float(p["hold_atr"]) * atr
            if recent_high >= london_high + br and close >= london_high + hold:
                direction = 1
            elif recent_low <= london_low - br and close <= london_low - hold:
                direction = -1
            else:
                continue
            meta = {
                "london_high": london_high,
                "london_low": london_low,
                "london_range": london_range,
                "recent_high": recent_high,
                "recent_low": recent_low,
                "close": close,
            }

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
        return "STAGE24E_PROMOTION_CANDIDATE_REVIEW_ONLY"
    if row["events"] >= 50 and row["pf_x1"] >= 1.10 and row["total_x1"] > 0:
        return "STAGE24E_KEEP_WATCHLIST_ONLY"
    return "STAGE24E_REJECT"


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
    lines.append("# Stage24E Mirror / Anti-Signal Discovery")
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
    lines.append("1. `day_open_extension_continuation` — mirror of rejected day-open reclaim/reversal: extension away from daily open continues.")
    lines.append("2. `prev_day_expansion_continuation` — mirror of exhaustion reversal: yesterday's expansion direction continues after current-day extension.")
    lines.append("3. `london_range_breakout_hold_continuation` — mirror of London stop-run/reclaim: NY break holds outside London range and continues.")
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
    lines.append("- If no promotion appears, close Stage24E and move to a non-entry discovery track such as regime/no-trade filters rather than widening mirror grids indefinitely.")
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
    lines.append("- `data/reports/stage24e_mirror_anti_signal_discovery/stage24e_mirror_anti_signal_discovery.json`")
    lines.append("- `data/reports/stage24e_mirror_anti_signal_discovery/stage24e_mirror_anti_signal_discovery.md`")
    lines.append("- `data/reports/stage24e_mirror_anti_signal_discovery/stage24e_proxy_candidates.csv`")
    lines.append("- `data/reports/stage24e_mirror_anti_signal_discovery/stage24e_exact_candidates.csv`")
    lines.append("- `data/reports/stage24e_mirror_anti_signal_discovery/stage24e_exact_trades.csv`")
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

    promotion_count = 0 if exact_df.empty else int((exact_df["decision"] == "STAGE24E_PROMOTION_CANDIDATE_REVIEW_ONLY").sum())
    watchlist_count = 0 if exact_df.empty else int((exact_df["decision"] == "STAGE24E_KEEP_WATCHLIST_ONLY").sum())
    if promotion_count > 0:
        decision = "STAGE24E_HAS_PROMOTION_REVIEW_CANDIDATE_RESEARCH_ONLY"
    elif watchlist_count > 0:
        decision = "STAGE24E_WATCHLIST_ONLY_KEEP_DISCOVERY_OPEN"
    else:
        decision = "STAGE24E_NO_PROMOTION_KEEP_DISCOVERY_OPEN"

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

    proxy_df.to_csv(REPORT_DIR / "stage24e_proxy_candidates.csv", index=False)
    exact_df.to_csv(REPORT_DIR / "stage24e_exact_candidates.csv", index=False)
    trades_df.to_csv(REPORT_DIR / "stage24e_exact_trades.csv", index=False)
    (REPORT_DIR / "stage24e_mirror_anti_signal_discovery.json").write_text(json.dumps(json_safe(report), indent=2), encoding="utf-8")
    (REPORT_DIR / "stage24e_mirror_anti_signal_discovery.md").write_text(render_markdown(report, proxy_df, exact_df), encoding="utf-8")
    print(f"Decision: {decision}")
    print(f"Report: {REPORT_DIR / 'stage24e_mirror_anti_signal_discovery.md'}")


if __name__ == "__main__":
    main()
