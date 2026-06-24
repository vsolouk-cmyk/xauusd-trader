#!/usr/bin/env python3
"""
Stage51 Broker-Real Multi-Timeframe Volatility Squeeze Breakout Audit

Thesis:
    M15 volatility compression may precede short-horizon directional continuation
    when price breaks out of the compressed range and M30 trend confirmation is aligned.

This is a hard-audit style diagnostic only. It does not authorize promotion, EA,
paper-live, or live trading.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import pandas as pd
except Exception as exc:  # pragma: no cover
    raise SystemExit("pandas is required for Stage51 audit. Install with: pip install pandas") from exc


STAGE = "Stage51_BROKER_REAL_VOLATILITY_SQUEEZE_BREAKOUT_AUDIT"
PATCH = "STAGE51_VOLATILITY_SQUEEZE_BREAKOUT_HARD_AUDIT_NO_PROMOTION"
NO_GO = "NO_GO"

TIMEFRAME_REQUIRED = ["M5", "M15", "M30"]

GRID = {
    "compression_windows_m15": [48, 96, 192],
    "compression_percentiles": [20.0, 30.0],
    "breakout_buffers_bps": [0.0, 3.0, 5.0],
    "m30_sma_windows": [20, 40],
    "horizon_m5_bars": [6, 12, 24],
}


@dataclass
class Stats:
    count: int = 0
    mean_bps: float = float("nan")
    median_bps: float = float("nan")
    win_rate: float = float("nan")
    t_stat: float = float("nan")
    total_bps: float = float("nan")
    max_drawdown_bps: float = float("nan")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_float(x: Any, default: float = float("nan")) -> float:
    try:
        if x is None:
            return default
        v = float(x)
        if math.isfinite(v):
            return v
        return default
    except Exception:
        return default


def ensure_out(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)


def read_cost_model(path: Path) -> Dict[str, float]:
    with path.expanduser().open("r", encoding="utf-8") as f:
        data = json.load(f)
    usage = data.get("recommended_usage", {}) if isinstance(data, dict) else {}
    def pick(*keys: str, default: float) -> float:
        for k in keys:
            if isinstance(data, dict) and k in data:
                return safe_float(data[k], default)
            if isinstance(usage, dict) and k in usage:
                return safe_float(usage[k], default)
        return default
    return {
        "default_cost_bps": pick("recommended_cost_bps", "default_scan_cost_bps", default=3.0),
        "stress_cost_bps": pick("stress_cost_bps", "stress_scan_cost_bps", default=3.0),
        "extreme_cost_bps": pick("extreme_cost_bps", "extreme_spread_filter_reference_bps", default=3.1),
    }


def get_table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [str(r[1]) for r in rows]


def find_bars_table(conn: sqlite3.Connection) -> str:
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    preferred = ["amarkets_bars", "bars", "ohlc", "candles"]
    for name in preferred:
        if name in tables:
            return name
    for name in tables:
        cols = set(get_table_columns(conn, name))
        lower = {c.lower() for c in cols}
        if {"open", "high", "low", "close"}.issubset(lower) and ("timeframe" in lower or "tf" in lower):
            return name
    raise RuntimeError(f"No suitable OHLC table found. Tables={tables}")


def col_pick(cols: Sequence[str], aliases: Sequence[str]) -> Optional[str]:
    lower = {c.lower(): c for c in cols}
    for a in aliases:
        if a.lower() in lower:
            return lower[a.lower()]
    return None


def load_timeframe(conn: sqlite3.Connection, table: str, timeframe: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    cols = get_table_columns(conn, table)
    ts_col = col_pick(cols, ["time_utc", "utc_time", "timestamp", "ts", "datetime"])
    open_col = col_pick(cols, ["open", "o"])
    high_col = col_pick(cols, ["high", "h"])
    low_col = col_pick(cols, ["low", "l"])
    close_col = col_pick(cols, ["close", "c"])
    spread_col = col_pick(cols, ["spread_points", "spread", "spread_close"])
    tf_col = col_pick(cols, ["timeframe", "interval", "tf"])
    volume_col = col_pick(cols, ["tick_volume", "tickvol", "volume", "vol", "real_volume"])
    required = [ts_col, open_col, high_col, low_col, close_col]
    if any(c is None for c in required):
        raise RuntimeError(f"Table {table} missing required columns. cols={cols}")
    select_cols = [ts_col, open_col, high_col, low_col, close_col]
    if spread_col:
        select_cols.append(spread_col)
    if tf_col and tf_col not in select_cols:
        select_cols.append(tf_col)
    if volume_col and volume_col not in select_cols:
        select_cols.append(volume_col)
    select_expr = ", ".join([f'"{c}"' for c in select_cols])
    if tf_col:
        q = f"SELECT {select_expr} FROM {table} WHERE UPPER({tf_col}) = UPPER(?) ORDER BY {ts_col}"
        raw = pd.read_sql_query(q, conn, params=(timeframe,))
    else:
        q = f"SELECT {select_expr} FROM {table} ORDER BY {ts_col}"
        raw = pd.read_sql_query(q, conn)
    rename = {
        ts_col: "time_utc",
        open_col: "open",
        high_col: "high",
        low_col: "low",
        close_col: "close",
    }
    if spread_col:
        rename[spread_col] = "spread_points"
    if tf_col:
        rename[tf_col] = "timeframe"
    if volume_col:
        rename[volume_col] = "volume"
    df = raw.rename(columns=rename).copy()
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close", "spread_points"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    bad_rows = int(df[["time_utc", "open", "high", "low", "close"]].isna().any(axis=1).sum())
    df = df.dropna(subset=["time_utc", "open", "high", "low", "close"])
    df = df.sort_values("time_utc").drop_duplicates("time_utc", keep="last").reset_index(drop=True)
    if "spread_points" not in df.columns:
        df["spread_points"] = float("nan")
    meta = {
        "table": table,
        "mapping": {
            "ts": ts_col,
            "open": open_col,
            "high": high_col,
            "low": low_col,
            "close": close_col,
            "spread": spread_col,
            "timeframe": tf_col,
            "volume": volume_col,
        },
        "rows": int(len(df)),
        "bad_rows": bad_rows,
        "start_utc": df["time_utc"].min().isoformat().replace("+00:00", "Z") if len(df) else None,
        "end_utc": df["time_utc"].max().isoformat().replace("+00:00", "Z") if len(df) else None,
    }
    return df, meta


def stats(values: Sequence[float]) -> Stats:
    s = pd.Series(list(values), dtype="float64").dropna()
    n = int(len(s))
    if n == 0:
        return Stats()
    mean = float(s.mean())
    median = float(s.median())
    win_rate = float((s > 0).mean())
    std = float(s.std(ddof=1)) if n > 1 else float("nan")
    t_stat = float(mean / (std / math.sqrt(n))) if n > 1 and std > 0 else float("nan")
    total = float(s.sum())
    curve = s.cumsum()
    dd = curve - curve.cummax()
    max_dd = float(dd.min()) if n else float("nan")
    return Stats(n, mean, median, win_rate, t_stat, total, max_dd)


def chrono_folds(events: pd.DataFrame, n_folds: int = 5) -> List[Dict[str, Any]]:
    if events.empty:
        return []
    ev = events.sort_values("entry_time").reset_index(drop=True)
    folds: List[Dict[str, Any]] = []
    parts = pd.Series(range(len(ev))) * n_folds // max(1, len(ev))
    for fold_idx in range(n_folds):
        part = ev[parts == fold_idx]
        if part.empty:
            continue
        st = stats(part["stress_return_bps"].tolist())
        d = asdict(st)
        d["fold"] = fold_idx + 1
        d["start"] = part["entry_time"].min().isoformat().replace("+00:00", "Z")
        d["end"] = part["entry_time"].max().isoformat().replace("+00:00", "Z")
        folds.append(d)
    return folds


def direction_stats(events: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for direction, part in events.groupby("direction_label"):
        out[str(direction)] = asdict(stats(part["stress_return_bps"].tolist()))
    return out


def decluster(events: pd.DataFrame, min_gap_hours: float = 6.0) -> pd.DataFrame:
    if events.empty:
        return events
    keep = []
    last_ts = None
    min_gap = pd.Timedelta(hours=min_gap_hours)
    for idx, row in events.sort_values("entry_time").iterrows():
        ts = row["entry_time"]
        if last_ts is None or ts - last_ts >= min_gap:
            keep.append(idx)
            last_ts = ts
    return events.loc[keep].copy()


def add_features(m15: pd.DataFrame, m30: pd.DataFrame, point_size: float, costs: Dict[str, float]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    m15 = m15.copy()
    m30 = m30.copy()
    m15["range_bps"] = (m15["high"] - m15["low"]) / m15["close"].replace(0, pd.NA) * 10000.0
    m15["body_bps"] = (m15["close"] - m15["open"]) / m15["open"].replace(0, pd.NA) * 10000.0
    m15["spread_cost_bps"] = (m15["spread_points"] * point_size) / m15["close"].replace(0, pd.NA) * 10000.0
    # previous compression window values are shifted later per candidate to avoid look-ahead.
    m30["ret_bps"] = m30["close"].pct_change() * 10000.0
    return m15, m30


def nearest_prior_asof(left: pd.DataFrame, right: pd.DataFrame, right_cols: List[str], tolerance: str) -> pd.DataFrame:
    return pd.merge_asof(
        left.sort_values("time_utc"),
        right[["time_utc"] + right_cols].sort_values("time_utc"),
        on="time_utc",
        direction="backward",
        tolerance=pd.Timedelta(tolerance),
    )


def build_events_for_candidate(
    m5: pd.DataFrame,
    m15_base: pd.DataFrame,
    m30_base: pd.DataFrame,
    compression_window: int,
    compression_pct: float,
    breakout_buffer_bps: float,
    m30_sma_window: int,
    horizon: int,
    costs: Dict[str, float],
    point_size: float,
) -> pd.DataFrame:
    if len(m15_base) < compression_window + 10 or len(m5) < horizon + 10:
        return pd.DataFrame()
    m15 = m15_base.copy()
    # Strictly prior compression window: all shifted by one closed M15 bar.
    prev_range = m15["range_bps"].shift(1)
    m15["compression_threshold"] = prev_range.rolling(compression_window, min_periods=max(20, compression_window // 2)).quantile(compression_pct / 100.0)
    m15["prior_high"] = m15["high"].shift(1).rolling(compression_window, min_periods=max(20, compression_window // 2)).max()
    m15["prior_low"] = m15["low"].shift(1).rolling(compression_window, min_periods=max(20, compression_window // 2)).min()
    m15["prior_median_range"] = prev_range.rolling(compression_window, min_periods=max(20, compression_window // 2)).median()
    # Signal bar must come after a compressed previous bar and break prior range.
    prev_was_compressed = prev_range <= m15["compression_threshold"]
    up_buffer = m15["prior_high"] * (1.0 + breakout_buffer_bps / 10000.0)
    dn_buffer = m15["prior_low"] * (1.0 - breakout_buffer_bps / 10000.0)
    long_sig = prev_was_compressed & (m15["close"] > up_buffer)
    short_sig = prev_was_compressed & (m15["close"] < dn_buffer)
    m15["direction"] = 0
    m15.loc[long_sig, "direction"] = 1
    m15.loc[short_sig, "direction"] = -1
    sig = m15[m15["direction"] != 0].copy()
    if sig.empty:
        return pd.DataFrame()

    m30 = m30_base.copy()
    m30[f"sma_{m30_sma_window}"] = m30["close"].rolling(m30_sma_window, min_periods=max(5, m30_sma_window // 2)).mean()
    m30["m30_slope_bps"] = (m30[f"sma_{m30_sma_window}"] - m30[f"sma_{m30_sma_window}"].shift(1)) / m30[f"sma_{m30_sma_window}"].shift(1) * 10000.0
    m30_feat = m30[["time_utc", f"sma_{m30_sma_window}", "m30_slope_bps", "close"]].rename(columns={"close": "m30_close"})
    sig = nearest_prior_asof(sig, m30_feat, [f"sma_{m30_sma_window}", "m30_slope_bps", "m30_close"], "2h")
    # M30 must not contradict breakout direction.
    trend_ok = (
        ((sig["direction"] == 1) & (sig["m30_close"] >= sig[f"sma_{m30_sma_window}"]) & (sig["m30_slope_bps"] >= -1.0))
        | ((sig["direction"] == -1) & (sig["m30_close"] <= sig[f"sma_{m30_sma_window}"]) & (sig["m30_slope_bps"] <= 1.0))
    )
    sig = sig[trend_ok].copy()
    if sig.empty:
        return pd.DataFrame()

    m5 = m5.copy().sort_values("time_utc").reset_index(drop=True)
    m5["spread_cost_bps"] = (m5["spread_points"] * point_size) / m5["close"].replace(0, pd.NA) * 10000.0
    m5["future_close"] = m5["close"].shift(-horizon)
    m5_entry = m5[["time_utc", "close", "future_close", "spread_points", "spread_cost_bps"]].rename(
        columns={"time_utc": "entry_time", "close": "entry_close", "spread_points": "entry_spread_points", "spread_cost_bps": "entry_spread_cost_bps"}
    )
    sig = sig.rename(columns={"time_utc": "signal_time"})
    sig["entry_time"] = sig["signal_time"] + pd.Timedelta(minutes=5)
    ev = pd.merge_asof(
        sig.sort_values("entry_time"),
        m5_entry.sort_values("entry_time"),
        on="entry_time",
        direction="forward",
        tolerance=pd.Timedelta("10min"),
    )
    ev = ev.dropna(subset=["entry_close", "future_close", "entry_spread_cost_bps"])
    ev = ev[ev["entry_spread_cost_bps"] <= costs["extreme_cost_bps"]].copy()
    if ev.empty:
        return pd.DataFrame()
    gross = ev["direction"] * (ev["future_close"] - ev["entry_close"]) / ev["entry_close"] * 10000.0
    ev["gross_return_bps"] = gross
    ev["stress_return_bps"] = ev["gross_return_bps"] - costs["stress_cost_bps"]
    ev["cost_x1_5_return_bps"] = ev["gross_return_bps"] - costs["stress_cost_bps"] * 1.5
    ev["cost_x2_return_bps"] = ev["gross_return_bps"] - costs["stress_cost_bps"] * 2.0
    ev["direction_label"] = ev["direction"].map({1: "LONG", -1: "SHORT"})
    ev["year"] = ev["entry_time"].dt.year.astype(int)
    ev["month"] = ev["entry_time"].dt.strftime("%Y-%m")
    ev["exit_time"] = ev["entry_time"] + pd.Timedelta(minutes=5 * horizon)
    return ev


def evaluate_candidate(candidate_id: str, events: pd.DataFrame) -> Dict[str, Any]:
    if events.empty:
        return {"candidate_id": candidate_id, "trade_count": 0, "decision": "NO_TRADES", "failure_reasons": ["no_trades"]}
    ev = events.sort_values("entry_time").reset_index(drop=True)
    n = len(ev)
    split = max(1, int(n * 0.8))
    is_ev = ev.iloc[:split].copy()
    oos_ev = ev.iloc[split:].copy()
    s = stats(ev["stress_return_bps"].tolist())
    is_s = stats(is_ev["stress_return_bps"].tolist())
    oos_s = stats(oos_ev["stress_return_bps"].tolist())
    x15_s = stats(ev["cost_x1_5_return_bps"].tolist())
    x2_s = stats(ev["cost_x2_return_bps"].tolist())
    folds = chrono_folds(ev, 5)
    worst_fold_mean = min([f["mean_bps"] for f in folds if f.get("count", 0) > 0], default=float("nan"))
    y = ev.groupby("year")["stress_return_bps"].sum()
    positive_year_count = int((y > 0).sum())
    negative_year_count = int((y <= 0).sum())
    max_year_share = float(ev.groupby("year").size().max() / n) if n else float("nan")
    max_month_share = float(ev.groupby("month").size().max() / n) if n else float("nan")
    decl = decluster(ev)
    decl_s = stats(decl["stress_return_bps"].tolist())
    dir_stats = direction_stats(ev)
    failures: List[str] = []
    if n < 100:
        failures.append("trade_count_lt_100")
    if not (s.mean_bps > 0):
        failures.append("mean_not_positive")
    if not (s.win_rate >= 0.52):
        failures.append("win_rate_lt_52pct")
    if not (is_s.mean_bps > 0):
        failures.append("is_mean_not_positive")
    if not (oos_s.mean_bps > 0):
        failures.append("oos_mean_not_positive")
    if not (oos_s.win_rate >= 0.52):
        failures.append("oos_win_rate_lt_52pct")
    if positive_year_count < 4:
        failures.append("positive_year_count_lt_4")
    if negative_year_count > 1:
        failures.append("negative_year_count_gt_1")
    if not (worst_fold_mean > 0):
        failures.append("worst_chrono_fold_not_positive")
    if not (x15_s.mean_bps > 0):
        failures.append("cost_x1_5_mean_not_positive")
    if not (x2_s.mean_bps > 0):
        failures.append("cost_x2_mean_not_positive")
    if not (decl_s.mean_bps > 0):
        failures.append("declustered_mean_not_positive")
    if not (decl_s.win_rate >= 0.52):
        failures.append("declustered_win_rate_lt_52pct")
    for dlabel in ["LONG", "SHORT"]:
        ds = dir_stats.get(dlabel)
        if ds and ds.get("count", 0) >= 50 and not (ds.get("mean_bps", float("nan")) > 0):
            failures.append(f"{dlabel.lower()}_direction_mean_not_positive")
    decision = "HARD_AUDIT_PASS_NEEDS_FORWARD_SHADOW_DESIGN" if not failures else "HARD_AUDIT_NO_PASS"
    out = {
        "candidate_id": candidate_id,
        "trade_count": n,
        **asdict(s),
        "is_count": is_s.count,
        "is_mean_bps": is_s.mean_bps,
        "is_win_rate": is_s.win_rate,
        "oos_count": oos_s.count,
        "oos_mean_bps": oos_s.mean_bps,
        "oos_win_rate": oos_s.win_rate,
        "positive_year_count": positive_year_count,
        "negative_year_count": negative_year_count,
        "max_year_share": max_year_share,
        "max_month_share": max_month_share,
        "worst_fold_mean_bps": worst_fold_mean,
        "cost_x1_5_mean_bps": x15_s.mean_bps,
        "cost_x2_mean_bps": x2_s.mean_bps,
        "declustered_count": decl_s.count,
        "declustered_mean_bps": decl_s.mean_bps,
        "declustered_win_rate": decl_s.win_rate,
        "direction_stats": dir_stats,
        "folds": folds,
        "decision": decision,
        "failure_reasons": failures,
    }
    return out


def candidate_sort_key(c: Dict[str, Any]) -> Tuple[float, float, float]:
    return (
        safe_float(c.get("oos_mean_bps"), -9999),
        safe_float(c.get("mean_bps"), -9999),
        safe_float(c.get("win_rate"), -9999),
    )


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    flat_rows: List[Dict[str, Any]] = []
    for r in rows:
        fr = {}
        for k, v in r.items():
            if isinstance(v, (dict, list)):
                fr[k] = json.dumps(v, ensure_ascii=False)
            else:
                fr[k] = v
        flat_rows.append(fr)
    keys = list(flat_rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(flat_rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage51 volatility squeeze breakout hard-audit diagnostic")
    ap.add_argument("--root", default=".", help="Repo root")
    ap.add_argument("--db", default="data/broker_normalized/amarkets_multitf.sqlite")
    ap.add_argument("--cost-model", default="reports/stage48f/stage48f_cost_model.json")
    ap.add_argument("--point-size", type=float, default=0.01)
    ap.add_argument("--out", default="reports/stage51_volatility_squeeze")
    ap.add_argument("--event-sample", type=int, default=500)
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    db_path = (root / args.db).resolve() if not Path(args.db).is_absolute() else Path(args.db).expanduser().resolve()
    cm_path = (root / args.cost_model).resolve() if not Path(args.cost_model).is_absolute() else Path(args.cost_model).expanduser().resolve()
    out = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out).expanduser().resolve()
    ensure_out(out)

    costs = read_cost_model(cm_path)
    with sqlite3.connect(str(db_path)) as conn:
        table = find_bars_table(conn)
        m5, m5_meta = load_timeframe(conn, table, "M5")
        m15, m15_meta = load_timeframe(conn, table, "M15")
        m30, m30_meta = load_timeframe(conn, table, "M30")

    m15, m30 = add_features(m15, m30, args.point_size, costs)
    results: List[Dict[str, Any]] = []
    all_events_sample: List[pd.DataFrame] = []
    for cw in GRID["compression_windows_m15"]:
        for cp in GRID["compression_percentiles"]:
            for bb in GRID["breakout_buffers_bps"]:
                for m30w in GRID["m30_sma_windows"]:
                    for hz in GRID["horizon_m5_bars"]:
                        cid = f"S51_VSQ_CW{cw}_P{int(cp)}_B{int(bb)}_M30{m30w}_H{hz}"
                        ev = build_events_for_candidate(m5, m15, m30, cw, cp, bb, m30w, hz, costs, args.point_size)
                        res = evaluate_candidate(cid, ev)
                        res.update({
                            "compression_window_m15": cw,
                            "compression_percentile": cp,
                            "breakout_buffer_bps": bb,
                            "m30_sma_window": m30w,
                            "horizon_m5_bars": hz,
                            "stress_cost_bps": costs["stress_cost_bps"],
                            "extreme_spread_gate_bps": costs["extreme_cost_bps"],
                        })
                        results.append(res)
                        if len(all_events_sample) < 20 and not ev.empty:
                            ev2 = ev.head(max(1, args.event_sample // 20)).copy()
                            ev2["candidate_id"] = cid
                            all_events_sample.append(ev2)
    results_sorted = sorted(results, key=candidate_sort_key, reverse=True)
    pass_count = sum(1 for r in results_sorted if r.get("decision") == "HARD_AUDIT_PASS_NEEDS_FORWARD_SHADOW_DESIGN")
    status = "VOLATILITY_SQUEEZE_HARD_AUDIT_PASS_NEEDS_FORWARD_SHADOW_NO_PROMOTION" if pass_count else "VOLATILITY_SQUEEZE_HARD_AUDIT_COMPLETE_NO_PASS_NO_PROMOTION"
    next_allowed = "FORWARD_SHADOW_DESIGN_NO_PROMOTION" if pass_count else "ARCHIVE_OR_REDESIGN_THESIS_NO_PROMOTION"

    candidate_path = out / "stage51_volatility_squeeze_breakout_candidates.csv"
    write_csv(candidate_path, results_sorted)
    event_path = out / "stage51_volatility_squeeze_breakout_event_sample.csv"
    if all_events_sample:
        evs = pd.concat(all_events_sample, ignore_index=True)
        cols = [c for c in ["candidate_id", "signal_time", "entry_time", "exit_time", "direction_label", "entry_close", "future_close", "gross_return_bps", "stress_return_bps", "entry_spread_cost_bps", "range_bps", "prior_median_range"] if c in evs.columns]
        evs[cols].head(args.event_sample).to_csv(event_path, index=False)
    else:
        event_path.write_text("", encoding="utf-8")

    summary = {
        "stage": STAGE,
        "patch": PATCH,
        "status": status,
        "promotion": NO_GO,
        "EA": NO_GO,
        "paper_live": NO_GO,
        "live": NO_GO,
        "next_allowed_step": next_allowed,
        "db": str(db_path),
        "cost_model": str(cm_path),
        "rows": {"M5": len(m5), "M15": len(m15), "M30": len(m30)},
        "m5_meta": m5_meta,
        "m15_meta": m15_meta,
        "m30_meta": m30_meta,
        "costs": costs,
        "grid": GRID,
        "grid_candidate_count": len(results_sorted),
        "hard_audit_pass_count": pass_count,
        "top_candidates": results_sorted[:10],
        "generated_utc": utc_now_iso(),
    }
    with (out / "stage51_volatility_squeeze_breakout_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

    lines = [
        "# Stage51 Broker-Real Volatility Squeeze Breakout Hard Audit",
        "",
        f"- status: `{status}`",
        f"- next_allowed_step: `{next_allowed}`",
        "- promotion: `NO_GO`",
        "- EA: `NO_GO`",
        "- paper_live: `NO_GO`",
        "- live: `NO_GO`",
        "",
        "## Thesis",
        "",
        "M15 volatility compression may precede short-horizon directional continuation when price breaks out of the compressed range and M30 trend confirmation is aligned. This is not a session open-range thesis, not H1 expansion persistence, and not a liquidity-sweep reversal rescue.",
        "",
        "## Inputs",
        "",
        f"- M5 rows: `{len(m5)}`",
        f"- M15 rows: `{len(m15)}`",
        f"- M30 rows: `{len(m30)}`",
        f"- stress_cost_bps: `{costs['stress_cost_bps']:.4f}`",
        f"- extreme_spread_gate_bps: `{costs['extreme_cost_bps']:.4f}`",
        "",
        "## Result",
        "",
        f"- grid_candidate_count: `{len(results_sorted)}`",
        f"- hard_audit_pass_count: `{pass_count}`",
        "",
        "## Top candidates",
    ]
    for r in results_sorted[:10]:
        lines.append(
            f"- `{r.get('candidate_id')}` trades=`{r.get('trade_count')}` mean=`{safe_float(r.get('mean_bps')):.4f}` "
            f"oos_mean=`{safe_float(r.get('oos_mean_bps')):.4f}` decision=`{r.get('decision')}` "
            f"notes=`{';'.join(r.get('failure_reasons', []))}`"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "This is a broker-real hard-audit diagnostic only. Passing it would still not authorize EA, paper-live, or live trading; it would only justify a controlled forward-shadow design package.",
    ]
    (out / "stage51_volatility_squeeze_breakout_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"stage": STAGE, "status": status, "hard_audit_pass_count": pass_count, "out": str(out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
