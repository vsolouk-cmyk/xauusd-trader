from __future__ import annotations

import argparse
import itertools
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import yaml

from app.xauusd_sqlite_store import connect, read_interval


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def latest_csv_for_interval(data_dir: Path, interval: str) -> Path:
    files = sorted(data_dir.glob("normalized_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files:
        try:
            head = pd.read_csv(path, nrows=5)
        except Exception:
            continue
        if "interval" in head.columns and len(head) > 0 and str(head["interval"].iloc[0]) == interval:
            return path
    raise FileNotFoundError(f"No normalized CSV found for interval={interval!r} in {data_dir}")


def finalize_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)
    df = df.dropna(subset=["time_utc", "open", "high", "low", "close"])
    df = df.sort_values("time_utc").drop_duplicates(subset=["time_utc"], keep="last").reset_index(drop=True)
    df["date_utc"] = df["time_utc"].dt.date.astype(str)
    df["hour_utc"] = df["time_utc"].dt.hour
    if "session_utc" not in df.columns or df["session_utc"].isna().all():
        hours = df["hour_utc"]
        df["session_utc"] = "other"
        df.loc[(hours >= 0) & (hours < 7), "session_utc"] = "asia"
        df.loc[(hours >= 7) & (hours < 13), "session_utc"] = "london"
        df.loc[(hours >= 13) & (hours < 17), "session_utc"] = "london_ny_overlap"
        df.loc[(hours >= 17) & (hours < 22), "session_utc"] = "new_york"
    return df


def load_interval_df(data_dir: Path, interval: str, db_path: Optional[str] = None) -> Tuple[str, pd.DataFrame]:
    if db_path:
        con = connect(db_path)
        try:
            df = read_interval(con, interval)
        finally:
            con.close()
        if df.empty:
            raise FileNotFoundError(f"No SQLite rows found for interval={interval!r} in {db_path}")
        return f"sqlite:{db_path}:{interval}", finalize_df(df)

    path = latest_csv_for_interval(data_dir, interval)
    df = pd.read_csv(path)
    return str(path), finalize_df(df)


def nonoverlap_indices(entry_idx: np.ndarray, exit_idx: np.ndarray, cooldown_bars: int) -> np.ndarray:
    if len(entry_idx) == 0:
        return np.array([], dtype=int)

    order = np.lexsort((exit_idx, entry_idx))
    accepted_positions: List[int] = []
    next_allowed = -1

    for pos in order:
        e = int(entry_idx[pos])
        if e < next_allowed:
            continue
        accepted_positions.append(int(pos))
        next_allowed = int(exit_idx[pos]) + int(cooldown_bars) + 1

    return np.array(accepted_positions, dtype=int)


def make_trade_frame(
    df: pd.DataFrame,
    family: str,
    variant: str,
    interval: str,
    entry_idx: np.ndarray,
    exit_idx: np.ndarray,
    direction: np.ndarray,
    reason: str,
    cost_usd: float,
    save_full: bool = False,
) -> tuple[np.ndarray, np.ndarray, Optional[pd.DataFrame]]:
    if len(entry_idx) == 0:
        return np.array([], dtype=float), np.array([], dtype=float), None

    close = df["close"].to_numpy(dtype=float)
    raw = direction.astype(float) * (close[exit_idx] - close[entry_idx])
    net = raw - float(cost_usd)

    if not save_full:
        return raw, net, None

    times = df["time_utc"].astype(str).to_numpy()
    trade_df = pd.DataFrame(
        {
            "family": family,
            "variant": variant,
            "interval": interval,
            "entry_idx": entry_idx.astype(int),
            "exit_idx": exit_idx.astype(int),
            "entry_time_utc": times[entry_idx],
            "exit_time_utc": times[exit_idx],
            "direction": direction.astype(int),
            "direction_label": np.where(direction > 0, "long", "short"),
            "entry_price": close[entry_idx],
            "exit_price": close[exit_idx],
            "raw_usd": raw,
            "cost_usd": float(cost_usd),
            "net_usd": net,
            "reason": reason,
        }
    )
    return raw, net, trade_df


def gen_sma_signal_arrays(
    df: pd.DataFrame,
    sma_window: int,
    horizon: int,
    min_distance: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, str]:
    close = df["close"]
    sma = close.rolling(int(sma_window)).mean()
    diff = close - sma

    valid = diff.notna() & (diff.abs() >= float(min_distance))
    valid.iloc[-int(horizon):] = False

    entry_idx = np.flatnonzero(valid.to_numpy())
    exit_idx = entry_idx + int(horizon)
    direction = np.where(diff.iloc[entry_idx].to_numpy(dtype=float) > 0, 1, -1).astype(int)
    reason = f"close_vs_sma{sma_window}_dist{min_distance:g}"
    return entry_idx.astype(int), exit_idx.astype(int), direction, reason


def gen_session_momentum_arrays(
    df: pd.DataFrame,
    lookback: int,
    horizon: int,
    min_move: float,
    sessions: Iterable[str],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, str]:
    close = df["close"]
    move = close - close.shift(int(lookback))
    session_ok = df["session_utc"].isin(set(sessions))

    valid = move.notna() & session_ok & (move.abs() >= float(min_move))
    valid.iloc[-int(horizon):] = False

    entry_idx = np.flatnonzero(valid.to_numpy())
    exit_idx = entry_idx + int(horizon)
    direction = np.where(move.iloc[entry_idx].to_numpy(dtype=float) > 0, 1, -1).astype(int)
    reason = f"lookback_momentum_lb{lookback}_move{min_move:g}"
    return entry_idx.astype(int), exit_idx.astype(int), direction, reason


def gen_range_expansion_arrays(
    df: pd.DataFrame,
    avg_range_window: int,
    multiplier: float,
    horizon: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, str]:
    bar_range = df["high"] - df["low"]
    avg_range = bar_range.rolling(int(avg_range_window)).mean()
    body = df["close"] - df["open"]

    valid = avg_range.notna() & (avg_range > 0) & (bar_range >= float(multiplier) * avg_range) & (body != 0)
    valid.iloc[-int(horizon):] = False

    entry_idx = np.flatnonzero(valid.to_numpy())
    exit_idx = entry_idx + int(horizon)
    direction = np.where(body.iloc[entry_idx].to_numpy(dtype=float) > 0, 1, -1).astype(int)
    reason = f"range_expansion_w{avg_range_window}_x{multiplier:g}"
    return entry_idx.astype(int), exit_idx.astype(int), direction, reason


def max_drawdown(values: np.ndarray) -> float:
    if values.size == 0:
        return 0.0
    equity = np.cumsum(values)
    peak = np.maximum.accumulate(equity)
    return float(np.min(equity - peak))


def profit_factor(values: np.ndarray) -> Optional[float]:
    if values.size == 0:
        return None
    wins = values[values > 0]
    losses = values[values <= 0]
    loss_abs = abs(float(np.sum(losses)))
    if loss_abs == 0:
        return None
    return float(np.sum(wins) / loss_abs)


def remove_top_k(values: np.ndarray, k: int) -> np.ndarray:
    if values.size == 0 or k <= 0:
        return values
    if values.size <= k:
        return np.array([], dtype=float)
    remove_idx = np.argpartition(values, -k)[-k:]
    mask = np.ones(values.size, dtype=bool)
    mask[remove_idx] = False
    return values[mask]


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


def evaluate_variant(
    family: str,
    variant: str,
    raw: np.ndarray,
    net: np.ndarray,
    cost_usd: float,
    train_fraction: float,
    decision_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    split_idx = int(net.size * float(train_fraction))

    base = metrics(net)
    train = metrics(net[:split_idx])
    test = metrics(net[split_idx:])
    remove_top5 = metrics(remove_top_k(net, 5))
    cost_x2 = metrics(raw - float(cost_usd) * 2.0)

    pf = base.get("profit_factor")
    checks = {
        "min_trades": int(base["trade_count"]) >= int(decision_cfg.get("min_trades", 50)),
        "min_test_trades": int(test["trade_count"]) >= int(decision_cfg.get("min_test_trades", 20)),
        "train_positive": float(train["total_net_usd"]) > 0,
        "test_positive": float(test["total_net_usd"]) > 0,
        "remove_top_5_positive": float(remove_top5["total_net_usd"]) > 0,
        "cost_x2_positive": float(cost_x2["total_net_usd"]) > 0,
        "profit_factor_min": pf is not None and float(pf) >= float(decision_cfg.get("require_profit_factor_min", 1.05)),
    }

    robust = all(checks.values())
    reason = "robust_grid_candidate" if robust else "failed_checks:" + ",".join(k for k, v in checks.items() if not v)

    return {
        "family": family,
        "variant": variant,
        "robust_grid_candidate": bool(robust),
        "reason": reason,
        "checks": checks,
        "base": base,
        "train": train,
        "test": test,
        "remove_top_5": remove_top5,
        "cost_x2": cost_x2,
    }


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.replace(path)


def write_markdown(path: Path, payload: Dict[str, Any]) -> None:
    lines: List[str] = []
    lines.append("# XAUUSD Stage 2D Baseline Grid Lab")
    lines.append("")
    lines.append(f"- Generated at UTC: `{payload['generated_at_utc']}`")
    lines.append(f"- Decision: `{payload['decision']['status']}`")
    lines.append(f"- Reason: `{payload['decision']['reason']}`")
    lines.append(f"- Data source: `{payload['data_source_mode']}`")
    lines.append(f"- Runtime seconds: `{payload['runtime_seconds']}`")
    lines.append(f"- Total variants: `{payload['variant_count']}`")
    lines.append(f"- Robust candidates: `{payload['decision']['robust_candidate_count']}`")
    lines.append("")
    lines.append("| Family | Variant | Robust | Reason | Trades | Train total | Test total | Total net | PF | Remove top5 total | Cost x2 total |")
    lines.append("|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|")
    for row in payload["top_variants"]:
        base, train, test = row["base"], row["train"], row["test"]
        pf = base.get("profit_factor")
        lines.append(
            "| {family} | {variant} | {robust} | {reason} | {trades} | {train:.4f} | {test:.4f} | {total:.4f} | {pf} | {r5:.4f} | {cx2:.4f} |".format(
                family=row["family"],
                variant=row["variant"],
                robust=row["robust_grid_candidate"],
                reason=row["reason"],
                trades=base["trade_count"],
                train=train["total_net_usd"],
                test=test["total_net_usd"],
                total=base["total_net_usd"],
                pf="n/a" if pf is None else f"{float(pf):.3f}",
                r5=row["remove_top_5"]["total_net_usd"],
                cx2=row["cost_x2"]["total_net_usd"],
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    started = time.perf_counter()

    parser = argparse.ArgumentParser(description="Stage 2D fast baseline grid lab with train/test split and robustness checks.")
    parser.add_argument("--config", default="configs/stage2d.yaml")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--data-db", default=None)
    parser.add_argument("--report-dir", default=None)
    parser.add_argument("--save-full-trades", action="store_true")
    args = parser.parse_args()

    cfg = load_yaml(Path(args.config))
    data_dir = Path(args.data_dir or cfg.get("data_dir", "data/normalized"))
    data_db = args.data_db if args.data_db is not None else cfg.get("data_db")
    report_dir = Path(args.report_dir or cfg.get("report_dir", "data/reports"))
    trades_dir = Path(cfg.get("trades_dir", "data/reports/stage2d_trades"))
    output_cfg = cfg.get("output", {}) or {}
    save_full_trades = bool(args.save_full_trades or output_cfg.get("save_full_trades", False))

    report_dir.mkdir(parents=True, exist_ok=True)
    trades_dir.mkdir(parents=True, exist_ok=True)

    cost_cfg = cfg.get("cost_model", {}) or {}
    cost_usd = float(
        cost_cfg.get(
            "total_roundtrip_cost_usd",
            float(cost_cfg.get("assumed_spread_usd", 0.30)) + float(cost_cfg.get("assumed_slippage_usd", 0.05)),
        )
    )
    train_fraction = float((cfg.get("split", {}) or {}).get("train_fraction", 0.60))
    decision_cfg = cfg.get("decision", {}) or {}
    families = cfg.get("families", {}) or {}

    required_intervals = sorted({str(f.get("interval")) for f in families.values() if f.get("enabled", True)})
    data_by_interval: Dict[str, pd.DataFrame] = {}
    data_files: Dict[str, str] = {}
    for interval in required_intervals:
        source, df = load_interval_df(data_dir, interval, db_path=data_db)
        data_by_interval[interval] = df
        data_files[interval] = source

    all_trade_frames: List[pd.DataFrame] = []
    evaluations: List[Dict[str, Any]] = []

    f = families.get("sma_trend_1h", {})
    if f.get("enabled", True):
        interval = str(f.get("interval", "1h"))
        df = data_by_interval[interval]
        family = "sma_trend_1h"
        for sma_window, horizon, cooldown, min_distance in itertools.product(
            f.get("sma_windows", [20]),
            f.get("horizon_bars", [3]),
            f.get("cooldown_bars", [1]),
            f.get("min_distance_usd", [0.0]),
        ):
            entry, exit_, direction, reason = gen_sma_signal_arrays(df, int(sma_window), int(horizon), float(min_distance))
            keep = nonoverlap_indices(entry, exit_, int(cooldown))
            if keep.size == 0:
                continue
            entry, exit_, direction = entry[keep], exit_[keep], direction[keep]
            variant = f"sma{sma_window}_h{horizon}_dist{float(min_distance):g}_cool{cooldown}"
            raw, net, trade_frame = make_trade_frame(df, family, variant, interval, entry, exit_, direction, reason, cost_usd, save_full_trades)
            evaluations.append(evaluate_variant(family, variant, raw, net, cost_usd, train_fraction, decision_cfg))
            if trade_frame is not None:
                all_trade_frames.append(trade_frame)

    f = families.get("session_momentum_15min", {})
    if f.get("enabled", True):
        interval = str(f.get("interval", "15min"))
        df = data_by_interval[interval]
        family = "session_momentum_15min"
        for lookback, horizon, cooldown, min_move in itertools.product(
            f.get("lookback_bars", [1]),
            f.get("horizon_bars", [4]),
            f.get("cooldown_bars", [1]),
            f.get("min_move_usd", [0.0]),
        ):
            entry, exit_, direction, reason = gen_session_momentum_arrays(
                df,
                int(lookback),
                int(horizon),
                float(min_move),
                f.get("sessions", ["london", "london_ny_overlap", "new_york"]),
            )
            keep = nonoverlap_indices(entry, exit_, int(cooldown))
            if keep.size == 0:
                continue
            entry, exit_, direction = entry[keep], exit_[keep], direction[keep]
            variant = f"lb{lookback}_h{horizon}_move{float(min_move):g}_cool{cooldown}"
            raw, net, trade_frame = make_trade_frame(df, family, variant, interval, entry, exit_, direction, reason, cost_usd, save_full_trades)
            evaluations.append(evaluate_variant(family, variant, raw, net, cost_usd, train_fraction, decision_cfg))
            if trade_frame is not None:
                all_trade_frames.append(trade_frame)

    f = families.get("range_expansion_15min", {})
    if f.get("enabled", True):
        interval = str(f.get("interval", "15min"))
        df = data_by_interval[interval]
        family = "range_expansion_15min"
        for avg_window, multiplier, horizon, cooldown in itertools.product(
            f.get("avg_range_windows", [20]),
            f.get("range_multipliers", [1.5]),
            f.get("horizon_bars", [4]),
            f.get("cooldown_bars", [1]),
        ):
            entry, exit_, direction, reason = gen_range_expansion_arrays(df, int(avg_window), float(multiplier), int(horizon))
            keep = nonoverlap_indices(entry, exit_, int(cooldown))
            if keep.size == 0:
                continue
            entry, exit_, direction = entry[keep], exit_[keep], direction[keep]
            variant = f"range{avg_window}_x{float(multiplier):g}_h{horizon}_cool{cooldown}"
            raw, net, trade_frame = make_trade_frame(df, family, variant, interval, entry, exit_, direction, reason, cost_usd, save_full_trades)
            evaluations.append(evaluate_variant(family, variant, raw, net, cost_usd, train_fraction, decision_cfg))
            if trade_frame is not None:
                all_trade_frames.append(trade_frame)

    robust = [e for e in evaluations if e["robust_grid_candidate"]]
    top = sorted(evaluations, key=lambda x: float(x["base"]["total_net_usd"]), reverse=True)[:20]

    if robust:
        status = "stage2d_robust_grid_candidate_found"
        reason = "At least one baseline variant passed train/test, outlier, cost, and PF checks."
    else:
        status = "no_stage2d_robust_grid_candidate"
        reason = "No simple baseline variant passed Stage 2D robustness checks."

    stamp = utc_stamp()
    trades_csv = None
    if save_full_trades:
        trades_csv_path = trades_dir / f"stage2d_grid_trades_{stamp}.csv"
        if all_trade_frames:
            pd.concat(all_trade_frames, ignore_index=True).to_csv(trades_csv_path, index=False)
        else:
            pd.DataFrame().to_csv(trades_csv_path, index=False)
        trades_csv = str(trades_csv_path)

    eval_csv = report_dir / f"stage2d_grid_evaluations_{stamp}.csv"
    summary_json = report_dir / f"stage2d_grid_summary_{stamp}.json"
    summary_md = report_dir / f"stage2d_grid_summary_{stamp}.md"

    eval_rows = []
    for e in evaluations:
        eval_rows.append(
            {
                "family": e["family"],
                "variant": e["variant"],
                "robust_grid_candidate": e["robust_grid_candidate"],
                "reason": e["reason"],
                "trade_count": e["base"]["trade_count"],
                "total_net_usd": e["base"]["total_net_usd"],
                "avg_net_usd": e["base"]["avg_net_usd"],
                "median_net_usd": e["base"]["median_net_usd"],
                "win_rate": e["base"]["win_rate"],
                "profit_factor": e["base"]["profit_factor"],
                "train_total_net_usd": e["train"]["total_net_usd"],
                "test_total_net_usd": e["test"]["total_net_usd"],
                "remove_top_5_total_net_usd": e["remove_top_5"]["total_net_usd"],
                "cost_x2_total_net_usd": e["cost_x2"]["total_net_usd"],
            }
        )
    pd.DataFrame(eval_rows).to_csv(eval_csv, index=False)

    runtime_seconds = round(time.perf_counter() - started, 3)
    payload = {
        "ok": True,
        "stage": "stage2d_baseline_grid_lab",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_seconds": runtime_seconds,
        "implementation": "fast_vectorized",
        "data_source_mode": "sqlite" if data_db else "csv",
        "data_db": data_db,
        "data_files": data_files,
        "cost_model": {**cost_cfg, "effective_roundtrip_cost_usd": cost_usd},
        "decision_config": decision_cfg,
        "decision": {
            "status": status,
            "reason": reason,
            "robust_candidate_count": int(len(robust)),
        },
        "variant_count": int(len(evaluations)),
        "save_full_trades": bool(save_full_trades),
        "robust_candidates": robust[:20],
        "top_variants": top,
        "trades_csv": trades_csv,
        "evaluations_csv": str(eval_csv),
    }

    write_json(summary_json, payload)
    write_markdown(summary_md, payload)

    print(
        json.dumps(
            {
                "ok": True,
                "decision": payload["decision"],
                "summary_json": str(summary_json),
                "summary_md": str(summary_md),
                "trades_csv": trades_csv,
                "evaluations_csv": str(eval_csv),
                "variant_count": len(evaluations),
                "runtime_seconds": runtime_seconds,
                "implementation": "fast_vectorized",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
