#!/usr/bin/env python3
"""
Stage38A T1 Locked Candidate Final Diagnostics

Final diagnostic pass for the current locked T1 structural-expansion candidate.

This script:
- reads the existing Stage38A T1 trade ledger,
- applies the locked structural-expansion filter,
- selects the current locked lead variant,
- produces concentration/drawdown/monthly/hourly/exit diagnostics.

It does not create new variants and does not authorize Stage39, EA, paper-live,
live execution, or orders.
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


DEFAULT_LEDGER = "data/reports/stage38a_t1_read_only_test/stage38a_t1_trade_ledger.csv"
DEFAULT_OUT_DIR = "data/reports/stage38a_t1_locked_candidate_final_diagnostics"

LEAD_VARIANT = "V1_CLOSE_ACCEPTANCE__previous_day_high__TP_1_5R__TIME_5H"

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


def max_drawdown_path(values: List[float], rows: List[Dict[str, Any]]) -> Tuple[float, List[Dict[str, Any]]]:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    out = []
    for i, (value, row) in enumerate(zip(values, rows), 1):
        equity += value
        peak = max(peak, equity)
        dd = peak - equity
        max_dd = max(max_dd, dd)
        out.append({
            "seq": i,
            "trade_id": row.get("trade_id", ""),
            "entry_utc": row.get("entry_utc", ""),
            "exit_utc": row.get("exit_utc", ""),
            "year": row.get("year", ""),
            "month": row.get("month", ""),
            "r_p90": value,
            "equity_R": equity,
            "peak_R": peak,
            "drawdown_R": dd,
            "exit_reason": row.get("exit_reason", ""),
            "macro_bucket": row.get("macro_bucket") or row.get("macro_regime") or "",
        })
    return max_dd, out


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
    max_dd, _ = max_drawdown_path(values, [{} for _ in values])
    return {
        "trade_count": len(values),
        "pf": profit_factor(values),
        "avg_R": sum(values) / len(values),
        "net_R": sum(values),
        "win_rate": sum(1 for v in values if v > 0) / len(values),
        "max_dd_R": max_dd,
    }


def enrich(row: Dict[str, str]) -> Dict[str, Any]:
    r: Dict[str, Any] = dict(row)
    r["year"] = row.get("entry_utc", "")[:4]
    r["month"] = row.get("entry_utc", "")[:7]
    r["utc_hour"] = row.get("entry_utc", "")[11:13]
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


def group_metrics(rows: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    groups = defaultdict(list)
    for row in rows:
        groups[str(row.get(key, ""))].append(row)
    out = []
    total_positive_net = sum(max(0.0, sum(float(r["r"]) for r in g)) for g in groups.values())
    for value, group in sorted(groups.items()):
        vals = [float(r["r"]) for r in group]
        m = summarize(vals)
        m[key] = value
        positive_net = max(0.0, m["net_R"])
        m["positive_contribution_share"] = positive_net / total_positive_net if total_positive_net > 0 else 0.0
        out.append(m)
    return out


def streaks(values: List[float]) -> Dict[str, Any]:
    cur_win = cur_loss = max_win = max_loss = 0
    for v in values:
        if v > 0:
            cur_win += 1
            cur_loss = 0
        elif v < 0:
            cur_loss += 1
            cur_win = 0
        else:
            cur_win = cur_loss = 0
        max_win = max(max_win, cur_win)
        max_loss = max(max_loss, cur_loss)
    return {"max_win_streak": max_win, "max_loss_streak": max_loss}


def decision(summary: Dict[str, Any]) -> str:
    n = int(summary["trade_count"])
    pf = float(summary["pf"])
    avg_r = float(summary["avg_R"])
    pre_net = float(summary["pre2025_net_R"])
    max_month_share = float(summary["max_month_positive_contribution_share"])
    max_year_share = float(summary["max_year_positive_contribution_share"])

    if (
        n >= 75
        and pf >= 1.30
        and avg_r > 0
        and pre_net > 0
        and max_month_share <= 0.35
        and max_year_share <= 0.75
    ):
        return "LOCKED_CANDIDATE_PROSPECTIVE_MONITOR_ALLOWED"

    if (
        n >= 75
        and pf >= 1.20
        and avg_r > 0
        and pre_net > -2.0
    ):
        return "LOCKED_CANDIDATE_LOW_CONFIDENCE_2025_DOMINATED"

    return "LOCKED_CANDIDATE_ARCHIVE_OR_REDESIGN"


def markdown(summary: Dict[str, Any], yearly: List[Dict[str, Any]], monthly_top: List[Dict[str, Any]], exits: List[Dict[str, Any]]) -> str:
    lines = []
    lines.append("# Stage38A T1 Locked Candidate Final Diagnostics")
    lines.append("")
    lines.append("چپ‌چین ادامه می‌دهم.")
    lines.append("")
    lines.append("## Executive Decision")
    lines.append("")
    lines.append("```text")
    for key in [
        "lead_variant",
        "trade_count",
        "pf",
        "net_R",
        "avg_R",
        "win_rate",
        "max_dd_R",
        "pre2025_net_R",
        "y2025_net_R",
        "max_year_positive_contribution_share",
        "max_month_positive_contribution_share",
        "candidate_decision",
        "stage39_status",
    ]:
        lines.append(f"{key} = {summary.get(key)}")
    lines.append("```")
    lines.append("")
    lines.append("## Yearly Metrics")
    lines.append("")
    lines.append("| year | trades | pf | avg_R | net_R | contribution_share |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for row in yearly:
        lines.append(
            f"| {row.get('year')} | {row.get('trade_count')} | {clean(row.get('pf'))} | "
            f"{clean(row.get('avg_R'))} | {clean(row.get('net_R'))} | "
            f"{clean(row.get('positive_contribution_share'))} |"
        )
    lines.append("")
    lines.append("## Top Monthly Contributions")
    lines.append("")
    lines.append("| month | trades | pf | avg_R | net_R | contribution_share |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for row in monthly_top:
        lines.append(
            f"| {row.get('month')} | {row.get('trade_count')} | {clean(row.get('pf'))} | "
            f"{clean(row.get('avg_R'))} | {clean(row.get('net_R'))} | "
            f"{clean(row.get('positive_contribution_share'))} |"
        )
    lines.append("")
    lines.append("## Exit Reasons")
    lines.append("")
    lines.append("| exit_reason | trades | pf | avg_R | net_R |")
    lines.append("|---|---:|---:|---:|---:|")
    for row in exits:
        lines.append(
            f"| {row.get('exit_reason')} | {row.get('trade_count')} | {clean(row.get('pf'))} | "
            f"{clean(row.get('avg_R'))} | {clean(row.get('net_R'))} |"
        )
    lines.append("")
    lines.append("## Required Warning")
    lines.append("")
    lines.append("```text")
    lines.append("This is final locked-candidate diagnostics only.")
    lines.append("It does not authorize Stage39, EA, paper-live, live execution, or orders.")
    lines.append("```")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage38A T1 locked candidate final diagnostics")
    parser.add_argument("--ledger", default=DEFAULT_LEDGER)
    parser.add_argument("--out", default=DEFAULT_OUT_DIR)
    parser.add_argument("--variant", default=LEAD_VARIANT)
    args = parser.parse_args()

    ledger_path = Path(args.ledger)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not ledger_path.exists():
        raise FileNotFoundError(f"Missing ledger: {ledger_path}")

    rows = [enrich(r) for r in read_csv(ledger_path)]
    selected = [
        r for r in rows
        if r.get("variant_id") == args.variant and r.get("locked_structural_filter")
    ]
    selected.sort(key=lambda r: r.get("entry_utc", ""))

    if not selected:
        raise RuntimeError(f"No selected locked-filter trades for variant: {args.variant}")

    values = [float(r["r"]) for r in selected]
    base = summarize(values)
    max_dd, dd_rows = max_drawdown_path(values, selected)
    base["max_dd_R"] = max_dd

    yearly = group_metrics(selected, "year")
    monthly = group_metrics(selected, "month")
    hourly = group_metrics(selected, "utc_hour")
    exits = group_metrics(selected, "exit_reason")
    macro = group_metrics([
        {**r, "macro_group": r.get("macro_bucket") or r.get("macro_regime") or ""}
        for r in selected
    ], "macro_group")

    pre2025 = [r for r in selected if r.get("year") in ("2022", "2023", "2024")]
    y2025 = [r for r in selected if r.get("year") == "2025"]
    pre_metrics = summarize([float(r["r"]) for r in pre2025])
    y2025_metrics = summarize([float(r["r"]) for r in y2025])

    max_year_share = max([float(r.get("positive_contribution_share") or 0.0) for r in yearly] or [0.0])
    max_month_share = max([float(r.get("positive_contribution_share") or 0.0) for r in monthly] or [0.0])
    st = streaks(values)

    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "input_ledger": str(ledger_path),
        "output_dir": str(out_dir),
        "lead_variant": args.variant,
        "thresholds": {
            "D1_TREND_PCT_MIN": D1_TREND_PCT_MIN,
            "H4_TREND_PCT_MIN": H4_TREND_PCT_MIN,
            "ATR_PCT_PRICE_MIN": ATR_PCT_PRICE_MIN,
        },
        "trade_count": base["trade_count"],
        "pf": base["pf"],
        "avg_R": base["avg_R"],
        "net_R": base["net_R"],
        "win_rate": base["win_rate"],
        "max_dd_R": base["max_dd_R"],
        "max_win_streak": st["max_win_streak"],
        "max_loss_streak": st["max_loss_streak"],
        "pre2025_trade_count": pre_metrics["trade_count"],
        "pre2025_pf": pre_metrics["pf"],
        "pre2025_net_R": pre_metrics["net_R"],
        "y2025_trade_count": y2025_metrics["trade_count"],
        "y2025_pf": y2025_metrics["pf"],
        "y2025_net_R": y2025_metrics["net_R"],
        "max_year_positive_contribution_share": max_year_share,
        "max_month_positive_contribution_share": max_month_share,
        "stage39_status": "NO_GO",
        "execution_authorization": "NO_EA_NO_PAPER_NO_LIVE_NO_ORDER",
    }
    summary["candidate_decision"] = decision(summary)

    write_json(out_dir / "stage38a_t1_locked_candidate_final_summary.json", summary)
    write_csv(out_dir / "stage38a_t1_locked_candidate_yearly.csv", yearly)
    write_csv(out_dir / "stage38a_t1_locked_candidate_monthly.csv", monthly)
    write_csv(out_dir / "stage38a_t1_locked_candidate_hourly.csv", hourly)
    write_csv(out_dir / "stage38a_t1_locked_candidate_exit_reasons.csv", exits)
    write_csv(out_dir / "stage38a_t1_locked_candidate_macro.csv", macro)
    write_csv(out_dir / "stage38a_t1_locked_candidate_drawdown.csv", dd_rows)
    write_csv(out_dir / "stage38a_t1_locked_candidate_selected_trades.csv", selected)

    monthly_top = sorted(monthly, key=lambda r: float(r.get("positive_contribution_share") or 0.0), reverse=True)[:12]
    md = markdown(summary, yearly, monthly_top, exits)
    (out_dir / "stage38a_t1_locked_candidate_final_diagnostics.md").write_text(md, encoding="utf-8")

    print("STAGE38A_T1_LOCKED_CANDIDATE_FINAL_DIAGNOSTICS_DONE")
    print(f"LEAD_VARIANT={args.variant}")
    print(f"CANDIDATE_DECISION={summary['candidate_decision']}")
    print(f"REPORT_DIR={out_dir}")
    print("STAGE39=NO_GO")
    print("EA_PAPER_LIVE_ORDER=NO_GO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
