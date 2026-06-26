#!/usr/bin/env python3
"""
Stage58A Context-Aware Stage51 Regime Audit

Historical, broker-real, cost-aware context/regime overlay for Stage51 volatility-squeeze candidates.
No promotion, no EA, no paper-live, no live trading, no order submission.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import pandas as pd
    import numpy as np
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"pandas/numpy are required: {exc}")

STAGE = "Stage58A_CONTEXT_AWARE_STAGE51_REGIME_AUDIT_NO_PROMOTION"
STATUS = "CONTEXT_AWARE_STAGE51_AUDIT_COMPLETE_NO_PROMOTION"
NO_GO = "NO_GO"

PASS_STATUS = "CONTEXT_AWARE_HARD_AUDIT_PASS_NEEDS_FORWARD_SHADOW_DESIGN"
NO_PASS_STATUS = "NO_PASS"

REQUIRED_COLS = {"time_utc", "timeframe", "open", "high", "low", "close", "spread_cost_bps"}


@dataclass
class CandidateParams:
    candidate_id: str
    cw: int
    pct: float
    buffer_bps: float
    m30_sma: int
    horizon_m5_bars: int


@dataclass
class AuditThresholds:
    min_trade_count: int = 80
    min_oos_trade_count: int = 20
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
    min_declustered_trade_count: int = 40
    min_declustered_mean_stress_bps: float = 0.0
    min_declustered_win_rate: float = 0.50


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=STAGE)
    p.add_argument("--root", default=".")
    p.add_argument("--db", default="data/broker_normalized/amarkets_multitf.sqlite")
    p.add_argument("--cost-model", default="reports/stage48f/stage48f_cost_model.json")
    p.add_argument("--stage51-candidates", default="reports/stage51_volatility_squeeze/stage51_volatility_squeeze_breakout_candidates.csv")
    p.add_argument("--m15-context", default="reports/stage57_context_precheck/stage57a_m15_context_regime_table.csv")
    p.add_argument("--m5-context", default="reports/stage57_context_precheck/stage57a_m5_context_regime_table.csv")
    p.add_argument("--config", default="configs/stage58a_context_aware_stage51_regime_audit.json")
    p.add_argument("--out", default="reports/stage58_context_aware_stage51")
    p.add_argument("--max-stage51-candidates", type=int, default=12)
    return p.parse_args()


def resolve(root: Path, path: str | Path) -> Path:
    q = Path(path)
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
    # Support both direct cost model and wrapped summaries.
    candidates = [data]
    for key in ("costs", "cost_model", "summary"):
        if isinstance(data.get(key), dict):
            candidates.append(data[key])
    out = {
        "stress_cost_bps": 2.982003733153722,
        "extreme_cost_bps": 3.0380209087577326,
    }
    for d in candidates:
        for k in ("stress_cost_bps", "recommended_cost_bps", "default_cost_bps"):
            if k in d and d[k] is not None:
                out["stress_cost_bps"] = float(d[k])
                break
        for k in ("extreme_cost_bps", "p99_spread_cost_bps"):
            if k in d and d[k] is not None:
                out["extreme_cost_bps"] = float(d[k])
                break
    return out


def sqlite_table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cur.fetchall()]


def load_bars(db: Path, timeframe: str) -> pd.DataFrame:
    if not db.exists():
        raise FileNotFoundError(f"DB not found: {db}")
    with sqlite3.connect(str(db)) as conn:
        cols = sqlite_table_columns(conn, "amarkets_bars")
        missing = REQUIRED_COLS - set(cols)
        if missing:
            raise ValueError(f"amarkets_bars missing columns: {sorted(missing)}")
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
    df = df.dropna(subset=["time_utc", "open", "high", "low", "close"]).reset_index(drop=True)
    return df


def infer_session(hour: int) -> str:
    # UTC session buckets aligned with prior project convention.
    if 0 <= hour < 7:
        return "asia"
    if 7 <= hour < 12:
        return "london"
    if 12 <= hour < 16:
        return "london_ny_overlap"
    if 16 <= hour < 21:
        return "new_york"
    return "late_us"


def add_derived_context(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    x = df.copy()
    x["range_bps"] = (x["high"] - x["low"]) / x["close"].replace(0, np.nan) * 1e4
    x["return_bps"] = x["close"].pct_change() * 1e4
    x["abs_return_bps"] = x["return_bps"].abs()
    x["hour_utc"] = x["time_utc"].dt.hour
    x["weekday"] = x["time_utc"].dt.weekday
    x["date_utc"] = x["time_utc"].dt.date.astype(str)
    x["session"] = x["hour_utc"].apply(infer_session)
    # Per-timeframe quantiles for deterministic labels.
    spread_q = x["spread_cost_bps"].quantile([0.5, 0.75, 0.9, 0.95, 0.99]).to_dict()
    range_q = x["range_bps"].quantile([0.25, 0.5, 0.75, 0.9]).to_dict()
    x["spread_regime"] = np.select(
        [
            x["spread_cost_bps"] <= spread_q.get(0.5, np.inf),
            x["spread_cost_bps"] <= spread_q.get(0.75, np.inf),
            x["spread_cost_bps"] <= spread_q.get(0.9, np.inf),
            x["spread_cost_bps"] <= spread_q.get(0.95, np.inf),
            x["spread_cost_bps"] <= spread_q.get(0.99, np.inf),
        ],
        ["spread_le_50", "spread_le_75", "spread_le_90", "spread_le_95", "spread_le_99"],
        default="spread_gt_99",
    )
    x["range_regime"] = np.select(
        [
            x["range_bps"] <= range_q.get(0.25, np.inf),
            x["range_bps"] <= range_q.get(0.5, np.inf),
            x["range_bps"] <= range_q.get(0.75, np.inf),
            x["range_bps"] <= range_q.get(0.9, np.inf),
        ],
        ["range_le_25", "range_le_50", "range_le_75", "range_le_90"],
        default="range_gt_90",
    )
    x["p95_spread_flag"] = x["spread_cost_bps"] > spread_q.get(0.95, np.inf)
    x["p90_range_flag"] = x["range_bps"] > range_q.get(0.9, np.inf)
    # Late US/rollover-like bucket: known to be less liquid around day boundary.
    x["rollover_like"] = x["hour_utc"].isin([21, 22, 23, 0])
    return x


def normalize_context_table(path: Path, fallback: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    # Stage57A tables may be large; use them only if present/readable. Otherwise derive inline.
    if path.exists():
        try:
            ctx = pd.read_csv(path)
            time_col = "time_utc" if "time_utc" in ctx.columns else None
            if time_col is None:
                for c in ctx.columns:
                    if c.lower() in ("utc_time", "entry_time_utc", "datetime", "time"):
                        time_col = c
                        break
            if time_col:
                ctx["time_utc"] = pd.to_datetime(ctx[time_col], utc=True)
                needed = {"time_utc", "session", "spread_regime", "range_regime", "p95_spread_flag", "rollover_like"}
                missing = needed - set(ctx.columns)
                if not missing:
                    keep = [c for c in ctx.columns if c in needed or c in {"hour_utc", "weekday", "range_bps", "spread_cost_bps"}]
                    return ctx[keep].drop_duplicates("time_utc").sort_values("time_utc").reset_index(drop=True)
        except Exception:
            pass
    derived = add_derived_context(fallback, timeframe)
    return derived[["time_utc", "session", "spread_regime", "range_regime", "p95_spread_flag", "rollover_like", "hour_utc", "weekday", "range_bps", "spread_cost_bps"]]


def parse_candidate_id(cid: str) -> Optional[CandidateParams]:
    # Example: S51_VSQ_CW96_P30_B5_M3020_H12
    m = re.search(r"CW(\d+)_P(\d+(?:\.\d+)?)_B(\d+(?:\.\d+)?)_M30(\d+)_H(\d+)", cid)
    if not m:
        return None
    return CandidateParams(
        candidate_id=cid,
        cw=int(m.group(1)),
        pct=float(m.group(2)),
        buffer_bps=float(m.group(3)),
        m30_sma=int(m.group(4)),
        horizon_m5_bars=int(m.group(5)),
    )


def load_stage51_pass_candidates(path: Path, max_n: int) -> Tuple[List[CandidateParams], Dict[str, Any]]:
    meta: Dict[str, Any] = {"path": str(path), "found": path.exists(), "rows": 0, "pass_rows": 0, "parse_failures": []}
    if not path.exists():
        return [], meta
    df = pd.read_csv(path)
    meta["rows"] = int(len(df))
    if "status" in df.columns:
        pass_df = df[df["status"].astype(str).str.contains("PASS", na=False)].copy()
    else:
        pass_df = df.copy()
    meta["pass_rows"] = int(len(pass_df))
    if "candidate_id" not in pass_df.columns:
        return [], meta
    out: List[CandidateParams] = []
    for cid in pass_df["candidate_id"].astype(str).tolist():
        cp = parse_candidate_id(cid)
        if cp is None:
            meta["parse_failures"].append(cid)
            continue
        out.append(cp)
        if len(out) >= max_n:
            break
    return out, meta


def generate_stage51_signals(m15: pd.DataFrame, m30: pd.DataFrame, m5: pd.DataFrame, cp: CandidateParams, stress_cost_bps: float) -> pd.DataFrame:
    x = m15[["time_utc", "open", "high", "low", "close", "spread_cost_bps"]].copy()
    x["range_bps"] = (x["high"] - x["low"]) / x["close"].replace(0, np.nan) * 1e4
    x["prior_high"] = x["high"].shift(1)
    x["prior_low"] = x["low"].shift(1)
    x["prior_range_bps"] = x["range_bps"].shift(1)
    q = x["range_bps"].rolling(cp.cw, min_periods=max(10, cp.cw // 3)).quantile(cp.pct / 100.0).shift(1)
    x["compressed"] = x["prior_range_bps"] <= q
    long_break = x["close"] > x["prior_high"] * (1.0 + cp.buffer_bps / 1e4)
    short_break = x["close"] < x["prior_low"] * (1.0 - cp.buffer_bps / 1e4)
    x["direction"] = np.where(x["compressed"] & long_break, 1, np.where(x["compressed"] & short_break, -1, 0))
    sig = x[x["direction"] != 0].copy()
    if sig.empty:
        return pd.DataFrame()

    trend = m30[["time_utc", "close"]].copy()
    trend = trend.sort_values("time_utc")
    trend["m30_sma"] = trend["close"].rolling(cp.m30_sma, min_periods=max(5, cp.m30_sma // 2)).mean()
    trend["m30_trend"] = np.where(trend["close"] > trend["m30_sma"], 1, np.where(trend["close"] < trend["m30_sma"], -1, 0))
    sig = pd.merge_asof(sig.sort_values("time_utc"), trend[["time_utc", "m30_trend"]].dropna().sort_values("time_utc"), on="time_utc", direction="backward")
    sig = sig[sig["direction"] == sig["m30_trend"]].copy()
    if sig.empty:
        return pd.DataFrame()

    m5s = m5[["time_utc", "close", "spread_cost_bps"]].dropna().sort_values("time_utc").reset_index(drop=True)
    tvals = m5s["time_utc"].values.astype("datetime64[ns]")
    sig_times = sig["time_utc"].values.astype("datetime64[ns]")
    entry_idx = np.searchsorted(tvals, sig_times, side="right")
    exit_idx = entry_idx + cp.horizon_m5_bars
    ok = (entry_idx >= 0) & (exit_idx < len(m5s))
    if not ok.any():
        return pd.DataFrame()
    sig = sig.loc[ok].copy()
    entry_idx = entry_idx[ok]
    exit_idx = exit_idx[ok]
    entry = m5s.iloc[entry_idx].reset_index(drop=True)
    exit_ = m5s.iloc[exit_idx].reset_index(drop=True)
    sig = sig.reset_index(drop=True)
    sig["candidate_id"] = cp.candidate_id
    sig["entry_time_utc"] = entry["time_utc"].values
    sig["exit_time_utc"] = exit_["time_utc"].values
    sig["entry_price"] = entry["close"].values
    sig["exit_price"] = exit_["close"].values
    sig["entry_spread_cost_bps"] = entry["spread_cost_bps"].values
    sig["gross_bps"] = sig["direction"] * (sig["exit_price"] / sig["entry_price"] - 1.0) * 1e4
    sig["stress_bps"] = sig["gross_bps"] - stress_cost_bps
    sig["horizon_m5_bars"] = cp.horizon_m5_bars
    return sig[["candidate_id", "time_utc", "entry_time_utc", "exit_time_utc", "direction", "entry_price", "exit_price", "entry_spread_cost_bps", "gross_bps", "stress_bps", "horizon_m5_bars"]]


def apply_context(sig: pd.DataFrame, ctx_m15: pd.DataFrame) -> pd.DataFrame:
    if sig.empty:
        return sig
    sig = sig.sort_values("time_utc").copy()
    ctx = ctx_m15.sort_values("time_utc").copy()
    out = pd.merge_asof(sig, ctx, on="time_utc", direction="nearest", tolerance=pd.Timedelta("1min"))
    out["entry_date_utc"] = pd.to_datetime(out["entry_time_utc"], utc=True).dt.date.astype(str)
    out["entry_year"] = pd.to_datetime(out["entry_time_utc"], utc=True).dt.year
    return out


def filter_variants(df: pd.DataFrame) -> Iterable[Tuple[str, pd.DataFrame, Dict[str, Any]]]:
    # Shared context overlays. Each variant remains an audit candidate, not a promotion.
    masks: List[Tuple[str, pd.Series, Dict[str, Any]]] = []
    all_mask = pd.Series(True, index=df.index)
    masks.append(("CTX_ALL", all_mask, {"session_filter": "all", "spread_filter": "all", "range_filter": "all"}))
    if "session" in df.columns:
        masks.extend([
            ("CTX_NO_ASIA_LATEUS", ~df["session"].isin(["asia", "late_us"]), {"session_filter": "exclude_asia_late_us"}),
            ("CTX_LONDON_OVERLAP_NY", df["session"].isin(["london", "london_ny_overlap", "new_york"]), {"session_filter": "london_overlap_new_york"}),
            ("CTX_OVERLAP_NY", df["session"].isin(["london_ny_overlap", "new_york"]), {"session_filter": "overlap_new_york"}),
        ])
    if "spread_regime" in df.columns:
        masks.extend([
            ("CTX_SPREAD_LE90", df["spread_regime"].isin(["spread_le_50", "spread_le_75", "spread_le_90"]), {"spread_filter": "spread_le_90"}),
            ("CTX_SPREAD_LE75", df["spread_regime"].isin(["spread_le_50", "spread_le_75"]), {"spread_filter": "spread_le_75"}),
        ])
    if "rollover_like" in df.columns:
        masks.append(("CTX_NO_ROLLOVER", ~df["rollover_like"].fillna(False).astype(bool), {"rollover_filter": "exclude_rollover_like"}))
    if "range_regime" in df.columns:
        masks.extend([
            ("CTX_RANGE_GT50", df["range_regime"].isin(["range_le_75", "range_le_90", "range_gt_90"]), {"range_filter": "range_gt_50"}),
            ("CTX_RANGE_50_90", df["range_regime"].isin(["range_le_75", "range_le_90"]), {"range_filter": "range_50_to_90"}),
        ])
    # Single filters plus useful intersections with spread/session.
    seen = set()
    for name, mask, meta in masks:
        if name not in seen:
            seen.add(name)
            yield name, df[mask.fillna(False)].copy(), meta
    # Intersections to test context-aware thesis without an unbounded grid.
    def get_mask(n: str) -> Optional[pd.Series]:
        for name, mask, _ in masks:
            if name == n:
                return mask
        return None
    combos = [
        ("CTX_LON_OV_NY_SPREAD_LE90", ["CTX_LONDON_OVERLAP_NY", "CTX_SPREAD_LE90"]),
        ("CTX_NO_ASIA_LATEUS_SPREAD_LE90", ["CTX_NO_ASIA_LATEUS", "CTX_SPREAD_LE90"]),
        ("CTX_LON_OV_NY_NO_ROLLOVER", ["CTX_LONDON_OVERLAP_NY", "CTX_NO_ROLLOVER"]),
        ("CTX_LON_OV_NY_SPREAD_LE90_RANGE_GT50", ["CTX_LONDON_OVERLAP_NY", "CTX_SPREAD_LE90", "CTX_RANGE_GT50"]),
    ]
    for cname, parts in combos:
        mask = pd.Series(True, index=df.index)
        ok = True
        for part in parts:
            pm = get_mask(part)
            if pm is None:
                ok = False
                break
            mask = mask & pm.fillna(False)
        if ok and cname not in seen:
            seen.add(cname)
            yield cname, df[mask].copy(), {"combo_filter": "+".join(parts)}


def max_share(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    vc = series.value_counts(normalize=True)
    return float(vc.iloc[0]) if len(vc) else 0.0


def audit(df: pd.DataFrame, thresholds: AuditThresholds, stress_cost_bps: float) -> Dict[str, Any]:
    n = int(len(df))
    if n == 0:
        base = {"trade_count": 0, "status": NO_PASS_STATUS, "failures": "trade_count_lt_min"}
        return base
    d = df.sort_values("entry_time_utc").copy()
    split = int(math.floor(0.8 * n))
    is_df = d.iloc[:split]
    oos_df = d.iloc[split:]
    years = d.groupby("entry_year")["stress_bps"].mean() if "entry_year" in d.columns else pd.Series(dtype=float)
    pos_years = int((years > 0).sum()) if len(years) else 0
    neg_years = int((years < 0).sum()) if len(years) else 0
    worst_year = float(years.min()) if len(years) else None
    # Decluster by candidate+day+direction; keep first event in each cluster.
    decl = d.drop_duplicates(["candidate_id", "entry_date_utc", "direction"]).copy()
    metrics = {
        "trade_count": n,
        "oos_trade_count": int(len(oos_df)),
        "mean_stress_bps": float(d["stress_bps"].mean()),
        "median_stress_bps": float(d["stress_bps"].median()),
        "win_rate": float((d["stress_bps"] > 0).mean()),
        "t_stat": float(d["stress_bps"].mean() / (d["stress_bps"].std(ddof=1) / math.sqrt(n))) if n > 1 and d["stress_bps"].std(ddof=1) and not math.isnan(d["stress_bps"].std(ddof=1)) else 0.0,
        "is_mean_stress_bps": float(is_df["stress_bps"].mean()) if len(is_df) else None,
        "is_win_rate": float((is_df["stress_bps"] > 0).mean()) if len(is_df) else None,
        "oos_mean_stress_bps": float(oos_df["stress_bps"].mean()) if len(oos_df) else None,
        "oos_win_rate": float((oos_df["stress_bps"] > 0).mean()) if len(oos_df) else None,
        "positive_year_count": pos_years,
        "negative_year_count": neg_years,
        "worst_year_mean_stress_bps": worst_year,
        "cost_x15_mean_stress_bps": float(d["gross_bps"].mean() - stress_cost_bps * 1.5),
        "cost_x2_mean_stress_bps": float(d["gross_bps"].mean() - stress_cost_bps * 2.0),
        "declustered_trade_count": int(len(decl)),
        "declustered_mean_stress_bps": float(decl["stress_bps"].mean()) if len(decl) else None,
        "declustered_win_rate": float((decl["stress_bps"] > 0).mean()) if len(decl) else None,
        "max_direction_share": max_share(d["direction"]),
        "max_day_share": max_share(d["entry_date_utc"]),
        "first_entry_utc": str(pd.to_datetime(d["entry_time_utc"].min(), utc=True).isoformat().replace("+00:00", "Z")),
        "last_entry_utc": str(pd.to_datetime(d["entry_time_utc"].max(), utc=True).isoformat().replace("+00:00", "Z")),
        "span_days": float((pd.to_datetime(d["entry_time_utc"].max(), utc=True) - pd.to_datetime(d["entry_time_utc"].min(), utc=True)).total_seconds() / 86400.0),
    }
    failures = []
    checks = [
        ("trade_count_lt_min", metrics["trade_count"] >= thresholds.min_trade_count),
        ("oos_trade_count_lt_min", metrics["oos_trade_count"] >= thresholds.min_oos_trade_count),
        ("mean_stress_lt_min", metrics["mean_stress_bps"] >= thresholds.min_mean_stress_bps),
        ("median_stress_lt_min", metrics["median_stress_bps"] >= thresholds.min_median_stress_bps),
        ("win_rate_lt_min", metrics["win_rate"] >= thresholds.min_win_rate),
        ("oos_mean_stress_lt_min", (metrics["oos_mean_stress_bps"] is not None and metrics["oos_mean_stress_bps"] >= thresholds.min_oos_mean_stress_bps)),
        ("oos_win_rate_lt_min", (metrics["oos_win_rate"] is not None and metrics["oos_win_rate"] >= thresholds.min_oos_win_rate)),
        ("positive_years_lt_min", metrics["positive_year_count"] >= thresholds.min_positive_years),
        ("negative_years_gt_max", metrics["negative_year_count"] <= thresholds.max_negative_years),
        ("worst_year_lt_min", (metrics["worst_year_mean_stress_bps"] is not None and metrics["worst_year_mean_stress_bps"] >= thresholds.min_worst_year_mean_stress_bps)),
        ("cost_x2_mean_lt_min", metrics["cost_x2_mean_stress_bps"] >= thresholds.min_cost_x2_mean_stress_bps),
        ("max_direction_share_gt_max", metrics["max_direction_share"] <= thresholds.max_direction_share),
        ("max_day_share_gt_max", metrics["max_day_share"] <= thresholds.max_day_share),
        ("declustered_trade_count_lt_min", metrics["declustered_trade_count"] >= thresholds.min_declustered_trade_count),
        ("declustered_mean_lt_min", metrics["declustered_mean_stress_bps"] is not None and metrics["declustered_mean_stress_bps"] >= thresholds.min_declustered_mean_stress_bps),
        ("declustered_win_rate_lt_min", metrics["declustered_win_rate"] is not None and metrics["declustered_win_rate"] >= thresholds.min_declustered_win_rate),
    ]
    for name, passed in checks:
        if not passed:
            failures.append(name)
    metrics["status"] = PASS_STATUS if not failures else NO_PASS_STATUS
    metrics["failures"] = ";".join(failures)
    return metrics


def load_config(path: Path) -> Dict[str, Any]:
    default = {"thresholds": asdict(AuditThresholds()), "max_exported_candidates": 100}
    cfg = read_json(path, default) or default
    # Fill missing thresholds.
    t = asdict(AuditThresholds())
    t.update(cfg.get("thresholds", {}))
    cfg["thresholds"] = t
    cfg.setdefault("max_exported_candidates", 100)
    return cfg


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    out_dir = resolve(root, args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    db = resolve(root, args.db)
    cost_model_path = resolve(root, args.cost_model)
    stage51_path = resolve(root, args.stage51_candidates)
    m15_ctx_path = resolve(root, args.m15_context)
    m5_ctx_path = resolve(root, args.m5_context)
    config_path = resolve(root, args.config)
    cfg = load_config(config_path)
    thresholds = AuditThresholds(**cfg.get("thresholds", {}))
    costs = load_cost_model(cost_model_path)
    stress_cost = float(costs["stress_cost_bps"])

    checks: List[Dict[str, Any]] = []
    errors: List[str] = []
    try:
        m15 = load_bars(db, "M15")
        m30 = load_bars(db, "M30")
        m5 = load_bars(db, "M5")
        checks.append({"check": "broker_db_timeframes_loaded", "passed": True, "severity": "HIGH", "observed": {"M15": len(m15), "M30": len(m30), "M5": len(m5)}})
    except Exception as exc:
        checks.append({"check": "broker_db_timeframes_loaded", "passed": False, "severity": "HIGH", "observed": str(exc)})
        raise

    ctx_m15 = normalize_context_table(m15_ctx_path, m15, "M15")
    _ctx_m5 = normalize_context_table(m5_ctx_path, m5, "M5")
    checks.append({"check": "m15_context_available_or_derived", "passed": len(ctx_m15) > 0, "severity": "HIGH", "observed": len(ctx_m15)})
    checks.append({"check": "m5_context_available_or_derived", "passed": len(_ctx_m5) > 0, "severity": "MEDIUM", "observed": len(_ctx_m5)})

    candidates, cand_meta = load_stage51_pass_candidates(stage51_path, args.max_stage51_candidates)
    checks.append({"check": "stage51_pass_candidates_loaded", "passed": len(candidates) > 0, "severity": "HIGH", "observed": {"loaded": len(candidates), **cand_meta}})
    all_rows: List[Dict[str, Any]] = []
    event_samples: List[pd.DataFrame] = []
    per_candidate_signal_counts: Dict[str, int] = {}

    for cp in candidates:
        try:
            raw_sig = generate_stage51_signals(m15, m30, m5, cp, stress_cost)
            per_candidate_signal_counts[cp.candidate_id] = int(len(raw_sig))
            if raw_sig.empty:
                continue
            with_ctx = apply_context(raw_sig, ctx_m15)
            # Export only a bounded event sample.
            event_samples.append(with_ctx.head(50).copy())
            for variant_name, filtered, meta in filter_variants(with_ctx):
                metrics = audit(filtered, thresholds, stress_cost)
                row = {
                    "candidate_id": f"S58A_{cp.candidate_id}_{variant_name}",
                    "base_candidate_id": cp.candidate_id,
                    "context_variant": variant_name,
                    "cw": cp.cw,
                    "pct": cp.pct,
                    "buffer_bps": cp.buffer_bps,
                    "m30_sma": cp.m30_sma,
                    "horizon_m5_bars": cp.horizon_m5_bars,
                    "params": json.dumps(meta, sort_keys=True),
                    **metrics,
                }
                all_rows.append(row)
        except Exception as exc:
            errors.append(f"{cp.candidate_id}: {exc}")

    cand_df = pd.DataFrame(all_rows)
    if not cand_df.empty:
        # Sort pass candidates first, then by OOS and mean quality.
        cand_df["pass_rank"] = np.where(cand_df["status"] == PASS_STATUS, 0, 1)
        sort_cols = ["pass_rank", "oos_mean_stress_bps", "mean_stress_bps", "win_rate", "trade_count"]
        existing = [c for c in sort_cols if c in cand_df.columns]
        cand_df = cand_df.sort_values(existing, ascending=[True] + [False] * (len(existing) - 1)).drop(columns=["pass_rank"])
    pass_count = int((cand_df["status"] == PASS_STATUS).sum()) if not cand_df.empty and "status" in cand_df.columns else 0
    decision = "CONTEXT_AWARE_STAGE51_AUDIT_PASS_NEEDS_FORWARD_SHADOW_DESIGN_NO_PROMOTION" if pass_count > 0 else "CONTEXT_AWARE_STAGE51_AUDIT_COMPLETE_NO_PASS_NO_PROMOTION"
    next_step = "DESIGN_STAGE58B_CONTEXT_FORWARD_SHADOW_NO_PROMOTION" if pass_count > 0 else "ARCHIVE_CONTEXT_OVERLAY_OR_ADD_EXTERNAL_CONTEXT_NO_PROMOTION"

    candidates_path = out_dir / "stage58a_context_aware_stage51_regime_audit_candidates.csv"
    sample_path = out_dir / "stage58a_context_aware_stage51_regime_audit_event_sample.csv"
    if not cand_df.empty:
        cand_df.head(int(cfg.get("max_exported_candidates", 100))).to_csv(candidates_path, index=False)
    else:
        pd.DataFrame(columns=["candidate_id", "status", "failures"]).to_csv(candidates_path, index=False)
    if event_samples:
        sample = pd.concat(event_samples, ignore_index=True).head(500)
        sample.to_csv(sample_path, index=False)
    else:
        pd.DataFrame().to_csv(sample_path, index=False)

    family_summary = {
        "base_candidates_loaded": len(candidates),
        "context_audit_candidates": int(len(cand_df)),
        "hard_audit_pass_count": pass_count,
        "signal_counts_by_base_candidate": per_candidate_signal_counts,
        "errors": errors,
    }
    summary = {
        "stage": STAGE,
        "status": STATUS,
        "promotion": NO_GO,
        "EA": NO_GO,
        "paper_live": NO_GO,
        "live": NO_GO,
        "decision": decision,
        "next_allowed_step": next_step,
        "root": str(root),
        "inputs": {
            "db": str(db),
            "cost_model": str(cost_model_path),
            "stage51_candidates": str(stage51_path),
            "m15_context": str(m15_ctx_path),
            "m5_context": str(m5_ctx_path),
            "config": str(config_path),
        },
        "rows": {"M15": int(len(m15)), "M30": int(len(m30)), "M5": int(len(m5)), "M15_context": int(len(ctx_m15)), "M5_context": int(len(_ctx_m5))},
        "costs": costs,
        "stage51_candidates_meta": cand_meta,
        "audit_thresholds": asdict(thresholds),
        "summary": family_summary,
        "failed_checks": [c["check"] for c in checks if not c.get("passed")],
        "checks": checks,
        "outputs": {"candidates": str(candidates_path), "event_sample": str(sample_path)},
        "generated_utc": utcnow(),
    }
    write_json(out_dir / "stage58a_context_aware_stage51_regime_audit_summary.json", summary)

    report_lines = [
        "# Stage58A Context-Aware Stage51 Regime Audit",
        "",
        f"- status: `{STATUS}`",
        f"- decision: `{decision}`",
        f"- next_allowed_step: `{next_step}`",
        f"- promotion: `{NO_GO}`",
        f"- EA: `{NO_GO}`",
        f"- paper_live: `{NO_GO}`",
        f"- live: `{NO_GO}`",
        "",
        "## Inputs",
        f"- db: `{db}`",
        f"- cost_model: `{cost_model_path}`",
        f"- stage51_candidates: `{stage51_path}`",
        f"- M15 context: `{m15_ctx_path}`",
        f"- M5 context: `{m5_ctx_path}`",
        "",
        "## Audit summary",
        f"- base_candidates_loaded: `{len(candidates)}`",
        f"- context_audit_candidates: `{int(len(cand_df))}`",
        f"- hard_audit_pass_count: `{pass_count}`",
        f"- costs: `{costs}`",
        "",
        "## Signal counts by base Stage51 candidate",
    ]
    for cid, n in per_candidate_signal_counts.items():
        report_lines.append(f"- `{cid}`: `{n}`")
    report_lines += ["", "## Top context candidates"]
    if not cand_df.empty:
        for _, r in cand_df.head(20).iterrows():
            report_lines.append(
                f"- `{r.get('candidate_id')}` status=`{r.get('status')}` trades=`{r.get('trade_count')}` "
                f"mean=`{float(r.get('mean_stress_bps', 0)):.3f}` wr=`{float(r.get('win_rate', 0)):.3f}` "
                f"oos_mean=`{float(r.get('oos_mean_stress_bps', 0)) if pd.notna(r.get('oos_mean_stress_bps')) else None}` "
                f"failures=`{r.get('failures')}`"
            )
    else:
        report_lines.append("- none")
    report_lines += [
        "",
        "## Interpretation",
        "Stage58A is a historical context/regime overlay audit only. It does not use historical context results as forward evidence and does not authorize promotion, EA, paper-live, live trading, or order submission.",
    ]
    (out_dir / "stage58a_context_aware_stage51_regime_audit_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print(json.dumps({"stage": STAGE, "status": STATUS, "decision": decision, "hard_audit_pass_count": pass_count, "out": str(out_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
