#!/usr/bin/env python3
"""Stage68D cluster-level return selection policy audit.

Diagnostic only. Reads Stage68C rule entry returns, reconstructs calendar-window
clusters, compares pre-registered static rule-priority policies, and writes a
cluster-selection report. It does not authorize orders or tune thresholds.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

STAGE = "Stage68D_CLUSTER_RETURN_SELECTION_POLICY"


def parse_date(s: str) -> date:
    return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()


def fnum(x: Any) -> float:
    if x is None or x == "":
        return float("nan")
    return float(x)


def safe_round(x: float, n: int = 4) -> Optional[float]:
    if x is None or not math.isfinite(x):
        return None
    return round(float(x), n)


@dataclass
class Entry:
    rule_key: str
    label: str
    typ: str
    horizon: int
    entry_date: date
    exit_date: date
    entry_price: float
    exit_price: float
    net_return_bps: float
    gross_return_bps: float
    row: Dict[str, Any]


def read_entries(path: Path) -> List[Entry]:
    if not path.exists():
        raise FileNotFoundError(f"missing Stage68C rule entry returns CSV: {path}")
    entries: List[Entry] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"rule_key", "label", "type", "horizon_trading_days", "entry_date", "exit_date", "entry_price", "exit_price", "net_return_bps", "gross_return_bps"}
        missing = sorted(required - set(reader.fieldnames or []))
        if missing:
            raise ValueError(f"entry returns CSV missing columns: {missing}")
        for r in reader:
            entries.append(Entry(
                rule_key=r["rule_key"],
                label=r.get("label", r["rule_key"]),
                typ=r.get("type", ""),
                horizon=int(float(r.get("horizon_trading_days") or 0)),
                entry_date=parse_date(r["entry_date"]),
                exit_date=parse_date(r["exit_date"]),
                entry_price=fnum(r["entry_price"]),
                exit_price=fnum(r["exit_price"]),
                net_return_bps=fnum(r["net_return_bps"]),
                gross_return_bps=fnum(r["gross_return_bps"]),
                row=r,
            ))
    entries.sort(key=lambda e: (e.entry_date, e.rule_key))
    return entries


def build_clusters(entries: List[Entry], window_days: int) -> List[List[Entry]]:
    clusters: List[List[Entry]] = []
    current: List[Entry] = []
    cluster_start: Optional[date] = None
    for e in sorted(entries, key=lambda x: (x.entry_date, x.rule_key)):
        if cluster_start is None:
            current = [e]
            cluster_start = e.entry_date
            continue
        if (e.entry_date - cluster_start).days <= window_days:
            current.append(e)
        else:
            clusters.append(current)
            current = [e]
            cluster_start = e.entry_date
    if current:
        clusters.append(current)
    return clusters


def choose_by_policy(cluster: List[Entry], priority: List[str], allow: List[str]) -> Optional[Entry]:
    candidates = [e for e in cluster if e.rule_key in set(allow)]
    if not candidates:
        return None
    pri = {rule: i for i, rule in enumerate(priority)}
    candidates.sort(key=lambda e: (pri.get(e.rule_key, 10_000), e.entry_date, -e.net_return_bps))
    return candidates[0]


def choose_oracle(cluster: List[Entry]) -> Optional[Entry]:
    if not cluster:
        return None
    return sorted(cluster, key=lambda e: (-e.net_return_bps, e.entry_date, e.rule_key))[0]


def metrics(entries: List[Entry]) -> Dict[str, Any]:
    vals = [e.net_return_bps for e in entries]
    n = len(vals)
    if n == 0:
        return {
            "entry_count": 0, "mean_net_return_bps": None, "median_net_return_bps": None,
            "win_rate": None, "min_net_return_bps": None, "max_net_return_bps": None,
            "total_net_return_bps": 0.0, "avg_calendar_gap_days": None,
            "worst_3_entry_sum_bps": None,
        }
    vals_sorted = sorted(vals)
    med = vals_sorted[n//2] if n % 2 else (vals_sorted[n//2 - 1] + vals_sorted[n//2]) / 2.0
    dates = sorted(e.entry_date for e in entries)
    gaps = [(dates[i] - dates[i-1]).days for i in range(1, len(dates))]
    worst3 = sum(sorted(vals)[:min(3, n)])
    return {
        "entry_count": n,
        "mean_net_return_bps": safe_round(sum(vals) / n),
        "median_net_return_bps": safe_round(med),
        "win_rate": safe_round(sum(1 for v in vals if v > 0) / n, 4),
        "min_net_return_bps": safe_round(min(vals)),
        "max_net_return_bps": safe_round(max(vals)),
        "total_net_return_bps": safe_round(sum(vals)),
        "avg_calendar_gap_days": safe_round(sum(gaps) / len(gaps), 2) if gaps else None,
        "worst_3_entry_sum_bps": safe_round(worst3),
    }


def passes_constraints(m: Dict[str, Any], cons: Dict[str, Any]) -> bool:
    if m["entry_count"] < int(cons.get("min_entry_count", 0)):
        return False
    if (m.get("win_rate") or 0) < float(cons.get("min_win_rate", 0)):
        return False
    if (m.get("mean_net_return_bps") or -1e9) < float(cons.get("min_mean_net_return_bps", -1e9)):
        return False
    worst = m.get("min_net_return_bps")
    if worst is not None and abs(float(worst)) > float(cons.get("max_abs_worst_loss_bps", 1e9)):
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    config_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    entries_path = root / cfg["inputs"]["rule_entry_returns_csv"]
    entries = read_entries(entries_path)
    clusters = build_clusters(entries, int(cfg.get("cluster_window_calendar_days", 60)))

    selected_rows: List[Dict[str, Any]] = []
    policy_results: Dict[str, Dict[str, Any]] = {}
    policy_selected: Dict[str, List[Entry]] = {}

    # static policies
    for p in cfg.get("policies", []):
        pid = p["policy_id"]
        chosen: List[Entry] = []
        for cid, cluster in enumerate(clusters, start=1):
            e = choose_by_policy(cluster, p.get("priority", []), p.get("allow_rules", []))
            if e is None:
                continue
            chosen.append(e)
            selected_rows.append({
                "policy_id": pid,
                "cluster_id": cid,
                "cluster_start": min(x.entry_date for x in cluster).isoformat(),
                "cluster_end": max(x.entry_date for x in cluster).isoformat(),
                "cluster_entry_count": len(cluster),
                "cluster_rules": ";".join(sorted(set(x.rule_key for x in cluster))),
                "selected_rule": e.rule_key,
                "selected_entry_date": e.entry_date.isoformat(),
                "selected_exit_date": e.exit_date.isoformat(),
                "selected_net_return_bps": safe_round(e.net_return_bps),
            })
        policy_selected[pid] = chosen
        policy_results[pid] = metrics(chosen)
        policy_results[pid]["policy_id"] = pid
        policy_results[pid]["priority"] = p.get("priority", [])
        policy_results[pid]["allow_rules"] = p.get("allow_rules", [])

    # oracle diagnostic
    oracle_id = cfg.get("diagnostic_oracle_policy_id", "ORACLE_BEST_IN_CLUSTER_DIAGNOSTIC_ONLY")
    oracle_entries: List[Entry] = []
    for cid, cluster in enumerate(clusters, start=1):
        e = choose_oracle(cluster)
        if e is None:
            continue
        oracle_entries.append(e)
        selected_rows.append({
            "policy_id": oracle_id,
            "cluster_id": cid,
            "cluster_start": min(x.entry_date for x in cluster).isoformat(),
            "cluster_end": max(x.entry_date for x in cluster).isoformat(),
            "cluster_entry_count": len(cluster),
            "cluster_rules": ";".join(sorted(set(x.rule_key for x in cluster))),
            "selected_rule": e.rule_key,
            "selected_entry_date": e.entry_date.isoformat(),
            "selected_exit_date": e.exit_date.isoformat(),
            "selected_net_return_bps": safe_round(e.net_return_bps),
        })
    policy_selected[oracle_id] = oracle_entries
    policy_results[oracle_id] = metrics(oracle_entries)
    policy_results[oracle_id]["policy_id"] = oracle_id
    policy_results[oracle_id]["diagnostic_only"] = True

    constraints = cfg.get("selection_constraints", {})
    eligible = [r for pid, r in policy_results.items() if pid != oracle_id and passes_constraints(r, constraints)]
    eligible.sort(key=lambda r: (r.get("mean_net_return_bps") or -1e9, r.get("median_net_return_bps") or -1e9, r.get("entry_count") or 0), reverse=True)
    selected_policy = eligible[0]["policy_id"] if eligible else None

    if selected_policy is None:
        posture = "NO_STATIC_CLUSTER_POLICY_PASSES_CONSTRAINTS_REQUIRES_THESIS_EXPANSION"
    else:
        best = policy_results[selected_policy]
        oracle_mean = policy_results[oracle_id].get("mean_net_return_bps") or 0
        gap = oracle_mean - (best.get("mean_net_return_bps") or 0)
        if gap > 250:
            posture = "STATIC_POLICY_POSITIVE_BUT_ORACLE_GAP_LARGE_REQUIRES_CAUTION"
        else:
            posture = "STATIC_CLUSTER_POLICY_CANDIDATE_READY_FOR_ROBUSTNESS_AUDIT_NO_ORDER"

    # CSV outputs
    comp_path = out_dir / cfg["outputs"].get("policy_comparison_csv", "stage68d_policy_comparison.csv")
    with comp_path.open("w", encoding="utf-8", newline="") as f:
        cols = ["policy_id", "entry_count", "mean_net_return_bps", "median_net_return_bps", "win_rate", "min_net_return_bps", "max_net_return_bps", "total_net_return_bps", "avg_calendar_gap_days", "worst_3_entry_sum_bps", "priority", "allow_rules", "diagnostic_only"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for pid, r in sorted(policy_results.items(), key=lambda kv: (kv[1].get("diagnostic_only", False), kv[1].get("mean_net_return_bps") or -1e9), reverse=True):
            w.writerow({c: json.dumps(r[c]) if isinstance(r.get(c), list) else r.get(c, "") for c in cols})

    sel_path = out_dir / cfg["outputs"].get("selected_entries_csv", "stage68d_selected_cluster_entries.csv")
    with sel_path.open("w", encoding="utf-8", newline="") as f:
        cols = ["policy_id", "cluster_id", "cluster_start", "cluster_end", "cluster_entry_count", "cluster_rules", "selected_rule", "selected_entry_date", "selected_exit_date", "selected_net_return_bps"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for row in selected_rows:
            w.writerow(row)

    # summary/report
    summary = {
        "stage": STAGE,
        "root": str(root),
        "config": str(config_path),
        "generated_utc": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "status": "STAGE68D_COMPLETE_NO_PROMOTION",
        "decision": "STAGE68D_CLUSTER_RETURN_SELECTION_POLICY_COMPLETE_NO_ORDER",
        "classification": "S68D_CLUSTER_SELECTION_POLICY_AUDIT_COMPLETE",
        "return_selection_posture": posture,
        "input_entries": {
            "path": str(entries_path),
            "raw_rule_entry_count": len(entries),
            "cluster_window_calendar_days": int(cfg.get("cluster_window_calendar_days", 60)),
            "entry_cluster_count": len(clusters),
            "cluster_compression_pct": safe_round((1 - len(clusters) / len(entries)) * 100.0) if entries else None,
        },
        "policy_results": policy_results,
        "selected_static_policy_candidate": selected_policy,
        "selection_constraints": constraints,
        "hard_blocks": cfg.get("hard_blocks", []),
        "operator_instructions": [
            "Stage68D is diagnostic only and cannot authorize orders.",
            "The oracle policy is an upper-bound diagnostic and must never be used for forward selection.",
            "Any static policy candidate requires robustness and out-of-sample checks before readiness integration.",
            "Broker, EA, paper-live, and live paths remain blocked.",
        ],
        "outputs": {
            "summary_json": str(out_dir / cfg["outputs"].get("summary_json", "stage68d_cluster_return_selection_policy_summary.json")),
            "report_md": str(out_dir / cfg["outputs"].get("report_md", "stage68d_cluster_return_selection_policy_report.md")),
            "policy_comparison_csv": str(comp_path),
            "selected_entries_csv": str(sel_path),
        },
    }

    summary_path = out_dir / cfg["outputs"].get("summary_json", "stage68d_cluster_return_selection_policy_summary.json")
    report_path = out_dir / cfg["outputs"].get("report_md", "stage68d_cluster_return_selection_policy_report.md")
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = []
    lines.append("# Stage68D Cluster Return Selection Policy\n")
    lines.append("## Decision\n")
    for k in ["status", "decision", "classification", "return_selection_posture"]:
        lines.append(f"- {k}: `{summary[k]}`")
    lines.append("\n## Input\n")
    inp = summary["input_entries"]
    for k in ["raw_rule_entry_count", "entry_cluster_count", "cluster_window_calendar_days", "cluster_compression_pct"]:
        lines.append(f"- {k}: `{inp[k]}`")
    lines.append("\n## Policy comparison\n")
    for pid, r in sorted(policy_results.items(), key=lambda kv: (kv[0] == oracle_id, kv[1].get("mean_net_return_bps") or -1e9), reverse=True):
        lines.append(f"\n### `{pid}`")
        for k in ["entry_count", "mean_net_return_bps", "median_net_return_bps", "win_rate", "min_net_return_bps", "max_net_return_bps", "avg_calendar_gap_days", "worst_3_entry_sum_bps"]:
            lines.append(f"- {k}: `{r.get(k)}`")
    lines.append("\n## Selected static policy candidate\n")
    lines.append(f"- `{selected_policy}`")
    lines.append("\n## Hard blocks\n")
    for hb in cfg.get("hard_blocks", []):
        lines.append(f"- `{hb}`")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "stage": STAGE,
        "status": summary["status"],
        "decision": summary["decision"],
        "return_selection_posture": posture,
        "selected_static_policy_candidate": selected_policy,
        "summary_json": str(summary_path),
        "report_md": str(report_path),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
