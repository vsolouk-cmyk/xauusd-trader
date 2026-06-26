#!/usr/bin/env python3
"""
Stage66E Complementary Shortlist Audit & Rule Lock

Audits the pre-registered Stage66D complementary-thesis shortlist, locks the
single top-ranked PASS_FAST candidate, and evaluates current no-broker readiness.
No orders, broker connections, EA promotion, paper-live, live path, or threshold
tuning are authorized.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE66E",
    "NO_THRESHOLD_TUNING",
    "NO_RESCUE_FILTERING",
    "NO_PROMOTION_FROM_COMPLEMENTARY_AUDIT_ONLY",
]


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_json(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")


def safe_float(x: Any) -> Optional[float]:
    try:
        if x is None or x == "":
            return None
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def parse_date(s: str) -> Optional[dt.date]:
    if not s:
        return None
    t = str(s).strip().replace("Z", "+00:00")
    try:
        if "T" in t:
            return dt.datetime.fromisoformat(t).date()
        return dt.date.fromisoformat(t[:10])
    except Exception:
        return None


def get_latest_macro_row(macro_path: Path, date_col: str = "feature_date_utc") -> Tuple[Optional[Dict[str, str]], Dict[str, Any]]:
    info = {
        "path": str(macro_path),
        "exists": macro_path.exists(),
        "date_column": date_col,
        "row_count": 0,
        "latest_date": None,
        "issues": [],
    }
    if not macro_path.exists():
        info["issues"].append("MACRO_DATASET_NOT_FOUND")
        return None, info
    latest_row = None
    latest_date = None
    with macro_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or date_col not in reader.fieldnames:
            info["issues"].append(f"DATE_COLUMN_NOT_FOUND:{date_col}")
            return None, info
        for row in reader:
            info["row_count"] += 1
            d = parse_date(row.get(date_col, ""))
            if d is None:
                continue
            if latest_date is None or d > latest_date:
                latest_date = d
                latest_row = row
    info["latest_date"] = latest_date.isoformat() if latest_date else None
    if latest_row is None:
        info["issues"].append("NO_PARSEABLE_MACRO_ROWS")
    return latest_row, info


def eval_conditions(row: Optional[Dict[str, str]], conditions: List[Dict[str, Any]]) -> Dict[str, Any]:
    results = []
    failures = []
    active = True
    if row is None:
        active = False
    for cond in conditions:
        field = cond.get("field")
        op = cond.get("operator")
        threshold = safe_float(cond.get("threshold", 0.0))
        value = safe_float(row.get(field)) if row is not None and field in row else None
        ok = False
        if value is not None and threshold is not None:
            if op == ">":
                ok = value > threshold
            elif op == ">=":
                ok = value >= threshold
            elif op == "<":
                ok = value < threshold
            elif op == "<=":
                ok = value <= threshold
            elif op == "==":
                ok = value == threshold
        if not ok:
            active = False
            failures.append(f"{field}:{value}{op}{threshold}")
        results.append({"field": field, "operator": op, "threshold": threshold, "value": value, "ok": ok})
    return {"signal_active": active, "condition_results": results, "rule_failures": failures}


def select_candidate(stage66d: Dict[str, Any], config: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], List[str], Dict[str, Any]]:
    issues: List[str] = []
    selection_cfg = config.get("selection_policy", {})
    required_decision = selection_cfg.get("required_stage66d_decision", "STAGE66D_PASS_FAST_COMPLEMENTARY_SHORTLIST_NO_ORDER")
    if stage66d.get("decision") != required_decision:
        issues.append(f"STAGE66D_DECISION_NOT_ALLOWED:{stage66d.get('decision')}")
        return None, issues, {}
    top = stage66d.get("top_ranked_results") or []
    pass_fast = [r for r in top if r.get("classification") == "PASS_FAST_COMPLEMENTARY_CANDIDATE_NO_ORDER"]
    if not pass_fast:
        issues.append("NO_PASS_FAST_CANDIDATE_IN_TOP_RANKED_RESULTS")
        return None, issues, {"pass_fast_count": 0}
    selected = pass_fast[0]
    expected_id = selection_cfg.get("expected_primary_thesis_id")
    expected_h = selection_cfg.get("expected_primary_horizon_trading_days")
    if expected_id and selected.get("thesis_id") != expected_id:
        issues.append(f"TOP_PASS_FAST_THESIS_MISMATCH:{selected.get('thesis_id')} != {expected_id}")
    if expected_h and int(selected.get("horizon_trading_days", -1)) != int(expected_h):
        issues.append(f"TOP_PASS_FAST_HORIZON_MISMATCH:{selected.get('horizon_trading_days')} != {expected_h}")
    return selected if not issues else None, issues, {
        "pass_fast_count": len(pass_fast),
        "top_pass_fast_thesis_id": selected.get("thesis_id"),
        "top_pass_fast_horizon_trading_days": selected.get("horizon_trading_days"),
    }


def gate_selected_candidate(selected: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    thresholds = config.get("audit_thresholds", {})
    ps = selected.get("position_stats", {})
    diag = selected.get("diagnostics", {})
    sizing = ps.get("sizing_band_stats") or []
    dbase = next((x for x in sizing if x.get("band") == thresholds.get("base_band_name", "D_base")), None)

    trade_count = safe_float(ps.get("trade_count"))
    mean_net = safe_float(ps.get("mean_net_return_bps"))
    win_rate = safe_float(ps.get("win_rate"))
    min_net = safe_float(ps.get("min_net_return_bps"))
    max_year_share = safe_float(ps.get("max_year_trade_share"))
    payoff = safe_float(ps.get("payoff_ratio_win_mean_abs_loss_mean"))
    base_dd = abs(safe_float(dbase.get("max_drawdown_pct")) or 999.0) if dbase else 999.0
    lookahead = safe_float(diag.get("lookahead_breaches"))
    active_rows = safe_float(diag.get("active_rows"))
    closed_positions = safe_float(diag.get("closed_positions"))
    skipped_overlap = safe_float(diag.get("skipped_overlap"))

    checks = {
        "trade_count_gate": (trade_count or 0) >= thresholds.get("min_closed_positions", 30),
        "mean_net_gate": (mean_net or -1e9) >= thresholds.get("min_mean_net_return_bps", 175.0),
        "win_rate_gate": (win_rate or 0) >= thresholds.get("min_win_rate", 0.58),
        "single_loss_gate": (min_net or -1e9) > thresholds.get("kill_if_single_trade_loss_bps_lte", -1800.0),
        "year_concentration_gate": (max_year_share or 1.0) <= thresholds.get("max_year_trade_share", 0.15),
        "base_drawdown_gate": base_dd <= thresholds.get("max_abs_base_band_drawdown_pct", 4.0),
        "payoff_gate": (payoff or 0) >= thresholds.get("min_payoff_ratio", 1.15),
        "lookahead_gate": (lookahead or 0) == 0,
    }
    all_ok = all(checks.values())
    return {
        "checks": checks,
        "all_gates_ok": all_ok,
        "metrics_used": {
            "active_rows": active_rows,
            "closed_positions": closed_positions,
            "skipped_overlap": skipped_overlap,
            "trade_count": trade_count,
            "mean_net_return_bps": mean_net,
            "win_rate": win_rate,
            "min_net_return_bps": min_net,
            "max_year_trade_share": max_year_share,
            "payoff_ratio": payoff,
            "base_band_abs_drawdown_pct": base_dd,
            "lookahead_breaches": lookahead,
        },
    }


def build_rule_lock(selected: Dict[str, Any], stage66d: Dict[str, Any], config: Dict[str, Any], stage66d_path: Path) -> Dict[str, Any]:
    rule = {
        "rule_id": f"{selected.get('thesis_id')}_H{selected.get('horizon_trading_days')}",
        "source_stage": "Stage66D_LIMITED_COMPLEMENTARY_THESIS_SCAN",
        "source_stage66d_summary_path": str(stage66d_path),
        "source_stage66d_summary_sha256": sha256_file(stage66d_path),
        "selection_policy": config.get("selection_policy", {}),
        "hypothesis": selected.get("hypothesis"),
        "thesis_id": selected.get("thesis_id"),
        "horizon_trading_days": selected.get("horizon_trading_days"),
        "entry_rule": stage66d.get("execution_model", {}).get("entry_rule", "first_external_d1_close_on_or_after_sample_available_after_utc"),
        "exit_rule": "fixed_registered_horizon",
        "position_mode": stage66d.get("execution_model", {}).get("position_mode", "single_position_non_overlapping"),
        "conditions": selected.get("conditions", []),
        "cost_policy": {
            "round_trip_execution_cost_bps": stage66d.get("execution_model", {}).get("round_trip_execution_cost_bps"),
            "feed_mismatch_penalty_bps": stage66d.get("execution_model", {}).get("feed_mismatch_penalty_bps"),
            "total_penalty_bps": stage66d.get("execution_model", {}).get("total_penalty_bps"),
        },
        "no_order_policy": "NO_ORDER_NO_BROKER_NO_EA_NO_PAPER_LIVE_NO_LIVE",
        "locked_at_utc": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
    }
    rule["rule_sha256"] = sha256_json({k: v for k, v in rule.items() if k != "rule_sha256"})
    return rule


def render_report(summary: Dict[str, Any]) -> str:
    sel = summary.get("selected_candidate", {})
    gate = summary.get("audit_gate", {})
    ready = summary.get("current_signal_evaluation", {})
    lines = [
        "# Stage66E Complementary Shortlist Audit & Rule Lock",
        "",
        "## Decision",
        "",
        f"- status: `{summary.get('status')}`",
        f"- decision: `{summary.get('decision')}`",
        f"- classification: `{summary.get('classification')}`",
        "",
        "## Selected candidate",
        "",
        f"- thesis_id: `{sel.get('thesis_id')}`",
        f"- horizon_trading_days: `{sel.get('horizon_trading_days')}`",
        f"- classification_from_stage66d: `{sel.get('classification')}`",
        f"- rule_lock_path: `{summary.get('outputs', {}).get('selected_rule_lock')}`",
        "",
        "## Audit metrics",
        "",
        "```json",
        json.dumps(gate.get("metrics_used", {}), indent=2, sort_keys=True),
        "```",
        "",
        "## Audit checks",
        "",
        "```json",
        json.dumps(gate.get("checks", {}), indent=2, sort_keys=True),
        "```",
        "",
        "## Current signal evaluation",
        "",
        "```json",
        json.dumps(ready, indent=2, sort_keys=True),
        "```",
        "",
        "## Hard blocks",
        "",
    ]
    lines.extend([f"- `{x}`" for x in summary.get("hard_blocks", [])])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage66e_complementary_shortlist_audit.json")
    ap.add_argument("--out", default="reports/stage66e_complementary_shortlist_audit")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    config_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    config = load_json(config_path)
    paths = config.get("input_paths", {})
    stage66d_path = root / paths.get("stage66d_summary_path", "reports/stage66d_limited_complementary_thesis_scan/stage66d_limited_complementary_thesis_scan_summary.json")
    stage66h_path = root / paths.get("stage66h_summary_path", "reports/stage66h_no_broker_dry_run_ticket_generator/stage66h_no_broker_dry_run_ticket_generator_summary.json")
    macro_path = root / paths.get("macro_dataset_path", "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv")

    issues: List[str] = []
    stage66d = {}
    stage66h = {}
    if not stage66d_path.exists():
        issues.append("STAGE66D_SUMMARY_NOT_FOUND")
    else:
        stage66d = load_json(stage66d_path)
    if stage66h_path.exists():
        stage66h = load_json(stage66h_path)

    selected, selection_issues, selection_diag = select_candidate(stage66d, config) if stage66d else (None, ["NO_STAGE66D_FOR_SELECTION"], {})
    issues.extend(selection_issues)

    audit_gate = {}
    rule_lock = None
    if selected is not None:
        audit_gate = gate_selected_candidate(selected, config)
        if audit_gate.get("all_gates_ok"):
            rule_lock = build_rule_lock(selected, stage66d, config, stage66d_path)
        else:
            issues.append("SELECTED_CANDIDATE_AUDIT_GATES_NOT_ALL_OK")

    latest_row = None
    macro_info = {}
    signal_eval = {"signal_active": False, "condition_results": [], "rule_failures": []}
    if selected is not None:
        latest_row, macro_info = get_latest_macro_row(macro_path, config.get("macro_date_column", "feature_date_utc"))
        signal_eval = eval_conditions(latest_row, selected.get("conditions", []))
        if latest_row:
            signal_eval["feature_date_utc"] = latest_row.get(config.get("macro_date_column", "feature_date_utc"))
            signal_eval["sample_available_after_utc"] = latest_row.get("sample_available_after_utc")

    rule_lock_path = None
    if rule_lock is not None:
        rule_lock_path = root / config.get("output_rule_lock_path", "configs/stage66e_selected_complementary_rule_lock.json")
        write_json(rule_lock_path, rule_lock)

    if issues:
        decision = "STAGE66E_STOP_COMPLEMENTARY_AUDIT_FAILED_NO_ORDER"
        classification = "E_FAIL_OR_REVIEW"
    elif signal_eval.get("signal_active"):
        decision = "STAGE66E_PASS_FAST_COMPLEMENTARY_RULE_LOCK_READY_SIGNAL_ACTIVE_NO_ORDER"
        classification = "E_PASS_FAST_SIGNAL_ACTIVE_DESIGN_READY"
    else:
        decision = "STAGE66E_PASS_FAST_COMPLEMENTARY_RULE_LOCK_READY_WAIT_SIGNAL_NO_ORDER"
        classification = "E_PASS_FAST_WAIT_SIGNAL"

    summary = {
        "stage": "Stage66E_COMPLEMENTARY_SHORTLIST_AUDIT",
        "status": "STAGE66E_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "generated_utc": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "root": str(root),
        "config": str(config_path),
        "hard_blocks": HARD_BLOCKS,
        "input_paths": {
            "stage66d_summary_path": str(stage66d_path.relative_to(root)) if stage66d_path.is_relative_to(root) else str(stage66d_path),
            "stage66h_summary_path": str(stage66h_path.relative_to(root)) if stage66h_path.is_relative_to(root) else str(stage66h_path),
            "macro_dataset_path": str(macro_path.relative_to(root)) if macro_path.is_relative_to(root) else str(macro_path),
        },
        "input_hashes": {
            "config_sha256": sha256_file(config_path),
            "stage66d_summary_sha256": sha256_file(stage66d_path),
            "stage66h_summary_sha256": sha256_file(stage66h_path),
            "macro_dataset_sha256": sha256_file(macro_path),
        },
        "input_gate": {
            "stage66d_decision": stage66d.get("decision"),
            "stage66h_decision": stage66h.get("decision"),
            "selection_diag": selection_diag,
            "issues": issues,
        },
        "selected_candidate": {
            "thesis_id": selected.get("thesis_id") if selected else None,
            "horizon_trading_days": selected.get("horizon_trading_days") if selected else None,
            "classification": selected.get("classification") if selected else None,
            "conditions": selected.get("conditions") if selected else None,
            "hypothesis": selected.get("hypothesis") if selected else None,
            "position_stats": selected.get("position_stats") if selected else None,
            "diagnostics": selected.get("diagnostics") if selected else None,
        },
        "audit_gate": audit_gate,
        "macro_info": macro_info,
        "current_signal_evaluation": signal_eval,
        "outputs": {
            "summary_json": str((out_dir / "stage66e_complementary_shortlist_audit_summary.json").relative_to(root)) if out_dir.is_relative_to(root) else str(out_dir / "stage66e_complementary_shortlist_audit_summary.json"),
            "report_md": str((out_dir / "stage66e_complementary_shortlist_audit_report.md").relative_to(root)) if out_dir.is_relative_to(root) else str(out_dir / "stage66e_complementary_shortlist_audit_report.md"),
            "selected_rule_lock": str(rule_lock_path.relative_to(root)) if rule_lock_path and rule_lock_path.is_relative_to(root) else (str(rule_lock_path) if rule_lock_path else None),
        },
        "next_step": "If PASS_FAST and signal is inactive, run daily Stage66E/Stage66H-style readiness while building Stage66I no-broker complementary dry-run ticket generator. No order path is authorized by Stage66E.",
    }

    summary_path = out_dir / "stage66e_complementary_shortlist_audit_summary.json"
    report_path = out_dir / "stage66e_complementary_shortlist_audit_report.md"
    write_json(summary_path, summary)
    report_path.write_text(render_report(summary), encoding="utf-8")
    print(json.dumps({"status": summary["status"], "decision": decision, "classification": classification, "summary": str(summary_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
