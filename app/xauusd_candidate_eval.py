from __future__ import annotations

import re
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from app.xauusd_sqlite_store import connect, read_interval


def finalize_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["time_utc", "open", "high", "low", "close"])
    df = df.sort_values("time_utc").drop_duplicates(subset=["time_utc"], keep="last").reset_index(drop=True)
    df["date_utc"] = df["time_utc"].dt.date.astype(str)
    df["month_utc"] = df["time_utc"].dt.to_period("M").astype(str)
    df["hour_utc"] = df["time_utc"].dt.hour
    if "session_utc" not in df.columns or df["session_utc"].isna().all():
        hours = df["hour_utc"]
        df["session_utc"] = "other"
        df.loc[(hours >= 0) & (hours < 7), "session_utc"] = "asia"
        df.loc[(hours >= 7) & (hours < 13), "session_utc"] = "london"
        df.loc[(hours >= 13) & (hours < 17), "session_utc"] = "london_ny_overlap"
        df.loc[(hours >= 17) & (hours < 22), "session_utc"] = "new_york"
    return df


def read_interval_from_db(db_path: str, interval: str) -> pd.DataFrame:
    con = connect(db_path)
    try:
        df = read_interval(con, interval)
    finally:
        con.close()
    return finalize_df(df)


def nonoverlap_indices(entry_idx: np.ndarray, exit_idx: np.ndarray, cooldown_bars: int) -> np.ndarray:
    if len(entry_idx) == 0:
        return np.array([], dtype=int)

    order = np.lexsort((exit_idx, entry_idx))
    accepted = []
    next_allowed = -1

    for pos in order:
        e = int(entry_idx[pos])
        if e < next_allowed:
            continue
        accepted.append(int(pos))
        next_allowed = int(exit_idx[pos]) + int(cooldown_bars) + 1

    return np.array(accepted, dtype=int)


def sma_candidate_trades(
    df: pd.DataFrame,
    family: str,
    variant: str,
    sma_window: int,
    horizon_bars: int,
    min_distance_usd: float,
    cooldown_bars: int,
    cost_usd: float,
) -> pd.DataFrame:
    close = df["close"]
    sma = close.rolling(int(sma_window)).mean()
    diff = close - sma

    valid = diff.notna() & (diff.abs() >= float(min_distance_usd))
    valid.iloc[-int(horizon_bars):] = False

    entry = np.flatnonzero(valid.to_numpy())
    exit_ = entry + int(horizon_bars)
    direction = np.where(diff.iloc[entry].to_numpy(dtype=float) > 0, 1, -1).astype(int)

    keep = nonoverlap_indices(entry, exit_, int(cooldown_bars))
    entry, exit_, direction = entry[keep], exit_[keep], direction[keep]

    if len(entry) == 0:
        return pd.DataFrame()

    close_np = df["close"].to_numpy(dtype=float)
    raw = direction.astype(float) * (close_np[exit_] - close_np[entry])
    net = raw - float(cost_usd)

    return pd.DataFrame(
        {
            "family": family,
            "variant": variant,
            "entry_time_utc": df["time_utc"].iloc[entry].astype(str).to_numpy(),
            "exit_time_utc": df["time_utc"].iloc[exit_].astype(str).to_numpy(),
            "entry_month_utc": df["month_utc"].iloc[entry].to_numpy(),
            "direction": direction,
            "direction_label": np.where(direction > 0, "long", "short"),
            "entry_price": close_np[entry],
            "exit_price": close_np[exit_],
            "raw_usd": raw,
            "cost_usd": float(cost_usd),
            "net_usd": net,
        }
    )


def max_drawdown(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return 0.0
    equity = np.cumsum(values)
    peak = np.maximum.accumulate(equity)
    return float(np.min(equity - peak))


def profit_factor(values: np.ndarray) -> Optional[float]:
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return None
    wins = values[values > 0]
    losses = values[values <= 0]
    loss_abs = abs(float(np.sum(losses)))
    if loss_abs == 0:
        return None
    return float(np.sum(wins) / loss_abs)


def metrics(values: np.ndarray) -> Dict[str, Any]:
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return {
            "trade_count": 0,
            "total_net_usd": 0.0,
            "avg_net_usd": 0.0,
            "median_net_usd": 0.0,
            "win_rate": 0.0,
            "max_drawdown_usd": 0.0,
            "profit_factor": None,
        }

    return {
        "trade_count": int(values.size),
        "total_net_usd": float(np.sum(values)),
        "avg_net_usd": float(np.mean(values)),
        "median_net_usd": float(np.median(values)),
        "win_rate": float(np.mean(values > 0)),
        "best_net_usd": float(np.max(values)),
        "worst_net_usd": float(np.min(values)),
        "max_drawdown_usd": max_drawdown(values),
        "profit_factor": profit_factor(values),
    }


def directional_metrics(trades: pd.DataFrame) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for direction, g in trades.groupby("direction_label", sort=True):
        out[str(direction)] = metrics(g["net_usd"].to_numpy(dtype=float))
    return out


def fold_metrics(trades: pd.DataFrame, folds: int = 5) -> Dict[str, Any]:
    work = trades.sort_values("entry_time_utc").reset_index(drop=True)
    n = len(work)
    if n == 0:
        return {"folds": [], "positive_fold_count": 0, "positive_fold_ratio": 0.0}

    rows = []
    for i in range(folds):
        start = int(i * n / folds)
        end = int((i + 1) * n / folds)
        m = metrics(work.iloc[start:end]["net_usd"].to_numpy(dtype=float))
        m["fold"] = i + 1
        rows.append(m)

    positive = [r for r in rows if float(r["total_net_usd"]) > 0]
    return {
        "folds": rows,
        "positive_fold_count": int(len(positive)),
        "positive_fold_ratio": float(len(positive) / max(len(rows), 1)),
    }


def monthly_metrics(trades: pd.DataFrame) -> Dict[str, Any]:
    rows = []
    for month, g in trades.groupby("entry_month_utc", sort=True):
        m = metrics(g["net_usd"].to_numpy(dtype=float))
        m["month"] = str(month)
        rows.append(m)

    positive = [r for r in rows if float(r["total_net_usd"]) > 0]
    return {
        "month_count": int(len(rows)),
        "positive_month_count": int(len(positive)),
        "positive_month_ratio": float(len(positive) / max(len(rows), 1)),
        "months": rows,
    }


def cost_stress_metrics(trades: pd.DataFrame, multipliers: list[float]) -> list[Dict[str, Any]]:
    if trades.empty:
        return []
    raw = trades["raw_usd"].to_numpy(dtype=float)
    cost = trades["cost_usd"].to_numpy(dtype=float)
    rows = []
    for mult in multipliers:
        m = metrics(raw - cost * float(mult))
        m["cost_multiplier"] = float(mult)
        rows.append(m)
    return rows


def evaluate_fixed_candidate(df: pd.DataFrame, candidate_cfg: Dict[str, Any], cost_usd: float) -> Dict[str, Any]:
    family = str(candidate_cfg.get("family", "sma_trend_1h"))
    variant = str(candidate_cfg.get("variant", "sma10_h12_dist10_cool1"))

    if family != "sma_trend_1h":
        raise ValueError(f"Only sma_trend_1h fixed candidate is supported in Stage 3A, got {family!r}")

    trades = sma_candidate_trades(
        df=df,
        family=family,
        variant=variant,
        sma_window=int(candidate_cfg.get("sma_window", 10)),
        horizon_bars=int(candidate_cfg.get("horizon_bars", 12)),
        min_distance_usd=float(candidate_cfg.get("min_distance_usd", 10.0)),
        cooldown_bars=int(candidate_cfg.get("cooldown_bars", 1)),
        cost_usd=cost_usd,
    )

    if trades.empty:
        return {
            "candidate": {"family": family, "variant": variant},
            "base": metrics(np.array([], dtype=float)),
            "direction": {},
            "folds": {},
            "monthly": {},
            "cost_stress": [],
        }

    return {
        "candidate": {"family": family, "variant": variant},
        "base": metrics(trades["net_usd"].to_numpy(dtype=float)),
        "direction": directional_metrics(trades),
        "folds": fold_metrics(trades, folds=5),
        "monthly": monthly_metrics(trades),
        "cost_stress": cost_stress_metrics(trades, multipliers=[1.0, 2.0, 3.0, 4.0]),
        "data_window": {
            "first_trade_utc": str(trades["entry_time_utc"].iloc[0]),
            "last_trade_utc": str(trades["entry_time_utc"].iloc[-1]),
        },
    }
