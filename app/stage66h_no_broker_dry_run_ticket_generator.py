#!/usr/bin/env python3
"""Stage66H no-broker dry-run paper-order ticket generator.

This script is intentionally non-executing. It never connects to a broker, never
places an order, and never authorizes paper/live trading. It converts the
Stage66G readiness design into either:
  * WAIT_FOR_FRESH_H64L_V2_SIGNAL_NO_DRY_RUN_TICKET, or
  * DRY_RUN_TICKET_READY_NO_BROKER_NO_ORDER.

The generated ticket, when present, is only a manual review artifact.
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

STAGE = "Stage66H_NO_BROKER_DRY_RUN_TICKET_GENERATOR"
UTC = dt.timezone.utc

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE66H",
    "NO_THRESHOLD_TUNING",
    "NO_PROMOTION_FROM_DRY_RUN_TICKET_ONLY",
]

DEFAULT_H64L_V2_CONDITIONS = [
    {"field": "gold_sma20_over_50", "operator": ">", "threshold": 0.0},
    {"field": "dxy_ret_20d", "operator": "<", "threshold": 0.0},
    {"field": "real_yield_change_20d", "operator": "<", "threshold": 0.0},
    {"field": "etf_flow_tonnes_3m", "operator": ">", "threshold": 0.0},
    {"field": "central_bank_demand_tonnes_3m", "operator": ">", "threshold": 0.0},
    {"field": "gold_sma50_over_200", "operator": ">", "threshold": 0.0},
]


def utc_now_iso() -> str:
    return dt.datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_date(value: Any) -> Optional[dt.datetime]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    # Normalize common suffixes and formats.
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    for candidate in (text, text.replace(" ", "T")):
        try:
            parsed = dt.datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            pass
    # Date-only fallback.
    try:
        d = dt.date.fromisoformat(str(value)[:10])
        return dt.datetime(d.year, d.month, d.day, tzinfo=UTC)
    except ValueError:
        return None


def date_key(value: Any) -> Optional[dt.date]:
    parsed = parse_date(value)
    return parsed.date() if parsed else None


def as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "none", "null"}:
        return None
    try:
        val = float(text)
    except ValueError:
        return None
    if math.isnan(val) or math.isinf(val):
        return None
    return val


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def resolve_path(root: Path, maybe_relative: str) -> Path:
    p = Path(maybe_relative)
    return p if p.is_absolute() else root / p


def choose_latest_macro_row(rows: List[Dict[str, str]], date_columns: Iterable[str]) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    best_row: Optional[Dict[str, str]] = None
    best_dt: Optional[dt.datetime] = None
    best_col: Optional[str] = None
    for row in rows:
        for col in date_columns:
            if col in row:
                parsed = parse_date(row.get(col))
                if parsed and (best_dt is None or parsed > best_dt):
                    best_dt = parsed
                    best_row = row
                    best_col = col
                break
    return best_row, best_col


def extract_conditions(rule_payload: Dict[str, Any], config: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates = []
    for key in ("conditions", "rule_conditions", "locked_conditions"):
        value = rule_payload.get(key)
        if isinstance(value, list):
            candidates = value
            break
    if not candidates and isinstance(rule_payload.get("rule"), dict):
        for key in ("conditions", "rule_conditions", "locked_conditions"):
            value = rule_payload["rule"].get(key)
            if isinstance(value, list):
                candidates = value
                break
    if not candidates:
        value = config.get("h64l_v2_conditions")
        if isinstance(value, list):
            candidates = value
    if not candidates:
        candidates = DEFAULT_H64L_V2_CONDITIONS
    normalized: List[Dict[str, Any]] = []
    for cond in candidates:
        if not isinstance(cond, dict):
            continue
        field = cond.get("field")
        op = cond.get("operator")
        threshold = cond.get("threshold")
        if field is None or op is None or threshold is None:
            continue
        normalized.append({"field": str(field), "operator": str(op), "threshold": float(threshold)})
    return normalized


def eval_condition(row: Dict[str, str], cond: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    field = cond["field"]
    op = cond["operator"]
    threshold = float(cond["threshold"])
    value = as_float(row.get(field))
    ok = False
    if value is not None:
        if op == ">":
            ok = value > threshold
        elif op == ">=":
            ok = value >= threshold
        elif op == "<":
            ok = value < threshold
        elif op == "<=":
            ok = value <= threshold
        elif op in {"==", "="}:
            ok = value == threshold
        else:
            ok = False
    return ok, {"field": field, "operator": op, "threshold": threshold, "value": value, "ok": ok}


def evaluate_signal(row: Optional[Dict[str, str]], conditions: List[Dict[str, Any]]) -> Dict[str, Any]:
    if row is None:
        return {"signal_active": False, "condition_results": [], "rule_failures": ["NO_MACRO_ROW"]}
    results = []
    failures = []
    for cond in conditions:
        ok, detail = eval_condition(row, cond)
        results.append(detail)
        if not ok:
            failures.append(f"{detail['field']}:{detail['value']}{detail['operator']}{detail['threshold']}")
    return {"signal_active": len(failures) == 0, "condition_results": results, "rule_failures": failures}


def first_external_row_on_or_after(rows: List[Dict[str, str]], target: dt.date, date_col: str) -> Optional[Dict[str, str]]:
    candidates: List[Tuple[dt.date, Dict[str, str]]] = []
    for row in rows:
        d = date_key(row.get(date_col))
        if d and d >= target:
            candidates.append((d, row))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def horizon_row(rows: List[Dict[str, str]], entry_date: dt.date, date_col: str, horizon_trading_days: int) -> Optional[Dict[str, str]]:
    ordered: List[Tuple[dt.date, Dict[str, str]]] = []
    for row in rows:
        d = date_key(row.get(date_col))
        if d and d >= entry_date:
            ordered.append((d, row))
    ordered.sort(key=lambda x: x[0])
    if len(ordered) <= horizon_trading_days:
        return None
    return ordered[horizon_trading_days][1]


def render_report(summary: Dict[str, Any], ticket: Optional[Dict[str, Any]]) -> str:
    lines = [
        "# Stage66H No-Broker Dry-Run Paper-Order Ticket Generator",
        "",
        "## Decision",
        "",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- classification: `{summary['classification']}`",
        "",
        "## Signal evaluation",
        "",
        "```json",
        json.dumps(summary["signal_evaluation"], indent=2, ensure_ascii=False, sort_keys=True),
        "```",
        "",
        "## Readiness gate",
        "",
        "```json",
        json.dumps(summary["readiness_gate"], indent=2, ensure_ascii=False, sort_keys=True),
        "```",
        "",
        "## Ticket output",
        "",
    ]
    if ticket:
        lines.extend(["```json", json.dumps(ticket, indent=2, ensure_ascii=False, sort_keys=True), "```", ""])
    else:
        lines.extend(["No dry-run ticket was generated because the active-signal gate is not satisfied.", ""])
    lines.extend(["## Hard blocks", ""])
    for block in HARD_BLOCKS:
        lines.append(f"- `{block}`")
    lines.append("")
    return "\n".join(lines)


def build_ticket(
    *,
    summary: Dict[str, Any],
    latest_row: Dict[str, str],
    entry_row: Dict[str, str],
    planned_exit_row: Optional[Dict[str, str]],
    external_date_col: str,
    config: Dict[str, Any],
    stage66g: Dict[str, Any],
) -> Dict[str, Any]:
    entry_close = as_float(entry_row.get("close"))
    if entry_close is None:
        raise ValueError("External D1 entry close is missing or non-numeric")
    initial_fraction = float(stage66g.get("readiness_design", {}).get("initial_notional_fraction", config.get("initial_notional_fraction", 0.05)))
    max_fraction = float(stage66g.get("readiness_design", {}).get("max_notional_fraction_before_new_forward_evidence", config.get("max_notional_fraction_before_new_forward_evidence", 0.10)))
    initial_fraction = min(initial_fraction, float(config.get("hard_max_initial_notional_fraction", 0.05)))
    max_fraction = min(max_fraction, float(config.get("hard_max_notional_fraction_before_new_forward_evidence", 0.10)))
    entry_date = date_key(entry_row.get(external_date_col))
    planned_exit_date = date_key(planned_exit_row.get(external_date_col)) if planned_exit_row else None
    return {
        "ticket_type": "DRY_RUN_NO_BROKER_PAPER_ORDER_TICKET",
        "ticket_status": "READY_FOR_MANUAL_REVIEW_ONLY_NO_ORDER",
        "created_utc": summary["generated_utc"],
        "hypothesis_id": config.get("hypothesis_id", "H64L_H1_FULL_MACRO_TAILWIND_LONG"),
        "rule_lock_path": config.get("rule_lock_path"),
        "side": "BUY_XAUUSD_REFERENCE_ONLY",
        "symbol": config.get("symbol", "XAUUSD"),
        "entry_reference": {
            "source": "external_d1_reference_close_no_broker",
            "date": entry_date.isoformat() if entry_date else None,
            "close": entry_close,
        },
        "planned_exit_reference": {
            "rule": f"fixed_{int(config.get('holding_period_trading_days', 120))}_trading_day_horizon",
            "date": planned_exit_date.isoformat() if planned_exit_date else None,
            "known_now": planned_exit_row is not None,
        },
        "sizing_design": {
            "initial_band": stage66g.get("readiness_design", {}).get("initial_band", "B_conservative"),
            "initial_notional_fraction": initial_fraction,
            "max_notional_fraction_before_new_forward_evidence": max_fraction,
            "fraction_basis": "fraction_of_target_paper_notional_not_real_capital",
        },
        "risk_controls": {
            "stop_after_first_adverse_move_bps": float(config.get("stop_after_first_adverse_move_bps", -1200.0)),
            "manual_user_authorization_required_before_any_real_paper_order": True,
            "event_calendar_forward_only_annotation_required": True,
            "no_historical_event_filtering": True,
            "fresh_h64l_v2_signal_required": True,
            "stop_after_data_or_rule_mismatch": True,
        },
        "non_execution_guards": {
            "broker_connection_authorized": False,
            "paper_order_is_authorized": False,
            "automated_order_authorized": False,
            "ea_promotion_authorized": False,
            "paper_live_or_live_authorized": False,
            "this_ticket_is_not_an_order": True,
        },
        "latest_feature_row": {
            "feature_date_utc": latest_row.get("feature_date_utc"),
            "sample_available_after_utc": latest_row.get("sample_available_after_utc"),
        },
    }


def run(root: Path, config_path: Path, out_dir: Path) -> Dict[str, Any]:
    config = load_json(config_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    stage66g_path = resolve_path(root, config["stage66g_summary_path"])
    macro_path = resolve_path(root, config["macro_dataset_path"])
    external_path = resolve_path(root, config["external_d1_path"])
    rule_path = resolve_path(root, config["rule_lock_path"])

    issues: List[str] = []
    if not stage66g_path.exists():
        issues.append(f"MISSING_STAGE66G_SUMMARY:{stage66g_path}")
    if not macro_path.exists():
        issues.append(f"MISSING_MACRO_DATASET:{macro_path}")
    if not external_path.exists():
        issues.append(f"MISSING_EXTERNAL_D1:{external_path}")
    if not rule_path.exists():
        issues.append(f"MISSING_RULE_LOCK:{rule_path}")

    stage66g = load_json(stage66g_path) if stage66g_path.exists() else {}
    rule_payload = load_json(rule_path) if rule_path.exists() else {}
    macro_rows = read_csv_rows(macro_path) if macro_path.exists() else []
    external_rows = read_csv_rows(external_path) if external_path.exists() else []

    latest_row, macro_date_col = choose_latest_macro_row(macro_rows, config.get("macro_date_columns", ["feature_date_utc", "date", "utc_time"]))
    conditions = extract_conditions(rule_payload, config)
    signal_eval = evaluate_signal(latest_row, conditions)

    now = dt.datetime.now(UTC)
    latest_dt = parse_date(latest_row.get(macro_date_col)) if latest_row and macro_date_col else None
    latest_lag_days = (now.date() - latest_dt.date()).days if latest_dt else None
    sample_available_after = parse_date(latest_row.get("sample_available_after_utc")) if latest_row else None
    sample_available_gate = bool(sample_available_after and sample_available_after <= now)
    freshness_gate = bool(latest_lag_days is not None and latest_lag_days <= int(config.get("macro_max_calendar_lag_days", 7)))

    expected_g_decision = config.get("required_stage66g_decision", "CONTROLLED_PAPER_ORDER_READINESS_DESIGN_BAND_B_NO_ORDER")
    g_decision_ok = stage66g.get("decision") == expected_g_decision
    g_class_ok = stage66g.get("classification") in set(config.get("allowed_stage66g_classifications", ["G_PASS_FAST_DESIGN_READY"]))
    g_no_order_ok = not bool(stage66g.get("readiness_design", {}).get("paper_order_is_authorized", False))
    g_no_broker_ok = not bool(stage66g.get("readiness_design", {}).get("broker_connection_authorized", False))
    g_no_live_ok = not bool(stage66g.get("readiness_design", {}).get("live_or_paper_live_authorized", False))

    readiness_gate = {
        "stage66g_decision_ok": g_decision_ok,
        "stage66g_class_ok": g_class_ok,
        "stage66g_no_order_ok": g_no_order_ok,
        "stage66g_no_broker_ok": g_no_broker_ok,
        "stage66g_no_live_ok": g_no_live_ok,
        "macro_latest_lag_days": latest_lag_days,
        "macro_freshness_gate": freshness_gate,
        "sample_available_after_gate": sample_available_gate,
        "h64l_v2_signal_active": signal_eval["signal_active"],
        "input_issues": issues,
    }

    generated_utc = utc_now_iso()
    summary: Dict[str, Any] = {
        "stage": STAGE,
        "status": "STAGE66H_COMPLETE_NO_PROMOTION",
        "generated_utc": generated_utc,
        "root": str(root),
        "config": str(config_path),
        "hard_blocks": HARD_BLOCKS,
        "input_paths": {
            "stage66g_summary_path": str(stage66g_path.relative_to(root) if stage66g_path.is_relative_to(root) else stage66g_path),
            "macro_dataset_path": str(macro_path.relative_to(root) if macro_path.is_relative_to(root) else macro_path),
            "external_d1_path": str(external_path.relative_to(root) if external_path.is_relative_to(root) else external_path),
            "rule_lock_path": str(rule_path.relative_to(root) if rule_path.is_relative_to(root) else rule_path),
        },
        "input_hashes": {
            "stage66g_summary_sha256": sha256_file(stage66g_path),
            "macro_dataset_sha256": sha256_file(macro_path),
            "external_d1_sha256": sha256_file(external_path),
            "rule_lock_sha256": sha256_file(rule_path),
        },
        "rule": {
            "condition_count": len(conditions),
            "conditions": conditions,
        },
        "signal_evaluation": {
            "macro_date_column": macro_date_col,
            "feature_date_utc": latest_row.get("feature_date_utc") if latest_row else None,
            "sample_available_after_utc": latest_row.get("sample_available_after_utc") if latest_row else None,
            "signal_active": signal_eval["signal_active"],
            "condition_results": signal_eval["condition_results"],
            "rule_failures": signal_eval["rule_failures"],
        },
        "readiness_gate": readiness_gate,
        "ticket_path": None,
        "report_md": str((out_dir / "stage66h_no_broker_dry_run_ticket_generator_report.md").relative_to(root) if (out_dir / "stage66h_no_broker_dry_run_ticket_generator_report.md").is_relative_to(root) else out_dir / "stage66h_no_broker_dry_run_ticket_generator_report.md"),
        "summary_json": str((out_dir / "stage66h_no_broker_dry_run_ticket_generator_summary.json").relative_to(root) if (out_dir / "stage66h_no_broker_dry_run_ticket_generator_summary.json").is_relative_to(root) else out_dir / "stage66h_no_broker_dry_run_ticket_generator_summary.json"),
        "next_step": "If WAIT, continue Stage65/Stage66H daily checks until a fresh H64L v2 signal is active. If DRY_RUN_TICKET_READY, manually review the ticket; real paper order still requires a later explicit authorization package.",
    }

    ticket: Optional[Dict[str, Any]] = None
    if issues:
        summary["decision"] = "STOP_FIX_STAGE66H_INPUTS_NO_TICKET"
        summary["classification"] = "H_KILL_INPUTS_MISSING"
    elif not (g_decision_ok and g_class_ok and g_no_order_ok and g_no_broker_ok and g_no_live_ok):
        summary["decision"] = "STOP_STAGE66G_READINESS_GATE_NOT_VALID_NO_TICKET"
        summary["classification"] = "H_KILL_READINESS_GATE"
    elif not (freshness_gate and sample_available_gate):
        summary["decision"] = "WAIT_FOR_FRESH_MACRO_DATA_NO_DRY_RUN_TICKET"
        summary["classification"] = "H_WAIT_DATA_FRESHNESS"
    elif not signal_eval["signal_active"]:
        summary["decision"] = "WAIT_FOR_FRESH_H64L_V2_SIGNAL_NO_DRY_RUN_TICKET"
        summary["classification"] = "H_WAIT_SIGNAL_INACTIVE"
    else:
        external_date_col = config.get("external_date_column", "date_utc")
        target_dt = sample_available_after or latest_dt
        assert latest_row is not None and target_dt is not None
        entry_delay = int(config.get("entry_delay_trading_days", 0))
        target_date = target_dt.date()
        if entry_delay > 0:
            # Delay by available trading rows rather than calendar days.
            start_row = first_external_row_on_or_after(external_rows, target_date, external_date_col)
            if start_row:
                sorted_rows = sorted(
                    [(date_key(r.get(external_date_col)), r) for r in external_rows if date_key(r.get(external_date_col)) and date_key(r.get(external_date_col)) >= date_key(start_row.get(external_date_col))],
                    key=lambda x: x[0],
                )
                if len(sorted_rows) > entry_delay:
                    target_date = sorted_rows[entry_delay][0]
        entry_row = first_external_row_on_or_after(external_rows, target_date, external_date_col)
        if entry_row is None:
            summary["decision"] = "WAIT_FOR_EXTERNAL_D1_ENTRY_REFERENCE_NO_DRY_RUN_TICKET"
            summary["classification"] = "H_WAIT_EXTERNAL_ENTRY"
        else:
            entry_date = date_key(entry_row.get(external_date_col))
            planned_exit = horizon_row(external_rows, entry_date, external_date_col, int(config.get("holding_period_trading_days", 120))) if entry_date else None
            ticket = build_ticket(
                summary=summary,
                latest_row=latest_row,
                entry_row=entry_row,
                planned_exit_row=planned_exit,
                external_date_col=external_date_col,
                config=config,
                stage66g=stage66g,
            )
            ticket_path = out_dir / "stage66h_no_broker_dry_run_ticket.json"
            write_json(ticket_path, ticket)
            summary["ticket_path"] = str(ticket_path.relative_to(root) if ticket_path.is_relative_to(root) else ticket_path)
            summary["decision"] = "DRY_RUN_TICKET_READY_NO_BROKER_NO_ORDER"
            summary["classification"] = "H_PASS_DRY_RUN_TICKET_READY"

    summary_path = out_dir / "stage66h_no_broker_dry_run_ticket_generator_summary.json"
    report_path = out_dir / "stage66h_no_broker_dry_run_ticket_generator_report.md"
    write_json(summary_path, summary)
    report_path.write_text(render_report(summary, ticket), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage66H no-broker dry-run paper-order ticket generator")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--config", default="configs/stage66h_no_broker_dry_run_ticket_generator.json")
    parser.add_argument("--out", default="reports/stage66h_no_broker_dry_run_ticket_generator")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    config_path = resolve_path(root, args.config)
    out_dir = resolve_path(root, args.out)
    summary = run(root, config_path, out_dir)
    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "decision": summary["decision"],
        "classification": summary["classification"],
        "ticket_path": summary.get("ticket_path"),
    }, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
