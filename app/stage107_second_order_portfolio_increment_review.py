#!/usr/bin/env python3
"""Stage107 second-order COT/macro portfolio increment review.

Reviews Stage106 hard-audit survivors for incremental contribution before any
observer-only expansion. This stage never changes MT5/EA/order state.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

STAGE = "Stage107_SECOND_ORDER_PORTFOLIO_INCREMENT_REVIEW"
HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_EA_PROMOTION",
    "NO_MT5_OR_EA_CHANGE",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE107",
    "NO_THRESHOLD_TUNING_FROM_STAGE107_PORTFOLIO_REVIEW",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_csv_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys = []
        for r in rows:
            for k in r.keys():
                if k not in keys:
                    keys.append(k)
        fieldnames = keys
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def as_float(row: Dict[str, Any], key: str, default: float = 0.0) -> float:
    v = row.get(key, default)
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s == "" or s.lower() in {"nan", "none", "null"}:
        return default
    try:
        return float(s)
    except Exception:
        return default


def as_int(row: Dict[str, Any], key: str, default: int = 0) -> int:
    return int(round(as_float(row, key, float(default))))


def clean_text(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if s.lower() in {"nan", "none", "null"}:
        return ""
    return s


def resolve_path(root: Path, maybe_path: str) -> Path:
    p = Path(maybe_path)
    if p.is_absolute():
        return p
    return root / p


def gate_candidate(row: Dict[str, Any], constraints: Dict[str, Any], already_selected: List[Dict[str, Any]]) -> Tuple[bool, List[str], float]:
    reasons: List[str] = []

    hard_score = as_float(row, "second_order_hard_audit_score")
    total_entries = as_int(row, "total_entry_count")
    total_mean = as_float(row, "total_mean_net_bps")
    total_win = as_float(row, "total_win_rate")
    worst_loss = abs(as_float(row, "total_min_net_return_bps"))
    locked_entries = as_int(row, "locked_forward_entry_count")
    locked_mean = as_float(row, "locked_forward_mean_net_bps")
    final_entries = as_int(row, "final_holdout_entry_count")
    final_mean = as_float(row, "final_holdout_mean_net_bps")
    post_entries = as_int(row, "post_asof_entry_count")
    post_mean = as_float(row, "post_asof_mean_net_bps")
    max_year_share = as_float(row, "max_year_entry_share")
    missing = as_int(row, "missing_required_feature_rows")
    lookahead = as_int(row, "lookahead_violations")
    incremental = as_int(row, "incremental_union_active_days_recomputed") or as_int(row, "incremental_union_active_days")
    active_days = as_int(row, "candidate_active_days_recomputed") or as_int(row, "raw_active_days")
    overlap = as_float(row, "overlap_with_current_union_pct_recomputed") or as_float(row, "overlap_with_current_union_pct")

    if hard_score < float(constraints.get("min_second_order_hard_audit_score", 0)):
        reasons.append("HARD_AUDIT_SCORE_TOO_LOW")
    if total_entries < int(constraints.get("min_total_entries", 0)):
        reasons.append("TOTAL_ENTRIES_TOO_LOW")
    if total_mean < float(constraints.get("min_total_mean_net_bps", -10**9)):
        reasons.append("TOTAL_MEAN_TOO_LOW")
    if total_win < float(constraints.get("min_total_win_rate", 0)):
        reasons.append("WIN_RATE_TOO_LOW")
    if worst_loss > float(constraints.get("max_abs_worst_loss_bps", 10**9)):
        reasons.append("WORST_LOSS_TOO_LARGE")
    if locked_entries < int(constraints.get("min_locked_forward_entries", 0)):
        reasons.append("LOCKED_FORWARD_ENTRIES_TOO_LOW")
    if locked_mean < float(constraints.get("min_locked_forward_mean_bps", -10**9)):
        reasons.append("LOCKED_FORWARD_MEAN_TOO_LOW")
    if final_entries < int(constraints.get("min_final_holdout_entries", 0)):
        reasons.append("FINAL_HOLDOUT_ENTRIES_TOO_LOW")
    if final_mean < float(constraints.get("min_final_holdout_mean_bps", -10**9)):
        reasons.append("FINAL_HOLDOUT_MEAN_TOO_LOW")
    if post_entries < int(constraints.get("min_post_asof_entries", 0)):
        reasons.append("POST_ASOF_ENTRIES_TOO_LOW")
    if post_mean < float(constraints.get("min_post_asof_mean_bps", -10**9)):
        reasons.append("POST_ASOF_MEAN_TOO_LOW")
    if max_year_share > float(constraints.get("max_year_entry_share", 1.0)):
        reasons.append("YEAR_CONCENTRATION_TOO_HIGH")
    if missing > int(constraints.get("max_missing_required_feature_rows", 0)):
        reasons.append("MISSING_REQUIRED_FEATURE_ROWS")
    if lookahead > int(constraints.get("max_lookahead_violations", 0)):
        reasons.append("LOOKAHEAD_VIOLATIONS")
    if active_days < int(constraints.get("min_candidate_active_days", 0)):
        reasons.append("ACTIVE_DAYS_TOO_LOW")
    if incremental < int(constraints.get("min_incremental_union_active_days", 0)):
        reasons.append("INCREMENTAL_DAYS_TOO_LOW")
    if overlap > float(constraints.get("max_overlap_with_current_pct", 100.0)):
        reasons.append("OVERLAP_WITH_CURRENT_TOO_HIGH")

    # For multiple additions, approximate pairwise overlap using existing selected raw active days only if a prior row exposed a same-rule marker.
    # Stage107 normally handles one Stage106 survivor; this remains deterministic and conservative.
    if already_selected and int(constraints.get("max_additions", 1)) <= len(already_selected):
        reasons.append("MAX_ADDITIONS_REACHED")

    score = (
        hard_score
        + final_mean * 0.8
        + post_mean * 0.8
        + locked_mean * 0.35
        + incremental * 2.0
        - max(0.0, overlap - 50.0) * 20.0
        - max(0.0, worst_loss - 1200.0) * 0.2
    )
    return len(reasons) == 0, reasons, score


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    config_path = resolve_path(root, args.config)
    out_dir = resolve_path(root, args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = load_json(config_path)
    stage106_summary_path = resolve_path(root, cfg.get("stage106_summary_path", "reports/stage106_second_order_cot_macro_hard_audit/stage106_second_order_cot_macro_hard_audit_summary.json"))
    stage106_selected_path = resolve_path(root, cfg.get("stage106_selected_csv_path", "reports/stage106_second_order_cot_macro_hard_audit/stage106_selected_for_stage107.csv"))

    issues: List[str] = []
    stage106_summary: Dict[str, Any] = {}
    if stage106_summary_path.exists():
        stage106_summary = load_json(stage106_summary_path)
    else:
        issues.append(f"MISSING_STAGE106_SUMMARY:{stage106_summary_path}")

    candidates = load_csv_rows(stage106_selected_path)
    if not candidates:
        issues.append(f"NO_STAGE106_SELECTED_ROWS:{stage106_selected_path}")

    constraints = cfg.get("constraints", {})
    max_additions = int(constraints.get("max_additions", 1))

    reviewed: List[Dict[str, Any]] = []
    selected: List[Dict[str, Any]] = []
    for row in candidates:
        row = dict(row)
        passed, reasons, score = gate_candidate(row, constraints, selected)
        if passed and len(selected) < max_additions:
            selected.append(row)
        elif passed and len(selected) >= max_additions:
            passed = False
            reasons = ["MAX_ADDITIONS_REACHED"]
        row["stage107_portfolio_review_score"] = round(score, 4)
        row["pass_stage107_portfolio_review"] = str(bool(passed)).lower()
        row["stage107_fail_reasons"] = "|".join(reasons)
        reviewed.append(row)

    selected_rule_ids = [clean_text(r.get("rule_id")) for r in selected]
    selected_for_stage108 = [r for r in reviewed if clean_text(r.get("rule_id")) in set(selected_rule_ids) and clean_text(r.get("pass_stage107_portfolio_review")) == "true"]

    current_rules = stage106_summary.get("current_unified_portfolio_rule_ids") or cfg.get("current_unified_portfolio_rule_ids", [])
    final_rules = current_rules + selected_rule_ids

    current_union = None
    if stage106_summary.get("selected_for_stage107"):
        try:
            current_union = int(round(float(stage106_summary["selected_for_stage107"][0].get("current_union_active_days_recomputed", 0))))
        except Exception:
            current_union = None
    if current_union is None:
        current_union = int(cfg.get("current_union_active_days_fallback", 0))

    inc_selected = sum(as_int(r, "incremental_union_active_days_recomputed") or as_int(r, "incremental_union_active_days") for r in selected_for_stage108)
    final_union = current_union + inc_selected if current_union else inc_selected

    decision = "STAGE107_NO_SECOND_ORDER_INCREMENT_SELECTED_NO_ORDER"
    classification = "S107_NO_SECOND_ORDER_INCREMENT_SELECTED"
    disposition = "KEEP_STAGE100_UNIFIED_COT_OBSERVER_ONLY"
    if selected_for_stage108:
        decision = "STAGE107_SECOND_ORDER_INCREMENT_SELECTED_FOR_OBSERVER_REVIEW_NO_ORDER"
        classification = "S107_SECOND_ORDER_INCREMENT_SELECTED"
        disposition = "SECOND_ORDER_INCREMENT_SELECTED_FOR_STAGE108_UNIFIED_OBSERVER_EXPANSION"

    review_csv = out_dir / "stage107_second_order_portfolio_increment_review.csv"
    selected_csv = out_dir / "stage107_selected_for_stage108.csv"
    write_csv(review_csv, reviewed)
    write_csv(selected_csv, selected_for_stage108, fieldnames=list(reviewed[0].keys()) if reviewed else None)

    summary = {
        "stage": STAGE,
        "root": str(root),
        "config": str(config_path),
        "generated_utc": utc_now(),
        "status": "STAGE107_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "principle": "Review Stage106 second-order hard-audit survivors for incremental portfolio contribution before any observer-only expansion. No order, broker, MT5, EA, paper-live, or live change.",
        "stage106_reference": {
            "summary_path": str(stage106_summary_path),
            "selected_csv_path": str(stage106_selected_path),
            "exists": stage106_summary_path.exists(),
            "decision": stage106_summary.get("decision"),
            "selected_rule_ids": stage106_summary.get("selected_rule_ids", []),
            "summary_sha256": sha256_file(stage106_summary_path),
            "selected_csv_sha256": sha256_file(stage106_selected_path),
        },
        "current_unified_portfolio_rule_ids": current_rules,
        "candidate_count": len(candidates),
        "selected_count": len(selected_for_stage108),
        "selected_rule_ids": selected_rule_ids,
        "selected_for_stage108": selected_for_stage108,
        "final_review_portfolio_rule_ids": final_rules,
        "current_union_active_days_recomputed_reference": current_union,
        "incremental_union_active_days_selected": inc_selected,
        "final_union_active_days_after_selected_additions_reference": final_union,
        "constraints": constraints,
        "issues": issues,
        "hard_blocks": HARD_BLOCKS,
        "outputs": {
            "summary_json": str(out_dir / "stage107_second_order_portfolio_increment_review_summary.json"),
            "report_md": str(out_dir / "stage107_second_order_portfolio_increment_review_report.md"),
            "review_csv": str(review_csv),
            "selected_csv": str(selected_csv),
        },
    }

    summary_path = out_dir / "stage107_second_order_portfolio_increment_review_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    report = [
        "# Stage107 Second-Order Portfolio Increment Review",
        "",
        "## Decision",
        f"- status: `{summary['status']}`",
        f"- decision: `{decision}`",
        f"- classification: `{classification}`",
        f"- disposition: `{disposition}`",
        "",
        "## Candidates",
        f"- candidate_count: `{len(candidates)}`",
        f"- selected_count: `{len(selected_for_stage108)}`",
        f"- selected_rule_ids: `{', '.join(selected_rule_ids)}`",
        "",
        "## Portfolio",
        f"- current_union_active_days_reference: `{current_union}`",
        f"- incremental_union_active_days_selected: `{inc_selected}`",
        f"- final_union_active_days_after_selected_additions_reference: `{final_union}`",
        "",
        "## Hard blocks",
    ]
    report.extend(f"- `{b}`" for b in HARD_BLOCKS)
    (out_dir / "stage107_second_order_portfolio_increment_review_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    print(json.dumps({"status": summary["status"], "decision": decision, "selected_rule_ids": selected_rule_ids, "issues": issues}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
