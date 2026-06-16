#!/usr/bin/env python3
"""
Stage38A T1 Locked Structural Filter Retest

Applies a locked, pre-declared structural-expansion filter to the existing
Stage38A T1 trade ledger across all 12 original variants.

This script does not generate new variants and does not modify strategy logic.
It only filters already-generated trades using fixed pre-trade fields.

No Stage39 / EA / paper-live / live order authorization.
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
DEFAULT_OUT_DIR = "data/reports/stage38a_t1_locked_structural_filter_retest"

D1_TREND_PCT_MIN = 0.05
H4_TREND_PCT_MIN = 0.02
ATR_PCT_PRICE_MIN = 0.003


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


def enrich(row: Dict[str, str]) -> Dict[str, Any]:
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

    r["locked_structural_filter"] = bool(d1_ok and h4_ok and atr_ok)
    return r


def metric_row(
    variant_id: str,
    group_name: str,
    rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    values = [float(r["r"]) for r in rows]
    m = summarize(values)
    m["variant_id"] = variant_id
    m["group"] = group_name
    m["supportive_trades"] = sum(1 for r in rows if (r.get("macro_bucket") or r.get("macro_regime")) == "supportive")
    m["neutral_non_hostile_trades"] = sum(1 for r in rows if (r.get("macro_bucket") or r.get("macro_regime")) == "neutral_non_hostile")
    m["tp_count"] = sum(1 for r in rows if r.get("exit_reason") == "TP")
    m["sl_count"] = sum(1 for r in rows if r.get("exit_reason") == "SL")
    m["time_count"] = sum(1 for r in rows if r.get("exit_reason") == "TIME")
    return m


def decision_for(selected: Dict[str, Any], rejected: Dict[str, Any], pre2025: Dict[str, Any]) -> str:
    n = selected["trade_count"]
    pf = safe_float(selected["pf"], 0.0) or 0.0
    avg_r = safe_float(selected["avg_R"], 0.0) or 0.0
    rej_pf = safe_float(rejected["pf"], 0.0) or 0.0
    pre_net = safe_float(pre2025["net_R"], 0.0) or 0.0

    if n >= 50 and pf >= 1.20 and avg_r > 0 and rej_pf < pf and pre_net > -2.0:
        return "LOCKED_FILTER_PASS_RESEARCH"
    if 25 <= n < 50 and pf >= 1.20 and avg_r > 0 and rej_pf < pf and pre_net > -2.0:
        return "LOW_SAMPLE_WATCHLIST"
    if n >= 20 and pf >= 1.00 and avg_r > 0:
        return "WEAK_FEASIBILITY"
    return "KILL_OR_ARCHIVE"


def markdown(summary: Dict[str, Any], variant_rows: List[Dict[str, Any]], by_year: List[Dict[str, Any]]) -> str:
    lines = []
    lines.append("# Stage38A T1 Locked Structural Filter Retest")
    lines.append("")
    lines.append("چپ‌چین ادامه می‌دهم.")
    lines.append("")
    lines.append("## Executive Decision")
    lines.append("")
    lines.append("```text")
    for key in [
        "best_locked_variant",
        "best_locked_decision",
        "best_locked_trade_count",
        "best_locked_pf",
        "best_locked_net_R",
        "pass_count",
        "watch_count",
        "stage39_status",
    ]:
        lines.append(f"{key} = {summary.get(key)}")
    lines.append("```")
    lines.append("")
    lines.append("## Locked Filter")
    lines.append("")
    lines.append("```text")
    lines.append("d1_trend_pct >= 0.05")
    lines.append("h4_trend_pct >= 0.02")
    lines.append("atr_pct_price >= 0.003")
    lines.append("```")
    lines.append("")
    lines.append("## Variant Metrics")
    lines.append("")
    lines.append("| variant | selected_trades | selected_pf | selected_net_R | pre2025_net_R | rejected_pf | decision |")
    lines.append("|---|---:|---:|---:|---:|---:|---|")
    for r in variant_rows:
        lines.append(
            f"| {r.get('variant_id')} | {r.get('selected_trade_count')} | {clean(r.get('selected_pf'))} | "
            f"{clean(r.get('selected_net_R'))} | {clean(r.get('selected_pre2025_net_R'))} | "
            f"{clean(r.get('rejected_pf'))} | {r.get('decision')} |"
        )
    lines.append("")
    lines.append("## Selected Group by Year")
    lines.append("")
    lines.append("| variant | year | trades | pf | avg_R | net_R |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for r in by_year:
        lines.append(
            f"| {r.get('variant_id')} | {r.get('year')} | {r.get('trade_count')} | "
            f"{clean(r.get('pf'))} | {clean(r.get('avg_R'))} | {clean(r.get('net_R'))} |"
        )
    lines.append("")
    lines.append("## Required Warning")
    lines.append("")
    lines.append("```text")
    lines.append("This is a locked-filter diagnostic retest only.")
    lines.append("It does not authorize Stage39, EA, paper-live, live execution, or orders.")
    lines.append("```")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage38A T1 locked structural filter retest")
    parser.add_argument("--ledger", default=DEFAULT_LEDGER)
    parser.add_argument("--out", default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    ledger_path = Path(args.ledger)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not ledger_path.exists():
        raise FileNotFoundError(f"Missing ledger: {ledger_path}")

    rows = [enrich(r) for r in read_csv(ledger_path)]
    variants = sorted({r.get("variant_id", "") for r in rows if r.get("variant_id")})

    variant_rows = []
    by_year_rows = []
    rejected_rows = []
    selected_trades = []

    for vid in variants:
        vrows = [r for r in rows if r.get("variant_id") == vid]
        selected = [r for r in vrows if r.get("locked_structural_filter")]
        rejected = [r for r in vrows if not r.get("locked_structural_filter")]
        pre2025 = [r for r in selected if r.get("year") in ("2022", "2023", "2024")]
        y2025 = [r for r in selected if r.get("year") == "2025"]

        selected_m = metric_row(vid, "selected", selected)
        rejected_m = metric_row(vid, "rejected", rejected)
        pre_m = metric_row(vid, "selected_pre2025", pre2025)
        y25_m = metric_row(vid, "selected_2025", y2025)
        decision = decision_for(selected_m, rejected_m, pre_m)

        variant_rows.append({
            "variant_id": vid,
            "selected_trade_count": selected_m["trade_count"],
            "selected_pf": selected_m["pf"],
            "selected_avg_R": selected_m["avg_R"],
            "selected_net_R": selected_m["net_R"],
            "selected_win_rate": selected_m["win_rate"],
            "selected_max_dd_R": selected_m["max_dd_R"],
            "selected_pre2025_trade_count": pre_m["trade_count"],
            "selected_pre2025_pf": pre_m["pf"],
            "selected_pre2025_net_R": pre_m["net_R"],
            "selected_2025_trade_count": y25_m["trade_count"],
            "selected_2025_pf": y25_m["pf"],
            "selected_2025_net_R": y25_m["net_R"],
            "rejected_trade_count": rejected_m["trade_count"],
            "rejected_pf": rejected_m["pf"],
            "rejected_net_R": rejected_m["net_R"],
            "decision": decision,
        })

        rejected_rows.extend([
            {"variant_id": vid, **rejected_m}
        ])

        for r in selected:
            selected_trades.append(r)

        years = sorted({r.get("year", "") for r in selected if r.get("year")})
        for year in years:
            group = [r for r in selected if r.get("year") == year]
            m = metric_row(vid, "selected", group)
            m["year"] = year
            by_year_rows.append(m)

    def sort_key(r: Dict[str, Any]) -> tuple:
        decision_rank = {
            "LOCKED_FILTER_PASS_RESEARCH": 0,
            "LOW_SAMPLE_WATCHLIST": 1,
            "WEAK_FEASIBILITY": 2,
            "KILL_OR_ARCHIVE": 3,
        }.get(r["decision"], 9)
        pf = safe_float(r.get("selected_pf"), 0.0) or 0.0
        n = int(r.get("selected_trade_count") or 0)
        return (decision_rank, -pf, -n)

    variant_rows.sort(key=sort_key)

    best = variant_rows[0] if variant_rows else {}
    pass_count = sum(1 for r in variant_rows if r["decision"] == "LOCKED_FILTER_PASS_RESEARCH")
    watch_count = sum(1 for r in variant_rows if r["decision"] == "LOW_SAMPLE_WATCHLIST")
    weak_count = sum(1 for r in variant_rows if r["decision"] == "WEAK_FEASIBILITY")
    kill_count = sum(1 for r in variant_rows if r["decision"] == "KILL_OR_ARCHIVE")

    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "input_ledger": str(ledger_path),
        "output_dir": str(out_dir),
        "thresholds": {
            "D1_TREND_PCT_MIN": D1_TREND_PCT_MIN,
            "H4_TREND_PCT_MIN": H4_TREND_PCT_MIN,
            "ATR_PCT_PRICE_MIN": ATR_PCT_PRICE_MIN,
        },
        "variant_count": len(variants),
        "best_locked_variant": best.get("variant_id"),
        "best_locked_decision": best.get("decision"),
        "best_locked_trade_count": best.get("selected_trade_count"),
        "best_locked_pf": best.get("selected_pf"),
        "best_locked_net_R": best.get("selected_net_R"),
        "pass_count": pass_count,
        "watch_count": watch_count,
        "weak_count": weak_count,
        "kill_count": kill_count,
        "stage39_status": "NO_GO",
        "execution_authorization": "NO_EA_NO_PAPER_NO_LIVE_NO_ORDER",
    }

    write_json(out_dir / "stage38a_t1_locked_structural_filter_summary.json", summary)
    write_csv(out_dir / "stage38a_t1_locked_structural_filter_variant_metrics.csv", variant_rows)
    write_csv(out_dir / "stage38a_t1_locked_structural_filter_variant_years.csv", by_year_rows)
    write_csv(out_dir / "stage38a_t1_locked_structural_filter_selected_trades.csv", selected_trades)
    write_csv(out_dir / "stage38a_t1_locked_structural_filter_rejected_metrics.csv", rejected_rows)
    md = markdown(summary, variant_rows, by_year_rows)
    (out_dir / "stage38a_t1_locked_structural_filter_retest.md").write_text(md, encoding="utf-8")

    print("STAGE38A_T1_LOCKED_STRUCTURAL_FILTER_RETEST_DONE")
    print(f"BEST_LOCKED_VARIANT={summary['best_locked_variant']}")
    print(f"BEST_LOCKED_DECISION={summary['best_locked_decision']}")
    print(f"REPORT_DIR={out_dir}")
    print("STAGE39=NO_GO")
    print("EA_PAPER_LIVE_ORDER=NO_GO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
