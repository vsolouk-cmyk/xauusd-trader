#!/usr/bin/env python3
"""
Stage29A — DB-first High-Range Regime Continuation Discovery.

Research/shadow only. No EA, paper/live mode, or order authorization.

Purpose
-------
Stage28C/28D showed that the canonical Stage23/25 lineage improves materially
when London range and prior-day range are high, but the lineage remains sparse.
Stage29A uses that insight to discover higher-density continuation variants
inside forward-safe high-range regimes instead of only filtering the sparse
Stage23B candidate.

Forward-safety rules
--------------------
- Candles are DB-first from SQLite via the validated Stage25C loader.
- AMarkets CSV market fallback is disabled.
- London features use the completed 07:00–13:00 UTC session and are only used
  for entries at or after 13:00 UTC.
- Prior-day range is known before the current session.
- Rolling/expanding quantile thresholds use only prior days, never full-sample
  future information.

Run:
    cd ~/Desktop/xauusd-trader
    python3 -m app.stage29a_high_range_regime_continuation_discovery
    cat data/reports/stage29a_high_range_regime_continuation_discovery/stage29a_high_range_regime_continuation_discovery.md
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

try:
    from app.stage25c_deduped_filter_validation import load_bars_from_db
except Exception as exc:  # pragma: no cover
    raise RuntimeError(
        "Stage29A requires app.stage25c_deduped_filter_validation.load_bars_from_db. "
        "Apply/run Stage25C before Stage29A. Original import error: " + str(exc)
    )


STAGE_NAME = "stage29a_high_range_regime_continuation_discovery"
REPORT_DIR = Path("data/reports") / STAGE_NAME
REPORT_MD = REPORT_DIR / "stage29a_high_range_regime_continuation_discovery.md"
REPORT_JSON = REPORT_DIR / "stage29a_high_range_regime_continuation_discovery.json"
CANDIDATES_CSV = REPORT_DIR / "stage29a_candidates.csv"
EXACT_TRADES_CSV = REPORT_DIR / "stage29a_exact_trades.csv"
FAMILY_COVERAGE_CSV = REPORT_DIR / "stage29a_family_coverage.csv"
FAMILY_SHORTLIST_CSV = REPORT_DIR / "stage29a_family_balanced_shortlist.csv"
DB_SCHEMA_CSV = REPORT_DIR / "stage29a_db_schema_diagnostic.csv"

DB_PATH = Path(os.getenv("STAGE29A_DB_PATH", "data/local/xauusd_local_store.sqlite")).expanduser()
RT_COST_X1 = float(os.getenv("STAGE29A_ROUNDTRIP_COST_X1", "0.35"))
MAX_RUNTIME_SECONDS = float(os.getenv("STAGE29A_MAX_RUNTIME_SECONDS", "240"))
MAX_CANDIDATES_PER_FAMILY = int(os.getenv("STAGE29A_MAX_CANDIDATES_PER_FAMILY", "10"))
MAX_TOTAL_CANDIDATES = int(os.getenv("STAGE29A_MAX_TOTAL_CANDIDATES", "48"))
MIN_EVENTS = int(os.getenv("STAGE29A_MIN_EVENTS", "45"))
BOOT_N = int(os.getenv("STAGE29A_BOOT_N", "120"))
RANDOM_SEED = int(os.getenv("STAGE29A_RANDOM_SEED", "2901"))

PROMO_PF_X4_MIN = float(os.getenv("STAGE29A_PROMO_PF_X4_MIN", "1.60"))
PROMO_PF_X6_MIN = float(os.getenv("STAGE29A_PROMO_PF_X6_MIN", "1.05"))
PROMO_BOOT_P05_X4_MIN = float(os.getenv("STAGE29A_PROMO_BOOT_P05_X4_MIN", "1.05"))
PROMO_TOTAL_X4_MIN = float(os.getenv("STAGE29A_PROMO_TOTAL_X4_MIN", "25"))
WATCH_PF_X4_MIN = float(os.getenv("STAGE29A_WATCH_PF_X4_MIN", "1.15"))


class Stage29AError(RuntimeError):
    pass


@dataclass(frozen=True)
class CandidateSpec:
    family: str
    name: str
    direction_mode: str
    entry_hour: int
    horizon_min: int
    tp_atr: float
    sl_atr: float
    london_q: float
    prior_q: Optional[float]
    asia_q: Optional[float]
    confirm_atr_min: float
    pullback_atr_max: Optional[float]
    breakout_atr_min: Optional[float]
    require_asia_london_align: bool


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _finite_json(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _finite_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_finite_json(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        x = float(obj)
        if math.isnan(x):
            return None
        if math.isinf(x):
            return "inf"
        return x
    if isinstance(obj, pd.Timestamp):
        return str(obj)
    return obj


def _fmt(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, (float, np.floating)):
        v = float(x)
        if math.isnan(v):
            return ""
        if math.isinf(v):
            return "inf"
        return f"{v:.4f}".rstrip("0").rstrip(".")
    return str(x)


def _norm_time_df(df: pd.DataFrame, label: str) -> pd.DataFrame:
    if df is None or df.empty:
        raise Stage29AError(f"Empty OHLC dataframe: {label}")
    out = df.copy()
    if "time" not in out.columns:
        if "timestamp" in out.columns:
            out = out.rename(columns={"timestamp": "time"})
        else:
            for c in ["datetime", "date_time", "bar_time", "broker_time", "ts"]:
                if c in out.columns:
                    out = out.rename(columns={c: "time"})
                    break
    if "time" not in out.columns:
        raise Stage29AError(f"No time/timestamp column in {label}; columns={list(df.columns)}")
    out["time"] = pd.to_datetime(out["time"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        if c not in out.columns:
            raise Stage29AError(f"Missing {c} column in {label}; columns={list(df.columns)}")
        out[c] = pd.to_numeric(out[c], errors="coerce")
    if "volume" not in out.columns:
        out["volume"] = 0.0
    out = out.dropna(subset=["time", "open", "high", "low", "close"]).sort_values("time")
    out = out.drop_duplicates("time", keep="last").reset_index(drop=True)
    return out[["time", "open", "high", "low", "close", "volume"]]


def _resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    x = df.copy().set_index("time").sort_index()
    out = (
        x[["open", "high", "low", "close", "volume"]]
        .resample(rule, label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["open", "high", "low", "close"])
        .reset_index()
    )
    return out


def load_market_data() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any], pd.DataFrame]:
    m1_raw, h1_raw, meta, schema_diag = load_bars_from_db(DB_PATH)
    m1 = _norm_time_df(m1_raw, "m1")
    if h1_raw is not None and not h1_raw.empty:
        h1 = _norm_time_df(h1_raw, "h1")
    else:
        h1 = _resample_ohlc(m1, "1h")
        meta["h1_mode_stage29a"] = "derived_from_m1_resample"
    m15 = _resample_ohlc(m1, "15min")
    meta.update({
        "db_first": True,
        "csv_fallback_enabled": False,
        "m1_rows_stage29a": int(len(m1)),
        "h1_rows_stage29a": int(len(h1)),
        "m15_rows_stage29a": int(len(m15)),
        "m1_span_stage29a": f"{m1['time'].min()} → {m1['time'].max()}" if len(m1) else "",
        "h1_span_stage29a": f"{h1['time'].min()} → {h1['time'].max()}" if len(h1) else "",
        "m15_span_stage29a": f"{m15['time'].min()} → {m15['time'].max()}" if len(m15) else "",
    })
    return m1, h1, m15, meta, schema_diag


def _atr_from_df(df: pd.DataFrame, period: int = 20) -> pd.Series:
    x = df.copy().sort_values("time")
    prev = x["close"].shift(1)
    tr = pd.concat([
        x["high"] - x["low"],
        (x["high"] - prev).abs(),
        (x["low"] - prev).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=max(5, period // 2)).mean()


def _pf(values: pd.Series) -> float:
    xs = pd.to_numeric(values, errors="coerce").dropna().astype(float)
    if len(xs) == 0:
        return 0.0
    pos = xs[xs > 0].sum()
    neg = -xs[xs < 0].sum()
    if neg == 0:
        return math.inf if pos > 0 else 0.0
    return float(pos / neg)


def _bootstrap_p05(values: pd.Series) -> float:
    xs = pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float)
    if len(xs) < 20:
        return 0.0
    rng = np.random.default_rng(RANDOM_SEED)
    vals: List[float] = []
    for _ in range(BOOT_N):
        sample = rng.choice(xs, size=len(xs), replace=True)
        pos = sample[sample > 0].sum()
        neg = -sample[sample < 0].sum()
        vals.append(math.inf if neg == 0 and pos > 0 else (0.0 if neg == 0 else float(pos / neg)))
    finite = np.array([v for v in vals if np.isfinite(v)], dtype=float)
    return float(np.percentile(finite, 5)) if len(finite) else 0.0


def metric_snapshot(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {
            "events": 0, "pf_x1": 0.0, "pf_x4": 0.0, "pf_x6": 0.0,
            "boot_pf_p05_x4": 0.0, "median_x4": 0.0, "total_x4": 0.0,
            "win_rate_x4": 0.0, "years_positive_x4": 0, "year_count": 0,
        }
    out = {
        "events": int(len(df)),
        "pf_x1": _pf(df["net_x1"]),
        "pf_x4": _pf(df["net_x4"]),
        "pf_x6": _pf(df["net_x6"]),
        "boot_pf_p05_x4": _bootstrap_p05(df["net_x4"]),
        "median_x4": float(pd.to_numeric(df["net_x4"], errors="coerce").median()),
        "total_x4": float(pd.to_numeric(df["net_x4"], errors="coerce").sum()),
        "win_rate_x4": float((pd.to_numeric(df["net_x4"], errors="coerce") > 0).mean()),
    }
    years = pd.to_datetime(df["entry_time"], utc=True, errors="coerce").dt.year
    yr = pd.DataFrame({"year": years, "x4": pd.to_numeric(df["net_x4"], errors="coerce")}).dropna().groupby("year")["x4"].sum()
    out["years_positive_x4"] = int((yr > 0).sum())
    out["year_count"] = int(len(yr))
    return out


def _decision(m: Dict[str, Any]) -> str:
    if (
        m.get("events", 0) >= MIN_EVENTS
        and m.get("pf_x4", 0) >= PROMO_PF_X4_MIN
        and m.get("pf_x6", 0) >= PROMO_PF_X6_MIN
        and m.get("boot_pf_p05_x4", 0) >= PROMO_BOOT_P05_X4_MIN
        and m.get("total_x4", 0) >= PROMO_TOTAL_X4_MIN
    ):
        return "STAGE29A_CANDIDATE_REVIEW_ONLY"
    if m.get("events", 0) >= MIN_EVENTS and m.get("pf_x4", 0) >= WATCH_PF_X4_MIN and m.get("total_x4", 0) > 0:
        return "STAGE29A_WATCHLIST_ONLY"
    return "STAGE29A_REJECT"


def _rank_score(m: Dict[str, Any]) -> float:
    pf4 = min(float(m.get("pf_x4", 0) if np.isfinite(m.get("pf_x4", 0)) else 8.0), 8.0)
    pf6 = min(float(m.get("pf_x6", 0) if np.isfinite(m.get("pf_x6", 0)) else 5.0), 5.0)
    boot = min(float(m.get("boot_pf_p05_x4", 0) if np.isfinite(m.get("boot_pf_p05_x4", 0)) else 5.0), 5.0)
    total = float(m.get("total_x4", 0))
    events = float(m.get("events", 0))
    return pf4 + 0.7 * pf6 + 0.8 * boot + 0.7 * np.tanh(total / 150.0) + 0.2 * np.tanh((events - MIN_EVENTS) / 250.0)


def _session_stats(g: pd.DataFrame, start_hour: int, end_hour: int) -> Dict[str, float]:
    t = pd.to_datetime(g["time"], utc=True, errors="coerce")
    s = g[(t.dt.hour >= start_hour) & (t.dt.hour < end_hour)].sort_values("time")
    if s.empty:
        return {"open": np.nan, "high": np.nan, "low": np.nan, "close": np.nan, "range": np.nan, "dir": np.nan, "eff": np.nan}
    op = float(s.iloc[0]["open"])
    cl = float(s.iloc[-1]["close"])
    hi = float(s["high"].max())
    lo = float(s["low"].min())
    rng = hi - lo
    return {"open": op, "high": hi, "low": lo, "close": cl, "range": rng, "dir": float(np.sign(cl - op)), "eff": abs(cl - op) / rng if rng > 0 else np.nan}


def build_daily_features(m15: pd.DataFrame) -> pd.DataFrame:
    x = m15.copy().sort_values("time")
    x["time"] = pd.to_datetime(x["time"], utc=True, errors="coerce")
    x = x.dropna(subset=["time"])
    x["event_day"] = x["time"].dt.floor("D")
    daily_ohlc = x.groupby("event_day").agg(day_high=("high", "max"), day_low=("low", "min"), day_open=("open", "first"), day_close=("close", "last"))
    daily_ohlc["day_range"] = daily_ohlc["day_high"] - daily_ohlc["day_low"]
    daily_ohlc["prior_day_range"] = daily_ohlc["day_range"].shift(1)
    rows: List[Dict[str, Any]] = []
    for day, g in x.groupby("event_day"):
        rec: Dict[str, Any] = {"event_day": day}
        for prefix, start, end in [("asia", 0, 7), ("london", 7, 13), ("ny_pre", 13, 16)]:
            stats = _session_stats(g, start, end)
            for k, v in stats.items():
                rec[f"{prefix}_{k}"] = v
        if day in daily_ohlc.index:
            rec["prior_day_range"] = float(daily_ohlc.loc[day, "prior_day_range"]) if pd.notna(daily_ohlc.loc[day, "prior_day_range"]) else np.nan
        rows.append(rec)
    d = pd.DataFrame(rows).sort_values("event_day").reset_index(drop=True)
    for col in ["prior_day_range", "asia_range", "london_range", "london_eff"]:
        if col in d.columns:
            # Shift(1) is the core forward-safety constraint: thresholds are trained only on prior days.
            base = pd.to_numeric(d[col], errors="coerce").shift(1)
            for q in [0.10, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.65, 0.70]:
                d[f"{col}_roll_q{int(q*100)}"] = base.rolling(250, min_periods=60).quantile(q)
    return d


def _entry_bar(m15: pd.DataFrame, day: pd.Timestamp, hour: int) -> Optional[pd.Series]:
    ts = pd.Timestamp(day).tz_convert("UTC") if pd.Timestamp(day).tzinfo else pd.Timestamp(day, tz="UTC")
    ts = ts + pd.Timedelta(hours=int(hour))
    idx = pd.DatetimeIndex(pd.to_datetime(m15["time"], utc=True, errors="coerce"))
    pos = idx.searchsorted(ts, side="left")
    if pos < len(m15) and idx[pos] == ts:
        return m15.iloc[pos]
    # Accept first M15 bar up to +15 minutes after nominal entry if exact timestamp is absent.
    if pos < len(m15) and idx[pos] <= ts + pd.Timedelta(minutes=15):
        return m15.iloc[pos]
    return None


def _m1_replay(
    m1_indexed: pd.DataFrame,
    entry_time: pd.Timestamp,
    direction: int,
    entry_price: float,
    atr: float,
    horizon_min: int,
    tp_atr: float,
    sl_atr: float,
) -> Dict[str, Any]:
    if not np.isfinite(entry_price) or not np.isfinite(atr) or atr <= 0:
        return {"exit_reason": "bad_input", "gross": 0.0, "exit_time": entry_time, "exit_price": entry_price}
    start = pd.Timestamp(entry_time)
    if start.tzinfo is None:
        start = start.tz_localize("UTC")
    else:
        start = start.tz_convert("UTC")
    end = start + pd.Timedelta(minutes=int(horizon_min))
    window = m1_indexed.loc[(m1_indexed.index > start) & (m1_indexed.index <= end)]
    if window.empty:
        return {"exit_reason": "no_window", "gross": 0.0, "exit_time": start, "exit_price": entry_price}
    tp = entry_price + direction * tp_atr * atr
    sl = entry_price - direction * sl_atr * atr
    for t, r in window.iterrows():
        hit_tp = bool(r["high"] >= tp) if direction > 0 else bool(r["low"] <= tp)
        hit_sl = bool(r["low"] <= sl) if direction > 0 else bool(r["high"] >= sl)
        if hit_tp and hit_sl:
            # Conservative same-M1 ordering.
            exit_price = sl
            return {"exit_reason": "both_hit_conservative_sl", "gross": float(direction * (exit_price - entry_price)), "exit_time": t, "exit_price": float(exit_price)}
        if hit_tp:
            return {"exit_reason": "tp", "gross": float(direction * (tp - entry_price)), "exit_time": t, "exit_price": float(tp)}
        if hit_sl:
            return {"exit_reason": "sl", "gross": float(direction * (sl - entry_price)), "exit_time": t, "exit_price": float(sl)}
    exit_price = float(window["close"].iloc[-1])
    return {"exit_reason": "horizon", "gross": float(direction * (exit_price - entry_price)), "exit_time": window.index[-1], "exit_price": exit_price}


def registry() -> List[CandidateSpec]:
    specs: List[CandidateSpec] = []
    # A: Broader high-range continuation than Stage23B; no tiny pullback constraint.
    for hour in [13, 14, 15]:
        for lq in [0.35, 0.40, 0.50, 0.60]:
            for pq in [0.10, 0.25, 0.35]:
                for confirm in [0.00, 0.10]:
                    specs.append(CandidateSpec(
                        "high_range_london_continuation_v1",
                        f"hr_london_follow_h{hour}_lq{int(lq*100)}_pq{int(pq*100)}_c{str(confirm).replace('.', '')}_tp06_sl065",
                        "follow_london", hour, 180, 0.60, 0.65, lq, pq, None, confirm, None, None, False,
                    ))
    # B: High-range continuation with broad pullback acceptance; aims for higher density than pb0.1.
    for hour in [13, 14]:
        for lq in [0.40, 0.60]:
            for pb in [0.25, 0.50, 0.80]:
                for tp, sl in [(0.55, 0.65), (0.70, 0.80)]:
                    specs.append(CandidateSpec(
                        "high_range_broad_pullback_continuation_v1",
                        f"hr_broad_pb_h{hour}_lq{int(lq*100)}_pb{str(pb).replace('.', '')}_tp{str(tp).replace('.', '')}_sl{str(sl).replace('.', '')}",
                        "follow_london", hour, 180, tp, sl, lq, 0.25, None, 0.00, pb, None, False,
                    ))
    # C: London breakout continuation after high London/prior-day range.
    for hour in [13, 14, 15]:
        for lq in [0.40, 0.60]:
            for b in [0.00, 0.10, 0.20]:
                specs.append(CandidateSpec(
                    "high_range_london_breakout_follow_v1",
                    f"hr_london_breakout_h{hour}_lq{int(lq*100)}_b{str(b).replace('.', '')}_tp06_sl08",
                    "follow_london", hour, 180, 0.60, 0.80, lq, 0.25, None, 0.00, None, b, False,
                ))
    # D: Asia + London aligned high-range handoff.
    for hour in [13, 14]:
        for lq in [0.35, 0.40, 0.60]:
            for aq in [0.25, 0.35, 0.40]:
                specs.append(CandidateSpec(
                    "high_range_asia_london_alignment_v1",
                    f"hr_asia_london_align_h{hour}_lq{int(lq*100)}_aq{int(aq*100)}_tp06_sl065",
                    "follow_london", hour, 180, 0.60, 0.65, lq, None, aq, 0.00, None, None, True,
                ))
    return specs


def _q_col(name: str, q: Optional[float]) -> Optional[str]:
    if q is None:
        return None
    return f"{name}_roll_q{int(round(q*100))}"


def _event_passes(spec: CandidateSpec, drow: pd.Series, entry: pd.Series, atr: float) -> Tuple[bool, Optional[int], str]:
    london_dir = drow.get("london_dir")
    if pd.isna(london_dir) or london_dir == 0:
        return False, None, "missing_london_direction"
    direction = int(np.sign(london_dir))

    # Main high-range gate using prior-day rolling thresholds only.
    lq_col = _q_col("london_range", spec.london_q)
    if lq_col is None or lq_col not in drow or pd.isna(drow.get("london_range")) or pd.isna(drow.get(lq_col)):
        return False, None, "missing_london_threshold"
    if float(drow["london_range"]) < float(drow[lq_col]):
        return False, None, "london_range_below_prior_roll_quantile"

    if spec.prior_q is not None:
        pq_col = _q_col("prior_day_range", spec.prior_q)
        if pq_col is None or pq_col not in drow or pd.isna(drow.get("prior_day_range")) or pd.isna(drow.get(pq_col)):
            return False, None, "missing_prior_day_threshold"
        if float(drow["prior_day_range"]) < float(drow[pq_col]):
            return False, None, "prior_day_range_below_prior_roll_quantile"

    if spec.asia_q is not None:
        aq_col = _q_col("asia_range", spec.asia_q)
        if aq_col is None or aq_col not in drow or pd.isna(drow.get("asia_range")) or pd.isna(drow.get(aq_col)):
            return False, None, "missing_asia_threshold"
        if float(drow["asia_range"]) < float(drow[aq_col]):
            return False, None, "asia_range_below_prior_roll_quantile"

    if spec.require_asia_london_align:
        asia_dir = drow.get("asia_dir")
        if pd.isna(asia_dir) or asia_dir == 0 or int(np.sign(asia_dir)) != direction:
            return False, None, "asia_london_not_aligned"

    if not np.isfinite(atr) or atr <= 0:
        return False, None, "bad_atr"

    entry_open = float(entry["open"])
    entry_close = float(entry["close"])
    confirm = direction * (entry_close - entry_open) / atr
    if confirm < spec.confirm_atr_min:
        return False, None, "entry_confirm_too_small"

    if spec.pullback_atr_max is not None:
        london_close = drow.get("london_close")
        if pd.isna(london_close):
            return False, None, "missing_london_close"
        # Positive value means price pulled back against London direction from London close.
        pullback = max(0.0, -direction * (entry_close - float(london_close)) / atr)
        if pullback > spec.pullback_atr_max:
            return False, None, "pullback_too_deep"

    if spec.breakout_atr_min is not None:
        lh = drow.get("london_high")
        ll = drow.get("london_low")
        if pd.isna(lh) or pd.isna(ll):
            return False, None, "missing_london_extreme"
        if direction > 0:
            broke = float(entry["high"]) >= float(lh) + spec.breakout_atr_min * atr
        else:
            broke = float(entry["low"]) <= float(ll) - spec.breakout_atr_min * atr
        if not broke:
            return False, None, "no_london_breakout"

    return True, direction, "passed_high_range_regime"


def _interleave_specs(specs: List[CandidateSpec]) -> List[CandidateSpec]:
    by_family: Dict[str, List[CandidateSpec]] = {}
    order: List[str] = []
    for s in specs:
        if s.family not in by_family:
            by_family[s.family] = []
            order.append(s.family)
        by_family[s.family].append(s)
    by_family = {fam: vals[:MAX_CANDIDATES_PER_FAMILY] for fam, vals in by_family.items()}
    out: List[CandidateSpec] = []
    max_len = max((len(v) for v in by_family.values()), default=0)
    for i in range(max_len):
        for fam in order:
            if i < len(by_family[fam]):
                out.append(by_family[fam][i])
    return out[:MAX_TOTAL_CANDIDATES]


def evaluate_candidate(
    spec: CandidateSpec,
    m1_indexed: pd.DataFrame,
    m15: pd.DataFrame,
    daily: pd.DataFrame,
    m15_atr: pd.Series,
    replay_cache: Dict[Tuple[str, int, int, float, float], Dict[str, Any]],
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for _, drow in daily.iterrows():
        day = drow["event_day"]
        entry = _entry_bar(m15, day, spec.entry_hour)
        if entry is None:
            continue
        et = pd.Timestamp(entry["time"])
        atr_val = np.nan
        if et in m15_atr.index:
            atr_val = float(m15_atr.loc[et])
        if not np.isfinite(atr_val) or atr_val <= 0:
            atr_val = float(entry["high"] - entry["low"])
        ok, direction, reason = _event_passes(spec, drow, entry, atr_val)
        if not ok or direction is None:
            continue
        key = (str(et), int(direction), int(spec.horizon_min), float(spec.tp_atr), float(spec.sl_atr))
        if key in replay_cache:
            replay = replay_cache[key]
        else:
            replay = _m1_replay(m1_indexed, et, int(direction), float(entry["close"]), atr_val, spec.horizon_min, spec.tp_atr, spec.sl_atr)
            replay_cache[key] = replay
        gross = float(replay["gross"])
        rows.append({
            "candidate": spec.name,
            "family": spec.family,
            "entry_time": et,
            "entry_hour": spec.entry_hour,
            "direction": int(direction),
            "entry_price": float(entry["close"]),
            "atr": float(atr_val),
            "horizon_min": int(spec.horizon_min),
            "tp_atr": float(spec.tp_atr),
            "sl_atr": float(spec.sl_atr),
            "exit_time": replay["exit_time"],
            "exit_price": float(replay["exit_price"]),
            "exit_reason": replay["exit_reason"],
            "gross": gross,
            "net_x1": gross - RT_COST_X1,
            "net_x4": gross - 4 * RT_COST_X1,
            "net_x6": gross - 6 * RT_COST_X1,
            "reason": reason,
            "london_range": drow.get("london_range"),
            "prior_day_range": drow.get("prior_day_range"),
            "asia_range": drow.get("asia_range"),
            "london_q": spec.london_q,
            "prior_q": spec.prior_q,
            "asia_q": spec.asia_q,
            "confirm_atr_min": spec.confirm_atr_min,
            "pullback_atr_max": spec.pullback_atr_max,
            "breakout_atr_min": spec.breakout_atr_min,
        })
    trades = pd.DataFrame(rows)
    m = metric_snapshot(trades)
    m.update(asdict(spec))
    m["decision"] = _decision(m)
    m["rank_score"] = _rank_score(m)
    return trades, m


def _family_coverage(candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame()
    rows: List[Dict[str, Any]] = []
    for fam, g in candidates.groupby("family"):
        g2 = g.sort_values(["rank_score", "pf_x4", "total_x4"], ascending=False)
        top = g2.iloc[0]
        rows.append({
            "family": fam,
            "candidates_tested": int(len(g)),
            "passing_min_events": int((g["events"] >= MIN_EVENTS).sum()),
            "review_count": int((g["decision"] == "STAGE29A_CANDIDATE_REVIEW_ONLY").sum()),
            "watchlist_count": int((g["decision"] == "STAGE29A_WATCHLIST_ONLY").sum()),
            "best_name": top["name"],
            "best_pf_x4": top["pf_x4"],
            "best_pf_x6": top["pf_x6"],
            "best_total_x4": top["total_x4"],
            "best_events": int(top["events"]),
        })
    return pd.DataFrame(rows).sort_values(["review_count", "best_pf_x4", "best_total_x4"], ascending=False)


def _shortlist(candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        return candidates
    c = candidates.sort_values(["rank_score", "pf_x4", "total_x4"], ascending=False)
    rows = []
    for _, g in c.groupby("family", sort=False):
        rows.append(g.head(3))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def run() -> Dict[str, Any]:
    started = time.time()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    m1, h1, m15, db_meta, schema_diag = load_market_data()
    daily = build_daily_features(m15)
    m15_work = m15.copy().sort_values("time").reset_index(drop=True)
    m15_work["atr20"] = _atr_from_df(m15_work, 20)
    m15_atr = pd.Series(m15_work["atr20"].to_numpy(), index=pd.DatetimeIndex(pd.to_datetime(m15_work["time"], utc=True)))
    m1_indexed = m1.copy().set_index(pd.DatetimeIndex(pd.to_datetime(m1["time"], utc=True))).sort_index()

    raw_specs = registry()
    specs = _interleave_specs(raw_specs)
    all_metrics: List[Dict[str, Any]] = []
    trade_parts: List[pd.DataFrame] = []
    replay_cache: Dict[Tuple[str, int, int, float, float], Dict[str, Any]] = {}
    timed_out = False

    for spec in specs:
        if time.time() - started > MAX_RUNTIME_SECONDS:
            timed_out = True
            break
        trades, met = evaluate_candidate(spec, m1_indexed, m15, daily, m15_atr, replay_cache)
        all_metrics.append(met)
        if not trades.empty:
            trade_parts.append(trades)

    candidates = pd.DataFrame(all_metrics)
    if not candidates.empty:
        candidates = candidates.sort_values(["decision", "rank_score", "pf_x4", "total_x4"], ascending=[True, False, False, False])
    
    clean_parts = [part.dropna(axis=1, how="all") for part in trade_parts if part is not None and not part.empty]
    clean_parts = [part for part in clean_parts if not part.empty]
    exact_trades = pd.concat(clean_parts, ignore_index=True) if clean_parts else pd.DataFrame()
    fam_df = _family_coverage(candidates)
    shortlist = _shortlist(candidates)

    review_count = int((candidates.get("decision", pd.Series(dtype=str)) == "STAGE29A_CANDIDATE_REVIEW_ONLY").sum()) if not candidates.empty else 0
    watch_count = int((candidates.get("decision", pd.Series(dtype=str)) == "STAGE29A_WATCHLIST_ONLY").sum()) if not candidates.empty else 0
    decision = "STAGE29A_HAS_HIGH_RANGE_CONTINUATION_CANDIDATE_REVIEW_ONLY" if review_count else ("STAGE29A_HAS_WATCHLIST_ONLY" if watch_count else "STAGE29A_NO_PROMOTION_KEEP_DISCOVERY_OPEN")

    candidates.to_csv(CANDIDATES_CSV, index=False)
    exact_trades.to_csv(EXACT_TRADES_CSV, index=False)
    fam_df.to_csv(FAMILY_COVERAGE_CSV, index=False)
    shortlist.to_csv(FAMILY_SHORTLIST_CSV, index=False)
    if schema_diag is not None and not getattr(schema_diag, "empty", True):
        schema_diag.to_csv(DB_SCHEMA_CSV, index=False)
    else:
        pd.DataFrame([db_meta]).to_csv(DB_SCHEMA_CSV, index=False)

    result: Dict[str, Any] = {
        "generated_utc": _utc_now(),
        "decision": decision,
        "scope_guardrails": [
            "Research/shadow discovery only.",
            "Stage18A/23D/25D/27D/28D remain unchanged.",
            "No EA change, no automatic trading, no paper/live/order authorization.",
            "Candles are DB-first from SQLite via Stage25C loader; AMarkets CSV fallback is disabled.",
            "London range is completed before entries at 13:00+; quantile thresholds are prior-day rolling only.",
        ],
        "db_source_of_truth": db_meta,
        "thesis": {
            "name": "high_range_regime_continuation_density_expansion",
            "description": "Use Stage28C high London/prior range insight to create denser continuation variants, not merely gate the sparse Stage23B event.",
        },
        "counts": {
            "registry_candidate_count": int(len(raw_specs)),
            "scheduled_candidate_count": int(len(specs)),
            "candidates_tested": int(len(candidates)),
            "candidates_passing_min_events": int((candidates.get("events", pd.Series(dtype=int)) >= MIN_EVENTS).sum()) if not candidates.empty else 0,
            "candidate_review_count": review_count,
            "watchlist_only_count": watch_count,
            "family_count": int(candidates["family"].nunique()) if not candidates.empty else 0,
            "replay_cache_size": int(len(replay_cache)),
            "timed_out": bool(timed_out),
            "runtime_seconds": round(time.time() - started, 2),
        },
        "family_coverage": fam_df.to_dict(orient="records") if not fam_df.empty else [],
        "top_candidates": candidates.head(30).to_dict(orient="records") if not candidates.empty else [],
        "output_files": [
            str(REPORT_JSON), str(REPORT_MD), str(CANDIDATES_CSV), str(EXACT_TRADES_CSV),
            str(FAMILY_COVERAGE_CSV), str(FAMILY_SHORTLIST_CSV), str(DB_SCHEMA_CSV),
        ],
    }
    return result


def write_report(result: Dict[str, Any]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(_finite_json(result), indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    lines: List[str] = []
    lines.append("# Stage29A DB-First High-Range Regime Continuation Discovery\n")
    lines.append(f"Generated UTC: `{result['generated_utc']}`\n")
    lines.append("## Decision\n")
    lines.append("```text")
    lines.append(str(result["decision"]))
    lines.append("```\n")
    lines.append("## Scope guardrails\n")
    for item in result["scope_guardrails"]:
        lines.append(f"- {item}")
    lines.append("\n## Thesis\n")
    lines.append(f"- name: `{result['thesis']['name']}`")
    lines.append(f"- description: {result['thesis']['description']}")
    lines.append("\n## DB source of truth\n")
    for k, v in result["db_source_of_truth"].items():
        lines.append(f"- {k}: `{_fmt(v)}`")
    lines.append("\n## Counts\n")
    for k, v in result["counts"].items():
        lines.append(f"- {k}: `{_fmt(v)}`")
    lines.append("\n## Family coverage\n")
    fam_cols = ["family", "candidates_tested", "passing_min_events", "review_count", "watchlist_count", "best_name", "best_events", "best_pf_x4", "best_pf_x6", "best_total_x4"]
    lines.append("| " + " | ".join(fam_cols) + " |")
    lines.append("| " + " | ".join(["---"] * len(fam_cols)) + " |")
    for r in result["family_coverage"][:20]:
        lines.append("| " + " | ".join(_fmt(r.get(c, "")) for c in fam_cols) + " |")
    lines.append("\n## Top candidate diagnostics\n")
    cols = ["decision", "family", "name", "events", "pf_x1", "pf_x4", "pf_x6", "boot_pf_p05_x4", "median_x4", "total_x4", "win_rate_x4", "years_positive_x4", "year_count", "rank_score"]
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("| " + " | ".join(["---"] * len(cols)) + " |")
    for r in result["top_candidates"][:30]:
        lines.append("| " + " | ".join(_fmt(r.get(c, "")) for c in cols) + " |")
    lines.append("\n## Interpretation\n")
    lines.append("- Stage29A is not another generic raw-entry grid; it explicitly uses the Stage28C high-range insight to seek more signal density.")
    lines.append("- A candidate-review result remains research-only and needs a dedicated validation stage plus a separate forward-shadow tracker.")
    lines.append("- If Stage29A does not produce candidates, the next useful step is not more OHLC-only mutation; it is exogenous/macro/news feature integration or ML meta-labeling on a larger candidate pool.")
    lines.append("\n## Operational reminder\n")
    lines.append("```bash")
    lines.append("cd ~/Desktop/xauusd-trader")
    lines.append("python3 -m app.run_active_shadow_suite")
    lines.append("python3 -m app.stage28d_forward_safe_meta_gate_tracker")
    lines.append("python3 -m app.stage29a_high_range_regime_continuation_discovery")
    lines.append("```")
    lines.append("\n## Output files\n")
    for f in result["output_files"]:
        lines.append(f"- `{f}`")
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    try:
        result = run()
    except Exception as exc:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        err = {
            "generated_utc": _utc_now(),
            "decision": "STAGE29A_ERROR_DIAGNOSTIC_ONLY",
            "error": f"{type(exc).__name__}: {exc}",
            "scope_guardrails": [
                "Research/shadow only.",
                "CSV market fallback is disabled.",
                "Active trackers remain unchanged.",
            ],
        }
        REPORT_JSON.write_text(json.dumps(err, indent=2, ensure_ascii=False), encoding="utf-8")
        REPORT_MD.write_text(
            "# Stage29A DB-First High-Range Regime Continuation Discovery\n\n"
            "## Decision\n\n```text\nSTAGE29A_ERROR_DIAGNOSTIC_ONLY\n```\n\n"
            "## Error\n\n```text\n" + err["error"] + "\n```\n",
            encoding="utf-8",
        )
        raise
    write_report(result)


if __name__ == "__main__":
    main()
