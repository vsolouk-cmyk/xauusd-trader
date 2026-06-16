#!/usr/bin/env python3
"""
Stage 14D — Robustness Validation for Sweep-Depth Filter

Candidate from Stage 14C:
- mechanism: prev_day_low_sweep_rejection
- side: LONG
- horizon_bars: 4
- filter: sweep_depth_ge_q50

Purpose:
- Validate the single top Stage 14C filter under stricter robustness checks.
- No new filter search.
- No EA/paper/live authorization.

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
from typing import Dict, Sequence, Tuple, List

import pandas as pd


TOOL_VERSION = "v1"
DEFAULT_FEATURES = Path("data/reports/stage14c_behavioral_filter_study/stage14c_candidate_features.csv")
DEFAULT_OUT_DIR = Path("data/reports/stage14d_sweep_depth_filter_robustness")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def profit_factor(vals: Sequence[float]) -> float:
    vals = [float(v) for v in vals]
    wins = sum(v for v in vals if v > 0)
    losses = abs(sum(v for v in vals if v < 0))
    if losses == 0:
        return 999.0 if wins > 0 else 0.0
    return round(wins / losses, 6)


def max_dd(vals: Sequence[float]) -> float:
    eq = peak = 0.0
    dd = 0.0
    for v in vals:
        eq += float(v)
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return round(dd, 6)


def metrics(df: pd.DataFrame, ret_col: str) -> Dict:
    if df.empty:
        return {
            "events": 0,
            "total": 0.0,
            "avg": 0.0,
            "median": 0.0,
            "win_rate": 0.0,
            "pf": 0.0,
            "max_dd": 0.0,
            "pos_years": 0,
            "years": 0,
            "pos_quarters": 0,
            "quarters": 0,
        }
    x = df.sort_values("entry_dt").copy()
    vals = x[ret_col].astype(float).tolist()
    s = pd.Series(vals)
    by_year = x.groupby(x["entry_dt"].dt.year)[ret_col].sum()
    by_quarter = x.groupby(x["entry_dt"].dt.to_period("Q").astype(str))[ret_col].sum()
    return {
        "events": int(len(vals)),
        "total": round(float(s.sum()), 6),
        "avg": round(float(s.mean()), 6),
        "median": round(float(s.median()), 6),
        "win_rate": round(float((s > 0).mean()), 6),
        "pf": profit_factor(vals),
        "max_dd": max_dd(vals),
        "pos_years": int((by_year > 0).sum()),
        "years": int(len(by_year)),
        "pos_quarters": int((by_quarter > 0).sum()),
        "quarters": int(len(by_quarter)),
    }


def period_metrics(df: pd.DataFrame, ret_col: str, period: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    x = df.sort_values("entry_dt").copy()
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
        m = metrics(g, ret_col)
        m["period"] = p
        rows.append(m)
    return pd.DataFrame(rows).sort_values("period") if rows else pd.DataFrame()


def split_metrics(df: pd.DataFrame, ret_col: str, train_frac: float) -> Dict:
    x = df.sort_values("entry_dt").reset_index(drop=True)
    cut = int(len(x) * train_frac)
    train = x.iloc[:cut].copy()
    test = x.iloc[cut:].copy()
    return {
        "train_frac": float(train_frac),
        "train": metrics(train, ret_col),
        "test": metrics(test, ret_col),
    }


def rolling_windows(df: pd.DataFrame, ret_col: str, window: int) -> pd.DataFrame:
    x = df.sort_values("entry_dt").reset_index(drop=True)
    if len(x) < window:
        return pd.DataFrame()
    rows = []
    step = max(1, window // 5)
    for start in range(0, len(x) - window + 1, step):
        end = start + window
        g = x.iloc[start:end].copy()
        m = metrics(g, ret_col)
        m["start_i"] = int(start)
        m["end_i"] = int(end - 1)
        m["start_utc"] = g.iloc[0]["entry_dt"].isoformat()
        m["end_utc"] = g.iloc[-1]["entry_dt"].isoformat()
        rows.append(m)
    return pd.DataFrame(rows)


def cost_stress(df: pd.DataFrame, base_cost: float, multipliers: Sequence[float]) -> pd.DataFrame:
    rows = []
    for mult in multipliers:
        x = df.copy()
        col = f"net_x{mult:g}"
        x[col] = x["ret_usd"].astype(float) - (base_cost * float(mult))
        m = metrics(x, col)
        m["cost_multiplier"] = float(mult)
        m["cost_usd"] = round(base_cost * float(mult), 6)
        rows.append(m)
    return pd.DataFrame(rows)


def depth_thresholds(df: pd.DataFrame) -> Dict:
    s = pd.to_numeric(df["sweep_depth"], errors="coerce").dropna()
    return {
        "q25": round(float(s.quantile(0.25)), 6),
        "q50": round(float(s.quantile(0.50)), 6),
        "q75": round(float(s.quantile(0.75)), 6),
        "mean": round(float(s.mean()), 6),
    }


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


def bootstrap_blocks(df: pd.DataFrame, ret_col: str, n: int = 500, seed: int = 14) -> Dict:
    # Deterministic pseudo-bootstrap using pandas sample. Small and fast.
    if df.empty:
        return {}
    x = df.sort_values("entry_dt").reset_index(drop=True)
    totals = []
    medians = []
    pfs = []
    for i in range(n):
        sample = x.sample(n=len(x), replace=True, random_state=seed + i)
        vals = sample[ret_col].astype(float).tolist()
        totals.append(sum(vals))
        medians.append(float(pd.Series(vals).median()))
        pfs.append(profit_factor(vals))
    ts = pd.Series(totals)
    ms = pd.Series(medians)
    ps = pd.Series(pfs)
    return {
        "n": int(n),
        "total_p05": round(float(ts.quantile(0.05)), 6),
        "total_p50": round(float(ts.quantile(0.50)), 6),
        "total_p95": round(float(ts.quantile(0.95)), 6),
        "median_p05": round(float(ms.quantile(0.05)), 6),
        "median_p50": round(float(ms.quantile(0.50)), 6),
        "pf_p05": round(float(ps.quantile(0.05)), 6),
        "pf_p50": round(float(ps.quantile(0.50)), 6),
        "prob_total_gt_0": round(float((ts > 0).mean()), 6),
        "prob_median_gt_0": round(float((ms > 0).mean()), 6),
        "prob_pf_gt_1": round(float((ps > 1.0).mean()), 6),
    }


def decide(
    net: Dict,
    x2: Dict,
    splits: List[Dict],
    year: pd.DataFrame,
    quarter: pd.DataFrame,
    roll: pd.DataFrame,
    boot: Dict,
) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    if net["events"] < 120:
        return "REJECT_TOO_FEW_FILTERED_EVENTS", ["Filtered candidate has too few events for robustness."]

    if not (net["total"] > 0 and net["pf"] >= 1.20 and net["median"] > 0.25 and net["win_rate"] >= 0.53):
        return "REJECT_NET_EDGE_WEAK", ["Net-after-cost edge fails strict minimum thresholds."]

    if not (x2["total"] > 0 and x2["pf"] >= 1.05):
        reasons.append("Fails or weakens strongly under x2 cost stress.")
        cost_fragile = True
    else:
        cost_fragile = False

    for sp in splits:
        test = sp["test"]
        if not (test["events"] >= 35 and test["total"] > 0 and test["pf"] >= 1.05):
            return "SPLIT_FRAGILE_FILTER", [f"Chronological split {sp['train_frac']} test segment is not independently positive enough."]

    if not year.empty:
        pos_years = int((year["total"] > 0).sum())
        years = int(len(year))
        if pos_years < max(3, round(years * 0.60)):
            return "YEAR_DISTRIBUTION_FRAGILE_FILTER", ["Year distribution is too concentrated."]

    if not quarter.empty:
        pos_q = int((quarter["total"] > 0).sum())
        q = int(len(quarter))
        if q >= 8 and pos_q / q < 0.55:
            return "QUARTER_DISTRIBUTION_FRAGILE_FILTER", ["Quarter distribution is too weak."]

    if not roll.empty:
        positive_rate = float((roll["total"] > 0).mean())
        if positive_rate < 0.60:
            return "ROLLING_FRAGILE_FILTER", ["Fewer than 60% of rolling event windows are positive."]

    if boot and boot.get("prob_total_gt_0", 0) < 0.90:
        return "BOOTSTRAP_FRAGILE_FILTER", ["Bootstrap probability of positive total is below 90%."]

    if cost_fragile:
        reasons.append("Candidate passes normal cost and split checks but remains cost-sensitive at x2.")
        return "ROBUST_ENOUGH_FOR_EXACT_REPLAY_BUT_COST_SENSITIVE", reasons

    reasons.append("Candidate passes strict focused robustness checks. Still no EA/paper/live authorization.")
    return "ROBUST_FILTER_CANDIDATE_FOR_EXACT_REPLAY", reasons


def run(
    features_path: Path,
    out_dir: Path,
    cost_usd: float,
    rolling_window: int,
    bootstrap_n: int,
) -> int:
    if not features_path.exists():
        raise FileNotFoundError(f"Feature CSV not found: {features_path}")
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = now_iso()

    df = pd.read_csv(features_path)
    required = {"entry_utc", "ret_usd", "sweep_depth"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise RuntimeError(f"Feature CSV missing required columns: {missing}")

    df["entry_dt"] = pd.to_datetime(df["entry_utc"], utc=True, errors="coerce")
    df["ret_usd"] = pd.to_numeric(df["ret_usd"], errors="coerce")
    df["sweep_depth"] = pd.to_numeric(df["sweep_depth"], errors="coerce")
    df = df.dropna(subset=["entry_dt", "ret_usd", "sweep_depth"]).sort_values("entry_dt").reset_index(drop=True)

    qs = depth_thresholds(df)
    threshold = qs["q50"]
    filtered = df[df["sweep_depth"] >= threshold].copy()
    filtered["net_x1"] = filtered["ret_usd"] - cost_usd
    filtered["net_x2"] = filtered["ret_usd"] - (2 * cost_usd)
    filtered["net_x4"] = filtered["ret_usd"] - (4 * cost_usd)

    baseline = df.copy()
    baseline["net_x1"] = baseline["ret_usd"] - cost_usd

    raw = metrics(filtered, "ret_usd")
    net = metrics(filtered, "net_x1")
    x2 = metrics(filtered, "net_x2")
    x4 = metrics(filtered, "net_x4")
    base_net = metrics(baseline, "net_x1")

    splits = [
        split_metrics(filtered, "net_x1", 0.60),
        split_metrics(filtered, "net_x1", 0.70),
        split_metrics(filtered, "net_x1", 0.80),
    ]
    year = period_metrics(filtered, "net_x1", "year")
    quarter = period_metrics(filtered, "net_x1", "quarter")
    month = period_metrics(filtered, "net_x1", "month")
    roll = rolling_windows(filtered, "net_x1", rolling_window)
    mfe_mae = mfe_mae_quality(filtered)
    boot = bootstrap_blocks(filtered, "net_x1", bootstrap_n)

    final_decision, reasons = decide(net, x2, splits, year, quarter, roll, boot)

    filtered_csv = out_dir / "stage14d_filtered_outcomes.csv"
    cost_csv = out_dir / "stage14d_cost_stress.csv"
    split_csv = out_dir / "stage14d_chronological_splits.csv"
    year_csv = out_dir / "stage14d_by_year.csv"
    quarter_csv = out_dir / "stage14d_by_quarter.csv"
    month_csv = out_dir / "stage14d_by_month.csv"
    rolling_csv = out_dir / "stage14d_rolling_windows.csv"
    json_path = out_dir / "stage14d_sweep_depth_filter_robustness.json"
    md_path = out_dir / "stage14d_sweep_depth_filter_robustness.md"

    filtered.to_csv(filtered_csv, index=False)
    cost_df = pd.DataFrame([
        {"cost_multiplier": 0, "cost_usd": 0.0, **raw},
        {"cost_multiplier": 1, "cost_usd": cost_usd, **net},
        {"cost_multiplier": 2, "cost_usd": 2 * cost_usd, **x2},
        {"cost_multiplier": 4, "cost_usd": 4 * cost_usd, **x4},
    ])
    cost_df.to_csv(cost_csv, index=False)

    split_rows = []
    for sp in splits:
        for seg in ["train", "test"]:
            row = {"train_frac": sp["train_frac"], "segment": seg}
            row.update(sp[seg])
            split_rows.append(row)
    split_df = pd.DataFrame(split_rows)
    split_df.to_csv(split_csv, index=False)

    year.to_csv(year_csv, index=False)
    quarter.to_csv(quarter_csv, index=False)
    month.to_csv(month_csv, index=False)
    roll.to_csv(rolling_csv, index=False)

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "inputs": {
            "features_path": str(features_path),
            "cost_usd": float(cost_usd),
            "rolling_window": int(rolling_window),
            "bootstrap_n": int(bootstrap_n),
        },
        "filter": {
            "name": "sweep_depth_ge_q50",
            "threshold": threshold,
            "thresholds": qs,
        },
        "final_decision": final_decision,
        "reasons": reasons,
        "baseline_net_x1": base_net,
        "raw_filtered": raw,
        "net_x1": net,
        "net_x2": x2,
        "net_x4": x4,
        "splits": splits,
        "mfe_mae_quality": mfe_mae,
        "bootstrap": boot,
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
        "# Stage 14D Sweep-Depth Filter Robustness",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: focused validation only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Candidate",
        "- mechanism: `prev_day_low_sweep_rejection`",
        "- side: `LONG`",
        "- horizon_bars: `4`",
        "- filter: `sweep_depth_ge_q50`",
        f"- sweep_depth_threshold: `{threshold}`",
        f"- cost_usd: `{cost_usd}`",
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
        "## Baseline vs filtered",
        "| Set | Events | Total | Avg | Median | WR | PF | DD | Pos years | Pos quarters |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| baseline_net_x1_all_candidate | {base_net['events']} | {base_net['total']} | {base_net['avg']} | {base_net['median']} | {base_net['win_rate']} | {base_net['pf']} | {base_net['max_dd']} | {base_net['pos_years']}/{base_net['years']} | {base_net['pos_quarters']}/{base_net['quarters']} |",
        f"| filtered_net_x1 | {net['events']} | {net['total']} | {net['avg']} | {net['median']} | {net['win_rate']} | {net['pf']} | {net['max_dd']} | {net['pos_years']}/{net['years']} | {net['pos_quarters']}/{net['quarters']} |",
        "",
        "## Cost stress",
        "| Cost x | Cost USD | Events | Total | Avg | Median | WR | PF | DD |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in cost_df.to_dict(orient="records"):
        lines.append(
            f"| {r['cost_multiplier']} | {r['cost_usd']} | {r['events']} | {r['total']} | {r['avg']} | "
            f"{r['median']} | {r['win_rate']} | {r['pf']} | {r['max_dd']} |"
        )

    lines += [
        "",
        "## Chronological splits - net x1",
        "| Train frac | Segment | Events | Total | Avg | Median | WR | PF | DD |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in split_df.to_dict(orient="records"):
        lines.append(
            f"| {r['train_frac']} | {r['segment']} | {r['events']} | {r['total']} | {r['avg']} | "
            f"{r['median']} | {r['win_rate']} | {r['pf']} | {r['max_dd']} |"
        )

    lines += [
        "",
        "## Year distribution - net x1",
        "| Year | Events | Total | Avg | Median | WR | PF | DD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in year.to_dict(orient="records"):
        lines.append(
            f"| {r['period']} | {r['events']} | {r['total']} | {r['avg']} | {r['median']} | "
            f"{r['win_rate']} | {r['pf']} | {r['max_dd']} |"
        )

    lines += [
        "",
        "## MFE/MAE quality",
        "```json",
        json.dumps(mfe_mae, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Bootstrap - net x1",
        "```json",
        json.dumps(boot, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Interpretation",
        "- `ROBUST_FILTER_CANDIDATE_FOR_EXACT_REPLAY` permits exact replay validation for this single filtered mechanism only.",
        "- `ROBUST_ENOUGH_FOR_EXACT_REPLAY_BUT_COST_SENSITIVE` permits exact replay but requires strict execution-cost awareness.",
        "- Any failure rejects this filtered candidate definition, not XAUUSD as a market.",
        "- No EA/paper/live/order authorization is granted by this report.",
        "",
        "## Output files",
        f"- filtered_csv: `{filtered_csv}`",
        f"- cost_csv: `{cost_csv}`",
        f"- split_csv: `{split_csv}`",
        f"- year_csv: `{year_csv}`",
        f"- quarter_csv: `{quarter_csv}`",
        f"- month_csv: `{month_csv}`",
        f"- rolling_csv: `{rolling_csv}`",
        f"- json: `{json_path}`",
        f"- md: `{md_path}`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 14D sweep-depth filter robustness: DONE")
    print(f"final_decision={final_decision}")
    print(f"filtered_events={net['events']} net_total={net['total']} net_pf={net['pf']} net_median={net['median']}")
    print(f"Report: {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--features", default=str(DEFAULT_FEATURES))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--cost-usd", type=float, default=0.35)
    p.add_argument("--rolling-window", type=int, default=50)
    p.add_argument("--bootstrap-n", type=int, default=500)
    args = p.parse_args()
    return run(
        features_path=Path(args.features),
        out_dir=Path(args.out_dir),
        cost_usd=args.cost_usd,
        rolling_window=args.rolling_window,
        bootstrap_n=args.bootstrap_n,
    )


if __name__ == "__main__":
    raise SystemExit(main())
