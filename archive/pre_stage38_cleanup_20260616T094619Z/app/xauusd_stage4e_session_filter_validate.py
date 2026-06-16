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


def replay_signal(sig: Dict[str, Any], arrays: Dict[str, np.ndarray], tp_usd: float, sl_usd: float, cost_usd: float) -> Optional[Dict[str, Any]]:
    if sig["direction_label"] != "long":
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

    entry_price = float(open_[entry_idx])
    path_high = high[entry_idx: time_exit_idx + 1]
    path_low = low[entry_idx: time_exit_idx + 1]

    tp_mask = path_high >= entry_price + float(tp_usd)
    sl_mask = path_low <= entry_price - float(sl_usd)

    tp_local = first_hit_index(tp_mask)
    sl_local = first_hit_index(sl_mask)
    tp_idx = None if tp_local is None else int(entry_idx + tp_local)
    sl_idx = None if sl_local is None else int(entry_idx + sl_local)

    exit_idx = time_exit_idx
    exit_reason = "time_exit"
    ambiguous_exit = False
    exit_price = float(close[time_exit_idx])

    if tp_idx is not None and sl_idx is not None:
        if tp_idx == sl_idx:
            exit_idx = sl_idx
            exit_reason = "ambiguous_sl_first"
            ambiguous_exit = True
            exit_price = entry_price - float(sl_usd)
        elif sl_idx < tp_idx:
            exit_idx = sl_idx
            exit_reason = "stop_loss"
            exit_price = entry_price - float(sl_usd)
        else:
            exit_idx = tp_idx
            exit_reason = "take_profit"
            exit_price = entry_price + float(tp_usd)
    elif sl_idx is not None:
        exit_idx = sl_idx
        exit_reason = "stop_loss"
        exit_price = entry_price - float(sl_usd)
    elif tp_idx is not None:
        exit_idx = tp_idx
        exit_reason = "take_profit"
        exit_price = entry_price + float(tp_usd)

    ph = high[entry_idx: exit_idx + 1]
    pl = low[entry_idx: exit_idx + 1]

    raw = float(exit_price) - entry_price
    net = raw - float(cost_usd)
    entry_time = str(time_str[entry_idx])
    exit_time = str(time_str[exit_idx])
    entry_ts = pd.to_datetime(entry_time, utc=True)
    hour = int(entry_ts.hour)

    return {
        **sig,
        "entry_time_utc": entry_time,
        "exit_time_utc": exit_time,
        "entry_hour_utc": hour,
        "entry_month_utc": entry_ts.strftime("%Y-%m"),
        "entry_year_utc": int(entry_ts.year),
        "session_utc": session_name(hour),
        "entry_price": entry_price,
        "exit_price": float(exit_price),
        "exit_reason": exit_reason,
        "ambiguous_exit": bool(ambiguous_exit),
        "raw_usd": float(raw),
        "cost_usd": float(cost_usd),
        "net_usd": float(net),
        "mfe_usd": float(ph.max() - entry_price),
        "mae_usd": float(entry_price - pl.min()),
        "m1_bars_in_trade": int(exit_idx - entry_idx + 1),
    }


def replay_selected(signals: list[Dict[str, Any]], arrays: Dict[str, np.ndarray], tp_usd: float, sl_usd: float, cost_usd: float) -> pd.DataFrame:
    rows = []
    for sig in signals:
        row = replay_signal(sig, arrays, tp_usd=tp_usd, sl_usd=sl_usd, cost_usd=cost_usd)
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


def summarize_trades(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        out = metrics_from_net(np.array([], dtype=float))
        out.update({"ambiguous_exit_count": 0, "ambiguous_exit_ratio": 0.0, "exit_reasons": {}})
        return out
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
    positive = [r for r in rows if float(r.get("total_net_usd", 0.0)) > 0]
    return {
        "fold_count": int(len(rows)),
        "positive_fold_count": int(len(positive)),
        "positive_fold_ratio": float(len(positive) / max(len(rows), 1)),
        "folds": rows,
    }


def year_breakdown(df: pd.DataFrame) -> Dict[str, Any]:
    out = {}
    if df.empty:
        return out
    for year, g in df.groupby("entry_year_utc", sort=True):
        out[str(year)] = summarize_trades(g)
    return out


def session_set_summary(df: pd.DataFrame, name: str, sessions: list[str], cfg: Dict[str, Any]) -> Dict[str, Any]:
    subset = df[df["session_utc"].isin(sessions)].copy()
    base = summarize_trades(subset)
    folds = fold_breakdown(subset)
    years = year_breakdown(subset)
    positive_years = [y for y, m in years.items() if float(m.get("total_net_usd", 0.0)) > 0]
    positive_year_ratio = float(len(positive_years) / max(len(years), 1))

    cost_cfg = cfg.get("cost_model", {}) or {}
    cost_base = float(cost_cfg.get("total_roundtrip_cost_usd", 0.35))
    multipliers = [float(x) for x in cost_cfg.get("cost_multipliers", [1, 2, 3, 4])]
    raw = subset["raw_usd"].to_numpy(dtype=float) if not subset.empty else np.array([], dtype=float)
    cost_stress = []
    for mult in multipliers:
        net = raw - cost_base * mult
        row = metrics_from_net(net)
        row["cost_multiplier"] = float(mult)
        cost_stress.append(row)

    th = cfg.get("thresholds", {}) or {}
    pf = base.get("profit_factor")
    by_cost = {float(x["cost_multiplier"]): x for x in cost_stress}

    checks = {
        "min_trades": int(base.get("trade_count", 0)) >= int(th.get("min_trades", 100)),
        "pf_min": pf is not None and float(pf) >= float(th.get("min_profit_factor", 1.30)),
        "median_nonnegative": float(base.get("median_net_usd", 0.0)) >= float(th.get("min_median_net_usd", 0.0)),
        "positive_fold_ratio": float(folds.get("positive_fold_ratio", 0.0)) >= float(th.get("min_positive_fold_ratio", 0.8)),
        "positive_year_ratio": positive_year_ratio >= float(th.get("min_positive_year_ratio", 0.75)),
        "ambiguous_exit_ratio_ok": float(base.get("ambiguous_exit_ratio", 999.0)) <= float(th.get("max_ambiguous_exit_ratio", 0.05)),
    }

    if 3.0 in by_cost:
        checks["cost_x3_positive"] = float(by_cost[3.0].get("total_net_usd", 0.0)) > float(th.get("min_cost_x3_total_net_usd", 0.0))

    if bool(th.get("require_recent_half_positive", True)):
        recent_folds = folds.get("folds", [])[-2:]
        checks["recent_half_positive"] = all(float(x.get("total_net_usd", 0.0)) > 0 for x in recent_folds)

    passed = all(checks.values())

    return {
        "name": name,
        "sessions": sessions,
        "passed": bool(passed),
        "checks": checks,
        "base": base,
        "folds": folds,
        "yearly": years,
        "positive_year_ratio": positive_year_ratio,
        "cost_stress": cost_stress,
    }


def sort_key(row: Dict[str, Any]) -> tuple:
    base = row.get("base", {})
    pf = base.get("profit_factor")
    return (
        1 if row.get("passed") else 0,
        float(pf) if pf is not None else -999.0,
        float(base.get("total_net_usd", -999.0)),
        float(base.get("median_net_usd", -999.0)),
        -abs(float(base.get("max_drawdown_usd", 999.0))),
    )


def write_markdown(path: Path, payload: Dict[str, Any]) -> None:
    lines = [
        "# XAUUSD Stage 4E Session Filter Validation",
        "",
        f"- Generated at UTC: `{payload['generated_at_utc']}`",
        f"- Decision: `{payload['decision']['status']}`",
        f"- Reason: `{payload['decision']['reason']}`",
        "",
        "## Top session sets",
        "",
        "| Rank | Name | Passed | Trades | Total net | PF | Median | Fold+ | Year+ | Max DD |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for i, row in enumerate(payload["ranked_session_sets"], start=1):
        b = row["base"]
        pf = b.get("profit_factor")
        lines.append(
            "| {rank} | `{name}` | {passed} | {trades} | {total:.4f} | {pf} | {median:.4f} | {fold:.2f} | {yr:.2f} | {dd:.4f} |".format(
                rank=i,
                name=row["name"],
                passed=row["passed"],
                trades=b["trade_count"],
                total=float(b["total_net_usd"]),
                pf="n/a" if pf is None else f"{float(pf):.3f}",
                median=float(b["median_net_usd"]),
                fold=float(row["folds"]["positive_fold_ratio"]),
                yr=float(row["positive_year_ratio"]),
                dd=float(b["max_drawdown_usd"]),
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate session filters for selected XAUUSD long TP/SL scenario.")
    parser.add_argument("--config", default="configs/stage4e.yaml")
    parser.add_argument("--mt5-db", default=None)
    parser.add_argument("--report-dir", default=None)
    args = parser.parse_args()

    cfg = load_yaml(Path(args.config))
    candidate = cfg.get("candidate", {}) or {}
    data_cfg = cfg.get("data", {}) or {}
    selected = cfg.get("selected_scenario", {}) or {}

    mt5_db = args.mt5_db or data_cfg.get("mt5_db_path", "data/second_source/second_source.sqlite")
    signal_interval = str(candidate.get("signal_interval", "1h"))
    path_interval = str(candidate.get("path_interval", "1min"))
    report_dir = Path(args.report_dir or cfg.get("report_dir", "data/reports"))
    report_dir.mkdir(parents=True, exist_ok=True)

    cost_usd = float((cfg.get("cost_model", {}) or {}).get("total_roundtrip_cost_usd", 0.35))
    tp_usd = float(selected.get("take_profit_usd", 24.0))
    sl_usd = float(selected.get("stop_loss_usd", 15.0))

    print("Loading H1/M1 data...")
    h1 = read_db_interval(mt5_db, signal_interval)
    m1 = read_db_interval(mt5_db, path_interval)
    print(f"Loaded h1_rows={len(h1)} m1_rows={len(m1)}")

    signals = build_h1_signals(h1, cfg)
    arrays = make_m1_arrays(m1)
    print(f"Built signals={len(signals)}")

    all_trades = replay_selected(signals, arrays, tp_usd=tp_usd, sl_usd=sl_usd, cost_usd=cost_usd)
    print(f"Replayed selected long trades={len(all_trades)}")

    session_sets = cfg.get("session_sets", {}) or {}
    summaries = []
    for name, sessions in session_sets.items():
        summaries.append(session_set_summary(all_trades, str(name), list(sessions), cfg))

    ranked = sorted(summaries, key=sort_key, reverse=True)
    passed = [x for x in ranked if x.get("passed")]

    status = "stage4e_session_filter_candidate_found" if passed else "stage4e_no_session_filter_candidate"
    reason = (
        "At least one session-filtered scenario passed Stage 4E checks."
        if passed else
        "No session-filtered scenario passed Stage 4E checks."
    )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_json = report_dir / f"stage4e_session_filter_summary_{stamp}.json"
    out_md = report_dir / f"stage4e_session_filter_summary_{stamp}.md"
    csv_path = report_dir / f"stage4e_session_filter_scenarios_{stamp}.csv"

    flat = []
    for row in ranked:
        b = row["base"]
        flat.append({
            "name": row["name"],
            "sessions": ",".join(row["sessions"]),
            "passed": row["passed"],
            "trade_count": b["trade_count"],
            "total_net_usd": b["total_net_usd"],
            "avg_net_usd": b["avg_net_usd"],
            "median_net_usd": b["median_net_usd"],
            "win_rate": b["win_rate"],
            "profit_factor": b["profit_factor"],
            "max_drawdown_usd": b["max_drawdown_usd"],
            "positive_fold_ratio": row["folds"]["positive_fold_ratio"],
            "positive_year_ratio": row["positive_year_ratio"],
        })
    pd.DataFrame(flat).to_csv(csv_path, index=False)

    payload = {
        "ok": True,
        "stage": "stage4e_session_filter_validation",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mt5_db_path": mt5_db,
        "data_windows": {
            "h1": window(h1),
            "m1": window(m1),
        },
        "selected_scenario": {
            "side_filter": "long",
            "take_profit_usd": tp_usd,
            "stop_loss_usd": sl_usd,
        },
        "all_selected_trades": summarize_trades(all_trades),
        "ranked_session_sets": ranked,
        "passed_session_sets": passed,
        "scenarios_csv": str(csv_path),
        "decision": {
            "status": status,
            "reason": reason,
            "passed_count": len(passed),
        },
        "warning": "Diagnostic only. Session filters are not authorized for demo/paper/live until reviewed.",
    }

    write_json(out_json, payload)
    write_markdown(out_md, payload)

    print(json.dumps({
        "ok": True,
        "decision": payload["decision"],
        "summary_json": str(out_json),
        "summary_md": str(out_md),
        "scenarios_csv": str(csv_path),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
