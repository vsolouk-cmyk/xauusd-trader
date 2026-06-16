#!/usr/bin/env python3
"""
Stage38A T1 Normalized Regime Filter Diagnostic

Purpose:
  Diagnose whether the 2025-dependent T1 edge can be explained by
  pre-trade observable, normalized structural/volatility conditions.

Important:
  This script does not create new strategy variants.
  It only evaluates coarse, pre-declared diagnostic filters on the existing
  best-variant trade ledger.

No Stage39 / EA / paper-live / order authorization.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_LEDGER = "data/reports/stage38a_t1_read_only_test/stage38a_t1_trade_ledger.csv"
DEFAULT_OUT_DIR = "data/reports/stage38a_t1_normalized_regime_filter_diagnostic"
BEST_VARIANT = "V3_STRICT_NEXT_BAR_HOLD__rolling_48h_high__TP_1R__TIME_5H"


# Coarse, pre-declared diagnostic thresholds.
# These are not optimized and are not authorized trading filters.
D1_TREND_PCT_MIN = 0.05      # D1 close at least 5% above D1 MA50
H4_TREND_PCT_MIN = 0.02      # H4 close at least 2% above H4 MA50
ATR_PCT_PRICE_MIN = 0.003    # H1 ATR at least 0.30% of entry price


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        v = float(value)
        if math.isnan(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


def clean(v: Any) -> Any:
    if isinstance(v, float):
        if math.isinf(v):
            return "inf"
        if math.isnan(v):
            return ""
        return round(v, 8)
    return v


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as f:
        if not fieldnames:
            f.write("")
            return
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: clean(row.get(k, "")) for k in fieldnames})


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def profit_factor(values: List[float]) -> float:
    wins = sum(v for v in values if v > 0)
    losses = -sum(v for v in values if v < 0)
    if losses == 0:
        return float("inf") if wins > 0 else 0.0
    return wins / losses


def max_drawdown(values: List[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for v in values:
        equity += v
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return max_dd


def summarize(values: List[float]) -> Dict[str, Any]:
    if not values:
        return {
            "trade_count": 0,
            "pf": 0.0,
            "avg_R": 0.0,
            "net_R": 0.0,
            "win_rate": 0.0,
            "max_dd_R": 0.0,
        }
    return {
        "trade_count": len(values),
        "pf": profit_factor(values),
        "avg_R": sum(values) / len(values),
        "net_R": sum(values),
        "win_rate": sum(1 for v in values if v > 0) / len(values),
        "max_dd_R": max_drawdown(values),
    }


def percentile(values: List[float], p: float) -> Optional[float]:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    rank = (len(vals) - 1) * p
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return vals[lo]
    frac = rank - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac


def enrich(rows: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    out = []
    for row in rows:
        r: Dict[str, Any] = dict(row)
        r["year"] = row.get("entry_utc", "")[:4]
        r["month"] = row.get("entry_utc", "")[:7]
        r["r"] = safe_float(row.get("r_stress_p90"), 0.0) or 0.0

        d1_close = safe_float(row.get("d1_close"))
        d1_ma50 = safe_float(row.get("d1_ma50"))
        h4_close = safe_float(row.get("h4_close"))
        h4_ma50 = safe_float(row.get("h4_ma50"))
        atr = safe_float(row.get("atr_h1_14"))
        entry_price = safe_float(row.get("entry_price"))

        r["d1_trend_pct"] = ((d1_close - d1_ma50) / d1_ma50) if d1_close is not None and d1_ma50 not in (None, 0) else None
        r["h4_trend_pct"] = ((h4_close - h4_ma50) / h4_ma50) if h4_close is not None and h4_ma50 not in (None, 0) else None
        r["atr_pct_price"] = (atr / entry_price) if atr is not None and entry_price not in (None, 0) else None

        d1_ok = r["d1_trend_pct"] is not None and r["d1_trend_pct"] >= D1_TREND_PCT_MIN
        h4_ok = r["h4_trend_pct"] is not None and r["h4_trend_pct"] >= H4_TREND_PCT_MIN
        atr_ok = r["atr_pct_price"] is not None and r["atr_pct_price"] >= ATR_PCT_PRICE_MIN

        r["filter_d1_trend_pct_5"] = d1_ok
        r["filter_h4_trend_pct_2"] = h4_ok
        r["filter_atr_pct_0_30"] = atr_ok
        r["filter_structural_expansion_all"] = d1_ok and h4_ok and atr_ok
        r["filter_d1_h4_only"] = d1_ok and h4_ok
        r["filter_d1_atr_only"] = d1_ok and atr_ok
        r["filter_h4_atr_only"] = h4_ok and atr_ok

        out.append(r)
    return out


def feature_summary(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    features = [
        "d1_trend_pct",
        "h4_trend_pct",
        "atr_pct_price",
        "macro_score_long_gold",
        "d_real_yield_20d",
        "d_usd_20d_pct",
        "signal_range_atr_ratio",
        "stop_distance_atr_ratio",
    ]
    out = []
    for group_name, predicate in [
        ("pre2025", lambda r: r["year"] in ("2022", "2023", "2024")),
        ("y2025", lambda r: r["year"] == "2025"),
        ("all", lambda r: True),
    ]:
        group = [r for r in rows if predicate(r)]
        perf = summarize([float(r["r"]) for r in group])
        for feature in features:
            vals = []
            for r in group:
                v = safe_float(r.get(feature))
                if v is not None:
                    vals.append(v)
            out.append({
                "group": group_name,
                "feature": feature,
                "n": len(vals),
                "mean": sum(vals) / len(vals) if vals else None,
                "p10": percentile(vals, 0.10),
                "p25": percentile(vals, 0.25),
                "p50": percentile(vals, 0.50),
                "p75": percentile(vals, 0.75),
                "p90": percentile(vals, 0.90),
                "trade_count": perf["trade_count"],
                "pf": perf["pf"],
                "avg_R": perf["avg_R"],
                "net_R": perf["net_R"],
            })
    return out


def filter_diagnostics(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    filters = [
        ("ALL_TRADES", lambda r: True),
        ("D1_TREND_PCT_GE_5", lambda r: bool(r.get("filter_d1_trend_pct_5"))),
        ("H4_TREND_PCT_GE_2", lambda r: bool(r.get("filter_h4_trend_pct_2"))),
        ("ATR_PCT_PRICE_GE_0_30", lambda r: bool(r.get("filter_atr_pct_0_30"))),
        ("D1_AND_H4", lambda r: bool(r.get("filter_d1_h4_only"))),
        ("D1_AND_ATR", lambda r: bool(r.get("filter_d1_atr_only"))),
        ("H4_AND_ATR", lambda r: bool(r.get("filter_h4_atr_only"))),
        ("STRUCTURAL_EXPANSION_ALL", lambda r: bool(r.get("filter_structural_expansion_all"))),
    ]

    out = []
    for filter_name, pred in filters:
        selected = [r for r in rows if pred(r)]
        rejected = [r for r in rows if not pred(r)]
        for group_name, group in [
            ("selected", selected),
            ("rejected", rejected),
            ("selected_pre2025", [r for r in selected if r["year"] in ("2022", "2023", "2024")]),
            ("selected_2025", [r for r in selected if r["year"] == "2025"]),
        ]:
            perf = summarize([float(r["r"]) for r in group])
            out.append({
                "filter_name": filter_name,
                "group": group_name,
                "trade_count": perf["trade_count"],
                "pf": perf["pf"],
                "avg_R": perf["avg_R"],
                "net_R": perf["net_R"],
                "win_rate": perf["win_rate"],
                "max_dd_R": perf["max_dd_R"],
            })
    return out


def filter_by_year(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    filters = [
        ("ALL_TRADES", lambda r: True),
        ("STRUCTURAL_EXPANSION_ALL", lambda r: bool(r.get("filter_structural_expansion_all"))),
        ("D1_AND_H4", lambda r: bool(r.get("filter_d1_h4_only"))),
    ]
    out = []
    for filter_name, pred in filters:
        selected = [r for r in rows if pred(r)]
        years = sorted({r["year"] for r in selected})
        for year in years:
            group = [r for r in selected if r["year"] == year]
            perf = summarize([float(r["r"]) for r in group])
            perf["filter_name"] = filter_name
            perf["year"] = year
            out.append(perf)
    return out


def markdown(summary: Dict[str, Any], filter_rows: List[Dict[str, Any]], feature_rows: List[Dict[str, Any]]) -> str:
    lines = []
    lines.append("# Stage38A T1 Normalized Regime Filter Diagnostic")
    lines.append("")
    lines.append("چپ‌چین ادامه می‌دهم.")
    lines.append("")
    lines.append("## Executive Decision")
    lines.append("")
    lines.append("```text")
    for key in [
        "best_variant",
        "diagnostic_decision",
        "structural_expansion_selected_trades",
        "structural_expansion_selected_pf",
        "structural_expansion_selected_net_R",
        "structural_expansion_pre2025_pf",
        "structural_expansion_pre2025_net_R",
        "stage39_status",
    ]:
        lines.append(f"{key} = {summary.get(key)}")
    lines.append("```")
    lines.append("")
    lines.append("## Filter Diagnostics")
    lines.append("")
    lines.append("| filter | group | trades | pf | avg_R | net_R |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for r in filter_rows:
        lines.append(f"| {r.get('filter_name')} | {r.get('group')} | {r.get('trade_count')} | {clean(r.get('pf'))} | {clean(r.get('avg_R'))} | {clean(r.get('net_R'))} |")
    lines.append("")
    lines.append("## Feature Summary")
    lines.append("")
    lines.append("| group | feature | mean | p50 | p75 | p90 |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for r in feature_rows:
        lines.append(f"| {r.get('group')} | {r.get('feature')} | {clean(r.get('mean'))} | {clean(r.get('p50'))} | {clean(r.get('p75'))} | {clean(r.get('p90'))} |")
    lines.append("")
    lines.append("## Required Warning")
    lines.append("")
    lines.append("```text")
    lines.append("These filters are diagnostic only.")
    lines.append("They are not authorized trading filters.")
    lines.append("No Stage39, EA, paper-live, live execution, or orders are authorized.")
    lines.append("```")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage38A T1 normalized regime filter diagnostic")
    parser.add_argument("--ledger", default=DEFAULT_LEDGER)
    parser.add_argument("--out", default=DEFAULT_OUT_DIR)
    parser.add_argument("--best-variant", default=BEST_VARIANT)
    args = parser.parse_args()

    ledger_path = Path(args.ledger)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not ledger_path.exists():
        raise FileNotFoundError(f"Missing ledger: {ledger_path}")

    raw = read_csv(ledger_path)
    rows = enrich([r for r in raw if r.get("variant_id") == args.best_variant])
    if not rows:
        raise RuntimeError(f"No rows found for variant: {args.best_variant}")

    feature_rows = feature_summary(rows)
    filter_rows = filter_diagnostics(rows)
    filter_year_rows = filter_by_year(rows)

    def lookup(filter_name: str, group: str, metric: str) -> Any:
        for r in filter_rows:
            if r["filter_name"] == filter_name and r["group"] == group:
                return r.get(metric)
        return None

    structural_selected_trades = lookup("STRUCTURAL_EXPANSION_ALL", "selected", "trade_count")
    structural_selected_pf = lookup("STRUCTURAL_EXPANSION_ALL", "selected", "pf")
    structural_selected_net = lookup("STRUCTURAL_EXPANSION_ALL", "selected", "net_R")
    structural_pre_pf = lookup("STRUCTURAL_EXPANSION_ALL", "selected_pre2025", "pf")
    structural_pre_net = lookup("STRUCTURAL_EXPANSION_ALL", "selected_pre2025", "net_R")

    diagnostic_decision = "NO_NORMALIZED_FILTER_CONFIRMED"
    if (
        structural_selected_trades is not None
        and structural_selected_trades >= 30
        and safe_float(structural_selected_pf, 0.0) >= 1.10
        and safe_float(structural_selected_net, 0.0) > 0
        and safe_float(structural_pre_pf, 0.0) >= 0.90
    ):
        diagnostic_decision = "STRUCTURAL_EXPANSION_FILTER_FEASIBLE_NEEDS_LOCKED_RETEST"
    elif (
        structural_selected_trades is not None
        and structural_selected_trades >= 20
        and safe_float(structural_selected_pf, 0.0) >= 1.00
        and safe_float(structural_selected_net, 0.0) > 0
    ):
        diagnostic_decision = "STRUCTURAL_EXPANSION_FILTER_WEAK_FEASIBILITY"

    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "input_ledger": str(ledger_path),
        "output_dir": str(out_dir),
        "best_variant": args.best_variant,
        "thresholds": {
            "D1_TREND_PCT_MIN": D1_TREND_PCT_MIN,
            "H4_TREND_PCT_MIN": H4_TREND_PCT_MIN,
            "ATR_PCT_PRICE_MIN": ATR_PCT_PRICE_MIN,
        },
        "structural_expansion_selected_trades": structural_selected_trades,
        "structural_expansion_selected_pf": structural_selected_pf,
        "structural_expansion_selected_net_R": structural_selected_net,
        "structural_expansion_pre2025_pf": structural_pre_pf,
        "structural_expansion_pre2025_net_R": structural_pre_net,
        "diagnostic_decision": diagnostic_decision,
        "stage39_status": "NO_GO",
        "execution_authorization": "NO_EA_NO_PAPER_NO_LIVE_NO_ORDER",
    }

    write_json(out_dir / "stage38a_t1_normalized_regime_filter_summary.json", summary)
    write_csv(out_dir / "stage38a_t1_normalized_feature_summary.csv", feature_rows)
    write_csv(out_dir / "stage38a_t1_normalized_filter_diagnostics.csv", filter_rows)
    write_csv(out_dir / "stage38a_t1_normalized_filter_by_year.csv", filter_year_rows)

    md = markdown(summary, filter_rows, feature_rows)
    (out_dir / "stage38a_t1_normalized_filter_diagnostic.md").write_text(md, encoding="utf-8")

    print("STAGE38A_T1_NORMALIZED_REGIME_FILTER_DIAGNOSTIC_DONE")
    print(f"DIAGNOSTIC_DECISION={diagnostic_decision}")
    print(f"REPORT_DIR={out_dir}")
    print("STAGE39=NO_GO")
    print("EA_PAPER_LIVE_ORDER=NO_GO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
