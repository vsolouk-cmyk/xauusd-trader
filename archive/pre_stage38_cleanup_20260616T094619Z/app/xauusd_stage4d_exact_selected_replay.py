from __future__ import annotations

import argparse
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


def replay_signal(
    sig: Dict[str, Any],
    arrays: Dict[str, np.ndarray],
    side_filter: str,
    tp_usd: Optional[float],
    sl_usd: Optional[float],
    cost_usd: float,
) -> Optional[Dict[str, Any]]:
    if side_filter != "both" and sig["direction_label"] != side_filter:
        return None

    time_ns = arrays["time_ns"]
    time_str = arrays["time_str"]
    open_ = arrays["open"]
    high = arrays["high"]
    low = arrays["low"]
    close = arrays["close"]

    entry_target_ns = to_ns(sig["entry_target_time_utc"])
    exit_target_ns = to_ns(sig["planned_exit_target_time_utc"])

    entry_idx = int(np.searchsorted(time_ns, entry_target_ns, side="left"))
    time_exit_idx = int(np.searchsorted(time_ns, exit_target_ns, side="left"))

    if entry_idx >= len(time_ns) or time_exit_idx >= len(time_ns) or time_exit_idx <= entry_idx:
        return None

    direction = int(sig["direction"])
    entry_price = float(open_[entry_idx])
    path_high = high[entry_idx: time_exit_idx + 1]
    path_low = low[entry_idx: time_exit_idx + 1]

    tp_idx: Optional[int] = None
    sl_idx: Optional[int] = None

    if tp_usd is not None:
        if direction > 0:
            tp_mask = path_high >= entry_price + float(tp_usd)
        else:
            tp_mask = path_low <= entry_price - float(tp_usd)
        local = first_hit_index(tp_mask)
        tp_idx = None if local is None else int(entry_idx + local)

    if sl_usd is not None:
        if direction > 0:
            sl_mask = path_low <= entry_price - float(sl_usd)
        else:
            sl_mask = path_high >= entry_price + float(sl_usd)
        local = first_hit_index(sl_mask)
        sl_idx = None if local is None else int(entry_idx + local)

    exit_idx = time_exit_idx
    exit_reason = "time_exit"
    ambiguous_exit = False
    exit_price = float(close[time_exit_idx])

    if tp_idx is not None and sl_idx is not None:
        if tp_idx == sl_idx:
            exit_idx = sl_idx
            exit_reason = "ambiguous_sl_first"
            ambiguous_exit = True
            exit_price = entry_price - float(sl_usd) if direction > 0 else entry_price + float(sl_usd)
        elif sl_idx < tp_idx:
            exit_idx = sl_idx
            exit_reason = "stop_loss"
            exit_price = entry_price - float(sl_usd) if direction > 0 else entry_price + float(sl_usd)
        else:
            exit_idx = tp_idx
            exit_reason = "take_profit"
            exit_price = entry_price + float(tp_usd) if direction > 0 else entry_price - float(tp_usd)
    elif sl_idx is not None:
        exit_idx = sl_idx
        exit_reason = "stop_loss"
        exit_price = entry_price - float(sl_usd) if direction > 0 else entry_price + float(sl_usd)
    elif tp_idx is not None:
        exit_idx = tp_idx
        exit_reason = "take_profit"
        exit_price = entry_price + float(tp_usd) if direction > 0 else entry_price - float(tp_usd)

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

    entry_time = str(time_str[entry_idx])
    exit_time = str(time_str[exit_idx])
    entry_ts = pd.to_datetime(entry_time, utc=True)

    return {
        **sig,
        "scenario": f"side={side_filter}|tp={tp_usd}|sl={sl_usd}",
        "side_filter": side_filter,
        "tp_usd": tp_usd,
        "sl_usd": sl_usd,
        "entry_time_utc": entry_time,
        "exit_time_utc": exit_time,
        "entry_hour_utc": int(entry_ts.hour),
        "entry_month_utc": entry_ts.strftime("%Y-%m"),
        "entry_year_utc": int(entry_ts.year),
        "session_utc": session_name(int(entry_ts.hour)),
        "entry_price": entry_price,
        "exit_price": float(exit_price),
        "exit_reason": exit_reason,
        "ambiguous_exit": bool(ambiguous_exit),
        "raw_usd": float(raw),
        "cost_usd": float(cost_usd),
        "net_usd": float(net),
        "mfe_usd": mfe,
        "mae_usd": mae,
        "m1_bars_in_trade": int(exit_idx - entry_idx + 1),
    }


def session_name(hour: int) -> str:
    if 0 <= hour < 7:
        return "asia"
    if 7 <= hour < 13:
        return "london"
    if 13 <= hour < 17:
        return "london_ny_overlap"
    if 17 <= hour < 22:
        return "new_york"
    return "other"


def replay_scenario(
    signals: list[Dict[str, Any]],
    arrays: Dict[str, np.ndarray],
    side_filter: str,
    tp_usd: Optional[float],
    sl_usd: Optional[float],
    cost_usd: float,
) -> pd.DataFrame:
    rows = []
    for sig in signals:
        row = replay_signal(sig, arrays, side_filter, tp_usd, sl_usd, cost_usd)
        if row is not None:
            rows.append(row)
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("entry_time_utc").reset_index(drop=True)
    return df


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


def metrics_from_net(net: np.ndarray) -> Dict[str, Any]:
    net = np.asarray(net, dtype=float)
    if net.size == 0:
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
        "trade_count": int(net.size),
        "total_net_usd": float(net.sum()),
        "avg_net_usd": float(net.mean()),
        "median_net_usd": float(np.median(net)),
        "win_rate": float((net > 0).mean()),
        "profit_factor": profit_factor(net),
        "best_net_usd": float(net.max()),
        "worst_net_usd": float(net.min()),
        "max_drawdown_usd": max_drawdown(net),
    }


def scenario_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return metrics_from_net(np.array([], dtype=float))
    out = metrics_from_net(df["net_usd"].to_numpy(dtype=float))
    out["ambiguous_exit_count"] = int(df["ambiguous_exit"].sum())
    out["ambiguous_exit_ratio"] = float(df["ambiguous_exit"].sum() / max(len(df), 1))
    out["exit_reasons"] = {str(k): int(v) for k, v in df["exit_reason"].value_counts().to_dict().items()}
    return out


def fold_breakdown(df: pd.DataFrame, folds: int = 5) -> Dict[str, Any]:
    work = df.sort_values("entry_time_utc").reset_index(drop=True)
    n = len(work)
    rows = []
    for i in range(folds):
        start = int(i * n / folds)
        end = int((i + 1) * n / folds)
        m = metrics_from_net(work.iloc[start:end]["net_usd"].to_numpy(dtype=float))
        m["fold"] = i + 1
        rows.append(m)
    positives = [r for r in rows if float(r["total_net_usd"]) > 0]
    return {
        "fold_count": len(rows),
        "positive_fold_count": len(positives),
        "positive_fold_ratio": float(len(positives) / max(len(rows), 1)),
        "folds": rows,
    }


def group_breakdown(df: pd.DataFrame, group_col: str) -> Dict[str, Any]:
    if df.empty:
        return {}
    out = {}
    for k, g in df.groupby(group_col, sort=True):
        out[str(k)] = metrics_from_net(g["net_usd"].to_numpy(dtype=float))
    return out


def cost_stress(df: pd.DataFrame, multipliers: list[float], base_cost: float) -> list[Dict[str, Any]]:
    raw = df["raw_usd"].to_numpy(dtype=float) if not df.empty else np.array([], dtype=float)
    rows = []
    for m in multipliers:
        net = raw - (float(base_cost) * float(m))
        row = metrics_from_net(net)
        row["cost_multiplier"] = float(m)
        rows.append(row)
    return rows


def decide(selected: Dict[str, Any], reference: Dict[str, Any], folds: Dict[str, Any], cost_rows: list[Dict[str, Any]], cfg: Dict[str, Any]) -> Dict[str, Any]:
    th = cfg.get("thresholds", {}) or {}
    pf = selected.get("profit_factor")
    checks = {
        "min_trades": int(selected.get("trade_count", 0)) >= int(th.get("min_trades", 100)),
        "pf_min": pf is not None and float(pf) >= float(th.get("min_profit_factor", 1.25)),
        "median_nonnegative": float(selected.get("median_net_usd", 0.0)) >= float(th.get("min_median_net_usd", 0.0)),
        "positive_fold_ratio": float(folds.get("positive_fold_ratio", 0.0)) >= float(th.get("min_positive_fold_ratio", 0.8)),
        "ambiguous_exit_ratio_ok": float(selected.get("ambiguous_exit_ratio", 999.0)) <= float(th.get("max_ambiguous_exit_ratio", 0.05)),
    }

    if bool(th.get("require_drawdown_better_than_reference", True)):
        checks["drawdown_better_than_reference"] = abs(float(selected.get("max_drawdown_usd", 0.0))) < abs(float(reference.get("max_drawdown_usd", 0.0)))

    by_mult = {float(r["cost_multiplier"]): r for r in cost_rows}
    if 2.0 in by_mult:
        checks["cost_x2_positive"] = float(by_mult[2.0].get("total_net_usd", 0.0)) > float(th.get("min_cost_x2_total_net_usd", 0.0))
    if 3.0 in by_mult:
        checks["cost_x3_positive"] = float(by_mult[3.0].get("total_net_usd", 0.0)) > float(th.get("min_cost_x3_total_net_usd", 0.0))

    if bool(th.get("require_recent_half_positive", True)):
        recent = folds.get("folds", [])[-2:]
        checks["recent_half_positive"] = all(float(x.get("total_net_usd", 0.0)) > 0 for x in recent)

    passed = all(checks.values())
    return {
        "status": "stage4d_exact_selected_replay_pass" if passed else "stage4d_exact_selected_replay_fail",
        "reason": "Selected scenario passed exact trade-level replay checks." if passed else "Selected scenario failed exact trade-level replay checks.",
        "checks": checks,
    }


def write_markdown(path: Path, payload: Dict[str, Any]) -> None:
    sel = payload["selected_metrics"]
    ref = payload["reference_metrics"]
    lines = [
        "# XAUUSD Stage 4D Exact Selected Replay",
        "",
        f"- Generated at UTC: `{payload['generated_at_utc']}`",
        f"- Decision: `{payload['decision']['status']}`",
        f"- Reason: `{payload['decision']['reason']}`",
        "",
        "## Selected scenario",
        "",
        f"- scenario: `{payload['selected_scenario']}`",
        f"- trades: `{sel['trade_count']}`",
        f"- total net: `{sel['total_net_usd']}`",
        f"- PF: `{sel['profit_factor']}`",
        f"- median: `{sel['median_net_usd']}`",
        f"- max DD: `{sel['max_drawdown_usd']}`",
        f"- ambiguous ratio: `{sel['ambiguous_exit_ratio']}`",
        "",
        "## Reference scenario",
        "",
        f"- scenario: `{payload['reference_scenario']}`",
        f"- total net: `{ref['total_net_usd']}`",
        f"- PF: `{ref['profit_factor']}`",
        f"- max DD: `{ref['max_drawdown_usd']}`",
        "",
        "## Cost stress",
        "",
        "| Cost x | Total net | PF | Median | Max DD |",
        "|---:|---:|---:|---:|---:|",
    ]
    for row in payload["cost_stress"]:
        pf = row.get("profit_factor")
        lines.append(
            "| {x} | {total:.4f} | {pf} | {median:.4f} | {dd:.4f} |".format(
                x=row["cost_multiplier"],
                total=float(row["total_net_usd"]),
                pf="n/a" if pf is None else f"{float(pf):.3f}",
                median=float(row["median_net_usd"]),
                dd=float(row["max_drawdown_usd"]),
            )
        )
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4D exact selected-scenario replay.")
    parser.add_argument("--config", default="configs/stage4d.yaml")
    parser.add_argument("--mt5-db", default=None)
    parser.add_argument("--report-dir", default=None)
    args = parser.parse_args()

    cfg = load_yaml(Path(args.config))
    candidate = cfg.get("candidate", {}) or {}
    selected_cfg = cfg.get("selected_scenario", {}) or {}
    reference_cfg = cfg.get("reference_scenario", {}) or {}
    data_cfg = cfg.get("data", {}) or {}
    cost_cfg = cfg.get("cost_model", {}) or {}
    output_cfg = cfg.get("output", {}) or {}

    mt5_db = args.mt5_db or data_cfg.get("mt5_db_path", "data/second_source/second_source.sqlite")
    signal_interval = str(candidate.get("signal_interval", "1h"))
    path_interval = str(candidate.get("path_interval", "1min"))
    report_dir = Path(args.report_dir or cfg.get("report_dir", "data/reports"))
    report_dir.mkdir(parents=True, exist_ok=True)

    base_cost = float(cost_cfg.get("total_roundtrip_cost_usd", 0.35))
    multipliers = [float(x) for x in cost_cfg.get("cost_multipliers", [1, 2, 3, 4])]

    print("Loading H1/M1 data...")
    h1 = read_db_interval(mt5_db, signal_interval)
    m1 = read_db_interval(mt5_db, path_interval)
    print(f"Loaded h1_rows={len(h1)} m1_rows={len(m1)}")

    signals = build_h1_signals(h1, cfg)
    arrays = make_m1_arrays(m1)
    print(f"Built signals={len(signals)}")

    selected_df = replay_scenario(
        signals=signals,
        arrays=arrays,
        side_filter=str(selected_cfg.get("side_filter", "long")),
        tp_usd=selected_cfg.get("take_profit_usd"),
        sl_usd=selected_cfg.get("stop_loss_usd"),
        cost_usd=base_cost,
    )

    reference_df = replay_scenario(
        signals=signals,
        arrays=arrays,
        side_filter=str(reference_cfg.get("side_filter", "long")),
        tp_usd=reference_cfg.get("take_profit_usd"),
        sl_usd=reference_cfg.get("stop_loss_usd"),
        cost_usd=base_cost,
    )

    selected_metrics = scenario_metrics(selected_df)
    reference_metrics = scenario_metrics(reference_df)
    folds = fold_breakdown(selected_df)
    stress_rows = cost_stress(selected_df, multipliers=multipliers, base_cost=base_cost)
    monthly = group_breakdown(selected_df, "entry_month_utc")
    yearly = group_breakdown(selected_df, "entry_year_utc")
    session = group_breakdown(selected_df, "session_utc")
    exit_reasons = selected_metrics.get("exit_reasons", {})

    decision = decide(selected_metrics, reference_metrics, folds, stress_rows, cfg)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    summary_json = report_dir / f"stage4d_exact_selected_replay_summary_{stamp}.json"
    summary_md = report_dir / f"stage4d_exact_selected_replay_summary_{stamp}.md"
    selected_csv = report_dir / f"stage4d_selected_trades_{stamp}.csv"
    reference_csv = report_dir / f"stage4d_reference_trades_{stamp}.csv"

    if bool(output_cfg.get("save_selected_trades_csv", True)):
        selected_df.to_csv(selected_csv, index=False)
    if bool(output_cfg.get("save_reference_trades_csv", True)):
        reference_df.to_csv(reference_csv, index=False)

    selected_scenario = f"side={selected_cfg.get('side_filter')}|tp={selected_cfg.get('take_profit_usd')}|sl={selected_cfg.get('stop_loss_usd')}"
    reference_scenario = f"side={reference_cfg.get('side_filter')}|tp={reference_cfg.get('take_profit_usd')}|sl={reference_cfg.get('stop_loss_usd')}"

    payload = {
        "ok": True,
        "stage": "stage4d_exact_selected_scenario_replay",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mt5_db_path": mt5_db,
        "data_windows": {
            "h1": window(h1),
            "m1": window(m1),
        },
        "signal_count": int(len(signals)),
        "selected_scenario": selected_scenario,
        "reference_scenario": reference_scenario,
        "selected_metrics": selected_metrics,
        "reference_metrics": reference_metrics,
        "folds": folds,
        "cost_stress": stress_rows,
        "monthly_breakdown": monthly,
        "yearly_breakdown": yearly,
        "session_breakdown": session,
        "exit_reasons": exit_reasons,
        "selected_trades_csv": str(selected_csv) if bool(output_cfg.get("save_selected_trades_csv", True)) else None,
        "reference_trades_csv": str(reference_csv) if bool(output_cfg.get("save_reference_trades_csv", True)) else None,
        "decision": decision,
        "warning": "Diagnostic only. No demo, no paper-order, no live trading.",
    }

    write_json(summary_json, payload)
    write_markdown(summary_md, payload)

    print(json.dumps(
        {
            "ok": True,
            "decision": decision,
            "summary_json": str(summary_json),
            "summary_md": str(summary_md),
            "selected_trades_csv": payload["selected_trades_csv"],
            "reference_trades_csv": payload["reference_trades_csv"],
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
