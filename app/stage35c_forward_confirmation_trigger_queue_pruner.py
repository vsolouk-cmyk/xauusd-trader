from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(".")
REPORT_DIR = ROOT / "data" / "reports" / "stage35c_forward_confirmation_trigger_queue_pruner"
STAGE35B_DIR = ROOT / "data" / "reports" / "stage35b_strict_variant_backtest_queue_evaluator"
STAGE33E_DIR = ROOT / "data" / "reports" / "stage33e_short_confirmation_recency_filter"
DEFAULT_LEDGER = ROOT / "data" / "reports" / "stage32c_dense_forward_shadow_tracker" / "dense_forward_signal_ledger.csv"

PRIMARY_VARIANT_ID = "stage35a_handoff_h13_h14_recency_guard_last5_recovery"
DEFAULT_INCLUDED_CANDIDATES = [
    "handoff_align_follow_h13_tp06_sl065",
    "handoff_align_follow_h14_tp06_sl065",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        f.write("\n")


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv_rows(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys: List[str] = []
        for r in rows:
            for k in r.keys():
                if k not in keys:
                    keys.append(k)
        fieldnames = keys or ["empty"]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})


def parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "nat"}:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # Common fallback without timezone.
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                dt = None  # type: ignore[assignment]
        if dt is None:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso_z(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def first_existing(row: Dict[str, Any], names: Iterable[str]) -> str:
    for name in names:
        if name in row and str(row.get(name, "")).strip():
            return str(row[name]).strip()
    return ""


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        s = str(value).strip()
        if not s or s.lower() in {"nan", "none"}:
            return default
        return float(s)
    except Exception:
        return default


def fmt_num(value: Any, digits: int = 6) -> Any:
    if isinstance(value, float):
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        if math.isnan(value):
            return "nan"
        return round(value, digits)
    return value


def compute_metrics(rows: List[Dict[str, Any]], cost_penalty_x4: float = 0.0) -> Dict[str, Any]:
    nets = [to_float(r.get("net_x4")) - cost_penalty_x4 for r in rows]
    n = len(nets)
    if n == 0:
        return {
            "signal_count": 0,
            "pf_x4": 0.0,
            "avg_net_x4": 0.0,
            "win_rate_x4": 0.0,
            "sum_net_x4": 0.0,
            "max_drawdown_x4": 0.0,
        }
    gross_profit = sum(x for x in nets if x > 0)
    gross_loss = abs(sum(x for x in nets if x < 0))
    if gross_loss == 0 and gross_profit > 0:
        pf = float("inf")
    elif gross_loss == 0:
        pf = 0.0
    else:
        pf = gross_profit / gross_loss
    avg = sum(nets) / n
    wr = sum(1 for x in nets if x > 0) / n
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for x in nets:
        cumulative += x
        peak = max(peak, cumulative)
        max_dd = min(max_dd, cumulative - peak)
    return {
        "signal_count": n,
        "pf_x4": pf,
        "avg_net_x4": avg,
        "win_rate_x4": wr,
        "sum_net_x4": sum(nets),
        "max_drawdown_x4": max_dd,
    }


def normalize_ledger_rows(raw_rows: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in raw_rows:
        candidate = first_existing(r, ["candidate", "candidate_id", "variant", "strategy_id"])
        family = first_existing(r, ["family", "target_family", "source_family"])
        ts_s = first_existing(r, ["entry_time", "entry_time_utc", "signal_ts_utc", "timestamp", "time", "datetime", "ts_utc"])
        ts = parse_dt(ts_s)
        net = first_existing(r, ["net_x4", "net", "outcome_net_x4", "ret_x4"])
        direction = first_existing(r, ["direction", "side"])
        if not candidate or ts is None:
            continue
        out.append({
            "candidate": candidate,
            "family": family,
            "entry_time": iso_z(ts),
            "entry_dt": ts,
            "direction": direction,
            "net_x4": to_float(net),
        })
    out.sort(key=lambda x: (x["entry_dt"], x["candidate"]))
    return out


def markdown_table(rows: List[Dict[str, Any]], columns: List[str]) -> str:
    if not rows:
        return "No rows."
    lines = []
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("| " + " | ".join(["---"] * len(columns)) + " |")
    for r in rows:
        vals = []
        for c in columns:
            v = r.get(c, "")
            if isinstance(v, float):
                v = fmt_num(v)
            vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def load_anchor_and_candidates() -> Tuple[Optional[datetime], List[str], int, int]:
    s33e = read_json(STAGE33E_DIR / "stage33e_summary.json")
    anchor = parse_dt(s33e.get("last_effective_event_ts"))
    included = s33e.get("included_candidates") or DEFAULT_INCLUDED_CANDIDATES
    if not isinstance(included, list):
        included = DEFAULT_INCLUDED_CANDIDATES
    min_new = int(s33e.get("short_confirmation_min_new_events", 5) or 5)
    target_new = int(s33e.get("short_confirmation_target_new_events", 10) or 10)
    return anchor, [str(x) for x in included], min_new, target_new


def classify_confirmation(new_rows: List[Dict[str, Any]], min_new: int, target_new: int) -> Tuple[str, str, Dict[str, Any], List[Dict[str, Any]]]:
    metrics = compute_metrics(new_rows)
    cost1 = compute_metrics(new_rows, cost_penalty_x4=1.0)
    n = metrics["signal_count"]
    gates = [
        {"gate": "new_signal_count", "value": n, "threshold": f">= {min_new}", "passed": n >= min_new, "severity": "fatal"},
        {"gate": "confirmation_pf", "value": fmt_num(metrics["pf_x4"]), "threshold": ">= 1.25", "passed": metrics["pf_x4"] >= 1.25, "severity": "fatal"},
        {"gate": "confirmation_avg", "value": fmt_num(metrics["avg_net_x4"]), "threshold": ">= 0.0", "passed": metrics["avg_net_x4"] >= 0.0, "severity": "fatal"},
        {"gate": "confirmation_win_rate", "value": fmt_num(metrics["win_rate_x4"]), "threshold": ">= 0.55", "passed": metrics["win_rate_x4"] >= 0.55, "severity": "fatal"},
        {"gate": "confirmation_drawdown", "value": fmt_num(metrics["max_drawdown_x4"]), "threshold": ">= -15.0", "passed": metrics["max_drawdown_x4"] >= -15.0, "severity": "fatal"},
        {"gate": "cost1_pf", "value": fmt_num(cost1["pf_x4"]), "threshold": ">= 1.0", "passed": cost1["pf_x4"] >= 1.0, "severity": "warning"},
    ]
    if n < min_new:
        decision = "STAGE35C_WAIT_FOR_MORE_FORWARD_EVENTS_RESEARCH_ONLY"
        next_action = "KEEP_STAGE33E_STAGE35B_BACKGROUND_TRIGGER_ACTIVE"
    else:
        fatal_failures = [g for g in gates if g["severity"] == "fatal" and not g["passed"]]
        if fatal_failures:
            decision = "STAGE35C_FORWARD_CONFIRMATION_FAILED_KILL_OR_REPAIR_RESEARCH_ONLY"
            next_action = "KILL_OR_REPAIR_H13_H14_RECENCY_GUARD_DO_NOT_PROMOTE"
        else:
            decision = "STAGE35C_READY_TO_RERUN_STAGE33D_E_35B_RESEARCH_ONLY"
            next_action = "RERUN_STAGE33D_STAGE33E_STAGE35B_NOW"
    summary_metrics = {
        **{f"new_{k}": v for k, v in metrics.items()},
        "new_cost1_pf_x4": cost1["pf_x4"],
        "min_new_events": min_new,
        "target_new_events": target_new,
    }
    return decision, next_action, summary_metrics, gates


def build_queue_pruner(stage35b_dir: Path) -> List[Dict[str, Any]]:
    eval_rows = read_csv_rows(stage35b_dir / "strict_variant_evaluation.csv")
    if not eval_rows:
        # Safe fallback from known Stage35B rows.
        eval_rows = [
            {"priority": "1", "variant_id": PRIMARY_VARIANT_ID, "stage35b_decision": "PENDING_FORWARD_CONFIRMATION_RESEARCH_ONLY", "next_action": "COLLECT_NEW_EVENTS_THEN_RERUN_STAGE35B"},
            {"priority": "2", "variant_id": "stage35a_handoff_h13_h14_exclude_recent_degradation_diagnostic", "stage35b_decision": "DIAGNOSTIC_ONLY_NO_PROMOTION_RESEARCH_ONLY", "next_action": "DIAGNOSTIC_ONLY_NO_PROMOTION"},
            {"priority": "3", "variant_id": "stage35a_vol_trans_fade_h12_cost_tail_repair", "stage35b_decision": "ACCELERATION_PENDING_MORE_EVIDENCE_RESEARCH_ONLY", "next_action": "KEEP_CHEAP_BACKGROUND_COLLECTION_ONLY"},
            {"priority": "4", "variant_id": "stage35a_calendar_friday_hour_suppression_repair", "stage35b_decision": "KILL_OR_REPAIR_RESEARCH_ONLY", "next_action": "KILL_CALENDAR_FAST_PATH_REPAIR"},
            {"priority": "5", "variant_id": "stage35a_vol_trans_follow_inverted_diagnostic_only", "stage35b_decision": "DIAGNOSTIC_ONLY_NO_PROMOTION_RESEARCH_ONLY", "next_action": "OPTIONAL_DIAGNOSTIC_REPORT_ONLY"},
        ]
    out = []
    for r in eval_rows:
        vid = r.get("variant_id", "")
        d = r.get("stage35b_decision", "")
        if "PENDING_FORWARD" in d:
            lane = "PRIMARY_FORWARD_CONFIRMATION"
            enforced_action = "KEEP_TRIGGER_ACTIVE_UNTIL_MIN_NEW_EVENTS"
            promotion_allowed = False
        elif "ACCELERATION" in d:
            lane = "CHEAP_BACKGROUND_ACCELERATION"
            enforced_action = "BACKGROUND_ONLY_NO_PROMOTION"
            promotion_allowed = False
        elif "DIAGNOSTIC_ONLY" in d:
            lane = "DIAGNOSTIC_ONLY"
            enforced_action = "KEEP_OUT_OF_PROMOTION_QUEUE"
            promotion_allowed = False
        elif "KILL" in d or "REPAIR" in d:
            lane = "KILL_OR_REPAIR"
            enforced_action = "REMOVE_FROM_FAST_PATH"
            promotion_allowed = False
        else:
            lane = "UNKNOWN_REVIEW_REQUIRED"
            enforced_action = "MANUAL_REVIEW_RESEARCH_ONLY"
            promotion_allowed = False
        out.append({
            "priority": r.get("priority", ""),
            "variant_id": vid,
            "stage35b_decision": d,
            "lane": lane,
            "promotion_allowed": promotion_allowed,
            "enforced_action": enforced_action,
            "source_next_action": r.get("next_action", ""),
        })
    return out


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    generated_utc = utc_now()

    stage35b_summary = read_json(STAGE35B_DIR / "stage35b_summary.json")
    stage35b_decision = stage35b_summary.get("decision", "UNKNOWN")
    ledger_path = Path(stage35b_summary.get("ledger_path") or DEFAULT_LEDGER)
    if not ledger_path.is_absolute():
        ledger_path = ROOT / ledger_path

    anchor, included_candidates, min_new, target_new = load_anchor_and_candidates()
    raw_ledger = read_csv_rows(ledger_path)
    ledger = normalize_ledger_rows(raw_ledger)
    forward_rows = [r for r in ledger if r["candidate"] in set(included_candidates) and anchor is not None and r["entry_dt"] > anchor]
    all_included_rows = [r for r in ledger if r["candidate"] in set(included_candidates)]

    decision, next_action, forward_metrics, gate_rows = classify_confirmation(forward_rows, min_new, target_new)
    queue_rows = build_queue_pruner(STAGE35B_DIR)

    latest_forward_ts = max((r["entry_dt"] for r in forward_rows), default=None)
    earliest_forward_ts = min((r["entry_dt"] for r in forward_rows), default=None)

    forward_state = [{
        "variant_id": PRIMARY_VARIANT_ID,
        "included_candidates": ";".join(included_candidates),
        "anchor_ts": iso_z(anchor),
        "first_new_event_ts": iso_z(earliest_forward_ts),
        "latest_new_event_ts": iso_z(latest_forward_ts),
        "new_signal_count": forward_metrics["new_signal_count"],
        "min_new_events": min_new,
        "target_new_events": target_new,
        "new_pf_x4": fmt_num(forward_metrics["new_pf_x4"]),
        "new_avg_net_x4": fmt_num(forward_metrics["new_avg_net_x4"]),
        "new_win_rate_x4": fmt_num(forward_metrics["new_win_rate_x4"]),
        "new_max_drawdown_x4": fmt_num(forward_metrics["new_max_drawdown_x4"]),
        "new_cost1_pf_x4": fmt_num(forward_metrics["new_cost1_pf_x4"]),
        "stage35c_decision": decision,
        "next_action": next_action,
    }]

    rerun_plan = [{
        "priority": 1,
        "condition": f"new_signal_count >= {min_new} and confirmation gates pass",
        "action": "RERUN_STAGE33D_STAGE33E_STAGE35B",
        "command_1": "python3 -m app.stage33d_strict_cost_aware_pre_paper_gate",
        "command_2": "python3 -m app.stage33e_short_confirmation_recency_filter",
        "command_3": "python3 -m app.stage35b_strict_variant_backtest_queue_evaluator",
    }, {
        "priority": 2,
        "condition": f"new_signal_count < {min_new}",
        "action": "WAIT_WITH_SCHEDULER_BACKGROUND_ONLY_NO_NEW_ANALYSIS_STAGE",
        "command_1": "python3 -m app.stage35c_forward_confirmation_trigger_queue_pruner",
        "command_2": "",
        "command_3": "",
    }, {
        "priority": 3,
        "condition": f"new_signal_count >= {min_new} and confirmation gates fail",
        "action": "KILL_OR_REPAIR_H13_H14_FAST_PATH_AND_RETURN_TO_TARGETED_INTAKE",
        "command_1": "python3 -m app.stage34c_controlled_intake_expansion",
        "command_2": "",
        "command_3": "",
    }]

    summary = {
        "generated_utc": generated_utc,
        "decision": decision,
        "execution_status": "RESEARCH_ONLY",
        "commercial_transition_authorized": False,
        "no_ea_change": True,
        "no_paper_live": True,
        "no_order_authorization": True,
        "primary_objective": "FORWARD_CONFIRMATION_TRIGGER_AND_QUEUE_PRUNING_TO_AVOID_PASSIVE_WAITING",
        "recommended_next_stage": next_action,
        "stage35b_decision": stage35b_decision,
        "stage35b_summary_path": str(STAGE35B_DIR / "stage35b_summary.json"),
        "stage33e_summary_path": str(STAGE33E_DIR / "stage33e_summary.json"),
        "ledger_path": str(ledger_path),
        "ledger_available": ledger_path.exists(),
        "ledger_rows": len(raw_ledger),
        "normalized_ledger_rows": len(ledger),
        "included_candidates": included_candidates,
        "anchor_ts": iso_z(anchor),
        "new_signal_count": forward_metrics["new_signal_count"],
        "min_new_events": min_new,
        "target_new_events": target_new,
        "new_pf_x4": forward_metrics["new_pf_x4"],
        "new_avg_net_x4": forward_metrics["new_avg_net_x4"],
        "new_win_rate_x4": forward_metrics["new_win_rate_x4"],
        "new_max_drawdown_x4": forward_metrics["new_max_drawdown_x4"],
        "new_cost1_pf_x4": forward_metrics["new_cost1_pf_x4"],
        "queue_pruner_rows": len(queue_rows),
        "promotion_allowed_now": decision == "STAGE35C_READY_TO_RERUN_STAGE33D_E_35B_RESEARCH_ONLY",
    }

    write_json(REPORT_DIR / "stage35c_summary.json", summary)
    write_csv_rows(REPORT_DIR / "forward_confirmation_state.csv", forward_state)
    write_csv_rows(REPORT_DIR / "forward_confirmation_gate_checks.csv", gate_rows)
    write_csv_rows(REPORT_DIR / "queue_pruner.csv", queue_rows)
    write_csv_rows(REPORT_DIR / "rerun_trigger_plan.csv", rerun_plan)

    # Keep the actual forward rows for audit, without Python-only dt objects.
    audit_rows = []
    for r in forward_rows:
        audit_rows.append({k: v for k, v in r.items() if k != "entry_dt"})
    write_csv_rows(REPORT_DIR / "new_forward_events_audit.csv", audit_rows)

    md = f"""# XAUUSD Stage35C — Forward Confirmation Trigger & Queue Pruner
Generated UTC: {generated_utc}

## Decision

DECISION = {decision}
EXECUTION_STATUS = RESEARCH_ONLY
COMMERCIAL_TRANSITION_AUTHORIZED = False
NO_EA_CHANGE = True
NO_PAPER_LIVE = True
NO_ORDER_AUTHORIZATION = True
PRIMARY_OBJECTIVE = FORWARD_CONFIRMATION_TRIGGER_AND_QUEUE_PRUNING_TO_AVOID_PASSIVE_WAITING
RECOMMENDED_NEXT_STAGE = {next_action}

## Why this stage exists

Stage35B found no strict-review-ready variant. The main h13+h14 recency-guard path is pending forward confirmation. Stage35C prevents passive waiting by counting new forward events after the Stage33E anchor and pruning non-promotable queues.

## Summary

stage35b_decision = {stage35b_decision}
ledger_available = {ledger_path.exists()}
ledger_rows = {len(raw_ledger)}
normalized_ledger_rows = {len(ledger)}
included_candidates = {';'.join(included_candidates)}
anchor_ts = {iso_z(anchor)}
new_signal_count = {forward_metrics['new_signal_count']}
min_new_events = {min_new}
target_new_events = {target_new}
new_pf_x4 = {fmt_num(forward_metrics['new_pf_x4'])}
new_avg_net_x4 = {fmt_num(forward_metrics['new_avg_net_x4'])}
new_win_rate_x4 = {fmt_num(forward_metrics['new_win_rate_x4'])}
new_max_drawdown_x4 = {fmt_num(forward_metrics['new_max_drawdown_x4'])}
new_cost1_pf_x4 = {fmt_num(forward_metrics['new_cost1_pf_x4'])}
queue_pruner_rows = {len(queue_rows)}

## Forward confirmation state

{markdown_table(forward_state, ['variant_id', 'anchor_ts', 'new_signal_count', 'min_new_events', 'target_new_events', 'new_pf_x4', 'new_avg_net_x4', 'new_win_rate_x4', 'stage35c_decision', 'next_action'])}

## Gate checks

{markdown_table(gate_rows, ['gate', 'value', 'threshold', 'passed', 'severity'])}

## Queue pruner

{markdown_table(queue_rows, ['priority', 'variant_id', 'lane', 'promotion_allowed', 'enforced_action'])}

## Rerun trigger plan

{markdown_table(rerun_plan, ['priority', 'condition', 'action'])}

## Operational interpretation

1. If new h13/h14 events are still below the minimum, do not create another analysis stage.
2. Keep Stage33E and Stage35B as background rerun targets only after enough new events.
3. Calendar fast-path repair is removed from promotion unless a future targeted intake explicitly revives it.
4. Diagnostic-only variants remain excluded from promotion.
5. No EA, paper-live, or order transition is authorized here.

## Output files

- `data/reports/stage35c_forward_confirmation_trigger_queue_pruner/stage35c_forward_confirmation_trigger_queue_pruner.md`
- `data/reports/stage35c_forward_confirmation_trigger_queue_pruner/stage35c_summary.json`
- `data/reports/stage35c_forward_confirmation_trigger_queue_pruner/forward_confirmation_state.csv`
- `data/reports/stage35c_forward_confirmation_trigger_queue_pruner/forward_confirmation_gate_checks.csv`
- `data/reports/stage35c_forward_confirmation_trigger_queue_pruner/queue_pruner.csv`
- `data/reports/stage35c_forward_confirmation_trigger_queue_pruner/rerun_trigger_plan.csv`
- `data/reports/stage35c_forward_confirmation_trigger_queue_pruner/new_forward_events_audit.csv`
"""
    (REPORT_DIR / "stage35c_forward_confirmation_trigger_queue_pruner.md").write_text(md, encoding="utf-8")

    print(f"DECISION={decision}")
    print("EXECUTION_STATUS=RESEARCH_ONLY")
    print("COMMERCIAL_TRANSITION_AUTHORIZED=False")
    print(f"NEW_SIGNAL_COUNT={forward_metrics['new_signal_count']}")
    print(f"MIN_NEW_EVENTS={min_new}")
    print(f"NEXT_ACTION={next_action}")
    print(f"REPORT={REPORT_DIR / 'stage35c_forward_confirmation_trigger_queue_pruner.md'}")
    print(f"SUMMARY={REPORT_DIR / 'stage35c_summary.json'}")


if __name__ == "__main__":
    main()
