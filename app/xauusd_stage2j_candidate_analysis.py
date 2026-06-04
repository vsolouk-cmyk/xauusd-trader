from __future__ import annotations

import argparse
import glob
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yaml

from app.xauusd_sqlite_store import connect, read_interval


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def latest_file(pattern: str) -> Optional[Path]:
    files = sorted(glob.glob(pattern), key=lambda p: Path(p).stat().st_mtime, reverse=True)
    return Path(files[0]) if files else None


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


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


def read_db_interval(db_path: str, interval: str) -> pd.DataFrame:
    con = connect(db_path)
    try:
        df = read_interval(con, interval)
    finally:
        con.close()
    if df.empty:
        raise FileNotFoundError(f"No SQLite rows for interval={interval!r} in {db_path}")
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


def parse_variant(family: str, variant: str) -> Dict[str, Any]:
    if family == "sma_trend_1h":
        m = re.fullmatch(r"sma(?P<sma>\d+)_h(?P<h>\d+)_dist(?P<dist>-?\d+(?:\.\d+)?)_cool(?P<cool>\d+)", variant)
        if not m:
            raise ValueError(f"Unsupported SMA variant: {variant}")
        return {
            "family": family,
            "interval": "1h",
            "sma_window": int(m.group("sma")),
            "horizon": int(m.group("h")),
            "min_distance": float(m.group("dist")),
            "cooldown": int(m.group("cool")),
        }

    if family == "session_momentum_15min":
        m = re.fullmatch(r"lb(?P<lb>\d+)_h(?P<h>\d+)_move(?P<move>-?\d+(?:\.\d+)?)_cool(?P<cool>\d+)", variant)
        if not m:
            raise ValueError(f"Unsupported session momentum variant: {variant}")
        return {
            "family": family,
            "interval": "15min",
            "lookback": int(m.group("lb")),
            "horizon": int(m.group("h")),
            "min_move": float(m.group("move")),
            "cooldown": int(m.group("cool")),
            "sessions": ["london", "london_ny_overlap", "new_york"],
        }

    if family == "range_expansion_15min":
        m = re.fullmatch(r"range(?P<w>\d+)_x(?P<x>-?\d+(?:\.\d+)?)_h(?P<h>\d+)_cool(?P<cool>\d+)", variant)
        if not m:
            raise ValueError(f"Unsupported range expansion variant: {variant}")
        return {
            "family": family,
            "interval": "15min",
            "avg_range_window": int(m.group("w")),
            "multiplier": float(m.group("x")),
            "horizon": int(m.group("h")),
            "cooldown": int(m.group("cool")),
        }

    raise ValueError(f"Unsupported family: {family}")


def gen_sma(df: pd.DataFrame, params: Dict[str, Any]) -> Tuple[np.ndarray, np.ndarray, np.ndarray, str]:
    horizon = int(params["horizon"])
    close = df["close"]
    sma = close.rolling(int(params["sma_window"])).mean()
    diff = close - sma
    valid = diff.notna() & (diff.abs() >= float(params["min_distance"]))
    valid.iloc[-horizon:] = False
    entry = np.flatnonzero(valid.to_numpy())
    exit_ = entry + horizon
    direction = np.where(diff.iloc[entry].to_numpy(dtype=float) > 0, 1, -1).astype(int)
    return entry.astype(int), exit_.astype(int), direction, "sma_trend"


def gen_session_momentum(df: pd.DataFrame, params: Dict[str, Any]) -> Tuple[np.ndarray, np.ndarray, np.ndarray, str]:
    horizon = int(params["horizon"])
    lookback = int(params["lookback"])
    move = df["close"] - df["close"].shift(lookback)
    session_ok = df["session_utc"].isin(set(params.get("sessions", ["london", "london_ny_overlap", "new_york"])))
    valid = move.notna() & session_ok & (move.abs() >= float(params["min_move"]))
    valid.iloc[-horizon:] = False
    entry = np.flatnonzero(valid.to_numpy())
    exit_ = entry + horizon
    direction = np.where(move.iloc[entry].to_numpy(dtype=float) > 0, 1, -1).astype(int)
    return entry.astype(int), exit_.astype(int), direction, "session_momentum"


def gen_range_expansion(df: pd.DataFrame, params: Dict[str, Any]) -> Tuple[np.ndarray, np.ndarray, np.ndarray, str]:
    horizon = int(params["horizon"])
    bar_range = df["high"] - df["low"]
    avg_range = bar_range.rolling(int(params["avg_range_window"])).mean()
    body = df["close"] - df["open"]
    valid = avg_range.notna() & (avg_range > 0) & (bar_range >= float(params["multiplier"]) * avg_range) & (body != 0)
    valid.iloc[-horizon:] = False
    entry = np.flatnonzero(valid.to_numpy())
    exit_ = entry + horizon
    direction = np.where(body.iloc[entry].to_numpy(dtype=float) > 0, 1, -1).astype(int)
    return entry.astype(int), exit_.astype(int), direction, "range_expansion"


def make_trades(df: pd.DataFrame, family: str, variant: str, params: Dict[str, Any], cost_usd: float) -> pd.DataFrame:
    if family == "sma_trend_1h":
        entry, exit_, direction, reason = gen_sma(df, params)
    elif family == "session_momentum_15min":
        entry, exit_, direction, reason = gen_session_momentum(df, params)
    elif family == "range_expansion_15min":
        entry, exit_, direction, reason = gen_range_expansion(df, params)
    else:
        raise ValueError(f"Unsupported family: {family}")

    keep = nonoverlap_indices(entry, exit_, int(params["cooldown"]))
    entry, exit_, direction = entry[keep], exit_[keep], direction[keep]

    if len(entry) == 0:
        return pd.DataFrame()

    close = df["close"].to_numpy(dtype=float)
    raw = direction.astype(float) * (close[exit_] - close[entry])
    net = raw - float(cost_usd)

    return pd.DataFrame(
        {
            "family": family,
            "variant": variant,
            "interval": params["interval"],
            "entry_idx": entry,
            "exit_idx": exit_,
            "entry_time_utc": df["time_utc"].iloc[entry].astype(str).to_numpy(),
            "exit_time_utc": df["time_utc"].iloc[exit_].astype(str).to_numpy(),
            "entry_month_utc": df["month_utc"].iloc[entry].to_numpy(),
            "direction": direction,
            "direction_label": np.where(direction > 0, "long", "short"),
            "raw_usd": raw,
            "cost_usd": float(cost_usd),
            "net_usd": net,
            "reason": reason,
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


def remove_top_k(values: np.ndarray, k: int) -> np.ndarray:
    values = np.asarray(values, dtype=float)
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


def monthly_breakdown(trades: pd.DataFrame) -> Dict[str, Any]:
    rows = []
    for month, g in trades.groupby("entry_month_utc", sort=True):
        m = metrics(g["net_usd"].to_numpy(dtype=float))
        m["month"] = str(month)
        rows.append(m)
    positive = [r for r in rows if float(r["total_net_usd"]) > 0]
    return {
        "months": rows,
        "month_count": int(len(rows)),
        "positive_month_count": int(len(positive)),
        "positive_month_ratio": float(len(positive) / max(len(rows), 1)),
        "worst_month": min(rows, key=lambda r: float(r["total_net_usd"])) if rows else None,
        "best_month": max(rows, key=lambda r: float(r["total_net_usd"])) if rows else None,
    }


def thirds_breakdown(trades: pd.DataFrame) -> Dict[str, Any]:
    work = trades.sort_values("entry_time_utc").reset_index(drop=True)
    n = len(work)
    if n == 0:
        return {}
    cuts = [0, n // 3, (2 * n) // 3, n]
    names = ["first_third", "middle_third", "last_third"]
    out = {}
    for name, start, end in zip(names, cuts[:-1], cuts[1:]):
        out[name] = metrics(work.iloc[start:end]["net_usd"].to_numpy(dtype=float))
    return out


def cost_stress(trades: pd.DataFrame, multipliers: List[float]) -> List[Dict[str, Any]]:
    raw = trades["raw_usd"].to_numpy(dtype=float)
    cost = trades["cost_usd"].to_numpy(dtype=float)
    rows = []
    for mult in multipliers:
        m = metrics(raw - cost * float(mult))
        m["cost_multiplier"] = float(mult)
        rows.append(m)
    return rows


def evaluate_candidate(
    family: str,
    variant: str,
    trades: pd.DataFrame,
    decision_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    net = trades["net_usd"].to_numpy(dtype=float)
    base = metrics(net)
    remove_top_10 = metrics(remove_top_k(net, 10))
    monthly = monthly_breakdown(trades)
    thirds = thirds_breakdown(trades)
    stress = cost_stress(trades, [1.0, 2.0, 3.0])
    stress_x3 = next((x for x in stress if float(x["cost_multiplier"]) == 3.0), {})

    pf = base.get("profit_factor")
    total = float(base["total_net_usd"])
    dd = abs(float(base["max_drawdown_usd"]))

    checks = {
        "min_trades": int(base["trade_count"]) >= int(decision_cfg.get("min_trades", 100)),
        "min_months": int(monthly["month_count"]) >= int(decision_cfg.get("min_months", 4)),
        "positive_month_ratio": float(monthly["positive_month_ratio"]) >= float(decision_cfg.get("min_positive_month_ratio", 0.60)),
        "all_time_thirds_positive": all(float(thirds.get(k, {}).get("total_net_usd", 0.0)) > 0 for k in ["first_third", "middle_third", "last_third"]),
        "remove_top_10_positive": float(remove_top_10["total_net_usd"]) > 0,
        "cost_x3_positive": float(stress_x3.get("total_net_usd", 0.0)) > 0,
        "profit_factor_min": pf is not None and float(pf) >= float(decision_cfg.get("require_profit_factor_min", 1.15)),
        "dd_to_total_ok": total > 0 and dd <= float(decision_cfg.get("max_dd_to_total_net_ratio", 0.80)) * total,
    }
    stable = all(checks.values())
    reason = "stable_candidate" if stable else "failed_checks:" + ",".join(k for k, v in checks.items() if not v)

    return {
        "family": family,
        "variant": variant,
        "stable_candidate": bool(stable),
        "reason": reason,
        "checks": checks,
        "base": base,
        "remove_top_10": remove_top_10,
        "thirds": thirds,
        "monthly": monthly,
        "cost_stress": stress,
    }


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.replace(path)


def write_markdown(path: Path, payload: Dict[str, Any]) -> None:
    lines = []
    lines.append("# XAUUSD Stage 2J Candidate Stability Analysis")
    lines.append("")
    lines.append(f"- Generated at UTC: `{payload['generated_at_utc']}`")
    lines.append(f"- Decision: `{payload['decision']['status']}`")
    lines.append(f"- Reason: `{payload['decision']['reason']}`")
    lines.append(f"- Candidates analyzed: `{payload['candidate_count']}`")
    lines.append("")
    lines.append("| Family | Variant | Stable | Reason | Trades | Total net | PF | Months +ratio | Last third | Remove top10 | Cost x3 | DD |")
    lines.append("|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in payload["top_analyses"]:
        base = row["base"]
        monthly = row["monthly"]
        thirds = row["thirds"]
        last = thirds.get("last_third", {})
        x3 = next((x for x in row["cost_stress"] if float(x["cost_multiplier"]) == 3.0), {})
        pf = base.get("profit_factor")
        lines.append(
            "| {family} | {variant} | {stable} | {reason} | {trades} | {total:.4f} | {pf} | {month_ratio:.2f} | {last_total:.4f} | {r10:.4f} | {x3:.4f} | {dd:.4f} |".format(
                family=row["family"],
                variant=row["variant"],
                stable=row["stable_candidate"],
                reason=row["reason"],
                trades=base["trade_count"],
                total=base["total_net_usd"],
                pf="n/a" if pf is None else f"{float(pf):.3f}",
                month_ratio=monthly["positive_month_ratio"],
                last_total=last.get("total_net_usd", 0.0),
                r10=row["remove_top_10"]["total_net_usd"],
                x3=x3.get("total_net_usd", 0.0),
                dd=base["max_drawdown_usd"],
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 2J candidate stability analysis from Stage 2D robust candidates.")
    parser.add_argument("--config", default="configs/stage2j.yaml")
    parser.add_argument("--stage2d-summary", default=None)
    parser.add_argument("--stage2d-evaluations", default=None)
    parser.add_argument("--data-db", default=None)
    parser.add_argument("--report-dir", default=None)
    args = parser.parse_args()

    cfg = load_yaml(Path(args.config))
    report_dir = Path(args.report_dir or cfg.get("report_dir", "data/reports"))
    report_dir.mkdir(parents=True, exist_ok=True)

    db_path = args.data_db or cfg.get("data_db", "data/store/xauusd.sqlite")
    summary_path = Path(args.stage2d_summary) if args.stage2d_summary else latest_file(cfg.get("stage2d_summary_glob", "data/reports/stage2d_grid_summary_*.json"))
    eval_path = Path(args.stage2d_evaluations) if args.stage2d_evaluations else latest_file(cfg.get("stage2d_evaluations_glob", "data/reports/stage2d_grid_evaluations_*.csv"))

    if not summary_path or not summary_path.exists():
        raise SystemExit("Stage 2D summary not found. Run Stage 2D first.")
    if not eval_path or not eval_path.exists():
        raise SystemExit("Stage 2D evaluations CSV not found. Run Stage 2D first.")

    stage2d_summary = load_json(summary_path)
    evals = pd.read_csv(eval_path)

    selection_cfg = cfg.get("selection", {}) or {}
    if bool(selection_cfg.get("only_robust_stage2d", True)):
        candidates = evals[evals["robust_grid_candidate"] == True].copy()  # noqa: E712
    else:
        candidates = evals.copy()

    sort_col = str(selection_cfg.get("sort_by", "total_net_usd"))
    if sort_col in candidates.columns:
        candidates = candidates.sort_values(sort_col, ascending=False)
    max_candidates = int(selection_cfg.get("max_candidates", 15))
    candidates = candidates.head(max_candidates)

    decision_cfg = cfg.get("decision", {}) or {}

    data_cache: Dict[str, pd.DataFrame] = {}
    analyses = []
    for _, row in candidates.iterrows():
        family = str(row["family"])
        variant = str(row["variant"])
        try:
            params = parse_variant(family, variant)
            interval = params["interval"]
            if interval not in data_cache:
                data_cache[interval] = read_db_interval(db_path, interval)
            trades = make_trades(data_cache[interval], family, variant, params, cost_usd=float(stage2d_summary["cost_model"]["effective_roundtrip_cost_usd"]))
            if trades.empty:
                continue
            analyses.append(evaluate_candidate(family, variant, trades, decision_cfg))
        except Exception as exc:
            analyses.append(
                {
                    "family": family,
                    "variant": variant,
                    "stable_candidate": False,
                    "reason": f"analysis_error:{exc}",
                    "checks": {},
                    "base": {},
                    "remove_top_10": {},
                    "thirds": {},
                    "monthly": {},
                    "cost_stress": [],
                }
            )

    stable = [x for x in analyses if x.get("stable_candidate")]
    top = sorted(analyses, key=lambda x: float(x.get("base", {}).get("total_net_usd", -10**18)), reverse=True)

    if stable:
        status = "stage2j_stable_candidate_found"
        reason = "At least one Stage 2D robust candidate remained stable across month/time/outlier/cost diagnostics."
    else:
        status = "no_stage2j_stable_candidate"
        reason = "No Stage 2D robust candidate survived Stage 2J stability diagnostics."

    stamp = utc_stamp()
    summary_json = report_dir / f"stage2j_candidate_stability_summary_{stamp}.json"
    summary_md = report_dir / f"stage2j_candidate_stability_summary_{stamp}.md"

    payload = {
        "ok": True,
        "stage": "stage2j_candidate_stability_analysis",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_db": db_path,
        "stage2d_summary": str(summary_path),
        "stage2d_evaluations": str(eval_path),
        "candidate_count": int(len(candidates)),
        "decision_config": decision_cfg,
        "decision": {
            "status": status,
            "reason": reason,
            "stable_candidate_count": int(len(stable)),
        },
        "stable_candidates": stable[:10],
        "top_analyses": top[:15],
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
                "candidate_count": len(candidates),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
