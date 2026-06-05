from __future__ import annotations

import argparse
import itertools
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import yaml

from app.xauusd_candidate_eval import finalize_df
from app.xauusd_sqlite_store import connect, read_interval


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_db_interval(db_path: str, interval: str) -> pd.DataFrame:
    con = connect(db_path)
    try:
        df = read_interval(con, interval)
    finally:
        con.close()
    return finalize_df(df)


def window(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {"rows": 0, "start_utc": None, "end_utc": None}
    return {
        "rows": int(len(df)),
        "start_utc": df["time_utc"].min().isoformat(),
        "end_utc": df["time_utc"].max().isoformat(),
    }


def nonoverlap_filter(signals: list[Dict[str, Any]], cooldown_bars: int, horizon_bars: int) -> list[Dict[str, Any]]:
    accepted: list[Dict[str, Any]] = []
    next_allowed_idx = -1
    for sig in sorted(signals, key=lambda x: int(x["signal_idx"])):
        idx = int(sig["signal_idx"])
        if idx < next_allowed_idx:
            continue
        accepted.append(sig)
        next_allowed_idx = idx + int(horizon_bars) + int(cooldown_bars) + 1
    return accepted


def build_h1_signals(h1: pd.DataFrame, cfg: Dict[str, Any]) -> list[Dict[str, Any]]:
    candidate = cfg.get("candidate", {}) or {}
    sma_window = int(candidate.get("sma_window", 10))
    horizon_bars = int(candidate.get("horizon_bars", 12))
    min_distance = float(candidate.get("min_distance_usd", 10.0))
    cooldown_bars = int(candidate.get("cooldown_bars", 1))

    work = h1.copy()
    work["sma"] = work["close"].rolling(sma_window).mean()
    work["diff"] = work["close"] - work["sma"]

    raw: list[Dict[str, Any]] = []
    for i in range(sma_window, len(work) - horizon_bars - 1):
        sma = work.loc[i, "sma"]
        if pd.isna(sma):
            continue
        diff = float(work.loc[i, "diff"])
        if abs(diff) < min_distance:
            continue
        direction = 1 if diff > 0 else -1
        raw.append(
            {
                "signal_idx": int(i),
                "signal_time_utc": pd.to_datetime(work.loc[i, "time_utc"], utc=True).isoformat(),
                "entry_target_time_utc": pd.to_datetime(work.loc[i + 1, "time_utc"], utc=True).isoformat(),
                "planned_exit_target_time_utc": pd.to_datetime(work.loc[i + 1 + horizon_bars, "time_utc"], utc=True).isoformat(),
                "direction": int(direction),
                "direction_label": "long" if direction > 0 else "short",
                "signal_close": float(work.loc[i, "close"]),
                "sma": float(sma),
                "diff": diff,
                "reason": f"close_sma_diff_{diff:.4f}",
            }
        )

    return nonoverlap_filter(raw, cooldown_bars=cooldown_bars, horizon_bars=horizon_bars)


def to_ns(ts: str) -> int:
    return int(pd.Timestamp(ts).tz_convert("UTC").value)


def make_m1_arrays(m1: pd.DataFrame) -> Dict[str, np.ndarray]:
    return {
        "time_ns": m1["time_utc"].astype("int64").to_numpy(),
        "time_str": m1["time_utc"].astype(str).to_numpy(),
        "open": m1["open"].to_numpy(dtype=float),
        "high": m1["high"].to_numpy(dtype=float),
        "low": m1["low"].to_numpy(dtype=float),
        "close": m1["close"].to_numpy(dtype=float),
    }


def first_hit_index(mask: np.ndarray) -> Optional[int]:
    if mask.size == 0 or not bool(mask.any()):
        return None
    return int(np.argmax(mask))


def precompute_base_trades(signals: list[Dict[str, Any]], arrays: Dict[str, np.ndarray], tp_values: list[Any], sl_values: list[Any]) -> list[Dict[str, Any]]:
    time_ns = arrays["time_ns"]
    open_ = arrays["open"]
    high = arrays["high"]
    low = arrays["low"]
    close = arrays["close"]
    time_str = arrays["time_str"]

    tp_nums = [float(x) for x in tp_values if x is not None]
    sl_nums = [float(x) for x in sl_values if x is not None]

    out: list[Dict[str, Any]] = []
    for sig in signals:
        entry_target_ns = to_ns(sig["entry_target_time_utc"])
        exit_target_ns = to_ns(sig["planned_exit_target_time_utc"])
        entry_idx = int(np.searchsorted(time_ns, entry_target_ns, side="left"))
        exit_idx = int(np.searchsorted(time_ns, exit_target_ns, side="left"))

        if entry_idx >= len(time_ns) or exit_idx >= len(time_ns) or exit_idx <= entry_idx:
            continue

        direction = int(sig["direction"])
        entry_price = float(open_[entry_idx])
        path_high = high[entry_idx: exit_idx + 1]
        path_low = low[entry_idx: exit_idx + 1]

        tp_hits: Dict[str, Optional[int]] = {}
        sl_hits: Dict[str, Optional[int]] = {}

        for tp in tp_nums:
            mask = path_high >= entry_price + tp if direction > 0 else path_low <= entry_price - tp
            local = first_hit_index(mask)
            tp_hits[str(tp)] = None if local is None else int(entry_idx + local)

        for sl in sl_nums:
            mask = path_low <= entry_price - sl if direction > 0 else path_high >= entry_price + sl
            local = first_hit_index(mask)
            sl_hits[str(sl)] = None if local is None else int(entry_idx + local)

        out.append(
            {
                **sig,
                "entry_idx": entry_idx,
                "time_exit_idx": exit_idx,
                "entry_time_utc": str(time_str[entry_idx]),
                "time_exit_time_utc": str(time_str[exit_idx]),
                "entry_price": entry_price,
                "time_exit_price": float(close[exit_idx]),
                "tp_hits": tp_hits,
                "sl_hits": sl_hits,
            }
        )
    return out


def choose_exit(base: Dict[str, Any], tp: Optional[float], sl: Optional[float]) -> tuple[int, str, bool, float]:
    direction = int(base["direction"])
    entry = float(base["entry_price"])
    tp_idx = None if tp is None else base["tp_hits"].get(str(float(tp)))
    sl_idx = None if sl is None else base["sl_hits"].get(str(float(sl)))

    if tp_idx is None and sl_idx is None:
        return int(base["time_exit_idx"]), "time_exit", False, float(base["time_exit_price"])

    if tp_idx is not None and sl_idx is not None:
        if int(tp_idx) == int(sl_idx):
            exit_price = entry - float(sl) if direction > 0 else entry + float(sl)
            return int(sl_idx), "ambiguous_sl_first", True, float(exit_price)
        if int(sl_idx) < int(tp_idx):
            exit_price = entry - float(sl) if direction > 0 else entry + float(sl)
            return int(sl_idx), "stop_loss", False, float(exit_price)
        exit_price = entry + float(tp) if direction > 0 else entry - float(tp)
        return int(tp_idx), "take_profit", False, float(exit_price)

    if sl_idx is not None:
        exit_price = entry - float(sl) if direction > 0 else entry + float(sl)
        return int(sl_idx), "stop_loss", False, float(exit_price)

    exit_price = entry + float(tp) if direction > 0 else entry - float(tp)
    return int(tp_idx), "take_profit", False, float(exit_price)


def run_scenario(base_trades: list[Dict[str, Any]], arrays: Dict[str, np.ndarray], side: str, tp: Optional[float], sl: Optional[float], cost_usd: float) -> pd.DataFrame:
    high = arrays["high"]
    low = arrays["low"]
    time_str = arrays["time_str"]

    rows = []
    for b in base_trades:
        if side != "both" and b["direction_label"] != side:
            continue

        exit_idx, exit_reason, ambiguous, exit_price = choose_exit(b, tp, sl)
        entry_idx = int(b["entry_idx"])
        direction = int(b["direction"])
        entry_price = float(b["entry_price"])

        ph = high[entry_idx: exit_idx + 1]
        pl = low[entry_idx: exit_idx + 1]
        if direction > 0:
            mfe = float(ph.max() - entry_price)
            mae = float(entry_price - pl.min())
        else:
            mfe = float(entry_price - pl.min())
            mae = float(ph.max() - entry_price)

        raw = direction * (float(exit_price) - entry_price)
        net = raw - float(cost_usd)

        rows.append(
            {
                "scenario": f"side={side}|tp={tp}|sl={sl}",
                "side_filter": side,
                "tp_usd": tp,
                "sl_usd": sl,
                "signal_time_utc": b["signal_time_utc"],
                "entry_time_utc": b["entry_time_utc"],
                "exit_time_utc": str(time_str[exit_idx]),
                "direction": direction,
                "direction_label": b["direction_label"],
                "entry_price": entry_price,
                "exit_price": float(exit_price),
                "exit_reason": exit_reason,
                "ambiguous_exit": bool(ambiguous),
                "raw_usd": float(raw),
                "cost_usd": float(cost_usd),
                "net_usd": float(net),
                "mfe_usd": mfe,
                "mae_usd": mae,
                "m1_bars_in_trade": int(exit_idx - entry_idx + 1),
            }
        )
    return pd.DataFrame(rows)


def profit_factor(values: np.ndarray) -> Optional[float]:
    if values.size == 0:
        return None
    wins = values[values > 0]
    losses = values[values <= 0]
    loss_abs = abs(float(losses.sum()))
    if loss_abs == 0:
        return None
    return float(wins.sum() / loss_abs)


def max_drawdown(values: np.ndarray) -> float:
    if values.size == 0:
        return 0.0
    equity = np.cumsum(values)
    peak = np.maximum.accumulate(equity)
    return float(np.min(equity - peak))


def metrics(values: np.ndarray) -> Dict[str, Any]:
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return {
            "trade_count": 0,
            "total_net_usd": 0.0,
            "avg_net_usd": 0.0,
            "median_net_usd": 0.0,
            "win_rate": 0.0,
            "profit_factor": None,
            "max_drawdown_usd": 0.0,
        }
    return {
        "trade_count": int(values.size),
        "total_net_usd": float(values.sum()),
        "avg_net_usd": float(values.mean()),
        "median_net_usd": float(np.median(values)),
        "win_rate": float((values > 0).mean()),
        "profit_factor": profit_factor(values),
        "best_net_usd": float(values.max()),
        "worst_net_usd": float(values.min()),
        "max_drawdown_usd": max_drawdown(values),
    }


def fold_metrics(net_values: np.ndarray, folds: int = 5) -> Dict[str, Any]:
    n = len(net_values)
    rows = []
    for i in range(folds):
        start = int(i * n / folds)
        end = int((i + 1) * n / folds)
        m = metrics(net_values[start:end])
        m["fold"] = i + 1
        rows.append(m)
    positive = [x for x in rows if float(x.get("total_net_usd", 0.0)) > 0]
    return {
        "fold_count": int(len(rows)),
        "positive_fold_count": int(len(positive)),
        "positive_fold_ratio": float(len(positive) / max(len(rows), 1)),
        "folds": rows,
    }


def exit_reason_counts(trades: pd.DataFrame) -> Dict[str, int]:
    if trades.empty:
        return {}
    return {str(k): int(v) for k, v in trades["exit_reason"].value_counts().to_dict().items()}


def summarize_scenario(trades: pd.DataFrame, side: str, tp: Optional[float], sl: Optional[float], thresholds: Dict[str, Any]) -> Dict[str, Any]:
    net = trades["net_usd"].to_numpy(dtype=float) if not trades.empty else np.array([], dtype=float)
    base = metrics(net)
    folds = fold_metrics(net, folds=5)
    ambiguous_count = int(trades["ambiguous_exit"].sum()) if not trades.empty else 0
    ambiguous_ratio = float(ambiguous_count / max(int(base["trade_count"]), 1))

    pf = base.get("profit_factor")
    checks = {
        "min_trades": int(base["trade_count"]) >= int(thresholds.get("min_trades", 100)),
        "pf_min": pf is not None and float(pf) >= float(thresholds.get("min_profit_factor", 1.25)),
        "median_nonnegative": float(base["median_net_usd"]) >= float(thresholds.get("min_median_net_usd", 0.0)),
        "positive_fold_ratio": float(folds["positive_fold_ratio"]) >= float(thresholds.get("min_positive_fold_ratio", 0.8)),
        "ambiguous_exit_ratio_ok": ambiguous_ratio <= float(thresholds.get("max_ambiguous_exit_ratio", 0.05)),
    }

    return {
        "scenario": f"side={side}|tp={tp}|sl={sl}",
        "side_filter": side,
        "tp_usd": tp,
        "sl_usd": sl,
        "passed": bool(all(checks.values())),
        "checks": checks,
        "base": base,
        "folds": folds,
        "ambiguous_exit_count": ambiguous_count,
        "ambiguous_exit_ratio": ambiguous_ratio,
        "exit_reasons": exit_reason_counts(trades),
    }


def scenario_sort_key(row: Dict[str, Any]) -> tuple:
    b = row.get("base", {})
    pf = b.get("profit_factor")
    return (
        1 if row.get("passed") else 0,
        float(pf) if pf is not None else -999.0,
        float(b.get("median_net_usd", -999.0)),
        float(b.get("total_net_usd", -999.0)),
        -float(row.get("ambiguous_exit_ratio", 999.0)),
    )


def write_markdown(path: Path, payload: Dict[str, Any]) -> None:
    lines = [
        "# XAUUSD Stage 4B Quick TP/SL Scenario Lab",
        "",
        f"- Generated at UTC: `{payload['generated_at_utc']}`",
        f"- Decision: `{payload['decision']['status']}`",
        f"- Reason: `{payload['decision']['reason']}`",
        "",
        "## Top scenarios",
        "",
        "| Rank | Scenario | Passed | Trades | Total net | PF | Median | Folds+ | Ambig% |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for i, row in enumerate(payload["top_scenarios"], start=1):
        b = row["base"]
        pf = b.get("profit_factor")
        lines.append(
            "| {rank} | `{scenario}` | {passed} | {trades} | {total:.4f} | {pf} | {median:.4f} | {fold:.2f} | {ambig:.2%} |".format(
                rank=i,
                scenario=row["scenario"],
                passed=row["passed"],
                trades=b["trade_count"],
                total=float(b["total_net_usd"]),
                pf="n/a" if pf is None else f"{float(pf):.3f}",
                median=float(b["median_net_usd"]),
                fold=float(row["folds"]["positive_fold_ratio"]),
                ambig=float(row["ambiguous_exit_ratio"]),
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Quick Stage 4B TP/SL and side-filter scenario lab.")
    parser.add_argument("--config", default="configs/stage4b.yaml")
    parser.add_argument("--mt5-db", default=None)
    parser.add_argument("--report-dir", default=None)
    args = parser.parse_args()

    cfg = load_yaml(Path(args.config))
    candidate = cfg.get("candidate", {}) or {}
    data_cfg = cfg.get("data", {}) or {}
    cost_cfg = cfg.get("cost_model", {}) or {}
    grid = cfg.get("scenario_grid", {}) or {}
    thresholds = cfg.get("filters", {}) or {}
    output_cfg = cfg.get("output", {}) or {}

    mt5_db = args.mt5_db or data_cfg.get("mt5_db_path", "data/second_source/second_source.sqlite")
    signal_interval = str(candidate.get("signal_interval", "1h"))
    path_interval = str(candidate.get("path_interval", "1min"))
    report_dir = Path(args.report_dir or cfg.get("report_dir", "data/reports"))
    report_dir.mkdir(parents=True, exist_ok=True)

    cost_usd = float(cost_cfg.get("total_roundtrip_cost_usd", 0.35))

    print("Loading H1/M1 data...")
    h1 = read_db_interval(mt5_db, signal_interval)
    m1 = read_db_interval(mt5_db, path_interval)
    if h1.empty or m1.empty:
        raise FileNotFoundError(f"Need both {signal_interval} and {path_interval} rows in {mt5_db}")

    print(f"Loaded h1_rows={len(h1)} m1_rows={len(m1)}")
    signals = build_h1_signals(h1, cfg)
    print(f"Built signals={len(signals)}")

    sides = list(grid.get("sides", ["long", "both"]))
    tps = list(grid.get("take_profit_usd", [None, 18, 24]))
    sls = list(grid.get("stop_loss_usd", [None, 12, 15]))

    arrays = make_m1_arrays(m1)
    base_trades = precompute_base_trades(signals, arrays, tp_values=tps, sl_values=sls)
    print(f"Precomputed base_trades={len(base_trades)} scenarios={len(sides) * len(tps) * len(sls)}")

    all_summaries: list[Dict[str, Any]] = []
    for side, tp, sl in itertools.product(sides, tps, sls):
        trades = run_scenario(base_trades, arrays, str(side), tp, sl, cost_usd)
        summary = summarize_scenario(trades, str(side), tp, sl, thresholds)
        all_summaries.append(summary)

    ranked = sorted(all_summaries, key=scenario_sort_key, reverse=True)
    passed = [x for x in ranked if x.get("passed")]

    status = "stage4b_candidate_scenario_found" if passed else "stage4b_no_candidate_scenario"
    reason = (
        "At least one limited TP/SL side-filter scenario passed Stage 4B thresholds."
        if passed else
        "No limited TP/SL side-filter scenario passed Stage 4B thresholds."
    )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    summary_json = report_dir / f"stage4b_tpsl_scenario_summary_{stamp}.json"
    summary_md = report_dir / f"stage4b_tpsl_scenario_summary_{stamp}.md"
    scenarios_csv = report_dir / f"stage4b_tpsl_scenarios_{stamp}.csv"

    if bool(output_cfg.get("save_all_scenarios_csv", True)):
        flat_rows = []
        for row in ranked:
            b = row["base"]
            flat_rows.append({
                "scenario": row["scenario"],
                "side_filter": row["side_filter"],
                "tp_usd": row["tp_usd"],
                "sl_usd": row["sl_usd"],
                "passed": row["passed"],
                "trade_count": b["trade_count"],
                "total_net_usd": b["total_net_usd"],
                "avg_net_usd": b["avg_net_usd"],
                "median_net_usd": b["median_net_usd"],
                "win_rate": b["win_rate"],
                "profit_factor": b["profit_factor"],
                "max_drawdown_usd": b["max_drawdown_usd"],
                "positive_fold_ratio": row["folds"]["positive_fold_ratio"],
                "ambiguous_exit_count": row["ambiguous_exit_count"],
                "ambiguous_exit_ratio": row["ambiguous_exit_ratio"],
            })
        pd.DataFrame(flat_rows).to_csv(scenarios_csv, index=False)

    payload = {
        "ok": True,
        "stage": "stage4b_quick_fast_tpsl_side_filter_scenario_lab",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate": {
            "family": candidate.get("family"),
            "variant": candidate.get("variant"),
            "signal_interval": signal_interval,
            "path_interval": path_interval,
        },
        "mt5_db_path": mt5_db,
        "data_windows": {
            "h1": window(h1),
            "m1": window(m1),
        },
        "signal_count": int(len(signals)),
        "base_trade_count": int(len(base_trades)),
        "scenario_count": int(len(all_summaries)),
        "passed_scenario_count": int(len(passed)),
        "thresholds": thresholds,
        "top_scenarios": ranked[: int(output_cfg.get("top_n", 12))],
        "passed_scenarios": passed[: int(output_cfg.get("top_n", 12))],
        "scenarios_csv": str(scenarios_csv) if bool(output_cfg.get("save_all_scenarios_csv", True)) else None,
        "decision": {
            "status": status,
            "reason": reason,
        },
        "warning": "Diagnostic only. TP/SL not finalized. No paper-order. No live trading.",
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
                "scenarios_csv": payload["scenarios_csv"],
                "signal_count": len(signals),
                "base_trade_count": len(base_trades),
                "scenario_count": len(all_summaries),
                "passed_scenario_count": len(passed),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
