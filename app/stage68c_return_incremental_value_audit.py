#!/usr/bin/env python3
"""Stage68C Return / Incremental Value Audit.

Diagnostic-only audit for XAUUSD macro-regime rules. It reads the rebuilt
Stage64/67 macro dataset, reconstructs registered rules, creates cooldown
entries, measures forward gross/net returns, and separates unique-vs-overlapped
entry value. It never connects to a broker and never authorizes orders.
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
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

STAGE = "Stage68C_RETURN_INCREMENTAL_VALUE_AUDIT"
HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE68C",
    "NO_THRESHOLD_TUNING_FROM_RETURN_AUDIT",
    "NO_PROMOTION_FROM_RETURN_AUDIT_ONLY",
]

DEFAULT_CONFIG = {
    "macro_dataset_path": "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
    "date_column_candidates": ["feature_date_utc", "date_utc"],
    "price_column_candidates": ["gold_close", "close"],
    "cost_bps_total": 50.0,
    "cluster_window_calendar_days": 60,
    "rules": [
        {
            "rule_key": "h64l_v2",
            "label": "H64L v2",
            "type": "primary",
            "horizon_trading_days": 120,
            "conditions": [
                {"column": "gold_sma20_over_50", "operator": ">", "threshold": 0.0},
                {"column": "dxy_ret_20d", "operator": "<", "threshold": 0.0},
                {"column": "real_yield_change_20d", "operator": "<", "threshold": 0.0},
                {"column": "etf_flow_tonnes_3m", "operator": ">", "threshold": 0.0},
                {"column": "central_bank_demand_tonnes_3m", "operator": ">", "threshold": 0.0},
                {"column": "gold_sma50_over_200", "operator": ">", "threshold": 0.0},
            ],
        },
        {
            "rule_key": "d3_h60",
            "label": "D3 Dollar Relief Trend Continuation H60",
            "type": "complementary_primary",
            "horizon_trading_days": 60,
            "conditions": [
                {"column": "gold_sma20_over_50", "operator": ">", "threshold": 0.0},
                {"column": "dxy_sma20_over_50", "operator": "<", "threshold": 0.0},
                {"column": "dxy_ret_20d", "operator": "<", "threshold": 0.0},
            ],
        },
        {
            "rule_key": "d1_backup",
            "label": "D1 DXY Real Yield Gold Trend H60",
            "type": "backup",
            "horizon_trading_days": 60,
            "conditions": [
                {"column": "gold_sma20_over_50", "operator": ">", "threshold": 0.0},
                {"column": "dxy_ret_20d", "operator": "<", "threshold": 0.0},
                {"column": "real_yield_change_20d", "operator": "<", "threshold": 0.0},
            ],
        },
        {
            "rule_key": "d4_backup",
            "label": "D4 Vol Risk-Off Real Yield Gold Long H60",
            "type": "backup",
            "horizon_trading_days": 60,
            "conditions": [
                {"column": "gold_sma20_over_50", "operator": ">", "threshold": 0.0},
                {"column": "vix_change_20d", "operator": ">", "threshold": 0.0},
                {"column": "real_yield_change_20d", "operator": "<", "threshold": 0.0},
            ],
        },
    ],
}


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_date(value: str) -> Optional[dt.date]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if "T" in s:
        s = s.split("T", 1)[0]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if not s or s.lower() in {"nan", "none", "null", "."}:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    if not math.isfinite(v):
        return None
    return v


def first_present(candidates: Sequence[str], columns: Sequence[str]) -> Optional[str]:
    colset = set(columns)
    for c in candidates:
        if c in colset:
            return c
    return None


def load_config(path: Optional[Path]) -> Dict[str, Any]:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if path and path.exists():
        with path.open("r", encoding="utf-8") as f:
            user_cfg = json.load(f)
        for k, v in user_cfg.items():
            cfg[k] = v
    return cfg


def load_macro(path: Path, cfg: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"macro dataset not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        columns = reader.fieldnames or []
    date_col = first_present(cfg.get("date_column_candidates", []), columns)
    price_col = first_present(cfg.get("price_column_candidates", []), columns)
    if not date_col:
        raise ValueError(f"no date column found in {path}; columns={columns}")
    if not price_col:
        raise ValueError(f"no gold price column found in {path}; columns={columns}")
    cleaned = []
    for raw in rows:
        d = parse_date(raw.get(date_col))
        price = parse_float(raw.get(price_col))
        if d is None or price is None or price <= 0:
            continue
        r = dict(raw)
        r["__date"] = d
        r["__price"] = price
        cleaned.append(r)
    cleaned.sort(key=lambda r: r["__date"])
    if not cleaned:
        raise ValueError("macro dataset has no valid dated price rows")
    info = {
        "path": str(path),
        "rows": len(cleaned),
        "raw_rows": len(rows),
        "columns": columns,
        "date_col": date_col,
        "price_col": price_col,
        "min_date": cleaned[0]["__date"].isoformat(),
        "max_date": cleaned[-1]["__date"].isoformat(),
        "sha256": sha256_file(path),
    }
    return cleaned, info


def condition_pass(value: Optional[float], op: str, threshold: float) -> Optional[bool]:
    if value is None:
        return None
    if op == ">":
        return value > threshold
    if op == ">=":
        return value >= threshold
    if op == "<":
        return value < threshold
    if op == "<=":
        return value <= threshold
    if op == "==":
        return value == threshold
    raise ValueError(f"unsupported operator: {op}")


def evaluate_rule_mask(rows: List[Dict[str, Any]], rule: Dict[str, Any]) -> Tuple[List[bool], Dict[str, Any]]:
    conds = rule.get("conditions", [])
    missing_columns = []
    columns = set(rows[0].keys()) if rows else set()
    for cond in conds:
        if cond["column"] not in columns:
            missing_columns.append(cond["column"])
    active = []
    evaluable = 0
    active_days = 0
    for r in rows:
        passes = []
        missing = False
        for cond in conds:
            val = parse_float(r.get(cond["column"]))
            p = condition_pass(val, cond["operator"], float(cond["threshold"]))
            if p is None:
                missing = True
            passes.append(p)
        if missing:
            active.append(False)
            continue
        evaluable += 1
        is_active = all(bool(x) for x in passes)
        active.append(is_active)
        if is_active:
            active_days += 1
    metrics = {
        "missing_columns": missing_columns,
        "evaluable_rows": evaluable,
        "active_days": active_days,
        "active_pct_of_evaluable": round(100.0 * active_days / evaluable, 4) if evaluable else 0.0,
    }
    return active, metrics


def make_entries(rows: List[Dict[str, Any]], mask: List[bool], rule: Dict[str, Any], cost_bps: float) -> List[Dict[str, Any]]:
    horizon = int(rule["horizon_trading_days"])
    entries: List[Dict[str, Any]] = []
    next_allowed_i = 0
    for i, is_active in enumerate(mask):
        if not is_active or i < next_allowed_i:
            continue
        exit_i = i + horizon
        if exit_i >= len(rows):
            continue
        entry_px = rows[i]["__price"]
        exit_px = rows[exit_i]["__price"]
        gross = (exit_px / entry_px - 1.0) * 10000.0
        net = gross - cost_bps
        entries.append({
            "rule_key": rule["rule_key"],
            "label": rule.get("label", rule["rule_key"]),
            "type": rule.get("type", "unknown"),
            "horizon_trading_days": horizon,
            "entry_index": i,
            "exit_index": exit_i,
            "entry_date": rows[i]["__date"].isoformat(),
            "exit_date": rows[exit_i]["__date"].isoformat(),
            "entry_price": round(entry_px, 6),
            "exit_price": round(exit_px, 6),
            "gross_return_bps": round(gross, 6),
            "net_return_bps": round(net, 6),
            "cost_bps_total": cost_bps,
        })
        next_allowed_i = exit_i + 1
    return entries


def mean(xs: Sequence[float]) -> Optional[float]:
    vals = [x for x in xs if x is not None and math.isfinite(x)]
    return sum(vals) / len(vals) if vals else None


def median(xs: Sequence[float]) -> Optional[float]:
    vals = sorted(x for x in xs if x is not None and math.isfinite(x))
    if not vals:
        return None
    mid = len(vals) // 2
    if len(vals) % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2


def summarize_returns(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    nets = [float(e["net_return_bps"]) for e in entries]
    gross = [float(e["gross_return_bps"]) for e in entries]
    wins = [x > 0 for x in nets]
    return {
        "entry_count": len(entries),
        "mean_gross_return_bps": round(mean(gross), 4) if gross else None,
        "mean_net_return_bps": round(mean(nets), 4) if nets else None,
        "median_net_return_bps": round(median(nets), 4) if nets else None,
        "win_rate": round(sum(wins) / len(wins), 4) if wins else None,
        "min_net_return_bps": round(min(nets), 4) if nets else None,
        "max_net_return_bps": round(max(nets), 4) if nets else None,
    }


def build_clusters(entries: List[Dict[str, Any]], window_days: int) -> List[Dict[str, Any]]:
    dated = []
    for e in entries:
        d = parse_date(e["entry_date"])
        if d:
            dated.append((d, e))
    dated.sort(key=lambda x: (x[0], x[1]["rule_key"]))
    clusters: List[Dict[str, Any]] = []
    current: List[Tuple[dt.date, Dict[str, Any]]] = []
    cluster_start: Optional[dt.date] = None
    for d, e in dated:
        if not current:
            current = [(d, e)]
            cluster_start = d
            continue
        assert cluster_start is not None
        if (d - cluster_start).days <= window_days:
            current.append((d, e))
        else:
            clusters.append(cluster_summary(len(clusters) + 1, current))
            current = [(d, e)]
            cluster_start = d
    if current:
        clusters.append(cluster_summary(len(clusters) + 1, current))
    return clusters


def cluster_summary(cluster_id: int, items: List[Tuple[dt.date, Dict[str, Any]]]) -> Dict[str, Any]:
    dates = [d for d, _ in items]
    entries = [e for _, e in items]
    rules = sorted({e["rule_key"] for e in entries})
    nets = [float(e["net_return_bps"]) for e in entries]
    return {
        "cluster_id": cluster_id,
        "cluster_start": min(dates).isoformat(),
        "cluster_end": max(dates).isoformat(),
        "entry_count": len(entries),
        "rule_count": len(rules),
        "rules": ";".join(rules),
        "mean_net_return_bps": round(mean(nets), 4) if nets else None,
        "best_net_return_bps": round(max(nets), 4) if nets else None,
        "worst_net_return_bps": round(min(nets), 4) if nets else None,
        "positive_entry_count": sum(1 for x in nets if x > 0),
    }


def annotate_overlap(entries_by_rule: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    all_entries = [e for entries in entries_by_rule.values() for e in entries]
    by_entry_date_rules: Dict[str, set] = {}
    for e in all_entries:
        by_entry_date_rules.setdefault(e["entry_date"], set()).add(e["rule_key"])
    annotated = []
    for e in all_entries:
        others_same_day = sorted(by_entry_date_rules.get(e["entry_date"], set()) - {e["rule_key"]})
        row = dict(e)
        row["same_day_other_rules"] = ";".join(others_same_day)
        row["is_same_day_unique"] = "true" if not others_same_day else "false"
        annotated.append(row)
    annotated.sort(key=lambda e: (e["entry_date"], e["rule_key"]))
    return annotated


def incremental_returns(annotated_entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for rule_key in sorted({e["rule_key"] for e in annotated_entries}):
        rule_entries = [e for e in annotated_entries if e["rule_key"] == rule_key]
        unique_entries = [e for e in rule_entries if e["is_same_day_unique"] == "true"]
        overlapped_entries = [e for e in rule_entries if e["is_same_day_unique"] != "true"]
        row = {"rule_key": rule_key}
        for prefix, group in (("all", rule_entries), ("same_day_unique", unique_entries), ("same_day_overlapped", overlapped_entries)):
            s = summarize_returns(group)
            row[f"{prefix}_entry_count"] = s["entry_count"]
            row[f"{prefix}_mean_net_return_bps"] = s["mean_net_return_bps"]
            row[f"{prefix}_win_rate"] = s["win_rate"]
            row[f"{prefix}_min_net_return_bps"] = s["min_net_return_bps"]
        row["same_day_unique_share_pct"] = round(100.0 * len(unique_entries) / len(rule_entries), 4) if rule_entries else 0.0
        out.append(row)
    return out


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: List[str] = []
    for row in rows:
        for k in row.keys():
            if k not in fields:
                fields.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def make_report(summary: Dict[str, Any]) -> str:
    lines = []
    lines.append("# Stage68C Return / Incremental Value Audit")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    for k in ("status", "decision", "classification", "return_value_posture"):
        lines.append(f"- {k}: `{summary.get(k)}`")
    lines.append("")
    lines.append("## Macro dataset")
    lines.append("")
    md = summary.get("macro_dataset", {})
    lines.append(f"- rows: `{md.get('rows')}`")
    lines.append(f"- min_date: `{md.get('min_date')}`")
    lines.append(f"- max_date: `{md.get('max_date')}`")
    lines.append("")
    lines.append("## Rule return metrics")
    lines.append("")
    for rk, m in summary.get("rule_return_metrics", {}).items():
        lines.append(f"### `{rk}`")
        for key in ["entry_count", "mean_net_return_bps", "median_net_return_bps", "win_rate", "min_net_return_bps", "max_net_return_bps"]:
            lines.append(f"- {key}: `{m.get(key)}`")
        lines.append("")
    lines.append("## Cluster metrics")
    lines.append("")
    for k, v in summary.get("cluster_metrics", {}).items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")
    lines.append("## Incremental same-day return contribution")
    lines.append("")
    for row in summary.get("incremental_return_contribution", []):
        lines.append(
            f"- `{row.get('rule_key')}`: all_entries=`{row.get('all_entry_count')}`, "
            f"unique_entries=`{row.get('same_day_unique_entry_count')}`, "
            f"unique_share=`{row.get('same_day_unique_share_pct')}`, "
            f"unique_mean_net_bps=`{row.get('same_day_unique_mean_net_return_bps')}`, "
            f"all_mean_net_bps=`{row.get('all_mean_net_return_bps')}`"
        )
    lines.append("")
    lines.append("## Hard blocks")
    for b in summary.get("hard_blocks", []):
        lines.append(f"- `{b}`")
    lines.append("")
    return "\n".join(lines)


def classify(summary: Dict[str, Any]) -> str:
    metrics = summary.get("rule_return_metrics", {})
    cluster = summary.get("cluster_metrics", {})
    positive_rules = 0
    for m in metrics.values():
        val = m.get("mean_net_return_bps")
        if isinstance(val, (int, float)) and val > 0:
            positive_rules += 1
    compression = cluster.get("entry_cluster_compression_pct") or 0.0
    if positive_rules >= 2 and compression >= 50:
        return "POSITIVE_RULE_RETURNS_BUT_MATERIAL_CLUSTERING_REQUIRE_CLUSTER_RETURN_SELECTION"
    if positive_rules >= 2:
        return "POSITIVE_RULE_RETURNS_LOW_CLUSTERING_REVIEW_FOR_READINESS_DESIGN"
    if positive_rules == 1:
        return "ONE_RULE_POSITIVE_OTHERS_REQUIRE_REWORK_OR_REJECT"
    return "NO_POSITIVE_MEAN_NET_RULE_RETURN_REJECT_OR_REDESIGN"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=STAGE)
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", default=None)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    cfg_path = (root / args.config).resolve() if args.config else None
    cfg = load_config(cfg_path)
    out_dir = (root / args.out).resolve() if not os.path.isabs(args.out) else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    macro_path = root / cfg["macro_dataset_path"]
    rows, macro_info = load_macro(macro_path, cfg)
    cost_bps = float(cfg.get("cost_bps_total", 50.0))
    cluster_window = int(cfg.get("cluster_window_calendar_days", 60))

    entries_by_rule: Dict[str, List[Dict[str, Any]]] = {}
    rule_return_metrics: Dict[str, Dict[str, Any]] = {}
    rule_activity_metrics: Dict[str, Dict[str, Any]] = {}
    for rule in cfg["rules"]:
        mask, activity = evaluate_rule_mask(rows, rule)
        entries = make_entries(rows, mask, rule, cost_bps)
        entries_by_rule[rule["rule_key"]] = entries
        rule_activity_metrics[rule["rule_key"]] = {
            **activity,
            "horizon_trading_days": rule["horizon_trading_days"],
            "label": rule.get("label"),
            "type": rule.get("type"),
        }
        rule_return_metrics[rule["rule_key"]] = summarize_returns(entries)

    annotated = annotate_overlap(entries_by_rule)
    clusters = build_clusters(annotated, cluster_window)
    incremental = incremental_returns(annotated)

    raw_entry_count = len(annotated)
    cluster_count = len(clusters)
    cluster_compression = round(100.0 * (raw_entry_count - cluster_count) / raw_entry_count, 4) if raw_entry_count else 0.0
    cluster_metrics = {
        "raw_rule_entry_count": raw_entry_count,
        "entry_cluster_window_calendar_days": cluster_window,
        "entry_cluster_count": cluster_count,
        "entry_cluster_compression_pct": cluster_compression,
    }

    summary: Dict[str, Any] = {
        "stage": STAGE,
        "root": str(root),
        "config": str(cfg_path) if cfg_path else None,
        "generated_utc": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "status": "STAGE68C_COMPLETE_NO_PROMOTION",
        "decision": "STAGE68C_RETURN_INCREMENTAL_VALUE_AUDIT_COMPLETE_NO_ORDER",
        "classification": "S68C_RETURN_INCREMENTAL_AUDIT_COMPLETE",
        "macro_dataset": macro_info,
        "cost_bps_total": cost_bps,
        "rule_activity_metrics": rule_activity_metrics,
        "rule_return_metrics": rule_return_metrics,
        "cluster_metrics": cluster_metrics,
        "incremental_return_contribution": incremental,
        "hard_blocks": HARD_BLOCKS,
        "operator_instructions": [
            "Stage68C is diagnostic only and cannot authorize orders.",
            "Do not tune thresholds from this audit alone.",
            "Use cluster and incremental return results to decide whether Stage69 complementary thesis expansion is needed.",
            "Broker, EA, paper-live, and live paths remain blocked.",
        ],
        "outputs": {
            "summary_json": str(out_dir / "stage68c_return_incremental_value_audit_summary.json"),
            "report_md": str(out_dir / "stage68c_return_incremental_value_audit_report.md"),
            "rule_entry_returns_csv": str(out_dir / "stage68c_rule_entry_returns.csv"),
            "entry_clusters_csv": str(out_dir / "stage68c_entry_clusters.csv"),
            "incremental_return_contribution_csv": str(out_dir / "stage68c_incremental_return_contribution.csv"),
        },
    }
    summary["return_value_posture"] = classify(summary)

    write_csv(out_dir / "stage68c_rule_entry_returns.csv", annotated)
    write_csv(out_dir / "stage68c_entry_clusters.csv", clusters)
    write_csv(out_dir / "stage68c_incremental_return_contribution.csv", incremental)

    summary_path = out_dir / "stage68c_return_incremental_value_audit_summary.json"
    report_path = out_dir / "stage68c_return_incremental_value_audit_report.md"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    report_path.write_text(make_report(summary), encoding="utf-8")

    print(json.dumps({
        "stage": STAGE,
        "status": summary["status"],
        "decision": summary["decision"],
        "classification": summary["classification"],
        "return_value_posture": summary["return_value_posture"],
        "summary_json": str(summary_path),
        "report_md": str(report_path),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
