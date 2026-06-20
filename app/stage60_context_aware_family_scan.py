#!/usr/bin/env python3
"""
Stage60 Context-Aware Parallel Family Scan

Historical broker-real scan of additional context-aware families while true-forward
Stage52/Stage58B continues. This is not forward evidence and authorizes no orders.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
    import pandas as pd
except Exception as exc:
    raise SystemExit(f"pandas/numpy are required: {exc}")

STAGE = "Stage60_CONTEXT_AWARE_PARALLEL_FAMILY_SCAN_NO_PROMOTION"
STATUS = "CONTEXT_AWARE_PARALLEL_SCAN_COMPLETE_NO_PROMOTION"
PASS_STATUS = "CONTEXT_FAMILY_HARD_AUDIT_PASS_NEEDS_FORWARD_SHADOW_DESIGN"
NO_PASS_STATUS = "NO_PASS"
NO_GO = "NO_GO"
REQUIRED_COLS = {"time_utc", "timeframe", "open", "high", "low", "close", "spread_cost_bps"}


@dataclass
class Thresholds:
    min_trade_count: int = 120
    min_oos_trade_count: int = 30
    min_mean_stress_bps: float = 2.0
    min_median_stress_bps: float = 0.0
    min_win_rate: float = 0.53
    min_oos_mean_stress_bps: float = 0.0
    min_oos_win_rate: float = 0.52
    min_positive_years: int = 4
    max_negative_years: int = 1
    min_worst_year_mean_stress_bps: float = 0.0
    min_cost_x2_mean_stress_bps: float = 0.0
    max_direction_share: float = 0.70
    max_day_share: float = 0.35
    min_declustered_trade_count: int = 50
    min_declustered_mean_stress_bps: float = 0.0
    min_declustered_win_rate: float = 0.50


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=STAGE)
    p.add_argument("--root", default=".")
    p.add_argument("--db", default="data/broker_normalized/amarkets_multitf.sqlite")
    p.add_argument("--cost-model", default="reports/stage48f/stage48f_cost_model.json")
    p.add_argument("--m15-context", default="reports/stage57_context_precheck/stage57a_m15_context_regime_table.csv")
    p.add_argument("--config", default="configs/stage60_context_aware_family_scan.json")
    p.add_argument("--out", default="reports/stage60_context_aware_family_scan")
    p.add_argument("--max-events-per-family", type=int, default=250000)
    return p.parse_args()


def resolve(root: Path, p: str | Path) -> Path:
    q = Path(p)
    return q if q.is_absolute() else root / q


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def load_cost_model(path: Path) -> Dict[str, float]:
    data = read_json(path, {}) or {}
    candidates = [data]
    for key in ("costs", "cost_model", "summary"):
        if isinstance(data.get(key), dict):
            candidates.append(data[key])
    out = {"stress_cost_bps": 2.982003733153722, "extreme_cost_bps": 3.0380209087577326}
    for d in candidates:
        for k in ("stress_cost_bps", "recommended_cost_bps", "default_cost_bps"):
            if k in d and d[k] is not None:
                out["stress_cost_bps"] = float(d[k]); break
        for k in ("extreme_cost_bps", "p99_spread_cost_bps"):
            if k in d and d[k] is not None:
                out["extreme_cost_bps"] = float(d[k]); break
    return out


def sqlite_table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def load_bars(db: Path, timeframe: str) -> pd.DataFrame:
    if not db.exists():
        raise FileNotFoundError(f"DB not found: {db}")
    with sqlite3.connect(str(db)) as conn:
        cols = sqlite_table_columns(conn, "amarkets_bars")
        missing = REQUIRED_COLS - set(cols)
        if missing:
            raise ValueError(f"amarkets_bars missing required columns: {sorted(missing)}")
        q = """
        SELECT time_utc, open, high, low, close, tick_volume, spread_cost_bps
        FROM amarkets_bars
        WHERE timeframe = ?
        ORDER BY time_utc
        """
        df = pd.read_sql_query(q, conn, params=(timeframe,))
    if df.empty:
        raise ValueError(f"No rows for timeframe {timeframe}")
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    for c in ["open", "high", "low", "close", "tick_volume", "spread_cost_bps"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["time_utc", "open", "high", "low", "close"]).reset_index(drop=True)


def infer_session(hour: int) -> str:
    if 0 <= hour < 7:
        return "asia"
    if 7 <= hour < 12:
        return "london"
    if 12 <= hour < 16:
        return "london_ny_overlap"
    if 16 <= hour < 21:
        return "new_york"
    return "late_us"


def add_context_inline(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    x["hour_utc"] = x["time_utc"].dt.hour
    x["weekday"] = x["time_utc"].dt.weekday
    x["date_utc"] = x["time_utc"].dt.date.astype(str)
    x["session"] = x["hour_utc"].apply(infer_session)
    x["range_bps"] = (x["high"] - x["low"]) / x["close"].replace(0, np.nan) * 1e4
    x["return_bps"] = x["close"].pct_change() * 1e4
    x["abs_return_bps"] = x["return_bps"].abs()
    sq = x["spread_cost_bps"].quantile([.5,.75,.9,.95,.99]).to_dict()
    rq = x["range_bps"].quantile([.25,.5,.75,.9]).to_dict()
    x["spread_regime"] = np.select(
        [x.spread_cost_bps <= sq.get(.5, np.inf), x.spread_cost_bps <= sq.get(.75, np.inf), x.spread_cost_bps <= sq.get(.9, np.inf), x.spread_cost_bps <= sq.get(.95, np.inf), x.spread_cost_bps <= sq.get(.99, np.inf)],
        ["spread_le_50", "spread_le_75", "spread_le_90", "spread_le_95", "spread_le_99"], default="spread_gt_99")
    x["range_regime"] = np.select(
        [x.range_bps <= rq.get(.25, np.inf), x.range_bps <= rq.get(.5, np.inf), x.range_bps <= rq.get(.75, np.inf), x.range_bps <= rq.get(.9, np.inf)],
        ["range_le_25", "range_le_50", "range_le_75", "range_le_90"], default="range_gt_90")
    x["rollover_like"] = x["hour_utc"].isin([21,22,23,0])
    return x


def load_or_derive_context(path: Path, m15: pd.DataFrame) -> pd.DataFrame:
    need = {"time_utc", "session", "spread_regime", "range_regime", "rollover_like", "range_bps", "spread_cost_bps"}
    if path.exists():
        try:
            ctx = pd.read_csv(path)
            if "time_utc" in ctx.columns and need.issubset(set(ctx.columns)):
                ctx["time_utc"] = pd.to_datetime(ctx["time_utc"], utc=True)
                return ctx
        except Exception:
            pass
    return add_context_inline(m15)


def prepare_frames(m15: pd.DataFrame, m30: pd.DataFrame, ctx: pd.DataFrame) -> pd.DataFrame:
    x = add_context_inline(m15)
    # Prefer Stage57A labels where available.
    keep = [c for c in ["time_utc", "session", "spread_regime", "range_regime", "rollover_like", "range_bps", "spread_cost_bps"] if c in ctx.columns]
    c = ctx[keep].copy()
    for col in ["session", "spread_regime", "range_regime", "rollover_like", "range_bps", "spread_cost_bps"]:
        if col in c.columns:
            c = c.rename(columns={col: f"ctx_{col}"})
    x = x.merge(c, on="time_utc", how="left")
    for col in ["session", "spread_regime", "range_regime", "rollover_like", "range_bps", "spread_cost_bps"]:
        cc = f"ctx_{col}"
        if cc in x.columns:
            x[col] = x[cc].combine_first(x[col])
            x.drop(columns=[cc], inplace=True)
    m30x = m30[["time_utc", "close"]].copy().sort_values("time_utc")
    for w in [20, 40, 72]:
        m30x[f"m30_sma_{w}"] = m30x["close"].rolling(w, min_periods=max(5, w//3)).mean()
    x = pd.merge_asof(x.sort_values("time_utc"), m30x, on="time_utc", direction="backward", suffixes=("", "_m30"))
    for w in [8, 16, 32, 48, 96]:
        x[f"sma_{w}"] = x["close"].rolling(w, min_periods=max(5, w//3)).mean()
        x[f"ret_{w}_bps"] = (x["close"] / x["close"].shift(w) - 1.0) * 1e4
    for w in [16, 32, 48, 96]:
        x[f"prior_high_{w}"] = x["high"].rolling(w, min_periods=max(5, w//3)).max().shift(1)
        x[f"prior_low_{w}"] = x["low"].rolling(w, min_periods=max(5, w//3)).min().shift(1)
    x["body_bps"] = (x["close"] - x["open"]) / x["close"].replace(0, np.nan) * 1e4
    x["upper_wick_bps"] = (x["high"] - x[["open", "close"]].max(axis=1)) / x["close"].replace(0, np.nan) * 1e4
    x["lower_wick_bps"] = (x[["open", "close"]].min(axis=1) - x["low"]) / x["close"].replace(0, np.nan) * 1e4
    return x.reset_index(drop=True)


def context_mask(df: pd.DataFrame, tag: str) -> pd.Series:
    if tag == "CTX_ALL":
        return pd.Series(True, index=df.index)
    if tag == "CTX_NO_ROLLOVER":
        return ~df["rollover_like"].astype(bool)
    if tag == "CTX_SPREAD_LE75":
        return df["spread_regime"].isin(["spread_le_50", "spread_le_75"])
    if tag == "CTX_SPREAD_LE90":
        return df["spread_regime"].isin(["spread_le_50", "spread_le_75", "spread_le_90"])
    if tag == "CTX_RANGE_GT50":
        return df["range_regime"].isin(["range_le_75", "range_le_90", "range_gt_90"])
    if tag == "CTX_LONDON_OVERLAP_NY":
        return df["session"].isin(["london", "london_ny_overlap", "new_york"])
    if tag == "CTX_CLEAN_ACTIVE":
        return (~df["rollover_like"].astype(bool)) & df["session"].isin(["london", "london_ny_overlap", "new_york"]) & df["spread_regime"].isin(["spread_le_50", "spread_le_75", "spread_le_90"])
    return pd.Series(True, index=df.index)


def _timestamp_to_utc_ns(value: Any) -> int:
    """Return a UTC nanosecond timestamp, normalizing tz-naive inputs as UTC.

    Pandas/NumPy searchsorted can fail when one side is tz-aware and the
    other side is tz-naive. Stage60 compares event timestamps against broker
    M5 timestamps, so both sides are converted to integer UTC nanoseconds.
    """
    t = pd.Timestamp(value)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    else:
        t = t.tz_convert("UTC")
    return int(t.value)


def _utc_ns_to_z(ns: int) -> str:
    return pd.Timestamp(int(ns), tz="UTC").isoformat().replace("+00:00", "Z")


def eval_events(events: pd.DataFrame, m5: pd.DataFrame, cost: float) -> pd.DataFrame:
    if events.empty:
        return events
    m5 = m5.sort_values("time_utc").reset_index(drop=True).copy()
    # Normalize all broker times to integer UTC nanoseconds. This avoids
    # tz-aware/tz-naive comparisons inside np.searchsorted on Python 3.14 / pandas.
    m5["time_utc"] = pd.to_datetime(m5["time_utc"], utc=True)
    times_ns = m5["time_utc"].map(_timestamp_to_utc_ns).to_numpy(dtype="int64")
    closes = m5["close"].to_numpy(dtype=float)
    spreads = m5["spread_cost_bps"].to_numpy(dtype=float) if "spread_cost_bps" in m5 else np.zeros(len(m5))
    rows = []
    for r in events.itertuples(index=False):
        try:
            t_ns = _timestamp_to_utc_ns(getattr(r, "signal_time_utc"))
        except Exception:
            continue
        pos = int(np.searchsorted(times_ns, t_ns, side="right"))
        h = int(getattr(r, "horizon_m5_bars"))
        exit_pos = pos + h
        if pos >= len(m5) or exit_pos >= len(m5):
            continue
        entry = float(closes[pos]); exitp = float(closes[exit_pos])
        if not (entry > 0 and exitp > 0):
            continue
        direction = int(getattr(r, "direction"))
        gross = (exitp / entry - 1.0) * 1e4 * direction
        eff_cost = max(float(cost), float(spreads[pos]) if not math.isnan(spreads[pos]) else 0.0)
        d = r._asdict()
        d.update({
            "entry_time_utc": _utc_ns_to_z(times_ns[pos]),
            "exit_time_utc": _utc_ns_to_z(times_ns[exit_pos]),
            "entry_price": entry,
            "exit_price": exitp,
            "gross_bps": gross,
            "stress_cost_bps": eff_cost,
            "stress_bps": gross - eff_cost,
            "date_utc": pd.Timestamp(int(times_ns[pos]), tz="UTC").date().isoformat(),
            "year": int(pd.Timestamp(int(times_ns[pos]), tz="UTC").year),
        })
        rows.append(d)
    return pd.DataFrame(rows)


def generate_family_events(df: pd.DataFrame, family: str, cfg: Dict[str, Any]) -> pd.DataFrame:
    rows = []
    context_tags = cfg.get("context_tags", ["CTX_ALL", "CTX_SPREAD_LE75", "CTX_RANGE_GT50", "CTX_CLEAN_ACTIVE"])
    horizons = cfg.get("horizons_m5", [6, 12, 24])
    if family == "CTX_MOMENTUM_CONTINUATION":
        for lookback in cfg.get("lookbacks", [16, 32, 48]):
            for min_imp in cfg.get("min_impulse_bps", [12, 18, 28]):
                for breakout_buffer in cfg.get("breakout_buffer_bps", [2, 4, 6]):
                    for m30_sma in cfg.get("m30_sma", [20, 40]):
                        trend = np.where(df["close_m30"] > df[f"m30_sma_{m30_sma}"], 1, -1)
                        up = (df[f"ret_{lookback}_bps"] >= min_imp) & (df["close"] > df[f"prior_high_{lookback}"] * (1 + breakout_buffer/1e4)) & (trend == 1)
                        dn = (df[f"ret_{lookback}_bps"] <= -min_imp) & (df["close"] < df[f"prior_low_{lookback}"] * (1 - breakout_buffer/1e4)) & (trend == -1)
                        for ctx_tag in context_tags:
                            base = context_mask(df, ctx_tag)
                            for h in horizons:
                                for direction, mask in [(1, up & base), (-1, dn & base)]:
                                    sub = df.loc[mask, ["time_utc"]].copy()
                                    if sub.empty: continue
                                    sub["family"] = family; sub["direction"] = direction; sub["horizon_m5_bars"] = h
                                    sub["candidate_id"] = f"S60_MOMO_L{lookback}_I{min_imp}_B{breakout_buffer}_M30{m30_sma}_H{h}_{ctx_tag}"
                                    sub["context_tag"] = ctx_tag
                                    sub["params_json"] = json.dumps({"lookback":lookback,"min_impulse_bps":min_imp,"breakout_buffer_bps":breakout_buffer,"m30_sma":m30_sma}, sort_keys=True)
                                    rows.append(sub.rename(columns={"time_utc":"signal_time_utc"}))
    elif family == "CTX_TREND_PULLBACK_CONTINUATION":
        for sma in cfg.get("value_sma", [16, 32, 48]):
            for max_dist in cfg.get("max_value_distance_bps", [4, 8, 12]):
                for min_trend in cfg.get("min_trend_bps", [12, 20, 32]):
                    for m30_sma in cfg.get("m30_sma", [20, 40, 72]):
                        trend = np.where(df["close_m30"] > df[f"m30_sma_{m30_sma}"], 1, -1)
                        dist = ((df["close"] - df[f"sma_{sma}"]).abs() / df["close"].replace(0, np.nan) * 1e4) <= max_dist
                        up = (trend == 1) & (df[f"ret_{sma}_bps"] >= min_trend) & dist & (df["close"] > df["open"])
                        dn = (trend == -1) & (df[f"ret_{sma}_bps"] <= -min_trend) & dist & (df["close"] < df["open"])
                        for ctx_tag in context_tags:
                            base = context_mask(df, ctx_tag)
                            for h in horizons:
                                for direction, mask in [(1, up & base), (-1, dn & base)]:
                                    sub = df.loc[mask, ["time_utc"]].copy()
                                    if sub.empty: continue
                                    sub["family"] = family; sub["direction"] = direction; sub["horizon_m5_bars"] = h
                                    sub["candidate_id"] = f"S60_PB_SMA{sma}_D{max_dist}_T{min_trend}_M30{m30_sma}_H{h}_{ctx_tag}"
                                    sub["context_tag"] = ctx_tag
                                    sub["params_json"] = json.dumps({"value_sma":sma,"max_dist_bps":max_dist,"min_trend_bps":min_trend,"m30_sma":m30_sma}, sort_keys=True)
                                    rows.append(sub.rename(columns={"time_utc":"signal_time_utc"}))
    elif family == "CTX_EXHAUSTION_REVERSAL":
        for min_range_regime in cfg.get("range_filters", ["range_gt_90", "range_gt_50"]):
            for min_wick in cfg.get("min_wick_bps", [4, 8, 12]):
                for body_max in cfg.get("max_abs_body_bps", [8, 14, 24]):
                    if min_range_regime == "range_gt_90":
                        rmask = df["range_regime"].isin(["range_gt_90"])
                    else:
                        rmask = df["range_regime"].isin(["range_le_75", "range_le_90", "range_gt_90"])
                    up_exhaust = rmask & (df["upper_wick_bps"] >= min_wick) & (df["body_bps"].abs() <= body_max) & (df["close"] < df["open"])
                    dn_exhaust = rmask & (df["lower_wick_bps"] >= min_wick) & (df["body_bps"].abs() <= body_max) & (df["close"] > df["open"])
                    for ctx_tag in context_tags:
                        base = context_mask(df, ctx_tag)
                        for h in horizons:
                            for direction, mask in [(-1, up_exhaust & base), (1, dn_exhaust & base)]:
                                sub = df.loc[mask, ["time_utc"]].copy()
                                if sub.empty: continue
                                sub["family"] = family; sub["direction"] = direction; sub["horizon_m5_bars"] = h
                                sub["candidate_id"] = f"S60_REV_R{min_range_regime}_W{min_wick}_B{body_max}_H{h}_{ctx_tag}"
                                sub["context_tag"] = ctx_tag
                                sub["params_json"] = json.dumps({"range_filter":min_range_regime,"min_wick_bps":min_wick,"max_abs_body_bps":body_max}, sort_keys=True)
                                rows.append(sub.rename(columns={"time_utc":"signal_time_utc"}))
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def mean_safe(x: pd.Series) -> Optional[float]:
    return None if x.empty else float(x.mean())


def audit_group(g: pd.DataFrame, th: Thresholds) -> Dict[str, Any]:
    g = g.sort_values("entry_time_utc").reset_index(drop=True)
    n = int(len(g))
    oos_start = int(n * 0.8)
    isg = g.iloc[:oos_start]
    oos = g.iloc[oos_start:]
    years = g.groupby("year")["stress_bps"].mean() if n else pd.Series(dtype=float)
    daily = g.groupby("date_utc").head(1) if n else g
    dir_counts = g["direction"].value_counts(normalize=True) if n else pd.Series(dtype=float)
    day_counts = g["date_utc"].value_counts(normalize=True) if n else pd.Series(dtype=float)
    cost2 = g["gross_bps"] - 2.0 * g["stress_cost_bps"] if n else pd.Series(dtype=float)
    out = {
        "trade_count": n,
        "oos_trade_count": int(len(oos)),
        "mean_stress_bps": mean_safe(g["stress_bps"]),
        "median_stress_bps": None if n == 0 else float(g["stress_bps"].median()),
        "win_rate": None if n == 0 else float((g["stress_bps"] > 0).mean()),
        "t_stat": None if n < 3 or float(g["stress_bps"].std(ddof=1) or 0) == 0 else float(g["stress_bps"].mean() / (g["stress_bps"].std(ddof=1) / math.sqrt(n))),
        "is_mean_stress_bps": mean_safe(isg["stress_bps"]),
        "is_win_rate": None if len(isg) == 0 else float((isg["stress_bps"] > 0).mean()),
        "oos_mean_stress_bps": mean_safe(oos["stress_bps"]),
        "oos_win_rate": None if len(oos) == 0 else float((oos["stress_bps"] > 0).mean()),
        "positive_year_count": int((years > 0).sum()),
        "negative_year_count": int((years < 0).sum()),
        "worst_year_mean_stress_bps": None if years.empty else float(years.min()),
        "cost_x2_mean_stress_bps": mean_safe(cost2),
        "declustered_trade_count": int(len(daily)),
        "declustered_mean_stress_bps": mean_safe(daily["stress_bps"]),
        "declustered_win_rate": None if len(daily) == 0 else float((daily["stress_bps"] > 0).mean()),
        "max_direction_share": 0.0 if dir_counts.empty else float(dir_counts.max()),
        "max_day_share": 0.0 if day_counts.empty else float(day_counts.max()),
        "first_entry_utc": None if n == 0 else str(g["entry_time_utc"].iloc[0]),
        "last_entry_utc": None if n == 0 else str(g["entry_time_utc"].iloc[-1]),
    }
    fail = []
    checks = [
        ("trade_count_lt_min", out["trade_count"] >= th.min_trade_count),
        ("oos_trade_count_lt_min", out["oos_trade_count"] >= th.min_oos_trade_count),
        ("mean_stress_lt_min", (out["mean_stress_bps"] or -1e9) >= th.min_mean_stress_bps),
        ("median_stress_lt_min", (out["median_stress_bps"] or -1e9) >= th.min_median_stress_bps),
        ("win_rate_lt_min", (out["win_rate"] or -1e9) >= th.min_win_rate),
        ("oos_mean_lt_min", (out["oos_mean_stress_bps"] or -1e9) >= th.min_oos_mean_stress_bps),
        ("oos_win_rate_lt_min", (out["oos_win_rate"] or -1e9) >= th.min_oos_win_rate),
        ("positive_years_lt_min", out["positive_year_count"] >= th.min_positive_years),
        ("negative_years_gt_max", out["negative_year_count"] <= th.max_negative_years),
        ("worst_year_lt_min", (out["worst_year_mean_stress_bps"] or -1e9) >= th.min_worst_year_mean_stress_bps),
        ("cost_x2_mean_lt_min", (out["cost_x2_mean_stress_bps"] or -1e9) >= th.min_cost_x2_mean_stress_bps),
        ("max_direction_share_gt_max", out["max_direction_share"] <= th.max_direction_share),
        ("max_day_share_gt_max", out["max_day_share"] <= th.max_day_share),
        ("declustered_trade_count_lt_min", out["declustered_trade_count"] >= th.min_declustered_trade_count),
        ("declustered_mean_lt_min", (out["declustered_mean_stress_bps"] or -1e9) >= th.min_declustered_mean_stress_bps),
        ("declustered_win_rate_lt_min", (out["declustered_win_rate"] or -1e9) >= th.min_declustered_win_rate),
    ]
    for name, ok in checks:
        if not ok: fail.append(name)
    out["failures"] = ";".join(fail)
    out["status"] = PASS_STATUS if not fail else NO_PASS_STATUS
    return out


def scan(root: Path, args: argparse.Namespace) -> Tuple[Dict[str, Any], pd.DataFrame, pd.DataFrame]:
    cfg = read_json(resolve(root, args.config), {}) or {}
    thresholds = Thresholds(**{**asdict(Thresholds()), **cfg.get("audit_thresholds", {})})
    costs = load_cost_model(resolve(root, args.cost_model))
    m15 = load_bars(resolve(root, args.db), "M15")
    m30 = load_bars(resolve(root, args.db), "M30")
    m5 = load_bars(resolve(root, args.db), "M5")
    ctx = load_or_derive_context(resolve(root, args.m15_context), m15)
    frame = prepare_frames(m15, m30, ctx)
    families = cfg.get("families", {}) or {}
    if not families:
        families = {
            "CTX_MOMENTUM_CONTINUATION": {},
            "CTX_TREND_PULLBACK_CONTINUATION": {},
            "CTX_EXHAUSTION_REVERSAL": {},
        }
    all_events = []
    family_summary = {}
    for family, fcfg in families.items():
        ev = generate_family_events(frame, family, fcfg or {})
        raw_events = int(len(ev))
        if len(ev) > args.max_events_per_family:
            ev = ev.sort_values("signal_time_utc").tail(args.max_events_per_family).reset_index(drop=True)
        tr = eval_events(ev, m5, costs["stress_cost_bps"])
        family_summary[family] = {"raw_events": raw_events, "evaluated_trade_rows": int(len(tr)), "candidate_count": int(tr["candidate_id"].nunique()) if not tr.empty else 0, "hard_audit_pass_count": 0}
        if not tr.empty:
            all_events.append(tr)
    trades = pd.concat(all_events, ignore_index=True) if all_events else pd.DataFrame()
    cand_rows = []
    if not trades.empty:
        for cid, g in trades.groupby("candidate_id"):
            row = audit_group(g, thresholds)
            row["candidate_id"] = cid
            row["family"] = str(g["family"].iloc[0])
            row["context_tag"] = str(g["context_tag"].iloc[0])
            row["params_json"] = str(g["params_json"].iloc[0])
            cand_rows.append(row)
    candidates = pd.DataFrame(cand_rows)
    if not candidates.empty:
        candidates = candidates.sort_values(["status", "oos_mean_stress_bps", "mean_stress_bps"], ascending=[True, False, False]).reset_index(drop=True)
        for fam in family_summary:
            family_summary[fam]["hard_audit_pass_count"] = int(((candidates["family"] == fam) & (candidates["status"] == PASS_STATUS)).sum())
    pass_count = int((candidates["status"] == PASS_STATUS).sum()) if not candidates.empty else 0
    summary = {
        "stage": STAGE,
        "status": STATUS,
        "promotion": NO_GO,
        "EA": NO_GO,
        "paper_live": NO_GO,
        "live": NO_GO,
        "decision": "CONTEXT_AWARE_PARALLEL_SCAN_PASS_NEEDS_FORWARD_SHADOW_DESIGN_NO_PROMOTION" if pass_count else "CONTEXT_AWARE_PARALLEL_SCAN_COMPLETE_NO_PASS_NO_PROMOTION",
        "next_allowed_step": "DESIGN_STAGE60_FORWARD_SHADOW_OR_MERGE_WITH_STAGE58B_NO_PROMOTION" if pass_count else "ARCHIVE_STAGE60_CONTEXT_FAMILIES_OR_EXPAND_EXTERNAL_CONTEXT_NO_PROMOTION",
        "root": str(root),
        "db": str(resolve(root, args.db)),
        "cost_model": str(resolve(root, args.cost_model)),
        "m15_context": str(resolve(root, args.m15_context)),
        "rows": {"M15": int(len(m15)), "M30": int(len(m30)), "M5": int(len(m5)), "M15_context": int(len(ctx))},
        "costs": costs,
        "family_summary": family_summary,
        "total_trade_rows": int(len(trades)),
        "total_candidates": int(len(candidates)),
        "hard_audit_pass_count": pass_count,
        "audit_thresholds": asdict(thresholds),
        "generated_utc": utcnow(),
    }
    return summary, candidates, trades


def write_report(path: Path, summary: Dict[str, Any], candidates: pd.DataFrame) -> None:
    lines = [
        "# Stage60 Context-Aware Parallel Family Scan", "",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- next_allowed_step: `{summary['next_allowed_step']}`",
        f"- promotion: `{summary['promotion']}`", f"- EA: `{summary['EA']}`", f"- paper_live: `{summary['paper_live']}`", f"- live: `{summary['live']}`", "",
        "## Family summary",
    ]
    for fam, d in summary.get("family_summary", {}).items():
        lines.append(f"- `{fam}`: candidates=`{d.get('candidate_count')}`, trades=`{d.get('evaluated_trade_rows')}`, pass=`{d.get('hard_audit_pass_count')}`, raw_events=`{d.get('raw_events')}`")
    lines += ["", "## Top candidates"]
    if candidates.empty:
        lines.append("- none")
    else:
        for _, r in candidates.head(25).iterrows():
            lines.append(f"- `{r['candidate_id']}` family=`{r['family']}` status=`{r['status']}` trades=`{int(r['trade_count'])}` mean=`{float(r['mean_stress_bps'] or 0):.3f}` wr=`{float(r['win_rate'] or 0):.3f}` oos_mean=`{r.get('oos_mean_stress_bps')}` failures=`{r.get('failures','')}`")
    lines += ["", "## Interpretation", "Stage60 is a historical context-aware scan only. It does not create forward evidence and does not authorize promotion, EA, paper-live, live trading, or order submission."]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    root = Path(args.root).resolve()
    out = resolve(root, args.out)
    out.mkdir(parents=True, exist_ok=True)
    summary, candidates, trades = scan(root, args)
    write_json(out / "stage60_context_aware_family_scan_summary.json", summary)
    write_report(out / "stage60_context_aware_family_scan_report.md", summary, candidates)
    candidates.to_csv(out / "stage60_context_aware_family_scan_candidates.csv", index=False)
    sample_cols = [c for c in ["candidate_id","family","context_tag","signal_time_utc","entry_time_utc","direction","horizon_m5_bars","entry_price","exit_price","gross_bps","stress_bps","params_json"] if c in trades.columns]
    if trades.empty or "entry_time_utc" not in trades.columns:
        pd.DataFrame(columns=sample_cols).to_csv(out / "stage60_context_aware_family_scan_event_sample.csv", index=False)
    else:
        trades.sort_values("entry_time_utc").head(3000)[sample_cols].to_csv(out / "stage60_context_aware_family_scan_event_sample.csv", index=False)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
