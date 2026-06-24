#!/usr/bin/env python3
"""
Stage38A T1 2025 Regime Diagnostic

Diagnoses why the best T1 variant works in 2025 but fails before 2025.

This script:
- reads only the existing Stage38A T1 trade ledger,
- creates no new strategy variants,
- does not optimize thresholds,
- writes diagnostics only.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


DEFAULT_LEDGER = "data/reports/stage38a_t1_read_only_test/stage38a_t1_trade_ledger.csv"
DEFAULT_OUT_DIR = "data/reports/stage38a_t1_2025_regime_diagnostic"
BEST_VARIANT = "V3_STRICT_NEXT_BAR_HOLD__rolling_48h_high__TP_1R__TIME_5H"


FEATURES = [
    "macro_score_long_gold",
    "d_real_yield_20d",
    "d_usd_20d_pct",
    "atr_h1_14",
    "signal_range_atr_ratio",
    "stop_distance_atr_ratio",
    "d1_trend_distance",
    "h4_trend_distance",
]


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
        for r in rows:
            writer.writerow({k: clean(r.get(k, "")) for k in fieldnames})


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def profit_factor(vals: List[float]) -> float:
    wins = sum(v for v in vals if v > 0)
    losses = -sum(v for v in vals if v < 0)
    if losses == 0:
        return float("inf") if wins > 0 else 0.0
    return wins / losses


def summarize_r(vals: List[float]) -> Dict[str, Any]:
    if not vals:
        return {"n": 0, "pf": 0.0, "avg_R": 0.0, "net_R": 0.0, "win_rate": 0.0}
    return {
        "n": len(vals),
        "pf": profit_factor(vals),
        "avg_R": sum(vals) / len(vals),
        "net_R": sum(vals),
        "win_rate": sum(1 for v in vals if v > 0) / len(vals),
    }


def percentile(vals: List[float], p: float) -> Optional[float]:
    vals = sorted(v for v in vals if v is not None)
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


def feature_values(rows: List[Dict[str, Any]], feature: str) -> List[float]:
    vals = []
    for r in rows:
        v = safe_float(r.get(feature))
        if v is not None:
            vals.append(v)
    return vals


def summarize_feature(rows: List[Dict[str, Any]], feature: str) -> Dict[str, Any]:
    vals = feature_values(rows, feature)
    return {
        "feature": feature,
        "n": len(vals),
        "mean": sum(vals) / len(vals) if vals else None,
        "p10": percentile(vals, 0.10),
        "p25": percentile(vals, 0.25),
        "p50": percentile(vals, 0.50),
        "p75": percentile(vals, 0.75),
        "p90": percentile(vals, 0.90),
        "min": min(vals) if vals else None,
        "max": max(vals) if vals else None,
    }


def enrich(rows: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    out = []
    for r in rows:
        rr: Dict[str, Any] = dict(r)
        rr["year"] = r.get("entry_utc", "")[:4]
        rr["month"] = r.get("entry_utc", "")[:7]
        rr["utc_hour"] = r.get("entry_utc", "")[11:13]
        rr["r"] = safe_float(r.get("r_stress_p90"), 0.0)

        d1_close = safe_float(r.get("d1_close"))
        d1_ma50 = safe_float(r.get("d1_ma50"))
        h4_close = safe_float(r.get("h4_close"))
        h4_ma50 = safe_float(r.get("h4_ma50"))
        atr = safe_float(r.get("atr_h1_14"))

        rr["d1_trend_distance"] = (d1_close - d1_ma50) if d1_close is not None and d1_ma50 is not None else None
        rr["h4_trend_distance"] = (h4_close - h4_ma50) if h4_close is not None and h4_ma50 is not None else None
        rr["d1_trend_distance_atr"] = ((d1_close - d1_ma50) / atr) if d1_close is not None and d1_ma50 is not None and atr and atr > 0 else None
        rr["h4_trend_distance_atr"] = ((h4_close - h4_ma50) / atr) if h4_close is not None and h4_ma50 is not None and atr and atr > 0 else None

        out.append(rr)
    return out


def group_summary(rows: List[Dict[str, Any]], keys: List[str]) -> List[Dict[str, Any]]:
    groups = defaultdict(list)
    for r in rows:
        k = tuple(str(r.get(key, "")) for key in keys)
        groups[k].append(r)
    out = []
    for k, group in sorted(groups.items()):
        vals = [float(g.get("r", 0.0)) for g in group]
        s = summarize_r(vals)
        for key, value in zip(keys, k):
            s[key] = value
        out.append(s)
    return out


def feature_summary_by_group(rows: List[Dict[str, Any]], group_name: str, group_func) -> List[Dict[str, Any]]:
    groups = defaultdict(list)
    for r in rows:
        groups[group_func(r)].append(r)
    out = []
    for group, g_rows in sorted(groups.items()):
        for feature in FEATURES:
            s = summarize_feature(g_rows, feature)
            vals_r = [float(r.get("r", 0.0)) for r in g_rows]
            perf = summarize_r(vals_r)
            s[group_name] = group
            s["trade_count"] = perf["n"]
            s["pf"] = perf["pf"]
            s["avg_R"] = perf["avg_R"]
            s["net_R"] = perf["net_R"]
            s["win_rate"] = perf["win_rate"]
            out.append(s)
    return out


def separation_table(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows_2025 = [r for r in rows if r["year"] == "2025"]
    rows_pre = [r for r in rows if r["year"] in ("2022", "2023", "2024")]
    out = []
    for feature in FEATURES + ["d1_trend_distance_atr", "h4_trend_distance_atr"]:
        s25 = summarize_feature(rows_2025, feature)
        spre = summarize_feature(rows_pre, feature)
        diff_mean = None
        if s25["mean"] is not None and spre["mean"] is not None:
            diff_mean = s25["mean"] - spre["mean"]
        out.append({
            "feature": feature,
            "pre2025_n": spre["n"],
            "pre2025_mean": spre["mean"],
            "pre2025_p50": spre["p50"],
            "pre2025_p75": spre["p75"],
            "y2025_n": s25["n"],
            "y2025_mean": s25["mean"],
            "y2025_p50": s25["p50"],
            "y2025_p25": s25["p25"],
            "mean_2025_minus_pre2025": diff_mean,
        })
    return out


def candidate_filter_notes(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Diagnostic notes only. These are not authorized trading filters.
    They point to possible pre-trade features to investigate.
    """
    sep = separation_table(rows)
    notes = []
    for r in sep:
        feature = r["feature"]
        diff = safe_float(r.get("mean_2025_minus_pre2025"), 0.0)
        pre = safe_float(r.get("pre2025_mean"), 0.0)
        y25 = safe_float(r.get("y2025_mean"), 0.0)
        note = "no_clear_separation"
        if diff is not None:
            scale = abs(pre) + 1e-9
            if abs(diff) > 0.5 * max(1.0, scale):
                note = "possible_2025_separation_feature"
        notes.append({
            "feature": feature,
            "pre2025_mean": pre,
            "y2025_mean": y25,
            "difference": diff,
            "diagnostic_note": note,
            "authorized_filter": "NO",
        })
    return notes


def markdown(summary: Dict[str, Any], sep_rows: List[Dict[str, Any]], candidate_notes: List[Dict[str, Any]], year_perf: List[Dict[str, Any]]) -> str:
    lines = []
    lines.append("# Stage38A T1 2025 Regime Diagnostic")
    lines.append("")
    lines.append("چپ‌چین ادامه می‌دهم.")
    lines.append("")
    lines.append("## Executive Decision")
    lines.append("")
    lines.append("```text")
    for k in [
        "best_variant",
        "trade_count",
        "pre2025_trade_count",
        "y2025_trade_count",
        "pre2025_net_R",
        "y2025_net_R",
        "diagnostic_decision",
        "stage39_status",
    ]:
        lines.append(f"{k} = {summary.get(k)}")
    lines.append("```")
    lines.append("")
    lines.append("## Year Performance")
    lines.append("")
    lines.append("| year | trades | pf | avg_R | net_R | win_rate |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for r in year_perf:
        lines.append(f"| {r.get('year')} | {r.get('n')} | {clean(r.get('pf'))} | {clean(r.get('avg_R'))} | {clean(r.get('net_R'))} | {clean(r.get('win_rate'))} |")
    lines.append("")
    lines.append("## 2025 vs Pre-2025 Feature Separation")
    lines.append("")
    lines.append("| feature | pre2025_mean | y2025_mean | diff | note |")
    lines.append("|---|---:|---:|---:|---|")
    note_map = {r["feature"]: r for r in candidate_notes}
    for r in sep_rows:
        note = note_map.get(r["feature"], {}).get("diagnostic_note", "")
        lines.append(f"| {r.get('feature')} | {clean(r.get('pre2025_mean'))} | {clean(r.get('y2025_mean'))} | {clean(r.get('mean_2025_minus_pre2025'))} | {note} |")
    lines.append("")
    lines.append("## Required Warning")
    lines.append("")
    lines.append("```text")
    lines.append("This diagnostic suggests possible features only.")
    lines.append("It does not authorize new filters, Stage39, EA, paper-live, live execution, or orders.")
    lines.append("```")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage38A T1 2025 regime diagnostic")
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
        raise RuntimeError(f"No rows for best variant: {args.best_variant}")

    pre2025 = [r for r in rows if r["year"] in ("2022", "2023", "2024")]
    y2025 = [r for r in rows if r["year"] == "2025"]

    pre_perf = summarize_r([float(r.get("r", 0.0)) for r in pre2025])
    y25_perf = summarize_r([float(r.get("r", 0.0)) for r in y2025])

    year_perf = group_summary(rows, ["year"])
    year_macro = group_summary(rows, ["year", "macro_bucket"])
    hour_exit = group_summary(rows, ["year", "utc_hour", "exit_reason"])
    feature_summary = feature_summary_by_group(rows, "year", lambda r: r["year"])
    win_loss_features = feature_summary_by_group(rows, "outcome", lambda r: "win" if float(r.get("r", 0.0)) > 0 else "loss")
    sep_rows = separation_table(rows)
    notes = candidate_filter_notes(rows)

    diagnostic_decision = "NO_2025_EX_ANTE_FILTER_YET"
    if y25_perf["net_R"] > 0 and pre_perf["net_R"] < 0:
        diagnostic_decision = "2025_FEATURE_SEPARATION_REQUIRED"

    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "input_ledger": str(ledger_path),
        "output_dir": str(out_dir),
        "best_variant": args.best_variant,
        "trade_count": len(rows),
        "pre2025_trade_count": len(pre2025),
        "y2025_trade_count": len(y2025),
        "pre2025_pf": pre_perf["pf"],
        "pre2025_avg_R": pre_perf["avg_R"],
        "pre2025_net_R": pre_perf["net_R"],
        "y2025_pf": y25_perf["pf"],
        "y2025_avg_R": y25_perf["avg_R"],
        "y2025_net_R": y25_perf["net_R"],
        "diagnostic_decision": diagnostic_decision,
        "stage39_status": "NO_GO",
        "execution_authorization": "NO_EA_NO_PAPER_NO_LIVE_NO_ORDER",
    }

    write_json(out_dir / "stage38a_t1_2025_regime_diagnostic_summary.json", summary)
    write_csv(out_dir / "stage38a_t1_2025_feature_summary.csv", sep_rows)
    write_csv(out_dir / "stage38a_t1_2025_year_feature_summary.csv", feature_summary)
    write_csv(out_dir / "stage38a_t1_2025_win_loss_features.csv", win_loss_features)
    write_csv(out_dir / "stage38a_t1_2025_hour_exit_summary.csv", hour_exit)
    write_csv(out_dir / "stage38a_t1_2025_candidate_filter_notes.csv", notes)
    write_csv(out_dir / "stage38a_t1_2025_year_macro_summary.csv", year_macro)
    md = markdown(summary, sep_rows, notes, year_perf)
    (out_dir / "stage38a_t1_2025_regime_diagnostic.md").write_text(md, encoding="utf-8")

    print("STAGE38A_T1_2025_REGIME_DIAGNOSTIC_DONE")
    print(f"BEST_VARIANT={args.best_variant}")
    print(f"DIAGNOSTIC_DECISION={diagnostic_decision}")
    print(f"REPORT_DIR={out_dir}")
    print("STAGE39=NO_GO")
    print("EA_PAPER_LIVE_ORDER=NO_GO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
