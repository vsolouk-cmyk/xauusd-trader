from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
import yaml


@dataclass(frozen=True)
class Trade:
    baseline: str
    interval: str
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


def safe_name(value: str) -> str:
    return (
        str(value)
        .replace("/", "_")
        .replace(":", "_")
        .replace(" ", "_")
        .replace("-", "_")
        .replace(".", "_")
    )


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


def load_interval_df(data_dir: Path, interval: str) -> tuple[Path, pd.DataFrame]:
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


def make_trade(
    baseline: str,
    interval: str,
    df: pd.DataFrame,
    entry_idx: int,
    exit_idx: int,
    direction: int,
    cost_usd: float,
    reason: str,
) -> Optional[Trade]:
    if entry_idx < 0 or exit_idx >= len(df) or exit_idx <= entry_idx:
        return None
    if direction not in {-1, 1}:
        return None

    entry_price = float(df.loc[entry_idx, "close"])
    exit_price = float(df.loc[exit_idx, "close"])
    raw_usd = direction * (exit_price - entry_price)
    net_usd = raw_usd - cost_usd

    return Trade(
        baseline=baseline,
        interval=interval,
        entry_time_utc=pd.Timestamp(df.loc[entry_idx, "time_utc"]).isoformat(),
        exit_time_utc=pd.Timestamp(df.loc[exit_idx, "time_utc"]).isoformat(),
        direction=direction,
        direction_label="long" if direction == 1 else "short",
        entry_price=entry_price,
        exit_price=exit_price,
        raw_usd=float(raw_usd),
        cost_usd=float(cost_usd),
        net_usd=float(net_usd),
        reason=reason,
    )


def baseline_higher_timeframe_sma20_trend(
    df: pd.DataFrame,
    interval: str,
    cost_usd: float,
    sma_window: int,
    horizon_bars: int,
) -> List[Trade]:
    baseline = "higher_timeframe_sma20_trend"
    work = df.copy()
    work["sma"] = work["close"].rolling(int(sma_window)).mean()
    trades: List[Trade] = []

    for i in range(len(work) - int(horizon_bars)):
        sma = work.loc[i, "sma"]
        if pd.isna(sma):
            continue
        close = float(work.loc[i, "close"])
        direction = 1 if close > float(sma) else -1
        trade = make_trade(
            baseline,
            interval,
            work,
            entry_idx=i,
            exit_idx=i + int(horizon_bars),
            direction=direction,
            cost_usd=cost_usd,
            reason=f"close_vs_sma{sma_window}",
        )
        if trade:
            trades.append(trade)

    return trades


def baseline_session_momentum(
    df: pd.DataFrame,
    interval: str,
    cost_usd: float,
    horizon_bars: int,
    sessions: Iterable[str],
) -> List[Trade]:
    baseline = "session_momentum_15min"
    allowed = set(sessions)
    work = df.copy()
    work["prev_return"] = work["close"].diff()
    trades: List[Trade] = []

    for i in range(1, len(work) - int(horizon_bars)):
        if str(work.loc[i, "session_utc"]) not in allowed:
            continue
        prev_return = float(work.loc[i, "prev_return"])
        if prev_return == 0:
            continue
        direction = 1 if prev_return > 0 else -1
        trade = make_trade(
            baseline,
            interval,
            work,
            entry_idx=i,
            exit_idx=i + int(horizon_bars),
            direction=direction,
            cost_usd=cost_usd,
            reason="prior_candle_momentum_in_active_session",
        )
        if trade:
            trades.append(trade)

    return trades


def baseline_atr_range_expansion(
    df: pd.DataFrame,
    interval: str,
    cost_usd: float,
    atr_window: int,
    range_multiplier: float,
    horizon_bars: int,
) -> List[Trade]:
    baseline = "atr_range_expansion_15min"
    work = df.copy()
    work["bar_range"] = work["high"] - work["low"]
    work["avg_range"] = work["bar_range"].rolling(int(atr_window)).mean()
    trades: List[Trade] = []

    for i in range(len(work) - int(horizon_bars)):
        avg_range = work.loc[i, "avg_range"]
        if pd.isna(avg_range) or avg_range <= 0:
            continue
        bar_range = float(work.loc[i, "bar_range"])
        if bar_range < float(range_multiplier) * float(avg_range):
            continue
        candle_body = float(work.loc[i, "close"] - work.loc[i, "open"])
        if candle_body == 0:
            continue
        direction = 1 if candle_body > 0 else -1
        trade = make_trade(
            baseline,
            interval,
            work,
            entry_idx=i,
            exit_idx=i + int(horizon_bars),
            direction=direction,
            cost_usd=cost_usd,
            reason=f"range_gt_{range_multiplier}x_avg_range{atr_window}",
        )
        if trade:
            trades.append(trade)

    return trades


def baseline_asia_range_breakout(
    df: pd.DataFrame,
    interval: str,
    cost_usd: float,
    asia_start_hour: int,
    asia_end_hour: int,
    trade_start_hour: int,
    trade_end_hour: int,
    horizon_bars: int,
    max_trades_per_day: int,
) -> List[Trade]:
    baseline = "asia_range_breakout_5min"
    trades: List[Trade] = []

    for date, day in df.groupby("date_utc", sort=True):
        asia = day[(day["hour_utc"] >= asia_start_hour) & (day["hour_utc"] < asia_end_hour)]
        trade_window = day[(day["hour_utc"] >= trade_start_hour) & (day["hour_utc"] < trade_end_hour)]

        if asia.empty or trade_window.empty:
            continue

        asia_high = float(asia["high"].max())
        asia_low = float(asia["low"].min())
        day_trade_count = 0

        for idx in trade_window.index:
            if day_trade_count >= int(max_trades_per_day):
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

            trade = make_trade(
                baseline,
                interval,
                df,
                entry_idx=int(idx),
                exit_idx=int(idx) + int(horizon_bars),
                direction=direction,
                cost_usd=cost_usd,
                reason=reason,
            )
            if trade:
                trades.append(trade)
                day_trade_count += 1

    return trades


def baseline_london_open_breakout(
    df: pd.DataFrame,
    interval: str,
    cost_usd: float,
    open_start_hour: int,
    open_end_hour: int,
    trade_start_hour: int,
    trade_end_hour: int,
    horizon_bars: int,
    max_trades_per_day: int,
) -> List[Trade]:
    baseline = "london_open_breakout_5min"
    trades: List[Trade] = []

    for date, day in df.groupby("date_utc", sort=True):
        open_range = day[(day["hour_utc"] >= open_start_hour) & (day["hour_utc"] < open_end_hour)]
        trade_window = day[(day["hour_utc"] >= trade_start_hour) & (day["hour_utc"] < trade_end_hour)]

        if open_range.empty or trade_window.empty:
            continue

        open_high = float(open_range["high"].max())
        open_low = float(open_range["low"].min())
        day_trade_count = 0

        for idx in trade_window.index:
            if day_trade_count >= int(max_trades_per_day):
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

            trade = make_trade(
                baseline,
                interval,
                df,
                entry_idx=int(idx),
                exit_idx=int(idx) + int(horizon_bars),
                direction=direction,
                cost_usd=cost_usd,
                reason=reason,
            )
            if trade:
                trades.append(trade)
                day_trade_count += 1

    return trades


def trade_to_dict(trade: Trade) -> Dict[str, Any]:
    return {
        "baseline": trade.baseline,
        "interval": trade.interval,
        "entry_time_utc": trade.entry_time_utc,
        "exit_time_utc": trade.exit_time_utc,
        "direction": trade.direction,
        "direction_label": trade.direction_label,
        "entry_price": trade.entry_price,
        "exit_price": trade.exit_price,
        "raw_usd": trade.raw_usd,
        "cost_usd": trade.cost_usd,
        "net_usd": trade.net_usd,
        "reason": trade.reason,
    }


def max_drawdown(values: List[float]) -> float:
    if not values:
        return 0.0
    equity = pd.Series(values).cumsum()
    peak = equity.cummax()
    dd = equity - peak
    return float(dd.min())


def summarize_trades(
    baseline: str,
    trades: List[Trade],
    min_trades: int,
    require_positive_avg_net: bool,
    require_positive_total_net: bool,
) -> Dict[str, Any]:
    if not trades:
        return {
            "baseline": baseline,
            "trade_count": 0,
            "sample_ok": False,
            "candidate": False,
            "reason": "no_trades",
        }

    raw = [t.raw_usd for t in trades]
    net = [t.net_usd for t in trades]
    wins = [x for x in net if x > 0]
    losses = [x for x in net if x <= 0]

    total_loss_abs = abs(sum(losses))
    profit_factor = None if total_loss_abs == 0 else float(sum(wins) / total_loss_abs)

    sample_ok = len(trades) >= int(min_trades)
    avg_net = float(sum(net) / len(net))
    total_net = float(sum(net))

    candidate = sample_ok
    if require_positive_avg_net:
        candidate = candidate and avg_net > 0
    if require_positive_total_net:
        candidate = candidate and total_net > 0

    reason = "candidate" if candidate else "failed"
    if not sample_ok:
        reason = "insufficient_trades"
    elif avg_net <= 0:
        reason = "negative_or_zero_avg_net_usd"
    elif total_net <= 0:
        reason = "negative_or_zero_total_net_usd"

    return {
        "baseline": baseline,
        "trade_count": int(len(trades)),
        "sample_ok": bool(sample_ok),
        "candidate": bool(candidate),
        "reason": reason,
        "win_rate": float(len(wins) / len(net)),
        "avg_raw_usd": float(sum(raw) / len(raw)),
        "avg_net_usd": avg_net,
        "median_net_usd": float(pd.Series(net).median()),
        "total_net_usd": total_net,
        "best_net_usd": float(max(net)),
        "worst_net_usd": float(min(net)),
        "max_drawdown_usd": max_drawdown(net),
        "profit_factor": profit_factor,
    }


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.replace(path)


def write_markdown(path: Path, payload: Dict[str, Any]) -> None:
    lines = []
    lines.append("# XAUUSD Stage 2A Baseline Lab")
    lines.append("")
    lines.append(f"- Generated at UTC: `{payload['generated_at_utc']}`")
    lines.append(f"- Overall decision: `{payload['decision']['status']}`")
    lines.append(f"- Decision reason: `{payload['decision']['reason']}`")
    lines.append("")
    lines.append("## Important limitation")
    lines.append("")
    lines.append("This is not a trading approval. This is an early diagnostic baseline lab.")
    lines.append("Twelve Data does not provide broker bid/ask spread in this pipeline, so costs are assumed conservatively.")
    lines.append("")
    lines.append("## Cost model")
    lines.append("")
    for k, v in payload.get("cost_model", {}).items():
        lines.append(f"- `{k}`: `{v}`")
    lines.append("")
    lines.append("## Baseline metrics")
    lines.append("")
    lines.append("| Baseline | Trades | Sample OK | Candidate | Reason | Win rate | Avg net USD | Total net USD | Max DD USD |")
    lines.append("|---|---:|---:|---:|---|---:|---:|---:|---:|")
    for s in payload["summaries"]:
        lines.append(
            "| {baseline} | {trade_count} | {sample_ok} | {candidate} | {reason} | {win_rate:.3f} | {avg_net:.4f} | {total_net:.4f} | {dd:.4f} |".format(
                baseline=s.get("baseline"),
                trade_count=s.get("trade_count", 0),
                sample_ok=s.get("sample_ok", False),
                candidate=s.get("candidate", False),
                reason=s.get("reason", ""),
                win_rate=float(s.get("win_rate", 0.0)),
                avg_net=float(s.get("avg_net_usd", 0.0)),
                total_net=float(s.get("total_net_usd", 0.0)),
                dd=float(s.get("max_drawdown_usd", 0.0)),
            )
        )
    lines.append("")
    lines.append("## Data files used")
    lines.append("")
    for interval, file_path in payload.get("data_files", {}).items():
        lines.append(f"- `{interval}`: `{file_path}`")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Stage 2A simple baseline lab on latest normalized XAUUSD data.")
    parser.add_argument("--config", default="configs/baselines.yaml")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--report-dir", default=None)
    args = parser.parse_args()

    cfg = load_yaml(Path(args.config))
    data_dir = Path(args.data_dir or cfg.get("data_dir", "data/normalized"))
    report_dir = Path(args.report_dir or cfg.get("report_dir", "data/reports"))
    trades_dir = Path(cfg.get("trades_dir", "data/reports/baseline_trades"))

    cost_cfg = cfg.get("cost_model", {}) or {}
    cost_usd = float(
        cost_cfg.get(
            "total_roundtrip_cost_usd",
            float(cost_cfg.get("assumed_spread_usd", 0.30)) + float(cost_cfg.get("assumed_slippage_usd", 0.05)),
        )
    )

    decision_cfg = cfg.get("decision", {}) or {}
    min_trades = int(decision_cfg.get("min_trades_per_baseline", 20))
    require_positive_avg_net = bool(decision_cfg.get("require_positive_avg_net_usd", True))
    require_positive_total_net = bool(decision_cfg.get("require_positive_total_net_usd", True))

    baseline_cfgs = cfg.get("baselines", {}) or {}

    required_intervals = sorted({str(b.get("interval")) for b in baseline_cfgs.values() if b.get("enabled", True)})
    data_by_interval: Dict[str, pd.DataFrame] = {}
    data_files: Dict[str, str] = {}

    for interval in required_intervals:
        path, df = load_interval_df(data_dir, interval)
        data_by_interval[interval] = df
        data_files[interval] = str(path)

    all_trades: List[Trade] = []
    trades_by_baseline: Dict[str, List[Trade]] = {}

    b = baseline_cfgs.get("higher_timeframe_sma20_trend", {})
    if b.get("enabled", True):
        interval = str(b.get("interval", "1h"))
        trades = baseline_higher_timeframe_sma20_trend(
            data_by_interval[interval],
            interval,
            cost_usd,
            sma_window=int(b.get("sma_window", 20)),
            horizon_bars=int(b.get("horizon_bars", 3)),
        )
        trades_by_baseline["higher_timeframe_sma20_trend"] = trades
        all_trades.extend(trades)

    b = baseline_cfgs.get("session_momentum_15min", {})
    if b.get("enabled", True):
        interval = str(b.get("interval", "15min"))
        trades = baseline_session_momentum(
            data_by_interval[interval],
            interval,
            cost_usd,
            horizon_bars=int(b.get("horizon_bars", 4)),
            sessions=b.get("sessions", ["london", "london_ny_overlap", "new_york"]),
        )
        trades_by_baseline["session_momentum_15min"] = trades
        all_trades.extend(trades)

    b = baseline_cfgs.get("atr_range_expansion_15min", {})
    if b.get("enabled", True):
        interval = str(b.get("interval", "15min"))
        trades = baseline_atr_range_expansion(
            data_by_interval[interval],
            interval,
            cost_usd,
            atr_window=int(b.get("atr_window", 20)),
            range_multiplier=float(b.get("range_multiplier", 1.5)),
            horizon_bars=int(b.get("horizon_bars", 4)),
        )
        trades_by_baseline["atr_range_expansion_15min"] = trades
        all_trades.extend(trades)

    b = baseline_cfgs.get("asia_range_breakout_5min", {})
    if b.get("enabled", True):
        interval = str(b.get("interval", "5min"))
        trades = baseline_asia_range_breakout(
            data_by_interval[interval],
            interval,
            cost_usd,
            asia_start_hour=int(b.get("asia_start_hour_utc", 0)),
            asia_end_hour=int(b.get("asia_end_hour_utc", 7)),
            trade_start_hour=int(b.get("trade_start_hour_utc", 7)),
            trade_end_hour=int(b.get("trade_end_hour_utc", 13)),
            horizon_bars=int(b.get("horizon_bars", 12)),
            max_trades_per_day=int(b.get("max_trades_per_day", 1)),
        )
        trades_by_baseline["asia_range_breakout_5min"] = trades
        all_trades.extend(trades)

    b = baseline_cfgs.get("london_open_breakout_5min", {})
    if b.get("enabled", True):
        interval = str(b.get("interval", "5min"))
        trades = baseline_london_open_breakout(
            data_by_interval[interval],
            interval,
            cost_usd,
            open_start_hour=int(b.get("open_start_hour_utc", 7)),
            open_end_hour=int(b.get("open_end_hour_utc", 8)),
            trade_start_hour=int(b.get("trade_start_hour_utc", 8)),
            trade_end_hour=int(b.get("trade_end_hour_utc", 13)),
            horizon_bars=int(b.get("horizon_bars", 12)),
            max_trades_per_day=int(b.get("max_trades_per_day", 1)),
        )
        trades_by_baseline["london_open_breakout_5min"] = trades
        all_trades.extend(trades)

    summaries = [
        summarize_trades(
            name,
            trades,
            min_trades=min_trades,
            require_positive_avg_net=require_positive_avg_net,
            require_positive_total_net=require_positive_total_net,
        )
        for name, trades in sorted(trades_by_baseline.items())
    ]

    candidates = [s for s in summaries if s.get("candidate")]
    any_sample_ok = any(s.get("sample_ok") for s in summaries)

    if candidates:
        status = "candidate_baseline_found"
        reason = "At least one simple baseline passed sample and net-cost filters."
    elif not any_sample_ok:
        status = "need_more_data"
        reason = "No baseline has enough trades for a decision."
    else:
        status = "no_candidate"
        reason = "At least one baseline had enough trades, but none was positive after assumed costs."

    stamp = utc_stamp()
    trades_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    trades_csv = trades_dir / f"stage2a_baseline_trades_{stamp}.csv"
    pd.DataFrame([trade_to_dict(t) for t in all_trades]).to_csv(trades_csv, index=False)

    payload = {
        "ok": True,
        "stage": "stage2a_baseline_lab",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_files": data_files,
        "cost_model": {
            **cost_cfg,
            "effective_roundtrip_cost_usd": cost_usd,
            "cost_warning": "Spread is assumed because Twelve Data does not provide broker bid/ask spread in this pipeline.",
        },
        "decision_config": {
            "min_trades_per_baseline": min_trades,
            "require_positive_avg_net_usd": require_positive_avg_net,
            "require_positive_total_net_usd": require_positive_total_net,
        },
        "decision": {
            "status": status,
            "reason": reason,
            "candidate_count": int(len(candidates)),
        },
        "summaries": summaries,
        "trades_csv": str(trades_csv),
    }

    summary_json = report_dir / f"stage2a_baseline_summary_{stamp}.json"
    summary_md = report_dir / f"stage2a_baseline_summary_{stamp}.md"
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
