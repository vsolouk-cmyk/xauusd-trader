#!/usr/bin/env python3
"""
Stage38A T1 Era Ablation Diagnostic

Reads existing Stage38A T1 trade ledger and evaluates whether the best T1
candidate is robust across eras or concentrated in one period.

This script:
- does not create new variants,
- does not run new strategy logic,
- does not touch broker/order/EA/paper/live components,
- writes only diagnostics under data/reports/stage38a_t1_era_ablation/.
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
DEFAULT_OUT_DIR = "data/reports/stage38a_t1_era_ablation"

BEST_VARIANT = "V3_STRICT_NEXT_BAR_HOLD__rolling_48h_high__TP_1R__TIME_5H"
COMPARE_VARIANTS = [
    "V3_STRICT_NEXT_BAR_HOLD__rolling_48h_high__TP_1R__TIME_5H",
    "V3_STRICT_NEXT_BAR_HOLD__rolling_48h_high__TP_1_5R__TIME_5H",
    "V3_STRICT_NEXT_BAR_HOLD__previous_day_high__TP_1R__TIME_5H",
    "V3_STRICT_NEXT_BAR_HOLD__previous_day_high__TP_1_5R__TIME_5H",
]


WINDOWS = [
    ("FULL", None, None),
    ("EXCLUDE_2025", "2022-01-01", "2024-12-31"),
    ("PRE_2025_2022_2024", "2022-01-01", "2024-12-31"),
    ("ERA_2022_2023", "2022-01-01", "2023-12-31"),
    ("ERA_2024_2025", "2024-01-01", "2025-12-31"),
    ("ERA_2025_ONLY", "2025-01-01", "2025-12-31"),
    ("ERA_2024_ONLY", "2024-01-01", "2024-12-31"),
]


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def clean_value(v: Any) -> Any:
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
        for r in rows:
            writer.writerow({k: clean_value(r.get(k, "")) for k in fieldnames})


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
        if equity > peak:
            peak = equity
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


def date_key(row: Dict[str, str]) -> str:
    return row.get("entry_utc", "")[:10]


def in_window(row: Dict[str, str], start: Optional[str], end: Optional[str]) -> bool:
    d = date_key(row)
    if not d:
        return False
    if start is not None and d < start:
        return False
    if end is not None and d > end:
        return False
    return True


def metrics_for_rows(rows: List[Dict[str, str]], value_col: str = "r_stress_p90") -> Dict[str, Any]:
    return summarize([safe_float(r.get(value_col)) for r in rows])


def group_by(rows: List[Dict[str, str]], key_func, group_name: str) -> List[Dict[str, Any]]:
    groups = defaultdict(list)
    for r in rows:
        groups[key_func(r)].append(r)
    out = []
    for k, group in sorted(groups.items()):
        m = metrics_for_rows(group)
        m[group_name] = k
        out.append(m)
    return out


def make_markdown(summary: Dict[str, Any], window_rows: List[Dict[str, Any]], year_macro_rows: List[Dict[str, Any]], variant_window_rows: List[Dict[str, Any]]) -> str:
    lines = []
    lines.append("# Stage38A T1 Era Ablation Diagnostic")
    lines.append("")
    lines.append("چپ‌چین ادامه می‌دهم.")
    lines.append("")
    lines.append("## Executive Decision")
    lines.append("")
    lines.append("```text")
    for k in [
        "best_variant",
        "full_pf",
        "full_net_R",
        "exclude_2025_pf",
        "exclude_2025_net_R",
        "era_2025_pf",
        "era_2025_net_R",
        "era_decision",
        "stage39_status",
    ]:
        lines.append(f"{k} = {summary.get(k)}")
    lines.append("```")
    lines.append("")
    lines.append("## Window Ablation")
    lines.append("")
    lines.append("| window | trades | pf | avg_R | net_R | win_rate | max_dd |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for r in window_rows:
        lines.append(f"| {r.get('window')} | {r.get('trade_count')} | {clean_value(r.get('pf'))} | {clean_value(r.get('avg_R'))} | {clean_value(r.get('net_R'))} | {clean_value(r.get('win_rate'))} | {clean_value(r.get('max_dd_R'))} |")
    lines.append("")
    lines.append("## Year × Macro Bucket")
    lines.append("")
    lines.append("| year | macro_bucket | trades | pf | avg_R | net_R |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for r in year_macro_rows:
        lines.append(f"| {r.get('year')} | {r.get('macro_bucket')} | {r.get('trade_count')} | {clean_value(r.get('pf'))} | {clean_value(r.get('avg_R'))} | {clean_value(r.get('net_R'))} |")
    lines.append("")
    lines.append("## Variant Window Comparison")
    lines.append("")
    lines.append("| variant | window | trades | pf | avg_R | net_R |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for r in variant_window_rows:
        lines.append(f"| {r.get('variant_id')} | {r.get('window')} | {r.get('trade_count')} | {clean_value(r.get('pf'))} | {clean_value(r.get('avg_R'))} | {clean_value(r.get('net_R'))} |")
    lines.append("")
    lines.append("## Required Warning")
    lines.append("")
    lines.append("```text")
    lines.append("This is era ablation only.")
    lines.append("It does not create new variants.")
    lines.append("It does not authorize Stage39, EA, paper-live, live execution, or orders.")
    lines.append("```")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage38A T1 era ablation")
    parser.add_argument("--ledger", default=DEFAULT_LEDGER)
    parser.add_argument("--out", default=DEFAULT_OUT_DIR)
    parser.add_argument("--best-variant", default=BEST_VARIANT)
    args = parser.parse_args()

    ledger_path = Path(args.ledger)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not ledger_path.exists():
        raise FileNotFoundError(f"Missing ledger: {ledger_path}")

    ledger = read_csv(ledger_path)
    best_rows = [r for r in ledger if r.get("variant_id") == args.best_variant]
    if not best_rows:
        raise RuntimeError(f"No rows for best variant: {args.best_variant}")

    best_rows.sort(key=lambda r: r.get("entry_utc", ""))

    window_rows = []
    for name, start, end in WINDOWS:
        group = [r for r in best_rows if in_window(r, start, end)]
        m = metrics_for_rows(group)
        m["window"] = name
        m["start"] = start or ""
        m["end"] = end or ""
        window_rows.append(m)

    # Year x macro bucket for best variant.
    year_macro_groups = defaultdict(list)
    for r in best_rows:
        year = r.get("entry_utc", "")[:4]
        bucket = r.get("macro_bucket") or r.get("macro_regime") or "unknown"
        year_macro_groups[(year, bucket)].append(r)
    year_macro_rows = []
    for (year, bucket), group in sorted(year_macro_groups.items()):
        m = metrics_for_rows(group)
        m["year"] = year
        m["macro_bucket"] = bucket
        year_macro_rows.append(m)

    # Year x hour for best variant.
    year_hour_groups = defaultdict(list)
    for r in best_rows:
        year = r.get("entry_utc", "")[:4]
        hour = r.get("entry_utc", "")[11:13]
        year_hour_groups[(year, hour)].append(r)
    year_hour_rows = []
    for (year, hour), group in sorted(year_hour_groups.items()):
        m = metrics_for_rows(group)
        m["year"] = year
        m["utc_hour"] = hour
        year_hour_rows.append(m)

    # Variant x windows for narrow variants.
    variant_window_rows = []
    for vid in COMPARE_VARIANTS:
        rows = [r for r in ledger if r.get("variant_id") == vid]
        for name, start, end in WINDOWS:
            group = [r for r in rows if in_window(r, start, end)]
            m = metrics_for_rows(group)
            m["variant_id"] = vid
            m["window"] = name
            variant_window_rows.append(m)

    full = next((r for r in window_rows if r["window"] == "FULL"), {})
    excl = next((r for r in window_rows if r["window"] == "EXCLUDE_2025"), {})
    era2025 = next((r for r in window_rows if r["window"] == "ERA_2025_ONLY"), {})
    era2024_2025 = next((r for r in window_rows if r["window"] == "ERA_2024_2025"), {})

    era_decision = "ERA_CONCENTRATED_NOT_ROBUST"
    if safe_float(excl.get("pf")) >= 1.05 and safe_float(excl.get("avg_R")) > 0:
        era_decision = "BROADER_THAN_2025_NEEDS_MORE_REVIEW"
    if safe_float(era2025.get("net_R")) > 0 and safe_float(excl.get("net_R")) <= 0:
        era_decision = "2025_DEPENDENT_EDGE"

    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "input_ledger": str(ledger_path),
        "output_dir": str(out_dir),
        "best_variant": args.best_variant,
        "full_pf": full.get("pf"),
        "full_net_R": full.get("net_R"),
        "exclude_2025_pf": excl.get("pf"),
        "exclude_2025_net_R": excl.get("net_R"),
        "era_2025_pf": era2025.get("pf"),
        "era_2025_net_R": era2025.get("net_R"),
        "era_2024_2025_pf": era2024_2025.get("pf"),
        "era_2024_2025_net_R": era2024_2025.get("net_R"),
        "era_decision": era_decision,
        "stage39_status": "NO_GO",
        "execution_authorization": "NO_EA_NO_PAPER_NO_LIVE_NO_ORDER",
    }

    write_json(out_dir / "stage38a_t1_era_ablation_summary.json", summary)
    write_csv(out_dir / "stage38a_t1_era_ablation_windows.csv", window_rows)
    write_csv(out_dir / "stage38a_t1_era_ablation_year_macro.csv", year_macro_rows)
    write_csv(out_dir / "stage38a_t1_era_ablation_year_hour.csv", year_hour_rows)
    write_csv(out_dir / "stage38a_t1_era_ablation_variant_windows.csv", variant_window_rows)

    md = make_markdown(summary, window_rows, year_macro_rows, variant_window_rows)
    (out_dir / "stage38a_t1_era_ablation.md").write_text(md, encoding="utf-8")

    print("STAGE38A_T1_ERA_ABLATION_DONE")
    print(f"BEST_VARIANT={args.best_variant}")
    print(f"ERA_DECISION={era_decision}")
    print(f"REPORT_DIR={out_dir}")
    print("STAGE39=NO_GO")
    print("EA_PAPER_LIVE_ORDER=NO_GO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
