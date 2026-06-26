#!/usr/bin/env python3
"""Stage66K - complementary backup readiness expansion.

Locks and monitors pre-registered backup pass-fast complementary candidates from
Stage66D. This stage never authorizes orders, broker connections, EA promotion,
paper-live, or live execution.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class Condition:
    field: str
    operator: str
    threshold: float


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_obj(obj: Any) -> str:
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def parse_date(s: str) -> date:
    return datetime.fromisoformat(str(s).replace("Z", "+00:00")).date()


def load_csv_latest_row(path: Path, date_column_preference: Iterable[str]) -> Tuple[Optional[Dict[str, str]], Optional[str], int, List[str]]:
    issues: List[str] = []
    if not path.exists():
        return None, None, 0, [f"missing_macro_dataset:{path}"]
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        return None, None, 0, ["macro_dataset_empty"]
    columns = list(rows[0].keys())
    date_col = None
    for c in date_column_preference:
        if c in columns:
            date_col = c
            break
    if date_col is None:
        return None, None, len(rows), ["macro_date_column_not_found"]
    usable = []
    for row in rows:
        try:
            parse_date(row[date_col])
            usable.append(row)
        except Exception:
            continue
    if not usable:
        return None, date_col, len(rows), ["macro_dataset_no_parseable_dates"]
    usable.sort(key=lambda r: parse_date(r[date_col]))
    return usable[-1], date_col, len(rows), issues


def eval_condition(value_raw: Any, operator: str, threshold: float) -> Tuple[bool, Optional[float], Optional[str]]:
    try:
        value = float(value_raw)
    except Exception:
        return False, None, "value_not_numeric_or_missing"
    if operator == ">":
        return value > threshold, value, None
    if operator == "<":
        return value < threshold, value, None
    if operator == ">=":
        return value >= threshold, value, None
    if operator == "<=":
        return value <= threshold, value, None
    if operator == "==":
        return value == threshold, value, None
    return False, value, f"unsupported_operator:{operator}"


def evaluate_signal(row: Optional[Dict[str, str]], date_col: Optional[str], conditions: List[Dict[str, Any]]) -> Dict[str, Any]:
    if row is None:
        return {
            "signal_active": False,
            "condition_results": [],
            "rule_failures": ["missing_latest_macro_row"],
            "feature_date_utc": None,
            "sample_available_after_utc": None,
            "macro_date_column": date_col,
        }
    results = []
    failures = []
    for cond in conditions:
        ok, value, issue = eval_condition(row.get(cond["field"]), cond["operator"], float(cond.get("threshold", 0.0)))
        item = {
            "field": cond["field"],
            "operator": cond["operator"],
            "threshold": float(cond.get("threshold", 0.0)),
            "value": value,
            "ok": ok,
        }
        if issue:
            item["issue"] = issue
        results.append(item)
        if not ok:
            failures.append(f"{cond['field']}:{value}{cond['operator']}{float(cond.get('threshold', 0.0))}")
    return {
        "signal_active": bool(results) and all(r["ok"] for r in results),
        "condition_results": results,
        "rule_failures": failures,
        "feature_date_utc": row.get(date_col) if date_col else None,
        "sample_available_after_utc": row.get("sample_available_after_utc"),
        "macro_date_column": date_col,
    }


def base_drawdown_abs_pct(position_stats: Dict[str, Any]) -> Optional[float]:
    for band in position_stats.get("sizing_band_stats", []):
        if band.get("band") in {"D_base", "B_base"}:
            try:
                return abs(float(band.get("max_drawdown_pct")))
            except Exception:
                return None
    return None


def find_candidate(stage66d: Dict[str, Any], thesis_id: str, horizon: int) -> Optional[Dict[str, Any]]:
    candidates = stage66d.get("all_results") or stage66d.get("top_ranked_results") or []
    for item in candidates:
        if item.get("thesis_id") == thesis_id and int(item.get("horizon_trading_days", -1)) == int(horizon):
            return item
    return None


def audit_candidate(item: Dict[str, Any], thresholds: Dict[str, Any]) -> Dict[str, Any]:
    pos = item.get("position_stats", {})
    diag = item.get("diagnostics", {})
    bd = base_drawdown_abs_pct(pos)
    metrics = {
        "classification_from_stage66d": item.get("classification"),
        "trade_count": float(pos.get("trade_count", 0) or 0),
        "mean_net_return_bps": float(pos.get("mean_net_return_bps", 0) or 0),
        "win_rate": float(pos.get("win_rate", 0) or 0),
        "max_year_trade_share": float(pos.get("max_year_trade_share", 1) or 1),
        "payoff_ratio": float(pos.get("payoff_ratio_win_mean_abs_loss_mean", 0) or 0),
        "min_net_return_bps": float(pos.get("min_net_return_bps", 0) or 0),
        "base_band_abs_drawdown_pct": bd,
        "lookahead_breaches": float(diag.get("lookahead_breaches", 999999) or 0),
        "active_rows": float(diag.get("active_rows", 0) or 0),
        "closed_positions": float(diag.get("closed_positions", 0) or 0),
        "skipped_overlap": float(diag.get("skipped_overlap", 0) or 0),
    }
    checks = {
        "stage66d_pass_fast_gate": item.get("classification") == "PASS_FAST_COMPLEMENTARY_CANDIDATE_NO_ORDER",
        "trade_count_gate": metrics["trade_count"] >= float(thresholds["min_trade_count"]),
        "mean_net_gate": metrics["mean_net_return_bps"] >= float(thresholds["min_mean_net_return_bps"]),
        "win_rate_gate": metrics["win_rate"] >= float(thresholds["min_win_rate"]),
        "base_drawdown_gate": bd is not None and bd <= float(thresholds["max_abs_base_drawdown_pct"]),
        "year_concentration_gate": metrics["max_year_trade_share"] <= float(thresholds["max_year_trade_share"]),
        "payoff_gate": metrics["payoff_ratio"] >= float(thresholds["min_payoff_ratio"]),
        "single_loss_gate": metrics["min_net_return_bps"] >= float(thresholds["kill_if_single_trade_loss_bps_lt"]),
        "lookahead_gate": (metrics["lookahead_breaches"] == 0) if thresholds.get("require_zero_lookahead_breaches", True) else True,
    }
    return {"all_gates_ok": all(checks.values()), "checks": checks, "metrics_used": metrics}


def build_rule_lock(item: Dict[str, Any], generated_utc: str, stage66d_path: Path) -> Dict[str, Any]:
    rule = {
        "source_stage": "Stage66D_LIMITED_COMPLEMENTARY_THESIS_SCAN",
        "source_stage66d_summary_path": str(stage66d_path),
        "source_stage66d_summary_sha256": sha256_file(stage66d_path),
        "locked_at_utc": generated_utc,
        "rule_id": f"{item['thesis_id']}_H{int(item['horizon_trading_days'])}",
        "thesis_id": item["thesis_id"],
        "horizon_trading_days": int(item["horizon_trading_days"]),
        "hypothesis": item.get("hypothesis"),
        "conditions": item.get("conditions", []),
        "entry_rule": "first_external_d1_close_on_or_after_sample_available_after_utc",
        "exit_rule": "fixed_registered_horizon",
        "position_mode": "single_position_non_overlapping",
        "cost_policy": {
            "round_trip_execution_cost_bps": 35.0,
            "feed_mismatch_penalty_bps": 15.0,
            "total_penalty_bps": 50.0,
        },
        "no_order_policy": "NO_ORDER_NO_BROKER_NO_EA_NO_PAPER_LIVE_NO_LIVE",
        "selection_policy": {
            "method": "pre_registered_backup_pass_fast_only_no_metric_retuning",
            "do_not_select_by_new_thresholds": True,
            "do_not_rescue_filter": True,
        },
    }
    rule["rule_sha256"] = sha256_obj({k: v for k, v in rule.items() if k != "rule_sha256"})
    return rule


def append_ledger(path: Path, summary: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    fields = [
        "generated_utc",
        "decision",
        "classification",
        "active_backup_count",
        "ready_backup_count",
        "latest_feature_date",
        "ticket_generation_allowed_here",
    ]
    row = {
        "generated_utc": summary.get("generated_utc"),
        "decision": summary.get("decision"),
        "classification": summary.get("classification"),
        "active_backup_count": summary.get("backup_counts", {}).get("active_backup_count"),
        "ready_backup_count": summary.get("backup_counts", {}).get("ready_backup_count"),
        "latest_feature_date": summary.get("macro_info", {}).get("latest_feature_date"),
        "ticket_generation_allowed_here": False,
    }
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def render_report(summary: Dict[str, Any]) -> str:
    lines = []
    lines.append("# Stage66K Complementary Backup Readiness Expansion")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append(f"- status: `{summary['status']}`")
    lines.append(f"- decision: `{summary['decision']}`")
    lines.append(f"- classification: `{summary['classification']}`")
    lines.append("")
    lines.append("## Backup candidates")
    lines.append("")
    for item in summary.get("backup_readiness", []):
        lines.append(f"### `{item['rule_lock']['rule_id']}`")
        lines.append("")
        lines.append(f"- audit_pass: `{item['audit_gate']['all_gates_ok']}`")
        lines.append(f"- signal_active: `{item['signal_evaluation']['signal_active']}`")
        lines.append(f"- feature_date_utc: `{item['signal_evaluation']['feature_date_utc']}`")
        lines.append(f"- rule_failures: `{';'.join(item['signal_evaluation'].get('rule_failures', []))}`")
        metrics = item["audit_gate"]["metrics_used"]
        lines.append(f"- trade_count: `{metrics['trade_count']}`")
        lines.append(f"- mean_net_return_bps: `{metrics['mean_net_return_bps']}`")
        lines.append(f"- win_rate: `{metrics['win_rate']}`")
        lines.append("")
    lines.append("## Hard blocks")
    lines.append("")
    for block in summary.get("hard_blocks", []):
        lines.append(f"- `{block}`")
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", default="configs/stage66k_complementary_backup_readiness_expansion.json")
    parser.add_argument("--out", default="reports/stage66k_complementary_backup_readiness_expansion")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    config_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    config = read_json(config_path)
    generated_utc = utc_now()
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    inputs = config["root_relative_inputs"]
    stage66j_path = root / inputs["stage66j_summary"]
    stage66d_path = root / inputs["stage66d_summary"]
    macro_path = root / inputs["macro_dataset"]

    issues: List[str] = []
    stage66j = read_json(stage66j_path) if stage66j_path.exists() else None
    stage66d = read_json(stage66d_path) if stage66d_path.exists() else None
    if stage66j is None:
        issues.append(f"missing_stage66j_summary:{stage66j_path}")
    if stage66d is None:
        issues.append(f"missing_stage66d_summary:{stage66d_path}")

    if stage66j and stage66j.get("decision") not in config.get("allowed_stage66j_decisions", []):
        issues.append(f"stage66j_decision_not_allowed:{stage66j.get('decision')}")
    if stage66d and stage66d.get("decision") != config.get("required_stage66d_decision"):
        issues.append(f"stage66d_decision_not_allowed:{stage66d.get('decision')}")

    latest_row, date_col, macro_rows, macro_issues = load_csv_latest_row(macro_path, ["feature_date_utc", "date_utc", "date"])
    issues.extend(macro_issues)
    latest_feature_date = latest_row.get(date_col) if latest_row and date_col else None
    macro_lag_days = None
    if latest_feature_date:
        try:
            macro_lag_days = (datetime.now(timezone.utc).date() - parse_date(latest_feature_date)).days
        except Exception:
            macro_lag_days = None
    macro_freshness_gate = macro_lag_days is not None and macro_lag_days <= int(config["readiness"]["macro_freshness_max_calendar_lag_days"])
    if not macro_freshness_gate:
        issues.append(f"macro_freshness_gate_failed:{macro_lag_days}")

    backup_items = []
    rule_locks = []
    if stage66d:
        for sel in config["candidate_policy"]["selected_backup_candidates"]:
            item = find_candidate(stage66d, sel["thesis_id"], int(sel["horizon_trading_days"]))
            if item is None:
                issues.append(f"selected_candidate_missing:{sel['thesis_id']}_H{sel['horizon_trading_days']}")
                continue
            audit = audit_candidate(item, config["audit_thresholds"])
            rule_lock = build_rule_lock(item, generated_utc, stage66d_path)
            signal_eval = evaluate_signal(latest_row, date_col, item.get("conditions", []))
            backup_items.append({
                "rule_lock": rule_lock,
                "audit_gate": audit,
                "signal_evaluation": signal_eval,
                "source_candidate_snapshot": item,
                "readiness_gate": {
                    "audit_gate_ok": audit["all_gates_ok"],
                    "macro_freshness_gate": macro_freshness_gate,
                    "backup_signal_active": signal_eval["signal_active"],
                    "ticket_generation_allowed_here": False,
                }
            })
            rule_locks.append(rule_lock)

    ready_count = sum(1 for x in backup_items if x["audit_gate"]["all_gates_ok"])
    active_count = sum(1 for x in backup_items if x["audit_gate"]["all_gates_ok"] and x["signal_evaluation"]["signal_active"])

    if issues:
        decision = "STAGE66K_STOP_INPUT_OR_DATA_ISSUE_NO_ORDER"
        classification = "K_STOP_ISSUES"
    elif ready_count != len(config["candidate_policy"]["selected_backup_candidates"]):
        decision = "STAGE66K_BACKUP_AUDIT_NOT_READY_NO_ORDER"
        classification = "K_BACKUP_AUDIT_FAIL"
    elif active_count > 0:
        decision = "STAGE66K_BACKUP_SIGNAL_ACTIVE_REQUIRES_STAGE66L_NO_ORDER"
        classification = "K_BACKUP_SIGNAL_ACTIVE"
    else:
        decision = "STAGE66K_BACKUP_RULE_LOCKS_READY_WAIT_SIGNALS_NO_ORDER"
        classification = "K_BACKUP_READY_WAIT_SIGNALS"

    rule_locks_obj = {
        "stage": "Stage66K_COMPLEMENTARY_BACKUP_READINESS_EXPANSION",
        "generated_utc": generated_utc,
        "no_order_policy": "NO_ORDER_NO_BROKER_NO_EA_NO_PAPER_LIVE_NO_LIVE",
        "selection_policy": config["candidate_policy"],
        "rule_locks": rule_locks,
    }
    if not issues and rule_locks:
        write_json(root / config["outputs"]["rule_locks_json"], rule_locks_obj)

    summary = {
        "stage": "Stage66K_COMPLEMENTARY_BACKUP_READINESS_EXPANSION",
        "status": "STAGE66K_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "generated_utc": generated_utc,
        "root": str(root),
        "config": str(config_path),
        "input_paths": {
            "stage66j_summary_path": str(stage66j_path.relative_to(root)) if stage66j_path.is_relative_to(root) else str(stage66j_path),
            "stage66d_summary_path": str(stage66d_path.relative_to(root)) if stage66d_path.is_relative_to(root) else str(stage66d_path),
            "macro_dataset_path": str(macro_path.relative_to(root)) if macro_path.is_relative_to(root) else str(macro_path),
        },
        "input_hashes": {
            "config_sha256": sha256_file(config_path),
            "stage66j_summary_sha256": sha256_file(stage66j_path),
            "stage66d_summary_sha256": sha256_file(stage66d_path),
            "macro_dataset_sha256": sha256_file(macro_path),
        },
        "input_gate": {
            "stage66j_decision": stage66j.get("decision") if stage66j else None,
            "stage66d_decision": stage66d.get("decision") if stage66d else None,
            "stage66j_allowed": bool(stage66j and stage66j.get("decision") in config.get("allowed_stage66j_decisions", [])),
            "stage66d_allowed": bool(stage66d and stage66d.get("decision") == config.get("required_stage66d_decision")),
        },
        "macro_info": {
            "macro_rows": macro_rows,
            "macro_date_column": date_col,
            "latest_feature_date": latest_feature_date,
            "macro_latest_lag_days": macro_lag_days,
            "macro_freshness_gate": macro_freshness_gate,
        },
        "backup_counts": {
            "configured_backup_count": len(config["candidate_policy"]["selected_backup_candidates"]),
            "ready_backup_count": ready_count,
            "active_backup_count": active_count,
        },
        "backup_readiness": backup_items,
        "issues": issues,
        "outputs": {
            "summary_json": str((out_dir / "stage66k_complementary_backup_readiness_expansion_summary.json").relative_to(root)) if (out_dir / "stage66k_complementary_backup_readiness_expansion_summary.json").is_relative_to(root) else str(out_dir / "stage66k_complementary_backup_readiness_expansion_summary.json"),
            "report_md": str((out_dir / "stage66k_complementary_backup_readiness_expansion_report.md").relative_to(root)) if (out_dir / "stage66k_complementary_backup_readiness_expansion_report.md").is_relative_to(root) else str(out_dir / "stage66k_complementary_backup_readiness_expansion_report.md"),
            "rule_locks_json": config["outputs"]["rule_locks_json"] if not issues else None,
            "ledger_csv": config["outputs"]["ledger_csv"],
        },
        "next_step": "If WAIT, add Stage66K collection to daily ops and continue readiness. If backup signal active, build Stage66L no-broker dry-run ticket generator for the active backup rule. No order path is authorized by Stage66K.",
        "hard_blocks": config["hard_blocks"],
    }

    write_json(out_dir / "stage66k_complementary_backup_readiness_expansion_summary.json", summary)
    (out_dir / "stage66k_complementary_backup_readiness_expansion_report.md").write_text(render_report(summary), encoding="utf-8")
    append_ledger(root / config["outputs"]["ledger_csv"], summary)

    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "decision": summary["decision"],
        "classification": summary["classification"],
        "active_backup_count": active_count,
        "ready_backup_count": ready_count,
    }, indent=2))
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
