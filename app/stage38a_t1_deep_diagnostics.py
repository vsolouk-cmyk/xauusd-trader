#!/usr/bin/env python3
"""
Stage38A T1 Deep Diagnostics

Reads the existing Stage38A T1 read-only trade ledger and variant metrics,
then produces deeper diagnostics for the current best candidate.

This script does NOT create new variants and does NOT touch any execution,
EA, paper/live, order, or broker-related component.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_IN_DIR = "data/reports/stage38a_t1_read_only_test"
DEFAULT_OUT_DIR = "data/reports/stage38a_t1_deep_diagnostics"

BEST_VARIANT = "V3_STRICT_NEXT_BAR_HOLD__rolling_48h_high__TP_1R__TIME_5H"
COMPARE_VARIANTS = [
    "V3_STRICT_NEXT_BAR_HOLD__rolling_48h_high__TP_1R__TIME_5H",
    "V3_STRICT_NEXT_BAR_HOLD__rolling_48h_high__TP_1_5R__TIME_5H",
    "V3_STRICT_NEXT_BAR_HOLD__previous_day_high__TP_1R__TIME_5H",
    "V3_STRICT_NEXT_BAR_HOLD__previous_day_high__TP_1_5R__TIME_5H",
]


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


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
        for r in rows:
            writer.writerow({k: clean_value(r.get(k, "")) for k in fieldnames})


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def clean_value(v: Any) -> Any:
    if isinstance(v, float):
        if math.isinf(v):
            return "inf"
        if math.isnan(v):
            return ""
        return round(v, 8)
    return v


def profit_factor(values: List[float]) -> float:
    wins = sum(v for v in values if v > 0)
    losses = -sum(v for v in values if v < 0)
    if losses == 0:
        return float("inf") if wins > 0 else 0.0
    return wins / losses


def max_drawdown_path(values: List[float]) -> Tuple[float, List[Dict[str, Any]]]:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    rows = []
    for i, v in enumerate(values, 1):
        equity += v
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
        rows.append({
            "seq": i,
            "r_p90": v,
            "equity_R": equity,
            "peak_R": peak,
            "drawdown_R": dd,
        })
    return max_dd, rows


def summarize_values(values: List[float]) -> Dict[str, Any]:
    if not values:
        return {
            "trade_count": 0,
            "pf": 0.0,
            "avg_R": 0.0,
            "win_rate": 0.0,
            "net_R": 0.0,
            "max_dd_R": 0.0,
        }
    max_dd, _ = max_drawdown_path(values)
    return {
        "trade_count": len(values),
        "pf": profit_factor(values),
        "avg_R": sum(values) / len(values),
        "win_rate": sum(1 for v in values if v > 0) / len(values),
        "net_R": sum(values),
        "max_dd_R": max_dd,
    }


def group_metrics(rows: List[Dict[str, str]], key: str, value_col: str = "r_stress_p90") -> List[Dict[str, Any]]:
    groups = defaultdict(list)
    for r in rows:
        groups[r.get(key, "")].append(safe_float(r.get(value_col)))
    out = []
    for k, vals in sorted(groups.items()):
        s = summarize_values(vals)
        s[key] = k
        out.append(s)
    return out


def streaks(values: List[float]) -> Dict[str, Any]:
    max_win = 0
    max_loss = 0
    cur_win = 0
    cur_loss = 0
    for v in values:
        if v > 0:
            cur_win += 1
            cur_loss = 0
        elif v < 0:
            cur_loss += 1
            cur_win = 0
        else:
            cur_win = 0
            cur_loss = 0
        max_win = max(max_win, cur_win)
        max_loss = max(max_loss, cur_loss)
    return {"max_win_streak": max_win, "max_loss_streak": max_loss}


def make_markdown(summary: Dict[str, Any], yearly: List[Dict[str, Any]], monthly_top: List[Dict[str, Any]], comparison: List[Dict[str, Any]]) -> str:
    lines = []
    lines.append("# Stage38A T1 Deep Diagnostics")
    lines.append("")
    lines.append("چپ‌چین ادامه می‌دهم.")
    lines.append("")
    lines.append("## Executive Decision")
    lines.append("")
    lines.append("```text")
    for k in [
        "best_variant",
        "best_trade_count",
        "best_net_R_p90",
        "best_pf_p90",
        "best_avg_R_p90",
        "best_max_dd_R",
        "best_max_loss_streak",
        "robustness_decision",
        "stage39_status",
    ]:
        lines.append(f"{k} = {summary.get(k)}")
    lines.append("```")
    lines.append("")
    lines.append("## Yearly Performance")
    lines.append("")
    lines.append("| year | trades | pf | avg_R | net_R | max_dd |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for r in yearly:
        lines.append(f"| {r.get('year')} | {r.get('trade_count')} | {clean_value(r.get('pf'))} | {clean_value(r.get('avg_R'))} | {clean_value(r.get('net_R'))} | {clean_value(r.get('max_dd_R'))} |")
    lines.append("")
    lines.append("## Top Monthly Net R Contributions")
    lines.append("")
    lines.append("| month | trades | pf | avg_R | net_R | contribution_share |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for r in monthly_top:
        lines.append(f"| {r.get('month')} | {r.get('trade_count')} | {clean_value(r.get('pf'))} | {clean_value(r.get('avg_R'))} | {clean_value(r.get('net_R'))} | {clean_value(r.get('positive_contribution_share'))} |")
    lines.append("")
    lines.append("## Narrow Variant Comparison")
    lines.append("")
    lines.append("| variant | trades | pf | avg_R | net_R | max_dd |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for r in comparison:
        lines.append(f"| {r.get('variant_id')} | {r.get('trade_count')} | {clean_value(r.get('pf'))} | {clean_value(r.get('avg_R'))} | {clean_value(r.get('net_R'))} | {clean_value(r.get('max_dd_R'))} |")
    lines.append("")
    lines.append("## Required Warning")
    lines.append("")
    lines.append("```text")
    lines.append("This is deep diagnostics only.")
    lines.append("It does not create new variants.")
    lines.append("It does not authorize Stage39, EA, paper-live, live execution, or orders.")
    lines.append("```")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage38A T1 deep diagnostics")
    parser.add_argument("--in-dir", default=DEFAULT_IN_DIR)
    parser.add_argument("--out", default=DEFAULT_OUT_DIR)
    parser.add_argument("--best-variant", default=BEST_VARIANT)
    args = parser.parse_args()

    in_dir = Path(args.in_dir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    ledger_path = in_dir / "stage38a_t1_trade_ledger.csv"
    variant_path = in_dir / "stage38a_t1_variant_metrics.csv"
    if not ledger_path.exists():
        raise FileNotFoundError(f"Missing trade ledger: {ledger_path}")
    if not variant_path.exists():
        raise FileNotFoundError(f"Missing variant metrics: {variant_path}")

    ledger = read_csv(ledger_path)
    variant_metrics = read_csv(variant_path)

    best_rows = [r for r in ledger if r.get("variant_id") == args.best_variant]
    if not best_rows:
        raise RuntimeError(f"No trades found for best variant: {args.best_variant}")

    # Sort by entry time for drawdown/streak path.
    best_rows.sort(key=lambda r: r.get("entry_utc", ""))
    best_values = [safe_float(r.get("r_stress_p90")) for r in best_rows]
    max_dd, dd_rows = max_drawdown_path(best_values)

    # Add trade metadata to drawdown rows.
    for dd, trade in zip(dd_rows, best_rows):
        dd["trade_id"] = trade.get("trade_id", "")
        dd["entry_utc"] = trade.get("entry_utc", "")
        dd["exit_utc"] = trade.get("exit_utc", "")
        dd["exit_reason"] = trade.get("exit_reason", "")
        dd["macro_bucket"] = trade.get("macro_bucket", "")

    # Group diagnostics.
    yearly_groups = defaultdict(list)
    monthly_groups = defaultdict(list)
    hourly_groups = defaultdict(list)
    for r in best_rows:
        yearly_groups[r.get("entry_utc", "")[:4]].append(safe_float(r.get("r_stress_p90")))
        monthly_groups[r.get("entry_utc", "")[:7]].append(safe_float(r.get("r_stress_p90")))
        # ISO format: YYYY-MM-DDTHH...
        hour = r.get("entry_utc", "")[11:13]
        hourly_groups[hour].append(safe_float(r.get("r_stress_p90")))

    yearly = []
    for y, vals in sorted(yearly_groups.items()):
        s = summarize_values(vals)
        s["year"] = y
        yearly.append(s)

    monthly = []
    total_positive_net = sum(max(0.0, sum(vals)) for vals in monthly_groups.values())
    for m, vals in sorted(monthly_groups.items()):
        s = summarize_values(vals)
        s["month"] = m
        positive = max(0.0, s["net_R"])
        s["positive_contribution_share"] = (positive / total_positive_net) if total_positive_net > 0 else 0.0
        monthly.append(s)

    hourly = []
    for h, vals in sorted(hourly_groups.items()):
        s = summarize_values(vals)
        s["utc_hour"] = h
        hourly.append(s)

    regime = group_metrics(best_rows, "macro_bucket")
    exit_reasons = group_metrics(best_rows, "exit_reason")

    st = streaks(best_values)
    best_summary = summarize_values(best_values)

    comparison = []
    for vid in COMPARE_VARIANTS:
        vals = [safe_float(r.get("r_stress_p90")) for r in ledger if r.get("variant_id") == vid]
        s = summarize_values(vals)
        s["variant_id"] = vid
        comparison.append(s)

    # Robustness rules.
    positive_years = sum(1 for r in yearly if safe_float(r.get("net_R")) > 0)
    years_count = len(yearly)
    max_month_share = max([safe_float(r.get("positive_contribution_share")) for r in monthly] or [0.0])
    max_year_net = max([safe_float(r.get("net_R")) for r in yearly] or [0.0])
    total_net = safe_float(best_summary.get("net_R"))
    max_year_share = (max_year_net / total_net) if total_net > 0 else 0.0

    robustness_decision = "ROBUSTNESS_FAIL_OR_NEEDS_REVIEW"
    if (
        years_count >= 3
        and positive_years >= 3
        and max_month_share <= 0.35
        and max_year_share <= 0.50
        and safe_float(best_summary.get("pf")) >= 1.10
        and safe_float(best_summary.get("avg_R")) > 0
    ):
        robustness_decision = "ROBUST_RESEARCH_CANDIDATE_NEEDS_READINESS_GATE"

    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "input_dir": str(in_dir),
        "output_dir": str(out_dir),
        "best_variant": args.best_variant,
        "best_trade_count": best_summary["trade_count"],
        "best_net_R_p90": best_summary["net_R"],
        "best_pf_p90": best_summary["pf"],
        "best_avg_R_p90": best_summary["avg_R"],
        "best_win_rate_p90": best_summary["win_rate"],
        "best_max_dd_R": max_dd,
        "best_max_win_streak": st["max_win_streak"],
        "best_max_loss_streak": st["max_loss_streak"],
        "year_count": years_count,
        "positive_year_count": positive_years,
        "max_month_positive_contribution_share": max_month_share,
        "max_year_net_R_share": max_year_share,
        "robustness_decision": robustness_decision,
        "stage39_status": "NO_GO",
        "execution_authorization": "NO_EA_NO_PAPER_NO_LIVE_NO_ORDER",
    }

    write_json(out_dir / "stage38a_t1_deep_diagnostics_summary.json", summary)
    write_csv(out_dir / "stage38a_t1_best_variant_yearly.csv", yearly)
    write_csv(out_dir / "stage38a_t1_best_variant_monthly.csv", monthly)
    write_csv(out_dir / "stage38a_t1_best_variant_hourly.csv", hourly)
    write_csv(out_dir / "stage38a_t1_best_variant_regime.csv", regime)
    write_csv(out_dir / "stage38a_t1_best_variant_drawdown.csv", dd_rows)
    write_csv(out_dir / "stage38a_t1_best_variant_streaks.csv", [st])
    write_csv(out_dir / "stage38a_t1_best_variant_exit_reasons.csv", exit_reasons)
    write_csv(out_dir / "stage38a_t1_variant_comparison_narrowed.csv", comparison)

    monthly_top = sorted(monthly, key=lambda r: safe_float(r.get("positive_contribution_share")), reverse=True)[:10]
    md = make_markdown(summary, yearly, monthly_top, comparison)
    (out_dir / "stage38a_t1_deep_diagnostics.md").write_text(md, encoding="utf-8")

    print("STAGE38A_T1_DEEP_DIAGNOSTICS_DONE")
    print(f"BEST_VARIANT={args.best_variant}")
    print(f"ROBUSTNESS_DECISION={robustness_decision}")
    print(f"REPORT_DIR={out_dir}")
    print("STAGE39=NO_GO")
    print("EA_PAPER_LIVE_ORDER=NO_GO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
