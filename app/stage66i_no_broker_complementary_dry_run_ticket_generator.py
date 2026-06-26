#!/usr/bin/env python3
"""
Stage66I no-broker complementary dry-run paper-order ticket generator.

This stage reads the Stage66E-selected complementary rule lock and evaluates the latest
macro feature row. If the locked complementary signal is inactive, it emits WAIT and no
ticket. If active, it emits a dry-run ticket for manual review only.

Hard policy: no broker, no automated order, no EA promotion, no paper-live, no live.
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
    "NO_BROKER_CONNECTION",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE66I",
    "NO_THRESHOLD_TUNING",
    "NO_PROMOTION_FROM_DRY_RUN_TICKET_ONLY",
]


ALLOWED_STAGE66E_DECISIONS = {
    "STAGE66E_PASS_FAST_COMPLEMENTARY_RULE_LOCK_READY_WAIT_SIGNAL_NO_ORDER",
    "STAGE66E_PASS_FAST_COMPLEMENTARY_RULE_LOCK_READY_SIGNAL_ACTIVE_NO_ORDER",
}


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_utc_now() -> str:
    return utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def parse_date_like(value: str) -> Optional[dt.datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # Normalize simple YYYY-MM-DD as UTC midnight.
    try:
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            return dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc)
        parsed = dt.datetime.fromisoformat(s)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        return None


def detect_date_column(headers: List[str], preferred: Optional[str] = None) -> str:
    if preferred and preferred in headers:
        return preferred
    candidates = [
        "feature_date_utc",
        "date_utc",
        "time_utc",
        "utc_time",
        "date",
    ]
    for c in candidates:
        if c in headers:
            return c
    raise ValueError(f"Could not detect date column in headers: {headers}")


def read_latest_csv_row(path: Path, preferred_date_column: Optional[str] = None) -> Tuple[Dict[str, str], str, int]:
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")

    latest_row: Optional[Dict[str, str]] = None
    latest_dt: Optional[dt.datetime] = None
    row_count = 0
    date_col = ""

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {path}")
        date_col = detect_date_column(reader.fieldnames, preferred_date_column)
        for row in reader:
            row_count += 1
            parsed = parse_date_like(row.get(date_col, ""))
            if parsed is None:
                continue
            if latest_dt is None or parsed > latest_dt:
                latest_dt = parsed
                latest_row = row

    if latest_row is None:
        raise ValueError(f"No parseable dated rows found in: {path}")

    return latest_row, date_col, row_count


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        x = float(str(value).strip())
    except Exception:
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def compare(value: float, operator: str, threshold: float) -> bool:
    if operator == ">":
        return value > threshold
    if operator == ">=":
        return value >= threshold
    if operator == "<":
        return value < threshold
    if operator == "<=":
        return value <= threshold
    if operator == "==":
        return value == threshold
    raise ValueError(f"Unsupported operator: {operator}")


def evaluate_rule(row: Dict[str, str], rule: Dict[str, Any]) -> Dict[str, Any]:
    condition_results: List[Dict[str, Any]] = []
    failures: List[str] = []

    for cond in rule.get("conditions", []):
        field = cond["field"]
        op = cond["operator"]
        threshold = float(cond.get("threshold", 0.0))
        value = to_float(row.get(field))
        ok = value is not None and compare(value, op, threshold)
        condition_results.append({
            "field": field,
            "operator": op,
            "threshold": threshold,
            "value": value,
            "ok": bool(ok),
        })
        if not ok:
            failures.append(f"{field}:{value}{op}{threshold}")

    return {
        "signal_active": bool(condition_results) and all(c["ok"] for c in condition_results),
        "condition_results": condition_results,
        "rule_failures": failures,
    }


def find_external_entry_reference(
    external_path: Path,
    sample_available_after_utc: Optional[str],
    preferred_date_column: Optional[str],
) -> Dict[str, Any]:
    if not external_path.exists():
        return {"available": False, "issue": f"external_d1_missing:{external_path}"}

    sample_dt = parse_date_like(sample_available_after_utc or "")
    if sample_dt is None:
        return {"available": False, "issue": "sample_available_after_utc_not_parseable"}

    with external_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return {"available": False, "issue": "external_d1_no_header"}
        date_col = detect_date_column(reader.fieldnames, preferred_date_column)
        best_row = None
        best_dt = None
        for row in reader:
            parsed = parse_date_like(row.get(date_col, ""))
            if parsed is None:
                continue
            if parsed >= sample_dt and (best_dt is None or parsed < best_dt):
                best_dt = parsed
                best_row = row

    if best_row is None or best_dt is None:
        return {"available": False, "issue": "no_external_row_on_or_after_sample_available_after_utc"}

    return {
        "available": True,
        "date_column": date_col,
        "entry_reference_date_utc": best_dt.date().isoformat(),
        "entry_reference_close": to_float(best_row.get("close")),
        "entry_reference_open": to_float(best_row.get("open")),
        "entry_reference_high": to_float(best_row.get("high")),
        "entry_reference_low": to_float(best_row.get("low")),
        "source": best_row.get("source"),
        "note": "Reference only; no broker order is authorized.",
    }


def load_config(root: Path, config_path: Path) -> Dict[str, Any]:
    cfg = read_json(config_path)
    # Default paths are relative to root.
    defaults = {
        "stage66e_summary_path": "reports/stage66e_complementary_shortlist_audit/stage66e_complementary_shortlist_audit_summary.json",
        "rule_lock_path": "configs/stage66e_selected_complementary_rule_lock.json",
        "macro_dataset_path": "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
        "external_d1_path": "data/macro_regime/raw/broker_or_spot_gold_d1_ohlc_2011_present.csv",
        "macro_date_column": "feature_date_utc",
        "external_date_column": "date_utc",
        "macro_freshness_max_calendar_lag_days": 7,
        "initial_manual_paper_order_fraction_reference": 0.05,
        "max_manual_paper_order_fraction_before_new_forward_evidence": 0.10,
        "stop_after_first_adverse_move_bps_reference": -1200.0,
        "ticket_side": "LONG",
        "ticket_type": "DRY_RUN_REVIEW_ONLY",
    }
    for k, v in defaults.items():
        cfg.setdefault(k, v)
    return cfg


def rel_or_abs(root: Path, p: str) -> Path:
    pp = Path(p)
    return pp if pp.is_absolute() else root / pp


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--config", required=True, help="Config JSON")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--write-ticket", action="store_true", default=True)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    config_path = rel_or_abs(root, args.config)
    out_dir = rel_or_abs(root, args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = load_config(root, config_path)

    stage66e_path = rel_or_abs(root, cfg["stage66e_summary_path"])
    rule_path = rel_or_abs(root, cfg["rule_lock_path"])
    macro_path = rel_or_abs(root, cfg["macro_dataset_path"])
    external_path = rel_or_abs(root, cfg["external_d1_path"])

    issues: List[str] = []
    stage66e = {}
    rule = {}

    try:
        stage66e = read_json(stage66e_path)
    except Exception as exc:
        issues.append(f"stage66e_summary_read_failed:{exc}")

    try:
        rule = read_json(rule_path)
    except Exception as exc:
        issues.append(f"rule_lock_read_failed:{exc}")

    latest_row: Dict[str, str] = {}
    macro_date_column = ""
    macro_rows = 0
    try:
        latest_row, macro_date_column, macro_rows = read_latest_csv_row(macro_path, cfg.get("macro_date_column"))
    except Exception as exc:
        issues.append(f"macro_dataset_read_failed:{exc}")

    stage66e_decision = stage66e.get("decision")
    stage66e_classification = stage66e.get("classification")
    stage66e_gate_ok = stage66e_decision in ALLOWED_STAGE66E_DECISIONS

    eval_result: Dict[str, Any] = {
        "signal_active": False,
        "condition_results": [],
        "rule_failures": [],
    }
    latest_feature_date = latest_row.get(macro_date_column) if latest_row else None
    sample_available_after = latest_row.get("sample_available_after_utc") if latest_row else None

    if latest_row and rule:
        eval_result = evaluate_rule(latest_row, rule)

    feature_dt = parse_date_like(latest_feature_date or "")
    now = utc_now()
    macro_lag_days = None
    if feature_dt is not None:
        macro_lag_days = max(0, (now.date() - feature_dt.date()).days)

    macro_freshness_gate = macro_lag_days is not None and macro_lag_days <= int(cfg["macro_freshness_max_calendar_lag_days"])
    sample_after_dt = parse_date_like(sample_available_after or "")
    sample_available_after_gate = sample_after_dt is not None and sample_after_dt <= now

    entry_ref = {}
    ticket_path: Optional[str] = None
    dry_run_ticket: Optional[Dict[str, Any]] = None

    base_gate_ok = (
        not issues
        and stage66e_gate_ok
        and macro_freshness_gate
        and sample_available_after_gate
        and bool(rule)
    )

    signal_active = bool(eval_result.get("signal_active"))

    if not base_gate_ok:
        decision = "BLOCKED_INPUT_OR_GOVERNANCE_GATE_NO_DRY_RUN_TICKET"
        classification = "I_BLOCKED_INPUT_OR_GOVERNANCE"
    elif not signal_active:
        decision = "WAIT_FOR_FRESH_COMPLEMENTARY_D3_H60_SIGNAL_NO_DRY_RUN_TICKET"
        classification = "I_WAIT_SIGNAL_INACTIVE"
    else:
        entry_ref = find_external_entry_reference(
            external_path,
            sample_available_after,
            cfg.get("external_date_column"),
        )
        if not entry_ref.get("available"):
            decision = "BLOCKED_MISSING_EXTERNAL_ENTRY_REFERENCE_NO_DRY_RUN_TICKET"
            classification = "I_BLOCKED_EXTERNAL_REFERENCE"
        else:
            decision = "COMPLEMENTARY_DRY_RUN_TICKET_READY_NO_BROKER_NO_ORDER"
            classification = "I_DRY_RUN_TICKET_READY"
            dry_run_ticket = {
                "ticket_type": cfg["ticket_type"],
                "generated_utc": iso_utc_now(),
                "source_stage": "Stage66I_NO_BROKER_COMPLEMENTARY_DRY_RUN_TICKET_GENERATOR",
                "rule_id": rule.get("rule_id"),
                "thesis_id": rule.get("thesis_id"),
                "horizon_trading_days": rule.get("horizon_trading_days"),
                "side": cfg["ticket_side"],
                "readiness_mode": "DRY_RUN_REVIEW_ONLY_NO_BROKER_NO_ORDER",
                "no_order_policy": "NO_ORDER_NO_BROKER_NO_EA_NO_PAPER_LIVE_NO_LIVE",
                "notional_fraction_reference": float(cfg["initial_manual_paper_order_fraction_reference"]),
                "max_notional_fraction_before_new_forward_evidence": float(cfg["max_manual_paper_order_fraction_before_new_forward_evidence"]),
                "stop_after_first_adverse_move_bps_reference": float(cfg["stop_after_first_adverse_move_bps_reference"]),
                "entry_rule": rule.get("entry_rule"),
                "exit_rule": rule.get("exit_rule"),
                "position_mode": rule.get("position_mode"),
                "cost_policy": rule.get("cost_policy", {}),
                "feature_date_utc": latest_feature_date,
                "sample_available_after_utc": sample_available_after,
                "signal_evaluation": eval_result,
                "entry_reference": entry_ref,
                "manual_review_required": True,
                "explicit_later_authorization_required_before_any_order": True,
                "hard_blocks": HARD_BLOCKS,
            }
            ticket_path_obj = out_dir / "stage66i_no_broker_complementary_dry_run_ticket.json"
            write_json(ticket_path_obj, dry_run_ticket)
            ticket_path = str(ticket_path_obj.relative_to(root)) if ticket_path_obj.is_relative_to(root) else str(ticket_path_obj)

    summary = {
        "stage": "Stage66I_NO_BROKER_COMPLEMENTARY_DRY_RUN_TICKET_GENERATOR",
        "status": "STAGE66I_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "generated_utc": iso_utc_now(),
        "root": str(root),
        "config": str(config_path),
        "input_paths": {
            "stage66e_summary_path": cfg["stage66e_summary_path"],
            "rule_lock_path": cfg["rule_lock_path"],
            "macro_dataset_path": cfg["macro_dataset_path"],
            "external_d1_path": cfg["external_d1_path"],
        },
        "input_hashes": {
            "config_sha256": sha256_file(config_path),
            "stage66e_summary_sha256": sha256_file(stage66e_path),
            "rule_lock_sha256": sha256_file(rule_path),
            "macro_dataset_sha256": sha256_file(macro_path),
            "external_d1_sha256": sha256_file(external_path),
        },
        "readiness_gate": {
            "input_issues": issues,
            "stage66e_decision": stage66e_decision,
            "stage66e_classification": stage66e_classification,
            "stage66e_gate_ok": stage66e_gate_ok,
            "macro_freshness_gate": macro_freshness_gate,
            "macro_latest_lag_days": macro_lag_days,
            "sample_available_after_gate": sample_available_after_gate,
            "complementary_signal_active": signal_active,
        },
        "macro_info": {
            "macro_date_column": macro_date_column,
            "macro_rows": macro_rows,
            "latest_feature_date": latest_feature_date,
            "sample_available_after_utc": sample_available_after,
        },
        "rule": {
            "rule_id": rule.get("rule_id"),
            "thesis_id": rule.get("thesis_id"),
            "horizon_trading_days": rule.get("horizon_trading_days"),
            "rule_sha256": rule.get("rule_sha256"),
            "conditions": rule.get("conditions", []),
        },
        "signal_evaluation": {
            **eval_result,
            "feature_date_utc": latest_feature_date,
            "sample_available_after_utc": sample_available_after,
            "macro_date_column": macro_date_column,
        },
        "ticket_path": ticket_path,
        "dry_run_ticket_generated": dry_run_ticket is not None,
        "next_step": (
            "If WAIT, continue daily Stage66H and Stage66I readiness checks. "
            "If DRY_RUN_TICKET_READY, manually review the dry-run ticket; real paper order still requires a later explicit authorization package."
        ),
        "hard_blocks": HARD_BLOCKS,
    }

    summary_path = out_dir / "stage66i_no_broker_complementary_dry_run_ticket_generator_summary.json"
    report_path = out_dir / "stage66i_no_broker_complementary_dry_run_ticket_generator_report.md"

    write_json(summary_path, summary)

    report_lines = [
        "# Stage66I No-Broker Complementary Dry-Run Ticket Generator",
        "",
        "## Decision",
        "",
        f"- status: `{summary['status']}`",
        f"- decision: `{decision}`",
        f"- classification: `{classification}`",
        "",
        "## Rule",
        "",
        "```json",
        json.dumps(summary["rule"], indent=2, sort_keys=True),
        "```",
        "",
        "## Readiness gate",
        "",
        "```json",
        json.dumps(summary["readiness_gate"], indent=2, sort_keys=True),
        "```",
        "",
        "## Signal evaluation",
        "",
        "```json",
        json.dumps(summary["signal_evaluation"], indent=2, sort_keys=True),
        "```",
        "",
        "## Ticket output",
        "",
    ]
    if dry_run_ticket is None:
        report_lines.append("No dry-run ticket was generated because a readiness or active-signal gate is not satisfied.")
    else:
        report_lines.append(f"Dry-run ticket generated at `{ticket_path}`. This is manual-review only and authorizes no order.")
    report_lines += [
        "",
        "## Hard blocks",
        "",
    ]
    report_lines += [f"- `{b}`" for b in HARD_BLOCKS]
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "decision": decision,
        "classification": classification,
        "summary_json": str(summary_path),
        "report_md": str(report_path),
        "ticket_path": ticket_path,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
