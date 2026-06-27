#!/usr/bin/env python3
"""
Stage69A Parallel Complementary Thesis Megascan

Purpose:
- Run a fast, pre-registered macro/D1 complementary thesis scan.
- Avoid waiting passively for the current robust selector to become active.
- Produce shortlist candidates for later hard audit only.
- No order, no broker, no EA, no paper-live, no live authorization.

Inputs:
- data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv

Outputs:
- summary JSON
- report MD
- candidate CSV
- yearly CSV
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd


HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE69A",
    "NO_THRESHOLD_TUNING_FROM_STAGE69A",
    "NO_PROMOTION_FROM_DISCOVERY_SCAN_ONLY",
]


@dataclass(frozen=True)
class Condition:
    column: str
    op: str
    threshold: float

    def evaluate(self, df: pd.DataFrame) -> pd.Series:
        if self.column not in df.columns:
            return pd.Series(False, index=df.index)
        s = pd.to_numeric(df[self.column], errors="coerce")
        if self.op == ">":
            return s > self.threshold
        if self.op == ">=":
            return s >= self.threshold
        if self.op == "<":
            return s < self.threshold
        if self.op == "<=":
            return s <= self.threshold
        raise ValueError(f"unsupported op: {self.op}")

    def label(self) -> str:
        return f"{self.column}{self.op}{self.threshold}"


@dataclass(frozen=True)
class Thesis:
    thesis_id: str
    family: str
    direction: str
    conditions: Tuple[Condition, ...]
    rationale: str


def default_theses() -> List[Thesis]:
    """Pre-registered complementary theses; no data-mined threshold search."""
    return [
        Thesis(
            thesis_id="T69_DXY_RELIEF_GOLD_TREND",
            family="DOLLAR_RELIEF_CONTINUATION",
            direction="long",
            conditions=(
                Condition("gold_sma20_over_50", ">", 0.0),
                Condition("dxy_ret_20d", "<", 0.0),
            ),
            rationale="Gold trend positive while dollar momentum is falling.",
        ),
        Thesis(
            thesis_id="T69_DXY_TREND_RELIEF_GOLD_TREND",
            family="DOLLAR_RELIEF_CONTINUATION",
            direction="long",
            conditions=(
                Condition("gold_sma20_over_50", ">", 0.0),
                Condition("dxy_sma20_over_50", "<", 0.0),
            ),
            rationale="Gold trend positive while DXY medium trend is weak.",
        ),
        Thesis(
            thesis_id="T69_REALYIELD_RELIEF_GOLD_TREND",
            family="REAL_YIELD_RELIEF_CONTINUATION",
            direction="long",
            conditions=(
                Condition("gold_sma20_over_50", ">", 0.0),
                Condition("real_yield_change_20d", "<", 0.0),
            ),
            rationale="Gold trend positive while real yields are falling.",
        ),
        Thesis(
            thesis_id="T69_DXY_REALYIELD_DUAL_RELIEF",
            family="DUAL_MACRO_RELIEF",
            direction="long",
            conditions=(
                Condition("dxy_ret_20d", "<", 0.0),
                Condition("real_yield_change_20d", "<", 0.0),
            ),
            rationale="Dollar and real-yield pressure both easing.",
        ),
        Thesis(
            thesis_id="T69_ETF_FLOW_TREND",
            family="ETF_FLOW_CONTINUATION",
            direction="long",
            conditions=(
                Condition("gold_sma20_over_50", ">", 0.0),
                Condition("etf_flow_tonnes_3m", ">", 0.0),
            ),
            rationale="Gold trend positive while ETF flow pressure is supportive.",
        ),
        Thesis(
            thesis_id="T69_CENTRAL_BANK_TREND",
            family="CENTRAL_BANK_SUPPORT_CONTINUATION",
            direction="long",
            conditions=(
                Condition("gold_sma20_over_50", ">", 0.0),
                Condition("central_bank_demand_tonnes_3m", ">", 0.0),
            ),
            rationale="Gold trend positive with central-bank net demand support.",
        ),
        Thesis(
            thesis_id="T69_RESILIENT_GOLD_VS_DXY",
            family="GOLD_RESILIENCE_AGAINST_DXY",
            direction="long",
            conditions=(
                Condition("gold_sma20_over_50", ">", 0.0),
                Condition("dxy_ret_20d", ">", 0.0),
                Condition("real_yield_change_20d", "<", 0.0),
            ),
            rationale="Gold trend holds despite dollar strength because real yields ease.",
        ),
        Thesis(
            thesis_id="T69_VOL_RISK_OFF_GOLD_TREND",
            family="VOL_RISK_OFF_CONTINUATION",
            direction="long",
            conditions=(
                Condition("gold_sma20_over_50", ">", 0.0),
                Condition("vix_change_20d", ">", 0.0),
            ),
            rationale="Risk-off volatility impulse with positive gold trend.",
        ),
        Thesis(
            thesis_id="T69_MACRO_SAFE_HAVEN_COMBO",
            family="SAFE_HAVEN_MACRO_COMBO",
            direction="long",
            conditions=(
                Condition("vix_change_20d", ">", 0.0),
                Condition("real_yield_change_20d", "<", 0.0),
            ),
            rationale="Risk-off plus easing real-yield pressure.",
        ),
        Thesis(
            thesis_id="T69_LONG_TREND_ONLY_REFERENCE",
            family="REFERENCE_TREND_ONLY",
            direction="long",
            conditions=(
                Condition("gold_sma50_over_200", ">", 0.0),
            ),
            rationale="Long trend reference; not sufficient alone for promotion.",
        ),
    ]


def load_macro(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"macro dataset not found: {path}")
    df = pd.read_csv(path)
    if "feature_date_utc" not in df.columns:
        raise ValueError("macro dataset must include feature_date_utc")
    if "gold_close" not in df.columns:
        raise ValueError("macro dataset must include gold_close")
    df = df.copy()
    df["feature_date_utc"] = pd.to_datetime(df["feature_date_utc"], utc=True, errors="coerce")
    df["gold_close"] = pd.to_numeric(df["gold_close"], errors="coerce")
    df = df.dropna(subset=["feature_date_utc", "gold_close"]).sort_values("feature_date_utc").reset_index(drop=True)
    return df


def active_mask(df: pd.DataFrame, thesis: Thesis) -> pd.Series:
    m = pd.Series(True, index=df.index)
    for cond in thesis.conditions:
        m = m & cond.evaluate(df)
    return m.fillna(False)


def cooldown_entries(df: pd.DataFrame, active: pd.Series, horizon: int) -> List[int]:
    entries: List[int] = []
    i = 0
    n = len(df)
    active_bool = active.astype(bool).tolist()
    while i < n:
        if not active_bool[i]:
            i += 1
            continue
        exit_i = i + horizon
        if exit_i < n:
            entries.append(i)
        i = max(i + horizon, i + 1)
    return entries


def period_label(dt: pd.Timestamp) -> str:
    y = int(dt.year)
    if y <= 2014:
        return "2011_2014"
    if y <= 2018:
        return "2015_2018"
    if y <= 2022:
        return "2019_2022"
    return "2023_2026"


def calc_return_bps(entry_price: float, exit_price: float, direction: str, cost_bps: float) -> float:
    if entry_price <= 0 or exit_price <= 0:
        return float("nan")
    gross = (exit_price / entry_price - 1.0) * 10000.0
    if direction == "short":
        gross *= -1.0
    return gross - cost_bps


def summarize_returns(values: Sequence[float]) -> Dict[str, Any]:
    vals = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if not vals:
        return {
            "entry_count": 0,
            "mean_net_return_bps": None,
            "median_net_return_bps": None,
            "win_rate": None,
            "min_net_return_bps": None,
            "max_net_return_bps": None,
            "total_net_return_bps": 0.0,
        }
    s = pd.Series(vals, dtype=float)
    return {
        "entry_count": int(len(vals)),
        "mean_net_return_bps": round(float(s.mean()), 4),
        "median_net_return_bps": round(float(s.median()), 4),
        "win_rate": round(float((s > 0).mean()), 4),
        "min_net_return_bps": round(float(s.min()), 4),
        "max_net_return_bps": round(float(s.max()), 4),
        "total_net_return_bps": round(float(s.sum()), 4),
    }


def max_year_share(entry_dates: Sequence[pd.Timestamp]) -> Optional[float]:
    if not entry_dates:
        return None
    years = pd.Series([int(d.year) for d in entry_dates])
    return round(float(years.value_counts().iloc[0] / len(years)), 4)


def run(root: Path, config_path: Path, out_dir: Path) -> Dict[str, Any]:
    cfg = json.loads(config_path.read_text()) if config_path.exists() else {}
    macro_path = root / cfg.get("macro_path", "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv")
    horizons = [int(x) for x in cfg.get("horizons_trading_days", [10, 20, 40, 60, 120])]
    cost_bps = float(cfg.get("cost_bps_total", 50.0))
    min_entries = int(cfg.get("shortlist_min_entries", 20))
    min_mean = float(cfg.get("shortlist_min_mean_net_return_bps", 75.0))
    min_win = float(cfg.get("shortlist_min_win_rate", 0.52))
    min_positive_period_share = float(cfg.get("shortlist_min_positive_period_share", 0.5))
    max_year_share_allowed = float(cfg.get("shortlist_max_year_share", 0.35))

    df = load_macro(macro_path)
    theses = default_theses()

    out_dir.mkdir(parents=True, exist_ok=True)
    candidate_rows: List[Dict[str, Any]] = []
    yearly_rows: List[Dict[str, Any]] = []
    shortlist: List[Dict[str, Any]] = []

    for thesis in theses:
        active = active_mask(df, thesis)
        evaluable = pd.Series(True, index=df.index)
        for cond in thesis.conditions:
            if cond.column not in df.columns:
                evaluable = pd.Series(False, index=df.index)
                break
            evaluable = evaluable & pd.to_numeric(df[cond.column], errors="coerce").notna()

        for horizon in horizons:
            entries_idx = cooldown_entries(df, active, horizon)
            returns: List[float] = []
            entry_dates: List[pd.Timestamp] = []
            periods: Dict[str, List[float]] = {}
            years: Dict[int, List[float]] = {}
            for i in entries_idx:
                exit_i = i + horizon
                if exit_i >= len(df):
                    continue
                entry_price = float(df.loc[i, "gold_close"])
                exit_price = float(df.loc[exit_i, "gold_close"])
                r = calc_return_bps(entry_price, exit_price, thesis.direction, cost_bps)
                if not math.isfinite(r):
                    continue
                dt = df.loc[i, "feature_date_utc"]
                entry_dates.append(dt)
                returns.append(r)
                periods.setdefault(period_label(dt), []).append(r)
                years.setdefault(int(dt.year), []).append(r)

            ret = summarize_returns(returns)
            pos_periods = sum(1 for vals in periods.values() if sum(vals) > 0)
            period_count = len(periods)
            pos_period_share = (pos_periods / period_count) if period_count else 0.0
            m_year_share = max_year_share(entry_dates)
            active_days = int(active.sum())
            ev_rows = int(evaluable.sum())
            row = {
                "thesis_id": thesis.thesis_id,
                "family": thesis.family,
                "direction": thesis.direction,
                "horizon_trading_days": horizon,
                "conditions": ";".join(c.label() for c in thesis.conditions),
                "rationale": thesis.rationale,
                "evaluable_rows": ev_rows,
                "active_days": active_days,
                "active_pct_of_evaluable": round((active_days / ev_rows * 100.0), 4) if ev_rows else 0.0,
                **ret,
                "positive_period_count": pos_periods,
                "period_count_with_entries": period_count,
                "positive_period_share": round(pos_period_share, 4),
                "max_year_entry_share": m_year_share,
                "first_entry_date": str(entry_dates[0].date()) if entry_dates else None,
                "last_entry_date": str(entry_dates[-1].date()) if entry_dates else None,
            }
            passes = (
                ret["entry_count"] >= min_entries
                and (ret["mean_net_return_bps"] is not None and ret["mean_net_return_bps"] >= min_mean)
                and (ret["win_rate"] is not None and ret["win_rate"] >= min_win)
                and pos_period_share >= min_positive_period_share
                and (m_year_share is not None and m_year_share <= max_year_share_allowed)
            )
            row["shortlist_pass"] = bool(passes)
            row["shortlist_reason"] = "PASS_FAST_DISCOVERY" if passes else "WATCH_OR_KILL"
            candidate_rows.append(row)
            if passes:
                shortlist.append(row)

            for y, vals in sorted(years.items()):
                yr = summarize_returns(vals)
                yearly_rows.append({
                    "thesis_id": thesis.thesis_id,
                    "horizon_trading_days": horizon,
                    "year": y,
                    **yr,
                })

    cand_df = pd.DataFrame(candidate_rows).sort_values(
        by=["shortlist_pass", "mean_net_return_bps", "entry_count"],
        ascending=[False, False, False],
        na_position="last",
    )
    yearly_df = pd.DataFrame(yearly_rows)

    candidates_csv = out_dir / "stage69a_parallel_complementary_thesis_megascan_candidates.csv"
    yearly_csv = out_dir / "stage69a_parallel_complementary_thesis_megascan_yearly.csv"
    cand_df.to_csv(candidates_csv, index=False)
    yearly_df.to_csv(yearly_csv, index=False)

    top = cand_df.head(15).to_dict(orient="records")
    pass_fast = cand_df[cand_df["shortlist_pass"] == True].to_dict(orient="records")
    decision = (
        "STAGE69A_SHORTLIST_READY_FOR_HARD_AUDIT_NO_ORDER"
        if pass_fast else
        "STAGE69A_NO_PASS_FAST_COMPLEMENTARY_CANDIDATE_NO_ORDER"
    )
    classification = "S69A_SHORTLIST_READY" if pass_fast else "S69A_NO_SHORTLIST"

    summary = {
        "stage": "Stage69A_PARALLEL_COMPLEMENTARY_THESIS_MEGASCAN",
        "status": "STAGE69A_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "macro_dataset": {
            "path": str(macro_path),
            "rows": int(len(df)),
            "min_date": str(df["feature_date_utc"].min().date()) if len(df) else None,
            "max_date": str(df["feature_date_utc"].max().date()) if len(df) else None,
        },
        "scan": {
            "thesis_count": len(theses),
            "horizons_trading_days": horizons,
            "candidate_count": int(len(cand_df)),
            "pass_fast_count": int(len(pass_fast)),
            "cost_bps_total": cost_bps,
            "selection_constraints": {
                "min_entries": min_entries,
                "min_mean_net_return_bps": min_mean,
                "min_win_rate": min_win,
                "min_positive_period_share": min_positive_period_share,
                "max_year_entry_share": max_year_share_allowed,
            },
        },
        "top_candidates": top,
        "pass_fast_candidates": pass_fast[:20],
        "hard_blocks": HARD_BLOCKS,
        "operator_instructions": [
            "Stage69A is a discovery megascan only and cannot authorize orders.",
            "Do not tune thresholds from Stage69A output alone.",
            "Pass-fast candidates require separate hard audit before any selector/readiness integration.",
            "Broker, EA, paper-live, and live paths remain blocked.",
        ],
        "outputs": {
            "summary_json": str(out_dir / "stage69a_parallel_complementary_thesis_megascan_summary.json"),
            "report_md": str(out_dir / "stage69a_parallel_complementary_thesis_megascan_report.md"),
            "candidates_csv": str(candidates_csv),
            "yearly_csv": str(yearly_csv),
        },
    }

    report = render_report(summary)
    (out_dir / "stage69a_parallel_complementary_thesis_megascan_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    (out_dir / "stage69a_parallel_complementary_thesis_megascan_report.md").write_text(report)
    return summary


def fmt(v: Any) -> str:
    return "None" if v is None else str(v)


def render_report(summary: Dict[str, Any]) -> str:
    lines = []
    lines.append("# Stage69A Parallel Complementary Thesis Megascan")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append(f"- status: `{summary['status']}`")
    lines.append(f"- decision: `{summary['decision']}`")
    lines.append(f"- classification: `{summary['classification']}`")
    lines.append("")
    lines.append("## Macro dataset")
    lines.append("")
    md = summary["macro_dataset"]
    lines.append(f"- rows: `{md['rows']}`")
    lines.append(f"- min_date: `{md['min_date']}`")
    lines.append(f"- max_date: `{md['max_date']}`")
    lines.append(f"- path: `{md['path']}`")
    lines.append("")
    lines.append("## Scan")
    lines.append("")
    sc = summary["scan"]
    lines.append(f"- thesis_count: `{sc['thesis_count']}`")
    lines.append(f"- horizons_trading_days: `{sc['horizons_trading_days']}`")
    lines.append(f"- candidate_count: `{sc['candidate_count']}`")
    lines.append(f"- pass_fast_count: `{sc['pass_fast_count']}`")
    lines.append(f"- cost_bps_total: `{sc['cost_bps_total']}`")
    lines.append("")
    lines.append("## Top candidates")
    lines.append("")
    for c in summary["top_candidates"][:10]:
        lines.append(f"### `{c['thesis_id']}` H{c['horizon_trading_days']}")
        lines.append(f"- family: `{c['family']}`")
        lines.append(f"- entries: `{c['entry_count']}`")
        lines.append(f"- mean_net_return_bps: `{fmt(c['mean_net_return_bps'])}`")
        lines.append(f"- median_net_return_bps: `{fmt(c['median_net_return_bps'])}`")
        lines.append(f"- win_rate: `{fmt(c['win_rate'])}`")
        lines.append(f"- positive_period_share: `{fmt(c['positive_period_share'])}`")
        lines.append(f"- max_year_entry_share: `{fmt(c['max_year_entry_share'])}`")
        lines.append(f"- shortlist_pass: `{c['shortlist_pass']}`")
        lines.append("")
    lines.append("## Hard blocks")
    lines.append("")
    for b in summary["hard_blocks"]:
        lines.append(f"- `{b}`")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage69a_parallel_complementary_thesis_megascan.json")
    ap.add_argument("--out", default="reports/stage69a_parallel_complementary_thesis_megascan")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    summary = run(root, Path(args.config), Path(args.out))
    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "decision": summary["decision"],
        "classification": summary["classification"],
        "pass_fast_count": summary["scan"]["pass_fast_count"],
        "summary_json": summary["outputs"]["summary_json"],
        "report_md": summary["outputs"]["report_md"],
    }, indent=2))


if __name__ == "__main__":
    main()
