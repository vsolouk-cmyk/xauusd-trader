#!/usr/bin/env python3
"""
Stage 14B — Focused Validation for Previous-Day Low Sweep Rejection

Purpose:
- Validate the only Stage 14A behavioral candidate:
  prev_day_low_sweep_rejection / LONG / horizon_bars=4
- Stress it with:
  1) roundtrip cost
  2) chronological train/test split
  3) year/quarter/month distribution
  4) rolling event-window stability
  5) MFE/MAE quality

This is NOT:
- EA development
- paper/live authorization
- a new grid
- a dashboard
- an order system

Hard rules:
- Research validation only.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import pandas as pd


TOOL_VERSION = "v1"
DEFAULT_OUT_DIR = Path("data/reports/stage14b_prev_day_low_sweep_validation")
DEFAULT_OUTCOMES = Path("data/reports/stage14a_liquidity_session_behavior_discovery/stage14a_mechanism_outcomes.csv")
DEFAULT_SUMMARY = Path("data/reports/stage14a_liquidity_session_behavior_discovery/stage14a_mechanism_summary.csv")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing CSV: {path}")
    return pd.read_csv(path)


def profit_factor(vals: Sequence[float]) -> float:
    vals = [float(v) for v in vals]
    wins = sum(v for v in vals if v > 0)
    losses = abs(sum(v for v in vals if v < 0))
    if losses == 0:
        return 999.0 if wins > 0 else 0.0
    return round(wins / losses, 6)


def max_drawdown(vals: Sequence[float]) -> float:
    eq = peak = 0.0
    dd = 0.0
    for v in vals:
        eq += float(v)
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return round(dd, 6)


def basic_metrics(df: pd.DataFrame, ret_col: str = "ret_usd") -> Dict:
    vals = df[ret_col].astype(float).tolist() if len(df) else []
    if not vals:
        return {
            "events": 0,
            "total": 0.0,
            "avg": 0.0,
            "median": 0.0,
            "win_rate": 0.0,
            "pf": 0.0,
            "max_dd": 0.0,
        }
    s = pd.Series(vals)
    return {
        "events": int(len(vals)),
        "total": round(float(s.sum()), 6),
        "avg": round(float(s.mean()), 6),
        "median": round(float(s.median()), 6),
        "win_rate": round(float((s > 0).mean()), 6),
        "pf": profit_factor(vals),
        "max_dd": max_drawdown(vals),
    }


def metrics_by_period(df: pd.DataFrame, period: str, ret_col: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    x = df.copy()
    x["entry_dt"] = pd.to_datetime(x["entry_utc"], utc=True, errors="coerce")
    x = x.dropna(subset=["entry_dt"])
    if period == "year":
        x["period"] = x["entry_dt"].dt.year.astype(str)
    elif period == "quarter":
        x["period"] = x["entry_dt"].dt.to_period("Q").astype(str)
    elif period == "month":
        x["period"] = x["entry_dt"].dt.to_period("M").astype(str)
    else:
        raise ValueError(period)

    rows = []
    for p, g in x.groupby("period"):
        m = basic_metrics(g, ret_col)
        m["period"] = p
        rows.append(m)
    return pd.DataFrame(rows).sort_values("period")


def chronological_split(df: pd.DataFrame, train_frac: float, ret_col: str) -> Dict:
    x = df.sort_values("entry_utc").reset_index(drop=True)
    n = len(x)
    cut = int(n * train_frac)
    train = x.iloc[:cut].copy()
    test = x.iloc[cut:].copy()
    return {
        "train_frac": train_frac,
        "train": basic_metrics(train, ret_col),
        "test": basic_metrics(test, ret_col),
    }


def rolling_event_windows(df: pd.DataFrame, window: int, ret_col: str) -> pd.DataFrame:
    x = df.sort_values("entry_utc").reset_index(drop=True)
    vals = x[ret_col].astype(float)
    rows = []
    if len(vals) < window:
        return pd.DataFrame()
    for start in range(0, len(vals) - window + 1, max(1, window // 5)):
        end = start + window
        g = x.iloc[start:end]
        m = basic_metrics(g, ret_col)
        m["start_i"] = int(start)
        m["end_i"] = int(end - 1)
        m["start_utc"] = str(g.iloc[0]["entry_utc"])
        m["end_utc"] = str(g.iloc[-1]["entry_utc"])
        rows.append(m)
    return pd.DataFrame(rows)


def mfe_mae_quality(df: pd.DataFrame) -> Dict:
    if df.empty or "mfe_max_h" not in df.columns or "mae_max_h" not in df.columns:
        return {}
    x = df.copy()
    x["mfe_max_h"] = pd.to_numeric(x["mfe_max_h"], errors="coerce")
    x["mae_max_h"] = pd.to_numeric(x["mae_max_h"], errors="coerce")
    x = x.dropna(subset=["mfe_max_h", "mae_max_h"])
    if x.empty:
        return {}
    return {
        "avg_mfe": round(float(x["mfe_max_h"].mean()), 6),
        "avg_mae": round(float(x["mae_max_h"].mean()), 6),
        "median_mfe": round(float(x["mfe_max_h"].median()), 6),
        "median_mae": round(float(x["mae_max_h"].median()), 6),
        "mfe_gt_mae_rate": round(float((x["mfe_max_h"] > x["mae_max_h"]).mean()), 6),
        "avg_mfe_mae_ratio": round(float(x["mfe_max_h"].mean() / max(1e-9, x["mae_max_h"].mean())), 6),
    }


def cost_stress(df: pd.DataFrame, cost_usd: float, multipliers: Sequence[float]) -> pd.DataFrame:
    rows = []
    for mult in multipliers:
        x = df.copy()
        net_col = f"net_x{mult:g}"
        x[net_col] = x["ret_usd"].astype(float) - (cost_usd * float(mult))
        m = basic_metrics(x, net_col)
        m["cost_multiplier"] = float(mult)
        m["cost_usd"] = round(cost_usd * float(mult), 6)
        rows.append(m)
    return pd.DataFrame(rows)


def decide(raw: Dict, cost_df: pd.DataFrame, split: Dict, year_df: pd.DataFrame, rolling_df: pd.DataFrame) -> Tuple[str, List[str]]:
    reasons: List[str] = []

    if raw["events"] < 150:
        reasons.append("Too few events for a robust behavioral candidate.")
        return "REJECT_TOO_FEW_EVENTS", reasons

    if not (raw["pf"] >= 1.20 and raw["median"] > 0 and raw["win_rate"] >= 0.52 and raw["total"] > 0):
        reasons.append("Raw candidate no longer passes basic Stage 14A thresholds.")
        return "REJECT_RAW_WEAK", reasons

    c1 = cost_df[cost_df["cost_multiplier"] == 1.0]
    c2 = cost_df[cost_df["cost_multiplier"] == 2.0]
    if not c1.empty:
        m1 = c1.iloc[0].to_dict()
        if not (m1["total"] > 0 and m1["pf"] >= 1.10):
            reasons.append("Fails x1 cost stress: total or PF is not strong enough after normal roundtrip cost.")
            return "COST_FRAGILE_CANDIDATE", reasons
        if m1["median"] <= 0:
            reasons.append("Median edge disappears after x1 cost; candidate is entry/cost sensitive.")
            return "COST_FRAGILE_CANDIDATE", reasons

    if not c2.empty:
        m2 = c2.iloc[0].to_dict()
        if not (m2["total"] > 0):
            reasons.append("Fails x2 cost stress; candidate may still be usable only with very tight execution and filters.")
            # Not an automatic reject, but not pass either.
            soft_cost_fragile = True
        else:
            soft_cost_fragile = False
    else:
        soft_cost_fragile = False

    test = split.get("test", {})
    train = split.get("train", {})
    if not (test.get("events", 0) >= 50 and test.get("total", 0) > 0 and test.get("pf", 0) >= 1.05):
        reasons.append("Chronological test segment does not independently preserve the edge.")
        return "SPLIT_FRAGILE_CANDIDATE", reasons

    if len(year_df):
        pos_years = int((year_df["total"] > 0).sum())
        years = int(len(year_df))
        if pos_years < max(3, round(years * 0.55)):
            reasons.append("Year distribution is too concentrated.")
            return "DISTRIBUTION_FRAGILE_CANDIDATE", reasons

    if len(rolling_df):
        neg_windows = int((rolling_df["total"] <= 0).sum())
        total_windows = int(len(rolling_df))
        if total_windows and neg_windows / total_windows > 0.45:
            reasons.append("Too many rolling event windows are non-positive.")
            return "ROLLING_FRAGILE_CANDIDATE", reasons

    if soft_cost_fragile:
        reasons.append("Passes x1 cost and split checks but fails x2 cost; keep for filtered validation, not EA/paper.")
        return "FILTER_REQUIRED_COST_SENSITIVE_CANDIDATE", reasons

    reasons.append("Candidate passes focused cost/split/distribution checks. Still not authorized for EA/paper/live.")
    return "VALIDATION_PASS_FOCUSED_REPLAY_CANDIDATE", reasons


def run(
    outcomes_path: Path,
    summary_path: Path,
    out_dir: Path,
    mechanism: str,
    side: str,
    horizon_bars: int,
    cost_usd: float,
    train_frac: float,
    rolling_window: int,
) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = now_iso()

    outcomes = load_csv(outcomes_path)
    summary = load_csv(summary_path) if summary_path.exists() else pd.DataFrame()

    req_cols = {"mechanism", "side", "horizon_bars", "ret_usd", "entry_utc"}
    missing = sorted(req_cols - set(outcomes.columns))
    if missing:
        raise RuntimeError(f"Outcomes CSV missing required columns: {missing}")

    x = outcomes[
        (outcomes["mechanism"].astype(str) == mechanism)
        & (outcomes["side"].astype(str).str.upper() == side.upper())
        & (outcomes["horizon_bars"].astype(int) == int(horizon_bars))
    ].copy()

    if x.empty:
        raise RuntimeError(f"No matching outcomes for mechanism={mechanism}, side={side}, horizon_bars={horizon_bars}")

    x["entry_utc"] = pd.to_datetime(x["entry_utc"], utc=True, errors="coerce")
    x = x.dropna(subset=["entry_utc"]).sort_values("entry_utc").reset_index(drop=True)
    x["entry_utc"] = x["entry_utc"].dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    x["ret_usd"] = pd.to_numeric(x["ret_usd"], errors="coerce")
    x = x.dropna(subset=["ret_usd"])

    raw = basic_metrics(x, "ret_usd")
    cost = cost_stress(x, cost_usd, [0.0, 1.0, 2.0, 4.0])
    x["net_x1"] = x["ret_usd"].astype(float) - cost_usd
    year = metrics_by_period(x, "year", "ret_usd")
    quarter = metrics_by_period(x, "quarter", "ret_usd")
    month = metrics_by_period(x, "month", "ret_usd")
    split = chronological_split(x, train_frac, "ret_usd")
    split_net = chronological_split(x.assign(net_x1=x["net_x1"]), train_frac, "net_x1")
    rolling = rolling_event_windows(x, rolling_window, "ret_usd")
    mfe_mae = mfe_mae_quality(x)

    final_decision, reasons = decide(raw, cost, split, year, rolling)

    # Write files
    candidate_csv = out_dir / "stage14b_candidate_outcomes.csv"
    cost_csv = out_dir / "stage14b_cost_stress.csv"
    year_csv = out_dir / "stage14b_by_year.csv"
    quarter_csv = out_dir / "stage14b_by_quarter.csv"
    month_csv = out_dir / "stage14b_by_month.csv"
    rolling_csv = out_dir / "stage14b_rolling_event_windows.csv"
    json_path = out_dir / "stage14b_prev_day_low_sweep_validation.json"
    md_path = out_dir / "stage14b_prev_day_low_sweep_validation.md"

    x.to_csv(candidate_csv, index=False)
    cost.to_csv(cost_csv, index=False)
    year.to_csv(year_csv, index=False)
    quarter.to_csv(quarter_csv, index=False)
    month.to_csv(month_csv, index=False)
    rolling.to_csv(rolling_csv, index=False)

    prior_summary = {}
    if not summary.empty:
        s = summary[
            (summary["mechanism"].astype(str) == mechanism)
            & (summary["side"].astype(str).str.upper() == side.upper())
            & (summary["horizon_bars"].astype(int) == int(horizon_bars))
        ]
        if not s.empty:
            prior_summary = s.iloc[0].to_dict()

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "inputs": {
            "outcomes_path": str(outcomes_path),
            "summary_path": str(summary_path),
            "mechanism": mechanism,
            "side": side.upper(),
            "horizon_bars": int(horizon_bars),
            "cost_usd": float(cost_usd),
            "train_frac": float(train_frac),
            "rolling_window": int(rolling_window),
        },
        "final_decision": final_decision,
        "reasons": reasons,
        "prior_summary": prior_summary,
        "raw_metrics": raw,
        "cost_stress": cost.to_dict(orient="records"),
        "chronological_split_raw": split,
        "chronological_split_net_x1": split_net,
        "mfe_mae_quality": mfe_mae,
        "year_rows": year.to_dict(orient="records"),
        "quarter_rows": quarter.to_dict(orient="records"),
        "rolling_rows": rolling.to_dict(orient="records"),
        "authorization_flags": {
            "trade_authorization": False,
            "ea_change_authorization": False,
            "paper_order_authorization": False,
            "live_order_authorization": False,
            "automatic_trading": False,
        },
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    lines = [
        "# Stage 14B Previous-Day Low Sweep Validation",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: focused validation only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Candidate",
        f"- mechanism: `{mechanism}`",
        f"- side: `{side.upper()}`",
        f"- horizon_bars: `{horizon_bars}`",
        f"- cost_usd: `{cost_usd}`",
        f"- train_frac: `{train_frac}`",
        f"- rolling_window: `{rolling_window}`",
        "",
        "## Final decision",
        f"- final_decision: `{final_decision}`",
        "",
        "## Reasons",
    ]
    for r in reasons:
        lines.append(f"- {r}")

    lines += [
        "",
        "## Raw metrics",
        "| Events | Total | Avg | Median | WR | PF | DD |",
        "|---:|---:|---:|---:|---:|---:|---:|",
        f"| {raw['events']} | {raw['total']} | {raw['avg']} | {raw['median']} | {raw['win_rate']} | {raw['pf']} | {raw['max_dd']} |",
        "",
        "## Cost stress",
        "| Cost x | Cost USD | Events | Total | Avg | Median | WR | PF | DD |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in cost.to_dict(orient="records"):
        lines.append(
            f"| {r['cost_multiplier']} | {r['cost_usd']} | {r['events']} | {r['total']} | {r['avg']} | "
            f"{r['median']} | {r['win_rate']} | {r['pf']} | {r['max_dd']} |"
        )

    lines += [
        "",
        "## Chronological split - raw",
        "| Segment | Events | Total | Avg | Median | WR | PF | DD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ["train", "test"]:
        m = split[name]
        lines.append(f"| {name} | {m['events']} | {m['total']} | {m['avg']} | {m['median']} | {m['win_rate']} | {m['pf']} | {m['max_dd']} |")

    lines += [
        "",
        "## Chronological split - net x1 cost",
        "| Segment | Events | Total | Avg | Median | WR | PF | DD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ["train", "test"]:
        m = split_net[name]
        lines.append(f"| {name} | {m['events']} | {m['total']} | {m['avg']} | {m['median']} | {m['win_rate']} | {m['pf']} | {m['max_dd']} |")

    lines += [
        "",
        "## MFE/MAE quality",
        "```json",
        json.dumps(mfe_mae, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Year distribution",
        "| Year | Events | Total | Avg | Median | WR | PF | DD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in year.to_dict(orient="records"):
        lines.append(f"| {r['period']} | {r['events']} | {r['total']} | {r['avg']} | {r['median']} | {r['win_rate']} | {r['pf']} | {r['max_dd']} |")

    lines += [
        "",
        "## Interpretation",
        "- If decision is `COST_FRAGILE_CANDIDATE`, the behavior may exist but the raw edge is too small for direct execution.",
        "- If decision is `FILTER_REQUIRED_COST_SENSITIVE_CANDIDATE`, the behavior may deserve one focused filter study, not EA/paper/live.",
        "- If decision is `VALIDATION_PASS_FOCUSED_REPLAY_CANDIDATE`, the next stage may run exact replay/robustness for this single mechanism.",
        "- Any negative result rejects this candidate definition, not the whole XAUUSD market.",
        "",
        "## Output files",
        f"- candidate_csv: `{candidate_csv}`",
        f"- cost_csv: `{cost_csv}`",
        f"- year_csv: `{year_csv}`",
        f"- quarter_csv: `{quarter_csv}`",
        f"- month_csv: `{month_csv}`",
        f"- rolling_csv: `{rolling_csv}`",
        f"- json: `{json_path}`",
        f"- md: `{md_path}`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 14B previous-day low sweep validation: DONE")
    print(f"final_decision={final_decision}")
    print(f"raw_events={raw['events']} raw_pf={raw['pf']} raw_median={raw['median']}")
    if not cost.empty:
        c1 = cost[cost["cost_multiplier"] == 1.0].iloc[0].to_dict()
        print(f"net_x1_total={c1['total']} net_x1_pf={c1['pf']} net_x1_median={c1['median']}")
    print(f"Report: {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--outcomes", default=str(DEFAULT_OUTCOMES))
    p.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--mechanism", default="prev_day_low_sweep_rejection")
    p.add_argument("--side", default="LONG")
    p.add_argument("--horizon-bars", type=int, default=4)
    p.add_argument("--cost-usd", type=float, default=0.35)
    p.add_argument("--train-frac", type=float, default=0.70)
    p.add_argument("--rolling-window", type=int, default=50)
    args = p.parse_args()

    return run(
        outcomes_path=Path(args.outcomes),
        summary_path=Path(args.summary),
        out_dir=Path(args.out_dir),
        mechanism=args.mechanism,
        side=args.side,
        horizon_bars=args.horizon_bars,
        cost_usd=args.cost_usd,
        train_frac=args.train_frac,
        rolling_window=args.rolling_window,
    )


if __name__ == "__main__":
    raise SystemExit(main())
