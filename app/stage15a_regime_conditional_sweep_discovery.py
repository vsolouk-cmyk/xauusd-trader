#!/usr/bin/env python3
"""
Stage 15A — Regime-Conditional Liquidity Sweep Discovery

Purpose:
- Explain why the Stage 14 sweep-depth filtered candidate worked better in 2023-2025
  and failed in 2026.
- Identify whether a *pre-trade observable* regime condition can separate good
  from bad sweep/reclaim environments.

This is NOT:
- a new entry strategy
- a rescue grid
- EA development
- paper/live authorization

Hard rules:
- Research only.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Sequence, Tuple

import pandas as pd


TOOL_VERSION = "v1"
DEFAULT_FEATURES = Path("data/reports/stage14c_behavioral_filter_study/stage14c_candidate_features.csv")
DEFAULT_OUT_DIR = Path("data/reports/stage15a_regime_conditional_sweep_discovery")


@dataclass(frozen=True)
class RegimeSpec:
    name: str
    description: str
    predicate: Callable[[pd.DataFrame], pd.Series]
    observable_pretrade: bool = True


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


def split_metrics(df: pd.DataFrame, ret_col: str, train_frac: float = 0.70) -> Dict:
    x = df.sort_values("entry_dt").reset_index(drop=True)
    cut = int(len(x) * train_frac)
    train = x.iloc[:cut].copy()
    test = x.iloc[cut:].copy()
    return {
        "train_frac": float(train_frac),
        "train": metrics(train, ret_col),
        "test": metrics(test, ret_col),
    }


def period_metrics(df: pd.DataFrame, ret_col: str, period: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    x = df.copy()
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
        row = {"period": p}
        row.update(metrics(g, ret_col))
        rows.append(row)
    return pd.DataFrame(rows).sort_values("period")


def q(series: pd.Series, p: float, default: float = 0.0) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return default
    return float(s.quantile(p))


def normalize_features(df: pd.DataFrame, cost_usd: float) -> pd.DataFrame:
    x = df.copy()
    x["entry_dt"] = pd.to_datetime(x["entry_utc"], utc=True, errors="coerce")
    x["event_dt"] = pd.to_datetime(x.get("event_utc", x["entry_utc"]), utc=True, errors="coerce")
    for c in [
        "ret_usd", "sweep_depth", "reclaim_above_ref", "lower_wick_to_range",
        "close_position_in_range", "bars_since_first_breach", "atr_pct_rank_252",
        "prior_range", "event_close_below_prior_mid", "event_close_above_prior_mid",
        "h4_up_context", "h4_slope_positive", "h4_slope3", "mfe_max_h", "mae_max_h",
    ]:
        if c in x.columns:
            x[c] = pd.to_numeric(x[c], errors="coerce")
    if "event_session" not in x.columns:
        x["event_session"] = "unknown"
    x = x.dropna(subset=["entry_dt", "ret_usd", "sweep_depth"]).sort_values("entry_dt").reset_index(drop=True)
    x["net_x1"] = x["ret_usd"].astype(float) - float(cost_usd)
    x["year"] = x["entry_dt"].dt.year
    x["quarter"] = x["entry_dt"].dt.to_period("Q").astype(str)
    return x


def build_regime_specs(df: pd.DataFrame) -> List[RegimeSpec]:
    d_q50 = q(df["sweep_depth"], 0.50)
    d_q75 = q(df["sweep_depth"], 0.75)
    reclaim_q50 = q(df["reclaim_above_ref"], 0.50) if "reclaim_above_ref" in df.columns else 0.0
    wick_q50 = q(df["lower_wick_to_range"], 0.50) if "lower_wick_to_range" in df.columns else 0.0
    prior_range_q50 = q(df["prior_range"], 0.50) if "prior_range" in df.columns else 0.0

    specs: List[RegimeSpec] = []

    # Time/regime cohorts. These include retrospective labels for diagnosis.
    specs += [
        RegimeSpec("years_2023_2025", "diagnostic cohort: years 2023-2025", lambda d: d["year"].between(2023, 2025), False),
        RegimeSpec("year_2026", "diagnostic cohort: year 2026", lambda d: d["year"].eq(2026), False),
        RegimeSpec("year_not_2026", "diagnostic cohort: excluding 2026", lambda d: ~d["year"].eq(2026), False),
    ]

    # Pre-trade/session conditions.
    for sess in ["asia", "london", "new_york", "late_us"]:
        specs.append(RegimeSpec(f"session_{sess}", f"event_session == {sess}", lambda d, sess=sess: d["event_session"].eq(sess)))
    specs += [
        RegimeSpec("session_london_or_ny", "event during London or New York", lambda d: d["event_session"].isin(["london", "new_york"])),
        RegimeSpec("session_not_new_york", "event not during New York", lambda d: ~d["event_session"].eq("new_york")),
    ]

    # Sweep-depth variants around the Stage14C condition.
    specs += [
        RegimeSpec("sweep_depth_ge_q50", "sweep_depth >= q50", lambda d, v=d_q50: d["sweep_depth"] >= v),
        RegimeSpec("sweep_depth_q50_to_q75", "q50 <= sweep_depth < q75", lambda d, a=d_q50, b=d_q75: (d["sweep_depth"] >= a) & (d["sweep_depth"] < b)),
        RegimeSpec("sweep_depth_ge_q75", "sweep_depth >= q75", lambda d, v=d_q75: d["sweep_depth"] >= v),
    ]

    if "bars_since_first_breach" in df.columns:
        specs += [
            RegimeSpec("fast_reclaim_le_1bar", "reclaim within <=1 bar after first breach", lambda d: d["bars_since_first_breach"] <= 1),
            RegimeSpec("slow_reclaim_gt_1bar", "reclaim after >1 bar", lambda d: d["bars_since_first_breach"] > 1),
        ]

    if "reclaim_above_ref" in df.columns:
        specs += [
            RegimeSpec("reclaim_ge_q50", "reclaim strength >= q50", lambda d, v=reclaim_q50: d["reclaim_above_ref"] >= v),
            RegimeSpec("reclaim_lt_q50", "reclaim strength < q50", lambda d, v=reclaim_q50: d["reclaim_above_ref"] < v),
        ]

    if "lower_wick_to_range" in df.columns:
        specs += [
            RegimeSpec("lower_wick_ratio_ge_q50", "lower wick/range >= q50", lambda d, v=wick_q50: d["lower_wick_to_range"] >= v),
            RegimeSpec("close_pos_ge_60pct", "event close in upper 40% of candle", lambda d: d["close_position_in_range"] >= 0.60),
        ]

    if "atr_pct_rank_252" in df.columns:
        specs += [
            RegimeSpec("atr_low_lt_40", "ATR percentile < 0.40", lambda d: d["atr_pct_rank_252"] < 0.40),
            RegimeSpec("atr_mid_40_85", "ATR percentile 0.40 to 0.85", lambda d: (d["atr_pct_rank_252"] >= 0.40) & (d["atr_pct_rank_252"] <= 0.85)),
            RegimeSpec("atr_high_gt_85", "ATR percentile > 0.85", lambda d: d["atr_pct_rank_252"] > 0.85),
        ]

    if "prior_range" in df.columns:
        specs += [
            RegimeSpec("prior_range_ge_q50", "previous-day range >= q50", lambda d, v=prior_range_q50: d["prior_range"] >= v),
            RegimeSpec("prior_range_lt_q50", "previous-day range < q50", lambda d, v=prior_range_q50: d["prior_range"] < v),
        ]

    # Context conditions.
    if "event_close_below_prior_mid" in df.columns:
        specs += [
            RegimeSpec("close_below_prior_mid", "event close below previous-day midpoint", lambda d: d["event_close_below_prior_mid"].eq(1)),
            RegimeSpec("close_above_prior_mid", "event close above previous-day midpoint", lambda d: d["event_close_above_prior_mid"].eq(1)),
        ]
    if "h4_up_context" in df.columns:
        specs += [
            RegimeSpec("h4_up_context", "H4 close above H4 SMA20", lambda d: d["h4_up_context"].eq(1)),
            RegimeSpec("not_h4_up_context", "H4 close not above H4 SMA20", lambda d: ~d["h4_up_context"].eq(1)),
        ]
    if "h4_slope_positive" in df.columns:
        specs += [
            RegimeSpec("h4_slope_positive", "H4 SMA20 slope3 positive", lambda d: d["h4_slope_positive"].eq(1)),
            RegimeSpec("h4_slope_nonpositive", "H4 SMA20 slope3 non-positive", lambda d: ~d["h4_slope_positive"].eq(1)),
            RegimeSpec("h4_up_and_slope_positive", "H4 up context and positive slope", lambda d: d["h4_up_context"].eq(1) & d["h4_slope_positive"].eq(1)),
        ]

    # Limited interaction candidates, chosen to diagnose 2026 failure rather than search everything.
    specs += [
        RegimeSpec("deep_sweep_london_or_ny", "sweep q50+ and London/NY", lambda d, v=d_q50: (d["sweep_depth"] >= v) & d["event_session"].isin(["london", "new_york"])),
        RegimeSpec("deep_sweep_not_new_york", "sweep q50+ and not NY", lambda d, v=d_q50: (d["sweep_depth"] >= v) & ~d["event_session"].eq("new_york")),
        RegimeSpec("deep_sweep_atr_mid", "sweep q50+ and ATR 0.40-0.85", lambda d, v=d_q50: (d["sweep_depth"] >= v) & (d["atr_pct_rank_252"] >= 0.40) & (d["atr_pct_rank_252"] <= 0.85)),
        RegimeSpec("deep_sweep_h4_slope_positive", "sweep q50+ and H4 slope positive", lambda d, v=d_q50: (d["sweep_depth"] >= v) & d["h4_slope_positive"].eq(1)),
        RegimeSpec("deep_sweep_close_below_mid", "sweep q50+ and close below prior midpoint", lambda d, v=d_q50: (d["sweep_depth"] >= v) & d["event_close_below_prior_mid"].eq(1)),
        RegimeSpec("deep_sweep_fast_reclaim", "sweep q50+ and reclaim <=1 bar", lambda d, v=d_q50: (d["sweep_depth"] >= v) & (d["bars_since_first_breach"] <= 1)),
    ]

    return specs


def evaluate_specs(df: pd.DataFrame, specs: Sequence[RegimeSpec], min_events: int) -> pd.DataFrame:
    rows = []
    base = metrics(df, "net_x1")
    for spec in specs:
        try:
            mask = spec.predicate(df).fillna(False)
        except Exception:
            continue
        sub = df[mask].copy()
        comp = df[~mask].copy()
        if len(sub) < max(10, min_events // 2):
            continue
        m = metrics(sub, "net_x1")
        c = metrics(comp, "net_x1")
        sp70 = split_metrics(sub, "net_x1", 0.70)
        # pass_candidate: not an execution signal; just a regime worth exact validation.
        pass_candidate = (
            spec.observable_pretrade
            and m["events"] >= min_events
            and m["total"] > 0
            and m["pf"] >= 1.20
            and m["median"] > 0
            and m["win_rate"] >= 0.53
            and m["pos_years"] >= max(3, round(max(1, m["years"]) * 0.60))
            and sp70["test"]["events"] >= 25
            and sp70["test"]["total"] > 0
            and sp70["test"]["pf"] >= 1.05
        )
        rows.append({
            "regime": spec.name,
            "description": spec.description,
            "observable_pretrade": bool(spec.observable_pretrade),
            "selected_events": m["events"],
            "coverage": round(m["events"] / max(1, len(df)), 6),
            "net_total": m["total"],
            "net_avg": m["avg"],
            "net_median": m["median"],
            "net_wr": m["win_rate"],
            "net_pf": m["pf"],
            "net_dd": m["max_dd"],
            "pos_years": m["pos_years"],
            "years": m["years"],
            "pos_quarters": m["pos_quarters"],
            "quarters": m["quarters"],
            "complement_events": c["events"],
            "complement_total": c["total"],
            "complement_median": c["median"],
            "complement_pf": c["pf"],
            "test_events": sp70["test"]["events"],
            "test_total": sp70["test"]["total"],
            "test_median": sp70["test"]["median"],
            "test_pf": sp70["test"]["pf"],
            "candidate_flag": bool(pass_candidate),
            "delta_pf_vs_base": round(m["pf"] - base["pf"], 6),
            "delta_median_vs_base": round(m["median"] - base["median"], 6),
            "delta_avg_vs_base": round(m["avg"] - base["avg"], 6),
        })
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    return out.sort_values(
        ["candidate_flag", "observable_pretrade", "net_pf", "net_median", "test_pf", "selected_events"],
        ascending=[False, False, False, False, False, False],
    )


def compare_good_bad_years(df: pd.DataFrame) -> pd.DataFrame:
    """
    Diagnostic only: compare feature distributions between 2023-2025 positive era and 2026 failure.
    """
    a = df[df["year"].between(2023, 2025)].copy()
    b = df[df["year"].eq(2026)].copy()
    cols = [
        "sweep_depth", "reclaim_above_ref", "lower_wick_to_range",
        "close_position_in_range", "bars_since_first_breach", "atr_pct_rank_252",
        "prior_range", "h4_slope3", "ret_usd", "net_x1",
    ]
    rows = []
    for col in cols:
        if col not in df.columns:
            continue
        aa = pd.to_numeric(a[col], errors="coerce").dropna()
        bb = pd.to_numeric(b[col], errors="coerce").dropna()
        if aa.empty or bb.empty:
            continue
        rows.append({
            "feature": col,
            "good_2023_2025_median": round(float(aa.median()), 6),
            "bad_2026_median": round(float(bb.median()), 6),
            "median_delta_good_minus_2026": round(float(aa.median() - bb.median()), 6),
            "good_mean": round(float(aa.mean()), 6),
            "bad_2026_mean": round(float(bb.mean()), 6),
        })
    return pd.DataFrame(rows).sort_values("median_delta_good_minus_2026", ascending=False) if rows else pd.DataFrame()


def decide(regime_summary: pd.DataFrame, current_2026: Dict, goodbad: pd.DataFrame) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    if regime_summary.empty:
        return "INCONCLUSIVE_NO_REGIME_RESULTS", ["No regime condition produced enough rows."]

    cands = regime_summary[regime_summary["candidate_flag"] == True]
    if not cands.empty:
        top = cands.iloc[0].to_dict()
        # If the top condition excludes 2026 or is retrospective, reject it for trading.
        if not top["observable_pretrade"]:
            return "RETROSPECTIVE_ONLY_NOT_TRADABLE", ["Top separator is retrospective/year-based, not a pre-trade condition."]
        reasons.append(f"Top pre-trade regime `{top['regime']}` passed strict diagnostic thresholds.")
        reasons.append("This permits exact replay/robustness for that single regime-conditioned setup only.")
        return "REGIME_CONDITION_CANDIDATE_FOUND", reasons

    # If 2026 is clearly bad and no pre-trade condition separates it, we have an explanation gap.
    if current_2026.get("events", 0) >= 20 and current_2026.get("total", 0) < 0:
        reasons.append("2026 segment is negative, but no pre-trade regime condition passed strict separation thresholds.")
        reasons.append("Do not trade or replay this branch until a pre-trade regime condition explains current-regime failure.")
        return "CURRENT_REGIME_FAILURE_NOT_EXPLAINED", reasons

    top = regime_summary.iloc[0].to_dict()
    if top["net_total"] > 0 and top["net_pf"] > 1.10:
        return "WEAK_REGIME_IMPROVEMENT_ONLY", [f"Best regime `{top['regime']}` is positive but fails strict thresholds."]

    return "NO_REGIME_CONDITION_FOUND", ["No tested regime condition explains/saves the sweep setup."]


def run(
    features_path: Path,
    out_dir: Path,
    cost_usd: float,
    min_events: int,
) -> int:
    if not features_path.exists():
        raise FileNotFoundError(f"Feature CSV not found: {features_path}")
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = now_iso()

    raw = pd.read_csv(features_path)
    df_all = normalize_features(raw, cost_usd)

    # Analyze the Stage14C/14D branch only: sweep_depth >= q50 over the whole candidate set.
    d_q50 = q(df_all["sweep_depth"], 0.50)
    df = df_all[df_all["sweep_depth"] >= d_q50].copy().reset_index(drop=True)

    specs = build_regime_specs(df)
    regime_summary = evaluate_specs(df, specs, min_events=min_events)
    goodbad = compare_good_bad_years(df)
    year = period_metrics(df, "net_x1", "year")
    quarter = period_metrics(df, "net_x1", "quarter")
    base = metrics(df, "net_x1")
    current_2026 = metrics(df[df["year"].eq(2026)], "net_x1")
    final_decision, reasons = decide(regime_summary, current_2026, goodbad)

    features_csv = out_dir / "stage15a_filtered_branch_features.csv"
    regime_csv = out_dir / "stage15a_regime_summary.csv"
    goodbad_csv = out_dir / "stage15a_good_years_vs_2026_feature_compare.csv"
    year_csv = out_dir / "stage15a_by_year.csv"
    quarter_csv = out_dir / "stage15a_by_quarter.csv"
    json_path = out_dir / "stage15a_regime_conditional_sweep_discovery.json"
    md_path = out_dir / "stage15a_regime_conditional_sweep_discovery.md"

    df.to_csv(features_csv, index=False)
    regime_summary.to_csv(regime_csv, index=False)
    goodbad.to_csv(goodbad_csv, index=False)
    year.to_csv(year_csv, index=False)
    quarter.to_csv(quarter_csv, index=False)

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "inputs": {
            "features_path": str(features_path),
            "cost_usd": float(cost_usd),
            "min_events": int(min_events),
        },
        "branch": {
            "base_setup": "prev_day_low_sweep_rejection_LONG_h4",
            "filter": "sweep_depth_ge_q50",
            "sweep_depth_q50": round(float(d_q50), 6),
            "events": int(len(df)),
        },
        "baseline_net_x1": base,
        "current_2026_net_x1": current_2026,
        "final_decision": final_decision,
        "reasons": reasons,
        "top_regimes": regime_summary.head(15).to_dict(orient="records") if not regime_summary.empty else [],
        "good_years_vs_2026_feature_compare": goodbad.to_dict(orient="records") if not goodbad.empty else [],
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
        "# Stage 15A Regime-Conditional Liquidity Sweep Discovery",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: research only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Branch under diagnosis",
        "- setup: `prev_day_low_sweep_rejection`",
        "- side: `LONG`",
        "- horizon_bars: `4`",
        "- branch_filter: `sweep_depth_ge_q50`",
        f"- sweep_depth_q50: `{round(float(d_q50), 6)}`",
        f"- branch_events: `{len(df)}`",
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
        "## Baseline branch net x1",
        "| Events | Total | Avg | Median | WR | PF | DD | Pos years | Pos quarters |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| {base['events']} | {base['total']} | {base['avg']} | {base['median']} | {base['win_rate']} | {base['pf']} | {base['max_dd']} | {base['pos_years']}/{base['years']} | {base['pos_quarters']}/{base['quarters']} |",
        "",
        "## Current 2026 segment net x1",
        "| Events | Total | Avg | Median | WR | PF | DD |",
        "|---:|---:|---:|---:|---:|---:|---:|",
        f"| {current_2026['events']} | {current_2026['total']} | {current_2026['avg']} | {current_2026['median']} | {current_2026['win_rate']} | {current_2026['pf']} | {current_2026['max_dd']} |",
        "",
        "## Top regime conditions",
        "| Rank | Regime | Observable | Events | Coverage | Net total | Net median | WR | PF | DD | Test total | Test PF | Candidate |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    if not regime_summary.empty:
        for i, r in enumerate(regime_summary.head(20).to_dict(orient="records"), 1):
            lines.append(
                f"| {i} | {r['regime']} | {r['observable_pretrade']} | {r['selected_events']} | {r['coverage']} | "
                f"{r['net_total']} | {r['net_median']} | {r['net_wr']} | {r['net_pf']} | {r['net_dd']} | "
                f"{r['test_total']} | {r['test_pf']} | {r['candidate_flag']} |"
            )
    else:
        lines.append("| 0 | none | False | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | False |")

    lines += [
        "",
        "## Year distribution - branch net x1",
        "| Year | Events | Total | Avg | Median | WR | PF | DD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in year.to_dict(orient="records"):
        lines.append(
            f"| {r['period']} | {r['events']} | {r['total']} | {r['avg']} | {r['median']} | {r['win_rate']} | {r['pf']} | {r['max_dd']} |"
        )

    lines += [
        "",
        "## Good years 2023-2025 vs failed 2026 feature deltas",
        "| Feature | Median 2023-2025 | Median 2026 | Delta good minus 2026 |",
        "|---|---:|---:|---:|",
    ]
    if not goodbad.empty:
        for r in goodbad.to_dict(orient="records"):
            lines.append(
                f"| {r['feature']} | {r['good_2023_2025_median']} | {r['bad_2026_median']} | {r['median_delta_good_minus_2026']} |"
            )
    else:
        lines.append("| none | 0 | 0 | 0 |")

    lines += [
        "",
        "## Interpretation",
        "- `REGIME_CONDITION_CANDIDATE_FOUND` permits exact replay/robustness for the top pre-trade regime condition only.",
        "- `CURRENT_REGIME_FAILURE_NOT_EXPLAINED` means the 2026 failure is visible but not explained by the tested pre-trade conditions.",
        "- Retrospective year-based separation is diagnostic only and cannot be traded.",
        "- No EA/paper/live/order authorization is granted.",
        "",
        "## Output files",
        f"- features_csv: `{features_csv}`",
        f"- regime_csv: `{regime_csv}`",
        f"- goodbad_csv: `{goodbad_csv}`",
        f"- year_csv: `{year_csv}`",
        f"- quarter_csv: `{quarter_csv}`",
        f"- json: `{json_path}`",
        f"- md: `{md_path}`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 15A regime-conditional sweep discovery: DONE")
    print(f"final_decision={final_decision}")
    print(f"branch_events={len(df)} current_2026_total={current_2026['total']} current_2026_pf={current_2026['pf']}")
    if not regime_summary.empty:
        top = regime_summary.iloc[0].to_dict()
        print(f"top_regime={top['regime']} net_pf={top['net_pf']} net_median={top['net_median']} candidate={top['candidate_flag']}")
    print(f"Report: {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--features", default=str(DEFAULT_FEATURES))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--cost-usd", type=float, default=0.35)
    p.add_argument("--min-events", type=int, default=60)
    args = p.parse_args()
    return run(
        features_path=Path(args.features),
        out_dir=Path(args.out_dir),
        cost_usd=args.cost_usd,
        min_events=args.min_events,
    )


if __name__ == "__main__":
    raise SystemExit(main())
