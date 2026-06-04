from __future__ import annotations

import argparse
import itertools
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
import yaml


@dataclass(frozen=True)
class Signal:
    family: str
    variant: str
    interval: str
    entry_idx: int
    exit_idx: int
    direction: int
    reason: str


@dataclass(frozen=True)
class Trade:
    family: str
    variant: str
    interval: str
    entry_idx: int
    exit_idx: int
    entry_time_utc: str
    exit_time_utc: str
    direction: int
    direction_label: str
    entry_price: float
    exit_price: float
    raw_usd: float
    cost_usd: float
    net_usd: float
    reason: str


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


def load_interval_df(data_dir: Path, interval: str) -> Tuple[Path, pd.DataFrame]:
    path = latest_csv_for_interval(data_dir, interval)
    df = pd.read_csv(path)

    required = {"time_utc", "open", "high", "low", "close", "interval", "provider", "symbol"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")

    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["time_utc", "open", "high", "low", "close"])
    df = df.sort_values("time_utc").drop_duplicates(subset=["time_utc"], keep="last").reset_index(drop=True)
    df["date_utc"] = df["time_utc"].dt.date.astype(str)
    df["hour_utc"] = df["time_utc"].dt.hour

    if "session_utc" not in df.columns:
        hours = df["hour_utc"]
        df["session_utc"] = "other"
        df.loc[(hours >= 0) & (hours < 7), "session_utc"] = "asia"
        df.loc[(hours >= 7) & (hours < 13), "session_utc"] = "london"
        df.loc[(hours >= 13) & (hours < 17), "session_utc"] = "london_ny_overlap"
        df.loc[(hours >= 17) & (hours < 22), "session_utc"] = "new_york"

    return path, df


def nonoverlap_filter(signals: List[Signal], cooldown_bars: int) -> List[Signal]:
    accepted: List[Signal] = []
    next_allowed = -1
    for s in sorted(signals, key=lambda x: (x.entry_idx, x.exit_idx)):
        if s.entry_idx < next_allowed:
            continue
        accepted.append(s)
        next_allowed = s.exit_idx + int(cooldown_bars) + 1
    return accepted


def signal_to_trade(s: Signal, df: pd.DataFrame, cost_usd: float) -> Optional[Trade]:
    if s.entry_idx < 0 or s.exit_idx >= len(df) or s.exit_idx <= s.entry_idx:
        return None
    if s.direction not in {-1, 1}:
        return None

    entry = float(df.loc[s.entry_idx, "close"])
    exit_ = float(df.loc[s.exit_idx, "close"])
    raw = s.direction * (exit_ - entry)
    net = raw - cost_usd

    return Trade(
        family=s.family,
        variant=s.variant,
        interval=s.interval,
        entry_idx=int(s.entry_idx),
        exit_idx=int(s.exit_idx),
        entry_time_utc=pd.Timestamp(df.loc[s.entry_idx, "time_utc"]).isoformat(),
        exit_time_utc=pd.Timestamp(df.loc[s.exit_idx, "time_utc"]).isoformat(),
        direction=int(s.direction),
        direction_label="long" if s.direction == 1 else "short",
        entry_price=entry,
        exit_price=exit_,
        raw_usd=float(raw),
        cost_usd=float(cost_usd),
        net_usd=float(net),
        reason=s.reason,
    )


def trades_from_signals(signals: List[Signal], df: pd.DataFrame, cost_usd: float) -> List[Trade]:
    out = []
    for s in signals:
        t = signal_to_trade(s, df, cost_usd)
        if t:
            out.append(t)
    return out


def gen_sma_trend(
    df: pd.DataFrame,
    interval: str,
    family: str,
    sma_window: int,
    horizon: int,
    min_distance: float,
) -> List[Signal]:
    work = df.copy()
    work["sma"] = work["close"].rolling(int(sma_window)).mean()
    signals: List[Signal] = []
    variant = f"sma{sma_window}_h{horizon}_dist{min_distance:g}"

    for i in range(len(work) - int(horizon)):
        sma = work.loc[i, "sma"]
        if pd.isna(sma):
            continue
        diff = float(work.loc[i, "close"] - sma)
        if abs(diff) < float(min_distance):
            continue
        direction = 1 if diff > 0 else -1
        signals.append(
            Signal(
                family=family,
                variant=variant,
                interval=interval,
                entry_idx=int(i),
                exit_idx=int(i + horizon),
                direction=direction,
                reason=f"close_sma_diff_{diff:.4f}",
            )
        )
    return signals


def gen_session_momentum(
    df: pd.DataFrame,
    interval: str,
    family: str,
    lookback: int,
    horizon: int,
    min_move: float,
    sessions: Iterable[str],
) -> List[Signal]:
    allowed = set(sessions)
    work = df.copy()
    work["lookback_move"] = work["close"] - work["close"].shift(int(lookback))
    signals: List[Signal] = []
    variant = f"lb{lookback}_h{horizon}_move{min_move:g}"

    for i in range(int(lookback), len(work) - int(horizon)):
        if str(work.loc[i, "session_utc"]) not in allowed:
            continue
        move = float(work.loc[i, "lookback_move"])
        if abs(move) < float(min_move):
            continue
        direction = 1 if move > 0 else -1
        signals.append(
            Signal(
                family=family,
                variant=variant,
                interval=interval,
                entry_idx=int(i),
                exit_idx=int(i + horizon),
                direction=direction,
                reason=f"lookback_move_{move:.4f}",
            )
        )
    return signals


def gen_range_expansion(
    df: pd.DataFrame,
    interval: str,
    family: str,
    avg_range_window: int,
    multiplier: float,
    horizon: int,
) -> List[Signal]:
    work = df.copy()
    work["bar_range"] = work["high"] - work["low"]
    work["avg_range"] = work["bar_range"].rolling(int(avg_range_window)).mean()
    signals: List[Signal] = []
    variant = f"range{avg_range_window}_x{multiplier:g}_h{horizon}"

    for i in range(int(avg_range_window), len(work) - int(horizon)):
        avg = work.loc[i, "avg_range"]
        if pd.isna(avg) or avg <= 0:
            continue
        rng = float(work.loc[i, "bar_range"])
        if rng < float(multiplier) * float(avg):
            continue
        body = float(work.loc[i, "close"] - work.loc[i, "open"])
        if body == 0:
            continue
        direction = 1 if body > 0 else -1
        signals.append(
            Signal(
                family=family,
                variant=variant,
                interval=interval,
                entry_idx=int(i),
                exit_idx=int(i + horizon),
                direction=direction,
                reason=f"range_{rng:.4f}_avg_{float(avg):.4f}",
            )
        )
    return signals


def max_drawdown(values: List[float]) -> float:
    if not values:
        return 0.0
    equity = pd.Series(values).cumsum()
    peak = equity.cummax()
    return float((equity - peak).min())


def profit_factor(values: List[float]) -> Optional[float]:
    wins = [x for x in values if x > 0]
    losses = [x for x in values if x <= 0]
    loss_abs = abs(sum(losses))
    if loss_abs == 0:
        return None
    return float(sum(wins) / loss_abs)


def remove_top_k(values: List[float], k: int) -> List[float]:
    remaining = list(values)
    for v in sorted(values, reverse=True)[: min(k, len(values))]:
        for i, x in enumerate(remaining):
            if x == v:
                remaining.pop(i)
                break
    return remaining


def metrics(values: List[float]) -> Dict[str, Any]:
    if not values:
        return {
            "trade_count": 0,
            "total_net_usd": 0.0,
            "avg_net_usd": 0.0,
            "median_net_usd": 0.0,
            "win_rate": 0.0,
            "max_drawdown_usd": 0.0,
            "profit_factor": None,
        }

    s = pd.Series(values, dtype="float64")
    return {
        "trade_count": int(len(s)),
        "total_net_usd": float(s.sum()),
        "avg_net_usd": float(s.mean()),
        "median_net_usd": float(s.median()),
        "win_rate": float((s > 0).mean()),
        "best_net_usd": float(s.max()),
        "worst_net_usd": float(s.min()),
        "max_drawdown_usd": max_drawdown(s.tolist()),
        "profit_factor": profit_factor(s.tolist()),
    }


def evaluate_variant(
    family: str,
    variant: str,
    trades: List[Trade],
    train_fraction: float,
    decision_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    trades_sorted = sorted(trades, key=lambda t: t.entry_time_utc)
    values = [t.net_usd for t in trades_sorted]
    raw = [t.raw_usd for t in trades_sorted]
    cost = [t.cost_usd for t in trades_sorted]

    split_idx = int(len(values) * float(train_fraction))
    train_values = values[:split_idx]
    test_values = values[split_idx:]

    base = metrics(values)
    train = metrics(train_values)
    test = metrics(test_values)
    remove_top5 = metrics(remove_top_k(values, 5))

    cost_x2_values = [r - c * 2.0 for r, c in zip(raw, cost)]
    cost_x2 = metrics(cost_x2_values)

    min_trades = int(decision_cfg.get("min_trades", 50))
    min_test_trades = int(decision_cfg.get("min_test_trades", 20))
    pf_min = float(decision_cfg.get("require_profit_factor_min", 1.05))

    checks = {
        "min_trades": int(base["trade_count"]) >= min_trades,
        "min_test_trades": int(test["trade_count"]) >= min_test_trades,
        "train_positive": float(train["total_net_usd"]) > 0,
        "test_positive": float(test["total_net_usd"]) > 0,
        "remove_top_5_positive": float(remove_top5["total_net_usd"]) > 0,
        "cost_x2_positive": float(cost_x2["total_net_usd"]) > 0,
        "profit_factor_min": base.get("profit_factor") is not None and float(base["profit_factor"]) >= pf_min,
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


def trade_to_dict(t: Trade) -> Dict[str, Any]:
    return {
        "family": t.family,
        "variant": t.variant,
        "interval": t.interval,
        "entry_idx": t.entry_idx,
        "exit_idx": t.exit_idx,
        "entry_time_utc": t.entry_time_utc,
        "exit_time_utc": t.exit_time_utc,
        "direction": t.direction,
        "direction_label": t.direction_label,
        "entry_price": t.entry_price,
        "exit_price": t.exit_price,
        "raw_usd": t.raw_usd,
        "cost_usd": t.cost_usd,
        "net_usd": t.net_usd,
        "reason": t.reason,
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
    lines.append(f"- Total variants: `{payload['variant_count']}`")
    lines.append(f"- Robust candidates: `{payload['decision']['robust_candidate_count']}`")
    lines.append("")
    lines.append("## Top variants by total net")
    lines.append("")
    lines.append("| Family | Variant | Robust | Reason | Trades | Train total | Test total | Total net | PF | Remove top5 total | Cost x2 total |")
    lines.append("|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|")
    for row in payload["top_variants"]:
        base = row["base"]
        train = row["train"]
        test = row["test"]
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
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("Stage 2D is still baseline-only. A robust candidate here does not authorize paper-order or live trading.")
    lines.append("If no robust candidate is found, the next step is better data/backfill or new baseline families, not ML.")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 2D baseline grid lab with train/test split and robustness checks.")
    parser.add_argument("--config", default="configs/stage2d.yaml")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--report-dir", default=None)
    args = parser.parse_args()

    cfg = load_yaml(Path(args.config))
    data_dir = Path(args.data_dir or cfg.get("data_dir", "data/normalized"))
    report_dir = Path(args.report_dir or cfg.get("report_dir", "data/reports"))
    trades_dir = Path(cfg.get("trades_dir", "data/reports/stage2d_trades"))
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
        path, df = load_interval_df(data_dir, interval)
        data_by_interval[interval] = df
        data_files[interval] = str(path)

    all_trades: List[Trade] = []
    evaluations: List[Dict[str, Any]] = []

    f = families.get("sma_trend_1h", {})
    if f.get("enabled", True):
        interval = str(f.get("interval", "1h"))
        df = data_by_interval[interval]
        for sma_window, horizon, cooldown, min_distance in itertools.product(
            f.get("sma_windows", [20]),
            f.get("horizon_bars", [3]),
            f.get("cooldown_bars", [1]),
            f.get("min_distance_usd", [0.0]),
        ):
            signals = gen_sma_trend(df, interval, "sma_trend_1h", int(sma_window), int(horizon), float(min_distance))
            accepted = nonoverlap_filter(signals, int(cooldown))
            trades = trades_from_signals(accepted, df, cost_usd)
            # add cooldown to variant label after generation
            trades = [
                Trade(
                    family=t.family,
                    variant=f"{t.variant}_cool{cooldown}",
                    interval=t.interval,
                    entry_idx=t.entry_idx,
                    exit_idx=t.exit_idx,
                    entry_time_utc=t.entry_time_utc,
                    exit_time_utc=t.exit_time_utc,
                    direction=t.direction,
                    direction_label=t.direction_label,
                    entry_price=t.entry_price,
                    exit_price=t.exit_price,
                    raw_usd=t.raw_usd,
                    cost_usd=t.cost_usd,
                    net_usd=t.net_usd,
                    reason=t.reason,
                )
                for t in trades
            ]
            if trades:
                variant = trades[0].variant
                all_trades.extend(trades)
                evaluations.append(evaluate_variant("sma_trend_1h", variant, trades, train_fraction, decision_cfg))

    f = families.get("session_momentum_15min", {})
    if f.get("enabled", True):
        interval = str(f.get("interval", "15min"))
        df = data_by_interval[interval]
        for lookback, horizon, cooldown, min_move in itertools.product(
            f.get("lookback_bars", [1]),
            f.get("horizon_bars", [4]),
            f.get("cooldown_bars", [1]),
            f.get("min_move_usd", [0.0]),
        ):
            signals = gen_session_momentum(
                df,
                interval,
                "session_momentum_15min",
                int(lookback),
                int(horizon),
                float(min_move),
                f.get("sessions", ["london", "london_ny_overlap", "new_york"]),
            )
            accepted = nonoverlap_filter(signals, int(cooldown))
            trades = trades_from_signals(accepted, df, cost_usd)
            trades = [
                Trade(
                    family=t.family,
                    variant=f"{t.variant}_cool{cooldown}",
                    interval=t.interval,
                    entry_idx=t.entry_idx,
                    exit_idx=t.exit_idx,
                    entry_time_utc=t.entry_time_utc,
                    exit_time_utc=t.exit_time_utc,
                    direction=t.direction,
                    direction_label=t.direction_label,
                    entry_price=t.entry_price,
                    exit_price=t.exit_price,
                    raw_usd=t.raw_usd,
                    cost_usd=t.cost_usd,
                    net_usd=t.net_usd,
                    reason=t.reason,
                )
                for t in trades
            ]
            if trades:
                variant = trades[0].variant
                all_trades.extend(trades)
                evaluations.append(evaluate_variant("session_momentum_15min", variant, trades, train_fraction, decision_cfg))

    f = families.get("range_expansion_15min", {})
    if f.get("enabled", True):
        interval = str(f.get("interval", "15min"))
        df = data_by_interval[interval]
        for avg_window, multiplier, horizon, cooldown in itertools.product(
            f.get("avg_range_windows", [20]),
            f.get("range_multipliers", [1.5]),
            f.get("horizon_bars", [4]),
            f.get("cooldown_bars", [1]),
        ):
            signals = gen_range_expansion(
                df,
                interval,
                "range_expansion_15min",
                int(avg_window),
                float(multiplier),
                int(horizon),
            )
            accepted = nonoverlap_filter(signals, int(cooldown))
            trades = trades_from_signals(accepted, df, cost_usd)
            trades = [
                Trade(
                    family=t.family,
                    variant=f"{t.variant}_cool{cooldown}",
                    interval=t.interval,
                    entry_idx=t.entry_idx,
                    exit_idx=t.exit_idx,
                    entry_time_utc=t.entry_time_utc,
                    exit_time_utc=t.exit_time_utc,
                    direction=t.direction,
                    direction_label=t.direction_label,
                    entry_price=t.entry_price,
                    exit_price=t.exit_price,
                    raw_usd=t.raw_usd,
                    cost_usd=t.cost_usd,
                    net_usd=t.net_usd,
                    reason=t.reason,
                )
                for t in trades
            ]
            if trades:
                variant = trades[0].variant
                all_trades.extend(trades)
                evaluations.append(evaluate_variant("range_expansion_15min", variant, trades, train_fraction, decision_cfg))

    robust = [e for e in evaluations if e["robust_grid_candidate"]]
    top = sorted(evaluations, key=lambda x: float(x["base"]["total_net_usd"]), reverse=True)[:20]

    if robust:
        status = "stage2d_robust_grid_candidate_found"
        reason = "At least one baseline variant passed train/test, outlier, cost, and PF checks."
    else:
        status = "no_stage2d_robust_grid_candidate"
        reason = "No simple baseline variant passed Stage 2D robustness checks."

    stamp = utc_stamp()
    trades_csv = trades_dir / f"stage2d_grid_trades_{stamp}.csv"
    eval_csv = report_dir / f"stage2d_grid_evaluations_{stamp}.csv"
    summary_json = report_dir / f"stage2d_grid_summary_{stamp}.json"
    summary_md = report_dir / f"stage2d_grid_summary_{stamp}.md"

    pd.DataFrame([trade_to_dict(t) for t in all_trades]).to_csv(trades_csv, index=False)

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

    payload = {
        "ok": True,
        "stage": "stage2d_baseline_grid_lab",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_files": data_files,
        "cost_model": {**cost_cfg, "effective_roundtrip_cost_usd": cost_usd},
        "decision_config": decision_cfg,
        "decision": {
            "status": status,
            "reason": reason,
            "robust_candidate_count": int(len(robust)),
        },
        "variant_count": int(len(evaluations)),
        "robust_candidates": robust[:20],
        "top_variants": top,
        "trades_csv": str(trades_csv),
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
                "trades_csv": str(trades_csv),
                "evaluations_csv": str(eval_csv),
                "variant_count": len(evaluations),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
