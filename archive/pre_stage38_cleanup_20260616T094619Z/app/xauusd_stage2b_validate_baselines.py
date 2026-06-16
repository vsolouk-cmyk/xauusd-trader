from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
import yaml


@dataclass(frozen=True)
class Signal:
    baseline: str
    interval: str
    entry_idx: int
    exit_idx: int
    direction: int
    reason: str


@dataclass(frozen=True)
class Trade:
    baseline: str
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
    next_allowed_entry_idx = -1

    for s in sorted(signals, key=lambda x: (x.entry_idx, x.exit_idx)):
        if s.entry_idx < next_allowed_entry_idx:
            continue
        accepted.append(s)
        next_allowed_entry_idx = s.exit_idx + int(cooldown_bars) + 1

    return accepted


def signal_to_trade(signal: Signal, df: pd.DataFrame, cost_usd: float) -> Optional[Trade]:
    if signal.entry_idx < 0 or signal.exit_idx >= len(df) or signal.exit_idx <= signal.entry_idx:
        return None
    if signal.direction not in {-1, 1}:
        return None

    entry_price = float(df.loc[signal.entry_idx, "close"])
    exit_price = float(df.loc[signal.exit_idx, "close"])
    raw_usd = signal.direction * (exit_price - entry_price)
    net_usd = raw_usd - cost_usd

    return Trade(
        baseline=signal.baseline,
        interval=signal.interval,
        entry_idx=int(signal.entry_idx),
        exit_idx=int(signal.exit_idx),
        entry_time_utc=pd.Timestamp(df.loc[signal.entry_idx, "time_utc"]).isoformat(),
        exit_time_utc=pd.Timestamp(df.loc[signal.exit_idx, "time_utc"]).isoformat(),
        direction=int(signal.direction),
        direction_label="long" if signal.direction == 1 else "short",
        entry_price=entry_price,
        exit_price=exit_price,
        raw_usd=float(raw_usd),
        cost_usd=float(cost_usd),
        net_usd=float(net_usd),
        reason=signal.reason,
    )


def trades_from_signals(signals: List[Signal], df: pd.DataFrame, cost_usd: float) -> List[Trade]:
    trades: List[Trade] = []
    for s in signals:
        t = signal_to_trade(s, df, cost_usd)
        if t:
            trades.append(t)
    return trades


def gen_sma_trend_signals(df: pd.DataFrame, interval: str, baseline: str, sma_window: int, horizon_bars: int) -> List[Signal]:
    work = df.copy()
    work["sma"] = work["close"].rolling(int(sma_window)).mean()
    signals: List[Signal] = []

    for i in range(len(work) - int(horizon_bars)):
        sma = work.loc[i, "sma"]
        if pd.isna(sma):
            continue
        close = float(work.loc[i, "close"])
        direction = 1 if close > float(sma) else -1
        signals.append(
            Signal(
                baseline=baseline,
                interval=interval,
                entry_idx=int(i),
                exit_idx=int(i) + int(horizon_bars),
                direction=direction,
                reason=f"close_vs_sma{sma_window}",
            )
        )

    return signals


def gen_session_momentum_signals(
    df: pd.DataFrame,
    interval: str,
    baseline: str,
    horizon_bars: int,
    sessions: Iterable[str],
) -> List[Signal]:
    allowed = set(sessions)
    work = df.copy()
    work["prev_return"] = work["close"].diff()
    signals: List[Signal] = []

    for i in range(1, len(work) - int(horizon_bars)):
        if str(work.loc[i, "session_utc"]) not in allowed:
            continue
        prev_return = float(work.loc[i, "prev_return"])
        if prev_return == 0:
            continue
        direction = 1 if prev_return > 0 else -1
        signals.append(
            Signal(
                baseline=baseline,
                interval=interval,
                entry_idx=int(i),
                exit_idx=int(i) + int(horizon_bars),
                direction=direction,
                reason="prior_candle_momentum_in_active_session",
            )
        )

    return signals


def gen_atr_expansion_signals(
    df: pd.DataFrame,
    interval: str,
    baseline: str,
    atr_window: int,
    range_multiplier: float,
    horizon_bars: int,
) -> List[Signal]:
    work = df.copy()
    work["bar_range"] = work["high"] - work["low"]
    work["avg_range"] = work["bar_range"].rolling(int(atr_window)).mean()
    signals: List[Signal] = []

    for i in range(len(work) - int(horizon_bars)):
        avg_range = work.loc[i, "avg_range"]
        if pd.isna(avg_range) or avg_range <= 0:
            continue
        bar_range = float(work.loc[i, "bar_range"])
        if bar_range < float(range_multiplier) * float(avg_range):
            continue
        body = float(work.loc[i, "close"] - work.loc[i, "open"])
        if body == 0:
            continue
        direction = 1 if body > 0 else -1
        signals.append(
            Signal(
                baseline=baseline,
                interval=interval,
                entry_idx=int(i),
                exit_idx=int(i) + int(horizon_bars),
                direction=direction,
                reason=f"range_gt_{range_multiplier}x_avg_range{atr_window}",
            )
        )

    return signals


def gen_asia_breakout_signals(
    df: pd.DataFrame,
    interval: str,
    baseline: str,
    asia_start_hour: int,
    asia_end_hour: int,
    trade_start_hour: int,
    trade_end_hour: int,
    horizon_bars: int,
    max_trades_per_day: int,
) -> List[Signal]:
    signals: List[Signal] = []

    for _, day in df.groupby("date_utc", sort=True):
        asia = day[(day["hour_utc"] >= asia_start_hour) & (day["hour_utc"] < asia_end_hour)]
        trade_window = day[(day["hour_utc"] >= trade_start_hour) & (day["hour_utc"] < trade_end_hour)]

        if asia.empty or trade_window.empty:
            continue

        asia_high = float(asia["high"].max())
        asia_low = float(asia["low"].min())
        count = 0

        for idx in trade_window.index:
            if count >= int(max_trades_per_day):
                break
            close = float(df.loc[idx, "close"])

            if close > asia_high:
                direction = 1
                reason = "close_breaks_above_asia_high"
            elif close < asia_low:
                direction = -1
                reason = "close_breaks_below_asia_low"
            else:
                continue

            exit_idx = int(idx) + int(horizon_bars)
            if exit_idx < len(df):
                signals.append(
                    Signal(
                        baseline=baseline,
                        interval=interval,
                        entry_idx=int(idx),
                        exit_idx=exit_idx,
                        direction=direction,
                        reason=reason,
                    )
                )
                count += 1

    return signals


def gen_london_open_breakout_signals(
    df: pd.DataFrame,
    interval: str,
    baseline: str,
    open_start_hour: int,
    open_end_hour: int,
    trade_start_hour: int,
    trade_end_hour: int,
    horizon_bars: int,
    max_trades_per_day: int,
) -> List[Signal]:
    signals: List[Signal] = []

    for _, day in df.groupby("date_utc", sort=True):
        open_range = day[(day["hour_utc"] >= open_start_hour) & (day["hour_utc"] < open_end_hour)]
        trade_window = day[(day["hour_utc"] >= trade_start_hour) & (day["hour_utc"] < trade_end_hour)]

        if open_range.empty or trade_window.empty:
            continue

        open_high = float(open_range["high"].max())
        open_low = float(open_range["low"].min())
        count = 0

        for idx in trade_window.index:
            if count >= int(max_trades_per_day):
                break
            close = float(df.loc[idx, "close"])

            if close > open_high:
                direction = 1
                reason = "close_breaks_above_london_open_high"
            elif close < open_low:
                direction = -1
                reason = "close_breaks_below_london_open_low"
            else:
                continue

            exit_idx = int(idx) + int(horizon_bars)
            if exit_idx < len(df):
                signals.append(
                    Signal(
                        baseline=baseline,
                        interval=interval,
                        entry_idx=int(idx),
                        exit_idx=exit_idx,
                        direction=direction,
                        reason=reason,
                    )
                )
                count += 1

    return signals


def max_drawdown(values: List[float]) -> float:
    if not values:
        return 0.0
    equity = pd.Series(values).cumsum()
    peak = equity.cummax()
    return float((equity - peak).min())


def profit_factor(net_values: List[float]) -> Optional[float]:
    wins = [x for x in net_values if x > 0]
    losses = [x for x in net_values if x <= 0]
    loss_abs = abs(sum(losses))
    if loss_abs == 0:
        return None
    return float(sum(wins) / loss_abs)


def summarize(
    baseline: str,
    raw_signal_count: int,
    accepted_signal_count: int,
    trades: List[Trade],
    min_trades: int,
    require_positive_avg_net: bool,
    require_positive_total_net: bool,
    max_dd_to_total_net_ratio: float,
) -> Dict[str, Any]:
    if not trades:
        return {
            "baseline": baseline,
            "raw_signal_count": int(raw_signal_count),
            "accepted_signal_count": int(accepted_signal_count),
            "trade_count": 0,
            "sample_ok": False,
            "robust_candidate": False,
            "reason": "no_trades_after_nonoverlap_filter",
        }

    net = [float(t.net_usd) for t in trades]
    raw = [float(t.raw_usd) for t in trades]
    wins = [x for x in net if x > 0]

    total_net = float(sum(net))
    avg_net = float(total_net / len(net))
    dd = max_drawdown(net)

    sample_ok = len(trades) >= int(min_trades)
    dd_ratio_ok = True
    if total_net > 0:
        dd_ratio_ok = abs(dd) <= float(max_dd_to_total_net_ratio) * total_net

    robust = sample_ok
    if require_positive_avg_net:
        robust = robust and avg_net > 0
    if require_positive_total_net:
        robust = robust and total_net > 0
    robust = robust and dd_ratio_ok

    if not sample_ok:
        reason = "insufficient_nonoverlap_trades"
    elif avg_net <= 0:
        reason = "negative_or_zero_avg_net_usd"
    elif total_net <= 0:
        reason = "negative_or_zero_total_net_usd"
    elif not dd_ratio_ok:
        reason = "drawdown_too_large_vs_total_net"
    else:
        reason = "robust_candidate"

    return {
        "baseline": baseline,
        "raw_signal_count": int(raw_signal_count),
        "accepted_signal_count": int(accepted_signal_count),
        "overlap_reduction_ratio": float(1.0 - (accepted_signal_count / max(raw_signal_count, 1))),
        "trade_count": int(len(trades)),
        "sample_ok": bool(sample_ok),
        "robust_candidate": bool(robust),
        "reason": reason,
        "win_rate": float(len(wins) / len(net)),
        "avg_raw_usd": float(sum(raw) / len(raw)),
        "avg_net_usd": avg_net,
        "median_net_usd": float(pd.Series(net).median()),
        "total_net_usd": total_net,
        "best_net_usd": float(max(net)),
        "worst_net_usd": float(min(net)),
        "max_drawdown_usd": dd,
        "profit_factor": profit_factor(net),
    }


def trade_to_dict(t: Trade) -> Dict[str, Any]:
    return {
        "baseline": t.baseline,
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
    lines.append("# XAUUSD Stage 2B Baseline Validation")
    lines.append("")
    lines.append(f"- Generated at UTC: `{payload['generated_at_utc']}`")
    lines.append(f"- Decision: `{payload['decision']['status']}`")
    lines.append(f"- Reason: `{payload['decision']['reason']}`")
    lines.append("")
    lines.append("## Critical interpretation")
    lines.append("")
    lines.append("Stage 2B reduces false optimism by removing overlapping trades.")
    lines.append("This is still not ML, not paper-order, and not live approval.")
    lines.append("")
    lines.append("## Metrics")
    lines.append("")
    lines.append("| Baseline | Raw signals | Accepted | Trades | Robust | Reason | Win rate | Avg net | Total net | Max DD |")
    lines.append("|---|---:|---:|---:|---:|---|---:|---:|---:|---:|")
    for s in payload["summaries"]:
        lines.append(
            "| {baseline} | {raw} | {accepted} | {trades} | {robust} | {reason} | {wr:.3f} | {avg:.4f} | {total:.4f} | {dd:.4f} |".format(
                baseline=s.get("baseline"),
                raw=s.get("raw_signal_count", 0),
                accepted=s.get("accepted_signal_count", 0),
                trades=s.get("trade_count", 0),
                robust=s.get("robust_candidate", False),
                reason=s.get("reason", ""),
                wr=float(s.get("win_rate", 0.0)),
                avg=float(s.get("avg_net_usd", 0.0)),
                total=float(s.get("total_net_usd", 0.0)),
                dd=float(s.get("max_drawdown_usd", 0.0)),
            )
        )
    lines.append("")
    lines.append("## Data files")
    lines.append("")
    for interval, file_path in payload.get("data_files", {}).items():
        lines.append(f"- `{interval}`: `{file_path}`")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 2B: validate baselines with non-overlapping trades.")
    parser.add_argument("--config", default="configs/stage2b.yaml")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--report-dir", default=None)
    args = parser.parse_args()

    cfg = load_yaml(Path(args.config))
    data_dir = Path(args.data_dir or cfg.get("data_dir", "data/normalized"))
    report_dir = Path(args.report_dir or cfg.get("report_dir", "data/reports"))
    trades_dir = Path(cfg.get("trades_dir", "data/reports/stage2b_trades"))

    cost_cfg = cfg.get("cost_model", {}) or {}
    cost_usd = float(
        cost_cfg.get(
            "total_roundtrip_cost_usd",
            float(cost_cfg.get("assumed_spread_usd", 0.30)) + float(cost_cfg.get("assumed_slippage_usd", 0.05)),
        )
    )

    decision_cfg = cfg.get("decision", {}) or {}
    min_trades = int(decision_cfg.get("min_nonoverlap_trades", 30))
    require_positive_avg_net = bool(decision_cfg.get("require_positive_avg_net_usd", True))
    require_positive_total_net = bool(decision_cfg.get("require_positive_total_net_usd", True))
    max_dd_ratio = float(decision_cfg.get("max_allowed_drawdown_to_total_net_ratio", 2.0))

    baseline_cfgs = cfg.get("baselines", {}) or {}
    required_intervals = sorted({str(b.get("interval")) for b in baseline_cfgs.values() if b.get("enabled", True)})

    data_by_interval: Dict[str, pd.DataFrame] = {}
    data_files: Dict[str, str] = {}
    for interval in required_intervals:
        path, df = load_interval_df(data_dir, interval)
        data_by_interval[interval] = df
        data_files[interval] = str(path)

    all_trades: List[Trade] = []
    summaries: List[Dict[str, Any]] = []

    for baseline_name, b in sorted(baseline_cfgs.items()):
        if not b.get("enabled", True):
            continue

        interval = str(b.get("interval"))
        df = data_by_interval[interval]
        horizon = int(b.get("horizon_bars", 1))
        cooldown = int(b.get("cooldown_bars", 0))

        if baseline_name == "higher_timeframe_sma20_trend_nonoverlap":
            raw_signals = gen_sma_trend_signals(
                df=df,
                interval=interval,
                baseline=baseline_name,
                sma_window=int(b.get("sma_window", 20)),
                horizon_bars=horizon,
            )
            accepted = nonoverlap_filter(raw_signals, cooldown_bars=cooldown)

        elif baseline_name == "session_momentum_15min_nonoverlap":
            raw_signals = gen_session_momentum_signals(
                df=df,
                interval=interval,
                baseline=baseline_name,
                horizon_bars=horizon,
                sessions=b.get("sessions", ["london", "london_ny_overlap", "new_york"]),
            )
            accepted = nonoverlap_filter(raw_signals, cooldown_bars=cooldown)

        elif baseline_name == "atr_range_expansion_15min_nonoverlap":
            raw_signals = gen_atr_expansion_signals(
                df=df,
                interval=interval,
                baseline=baseline_name,
                atr_window=int(b.get("atr_window", 20)),
                range_multiplier=float(b.get("range_multiplier", 1.5)),
                horizon_bars=horizon,
            )
            accepted = nonoverlap_filter(raw_signals, cooldown_bars=cooldown)

        elif baseline_name == "asia_range_breakout_5min_daily":
            raw_signals = gen_asia_breakout_signals(
                df=df,
                interval=interval,
                baseline=baseline_name,
                asia_start_hour=int(b.get("asia_start_hour_utc", 0)),
                asia_end_hour=int(b.get("asia_end_hour_utc", 7)),
                trade_start_hour=int(b.get("trade_start_hour_utc", 7)),
                trade_end_hour=int(b.get("trade_end_hour_utc", 13)),
                horizon_bars=horizon,
                max_trades_per_day=int(b.get("max_trades_per_day", 1)),
            )
            accepted = raw_signals

        elif baseline_name == "london_open_breakout_5min_daily":
            raw_signals = gen_london_open_breakout_signals(
                df=df,
                interval=interval,
                baseline=baseline_name,
                open_start_hour=int(b.get("open_start_hour_utc", 7)),
                open_end_hour=int(b.get("open_end_hour_utc", 8)),
                trade_start_hour=int(b.get("trade_start_hour_utc", 8)),
                trade_end_hour=int(b.get("trade_end_hour_utc", 13)),
                horizon_bars=horizon,
                max_trades_per_day=int(b.get("max_trades_per_day", 1)),
            )
            accepted = raw_signals

        else:
            continue

        trades = trades_from_signals(accepted, df, cost_usd)
        all_trades.extend(trades)
        summaries.append(
            summarize(
                baseline=baseline_name,
                raw_signal_count=len(raw_signals),
                accepted_signal_count=len(accepted),
                trades=trades,
                min_trades=min_trades,
                require_positive_avg_net=require_positive_avg_net,
                require_positive_total_net=require_positive_total_net,
                max_dd_to_total_net_ratio=max_dd_ratio,
            )
        )

    robust_candidates = [s for s in summaries if s.get("robust_candidate")]
    any_sample_ok = any(s.get("sample_ok") for s in summaries)

    if robust_candidates:
        status = "robust_candidate_found"
        reason = "At least one baseline stayed positive after non-overlap filtering and assumed costs."
    elif not any_sample_ok:
        status = "need_more_data"
        reason = "No baseline has enough non-overlapping trades for a decision."
    else:
        status = "no_robust_candidate"
        reason = "Baselines did not survive non-overlap validation after assumed costs."

    stamp = utc_stamp()
    report_dir.mkdir(parents=True, exist_ok=True)
    trades_dir.mkdir(parents=True, exist_ok=True)

    trades_csv = trades_dir / f"stage2b_nonoverlap_trades_{stamp}.csv"
    pd.DataFrame([trade_to_dict(t) for t in all_trades]).to_csv(trades_csv, index=False)

    payload = {
        "ok": True,
        "stage": "stage2b_baseline_validation_nonoverlap",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_files": data_files,
        "cost_model": {
            **cost_cfg,
            "effective_roundtrip_cost_usd": cost_usd,
            "cost_warning": "Spread is assumed because Twelve Data does not provide broker bid/ask spread in this pipeline.",
        },
        "decision_config": {
            "min_nonoverlap_trades": min_trades,
            "require_positive_avg_net_usd": require_positive_avg_net,
            "require_positive_total_net_usd": require_positive_total_net,
            "max_allowed_drawdown_to_total_net_ratio": max_dd_ratio,
        },
        "decision": {
            "status": status,
            "reason": reason,
            "robust_candidate_count": int(len(robust_candidates)),
        },
        "summaries": summaries,
        "trades_csv": str(trades_csv),
    }

    summary_json = report_dir / f"stage2b_validation_summary_{stamp}.json"
    summary_md = report_dir / f"stage2b_validation_summary_{stamp}.md"
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
                "baseline_count": len(summaries),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
