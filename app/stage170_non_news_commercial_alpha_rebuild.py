#!/usr/bin/env python3
"""
Stage170_NON_NEWS_COMMERCIAL_ALPHA_REBUILD

Purpose:
  After Stage168/169 killed GDELT/news as an independent alpha, rebuild the
  commercial discovery path on non-news intraday XAUUSD behavior while using the
  event/news panel only as a guard/context filter.

Safety:
  Read-only research script. Does not write MT5 signal/KV files. Does not allow
  demo/live routing.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

STAGE = "Stage170_NON_NEWS_COMMERCIAL_ALPHA_REBUILD"
ORDER_ROUTING_ALLOWED = False
DEMO_RELEASE_ALLOWED = False
REPORT_DIRNAME = "stage170_non_news_commercial_alpha_rebuild"


def detect_separator(path: Path) -> str:
    sample = path.read_text(errors="replace")[:4096]
    header = sample.splitlines()[0] if sample.splitlines() else ""
    counts = {"\t": header.count("\t"), ",": header.count(","), ";": header.count(";"), "|": header.count("|")}
    sep = max(counts, key=counts.get)
    return sep if counts[sep] > 0 else ","


def clean_col(c: str) -> str:
    return str(c).strip().strip("<>").strip().lower().replace(" ", "_")


def load_bars_m5(path: Path, timestamp_shift_hours: float = -3.0) -> Tuple[pd.DataFrame, dict]:
    if not path.exists():
        raise FileNotFoundError(path)
    sep = detect_separator(path)
    df = pd.read_csv(path, sep=sep, engine="python")
    raw_columns = list(df.columns)
    df.columns = [clean_col(c) for c in df.columns]

    if "date" in df.columns and "time" in df.columns:
        ts = pd.to_datetime(df["date"].astype(str).str.strip() + " " + df["time"].astype(str).str.strip(), errors="coerce")
        parse_mode = "mt5_split_date_time"
    elif "time_utc" in df.columns:
        ts = pd.to_datetime(df["time_utc"], errors="coerce")
        parse_mode = "time_utc"
    elif "utc_time" in df.columns:
        ts = pd.to_datetime(df["utc_time"], errors="coerce")
        parse_mode = "utc_time"
    elif "time" in df.columns:
        ts = pd.to_datetime(df["time"], errors="coerce")
        parse_mode = "time"
    else:
        raise ValueError(f"Cannot identify time columns in bars: {raw_columns}")

    if getattr(ts.dt, "tz", None) is None:
        ts = ts.dt.tz_localize("UTC")
    else:
        ts = ts.dt.tz_convert("UTC")
    if parse_mode == "mt5_split_date_time" and timestamp_shift_hours:
        ts = ts + pd.to_timedelta(timestamp_shift_hours, unit="h")

    colmap = {}
    for c in ["open", "high", "low", "close", "tickvol", "vol", "spread"]:
        if c in df.columns:
            colmap[c] = c
    required = ["open", "high", "low", "close"]
    missing = [c for c in required if c not in colmap]
    if missing:
        raise ValueError(f"Missing OHLC columns after normalize: {missing}; raw columns={raw_columns}")

    out = pd.DataFrame({
        "time_utc": ts,
        "open": pd.to_numeric(df[colmap["open"]], errors="coerce"),
        "high": pd.to_numeric(df[colmap["high"]], errors="coerce"),
        "low": pd.to_numeric(df[colmap["low"]], errors="coerce"),
        "close": pd.to_numeric(df[colmap["close"]], errors="coerce"),
    })
    if "spread" in colmap:
        out["spread"] = pd.to_numeric(df[colmap["spread"]], errors="coerce")
    else:
        out["spread"] = np.nan
    if "tickvol" in colmap:
        out["tickvol"] = pd.to_numeric(df[colmap["tickvol"]], errors="coerce")
    else:
        out["tickvol"] = np.nan

    out = out.dropna(subset=["time_utc", "open", "high", "low", "close"]).sort_values("time_utc").drop_duplicates("time_utc").reset_index(drop=True)
    meta = {
        "source_path": str(path),
        "detected_separator": "tab" if sep == "\t" else sep,
        "raw_columns": raw_columns,
        "parse_mode": parse_mode,
        "timestamp_shift_hours": timestamp_shift_hours,
        "raw_row_count": int(len(df)),
        "bar_count": int(len(out)),
        "min_time_utc": str(out["time_utc"].min()) if len(out) else None,
        "max_time_utc": str(out["time_utc"].max()) if len(out) else None,
        "spread_nonnull_pct": float(out["spread"].notna().mean() * 100.0) if len(out) else 0.0,
    }
    return out, meta


def load_event_panel(path: Optional[Path]) -> Tuple[Optional[pd.DataFrame], dict]:
    if path is None or not path.exists():
        return None, {"loaded": False, "reason": "missing" if path else "not_provided"}
    sep = detect_separator(path)
    df = pd.read_csv(path, sep=sep, engine="python")
    raw_columns = list(df.columns)
    df.columns = [clean_col(c) for c in df.columns]
    tcol = "time_bucket_utc" if "time_bucket_utc" in df.columns else "time_utc" if "time_utc" in df.columns else None
    if tcol is None:
        return None, {"loaded": False, "reason": "no_time_column", "raw_columns": raw_columns}
    df["time_utc"] = pd.to_datetime(df[tcol], errors="coerce", utc=True)
    keep = ["time_utc"]
    for c in ["shock_abs", "gold_long_pressure", "gold_short_pressure", "net_gold_event_pressure", "event_count"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
            keep.append(c)
    out = df[keep].dropna(subset=["time_utc"]).sort_values("time_utc").drop_duplicates("time_utc").reset_index(drop=True)
    meta = {
        "loaded": True,
        "path": str(path),
        "raw_columns": raw_columns,
        "row_count": int(len(out)),
        "min_time_utc": str(out["time_utc"].min()) if len(out) else None,
        "max_time_utc": str(out["time_utc"].max()) if len(out) else None,
        "nonzero_shock_rows": int((out.get("shock_abs", pd.Series(dtype=float)) > 0).sum()) if len(out) else 0,
    }
    return out, meta


def add_features(bars: pd.DataFrame, event_panel: Optional[pd.DataFrame], spread_point_size: float) -> pd.DataFrame:
    df = bars.copy()
    df["hour"] = df["time_utc"].dt.hour
    df["date"] = df["time_utc"].dt.date.astype(str)
    df["dow"] = df["time_utc"].dt.dayofweek
    df["ret1_bps"] = df["close"].pct_change() * 10000.0
    true_range = np.maximum.reduce([
        (df["high"] - df["low"]).to_numpy(),
        (df["high"] - df["close"].shift(1)).abs().to_numpy(),
        (df["low"] - df["close"].shift(1)).abs().to_numpy(),
    ])
    df["tr_bps"] = true_range / df["close"].replace(0, np.nan).to_numpy() * 10000.0
    df["atr48_bps"] = pd.Series(df["tr_bps"]).rolling(48, min_periods=24).mean()
    df["range96_bps"] = (df["high"].rolling(96, min_periods=48).max() - df["low"].rolling(96, min_periods=48).min()) / df["close"] * 10000.0
    df["range288_bps"] = (df["high"].rolling(288, min_periods=144).max() - df["low"].rolling(288, min_periods=144).min()) / df["close"] * 10000.0
    for n in [3, 6, 12, 24, 48, 96]:
        df[f"mom{n}_bps"] = (df["close"] / df["close"].shift(n) - 1.0) * 10000.0
    for n in [48, 96, 192, 288]:
        df[f"roll_high_{n}"] = df["high"].rolling(n, min_periods=max(12, n//3)).max().shift(1)
        df[f"roll_low_{n}"] = df["low"].rolling(n, min_periods=max(12, n//3)).min().shift(1)
    body = (df["close"] - df["open"]).abs().replace(0, np.nan)
    df["upper_wick_ratio"] = (df["high"] - df[["open", "close"]].max(axis=1)) / body
    df["lower_wick_ratio"] = (df[["open", "close"]].min(axis=1) - df["low"]) / body
    df["spread_bps_est"] = (df["spread"] * spread_point_size / df["close"] * 10000.0).where(df["spread"].notna(), np.nan)

    if event_panel is not None and len(event_panel):
        ev = event_panel.copy()
        ev["hour_bucket"] = ev["time_utc"].dt.floor("1h")
        df["hour_bucket"] = df["time_utc"].dt.floor("1h")
        df = df.merge(ev.drop(columns=["time_utc"], errors="ignore"), on="hour_bucket", how="left")
    else:
        df["hour_bucket"] = df["time_utc"].dt.floor("1h")
    for c in ["shock_abs", "gold_long_pressure", "gold_short_pressure", "net_gold_event_pressure", "event_count"]:
        if c not in df.columns:
            df[c] = 0.0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    # Asia range for London/NY breakout tests.
    is_asia = df["hour"].between(0, 6)
    asia = df.loc[is_asia].groupby("date").agg(asia_high=("high", "max"), asia_low=("low", "min"), asia_rows=("close", "size")).reset_index()
    df = df.merge(asia, on="date", how="left")
    df["above_asia_high"] = df["close"] > df["asia_high"]
    df["below_asia_low"] = df["close"] < df["asia_low"]
    return df


@dataclass
class RuleSpec:
    rule_id: str
    family: str
    side: str
    horizon_bars: int
    horizon_minutes: int
    session: str
    guard_policy: str
    params: dict


def session_mask(df: pd.DataFrame, session: str) -> np.ndarray:
    h = df["hour"].to_numpy()
    if session == "ALL":
        return np.ones(len(df), dtype=bool)
    if session == "ASIA":
        return (h >= 0) & (h <= 6)
    if session == "LONDON":
        return (h >= 7) & (h <= 12)
    if session == "NY":
        return (h >= 13) & (h <= 20)
    if session == "LONDON_NY":
        return (h >= 7) & (h <= 20)
    return np.ones(len(df), dtype=bool)


def build_thresholds(train: pd.DataFrame) -> dict:
    def q(col: str, quant: float, positive: bool = False, default: float = 0.0) -> float:
        s = pd.to_numeric(train[col], errors="coerce").dropna()
        if positive:
            s = s[s > 0]
        if len(s) == 0:
            return default
        return float(s.quantile(quant))
    return {
        "atr_q40": q("atr48_bps", 0.40),
        "atr_q60": q("atr48_bps", 0.60),
        "atr_q80": q("atr48_bps", 0.80),
        "range96_q35": q("range96_bps", 0.35),
        "range96_q50": q("range96_bps", 0.50),
        "range288_q35": q("range288_bps", 0.35),
        "mom12_abs_q55": float(train["mom12_bps"].abs().dropna().quantile(0.55)),
        "mom24_abs_q55": float(train["mom24_bps"].abs().dropna().quantile(0.55)),
        "event_shock_q90_positive": q("shock_abs", 0.90, positive=True, default=math.inf),
        "event_long_q80_positive": q("gold_long_pressure", 0.80, positive=True, default=math.inf),
        "event_short_q80_positive": q("gold_short_pressure", 0.80, positive=True, default=math.inf),
    }


def make_rule_specs(th: dict) -> List[RuleSpec]:
    specs: List[RuleSpec] = []
    sessions = ["ALL", "LONDON", "NY", "LONDON_NY"]
    guard_policies = ["NONE", "EXCLUDE_HIGH_EVENT", "EXCLUDE_OPPOSING_EVENT"]
    horizons = [6, 12, 24, 48, 96]  # 30m, 60m, 120m, 240m, 480m
    profile_id = 0

    for hb in horizons:
        hm = hb * 5
        for sess in sessions:
            for gp in guard_policies:
                for side in ["LONG", "SHORT"]:
                    for mom_col, mom_thr in [("mom12_bps", th["mom12_abs_q55"]), ("mom24_bps", th["mom24_abs_q55"]), ("mom48_bps", th["mom24_abs_q55"] * 1.25)]:
                        profile_id += 1
                        specs.append(RuleSpec(f"D170_TREND_MOM_{side}_{mom_col}_{sess}_{gp}_{hm}M", "TREND_MOMENTUM", side, hb, hm, sess, gp, {"mom_col": mom_col, "mom_thr": mom_thr, "atr_min": th["atr_q40"]}))
                    for mom_col in ["mom12_bps", "mom24_bps"]:
                        profile_id += 1
                        specs.append(RuleSpec(f"D170_MOM_FADE_{side}_{mom_col}_{sess}_{gp}_{hm}M", "MOMENTUM_FADE", side, hb, hm, sess, gp, {"mom_col": mom_col, "mom_thr": th["mom12_abs_q55"], "atr_max": th["atr_q80"]}))
                    for n, range_thr in [(96, th["range96_q35"]), (192, th["range96_q50"]), (288, th["range288_q35"] or th["range96_q35"] * 1.5)]:
                        profile_id += 1
                        specs.append(RuleSpec(f"D170_RANGE_BREAK_{side}_{n}_{sess}_{gp}_{hm}M", "RANGE_BREAKOUT", side, hb, hm, sess, gp, {"window": n, "range_thr": range_thr, "atr_min": th["atr_q40"]}))
                    profile_id += 1
                    specs.append(RuleSpec(f"D170_WICK_REV_{side}_{sess}_{gp}_{hm}M", "WICK_REVERSAL", side, hb, hm, sess, gp, {"wick_min": 1.5, "atr_max": th["atr_q80"]}))
                    profile_id += 1
                    specs.append(RuleSpec(f"D170_ASIA_BREAK_{side}_{sess}_{gp}_{hm}M", "ASIA_RANGE_BREAKOUT", side, hb, hm, sess, gp, {"atr_min": th["atr_q40"]}))
    return specs


def rule_signal(df: pd.DataFrame, spec: RuleSpec, th: dict) -> np.ndarray:
    mask = session_mask(df, spec.session)
    p = spec.params
    side_long = spec.side == "LONG"

    if spec.family == "TREND_MOMENTUM":
        mom = pd.to_numeric(df[p["mom_col"]], errors="coerce").to_numpy()
        sig = mom > p["mom_thr"] if side_long else mom < -p["mom_thr"]
        sig &= df["atr48_bps"].to_numpy() >= p["atr_min"]
    elif spec.family == "MOMENTUM_FADE":
        mom = pd.to_numeric(df[p["mom_col"]], errors="coerce").to_numpy()
        sig = mom < -p["mom_thr"] if side_long else mom > p["mom_thr"]
        sig &= df["atr48_bps"].to_numpy() <= p["atr_max"]
    elif spec.family == "RANGE_BREAKOUT":
        n = p["window"]
        if side_long:
            sig = df["close"].to_numpy() > df[f"roll_high_{n}"].to_numpy()
        else:
            sig = df["close"].to_numpy() < df[f"roll_low_{n}"].to_numpy()
        sig &= df["range96_bps"].to_numpy() <= p["range_thr"]
        sig &= df["atr48_bps"].to_numpy() >= p["atr_min"]
    elif spec.family == "WICK_REVERSAL":
        if side_long:
            sig = (df["lower_wick_ratio"].to_numpy() >= p["wick_min"]) & (df["mom12_bps"].to_numpy() < 0)
        else:
            sig = (df["upper_wick_ratio"].to_numpy() >= p["wick_min"]) & (df["mom12_bps"].to_numpy() > 0)
        sig &= df["atr48_bps"].to_numpy() <= p["atr_max"]
    elif spec.family == "ASIA_RANGE_BREAKOUT":
        valid_time = df["hour"].between(7, 20).to_numpy()
        if side_long:
            sig = df["above_asia_high"].fillna(False).to_numpy()
        else:
            sig = df["below_asia_low"].fillna(False).to_numpy()
        sig &= valid_time
        sig &= df["atr48_bps"].to_numpy() >= p["atr_min"]
    else:
        sig = np.zeros(len(df), dtype=bool)

    sig = sig & mask
    if spec.guard_policy == "EXCLUDE_HIGH_EVENT" and math.isfinite(th["event_shock_q90_positive"]):
        sig &= df["shock_abs"].to_numpy() < th["event_shock_q90_positive"]
    elif spec.guard_policy == "EXCLUDE_OPPOSING_EVENT":
        if side_long and math.isfinite(th["event_short_q80_positive"]):
            sig &= df["gold_short_pressure"].to_numpy() < th["event_short_q80_positive"]
        if (not side_long) and math.isfinite(th["event_long_q80_positive"]):
            sig &= df["gold_long_pressure"].to_numpy() < th["event_long_q80_positive"]
    return np.asarray(sig, dtype=bool)


def nonoverlap_indices(indices: np.ndarray, horizon_bars: int, max_events: int = 200000) -> np.ndarray:
    if len(indices) == 0:
        return indices
    keep = []
    last = -10**9
    for i in indices:
        if i > last:
            keep.append(i)
            last = int(i) + horizon_bars
            if len(keep) >= max_events:
                break
    return np.asarray(keep, dtype=int)


def evaluate_rule(df: pd.DataFrame, spec: RuleSpec, th: dict, split_index: int, cost_bps: float, fixed_cost_bps: float, use_nonoverlap: bool = True) -> Tuple[dict, Optional[pd.DataFrame]]:
    sig = rule_signal(df, spec, th)
    idx = np.flatnonzero(sig)
    idx = idx[idx + spec.horizon_bars < len(df)]
    if use_nonoverlap:
        idx = nonoverlap_indices(idx, spec.horizon_bars)
    if len(idx) == 0:
        return score_dict(spec, 0, np.nan, np.nan, np.nan, 0, np.nan, np.nan, np.nan, ["NO_EVENTS"]), None

    entry = df["close"].to_numpy()[idx]
    exitp = df["close"].to_numpy()[idx + spec.horizon_bars]
    side_mult = 1.0 if spec.side == "LONG" else -1.0
    gross = side_mult * (exitp / entry - 1.0) * 10000.0
    spread_est = df["spread_bps_est"].to_numpy()[idx]
    effective_cost = np.where(np.isfinite(spread_est) & (spread_est > 0), spread_est, fixed_cost_bps) + fixed_cost_bps
    net = gross - effective_cost
    times = df["time_utc"].iloc[idx].reset_index(drop=True)
    is_train = idx < split_index
    is_holdout = idx >= split_index

    def stats(values: np.ndarray) -> Tuple[int, float, float, float, float]:
        if len(values) == 0:
            return 0, np.nan, np.nan, np.nan, np.nan
        return int(len(values)), float(np.mean(values)), float(np.mean(values > 0)), float(np.quantile(values, 0.10)), float(np.quantile(values, 0.90))

    tr_n, tr_mean, tr_hit, tr_p10, tr_p90 = stats(net[is_train])
    ho_n, ho_mean, ho_hit, ho_p10, ho_p90 = stats(net[is_holdout])

    # concentration by UTC date on all events and holdout events.
    if len(times):
        day_share_all = float(times.dt.date.astype(str).value_counts(normalize=True).iloc[0])
    else:
        day_share_all = np.nan
    if is_holdout.sum() > 0:
        htimes = times[is_holdout].dt.date.astype(str)
        day_share_holdout = float(htimes.value_counts(normalize=True).iloc[0])
    else:
        day_share_holdout = np.nan

    kill = []
    # thresholds stored outside through args? use defaults here and final gating separately in main.
    score = {
        **asdict(spec),
        "params_json": json.dumps(spec.params, sort_keys=True),
        "train_events": tr_n,
        "train_mean_net_bps": tr_mean,
        "train_hit_rate": tr_hit,
        "train_p10_net_bps": tr_p10,
        "train_p90_net_bps": tr_p90,
        "holdout_events": ho_n,
        "holdout_mean_net_bps": ho_mean,
        "holdout_hit_rate": ho_hit,
        "holdout_p10_net_bps": ho_p10,
        "holdout_p90_net_bps": ho_p90,
        "single_day_trade_share_all": day_share_all,
        "single_day_trade_share_holdout": day_share_holdout,
        "event_count_all": int(len(idx)),
    }
    trades = pd.DataFrame({
        "rule_id": spec.rule_id,
        "time_utc": times,
        "side": spec.side,
        "horizon_minutes": spec.horizon_minutes,
        "entry_close": entry,
        "exit_close": exitp,
        "gross_bps": gross,
        "net_bps": net,
        "is_train": is_train,
        "is_holdout": is_holdout,
    })
    return score, trades


def score_dict(spec: RuleSpec, tr_n, tr_mean, tr_hit, tr_p10, ho_n, ho_mean, ho_hit, ho_p10, kill) -> dict:
    return {**asdict(spec), "params_json": json.dumps(spec.params, sort_keys=True), "train_events": tr_n, "train_mean_net_bps": tr_mean, "train_hit_rate": tr_hit, "train_p10_net_bps": tr_p10, "holdout_events": ho_n, "holdout_mean_net_bps": ho_mean, "holdout_hit_rate": ho_hit, "holdout_p10_net_bps": ho_p10, "kill_reasons": ";".join(kill)}


def apply_gates(score: dict, args) -> Tuple[bool, List[str]]:
    kill = []
    if score.get("train_events", 0) < args.min_train_events:
        kill.append("TRAIN_EVENTS_LT_MIN")
    if score.get("holdout_events", 0) < args.min_holdout_events:
        kill.append("HOLDOUT_EVENTS_LT_MIN")
    if not np.isfinite(score.get("train_mean_net_bps", np.nan)) or score["train_mean_net_bps"] < args.min_train_mean_bps:
        kill.append("TRAIN_MEAN_LT_MIN")
    if not np.isfinite(score.get("holdout_mean_net_bps", np.nan)) or score["holdout_mean_net_bps"] < args.min_holdout_mean_bps:
        kill.append("HOLDOUT_MEAN_LT_MIN")
    if not np.isfinite(score.get("train_hit_rate", np.nan)) or score["train_hit_rate"] < args.min_train_hit_rate:
        kill.append("TRAIN_HIT_LT_MIN")
    if not np.isfinite(score.get("holdout_hit_rate", np.nan)) or score["holdout_hit_rate"] < args.min_holdout_hit_rate:
        kill.append("HOLDOUT_HIT_LT_MIN")
    if not np.isfinite(score.get("holdout_p10_net_bps", np.nan)) or score["holdout_p10_net_bps"] < args.min_holdout_p10_bps:
        kill.append("HOLDOUT_LEFT_TAIL_TOO_WEAK")
    if np.isfinite(score.get("single_day_trade_share_holdout", np.nan)) and score["single_day_trade_share_holdout"] > args.max_single_day_trade_share:
        kill.append("HOLDOUT_DAY_CONCENTRATION_TOO_HIGH")
    return len(kill) == 0, kill


def write_decision_md(path: Path, summary: dict, scores: pd.DataFrame) -> None:
    lines = []
    lines.append("# Stage170 Non-News Commercial Alpha Rebuild")
    lines.append("")
    lines.append(f"Generated UTC: `{summary['generated_utc']}`")
    lines.append("")
    lines.append(f"Decision: `{summary['decision']}`")
    lines.append(f"Recommended action: `{summary['recommended_action']}`")
    lines.append("")
    lines.append("## Core rule")
    lines.append("")
    lines.append("GDELT/news is not used as an alpha. It is only a guard/context filter. Commercial discovery is returned to non-news intraday behavior.")
    lines.append("")
    lines.append("## Counts")
    lines.append("")
    ev = summary["evaluation_context"]
    lines.append(f"Rules scanned: `{ev['rule_spec_count']}`")
    lines.append(f"Scores: `{ev['score_count']}`")
    lines.append(f"Commercial shortlist: `{ev['shortlist_count']}`")
    lines.append("")
    lines.append("## Event guard")
    lines.append("")
    lines.append(f"Event guard mode: `{summary['event_guard_context']['mode']}`")
    lines.append(f"Recent guard state: `{summary['event_guard_context'].get('recent_guard_state')}`")
    lines.append("")
    lines.append("## Top failed candidates / candidates")
    lines.append("")
    if len(scores):
        cols = ["rule_id", "family", "side", "horizon_minutes", "session", "guard_policy", "train_events", "train_mean_net_bps", "train_hit_rate", "holdout_events", "holdout_mean_net_bps", "holdout_hit_rate", "holdout_p10_net_bps", "kill_reasons"]
        top = scores.sort_values(["passed", "holdout_mean_net_bps", "train_mean_net_bps"], ascending=[False, False, False]).head(20)
        lines.append(top[cols].to_markdown(index=False))
    else:
        lines.append("No scores generated.")
    lines.append("")
    lines.append("## Next")
    lines.append("")
    for n in summary["next"]:
        lines.append(f"- {n}")
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", required=True)
    ap.add_argument("--bars-m5", required=True)
    ap.add_argument("--event-panel", default=None)
    ap.add_argument("--stage169-guard", default=None)
    ap.add_argument("--holdout-pct", type=float, default=0.20)
    ap.add_argument("--timestamp-shift-hours", type=float, default=-3.0)
    ap.add_argument("--cost-bps", type=float, default=4.0)
    ap.add_argument("--spread-point-size", type=float, default=0.01)
    ap.add_argument("--min-train-events", type=int, default=250)
    ap.add_argument("--min-holdout-events", type=int, default=50)
    ap.add_argument("--min-train-mean-bps", type=float, default=1.0)
    ap.add_argument("--min-holdout-mean-bps", type=float, default=0.25)
    ap.add_argument("--min-train-hit-rate", type=float, default=0.505)
    ap.add_argument("--min-holdout-hit-rate", type=float, default=0.50)
    ap.add_argument("--min-holdout-p10-bps", type=float, default=-45.0)
    ap.add_argument("--max-single-day-trade-share", type=float, default=0.12)
    ap.add_argument("--export-all-rule-trades", action="store_true")
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser()
    outdir = root / "reports" / REPORT_DIRNAME
    outdir.mkdir(parents=True, exist_ok=True)

    bars, bars_meta = load_bars_m5(Path(args.bars_m5).expanduser(), args.timestamp_shift_hours)
    event_panel, event_meta = load_event_panel(Path(args.event_panel).expanduser() if args.event_panel else None)
    df = add_features(bars, event_panel, args.spread_point_size)
    df = df.dropna(subset=["atr48_bps", "mom12_bps", "mom24_bps", "mom48_bps"]).reset_index(drop=True)

    split_index = int(len(df) * (1.0 - args.holdout_pct))
    split_index = max(1, min(split_index, len(df) - 1))
    train = df.iloc[:split_index].copy()
    holdout = df.iloc[split_index:].copy()
    th = build_thresholds(train)
    specs = make_rule_specs(th)

    all_scores = []
    top_trade_frames = []
    all_trade_frames = []
    for i, spec in enumerate(specs):
        score, trades = evaluate_rule(df, spec, th, split_index, args.cost_bps, args.cost_bps, use_nonoverlap=True)
        passed, kill = apply_gates(score, args)
        score["passed"] = bool(passed)
        score["kill_reasons"] = ";".join(kill)
        all_scores.append(score)
        if trades is not None:
            # only keep trades for potentially interesting rules unless full audit requested
            if args.export_all_rule_trades:
                all_trade_frames.append(trades)
            if passed or (np.isfinite(score.get("holdout_mean_net_bps", np.nan)) and score.get("holdout_mean_net_bps", -999) > 0 and score.get("holdout_events", 0) >= max(10, args.min_holdout_events // 2)):
                top_trade_frames.append(trades.assign(passed=passed).head(5000))

    scores = pd.DataFrame(all_scores)
    if len(scores):
        scores = scores.sort_values(["passed", "holdout_mean_net_bps", "train_mean_net_bps", "holdout_events"], ascending=[False, False, False, False]).reset_index(drop=True)
    shortlist = scores[scores["passed"] == True].copy() if len(scores) else pd.DataFrame()

    all_scores_path = outdir / "stage170_all_rule_scores.csv"
    shortlist_path = outdir / "stage170_commercial_shortlist.csv"
    top_trades_path = outdir / "stage170_top_rule_trades.csv"
    all_trades_path = outdir / "stage170_all_rule_trades.csv"
    summary_path = outdir / "stage170_non_news_commercial_alpha_rebuild_summary.json"
    thresholds_path = outdir / "stage170_train_thresholds.json"
    decision_path = outdir / "stage170_decision.md"

    scores.to_csv(all_scores_path, index=False)
    shortlist.to_csv(shortlist_path, index=False)
    if top_trade_frames:
        pd.concat(top_trade_frames, ignore_index=True).to_csv(top_trades_path, index=False)
    else:
        pd.DataFrame().to_csv(top_trades_path, index=False)
    if args.export_all_rule_trades and all_trade_frames:
        pd.concat(all_trade_frames, ignore_index=True).to_csv(all_trades_path, index=False)
    elif args.export_all_rule_trades:
        pd.DataFrame().to_csv(all_trades_path, index=False)

    guard_state = None
    if args.stage169_guard:
        gpath = Path(args.stage169_guard).expanduser()
        if gpath.exists():
            try:
                gj = json.loads(gpath.read_text())
                guard_state = gj.get("current_guard", {}).get("guard_state") or gj.get("guard_state")
            except Exception:
                guard_state = None

    decision = "STAGE170_NON_NEWS_COMMERCIAL_CANDIDATES_FOUND_REQUIRES_STAGE171_EXECUTION_REPLAY" if len(shortlist) else "STAGE170_NO_NON_NEWS_COMMERCIAL_HOLDOUT_CANDIDATE_REDESIGN_OR_KILL_TECH_RULESPACE"
    recommended = "RUN_STAGE171_COSTED_EXECUTION_REPLAY_NO_DEMO_RELEASE" if len(shortlist) else "DO_NOT_WAIT; REBUILD_THESIS_WITH_NEW_FEATURES_OR_RETURN_TO_HUMAN_DESIGNED_BASELINES"
    severity = "WARN" if len(shortlist) else "HIGH"
    summary = {
        "stage": STAGE,
        "generated_utc": pd.Timestamp.utcnow().isoformat(),
        "root": str(root),
        "order_routing_allowed": ORDER_ROUTING_ALLOWED,
        "demo_release_allowed": DEMO_RELEASE_ALLOWED,
        "status": "STAGE170_COMPLETE_NON_NEWS_COMMERCIAL_ALPHA_REBUILD_READY",
        "decision": decision,
        "severity": severity,
        "recommended_action": recommended,
        "bars_m5": str(Path(args.bars_m5).expanduser()),
        "event_panel": str(Path(args.event_panel).expanduser()) if args.event_panel else None,
        "bars_meta": bars_meta,
        "event_meta": event_meta,
        "split_meta": {
            "row_count": int(len(df)),
            "holdout_pct": args.holdout_pct,
            "split_index": int(split_index),
            "train_rows": int(len(train)),
            "holdout_rows": int(len(holdout)),
            "train_start_utc": str(train["time_utc"].min()),
            "train_end_utc": str(train["time_utc"].max()),
            "holdout_start_utc": str(holdout["time_utc"].min()),
            "holdout_end_utc": str(holdout["time_utc"].max()),
        },
        "event_guard_context": {
            "mode": "GUARD_ONLY_NOT_ALPHA",
            "recent_guard_state": guard_state,
            "guard_policies_scanned": ["NONE", "EXCLUDE_HIGH_EVENT", "EXCLUDE_OPPOSING_EVENT"],
            "note": "Event/news panel is used only as a filter/context guard; no rule enters because of event intensity alone.",
        },
        "thresholds": th,
        "gate_thresholds": {
            "min_train_events": args.min_train_events,
            "min_holdout_events": args.min_holdout_events,
            "min_train_mean_bps": args.min_train_mean_bps,
            "min_holdout_mean_bps": args.min_holdout_mean_bps,
            "min_train_hit_rate": args.min_train_hit_rate,
            "min_holdout_hit_rate": args.min_holdout_hit_rate,
            "min_holdout_p10_bps": args.min_holdout_p10_bps,
            "max_single_day_trade_share": args.max_single_day_trade_share,
        },
        "evaluation_context": {
            "rule_spec_count": int(len(specs)),
            "score_count": int(len(scores)),
            "shortlist_count": int(len(shortlist)),
            "pass_family_counts": shortlist["family"].value_counts().to_dict() if len(shortlist) else {},
            "candidate_family_counts": scores["family"].value_counts().to_dict() if len(scores) else {},
            "export_all_rule_trades": bool(args.export_all_rule_trades),
        },
        "top_shortlist_rule_ids": shortlist["rule_id"].head(20).tolist() if len(shortlist) else [],
        "top_score_rule_ids": scores["rule_id"].head(20).tolist() if len(scores) else [],
        "outputs": {
            "summary_json": str(summary_path),
            "all_rule_scores_csv": str(all_scores_path),
            "commercial_shortlist_csv": str(shortlist_path),
            "top_rule_trades_csv": str(top_trades_path),
            "all_rule_trades_csv": str(all_trades_path) if args.export_all_rule_trades else None,
            "thresholds_json": str(thresholds_path),
            "decision_md": str(decision_path),
        },
        "next": [
            "If shortlist_count is positive, run Stage171 execution replay before any demo release.",
            "If shortlist_count is zero, do not wait for more samples; either redesign features or return to prior human-designed baseline families.",
            "Keep GDELT/news as current guard only unless stronger labeled historical event data is added.",
            "Do not release demo/live orders from Stage170 output alone.",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    thresholds_path.write_text(json.dumps(th, indent=2), encoding="utf-8")
    write_decision_md(decision_path, summary, scores)
    print(json.dumps({"stage": STAGE, "decision": decision, "shortlist_count": int(len(shortlist)), "score_count": int(len(scores)), "summary_json": str(summary_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
