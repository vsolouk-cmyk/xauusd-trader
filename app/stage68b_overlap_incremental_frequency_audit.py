#!/usr/bin/env python3
"""
Stage68B Active-Day Overlap and Incremental Frequency Audit.

No order, broker, EA, paper-live, live, or threshold tuning is authorized.
This diagnostic reads the Stage64/67 macro dataset and evaluates the locked
H64L/D3/D1/D4 macro-regime rules to quantify overlap and incremental coverage.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

STAGE = "Stage68B_OVERLAP_INCREMENTAL_FREQUENCY_AUDIT"

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE68B",
    "NO_THRESHOLD_TUNING_FROM_OVERLAP_AUDIT",
    "NO_PROMOTION_FROM_OVERLAP_AUDIT_ONLY",
]

DEFAULT_RULES = [
    {
        "rule_key": "h64l_v2",
        "label": "H64L v2",
        "type": "primary",
        "horizon_trading_days": 120,
        "conditions": [
            ["gold_sma20_over_50", ">", 0.0],
            ["dxy_ret_20d", "<", 0.0],
            ["real_yield_change_20d", "<", 0.0],
            ["etf_flow_tonnes_3m", ">", 0.0],
            ["central_bank_demand_tonnes_3m", ">", 0.0],
            ["gold_sma50_over_200", ">", 0.0],
        ],
    },
    {
        "rule_key": "d3_h60",
        "label": "D3 Dollar Relief Trend Continuation H60",
        "type": "complementary_primary",
        "horizon_trading_days": 60,
        "conditions": [
            ["gold_sma20_over_50", ">", 0.0],
            ["dxy_sma20_over_50", "<", 0.0],
            ["dxy_ret_20d", "<", 0.0],
        ],
    },
    {
        "rule_key": "d1_backup",
        "label": "D1 DXY Real Yield Gold Trend H60",
        "type": "backup",
        "horizon_trading_days": 60,
        "conditions": [
            ["gold_sma20_over_50", ">", 0.0],
            ["dxy_ret_20d", "<", 0.0],
            ["real_yield_change_20d", "<", 0.0],
        ],
    },
    {
        "rule_key": "d4_backup",
        "label": "D4 Vol Risk-Off Real Yield Gold Long H60",
        "type": "backup",
        "horizon_trading_days": 60,
        "conditions": [
            ["gold_sma20_over_50", ">", 0.0],
            ["vix_change_20d", ">", 0.0],
            ["real_yield_change_20d", "<", 0.0],
        ],
    },
]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def parse_date(value: str) -> Optional[dt.date]:
    s = (value or "").strip()
    if not s:
        return None
    if "T" in s:
        s = s.split("T", 1)[0]
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if s == "" or s.lower() in {"none", "nan", "null"}:
        return None
    s = s.replace(",", "")
    try:
        x = float(s)
    except ValueError:
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def compare(value: float, op: str, threshold: float) -> bool:
    if op == ">":
        return value > threshold
    if op == "<":
        return value < threshold
    if op == ">=":
        return value >= threshold
    if op == "<=":
        return value <= threshold
    if op == "==":
        return value == threshold
    raise ValueError(f"Unsupported operator: {op}")


def condition_eval(row: Dict[str, str], condition: List[Any]) -> Tuple[Optional[bool], Optional[float]]:
    col, op, threshold = condition
    value = parse_float(row.get(col))
    if value is None:
        return None, None
    return compare(value, op, float(threshold)), value


def active_for_rule(row: Dict[str, str], rule: Dict[str, Any]) -> Tuple[bool, bool]:
    """Return (evaluable, active). Missing required values make row non-evaluable."""
    for cond in rule["conditions"]:
        passed, _value = condition_eval(row, cond)
        if passed is None:
            return False, False
        if not passed:
            return True, False
    return True, True


def load_macro(path: Path, date_col_hint: Optional[str]) -> Tuple[List[Dict[str, str]], str, List[str]]:
    if not path.exists():
        raise FileNotFoundError(f"macro dataset not found: {path}")
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        cols = reader.fieldnames or []
    if not rows:
        raise ValueError("macro dataset is empty")
    if date_col_hint and date_col_hint in cols:
        date_col = date_col_hint
    elif "feature_date_utc" in cols:
        date_col = "feature_date_utc"
    elif "date_utc" in cols:
        date_col = "date_utc"
    else:
        raise ValueError("no supported date column found; expected feature_date_utc or date_utc")
    return rows, date_col, cols


def episode_starts(dates: List[dt.date], active_flags: List[bool]) -> List[dt.date]:
    starts = []
    prev_active = False
    for d, active in zip(dates, active_flags):
        if active and not prev_active:
            starts.append(d)
        prev_active = active
    return starts


def cooldown_entries(starts: List[dt.date], horizon_trading_days: int) -> List[dt.date]:
    # Conservative calendar approximation for cooldown: trading horizon * 7/5.
    cooldown_days = max(1, int(round(horizon_trading_days * 7 / 5)))
    out: List[dt.date] = []
    last: Optional[dt.date] = None
    for d in starts:
        if last is None or (d - last).days >= cooldown_days:
            out.append(d)
            last = d
    return out


def cluster_entries(entries: List[Dict[str, Any]], window_days: int) -> List[Dict[str, Any]]:
    sorted_entries = sorted(entries, key=lambda x: (x["entry_date"], x["rule_key"]))
    clusters: List[Dict[str, Any]] = []
    for ent in sorted_entries:
        d = ent["entry_date"]
        if not clusters or (d - clusters[-1]["cluster_start"]).days > window_days:
            clusters.append({
                "cluster_id": len(clusters) + 1,
                "cluster_start": d,
                "cluster_end": d,
                "rule_keys": {ent["rule_key"]},
                "entries": [ent],
            })
        else:
            clusters[-1]["cluster_end"] = max(clusters[-1]["cluster_end"], d)
            clusters[-1]["rule_keys"].add(ent["rule_key"])
            clusters[-1]["entries"].append(ent)
    final = []
    for c in clusters:
        final.append({
            "cluster_id": c["cluster_id"],
            "cluster_start": c["cluster_start"].isoformat(),
            "cluster_end": c["cluster_end"].isoformat(),
            "calendar_span_days": (c["cluster_end"] - c["cluster_start"]).days + 1,
            "rule_count": len(c["rule_keys"]),
            "rules": ";".join(sorted(c["rule_keys"])),
            "entry_count": len(c["entries"]),
        })
    return final


def pct(num: int, denom: int) -> float:
    return round(100.0 * num / denom, 4) if denom else 0.0


def audit(root: Path, config: Dict[str, Any], out_dir: Path) -> Dict[str, Any]:
    macro_path = root / config.get("macro_path", "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv")
    rows, date_col, cols = load_macro(macro_path, config.get("date_col"))
    dated_rows = []
    for r in rows:
        d = parse_date(r.get(date_col, ""))
        if d is not None:
            dated_rows.append((d, r))
    dated_rows.sort(key=lambda x: x[0])
    if not dated_rows:
        raise ValueError("no rows with parseable macro dates")
    dates = [x[0] for x in dated_rows]
    rules = config.get("rules") or DEFAULT_RULES
    rule_keys = [r["rule_key"] for r in rules]

    active_by_rule: Dict[str, List[bool]] = {}
    eval_by_rule: Dict[str, List[bool]] = {}
    rule_metrics: Dict[str, Dict[str, Any]] = {}
    all_entries: List[Dict[str, Any]] = []

    for rule in rules:
        key = rule["rule_key"]
        active_flags = []
        eval_flags = []
        for _d, row in dated_rows:
            evaluable, active = active_for_rule(row, rule)
            eval_flags.append(evaluable)
            active_flags.append(active)
        eval_by_rule[key] = eval_flags
        active_by_rule[key] = active_flags

        starts = episode_starts(dates, active_flags)
        entries = cooldown_entries(starts, int(rule.get("horizon_trading_days", 60)))
        for e in entries:
            all_entries.append({"rule_key": key, "label": rule.get("label", key), "entry_date": e})
        active_days = sum(active_flags)
        evaluable_rows = sum(eval_flags)
        rule_metrics[key] = {
            "label": rule.get("label", key),
            "type": rule.get("type"),
            "horizon_trading_days": rule.get("horizon_trading_days"),
            "evaluable_rows": evaluable_rows,
            "active_days": active_days,
            "active_pct_of_evaluable": pct(active_days, evaluable_rows),
            "episode_count": len(starts),
            "cooldown_entry_count": len(entries),
            "first_active_date": next((d.isoformat() for d, a in zip(dates, active_flags) if a), None),
            "last_active_date": next((d.isoformat() for d, a in reversed(list(zip(dates, active_flags))) if a), None),
        }

    n = len(dates)
    any_all = [any(active_by_rule[k][i] for k in rule_keys) for i in range(n)]
    any_primary = [any(active_by_rule[k][i] for k in rule_keys if k in {"h64l_v2", "d3_h60"}) for i in range(n)]
    combined = {
        "any_all_rules": {
            "active_days": sum(any_all),
            "active_pct_of_rows": pct(sum(any_all), n),
        },
        "any_primary_h64l_or_d3": {
            "active_days": sum(any_primary),
            "active_pct_of_rows": pct(sum(any_primary), n),
        },
    }

    # Pairwise active-day overlap.
    pairwise_rows = []
    for i, a in enumerate(rule_keys):
        for b in rule_keys[i+1:]:
            A = active_by_rule[a]
            B = active_by_rule[b]
            a_days = sum(A)
            b_days = sum(B)
            inter = sum(aa and bb for aa, bb in zip(A, B))
            union = sum(aa or bb for aa, bb in zip(A, B))
            pairwise_rows.append({
                "rule_a": a,
                "rule_b": b,
                "a_active_days": a_days,
                "b_active_days": b_days,
                "intersection_days": inter,
                "union_days": union,
                "jaccard_overlap_pct": pct(inter, union),
                "a_contained_in_b_pct": pct(inter, a_days),
                "b_contained_in_a_pct": pct(inter, b_days),
            })

    # Incremental active-day contribution.
    contribution_rows = []
    for k in rule_keys:
        active = active_by_rule[k]
        others = [ok for ok in rule_keys if ok != k]
        unique_days = 0
        overlap_days = 0
        for idx, flag in enumerate(active):
            if not flag:
                continue
            if any(active_by_rule[ok][idx] for ok in others):
                overlap_days += 1
            else:
                unique_days += 1
        total_active = sum(active)
        contribution_rows.append({
            "rule_key": k,
            "active_days": total_active,
            "unique_active_days_vs_other_rules": unique_days,
            "overlapped_active_days_vs_other_rules": overlap_days,
            "unique_share_of_rule_active_pct": pct(unique_days, total_active),
            "unique_share_of_any_all_active_pct": pct(unique_days, sum(any_all)),
        })

    window_days = int(config.get("entry_cluster_window_calendar_days", 60))
    clusters = cluster_entries(all_entries, window_days)
    raw_entry_count = len(all_entries)
    cluster_count = len(clusters)
    entry_cluster_compression_pct = round(100.0 * (1 - cluster_count / raw_entry_count), 4) if raw_entry_count else 0.0

    # Simple posture.
    max_pairwise_jaccard = max((r["jaccard_overlap_pct"] for r in pairwise_rows), default=0.0)
    total_unique = sum(r["unique_active_days_vs_other_rules"] for r in contribution_rows)
    unique_any_pct = pct(total_unique, sum(any_all))
    if max_pairwise_jaccard >= 50 or entry_cluster_compression_pct >= 35:
        overlap_posture = "MATERIAL_CLUSTERING_REQUIRES_INCREMENTAL_VALUE_AUDIT"
    elif max_pairwise_jaccard >= 25 or entry_cluster_compression_pct >= 20:
        overlap_posture = "MODERATE_CLUSTERING_REVIEW_PRIORITY"
    else:
        overlap_posture = "LOW_CLUSTERING_FREQUENCY_DIVERSIFIED"

    out_dir.mkdir(parents=True, exist_ok=True)
    pairwise_csv = out_dir / "stage68b_pairwise_active_day_overlap.csv"
    contribution_csv = out_dir / "stage68b_incremental_day_contribution.csv"
    cluster_csv = out_dir / "stage68b_entry_clusters.csv"
    entries_csv = out_dir / "stage68b_rule_entries.csv"

    def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            for r in rows:
                w.writerow(r)

    entries_rows = [{"rule_key": e["rule_key"], "label": e["label"], "entry_date": e["entry_date"].isoformat()} for e in sorted(all_entries, key=lambda x: (x["entry_date"], x["rule_key"]))]
    write_csv(pairwise_csv, pairwise_rows)
    write_csv(contribution_csv, contribution_rows)
    write_csv(cluster_csv, clusters)
    write_csv(entries_csv, entries_rows)

    summary = {
        "stage": STAGE,
        "root": str(root),
        "config": str(config.get("_config_path", "")),
        "generated_utc": utc_now(),
        "status": "STAGE68B_COMPLETE_NO_PROMOTION",
        "decision": "STAGE68B_OVERLAP_INCREMENTAL_AUDIT_COMPLETE_NO_ORDER",
        "classification": "S68B_OVERLAP_AUDIT_COMPLETE",
        "overlap_posture": overlap_posture,
        "macro_dataset": {
            "path": str(macro_path),
            "rows": len(rows),
            "dated_rows": len(dated_rows),
            "date_col": date_col,
            "min_date": dates[0].isoformat(),
            "max_date": dates[-1].isoformat(),
            "sha256": sha256_file(macro_path),
        },
        "rule_metrics": rule_metrics,
        "combined_metrics": combined,
        "overlap_metrics": {
            "max_pairwise_jaccard_overlap_pct": max_pairwise_jaccard,
            "raw_rule_entry_count": raw_entry_count,
            "entry_cluster_window_calendar_days": window_days,
            "entry_cluster_count": cluster_count,
            "entry_cluster_compression_pct": entry_cluster_compression_pct,
            "sum_unique_active_days_across_rules": total_unique,
            "sum_unique_active_days_as_pct_of_any_all_active": unique_any_pct,
        },
        "pairwise_active_day_overlap": pairwise_rows,
        "incremental_day_contribution": contribution_rows,
        "hard_blocks": HARD_BLOCKS,
        "operator_instructions": [
            "Stage68B is diagnostic only and cannot authorize orders.",
            "Do not tune thresholds from this audit alone.",
            "If overlap is material, use a separate return/incremental-value audit before adding readiness paths.",
            "Broker, EA, paper-live, and live paths remain blocked.",
        ],
        "outputs": {
            "summary_json": str(out_dir / "stage68b_overlap_incremental_frequency_audit_summary.json"),
            "report_md": str(out_dir / "stage68b_overlap_incremental_frequency_audit_report.md"),
            "pairwise_csv": str(pairwise_csv),
            "contribution_csv": str(contribution_csv),
            "clusters_csv": str(cluster_csv),
            "entries_csv": str(entries_csv),
        },
    }

    report = render_report(summary)
    summary_path = out_dir / "stage68b_overlap_incremental_frequency_audit_summary.json"
    report_path = out_dir / "stage68b_overlap_incremental_frequency_audit_report.md"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=False), encoding="utf-8")
    report_path.write_text(report, encoding="utf-8")
    return summary


def render_report(summary: Dict[str, Any]) -> str:
    lines = [
        "# Stage68B Overlap / Incremental Frequency Audit",
        "",
        "## Decision",
        "",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- classification: `{summary['classification']}`",
        f"- overlap_posture: `{summary['overlap_posture']}`",
        "",
        "## Macro dataset",
        "",
        f"- rows: `{summary['macro_dataset']['rows']}`",
        f"- min_date: `{summary['macro_dataset']['min_date']}`",
        f"- max_date: `{summary['macro_dataset']['max_date']}`",
        "",
        "## Combined metrics",
        "",
    ]
    for key, val in summary["combined_metrics"].items():
        lines.append(f"- `{key}`: active_days=`{val['active_days']}`, active_pct=`{val['active_pct_of_rows']}`")
    lines += [
        "",
        "## Overlap metrics",
        "",
        f"- max_pairwise_jaccard_overlap_pct: `{summary['overlap_metrics']['max_pairwise_jaccard_overlap_pct']}`",
        f"- raw_rule_entry_count: `{summary['overlap_metrics']['raw_rule_entry_count']}`",
        f"- entry_cluster_count: `{summary['overlap_metrics']['entry_cluster_count']}`",
        f"- entry_cluster_compression_pct: `{summary['overlap_metrics']['entry_cluster_compression_pct']}`",
        f"- sum_unique_active_days_as_pct_of_any_all_active: `{summary['overlap_metrics']['sum_unique_active_days_as_pct_of_any_all_active']}`",
        "",
        "## Incremental day contribution",
        "",
    ]
    for row in summary["incremental_day_contribution"]:
        lines.append(
            f"- `{row['rule_key']}`: active_days=`{row['active_days']}`, "
            f"unique_days=`{row['unique_active_days_vs_other_rules']}`, "
            f"unique_share_of_rule_active_pct=`{row['unique_share_of_rule_active_pct']}`"
        )
    lines += [
        "",
        "## Pairwise active-day overlap",
        "",
    ]
    for row in summary["pairwise_active_day_overlap"]:
        lines.append(
            f"- `{row['rule_a']}` vs `{row['rule_b']}`: "
            f"intersection_days=`{row['intersection_days']}`, "
            f"jaccard=`{row['jaccard_overlap_pct']}`, "
            f"a_in_b=`{row['a_contained_in_b_pct']}`, "
            f"b_in_a=`{row['b_contained_in_a_pct']}`"
        )
    lines += [
        "",
        "## Hard blocks",
        "",
    ]
    for b in HARD_BLOCKS:
        lines.append(f"- `{b}`")
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--config", default="configs/stage68b_overlap_incremental_frequency_audit.json")
    p.add_argument("--out", default="reports/stage68b_overlap_incremental_frequency_audit")
    args = p.parse_args()

    root = Path(args.root).resolve()
    config_path = (root / args.config).resolve() if not os.path.isabs(args.config) else Path(args.config)
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
    else:
        config = {}
    config["_config_path"] = str(config_path)
    summary = audit(root, config, (root / args.out).resolve() if not os.path.isabs(args.out) else Path(args.out))
    print(json.dumps({
        "stage": STAGE,
        "status": summary["status"],
        "decision": summary["decision"],
        "classification": summary["classification"],
        "overlap_posture": summary["overlap_posture"],
        "summary_json": summary["outputs"]["summary_json"],
        "report_md": summary["outputs"]["report_md"],
    }, indent=2))


if __name__ == "__main__":
    main()
