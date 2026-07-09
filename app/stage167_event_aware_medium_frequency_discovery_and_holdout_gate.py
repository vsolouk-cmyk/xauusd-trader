#!/usr/bin/env python3
"""
Stage167C Event-Aware Medium-Frequency Discovery and Holdout Gate

Commercial-purpose read-only discovery gate for XAUUSD/gold.

Hotfix C fixes sparse historical event panels by computing event thresholds on the positive train distribution, while keeping fast-stop protection for truly empty panels.

This stage is designed specifically to avoid the recurring project failure mode:
low-frequency rules + weak edge + waiting for more samples.

What it does:
- Reads broker bars, preferably AMarkets M5.
- Reads Stage166 current-event shock overlay if available.
- Builds train/holdout split with the newest holdout_pct segment locked as final validation.
- Scans deterministic medium-frequency event-aware rule families.
- Evaluates cost/slippage-adjusted outcomes on train and holdout separately.
- Kills candidates that are too low-frequency, unstable, or holdout-negative.

What it does NOT do:
- It does not write MT5 execution files.
- It does not authorize demo/live orders.
- It does not tune on holdout.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

STAGE = "Stage167_EVENT_AWARE_MEDIUM_FREQUENCY_DISCOVERY_AND_HOLDOUT_GATE"


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def normalize_col(c: Any) -> str:
    s = str(c).strip().strip("\ufeff")
    s = re.sub(r"[<>]", "", s)
    return s.lower().replace(" ", "_").replace("-", "_")


def _read_csv_auto(path: Path, nrows: Optional[int] = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(str(path))
    seps = ["\t", ",", ";", "|"]
    best_sep = ","
    best_score = -1
    for sep in seps:
        try:
            sample = pd.read_csv(path, sep=sep, nrows=5)
            score = len(sample.columns)
            if score > best_score:
                best_score = score
                best_sep = sep
        except Exception:
            pass
    return pd.read_csv(path, sep=best_sep, nrows=nrows)


def load_bars(path: Path, timestamp_shift_hours: float = -3.0) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    df = _read_csv_auto(path)
    raw_columns = list(df.columns)
    df.columns = [normalize_col(c) for c in df.columns]
    meta: Dict[str, Any] = {
        "source_path": str(path),
        "raw_columns": raw_columns,
        "raw_row_count": int(len(df)),
        "timestamp_shift_hours": timestamp_shift_hours,
    }

    if "date" in df.columns and "time" in df.columns:
        ts = pd.to_datetime(
            df["date"].astype(str).str.strip() + " " + df["time"].astype(str).str.strip(),
            format="%Y.%m.%d %H:%M:%S",
            errors="coerce",
            utc=False,
        )
        # AMarkets MT5 server has been treated as UTC+3 in this project; default shift converts to UTC.
        ts = ts + pd.to_timedelta(timestamp_shift_hours, unit="h")
        ts = pd.to_datetime(ts, utc=True, errors="coerce")
        meta["parse_mode"] = "mt5_split_date_time"
    else:
        time_col = None
        for c in ["time_utc", "utc_time", "datetime", "timestamp", "server_time", "time", "date"]:
            if c in df.columns:
                time_col = c
                break
        if time_col is None:
            for c in df.columns:
                if any(x in c for x in ["date", "time", "utc"]):
                    time_col = c
                    break
        if time_col is None:
            raise ValueError(f"No timestamp column in {path}; columns={list(df.columns)}")
        ts = pd.to_datetime(df[time_col], errors="coerce", utc=True)
        if timestamp_shift_hours and time_col not in {"time_utc", "utc_time"}:
            ts = ts + pd.to_timedelta(timestamp_shift_hours, unit="h")
        meta["parse_mode"] = f"single_timestamp:{time_col}"

    out = pd.DataFrame({"time_utc": ts})
    colmap = {
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "tickvol": "volume",
        "tick_volume": "volume",
        "real_volume": "real_volume",
        "vol": "real_volume",
        "volume": "volume",
        "spread": "spread",
        "spread_points": "spread",
    }
    for src, dst in colmap.items():
        if src in df.columns:
            out[dst] = pd.to_numeric(df[src], errors="coerce")
    for c in ["open", "high", "low", "close"]:
        if c not in out.columns:
            raise ValueError(f"Missing OHLC column {c}; columns={list(df.columns)}")
    if "volume" not in out.columns:
        out["volume"] = 0.0
    if "spread" not in out.columns:
        out["spread"] = float("nan")

    out = out.dropna(subset=["time_utc", "open", "high", "low", "close"]).copy()
    out = out.sort_values("time_utc").drop_duplicates("time_utc", keep="last").reset_index(drop=True)
    meta.update({
        "bar_count": int(len(out)),
        "min_time_utc": str(out["time_utc"].min()) if len(out) else None,
        "max_time_utc": str(out["time_utc"].max()) if len(out) else None,
        "spread_nonnull_pct": float(out["spread"].notna().mean() * 100.0) if len(out) else 0.0,
    })
    return out, meta


def timeframe_minutes(bars: pd.DataFrame) -> int:
    if len(bars) < 3:
        return 5
    d = bars["time_utc"].sort_values().diff().dropna().dt.total_seconds() / 60.0
    med = float(d.median()) if len(d) else 5.0
    if not math.isfinite(med) or med <= 0:
        return 5
    return max(1, int(round(med)))


def find_time_col(df: pd.DataFrame) -> Optional[str]:
    for c in ["time_utc", "utc_time", "bar_time_utc", "window_start_utc", "timestamp", "datetime", "date"]:
        if c in df.columns:
            return c
    for c in df.columns:
        if any(x in c for x in ["time", "date", "utc"]):
            return c
    return None


def load_event_panel(path: Path, bars: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    meta: Dict[str, Any] = {"event_panel_path": str(path), "loaded": False}
    if not path.exists():
        neutral = pd.DataFrame({"time_utc": bars["time_utc"].copy()})
        return neutral_event_columns(neutral), {**meta, "reason": "missing_event_panel_neutralized"}

    df = _read_csv_auto(path)
    raw_columns = list(df.columns)
    df.columns = [normalize_col(c) for c in df.columns]
    time_col = find_time_col(df)
    if time_col is None:
        neutral = pd.DataFrame({"time_utc": bars["time_utc"].copy()})
        return neutral_event_columns(neutral), {**meta, "reason": "no_time_col_neutralized", "raw_columns": raw_columns}

    df["time_utc"] = pd.to_datetime(df[time_col], errors="coerce", utc=True)
    df = df.dropna(subset=["time_utc"]).sort_values("time_utc").drop_duplicates("time_utc", keep="last").reset_index(drop=True)
    df = neutral_event_columns(df)
    meta.update({
        "loaded": True,
        "raw_columns": raw_columns,
        "row_count": int(len(df)),
        "min_time_utc": str(df["time_utc"].min()) if len(df) else None,
        "max_time_utc": str(df["time_utc"].max()) if len(df) else None,
        "columns": list(df.columns),
    })
    return df, meta


def neutral_event_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    numeric_defaults = {
        "gold_long_pressure": 0.0,
        "gold_short_pressure": 0.0,
        "shock_abs": 0.0,
        "geopolitical_escalation_score": 0.0,
        "deescalation_score": 0.0,
        "macro_policy_hawkish_score": 0.0,
        "macro_policy_dovish_score": 0.0,
        "inflation_energy_shock_score": 0.0,
        "gold_direct_score": 0.0,
        "event_count": 0.0,
        "event_count_weighted": 0.0,
    }
    text_defaults = {
        "event_side_bias": "NONE",
        "event_shock_regime": "EVENT_NEUTRAL",
    }
    for c, v in numeric_defaults.items():
        if c not in out.columns:
            out[c] = v
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(v)
    for c, v in text_defaults.items():
        if c not in out.columns:
            out[c] = v
        out[c] = out[c].astype(str).replace({"nan": v, "None": v}).fillna(v)
    return out


def enrich_features(bars: pd.DataFrame, event_panel: pd.DataFrame, spread_point_size: float, cost_bps: float) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    x = bars.copy().sort_values("time_utc").reset_index(drop=True)
    tf_min = timeframe_minutes(x)
    x["tf_min"] = tf_min
    x["bar_index"] = range(len(x))
    x["ret_1_bps"] = (x["close"] / x["close"].shift(1) - 1.0) * 10000.0
    for n in [3, 6, 12, 24, 48, 96, 192]:
        x[f"ret_{n}_bps"] = (x["close"] / x["close"].shift(n) - 1.0) * 10000.0
    tr_components = pd.concat([
        (x["high"] - x["low"]).abs(),
        (x["high"] - x["close"].shift(1)).abs(),
        (x["low"] - x["close"].shift(1)).abs(),
    ], axis=1)
    x["tr"] = tr_components.max(axis=1)
    x["tr_bps"] = x["tr"] / x["close"] * 10000.0
    for w in [12, 48, 96, 288]:
        x[f"atr_{w}_bps"] = x["tr_bps"].rolling(w, min_periods=max(5, min(w // 3, 20))).mean()
        x[f"range_pct_rank_{w}"] = x["tr_bps"].rolling(w, min_periods=max(10, min(w // 2, 30))).rank(pct=True)
    x["body_bps"] = (x["close"] - x["open"]) / x["open"] * 10000.0
    x["upper_wick_bps"] = (x["high"] - x[["open", "close"]].max(axis=1)) / x["close"] * 10000.0
    x["lower_wick_bps"] = (x[["open", "close"]].min(axis=1) - x["low"]) / x["close"] * 10000.0
    x["hour_utc"] = x["time_utc"].dt.hour
    x["dow"] = x["time_utc"].dt.dayofweek
    x["session"] = x["hour_utc"].map(session_label)
    x["spread_bps_est"] = pd.to_numeric(x.get("spread"), errors="coerce") * spread_point_size / x["close"] * 10000.0
    x["spread_bps_est"] = x["spread_bps_est"].where(x["spread_bps_est"].between(0, 50), float("nan"))
    x["effective_cost_bps"] = x["spread_bps_est"].fillna(cost_bps) + cost_bps

    e = event_panel.copy().sort_values("time_utc").reset_index(drop=True)
    e = neutral_event_columns(e)
    event_cols = [
        "time_utc", "gold_long_pressure", "gold_short_pressure", "shock_abs",
        "geopolitical_escalation_score", "deescalation_score", "macro_policy_hawkish_score",
        "macro_policy_dovish_score", "inflation_energy_shock_score", "gold_direct_score",
        "event_count", "event_count_weighted", "event_side_bias", "event_shock_regime",
    ]
    for c in event_cols:
        if c not in e.columns:
            e[c] = 0.0 if c not in {"event_side_bias", "event_shock_regime"} else "NONE"
    joined = pd.merge_asof(
        x.sort_values("time_utc"),
        e[event_cols].sort_values("time_utc"),
        on="time_utc",
        direction="backward",
        tolerance=pd.Timedelta(hours=6),
        suffixes=("", "_event"),
    )
    joined = neutral_event_columns(joined)
    meta = {"timeframe_minutes": tf_min, "feature_row_count": int(len(joined))}
    return joined, meta


def session_label(hour: int) -> str:
    if 0 <= int(hour) < 7:
        return "ASIA"
    if 7 <= int(hour) < 12:
        return "LONDON_OPEN"
    if 12 <= int(hour) < 16:
        return "LONDON_NY_OVERLAP"
    if 16 <= int(hour) < 21:
        return "NY_PM"
    return "OFFHOURS"


def compute_train_thresholds(train: pd.DataFrame) -> Dict[str, float]:
    """Compute train-only thresholds.

    Stage167B incorrectly treated sparse but valid historical news panels as
    unusable because quantiles were computed over every M5 bar. A GDELT-style
    hourly event panel is naturally sparse; most M5 bars have zero news pressure,
    so all-bar q50/q80 can be zero even when thousands of train bars carry
    real event signal. For event columns we therefore compute effective
    thresholds on the strictly positive train distribution and keep all-bar
    quantiles only as diagnostics. Technical thresholds remain all-bar.
    """
    def _series(col: str) -> pd.Series:
        return pd.to_numeric(train.get(col), errors="coerce").dropna()

    def q_all(col: str, p: float, default: float = 0.0) -> float:
        vals = _series(col)
        if len(vals) < 10:
            return default
        v = float(vals.quantile(p))
        return v if math.isfinite(v) else default

    def q_pos(col: str, p: float, default: float = 0.0, min_count: int = 10) -> float:
        vals = _series(col)
        vals = vals[vals > 0]
        if len(vals) < min_count:
            return default
        v = float(vals.quantile(p))
        return v if math.isfinite(v) else default

    shock_pos_count = int((_series("shock_abs") > 0).sum())
    long_pos_count = int((_series("gold_long_pressure") > 0).sum())
    short_pos_count = int((_series("gold_short_pressure") > 0).sum())

    thresholds: Dict[str, float] = {
        # Effective event thresholds used by rule profiles.
        "shock_q50": q_pos("shock_abs", 0.50, 0.0),
        "shock_q60": q_pos("shock_abs", 0.60, 0.0),
        "shock_q70": q_pos("shock_abs", 0.70, 0.0),
        "shock_q80": q_pos("shock_abs", 0.80, 0.0),
        "long_q60": q_pos("gold_long_pressure", 0.60, 0.0),
        "long_q75": q_pos("gold_long_pressure", 0.75, 0.0),
        "short_q60": q_pos("gold_short_pressure", 0.60, 0.0),
        "short_q75": q_pos("gold_short_pressure", 0.75, 0.0),
        # Diagnostics: all-bar quantiles explain sparsity and should not gate valid sparse panels.
        "shock_allbar_q80": q_all("shock_abs", 0.80, 0.0),
        "long_allbar_q75": q_all("gold_long_pressure", 0.75, 0.0),
        "short_allbar_q75": q_all("gold_short_pressure", 0.75, 0.0),
        "shock_positive_train_count": float(shock_pos_count),
        "long_positive_train_count": float(long_pos_count),
        "short_positive_train_count": float(short_pos_count),
        "event_threshold_source": "positive_train_distribution",
        # Technical thresholds.
        "atr48_q40": q_all("atr_48_bps", 0.40, 1.0),
        "atr48_q60": q_all("atr_48_bps", 0.60, 2.0),
        "atr48_q80": q_all("atr_48_bps", 0.80, 4.0),
        "mom6_abs_q55": q_all("ret_6_bps", 0.55, 0.0),
        "mom12_abs_q55": q_all("ret_12_bps", 0.55, 0.0),
        "range96_q60": q_all("range_pct_rank_96", 0.60, 0.5),
        "range96_q80": q_all("range_pct_rank_96", 0.80, 0.8),
    }
    return thresholds


@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    family: str
    side: str
    horizon_bars: int
    cooldown_bars: int
    description: str
    threshold_profile: str
    sessions: Tuple[str, ...]


def build_rule_specs(tf_min: int) -> List[RuleSpec]:
    # Medium-frequency horizons: 30m, 1h, 2h, 4h, 8h on M5; scaled for other TFs.
    def bars_for_minutes(minutes: int) -> int:
        return max(1, int(round(minutes / max(tf_min, 1))))
    horizons = [30, 60, 120, 240, 480]
    sessions_all = ("ASIA", "LONDON_OPEN", "LONDON_NY_OVERLAP", "NY_PM")
    liquid = ("LONDON_OPEN", "LONDON_NY_OVERLAP", "NY_PM")
    london_ny = ("LONDON_OPEN", "LONDON_NY_OVERLAP")
    specs: List[RuleSpec] = []
    profiles = ["loose", "base", "strict"]
    for mins in horizons:
        h = bars_for_minutes(mins)
        cd = max(h, bars_for_minutes(30))
        for profile in profiles:
            specs.extend([
                RuleSpec(f"D167_EVT_LONG_MOM_{profile}_{mins}M", "EVENT_LONG_MOMENTUM", "LONG", h, cd, "Long safe-haven/current-event pressure with short-term momentum", profile, liquid),
                RuleSpec(f"D167_EVT_LONG_PULLBACK_{profile}_{mins}M", "EVENT_LONG_PULLBACK", "LONG", h, cd, "Long safe-haven/current-event pressure after technical pullback", profile, sessions_all),
                RuleSpec(f"D167_EVT_SHORT_MOM_{profile}_{mins}M", "EVENT_SHORT_MOMENTUM", "SHORT", h, cd, "Short risk-on/hawkish/de-escalation pressure with downside momentum", profile, liquid),
                RuleSpec(f"D167_EVT_SHORT_PULLBACK_{profile}_{mins}M", "EVENT_SHORT_PULLBACK", "SHORT", h, cd, "Short risk-on/hawkish/de-escalation pressure after upside pullback", profile, sessions_all),
                RuleSpec(f"D167_SHOCK_BREAKOUT_LONG_{profile}_{mins}M", "SHOCK_BREAKOUT_LONG", "LONG", h, cd, "Event shock plus expansion breakout long", profile, london_ny),
                RuleSpec(f"D167_SHOCK_BREAKOUT_SHORT_{profile}_{mins}M", "SHOCK_BREAKOUT_SHORT", "SHORT", h, cd, "Event shock plus expansion breakout short", profile, london_ny),
                RuleSpec(f"D167_EVENT_NEUTRAL_MOM_LONG_{profile}_{mins}M", "EVENT_NEUTRAL_MOM_LONG", "LONG", h, cd, "Neutral-event technical momentum control long", profile, liquid),
                RuleSpec(f"D167_EVENT_NEUTRAL_MOM_SHORT_{profile}_{mins}M", "EVENT_NEUTRAL_MOM_SHORT", "SHORT", h, cd, "Neutral-event technical momentum control short", profile, liquid),
            ])
    return specs


def profile_thresholds(profile: str, th: Dict[str, float]) -> Dict[str, float]:
    if profile == "strict":
        return {
            "shock_min": th["shock_q70"],
            "long_min": th["long_q75"],
            "short_min": th["short_q75"],
            "atr_min": th["atr48_q60"],
            "range_min": th["range96_q80"],
            "mom6_min": max(1.0, abs(th["mom6_abs_q55"])),
            "mom12_min": max(1.5, abs(th["mom12_abs_q55"])),
        }
    if profile == "loose":
        return {
            "shock_min": th["shock_q50"],
            "long_min": th["long_q60"],
            "short_min": th["short_q60"],
            "atr_min": th["atr48_q40"],
            "range_min": th["range96_q60"],
            "mom6_min": 0.5,
            "mom12_min": 0.8,
        }
    return {
        "shock_min": th["shock_q60"],
        "long_min": th["long_q60"],
        "short_min": th["short_q60"],
        "atr_min": th["atr48_q60"],
        "range_min": th["range96_q60"],
        "mom6_min": max(0.8, abs(th["mom6_abs_q55"])),
        "mom12_min": max(1.0, abs(th["mom12_abs_q55"])),
    }


def signal_mask(x: pd.DataFrame, spec: RuleSpec, th: Dict[str, float]) -> pd.Series:
    p = profile_thresholds(spec.threshold_profile, th)
    session_ok = x["session"].isin(spec.sessions)
    atr_ok = x["atr_48_bps"].fillna(0) >= p["atr_min"]
    range_ok = x["range_pct_rank_96"].fillna(0) >= p["range_min"]
    shock_ok = x["shock_abs"].fillna(0) >= p["shock_min"]
    long_event_ok = (x["gold_long_pressure"].fillna(0) >= p["long_min"]) | (x["event_side_bias"].astype(str).str.upper() == "LONG")
    short_event_ok = (x["gold_short_pressure"].fillna(0) >= p["short_min"]) | (x["event_side_bias"].astype(str).str.upper() == "SHORT")
    neutral_event_ok = (x["shock_abs"].fillna(0) <= max(p["shock_min"], th["shock_q60"])) & (x["event_side_bias"].astype(str).str.upper().isin(["NONE", "NEUTRAL", "NAN"]))

    mom_long = (x["ret_6_bps"].fillna(0) >= p["mom6_min"]) & (x["ret_12_bps"].fillna(0) >= 0)
    mom_short = (x["ret_6_bps"].fillna(0) <= -p["mom6_min"]) & (x["ret_12_bps"].fillna(0) <= 0)
    pullback_long = (x["ret_6_bps"].fillna(0) <= -p["mom6_min"]) & (x["lower_wick_bps"].fillna(0) >= 0)
    pullback_short = (x["ret_6_bps"].fillna(0) >= p["mom6_min"]) & (x["upper_wick_bps"].fillna(0) >= 0)
    breakout_long = (x["ret_3_bps"].fillna(0) >= p["mom6_min"] / 2.0) & (x["body_bps"].fillna(0) > 0) & range_ok
    breakout_short = (x["ret_3_bps"].fillna(0) <= -p["mom6_min"] / 2.0) & (x["body_bps"].fillna(0) < 0) & range_ok

    if spec.family == "EVENT_LONG_MOMENTUM":
        return session_ok & atr_ok & long_event_ok & mom_long
    if spec.family == "EVENT_LONG_PULLBACK":
        return session_ok & atr_ok & long_event_ok & pullback_long
    if spec.family == "EVENT_SHORT_MOMENTUM":
        return session_ok & atr_ok & short_event_ok & mom_short
    if spec.family == "EVENT_SHORT_PULLBACK":
        return session_ok & atr_ok & short_event_ok & pullback_short
    if spec.family == "SHOCK_BREAKOUT_LONG":
        return session_ok & atr_ok & shock_ok & long_event_ok & breakout_long
    if spec.family == "SHOCK_BREAKOUT_SHORT":
        return session_ok & atr_ok & shock_ok & short_event_ok & breakout_short
    if spec.family == "EVENT_NEUTRAL_MOM_LONG":
        return session_ok & atr_ok & neutral_event_ok & mom_long
    if spec.family == "EVENT_NEUTRAL_MOM_SHORT":
        return session_ok & atr_ok & neutral_event_ok & mom_short
    return pd.Series(False, index=x.index)


def apply_cooldown(mask: pd.Series, cooldown_bars: int) -> pd.Series:
    raw_idx = list(mask[mask].index)
    keep = []
    last = -10**12
    for idx in raw_idx:
        if idx - last >= cooldown_bars:
            keep.append(idx)
            last = idx
    out = pd.Series(False, index=mask.index)
    if keep:
        out.loc[keep] = True
    return out


def build_trade_rows(x: pd.DataFrame, spec: RuleSpec, mask: pd.Series, split_name: str) -> pd.DataFrame:
    idx = list(mask[mask].index)
    rows: List[Dict[str, Any]] = []
    h = int(spec.horizon_bars)
    for i in idx:
        j = i + h
        if j >= len(x):
            continue
        entry = float(x.at[i, "close"])
        exit_ = float(x.at[j, "close"])
        raw_bps = (exit_ / entry - 1.0) * 10000.0
        side_bps = raw_bps if spec.side == "LONG" else -raw_bps
        cost = float(x.at[i, "effective_cost_bps"]) if pd.notna(x.at[i, "effective_cost_bps"]) else 0.0
        net_bps = side_bps - cost
        rows.append({
            "rule_id": spec.rule_id,
            "family": spec.family,
            "side": spec.side,
            "split": split_name,
            "entry_time_utc": x.at[i, "time_utc"],
            "exit_time_utc": x.at[j, "time_utc"],
            "entry_close": entry,
            "exit_close": exit_,
            "horizon_bars": h,
            "raw_side_bps": round(side_bps, 6),
            "cost_bps": round(cost, 6),
            "net_bps": round(net_bps, 6),
            "session": x.at[i, "session"],
            "shock_abs": float(x.at[i, "shock_abs"]),
            "gold_long_pressure": float(x.at[i, "gold_long_pressure"]),
            "gold_short_pressure": float(x.at[i, "gold_short_pressure"]),
            "event_side_bias": str(x.at[i, "event_side_bias"]),
            "event_shock_regime": str(x.at[i, "event_shock_regime"]),
            "ret_6_bps": float(x.at[i, "ret_6_bps"]) if pd.notna(x.at[i, "ret_6_bps"]) else None,
            "atr_48_bps": float(x.at[i, "atr_48_bps"]) if pd.notna(x.at[i, "atr_48_bps"]) else None,
        })
    return pd.DataFrame(rows)


def summarize_trades(trades: pd.DataFrame, prefix: str) -> Dict[str, Any]:
    if trades.empty:
        return {
            f"{prefix}_events": 0,
            f"{prefix}_mean_net_bps": None,
            f"{prefix}_median_net_bps": None,
            f"{prefix}_hit_rate": None,
            f"{prefix}_p10_net_bps": None,
            f"{prefix}_p90_net_bps": None,
            f"{prefix}_profit_factor": None,
            f"{prefix}_max_drawdown_proxy_bps": None,
        }
    vals = pd.to_numeric(trades["net_bps"], errors="coerce").dropna()
    wins = vals[vals > 0]
    losses = vals[vals <= 0]
    equity = vals.cumsum()
    dd = equity - equity.cummax()
    gross_win = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(-losses.sum()) if len(losses) else 0.0
    pf = gross_win / gross_loss if gross_loss > 0 else (float("inf") if gross_win > 0 else None)
    return {
        f"{prefix}_events": int(len(vals)),
        f"{prefix}_mean_net_bps": round(float(vals.mean()), 6),
        f"{prefix}_median_net_bps": round(float(vals.median()), 6),
        f"{prefix}_hit_rate": round(float((vals > 0).mean()), 6),
        f"{prefix}_p10_net_bps": round(float(vals.quantile(0.10)), 6),
        f"{prefix}_p90_net_bps": round(float(vals.quantile(0.90)), 6),
        f"{prefix}_profit_factor": round(float(pf), 6) if pf is not None and math.isfinite(pf) else pf,
        f"{prefix}_max_drawdown_proxy_bps": round(float(dd.min()), 6) if len(dd) else None,
    }



EMPTY_TRADE_COLUMNS = [
    "rule_id", "family", "side", "split", "entry_time_utc", "exit_time_utc",
    "entry_close", "exit_close", "horizon_bars", "raw_side_bps", "cost_bps", "net_bps",
    "session", "shock_abs", "gold_long_pressure", "gold_short_pressure",
    "event_side_bias", "event_shock_regime", "ret_6_bps", "atr_48_bps",
]


def summarize_net_values(vals: pd.Series, prefix: str) -> Dict[str, Any]:
    vals = pd.to_numeric(vals, errors="coerce").dropna()
    if len(vals) == 0:
        return {
            f"{prefix}_events": 0,
            f"{prefix}_mean_net_bps": None,
            f"{prefix}_median_net_bps": None,
            f"{prefix}_hit_rate": None,
            f"{prefix}_p10_net_bps": None,
            f"{prefix}_p90_net_bps": None,
            f"{prefix}_profit_factor": None,
            f"{prefix}_max_drawdown_proxy_bps": None,
        }
    wins = vals[vals > 0]
    losses = vals[vals <= 0]
    equity = vals.cumsum()
    dd = equity - equity.cummax()
    gross_win = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(-losses.sum()) if len(losses) else 0.0
    pf = gross_win / gross_loss if gross_loss > 0 else (float("inf") if gross_win > 0 else None)
    return {
        f"{prefix}_events": int(len(vals)),
        f"{prefix}_mean_net_bps": round(float(vals.mean()), 6),
        f"{prefix}_median_net_bps": round(float(vals.median()), 6),
        f"{prefix}_hit_rate": round(float((vals > 0).mean()), 6),
        f"{prefix}_p10_net_bps": round(float(vals.quantile(0.10)), 6),
        f"{prefix}_p90_net_bps": round(float(vals.quantile(0.90)), 6),
        f"{prefix}_profit_factor": round(float(pf), 6) if pf is not None and math.isfinite(pf) else pf,
        f"{prefix}_max_drawdown_proxy_bps": round(float(dd.min()), 6) if len(dd) else None,
    }


def event_panel_health_check(event_panel: pd.DataFrame, event_meta: Dict[str, Any], features: pd.DataFrame, train: pd.DataFrame, holdout: pd.DataFrame, thresholds: Dict[str, float], args: argparse.Namespace) -> Dict[str, Any]:
    """Detect the common failure where Stage166 only covers recent/current news.

    In that case train-side event thresholds collapse to zero and Stage167 is not a
    legitimate event-aware historical discovery. Fast-stopping here does not hide
    edge; it prevents wasting time scanning technical-control rules under a false
    event-aware label.
    """
    nonzero_cols = ["shock_abs", "gold_long_pressure", "gold_short_pressure", "gold_direct_score", "event_count", "event_count_weighted"]
    def active_rows(df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        active = pd.Series(False, index=df.index)
        for c in nonzero_cols:
            if c in df.columns:
                active = active | (pd.to_numeric(df[c], errors="coerce").fillna(0).abs() > 0)
        return int(active.sum())
    panel_rows = int(event_meta.get("row_count") or len(event_panel) or 0)
    train_active = active_rows(train)
    holdout_active = active_rows(holdout)
    feature_active = active_rows(features)
    shock_thresholds_zero = all(float(thresholds.get(k, 0.0) or 0.0) == 0.0 for k in ["shock_q50", "shock_q60", "shock_q70", "shock_q80"])
    pressure_thresholds_zero = all(float(thresholds.get(k, 0.0) or 0.0) == 0.0 for k in ["long_q60", "long_q75", "short_q60", "short_q75"])
    positive_threshold_counts = {
        "shock_positive_train_count": int(float(thresholds.get("shock_positive_train_count", 0.0) or 0.0)),
        "long_positive_train_count": int(float(thresholds.get("long_positive_train_count", 0.0) or 0.0)),
        "short_positive_train_count": int(float(thresholds.get("short_positive_train_count", 0.0) or 0.0)),
    }
    sparse_but_thresholded = (
        train_active >= int(args.min_train_active_event_bars)
        and not shock_thresholds_zero
        and sum(positive_threshold_counts.values()) >= int(args.min_train_active_event_bars)
    )
    reasons: List[str] = []
    if panel_rows < int(args.min_event_panel_rows):
        reasons.append("EVENT_PANEL_ROWS_LT_MIN")
    if train_active < int(args.min_train_active_event_bars):
        reasons.append("TRAIN_ACTIVE_EVENT_BARS_LT_MIN")
    if shock_thresholds_zero and pressure_thresholds_zero and not sparse_but_thresholded:
        reasons.append("TRAIN_EVENT_THRESHOLDS_COLLAPSED_TO_ZERO")
    return {
        "panel_rows": panel_rows,
        "feature_active_event_bars": feature_active,
        "train_active_event_bars": train_active,
        "holdout_active_event_bars": holdout_active,
        "min_event_panel_rows": int(args.min_event_panel_rows),
        "min_train_active_event_bars": int(args.min_train_active_event_bars),
        "shock_thresholds_zero": bool(shock_thresholds_zero),
        "pressure_thresholds_zero": bool(pressure_thresholds_zero),
        "positive_threshold_counts": positive_threshold_counts,
        "event_threshold_source": str(thresholds.get("event_threshold_source", "unknown")),
        "sparse_but_thresholded": bool(sparse_but_thresholded),
        "event_overlay_trainable": len(reasons) == 0,
        "fast_stop": len(reasons) > 0,
        "fast_stop_reasons": reasons,
    }


def build_trade_rows_from_indices(x: pd.DataFrame, spec: RuleSpec, idx: Sequence[int], split_name: str) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    h = int(spec.horizon_bars)
    for i in idx:
        j = int(i) + h
        if j >= len(x):
            continue
        entry = float(x.at[int(i), "close"])
        exit_ = float(x.at[j, "close"])
        raw_bps = (exit_ / entry - 1.0) * 10000.0
        side_bps = raw_bps if spec.side == "LONG" else -raw_bps
        cost = float(x.at[int(i), "effective_cost_bps"]) if pd.notna(x.at[int(i), "effective_cost_bps"]) else 0.0
        net_bps = side_bps - cost
        rows.append({
            "rule_id": spec.rule_id,
            "family": spec.family,
            "side": spec.side,
            "split": split_name,
            "entry_time_utc": x.at[int(i), "time_utc"],
            "exit_time_utc": x.at[j, "time_utc"],
            "entry_close": entry,
            "exit_close": exit_,
            "horizon_bars": h,
            "raw_side_bps": round(side_bps, 6),
            "cost_bps": round(cost, 6),
            "net_bps": round(net_bps, 6),
            "session": x.at[int(i), "session"],
            "shock_abs": float(x.at[int(i), "shock_abs"]),
            "gold_long_pressure": float(x.at[int(i), "gold_long_pressure"]),
            "gold_short_pressure": float(x.at[int(i), "gold_short_pressure"]),
            "event_side_bias": str(x.at[int(i), "event_side_bias"]),
            "event_shock_regime": str(x.at[int(i), "event_shock_regime"]),
            "ret_6_bps": float(x.at[int(i), "ret_6_bps"]) if pd.notna(x.at[int(i), "ret_6_bps"]) else None,
            "atr_48_bps": float(x.at[int(i), "atr_48_bps"]) if pd.notna(x.at[int(i), "atr_48_bps"]) else None,
        })
    return pd.DataFrame(rows, columns=EMPTY_TRADE_COLUMNS)


def evaluate_rules_fast(x: pd.DataFrame, train: pd.DataFrame, holdout: pd.DataFrame, thresholds: Dict[str, float], args: argparse.Namespace) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    specs = build_rule_specs(timeframe_minutes(x))
    rows: List[Dict[str, Any]] = []
    trade_frames: List[pd.DataFrame] = []
    trade_index_by_rule: Dict[str, List[int]] = {}

    train_end = train["time_utc"].max() if len(train) else pd.Timestamp.min.tz_localize("UTC")
    holdout_start = holdout["time_utc"].min() if len(holdout) else pd.Timestamp.max.tz_localize("UTC")
    close = pd.to_numeric(x["close"], errors="coerce")
    cost = pd.to_numeric(x["effective_cost_bps"], errors="coerce").fillna(0.0)
    times = pd.to_datetime(x["time_utc"], errors="coerce", utc=True)
    shock = pd.to_numeric(x.get("shock_abs"), errors="coerce").fillna(0.0)
    tf = timeframe_minutes(x)

    for spec in specs:
        raw_mask = signal_mask(x, spec, thresholds)
        mask = apply_cooldown(raw_mask, spec.cooldown_bars)
        idx = pd.Index(mask[mask].index).astype(int)
        h = int(spec.horizon_bars)
        idx = idx[(idx + h) < len(x)]
        trade_index_by_rule[spec.rule_id] = list(idx)
        if len(idx) == 0:
            train_vals = pd.Series(dtype=float)
            holdout_vals = pd.Series(dtype=float)
            event_dep_train = 0.0
            train_events = 1
            holdout_events = 0
        else:
            exit_idx = idx + h
            raw = (close.iloc[exit_idx].to_numpy() / close.iloc[idx].to_numpy() - 1.0) * 10000.0
            side_vals = raw if spec.side == "LONG" else -raw
            net = pd.Series(side_vals - cost.iloc[idx].to_numpy(), index=idx)
            entry_times = times.iloc[idx]
            train_sel = entry_times <= train_end
            holdout_sel = entry_times >= holdout_start
            train_vals = net.loc[idx[train_sel.to_numpy()]] if hasattr(train_sel, 'to_numpy') else net[train_sel]
            holdout_vals = net.loc[idx[holdout_sel.to_numpy()]] if hasattr(holdout_sel, 'to_numpy') else net[holdout_sel]
            train_events = max(1, int(len(train_vals)))
            holdout_events = int(len(holdout_vals))
            train_idx = idx[train_sel.to_numpy()] if hasattr(train_sel, 'to_numpy') else idx[train_sel]
            if len(train_idx):
                event_dep_train = float((shock.iloc[train_idx].to_numpy() > thresholds.get("shock_q80", 0)).mean())
            else:
                event_dep_train = 0.0
        row: Dict[str, Any] = {
            "rule_id": spec.rule_id,
            "family": spec.family,
            "side": spec.side,
            "horizon_bars": spec.horizon_bars,
            "horizon_minutes": spec.horizon_bars * tf,
            "cooldown_bars": spec.cooldown_bars,
            "threshold_profile": spec.threshold_profile,
            "sessions": ";".join(spec.sessions),
            "description": spec.description,
        }
        row.update(summarize_net_values(train_vals, "train"))
        row.update(summarize_net_values(holdout_vals, "holdout"))
        row["event_dependency_ratio"] = round(event_dep_train, 6)
        row["annualized_train_frequency_proxy"] = round(float(train_events) / max(1.0, len(train)) * (365 * 24 * 60 / max(1, tf)), 4)
        row["annualized_holdout_frequency_proxy"] = round(float(holdout_events) / max(1.0, len(holdout)) * (365 * 24 * 60 / max(1, tf)), 4)
        passed, reasons = pass_gate(row, args)
        row["passes_commercial_holdout_gate"] = bool(passed)
        row["kill_reasons"] = ";".join(reasons) if reasons else "PASS"
        rows.append(row)

    scores = pd.DataFrame(rows)
    if not scores.empty:
        scores = scores.sort_values(
            ["passes_commercial_holdout_gate", "holdout_mean_net_bps", "holdout_hit_rate", "holdout_events", "train_mean_net_bps"],
            ascending=[False, False, False, False, False],
        ).reset_index(drop=True)
    shortlist = scores[scores["passes_commercial_holdout_gate"]].copy() if not scores.empty else scores.copy()

    trades = pd.DataFrame(columns=EMPTY_TRADE_COLUMNS)
    if args.export_all_rule_trades:
        for spec in specs:
            idx = trade_index_by_rule.get(spec.rule_id, [])
            if idx:
                tf_all = build_trade_rows_from_indices(x, spec, idx, "all")
                if not tf_all.empty:
                    tf_all["entry_time_utc"] = pd.to_datetime(tf_all["entry_time_utc"], errors="coerce", utc=True)
                    tf_all.loc[tf_all["entry_time_utc"] <= train_end, "split"] = "train"
                    tf_all.loc[tf_all["entry_time_utc"] >= holdout_start, "split"] = "holdout"
                    trade_frames.append(tf_all)
        trades = pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame(columns=EMPTY_TRADE_COLUMNS)

    top_ids = shortlist["rule_id"].head(args.max_top_trade_exports).tolist() if not shortlist.empty else scores["rule_id"].head(args.max_top_trade_exports).tolist() if not scores.empty else []
    top_frames: List[pd.DataFrame] = []
    spec_by_id = {s.rule_id: s for s in specs}
    for rid in top_ids:
        spec = spec_by_id.get(rid)
        idx = trade_index_by_rule.get(rid, [])
        if spec and idx:
            tf_top = build_trade_rows_from_indices(x, spec, idx, "all")
            if not tf_top.empty:
                tf_top["entry_time_utc"] = pd.to_datetime(tf_top["entry_time_utc"], errors="coerce", utc=True)
                tf_top.loc[tf_top["entry_time_utc"] <= train_end, "split"] = "train"
                tf_top.loc[tf_top["entry_time_utc"] >= holdout_start, "split"] = "holdout"
                top_frames.append(tf_top)
    top_trades = pd.concat(top_frames, ignore_index=True) if top_frames else pd.DataFrame(columns=EMPTY_TRADE_COLUMNS)

    context = {
        "rule_spec_count": len(specs),
        "score_count": int(len(scores)),
        "shortlist_count": int(len(shortlist)),
        "candidate_family_counts": scores["family"].value_counts().to_dict() if not scores.empty else {},
        "pass_family_counts": shortlist["family"].value_counts().to_dict() if not shortlist.empty else {},
        "evaluation_mode": "FAST_VECTOR_SUMMARY_WITH_OPTIONAL_FULL_TRADE_EXPORT",
        "all_rule_trades_exported": bool(args.export_all_rule_trades),
    }
    return scores, shortlist, trades, top_trades, context

def pass_gate(row: Dict[str, Any], args: argparse.Namespace) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    if int(row.get("train_events") or 0) < args.min_train_events:
        reasons.append("TRAIN_EVENTS_LT_MIN")
    if int(row.get("holdout_events") or 0) < args.min_holdout_events:
        reasons.append("HOLDOUT_EVENTS_LT_MIN")
    if (row.get("train_mean_net_bps") is None) or float(row.get("train_mean_net_bps") or -9999) < args.min_train_mean_bps:
        reasons.append("TRAIN_MEAN_LT_MIN")
    if (row.get("holdout_mean_net_bps") is None) or float(row.get("holdout_mean_net_bps") or -9999) < args.min_holdout_mean_bps:
        reasons.append("HOLDOUT_MEAN_LT_MIN")
    if (row.get("train_hit_rate") is None) or float(row.get("train_hit_rate") or 0) < args.min_train_hit_rate:
        reasons.append("TRAIN_HIT_LT_MIN")
    if (row.get("holdout_hit_rate") is None) or float(row.get("holdout_hit_rate") or 0) < args.min_holdout_hit_rate:
        reasons.append("HOLDOUT_HIT_LT_MIN")
    if (row.get("holdout_p10_net_bps") is None) or float(row.get("holdout_p10_net_bps") or -9999) < args.min_holdout_p10_bps:
        reasons.append("HOLDOUT_LEFT_TAIL_TOO_WEAK")
    if float(row.get("event_dependency_ratio") or 0.0) > args.max_event_dependency_ratio:
        reasons.append("TOO_EVENT_SPIKE_DEPENDENT")
    return (len(reasons) == 0), reasons


def split_train_holdout(x: pd.DataFrame, holdout_pct: float) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    y = x.sort_values("time_utc").reset_index(drop=True).copy()
    n = len(y)
    holdout_n = max(1, int(round(n * holdout_pct))) if n else 0
    split_idx = max(0, n - holdout_n)
    y["split"] = "train"
    y.loc[y.index >= split_idx, "split"] = "holdout"
    train = y[y["split"] == "train"].copy()
    holdout = y[y["split"] == "holdout"].copy()
    meta = {
        "row_count": int(n),
        "holdout_pct": holdout_pct,
        "split_index": int(split_idx),
        "train_rows": int(len(train)),
        "holdout_rows": int(len(holdout)),
        "train_start_utc": str(train["time_utc"].min()) if len(train) else None,
        "train_end_utc": str(train["time_utc"].max()) if len(train) else None,
        "holdout_start_utc": str(holdout["time_utc"].min()) if len(holdout) else None,
        "holdout_end_utc": str(holdout["time_utc"].max()) if len(holdout) else None,
    }
    return train, holdout, meta


def evaluate_rules(x: pd.DataFrame, train: pd.DataFrame, holdout: pd.DataFrame, thresholds: Dict[str, float], args: argparse.Namespace) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    specs = build_rule_specs(timeframe_minutes(x))
    rows: List[Dict[str, Any]] = []
    trade_frames: List[pd.DataFrame] = []
    top_trade_frames: List[pd.DataFrame] = []

    # Evaluate on the full indexed dataframe, then assign split by entry timestamp.
    train_end = train["time_utc"].max() if len(train) else pd.Timestamp.min.tz_localize("UTC")
    holdout_start = holdout["time_utc"].min() if len(holdout) else pd.Timestamp.max.tz_localize("UTC")

    for spec in specs:
        raw_mask = signal_mask(x, spec, thresholds)
        mask = apply_cooldown(raw_mask, spec.cooldown_bars)
        trades_all = build_trade_rows(x, spec, mask, "all")
        if trades_all.empty:
            train_trades = pd.DataFrame()
            holdout_trades = pd.DataFrame()
        else:
            trades_all["entry_time_utc"] = pd.to_datetime(trades_all["entry_time_utc"], errors="coerce", utc=True)
            train_trades = trades_all[trades_all["entry_time_utc"] <= train_end].copy()
            holdout_trades = trades_all[trades_all["entry_time_utc"] >= holdout_start].copy()
            train_trades["split"] = "train"
            holdout_trades["split"] = "holdout"
        row: Dict[str, Any] = {
            "rule_id": spec.rule_id,
            "family": spec.family,
            "side": spec.side,
            "horizon_bars": spec.horizon_bars,
            "horizon_minutes": spec.horizon_bars * timeframe_minutes(x),
            "cooldown_bars": spec.cooldown_bars,
            "threshold_profile": spec.threshold_profile,
            "sessions": ";".join(spec.sessions),
            "description": spec.description,
        }
        row.update(summarize_trades(train_trades, "train"))
        row.update(summarize_trades(holdout_trades, "holdout"))
        train_events = max(1, int(row.get("train_events") or 0))
        holdout_events = int(row.get("holdout_events") or 0)
        # Penalize candidates that only trade during rare extreme shock windows.
        event_dep_train = 0.0
        if not train_trades.empty:
            event_dep_train = float((pd.to_numeric(train_trades["shock_abs"], errors="coerce").fillna(0) > thresholds.get("shock_q80", 0)).mean())
        row["event_dependency_ratio"] = round(event_dep_train, 6)
        row["annualized_train_frequency_proxy"] = round(float(train_events) / max(1.0, len(train)) * (365 * 24 * 60 / max(1, timeframe_minutes(x))), 4)
        row["annualized_holdout_frequency_proxy"] = round(float(holdout_events) / max(1.0, len(holdout)) * (365 * 24 * 60 / max(1, timeframe_minutes(x))), 4)
        passed, reasons = pass_gate(row, args)
        row["passes_commercial_holdout_gate"] = bool(passed)
        row["kill_reasons"] = ";".join(reasons) if reasons else "PASS"
        rows.append(row)
        if not train_trades.empty or not holdout_trades.empty:
            trade_frames.append(pd.concat([train_trades, holdout_trades], ignore_index=True))

    scores = pd.DataFrame(rows)
    if not scores.empty:
        scores = scores.sort_values(
            ["passes_commercial_holdout_gate", "holdout_mean_net_bps", "holdout_hit_rate", "holdout_events", "train_mean_net_bps"],
            ascending=[False, False, False, False, False],
        ).reset_index(drop=True)
    shortlist = scores[scores["passes_commercial_holdout_gate"]].copy() if not scores.empty else scores.copy()

    trades = pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame()
    if not shortlist.empty and not trades.empty:
        top_ids = shortlist["rule_id"].head(args.max_top_trade_exports).tolist()
        top_trades = trades[trades["rule_id"].isin(top_ids)].copy()
    else:
        top_trades = pd.DataFrame()

    context = {
        "rule_spec_count": len(specs),
        "score_count": int(len(scores)),
        "shortlist_count": int(len(shortlist)),
        "candidate_family_counts": scores["family"].value_counts().to_dict() if not scores.empty else {},
        "pass_family_counts": shortlist["family"].value_counts().to_dict() if not shortlist.empty else {},
    }
    return scores, shortlist, trades, top_trades, context


def run(args: argparse.Namespace) -> Dict[str, Any]:
    root = Path(args.root).expanduser().resolve()
    report_dir = root / "reports" / "stage167_event_aware_medium_frequency_discovery_and_holdout_gate"
    ensure_dir(report_dir)

    outputs = {
        "summary_json": str(report_dir / "stage167_event_aware_holdout_gate_summary.json"),
        "all_rule_scores_csv": str(report_dir / "stage167_all_rule_scores.csv"),
        "commercial_shortlist_csv": str(report_dir / "stage167_commercial_shortlist.csv"),
        "all_rule_trades_csv": str(report_dir / "stage167_all_rule_trades.csv"),
        "top_rule_trades_csv": str(report_dir / "stage167_top_rule_trades.csv"),
        "thresholds_json": str(report_dir / "stage167_train_thresholds.json"),
        "holdout_map_json": str(report_dir / "stage167_holdout_map.json"),
        "decision_md": str(report_dir / "stage167_decision.md"),
    }

    try:
        bars, bars_meta = load_bars(Path(args.bars_m5).expanduser(), args.timestamp_shift_hours)
        event_path = Path(args.event_panel).expanduser() if args.event_panel else root / "reports" / "stage166_current_event_shock_overlay" / "stage166_current_event_intraday_panel.csv"
        event_panel, event_meta = load_event_panel(event_path, bars)
        features, feature_meta = enrich_features(bars, event_panel, args.spread_point_size, args.cost_bps)
        # Avoid warmup NaNs polluting early train metrics.
        features = features.dropna(subset=["ret_6_bps", "ret_12_bps", "atr_48_bps"]).reset_index(drop=True)
        train, holdout, split_meta = split_train_holdout(features, args.holdout_pct)
        thresholds = compute_train_thresholds(train)
        write_json(Path(outputs["thresholds_json"]), thresholds)
        write_json(Path(outputs["holdout_map_json"]), split_meta)
        event_health = event_panel_health_check(event_panel, event_meta, features, train, holdout, thresholds, args)
        if event_health.get("fast_stop") and not args.force_scan_with_insufficient_event_panel:
            scores = pd.DataFrame(columns=["rule_id", "family", "side", "passes_commercial_holdout_gate", "kill_reasons"])
            shortlist = scores.copy()
            trades = pd.DataFrame(columns=EMPTY_TRADE_COLUMNS)
            top_trades = pd.DataFrame(columns=EMPTY_TRADE_COLUMNS)
            eval_context = {
                "rule_spec_count": len(build_rule_specs(timeframe_minutes(features))),
                "score_count": 0,
                "shortlist_count": 0,
                "candidate_family_counts": {},
                "pass_family_counts": {},
                "evaluation_mode": "FAST_STOP_EVENT_PANEL_NOT_TRAINABLE",
                "all_rule_trades_exported": False,
            }
        else:
            scores, shortlist, trades, top_trades, eval_context = evaluate_rules_fast(features, train, holdout, thresholds, args)
        scores.to_csv(outputs["all_rule_scores_csv"], index=False)
        shortlist.to_csv(outputs["commercial_shortlist_csv"], index=False)
        trades.to_csv(outputs["all_rule_trades_csv"], index=False)
        top_trades.to_csv(outputs["top_rule_trades_csv"], index=False)

        if event_health.get("fast_stop") and not args.force_scan_with_insufficient_event_panel:
            decision = "STAGE167C_EVENT_PANEL_NOT_TRAINABLE_FAST_STOP_REBUILD_STAGE166_HISTORY_FIRST"
            severity = "HIGH"
            recommended_action = "DO_NOT_SCAN_TECHNICAL_CONTROLS_AS_EVENT_AWARE; BACKFILL_OR_REBUILD_CURRENT_EVENT_HISTORY_PANEL"
        elif len(shortlist) > 0:
            decision = "STAGE167_EVENT_AWARE_HOLDOUT_CANDIDATES_FOUND_REQUIRES_EXECUTION_SIM_NO_DEMO_RELEASE"
            severity = "WARN"
            recommended_action = "RUN_STAGE168_COSTED_EXECUTION_REPLAY_FOR_SHORTLIST_BEFORE_DEMO"
        else:
            decision = "STAGE167_NO_COMMERCIAL_HOLDOUT_CANDIDATE_KILL_LOW_FREQUENCY_WAITING_PATH"
            severity = "HIGH"
            recommended_action = "DO_NOT_WAIT_FOR_MORE_SAMPLES; REBUILD_RULE_SPACE_OR_ADD_STRONGER_EVENT_FEATURES"

        summary = {
            "stage": STAGE,
            "generated_utc": now_utc_iso(),
            "root": str(root),
            "order_routing_allowed": False,
            "demo_release_allowed": False,
            "status": "STAGE167_COMPLETE_EVENT_AWARE_HOLDOUT_GATE_READY",
            "decision": decision,
            "severity": severity,
            "recommended_action": recommended_action,
            "bars_m5": str(Path(args.bars_m5).expanduser()),
            "event_panel": str(event_path),
            "bars_meta": bars_meta,
            "event_meta": event_meta,
            "feature_meta": feature_meta,
            "split_meta": split_meta,
            "thresholds": thresholds,
            "event_panel_health": event_health,
            "runtime_export_policy": {
                "fast_stop_enabled": not args.force_scan_with_insufficient_event_panel,
                "export_all_rule_trades": bool(args.export_all_rule_trades),
                "note": "Default skips full all-rule trade ledger and exports only scores/top trades; metrics are unchanged. Use --export-all-rule-trades for full audit export.",
            },
            "cost_policy": {
                "fixed_cost_bps": args.cost_bps,
                "spread_point_size": args.spread_point_size,
                "note": "effective_cost_bps = estimated spread bps if valid else fixed_cost_bps, then plus fixed_cost_bps",
            },
            "gate_thresholds": {
                "min_train_events": args.min_train_events,
                "min_holdout_events": args.min_holdout_events,
                "min_train_mean_bps": args.min_train_mean_bps,
                "min_holdout_mean_bps": args.min_holdout_mean_bps,
                "min_train_hit_rate": args.min_train_hit_rate,
                "min_holdout_hit_rate": args.min_holdout_hit_rate,
                "min_holdout_p10_bps": args.min_holdout_p10_bps,
                "max_event_dependency_ratio": args.max_event_dependency_ratio,
            },
            "evaluation_context": eval_context,
            "top_shortlist_rule_ids": shortlist["rule_id"].head(20).tolist() if not shortlist.empty else [],
            "top_score_rule_ids": scores["rule_id"].head(20).tolist() if not scores.empty else [],
            "outputs": outputs,
            "next": [
                "If event_panel_health.fast_stop is true, rebuild Stage166 with broader historical/current-event coverage before rescanning.",
                "Stage167C uses positive-train event thresholds so sparse but valid GDELT panels can be scanned without becoming technical controls.",
                "If shortlist_count is zero, do not wait for more low-frequency samples.",
                "If shortlist_count is positive, review stage167_commercial_shortlist.csv and run Stage168 execution replay before any demo order release.",
                "Send summary JSON, decision MD, and shortlist CSV back for decision review.",
            ],
        }
        write_json(Path(outputs["summary_json"]), summary)
        write_decision_md(Path(outputs["decision_md"]), summary, scores, shortlist)
        return summary
    except Exception as e:
        summary = {
            "stage": STAGE,
            "generated_utc": now_utc_iso(),
            "root": str(root),
            "order_routing_allowed": False,
            "demo_release_allowed": False,
            "status": "STAGE167_FAILURE_ARTIFACTS_WRITTEN",
            "decision": "STAGE167_RUN_FAILED_KEEP_FREEZE",
            "severity": "HIGH",
            "recommended_action": "KEEP_FREEZE_AND_INSPECT_ERROR",
            "error_type": type(e).__name__,
            "error_message": str(e),
            "outputs": outputs,
        }
        write_json(Path(outputs["summary_json"]), summary)
        pd.DataFrame(columns=["rule_id", "family", "side", "passes_commercial_holdout_gate", "kill_reasons"]).to_csv(outputs["all_rule_scores_csv"], index=False)
        pd.DataFrame(columns=["rule_id", "family", "side", "passes_commercial_holdout_gate", "kill_reasons"]).to_csv(outputs["commercial_shortlist_csv"], index=False)
        pd.DataFrame().to_csv(outputs["all_rule_trades_csv"], index=False)
        pd.DataFrame().to_csv(outputs["top_rule_trades_csv"], index=False)
        write_json(Path(outputs["thresholds_json"]), {})
        write_json(Path(outputs["holdout_map_json"]), {})
        Path(outputs["decision_md"]).write_text(f"# Stage167 failed\n\n{type(e).__name__}: {e}\n", encoding="utf-8")
        return summary


def write_decision_md(path: Path, summary: Dict[str, Any], scores: pd.DataFrame, shortlist: pd.DataFrame) -> None:
    lines: List[str] = []
    lines.append("# Stage167 Event-Aware Medium-Frequency Discovery and Holdout Gate")
    lines.append("")
    lines.append(f"Generated UTC: `{summary.get('generated_utc')}`")
    lines.append("")
    lines.append(f"Decision: `{summary.get('decision')}`")
    lines.append(f"Recommended action: `{summary.get('recommended_action')}`")
    lines.append("")
    lines.append("## Core rule")
    lines.append("")
    lines.append("Do not solve low frequency by waiting for more samples. Candidates that fail frequency, holdout, or cost gates are killed.")
    lines.append("")
    lines.append("## Split")
    lines.append("")
    sm = summary.get("split_meta", {})
    lines.append(f"Train: `{sm.get('train_start_utc')}` to `{sm.get('train_end_utc')}` rows={sm.get('train_rows')}")
    lines.append(f"Holdout: `{sm.get('holdout_start_utc')}` to `{sm.get('holdout_end_utc')}` rows={sm.get('holdout_rows')}")
    lines.append("")
    lines.append("## Counts")
    lines.append("")
    ec = summary.get("evaluation_context", {})
    lines.append(f"Rules scanned: `{ec.get('score_count')}`")
    lines.append(f"Commercial shortlist: `{ec.get('shortlist_count')}`")
    lines.append("")
    if not shortlist.empty:
        lines.append("## Top passed candidates")
        lines.append("")
        cols = ["rule_id", "family", "side", "horizon_minutes", "train_events", "train_mean_net_bps", "train_hit_rate", "holdout_events", "holdout_mean_net_bps", "holdout_hit_rate", "kill_reasons"]
        existing = [c for c in cols if c in shortlist.columns]
        lines.append(shortlist[existing].head(20).to_markdown(index=False))
    elif not scores.empty:
        lines.append("## Top failed candidates for diagnosis")
        lines.append("")
        cols = ["rule_id", "family", "side", "horizon_minutes", "train_events", "train_mean_net_bps", "train_hit_rate", "holdout_events", "holdout_mean_net_bps", "holdout_hit_rate", "kill_reasons"]
        existing = [c for c in cols if c in scores.columns]
        lines.append(scores[existing].head(20).to_markdown(index=False))
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Stage167 event-aware medium-frequency discovery and holdout gate")
    p.add_argument("--root", required=True)
    p.add_argument("--bars-m5", required=True)
    p.add_argument("--event-panel", default="")
    p.add_argument("--timestamp-shift-hours", type=float, default=-3.0)
    p.add_argument("--holdout-pct", type=float, default=0.20)
    p.add_argument("--cost-bps", type=float, default=4.0)
    p.add_argument("--spread-point-size", type=float, default=0.01)
    p.add_argument("--min-train-events", type=int, default=150)
    p.add_argument("--min-holdout-events", type=int, default=30)
    p.add_argument("--min-train-mean-bps", type=float, default=1.5)
    p.add_argument("--min-holdout-mean-bps", type=float, default=0.5)
    p.add_argument("--min-train-hit-rate", type=float, default=0.515)
    p.add_argument("--min-holdout-hit-rate", type=float, default=0.505)
    p.add_argument("--min-holdout-p10-bps", type=float, default=-35.0)
    p.add_argument("--max-event-dependency-ratio", type=float, default=0.55)
    p.add_argument("--min-event-panel-rows", type=int, default=30)
    p.add_argument("--min-train-active-event-bars", type=int, default=500)
    p.add_argument("--force-scan-with-insufficient-event-panel", action="store_true")
    p.add_argument("--export-all-rule-trades", action="store_true")
    p.add_argument("--max-top-trade-exports", type=int, default=20)
    return p


if __name__ == "__main__":
    summary = run(build_arg_parser().parse_args())
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
