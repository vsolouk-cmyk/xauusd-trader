#!/usr/bin/env python3
"""
Stage70 Known-Thesis Convergence Runner

Purpose:
  One finite runner to test a pre-registered list of publicly-known gold/XAUUSD theses
  plus the project's old thesis surface, without opening unlimited parallel paths.

Hard blocks:
  No order, no broker, no EA, no paper-live, no live, no threshold tuning from this scan.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
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
    "NO_ORDER_AUTHORIZATION_FROM_STAGE70",
    "NO_THRESHOLD_TUNING_FROM_KNOWN_THESIS_RUNNER",
    "NO_PROMOTION_FROM_CONVERGENCE_SCAN_ONLY",
]

DEFAULT_MACRO_PATH = "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv"

@dataclass(frozen=True)
class Condition:
    column: str
    operator: str
    threshold: float

@dataclass(frozen=True)
class Thesis:
    thesis_id: str
    list_bucket: str  # known_public_new, known_public_already_covered, old_project, missing_data_public
    family: str
    direction: str
    horizon_trading_days: int
    conditions: Tuple[Condition, ...]
    public_methodology: str
    public_examples: str
    relation_to_project: str
    known_project_status: str
    likely_old_failure_reason: str
    required_data: str
    process_to_system: str


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_config(path: Optional[Path]) -> Dict[str, Any]:
    if not path or not path.exists():
        return {}
    return json.loads(path.read_text())


def get_date_col(df: pd.DataFrame) -> str:
    for c in ["feature_date_utc", "date_utc", "utc_time", "date"]:
        if c in df.columns:
            return c
    raise ValueError("No date column found. Expected feature_date_utc/date_utc/utc_time/date")


def get_price_col(df: pd.DataFrame) -> str:
    for c in ["gold_close", "close"]:
        if c in df.columns:
            return c
    raise ValueError("No gold price column found. Expected gold_close or close")


def op_eval(s: pd.Series, operator: str, threshold: float) -> pd.Series:
    if operator == ">":
        return s > threshold
    if operator == ">=":
        return s >= threshold
    if operator == "<":
        return s < threshold
    if operator == "<=":
        return s <= threshold
    if operator == "==":
        return s == threshold
    raise ValueError(f"Unsupported operator: {operator}")


def eval_thesis_signal(df: pd.DataFrame, thesis: Thesis) -> Tuple[pd.Series, List[str]]:
    missing = [c.column for c in thesis.conditions if c.column not in df.columns]
    if missing:
        return pd.Series([False] * len(df), index=df.index), missing
    mask = pd.Series([True] * len(df), index=df.index)
    for cond in thesis.conditions:
        vals = pd.to_numeric(df[cond.column], errors="coerce")
        mask &= op_eval(vals, cond.operator, cond.threshold).fillna(False)
    return mask.astype(bool), []


def cooldown_entries(mask: pd.Series, horizon: int) -> List[int]:
    idxs: List[int] = []
    next_allowed = -1
    active_indices = [int(i) for i, v in enumerate(mask.to_list()) if bool(v)]
    for i in active_indices:
        if i >= next_allowed:
            idxs.append(i)
            next_allowed = i + max(1, horizon)
    return idxs


def period_label(year: int) -> str:
    if year <= 2014:
        return "2011_2014"
    if year <= 2018:
        return "2015_2018"
    if year <= 2022:
        return "2019_2022"
    return "2023_latest"


def calc_returns(df: pd.DataFrame, entry_indices: List[int], horizon: int, price_col: str, cost_bps: float) -> List[Dict[str, Any]]:
    prices = pd.to_numeric(df[price_col], errors="coerce").reset_index(drop=True)
    dates = pd.to_datetime(df["_date"], errors="coerce").reset_index(drop=True)
    out: List[Dict[str, Any]] = []
    n = len(df)
    for i in entry_indices:
        j = i + horizon
        if j >= n:
            continue
        p0 = prices.iloc[i]
        p1 = prices.iloc[j]
        if not (math.isfinite(p0) and math.isfinite(p1) and p0 > 0):
            continue
        gross = (p1 / p0 - 1.0) * 10000.0
        net = gross - cost_bps
        d0 = dates.iloc[i]
        d1 = dates.iloc[j]
        out.append({
            "entry_index": i,
            "exit_index": j,
            "entry_date": d0.date().isoformat() if pd.notna(d0) else None,
            "exit_date": d1.date().isoformat() if pd.notna(d1) else None,
            "entry_year": int(d0.year) if pd.notna(d0) else None,
            "period": period_label(int(d0.year)) if pd.notna(d0) else None,
            "entry_price": float(p0),
            "exit_price": float(p1),
            "gross_return_bps": float(gross),
            "net_return_bps": float(net),
        })
    return out


def summarize_entries(rows: List[Dict[str, Any]], active_days: int, evaluable_rows: int) -> Dict[str, Any]:
    if not rows:
        return {
            "entry_count": 0,
            "mean_net_return_bps": None,
            "median_net_return_bps": None,
            "win_rate": None,
            "min_net_return_bps": None,
            "max_net_return_bps": None,
            "total_net_return_bps": 0.0,
            "positive_period_share": 0.0,
            "positive_year_share": 0.0,
            "max_year_entry_share": 0.0,
            "active_days": active_days,
            "active_pct_of_evaluable": round(active_days / evaluable_rows * 100, 4) if evaluable_rows else 0.0,
        }
    vals = pd.Series([r["net_return_bps"] for r in rows], dtype="float")
    years = pd.Series([r["entry_year"] for r in rows if r.get("entry_year") is not None])
    periods: Dict[str, List[float]] = {}
    yearly: Dict[int, List[float]] = {}
    for r in rows:
        if r.get("period"):
            periods.setdefault(str(r["period"]), []).append(float(r["net_return_bps"]))
        if r.get("entry_year") is not None:
            yearly.setdefault(int(r["entry_year"]), []).append(float(r["net_return_bps"]))
    period_sums = {k: sum(v) for k, v in periods.items()}
    year_sums = {k: sum(v) for k, v in yearly.items()}
    pos_period_share = sum(1 for v in period_sums.values() if v > 0) / len(period_sums) if period_sums else 0.0
    pos_year_share = sum(1 for v in year_sums.values() if v > 0) / len(year_sums) if year_sums else 0.0
    max_year_share = years.value_counts(normalize=True).max() if len(years) else 0.0
    return {
        "entry_count": int(len(rows)),
        "mean_net_return_bps": round(float(vals.mean()), 4),
        "median_net_return_bps": round(float(vals.median()), 4),
        "win_rate": round(float((vals > 0).mean()), 4),
        "min_net_return_bps": round(float(vals.min()), 4),
        "max_net_return_bps": round(float(vals.max()), 4),
        "total_net_return_bps": round(float(vals.sum()), 4),
        "positive_period_share": round(float(pos_period_share), 4),
        "positive_year_share": round(float(pos_year_share), 4),
        "max_year_entry_share": round(float(max_year_share), 4),
        "active_days": active_days,
        "active_pct_of_evaluable": round(active_days / evaluable_rows * 100, 4) if evaluable_rows else 0.0,
    }


def thesis_catalog() -> List[Thesis]:
    C = Condition
    return [
        Thesis(
            thesis_id="K01_WGC_OPPORTUNITY_COST_RELIEF",
            list_bucket="known_public_already_covered",
            family="OPPORTUNITY_COST_REAL_YIELD_USD",
            direction="long",
            horizon_trading_days=120,
            conditions=(C("real_yield_change_20d", "<", 0.0), C("dxy_ret_20d", "<", 0.0)),
            public_methodology="Gold often responds to opportunity cost: real rates and USD direction.",
            public_examples="World Gold Council GRAM opportunity-cost bucket; bank macro gold notes.",
            relation_to_project="Covered through DXY/real-yield macro relief scans.",
            known_project_status="IMPLEMENTED_MACRO_DAILY",
            likely_old_failure_reason="Overlap with other dollar/real-yield relief rules; slow 20D signals; clustered entries.",
            required_data="DXY, real yield, gold D1.",
            process_to_system="Keep as macro component; do not promote standalone without cluster selection.",
        ),
        Thesis(
            thesis_id="K02_CTA_TIME_SERIES_MOMENTUM_GOLD",
            list_bucket="known_public_already_covered",
            family="CTA_TREND_FOLLOWING",
            direction="long",
            horizon_trading_days=60,
            conditions=(C("gold_sma20_over_50", ">", 0.0), C("gold_sma50_over_200", ">", 0.0)),
            public_methodology="Systematic trend following / time-series momentum in liquid futures including gold.",
            public_examples="AQR / Man AHL / CTA trend-following literature.",
            relation_to_project="Covered by trend references and several macro+trend rules.",
            known_project_status="IMPLEMENTED_REFERENCE",
            likely_old_failure_reason="Trend-only is too broad; high exposure and overlap; needs macro filter or execution overlay.",
            required_data="Gold D1 or futures continuous price; optional volatility target.",
            process_to_system="Use as regime filter or benchmark, not standalone champion.",
        ),
        Thesis(
            thesis_id="K03_WGC_RISK_UNCERTAINTY_SAFE_HAVEN",
            list_bucket="known_public_already_covered",
            family="RISK_UNCERTAINTY_SAFE_HAVEN",
            direction="long",
            horizon_trading_days=120,
            conditions=(C("vix_change_20d", ">", 0.0), C("real_yield_change_20d", "<", 0.0)),
            public_methodology="Risk-off demand works best when opportunity cost is not tightening.",
            public_examples="World Gold Council risk & uncertainty bucket; bank safe-haven commentary.",
            relation_to_project="Covered in D4 / safe-haven macro combo.",
            known_project_status="IMPLEMENTED_MACRO_DAILY",
            likely_old_failure_reason="Risk-off alone is insufficient; geopolitics can fade; needs rate filter and stop discipline.",
            required_data="VIX, real yield, gold D1; optional event calendar.",
            process_to_system="Audit as diversifier; do not merge blindly with DXY relief.",
        ),
        Thesis(
            thesis_id="K04_ETF_FLOW_CONTINUATION",
            list_bucket="known_public_already_covered",
            family="ETF_FLOW_CONTINUATION",
            direction="long",
            horizon_trading_days=60,
            conditions=(C("gold_sma20_over_50", ">", 0.0), C("etf_flow_tonnes_3m", ">", 0.0)),
            public_methodology="ETF demand is a marginal short/medium-term investment demand driver.",
            public_examples="World Gold Council ETF flow research; bank ETF-demand gold outlooks.",
            relation_to_project="Covered after Stage67D6 ETF mapping.",
            known_project_status="IMPLEMENTED_MACRO_DAILY",
            likely_old_failure_reason="Monthly flow data lags; broad exposure; overlaps trend and central-bank demand.",
            required_data="WGC ETF monthly flows, gold D1.",
            process_to_system="Use as supportive feature; audit lag and reporting delay explicitly.",
        ),
        Thesis(
            thesis_id="K05_CENTRAL_BANK_SUPPORT_CONTINUATION",
            list_bucket="known_public_already_covered",
            family="CENTRAL_BANK_DEMAND",
            direction="long",
            horizon_trading_days=60,
            conditions=(C("gold_sma20_over_50", ">", 0.0), C("central_bank_demand_tonnes_3m", ">", 0.0)),
            public_methodology="Official-sector buying can provide structural support but may not drive short-term timing alone.",
            public_examples="World Gold Council central bank demand; Reuters/ING/Goldman commentary.",
            relation_to_project="Covered after Stage67E central-bank changes mapper.",
            known_project_status="IMPLEMENTED_MACRO_DAILY",
            likely_old_failure_reason="Monthly/lagged data; support thesis may not time entries; overlaps broad gold trend.",
            required_data="WGC monthly central-bank changes, gold D1.",
            process_to_system="Keep as regime prior; require timing confirmation.",
        ),
        Thesis(
            thesis_id="K06_RESILIENT_GOLD_VS_DXY",
            list_bucket="known_public_new_champion",
            family="GOLD_RESILIENCE_AGAINST_DXY",
            direction="long",
            horizon_trading_days=120,
            conditions=(C("gold_sma20_over_50", ">", 0.0), C("dxy_ret_20d", ">", 0.0), C("real_yield_change_20d", "<", 0.0)),
            public_methodology="Gold rising/holding despite USD strength can indicate real-yield relief or non-dollar demand dominance.",
            public_examples="Institutional macro framing: dollar strength headwind overridden by real-yield or reserve/flow support.",
            relation_to_project="New champion selected from Stage69A; less redundant than simple DXY relief.",
            known_project_status="NEW_CHAMPION_TO_AUDIT",
            likely_old_failure_reason="Not previously isolated; old scans favored relief rather than resilience regimes.",
            required_data="Gold D1, DXY, real yield; optional ETF/central bank confirmation.",
            process_to_system="Hard audit only this champion; if fail, close Stage69 before opening more.",
        ),
        Thesis(
            thesis_id="K07_DXY_TREND_RELIEF_GOLD_TREND",
            list_bucket="known_public_already_covered",
            family="DOLLAR_RELIEF_CONTINUATION",
            direction="long",
            horizon_trading_days=120,
            conditions=(C("gold_sma20_over_50", ">", 0.0), C("dxy_sma20_over_50", "<", 0.0)),
            public_methodology="Gold trend continuation when the dollar medium trend weakens.",
            public_examples="Common macro/technical gold strategy: weak USD + gold trend.",
            relation_to_project="Close to D3 and Stage69A top candidate; reference only unless champion fails.",
            known_project_status="IMPLEMENTED_REFERENCE",
            likely_old_failure_reason="High overlap with D3 and D1; not sufficiently distinct.",
            required_data="DXY, gold trend.",
            process_to_system="Reference benchmark; not next champion unless resilience fails.",
        ),
        Thesis(
            thesis_id="K08_COT_POSITIONING_EXTREME_REVERSAL",
            list_bucket="missing_data_public",
            family="POSITIONING_SENTIMENT_COT",
            direction="long_or_short",
            horizon_trading_days=20,
            conditions=(C("cot_managed_money_z", "<", -1.5), C("gold_sma20_over_50", ">", 0.0)),
            public_methodology="CFTC COT managed-money extremes can identify crowded trend or contrarian setups.",
            public_examples="CFTC COT reports; CME/COT tools.",
            relation_to_project="Earlier COT work existed but not in current macro selector dataset.",
            known_project_status="PARTIAL_ARCHIVED_OR_MISSING_CURRENT_COLUMNS",
            likely_old_failure_reason="Weekly data alignment, crowding can persist, and COT by itself is not timing.",
            required_data="CFTC disaggregated gold COT, managed money long/short/spreading, weekly lag handling.",
            process_to_system="Reintroduce only via a bounded weekly overlay test if current macro champion fails.",
        ),
        Thesis(
            thesis_id="K09_INTRADAY_LONDON_NY_LIQUIDITY_BREAKOUT",
            list_bucket="missing_data_public",
            family="INTRADAY_LIQUIDITY_SESSION",
            direction="long_or_short",
            horizon_trading_days=1,
            conditions=(C("session_breakout_signal", ">", 0.0),),
            public_methodology="Gold liquidity clusters around London/NY overlap, COMEX hours, fixes, and macro data releases.",
            public_examples="Common discretionary/proprietary XAUUSD execution playbook: session breakout/range/stop-run.",
            relation_to_project="Earlier Asia/range and intraday research existed, but current macro runner is D1-only.",
            known_project_status="ARCHIVED_OR_NEEDS_M5_FEATURES",
            likely_old_failure_reason="Spread/slippage, stop-run noise, session definition, broker feed dependence.",
            required_data="M1/M5 bars, session calendar, spread, news timestamps, intraday volatility.",
            process_to_system="Only after macro system convergence, build one intraday confirmation layer; not a parallel rabbit hole.",
        ),
        Thesis(
            thesis_id="K10_EVENT_SHOCK_CONTINUATION_OR_REVERSAL",
            list_bucket="missing_data_public",
            family="EVENT_MACRO_SHOCK",
            direction="long_or_short",
            horizon_trading_days=5,
            conditions=(C("macro_event_surprise_z", ">", 1.0),),
            public_methodology="Gold reacts to CPI, NFP, FOMC and real-yield/dollar surprise; reaction may continue or reverse.",
            public_examples="Bank event desks and macro discretionary traders; Reuters daily gold driver reports.",
            relation_to_project="Calendar work existed but surprise data is not yet integrated.",
            known_project_status="NEEDS_EVENT_SURPRISE_DATA",
            likely_old_failure_reason="Event labels without surprise magnitude are too weak; high slippage around releases.",
            required_data="Economic calendar, actual/consensus/previous, timestamp, DXY/yield immediate reaction, M1/M5 spreads.",
            process_to_system="Can be a later execution overlay, not core system until surprise database exists.",
        ),
        Thesis(
            thesis_id="O01_H64L_V2",
            list_bucket="old_project",
            family="H64L_FULL_MACRO_TAILWIND",
            direction="long",
            horizon_trading_days=120,
            conditions=(C("gold_sma20_over_50", ">", 0.0), C("dxy_ret_20d", "<", 0.0), C("real_yield_change_20d", "<", 0.0), C("etf_flow_tonnes_3m", ">", 0.0), C("central_bank_demand_tonnes_3m", ">", 0.0), C("gold_sma50_over_200", ">", 0.0)),
            public_methodology="Multi-driver macro tailwind: trend + dollar relief + real-yield relief + flows.",
            public_examples="Composite of public gold driver families.",
            relation_to_project="Stage64/66/68 primary rule.",
            known_project_status="SHADOW_SELECTOR_COMPONENT",
            likely_old_failure_reason="Too strict; low frequency; no unique active days versus D1; recent not active.",
            required_data="Full macro dataset.",
            process_to_system="Keep only as quality overlay inside robust selector, not sole system.",
        ),
        Thesis(
            thesis_id="O02_D3_H60",
            list_bucket="old_project",
            family="DOLLAR_RELIEF_CONTINUATION",
            direction="long",
            horizon_trading_days=60,
            conditions=(C("gold_sma20_over_50", ">", 0.0), C("dxy_sma20_over_50", "<", 0.0), C("dxy_ret_20d", "<", 0.0)),
            public_methodology="Gold trend continuation with weak dollar momentum/trend.",
            public_examples="Common public macro/CTA hybrid.",
            relation_to_project="Stage66E/68F robust policy primary.",
            known_project_status="ROBUST_POLICY_PRIMARY_SHADOW",
            likely_old_failure_reason="Inactive in current regime; overlap with DXY relief families; not enough alone.",
            required_data="Gold D1, DXY.",
            process_to_system="Daily shadow monitor only; no order path without activation playbook and governance.",
        ),
        Thesis(
            thesis_id="O03_D4_H60",
            list_bucket="old_project",
            family="VOL_RISK_OFF_REAL_YIELD",
            direction="long",
            horizon_trading_days=60,
            conditions=(C("gold_sma20_over_50", ">", 0.0), C("vix_change_20d", ">", 0.0), C("real_yield_change_20d", "<", 0.0)),
            public_methodology="Risk-off plus easing opportunity cost.",
            public_examples="Safe-haven/risk uncertainty public thesis.",
            relation_to_project="Stage66K/68F diversifier.",
            known_project_status="ROBUST_POLICY_DIVERSIFIER_SHADOW",
            likely_old_failure_reason="Needs gold trend; risk-off alone insufficient; currently real-yield filter fails.",
            required_data="Gold D1, VIX, real yield.",
            process_to_system="Keep as diversifier only; no separate readiness path.",
        ),
        Thesis(
            thesis_id="O04_D1_REFERENCE",
            list_bucket="old_project",
            family="DXY_REALYIELD_RELIEF",
            direction="long",
            horizon_trading_days=60,
            conditions=(C("gold_sma20_over_50", ">", 0.0), C("dxy_ret_20d", "<", 0.0), C("real_yield_change_20d", "<", 0.0)),
            public_methodology="DXY + real-yield relief with gold trend.",
            public_examples="Public opportunity-cost macro thesis.",
            relation_to_project="Stage66K backup, later reference-only after overlap audit.",
            known_project_status="REFERENCE_ONLY_EXCLUDED_FROM_POLICY",
            likely_old_failure_reason="Near-total overlap and low incremental active-day contribution.",
            required_data="Gold D1, DXY, real yield.",
            process_to_system="Do not promote unless future evidence contradicts overlap/incremental weakness.",
        ),
    ]


def pass_fast(summary: Dict[str, Any], constraints: Dict[str, Any]) -> bool:
    if summary.get("entry_count", 0) < constraints["min_entries"]:
        return False
    if summary.get("mean_net_return_bps") is None or summary["mean_net_return_bps"] < constraints["min_mean_net_return_bps"]:
        return False
    if summary.get("win_rate") is None or summary["win_rate"] < constraints["min_win_rate"]:
        return False
    if summary.get("positive_period_share", 0) < constraints["min_positive_period_share"]:
        return False
    if summary.get("max_year_entry_share", 1) > constraints["max_year_entry_share"]:
        return False
    return True


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default=None)
    ap.add_argument("--out", default="reports/stage70_known_thesis_convergence_runner")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    cfg = read_config(Path(args.config)) if args.config else {}
    macro_path = root / cfg.get("macro_path", DEFAULT_MACRO_PATH)
    out_dir = root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    constraints = {
        "min_entries": int(cfg.get("min_entries", 20)),
        "min_mean_net_return_bps": float(cfg.get("min_mean_net_return_bps", 100.0)),
        "min_win_rate": float(cfg.get("min_win_rate", 0.55)),
        "min_positive_period_share": float(cfg.get("min_positive_period_share", 0.75)),
        "max_year_entry_share": float(cfg.get("max_year_entry_share", 0.30)),
    }
    cost_bps = float(cfg.get("cost_bps_total", 50.0))
    max_followup_tests = int(cfg.get("max_followup_tests", 10))

    issues: List[str] = []
    if not macro_path.exists():
        raise FileNotFoundError(f"Macro dataset not found: {macro_path}")
    df = pd.read_csv(macro_path)
    date_col = get_date_col(df)
    price_col = get_price_col(df)
    df["_date"] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.sort_values("_date").reset_index(drop=True)
    raw_rows = len(df)
    df = df[pd.notna(df["_date"])].reset_index(drop=True)
    price = pd.to_numeric(df[price_col], errors="coerce")
    df = df[price.notna()].reset_index(drop=True)

    theses = thesis_catalog()

    catalog_rows = []
    result_rows = []
    entry_rows = []
    missing_rows = []
    for t in theses:
        catalog_rows.append({
            "thesis_id": t.thesis_id,
            "list_bucket": t.list_bucket,
            "family": t.family,
            "direction": t.direction,
            "horizon_trading_days": t.horizon_trading_days,
            "conditions": ";".join(f"{c.column}{c.operator}{c.threshold}" for c in t.conditions),
            "public_methodology": t.public_methodology,
            "public_examples": t.public_examples,
            "relation_to_project": t.relation_to_project,
            "known_project_status": t.known_project_status,
            "likely_old_failure_reason": t.likely_old_failure_reason,
            "required_data": t.required_data,
            "process_to_system": t.process_to_system,
        })
        mask, missing = eval_thesis_signal(df, t)
        if missing:
            missing_rows.append({
                "thesis_id": t.thesis_id,
                "missing_columns": ";".join(missing),
                "required_data": t.required_data,
                "process_to_system": t.process_to_system,
            })
            result_rows.append({
                "thesis_id": t.thesis_id,
                "list_bucket": t.list_bucket,
                "family": t.family,
                "horizon_trading_days": t.horizon_trading_days,
                "scan_status": "SKIPPED_MISSING_COLUMNS",
                "missing_columns": ";".join(missing),
            })
            continue
        evaluable = int(mask.notna().sum())
        active_days = int(mask.sum())
        entries = cooldown_entries(mask, t.horizon_trading_days)
        returns = calc_returns(df, entries, t.horizon_trading_days, price_col, cost_bps)
        sm = summarize_entries(returns, active_days, evaluable)
        p = pass_fast(sm, constraints)
        result = {
            "thesis_id": t.thesis_id,
            "list_bucket": t.list_bucket,
            "family": t.family,
            "direction": t.direction,
            "horizon_trading_days": t.horizon_trading_days,
            "conditions": ";".join(f"{c.column}{c.operator}{c.threshold}" for c in t.conditions),
            "scan_status": "TESTED",
            "missing_columns": "",
            **sm,
            "pass_fast": bool(p),
            "known_project_status": t.known_project_status,
            "relation_to_project": t.relation_to_project,
            "likely_old_failure_reason": t.likely_old_failure_reason,
        }
        result_rows.append(result)
        for r in returns:
            rr = dict(r)
            rr.update({"thesis_id": t.thesis_id, "family": t.family, "horizon_trading_days": t.horizon_trading_days})
            entry_rows.append(rr)

    catalog_df = pd.DataFrame(catalog_rows)
    results_df = pd.DataFrame(result_rows)
    entries_df = pd.DataFrame(entry_rows)
    missing_df = pd.DataFrame(missing_rows)

    # Convergence decision: never keep more than one new champion plus old monitor.
    tested = results_df[results_df["scan_status"].eq("TESTED")].copy()
    passfast = tested[tested.get("pass_fast", False).eq(True)].copy() if not tested.empty else tested
    champion_rows = passfast[passfast["thesis_id"].eq("K06_RESILIENT_GOLD_VS_DXY")]
    if champion_rows.empty and not passfast.empty:
        # Fallback score: robust first, not purely mean chasing.
        passfast["score"] = (
            passfast["mean_net_return_bps"].fillna(0) * 0.40
            + passfast["median_net_return_bps"].fillna(0) * 0.25
            + passfast["win_rate"].fillna(0) * 1000 * 0.20
            + passfast["positive_period_share"].fillna(0) * 500 * 0.15
        )
        champion_rows = passfast.sort_values("score", ascending=False).head(1)
    selected_champion = champion_rows.iloc[0].to_dict() if not champion_rows.empty else None

    if selected_champion:
        decision = "STAGE70_CHAMPION_SELECTED_FOR_SINGLE_HARD_AUDIT_NO_ORDER"
        classification = "S70_CONVERGENCE_CHAMPION_SELECTED"
    else:
        decision = "STAGE70_NO_TESTABLE_CHAMPION_CLOSE_OR_REQUEST_DATA_NO_ORDER"
        classification = "S70_NO_CHAMPION"
        issues.append("NO_PASS_FAST_TESTABLE_CHAMPION")

    old_monitor = ["O02_D3_H60", "O01_H64L_V2", "O03_D4_H60"]
    locked_scope = {
        "daily_shadow_monitor": "Stage67D6 -> Stage67E -> Stage68F",
        "old_policy_monitor_rules": old_monitor,
        "new_champion": selected_champion.get("thesis_id") if selected_champion else None,
        "max_followup_tests_total": max_followup_tests,
        "allowed_next_step": "ONE_CHAMPION_HARD_AUDIT_ONLY",
        "forbidden_next_steps": [
            "NO_NEW_MEGASCAN_UNTIL_CHAMPION_CLOSED",
            "NO_AUDIT_OF_ALL_PASS_FAST_CANDIDATES",
            "NO_READINESS_INTEGRATION_FROM_THIS_RUN",
            "NO_DEMO_EA_FROM_THIS_RUN",
            "NO_LIVE_TIMELINE_PROMISE",
        ],
    }

    # Write outputs.
    catalog_path = out_dir / "stage70_known_thesis_catalog.csv"
    results_path = out_dir / "stage70_known_vs_old_thesis_scan_results.csv"
    entries_path = out_dir / "stage70_thesis_entry_returns.csv"
    missing_path = out_dir / "stage70_missing_data_requirements.csv"
    summary_path = out_dir / "stage70_known_thesis_convergence_runner_summary.json"
    report_path = out_dir / "stage70_known_thesis_convergence_runner_report.md"

    catalog_df.to_csv(catalog_path, index=False)
    results_df.to_csv(results_path, index=False)
    entries_df.to_csv(entries_path, index=False)
    missing_df.to_csv(missing_path, index=False)

    summary = {
        "stage": "Stage70_KNOWN_THESIS_CONVERGENCE_RUNNER",
        "status": "STAGE70_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "macro_dataset": {
            "path": str(macro_path),
            "rows_raw": raw_rows,
            "rows_used": len(df),
            "min_date": df["_date"].min().date().isoformat() if len(df) else None,
            "max_date": df["_date"].max().date().isoformat() if len(df) else None,
            "sha256": sha256_file(macro_path),
        },
        "scan": {
            "catalog_thesis_count": len(theses),
            "tested_count": int((results_df["scan_status"] == "TESTED").sum()) if not results_df.empty else 0,
            "skipped_missing_data_count": int((results_df["scan_status"] == "SKIPPED_MISSING_COLUMNS").sum()) if not results_df.empty else 0,
            "pass_fast_count": int(results_df["pass_fast"].map(lambda x: bool(x) if pd.notna(x) else False).sum()) if (not results_df.empty and "pass_fast" in results_df.columns) else 0,
            "cost_bps_total": cost_bps,
            "constraints": constraints,
        },
        "selected_champion": selected_champion,
        "locked_scope": locked_scope,
        "issues": issues,
        "hard_blocks": HARD_BLOCKS,
        "outputs": {
            "summary_json": str(summary_path),
            "report_md": str(report_path),
            "catalog_csv": str(catalog_path),
            "scan_results_csv": str(results_path),
            "entry_returns_csv": str(entries_path),
            "missing_data_csv": str(missing_path),
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    top_cols = ["thesis_id", "list_bucket", "family", "horizon_trading_days", "entry_count", "mean_net_return_bps", "median_net_return_bps", "win_rate", "positive_period_share", "max_year_entry_share", "pass_fast"]
    top = tested.sort_values(["pass_fast", "mean_net_return_bps"], ascending=[False, False]).head(12) if not tested.empty else tested
    lines = []
    lines.append("# Stage70 Known-Thesis Convergence Runner")
    lines.append("")
    lines.append("## Decision")
    lines.append(f"- status: `STAGE70_COMPLETE_NO_PROMOTION`")
    lines.append(f"- decision: `{decision}`")
    lines.append(f"- classification: `{classification}`")
    lines.append("")
    lines.append("## Convergence rule")
    lines.append("- No new megascan until the selected champion is closed, killed, or promoted to no-order shadow candidate.")
    lines.append("- Do not audit all pass-fast rows.")
    lines.append("- Keep Stage68F only as daily shadow monitor.")
    lines.append("")
    lines.append("## Selected champion")
    if selected_champion:
        lines.append(f"- thesis_id: `{selected_champion.get('thesis_id')}`")
        lines.append(f"- family: `{selected_champion.get('family')}`")
        lines.append(f"- horizon_trading_days: `{selected_champion.get('horizon_trading_days')}`")
        lines.append(f"- mean_net_return_bps: `{selected_champion.get('mean_net_return_bps')}`")
        lines.append(f"- win_rate: `{selected_champion.get('win_rate')}`")
        lines.append(f"- positive_period_share: `{selected_champion.get('positive_period_share')}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Top tested rows")
    if not top.empty:
        for _, r in top.iterrows():
            lines.append(f"- `{r.get('thesis_id')}` H{r.get('horizon_trading_days')}: entries=`{r.get('entry_count')}`, mean_net=`{r.get('mean_net_return_bps')}`, win=`{r.get('win_rate')}`, pass_fast=`{r.get('pass_fast')}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Missing-data public theses")
    if not missing_df.empty:
        for _, r in missing_df.iterrows():
            lines.append(f"- `{r['thesis_id']}` missing `{r['missing_columns']}`; required: {r['required_data']}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Hard blocks")
    for hb in HARD_BLOCKS:
        lines.append(f"- `{hb}`")
    report_path.write_text("\n".join(lines))

    print(json.dumps({
        "stage": "Stage70_KNOWN_THESIS_CONVERGENCE_RUNNER",
        "status": "STAGE70_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "selected_champion": locked_scope["new_champion"],
        "summary_json": str(summary_path),
        "report_md": str(report_path),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
