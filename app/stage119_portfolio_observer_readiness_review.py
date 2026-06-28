#!/usr/bin/env python3
"""
Stage119_PORTFOLIO_OBSERVER_READINESS_REVIEW

Portfolio/overlap/observer-readiness review for rules that survived Stage118.
Data-only governance stage. It never writes MT5 bridge files, never edits EA files,
and never authorizes paper/demo/live orders.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

STAGE = "Stage119_PORTFOLIO_OBSERVER_READINESS_REVIEW"
STATUS = "STAGE119_COMPLETE_PORTFOLIO_OBSERVER_REVIEW_READY_NO_PROMOTION"
HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_MT5_OR_EA_CHANGE_FROM_STAGE119",
    "NO_EA_CHANGE",
    "NO_OBSERVER_UPDATE_FROM_STAGE119",
    "NO_PAPER_LIVE",
    "NO_LIVE",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_csv_dicts(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv_dicts(path: Path, rows: List[Dict[str, object]], fieldnames: Optional[List[str]] = None) -> None:
    ensure_dir(path.parent)
    if fieldnames is None:
        keys: List[str] = []
        for row in rows:
            for k in row.keys():
                if k not in keys:
                    keys.append(k)
        fieldnames = keys
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def write_json(path: Path, obj: Dict[str, object]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def as_float(value: object, default: float = math.nan) -> float:
    try:
        if value is None:
            return default
        s = str(value).strip()
        if s == "" or s.lower() in {"nan", "none", "null"}:
            return default
        return float(s)
    except Exception:
        return default


def as_bool(value: object) -> bool:
    s = str(value).strip().lower()
    return s in {"true", "1", "yes", "y"}


def index_cost_summary(rows: List[Dict[str, str]]) -> Dict[Tuple[str, str, float], Dict[str, str]]:
    out: Dict[Tuple[str, str, float], Dict[str, str]] = {}
    for row in rows:
        key = (row.get("rule_id", ""), row.get("split", ""), as_float(row.get("cost_bps"), 0.0))
        out[key] = row
    return out


def overlap_lookup(rows: List[Dict[str, str]]) -> Dict[Tuple[str, str], Dict[str, str]]:
    out: Dict[Tuple[str, str], Dict[str, str]] = {}
    for row in rows:
        out[(row.get("rule_id_a", ""), row.get("rule_id_b", ""))] = row
    return out


def load_stage116_context(root: Path) -> Dict[str, object]:
    p = root / "reports" / "stage116_source_specific_wgc_spdr_dxy_validator" / "stage116_source_specific_wgc_spdr_dxy_validator_summary.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {"stage116_context_error": f"could not parse {p}"}
    return {"stage116_context_error": "missing Stage116 summary"}


def readiness_for_rule(row: Dict[str, str], cost_idx: Dict[Tuple[str, str, float], Dict[str, str]]) -> Dict[str, object]:
    rule_id = row.get("rule_id", "")
    decision = row.get("audit_decision", "")
    candidate_only = as_bool(row.get("candidate_only"))
    stage116_dxy_fallback = as_bool(row.get("stage116_dxy_fallback_active"))
    stage116_direct_dxy_valid = as_bool(row.get("stage116_direct_dxy_valid"))
    spdr_status = row.get("stage116_spdr_status", "")

    val10 = cost_idx.get((rule_id, "validation", 10.0), {})
    tail10 = cost_idx.get((rule_id, "tail_forward_proxy", 10.0), {})
    val10_mean = as_float(val10.get("raw_mean_bps"))
    tail10_mean = as_float(tail10.get("raw_mean_bps"))
    val10_hit = as_float(val10.get("raw_hit_rate"))
    tail10_hit = as_float(tail10.get("raw_hit_rate"))
    val10_nonoverlap = as_float(val10.get("nonoverlap_mean_bps"))
    tail10_nonoverlap = as_float(tail10.get("nonoverlap_mean_bps"))

    score = 0.0
    reasons: List[str] = []

    if decision == "HARD_PASS_STAGE119_AUDIT_QUEUE":
        score += 45
        reasons.append("stage118_hard_pass")
    elif decision == "WATCH_STAGE119_ONLY_WITH_EXTRA_CONFIRMATION":
        score += 20
        reasons.append("stage118_watch_only")
    else:
        score -= 100
        reasons.append("stage118_not_selected")

    if math.isfinite(val10_mean) and val10_mean > 25:
        score += 12
        reasons.append("validation_cost10_mean_positive")
    if math.isfinite(tail10_mean) and tail10_mean > 25:
        score += 18
        reasons.append("tail_cost10_mean_positive")
    elif math.isfinite(tail10_mean) and tail10_mean > 0:
        score += 6
        reasons.append("tail_cost10_mean_barely_positive")
    elif math.isfinite(tail10_mean):
        score -= 20
        reasons.append("tail_cost10_mean_nonpositive")

    if math.isfinite(tail10_hit) and tail10_hit >= 0.60:
        score += 10
        reasons.append("tail_cost10_hit_ge_60pct")
    elif math.isfinite(tail10_hit) and tail10_hit < 0.53:
        score -= 10
        reasons.append("tail_cost10_hit_weak")

    if math.isfinite(tail10_nonoverlap) and tail10_nonoverlap > 25:
        score += 8
        reasons.append("tail_nonoverlap_cost10_positive")

    if candidate_only:
        score -= 12
        reasons.append("candidate_only_source_penalty")
        if spdr_status == "VALIDATED_CANDIDATE":
            score += 8
            reasons.append("spdr_validated_candidate_source")

    if stage116_dxy_fallback and not stage116_direct_dxy_valid:
        score -= 4
        reasons.append("direct_dxy_invalid_using_fallback")

    if decision == "HARD_PASS_STAGE119_AUDIT_QUEUE" and score >= 65:
        readiness = "PRIMARY_OBSERVER_REVIEW_CANDIDATE_NO_UPDATE"
    elif decision == "HARD_PASS_STAGE119_AUDIT_QUEUE" and score >= 50:
        readiness = "SECONDARY_OBSERVER_REVIEW_CANDIDATE_NO_UPDATE"
    elif decision.startswith("WATCH") or score >= 30:
        readiness = "WATCH_ONLY_EXTRA_CONFIRMATION_NO_UPDATE"
    else:
        readiness = "DO_NOT_CARRY_FORWARD"

    return {
        "rule_id": rule_id,
        "description": row.get("description", ""),
        "stage118_audit_decision": decision,
        "candidate_only": candidate_only,
        "observer_readiness": readiness,
        "readiness_score": round(score, 2),
        "validation_cost10_mean_bps": val10_mean,
        "validation_cost10_hit_rate": val10_hit,
        "tail_cost10_mean_bps": tail10_mean,
        "tail_cost10_hit_rate": tail10_hit,
        "validation_nonoverlap_cost10_mean_bps": val10_nonoverlap,
        "tail_nonoverlap_cost10_mean_bps": tail10_nonoverlap,
        "raw_all_events": as_float(row.get("raw_all_events"), 0.0),
        "stage116_dxy_fallback_active": stage116_dxy_fallback,
        "stage116_direct_dxy_valid": stage116_direct_dxy_valid,
        "stage116_spdr_status": spdr_status,
        "readiness_reasons": ";".join(reasons),
    }


def build_portfolio_review(selected: List[Dict[str, str]], overlap_rows: List[Dict[str, str]]) -> List[Dict[str, object]]:
    lookup = overlap_lookup(overlap_rows)
    rows: List[Dict[str, object]] = []
    for i, a in enumerate(selected):
        for b in selected[i + 1:]:
            rid_a = a.get("rule_id", "")
            rid_b = b.get("rule_id", "")
            ov = lookup.get((rid_a, rid_b), lookup.get((rid_b, rid_a), {}))
            j = as_float(ov.get("raw_hourly_jaccard"), math.nan)
            if math.isfinite(j):
                if j <= 0.15:
                    bucket = "LOW_OVERLAP_CAN_COMBINE_IN_STAGE120_DESIGN"
                elif j <= 0.35:
                    bucket = "MEDIUM_OVERLAP_NEEDS_CAP_OR_DEDUP"
                else:
                    bucket = "HIGH_OVERLAP_DO_NOT_STACK"
            else:
                bucket = "OVERLAP_UNKNOWN"
            rows.append({
                "rule_id_a": rid_a,
                "rule_id_b": rid_b,
                "raw_hourly_jaccard": j,
                "raw_hourly_intersection": ov.get("raw_hourly_intersection", ""),
                "raw_hourly_union": ov.get("raw_hourly_union", ""),
                "portfolio_overlap_bucket": bucket,
            })
    return rows


def governance_rows(readiness_rows: List[Dict[str, object]], stage116_context: Dict[str, object]) -> List[Dict[str, object]]:
    primary_count = sum(str(r.get("observer_readiness", "")).startswith("PRIMARY") for r in readiness_rows)
    secondary_count = sum(str(r.get("observer_readiness", "")).startswith("SECONDARY") for r in readiness_rows)
    watch_count = sum(str(r.get("observer_readiness", "")).startswith("WATCH") for r in readiness_rows)
    return [
        {"gate": "ORDER_PERMISSION", "status": "BLOCKED", "reason": "Stage119 is review-only; no automated/paper/demo/live order."},
        {"gate": "MT5_OR_EA_CHANGE", "status": "BLOCKED", "reason": "No EA, MT5 bridge, or observer file update is allowed by Stage119."},
        {"gate": "DIRECT_DXY", "status": "SOFT_FAIL_FALLBACK_OK", "reason": f"direct_dxy_valid={stage116_context.get('direct_dxy_valid')} fallback={stage116_context.get('dxy_fallback_active')}"},
        {"gate": "WGC_CENTRAL_BANK", "status": "EXCLUDED_FROM_HARD_FEATURES", "reason": f"wgc rows/status: ETF={stage116_context.get('wgc_gold_etf_status')} CB={stage116_context.get('wgc_central_bank_status')}"},
        {"gate": "STAGE120_DESIGN_QUEUE", "status": "READY" if primary_count + secondary_count + watch_count > 0 else "NOT_READY", "reason": f"primary={primary_count} secondary={secondary_count} watch={watch_count}"},
    ]


def write_report(path: Path, summary: Dict[str, object], readiness: List[Dict[str, object]], portfolio: List[Dict[str, object]]) -> None:
    lines: List[str] = []
    lines.append(f"# {STAGE}")
    lines.append("")
    lines.append(f"Generated UTC: {summary['generated_utc']}")
    lines.append("")
    lines.append(f"Status: `{summary['status']}`")
    lines.append("")
    lines.append(f"Decision: `{summary['decision']}`")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("Stage119 reviews the Stage118 survivors as a combined portfolio / observer-readiness queue. It does not update any observer, MT5 bridge, EA, broker connection, or order surface.")
    lines.append("")
    lines.append("## Rule readiness")
    lines.append("")
    for r in readiness:
        lines.append(f"- `{r['rule_id']}`: `{r['observer_readiness']}` | score={r['readiness_score']} | tail_cost10_mean={r['tail_cost10_mean_bps']}")
    lines.append("")
    lines.append("## Portfolio overlap")
    lines.append("")
    if portfolio:
        for p in portfolio:
            lines.append(f"- `{p['rule_id_a']}` vs `{p['rule_id_b']}`: jaccard={p['raw_hourly_jaccard']} → `{p['portfolio_overlap_bucket']}`")
    else:
        lines.append("- Only one rule or overlap unavailable.")
    lines.append("")
    lines.append("## Next")
    lines.append("")
    lines.append("If Stage120 is built, it should create an observer-design review package only. It should not write production observer CSVs or authorize orders without a separate approval gate.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(root: Path) -> Dict[str, object]:
    stage118_dir = root / "reports" / "stage118_macro_cot_spdr_hard_audit"
    out_dir = root / "reports" / "stage119_portfolio_observer_readiness_review"
    ensure_dir(out_dir)

    selected = read_csv_dicts(stage118_dir / "stage118_selected_for_stage119.csv")
    audit = read_csv_dicts(stage118_dir / "stage118_rule_audit_metrics.csv")
    cost = read_csv_dicts(stage118_dir / "stage118_cost_stress_summary.csv")
    overlap = read_csv_dicts(stage118_dir / "stage118_overlap_matrix.csv")
    feature_cov = read_csv_dicts(stage118_dir / "stage118_feature_coverage_by_rule.csv")
    stage116_context = load_stage116_context(root)

    selected_by_id = {r.get("rule_id", ""): r for r in selected if r.get("rule_id")}
    if not selected_by_id:
        selected_by_id = {r.get("rule_id", ""): r for r in audit if r.get("rule_id") and r.get("audit_decision") not in {"FAIL_NO_STAGE119", ""}}

    selected_rows = list(selected_by_id.values())
    cost_idx = index_cost_summary(cost)
    readiness = [readiness_for_rule(r, cost_idx) for r in selected_rows]
    readiness.sort(key=lambda r: float(r.get("readiness_score", 0.0)), reverse=True)

    portfolio = build_portfolio_review(selected_rows, overlap)
    governance = governance_rows(readiness, stage116_context)

    observer_queue = [r for r in readiness if r["observer_readiness"] != "DO_NOT_CARRY_FORWARD"]
    primary_count = sum(str(r["observer_readiness"]).startswith("PRIMARY") for r in readiness)
    secondary_count = sum(str(r["observer_readiness"]).startswith("SECONDARY") for r in readiness)
    watch_count = sum(str(r["observer_readiness"]).startswith("WATCH") for r in readiness)

    if primary_count > 0:
        decision = "STAGE119_PRIMARY_OBSERVER_DESIGN_QUEUE_READY_NO_UPDATE"
    elif secondary_count > 0 or watch_count > 0:
        decision = "STAGE119_WATCH_OBSERVER_DESIGN_QUEUE_READY_NO_UPDATE"
    else:
        decision = "STAGE119_NO_OBSERVER_DESIGN_QUEUE_NO_UPDATE"

    paths = {
        "rule_readiness_scores": out_dir / "stage119_rule_readiness_scores.csv",
        "portfolio_overlap_review": out_dir / "stage119_portfolio_overlap_review.csv",
        "observer_readiness_queue": out_dir / "stage119_observer_readiness_queue.csv",
        "governance_gate": out_dir / "stage119_governance_gate.csv",
        "feature_coverage_copy": out_dir / "stage119_feature_coverage_review.csv",
        "summary_json": out_dir / "stage119_portfolio_observer_readiness_review_summary.json",
        "report_md": out_dir / "stage119_portfolio_observer_readiness_review_report.md",
    }

    write_csv_dicts(paths["rule_readiness_scores"], readiness)
    write_csv_dicts(paths["portfolio_overlap_review"], portfolio)
    write_csv_dicts(paths["observer_readiness_queue"], observer_queue)
    write_csv_dicts(paths["governance_gate"], governance)
    write_csv_dicts(paths["feature_coverage_copy"], feature_cov)

    summary: Dict[str, object] = {
        "stage": STAGE,
        "generated_utc": utc_now(),
        "status": STATUS,
        "decision": decision,
        "classification": "PORTFOLIO_OBSERVER_READINESS_REVIEW_ONLY_NO_UPDATE",
        "hard_blocks": HARD_BLOCKS,
        "root": str(root),
        "stage118_dir": str(stage118_dir),
        "stage118_selected_count": len(selected_rows),
        "primary_count": primary_count,
        "secondary_count": secondary_count,
        "watch_count": watch_count,
        "do_not_carry_forward_count": sum(r["observer_readiness"] == "DO_NOT_CARRY_FORWARD" for r in readiness),
        "stage116_context": stage116_context,
        "rule_readiness_scores": str(paths["rule_readiness_scores"]),
        "portfolio_overlap_review": str(paths["portfolio_overlap_review"]),
        "observer_readiness_queue": str(paths["observer_readiness_queue"]),
        "governance_gate": str(paths["governance_gate"]),
        "feature_coverage_review": str(paths["feature_coverage_copy"]),
        "summary_json": str(paths["summary_json"]),
        "report_md": str(paths["report_md"]),
        "next": [
            "If a primary or secondary observer-design queue exists, Stage120 may create an observer-design review package only.",
            "Stage120 must not write the live observer bridge or authorize order flow unless a separate explicit gate is created.",
            "If only watch rules exist, require extra confirmation or a fresh segmented discovery run before observer design.",
        ],
    }
    write_json(paths["summary_json"], summary)
    write_report(paths["report_md"], summary, readiness, portfolio)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default=".", help="Repository root")
    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve()
    summary = run(root)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
