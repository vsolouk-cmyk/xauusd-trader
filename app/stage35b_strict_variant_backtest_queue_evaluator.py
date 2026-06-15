#!/usr/bin/env python3
"""Stage35B Strict Variant Backtest / Queue Evaluator.

Research-only evaluator for targeted Stage35A variant specs.
It reads the Stage35A variant queue and the Stage32C dense forward ledger,
then separates variants into strict-review-ready, pending confirmation,
diagnostic-only, acceleration-only, and kill/repair buckets.

No EA, no paper-live, no order authorization.
"""
from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

REPORT_DIR = Path("data/reports/stage35b_strict_variant_backtest_queue_evaluator")
STAGE35A_SPECS = Path("data/reports/stage35a_targeted_variant_generator/targeted_variant_specs.csv")
STAGE32C_LEDGER = Path("data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_signal_ledger.csv")
STAGE33E_SUMMARY = Path("data/reports/stage33e_short_confirmation_recency_filter/stage33e_summary.json")
STAGE35A_SUMMARY = Path("data/reports/stage35a_targeted_variant_generator/stage35a_summary.json")

DECISION_READY = "STAGE35B_HAS_STRICT_VARIANT_REVIEW_CANDIDATE_RESEARCH_ONLY"
DECISION_PENDING = "STAGE35B_VARIANTS_PENDING_FORWARD_CONFIRMATION_RESEARCH_ONLY"
DECISION_ACCEL = "STAGE35B_ACCELERATION_ONLY_NO_STRICT_REVIEW_CANDIDATE_RESEARCH_ONLY"
DECISION_NO_FAST_PATH = "STAGE35B_NO_STRICT_VARIANT_FAST_PATH_REPAIR_OR_TARGETED_INTAKE_RESEARCH_ONLY"

NO_EXEC_STATUS = "RESEARCH_ONLY_NO_EA_NO_PAPER_LIVE_NO_ORDER"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        seen: List[str] = []
        for row in rows:
            for key in row.keys():
                if key not in seen:
                    seen.append(key)
        fieldnames = seen
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def as_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        if isinstance(v, str) and v.lower() in {"inf", "+inf", "infinity"}:
            return math.inf
        if isinstance(v, str) and v.lower() in {"-inf", "-infinity"}:
            return -math.inf
        return float(v)
    except Exception:
        return default


def as_int(v: Any, default: int = 0) -> int:
    try:
        if v is None or v == "":
            return default
        return int(float(v))
    except Exception:
        return default


def parse_ts(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # tolerate common non-ISO local format
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y.%m.%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(s.replace("/", "-"), fmt)
                break
            except Exception:
                dt = None
        if dt is None:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso_z(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def extract_anchor(entry_filter: str, fallback: str = "") -> Optional[datetime]:
    text = entry_filter or ""
    # Example: entry_time > 2026-06-15T13:00:00Z
    m = re.search(r"(20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?)", text)
    if m:
        return parse_ts(m.group(1))
    return parse_ts(fallback)


def find_col(row: Dict[str, Any], candidates: Sequence[str], contains: Sequence[str] = ()) -> Optional[str]:
    keys = list(row.keys())
    lower = {k.lower(): k for k in keys}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    for k in keys:
        kl = k.lower()
        if any(part in kl for part in contains):
            return k
    return None


@dataclass
class Metric:
    signal_count: int
    pf_x4: float
    avg_net_x4: float
    win_rate_x4: float
    tail_pf_x4: float
    max_drawdown_x4: float
    sum_net_x4: float
    first_ts: str
    last_ts: str


def compute_pf(values: Sequence[float]) -> float:
    gp = sum(v for v in values if v > 0)
    gl = abs(sum(v for v in values if v < 0))
    if gl == 0:
        if gp > 0:
            return math.inf
        return 0.0
    return gp / gl


def max_drawdown(values: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    mdd = 0.0
    for v in values:
        equity += v
        if equity > peak:
            peak = equity
        dd = equity - peak
        if dd < mdd:
            mdd = dd
    return mdd


def metrics(rows: Sequence[Dict[str, Any]], net_col: str = "_net_x4", cost_penalty_x4: float = 0.0) -> Metric:
    vals: List[float] = []
    tss: List[datetime] = []
    for row in rows:
        v = as_float(row.get(net_col), 0.0) - cost_penalty_x4
        vals.append(v)
        ts = row.get("_ts")
        if isinstance(ts, datetime):
            tss.append(ts)
    n = len(vals)
    if n == 0:
        return Metric(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "", "")
    tail_vals = vals[-min(10, n):]
    return Metric(
        signal_count=n,
        pf_x4=compute_pf(vals),
        avg_net_x4=sum(vals) / n,
        win_rate_x4=sum(1 for v in vals if v > 0) / n,
        tail_pf_x4=compute_pf(tail_vals),
        max_drawdown_x4=max_drawdown(vals),
        sum_net_x4=sum(vals),
        first_ts=iso_z(min(tss)) if tss else "",
        last_ts=iso_z(max(tss)) if tss else "",
    )


def fmt_float(v: float) -> Any:
    if isinstance(v, float) and math.isinf(v):
        return "inf" if v > 0 else "-inf"
    if isinstance(v, float) and math.isnan(v):
        return ""
    return round(float(v), 6)


def metric_to_row(prefix: str, m: Metric) -> Dict[str, Any]:
    return {
        f"{prefix}signal_count": m.signal_count,
        f"{prefix}pf_x4": fmt_float(m.pf_x4),
        f"{prefix}avg_net_x4": fmt_float(m.avg_net_x4),
        f"{prefix}win_rate_x4": fmt_float(m.win_rate_x4),
        f"{prefix}tail_pf_x4": fmt_float(m.tail_pf_x4),
        f"{prefix}max_drawdown_x4": fmt_float(m.max_drawdown_x4),
        f"{prefix}sum_net_x4": fmt_float(m.sum_net_x4),
        f"{prefix}first_ts": m.first_ts,
        f"{prefix}last_ts": m.last_ts,
    }


def split_candidates(s: str) -> List[str]:
    return [x.strip() for x in (s or "").split(";") if x.strip()]


def normalize_ledger(rows: List[Dict[str, str]]) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    if not rows:
        return [], {}
    sample = rows[0]
    candidate_col = find_col(sample, ["candidate", "candidate_id", "spec_id"])
    family_col = find_col(sample, ["family", "family_id", "target_family"])
    ts_col = find_col(sample, ["entry_time", "entry_time_utc", "signal_ts_utc", "signal_time_utc", "timestamp", "time"], contains=["time", "ts"])
    net_col = find_col(sample, ["net_x4", "net", "pnl_x4", "outcome_net_x4"])
    if not candidate_col or not ts_col or not net_col:
        return [], {
            "candidate_col": str(candidate_col),
            "family_col": str(family_col),
            "timestamp_col": str(ts_col),
            "net_col": str(net_col),
            "error": "missing_required_ledger_columns",
        }
    out: List[Dict[str, Any]] = []
    for row in rows:
        ts = parse_ts(row.get(ts_col))
        if ts is None:
            continue
        r = dict(row)
        r["_candidate"] = str(row.get(candidate_col, "")).strip()
        r["_family"] = str(row.get(family_col, "")).strip() if family_col else ""
        r["_ts"] = ts
        r["_net_x4"] = as_float(row.get(net_col), 0.0)
        out.append(r)
    out.sort(key=lambda x: x["_ts"])
    return out, {
        "candidate_col": candidate_col,
        "family_col": str(family_col),
        "timestamp_col": ts_col,
        "net_col": net_col,
    }


def row_pass(value: float, threshold: float, op: str = ">=") -> bool:
    if math.isinf(value) and value > 0:
        return True if op == ">=" else False
    if op == ">=":
        return value >= threshold
    if op == "<=":
        return value <= threshold
    return False


def evaluate_gates(spec: Dict[str, str], full: Metric, cost1: Metric, last5: Metric, newm: Metric, decision_context: str) -> Tuple[List[Dict[str, Any]], int, int]:
    checks: List[Dict[str, Any]] = []
    fatal_fail = 0
    warn_fail = 0

    def add(gate: str, value: Any, threshold: Any, passed: bool, severity: str, implication: str) -> None:
        nonlocal fatal_fail, warn_fail
        if not passed:
            if severity == "fatal":
                fatal_fail += 1
            else:
                warn_fail += 1
        checks.append({
            "variant_id": spec.get("variant_id", ""),
            "gate": gate,
            "value": value,
            "threshold": threshold,
            "passed": passed,
            "severity": severity,
            "decision_context": decision_context,
            "implication": implication,
        })

    min_total = as_int(spec.get("min_total_events_for_review"), 0)
    min_new = as_int(spec.get("min_required_new_events"), 0)
    add("total_event_count", full.signal_count, f">= {min_total}", full.signal_count >= min_total, "fatal", "Enough total evidence is required for strict review.")
    if decision_context == "forward_confirmation":
        add("new_event_count", newm.signal_count, f">= {min_new}", newm.signal_count >= min_new, "fatal", "Forward confirmation needs enough new events after the anchor.")
    add("pf_x4", fmt_float(full.pf_x4), f">= {spec.get('gate_pf_x4')}", row_pass(full.pf_x4, as_float(spec.get("gate_pf_x4"))), "fatal", "Core PF must clear the targeted gate.")
    add("avg_net_x4", fmt_float(full.avg_net_x4), f">= {spec.get('gate_avg_net_x4')}", row_pass(full.avg_net_x4, as_float(spec.get("gate_avg_net_x4"))), "fatal", "Average net must be positive enough.")
    add("win_rate_x4", fmt_float(full.win_rate_x4), f">= {spec.get('gate_win_rate_x4')}", row_pass(full.win_rate_x4, as_float(spec.get("gate_win_rate_x4"))), "fatal", "Win rate must be robust.")
    add("tail_pf_x4", fmt_float(full.tail_pf_x4), f">= {spec.get('gate_tail_pf_x4')}", row_pass(full.tail_pf_x4, as_float(spec.get("gate_tail_pf_x4"))), "fatal", "Tail PF must not collapse.")
    add("cost_1_pf_x4", fmt_float(cost1.pf_x4), f">= {spec.get('gate_cost1_pf_x4')}", row_pass(cost1.pf_x4, as_float(spec.get("gate_cost1_pf_x4"))), "fatal", "Severe cost/slippage stress must pass.")
    add("last5_pf_x4", fmt_float(last5.pf_x4), f">= {spec.get('gate_last5_pf_x4')}", row_pass(last5.pf_x4, as_float(spec.get("gate_last5_pf_x4"))), "fatal", "Latest window cannot be losing for strict review.")
    add("last5_avg_net_x4", fmt_float(last5.avg_net_x4), ">= 0.0", row_pass(last5.avg_net_x4, 0.0), "fatal", "Latest window average must be non-negative.")
    add("drawdown_x4", fmt_float(full.max_drawdown_x4), f">= {spec.get('max_drawdown_x4')}", row_pass(full.max_drawdown_x4, as_float(spec.get("max_drawdown_x4"))), "fatal", "Drawdown proxy must stay within the guardrail.")
    return checks, fatal_fail, warn_fail


def suppress_weak_hours(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
    # For calendar hour-suppression repair: remove candidate-hour groups whose own last5 is weak.
    groups: Dict[Tuple[str, int], List[Dict[str, Any]]] = {}
    for r in rows:
        key = (r.get("_candidate", ""), r["_ts"].hour)
        groups.setdefault(key, []).append(r)
    keep: List[Dict[str, Any]] = []
    dropped: List[str] = []
    for key, grp in groups.items():
        grp = sorted(grp, key=lambda x: x["_ts"])
        last = metrics(grp[-min(5, len(grp)):])
        if last.signal_count >= 3 and (last.pf_x4 < 1.0 or last.avg_net_x4 < 0.0):
            dropped.append(f"{key[0]}@h{key[1]}")
            continue
        keep.extend(grp)
    keep.sort(key=lambda x: x["_ts"])
    return keep, ";".join(dropped)


def evaluate_variant(spec: Dict[str, str], ledger: List[Dict[str, Any]], stage33e_summary: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    variant_id = spec.get("variant_id", "")
    variant_type = spec.get("variant_type", "")
    candidates = set(split_candidates(spec.get("base_candidates", "")))
    rows = [dict(r) for r in ledger if r.get("_candidate") in candidates]
    rows.sort(key=lambda x: x["_ts"])

    transform_note = "raw_net"
    if "INVERSION" in variant_type:
        for r in rows:
            r["_net_x4"] = -as_float(r.get("_net_x4"), 0.0)
        transform_note = "inverted_net_diagnostic_only"

    filter_note = "none"
    if "HOUR_SUPPRESSION" in variant_type:
        rows, dropped = suppress_weak_hours(rows)
        filter_note = "hour_suppression_dropped=" + (dropped or "none")

    anchor = extract_anchor(spec.get("entry_filter", ""), str(stage33e_summary.get("last_effective_event_ts", "")))
    new_rows = [r for r in rows if anchor is not None and r["_ts"] > anchor]

    full = metrics(rows)
    cost1 = metrics(rows, cost_penalty_x4=1.0)
    last5_rows = rows[-min(5, len(rows)):]
    last5 = metrics(last5_rows)
    newm = metrics(new_rows)

    decision_context = "historical_strict_eval"
    stage_decision = "KILL_OR_REPAIR_RESEARCH_ONLY"
    next_action = spec.get("next_stage_if_fail", "KILL_OR_REPAIR")
    fatal_failed = 0
    warning_failed = 0

    if "DIAGNOSTIC" in variant_type:
        checks, fatal_failed, warning_failed = evaluate_gates(spec, full, cost1, last5, newm, "diagnostic_only")
        stage_decision = "DIAGNOSTIC_ONLY_NO_PROMOTION_RESEARCH_ONLY"
        next_action = spec.get("next_stage_if_pass", "OPTIONAL_DIAGNOSTIC_REPORT_ONLY")
    elif "RECENCY_GUARD" in variant_type:
        # This variant is not allowed to pass until new forward events arrive after Stage33E anchor.
        checks, fatal_failed, warning_failed = evaluate_gates(spec, full, cost1, last5, newm, "forward_confirmation")
        if newm.signal_count < as_int(spec.get("min_required_new_events"), 0):
            stage_decision = "PENDING_FORWARD_CONFIRMATION_RESEARCH_ONLY"
            next_action = "COLLECT_NEW_EVENTS_THEN_RERUN_STAGE35B"
        elif fatal_failed == 0:
            stage_decision = "STRICT_VARIANT_REVIEW_READY_RESEARCH_ONLY"
            next_action = spec.get("next_stage_if_pass", "STRICT_REVIEW")
        else:
            stage_decision = "KILL_OR_BACKGROUND_ONLY_RESEARCH_ONLY"
            next_action = spec.get("next_stage_if_fail", "KILL_OR_BACKGROUND")
    else:
        checks, fatal_failed, warning_failed = evaluate_gates(spec, full, cost1, last5, newm, "historical_strict_eval")
        if fatal_failed == 0:
            stage_decision = "STRICT_VARIANT_REVIEW_READY_RESEARCH_ONLY"
            next_action = spec.get("next_stage_if_pass", "STRICT_REVIEW")
        elif full.signal_count >= as_int(spec.get("min_required_new_events"), 0) and full.signal_count < as_int(spec.get("min_total_events_for_review"), 0):
            stage_decision = "ACCELERATION_PENDING_MORE_EVIDENCE_RESEARCH_ONLY"
            next_action = "KEEP_CHEAP_BACKGROUND_COLLECTION_ONLY"
        else:
            stage_decision = "KILL_OR_REPAIR_RESEARCH_ONLY"
            next_action = spec.get("next_stage_if_fail", "KILL_OR_REPAIR")

    row: Dict[str, Any] = {
        "priority": spec.get("priority", ""),
        "variant_id": variant_id,
        "lane": spec.get("lane", ""),
        "target_family": spec.get("target_family", ""),
        "variant_type": variant_type,
        "base_candidates": spec.get("base_candidates", ""),
        "transform_note": transform_note,
        "filter_note": filter_note,
        "anchor_ts": iso_z(anchor),
        "min_required_new_events": spec.get("min_required_new_events", ""),
        "target_new_events": spec.get("target_new_events", ""),
        "min_total_events_for_review": spec.get("min_total_events_for_review", ""),
        **metric_to_row("full_", full),
        **metric_to_row("cost1_", cost1),
        **metric_to_row("last5_", last5),
        **metric_to_row("new_", newm),
        "fatal_failed_gates": fatal_failed,
        "warning_failed_gates": warning_failed,
        "stage35b_decision": stage_decision,
        "next_action": next_action,
        "commercial_status": NO_EXEC_STATUS,
    }
    return row, checks


def markdown_table(rows: List[Dict[str, Any]], columns: List[str]) -> str:
    if not rows:
        return "No rows.\n"
    lines = []
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("| " + " | ".join(["---"] * len(columns)) + " |")
    for r in rows:
        vals = []
        for c in columns:
            v = str(r.get(c, ""))
            if len(v) > 110:
                v = v[:107] + "..."
            vals.append(v.replace("|", "/"))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines) + "\n"


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    specs = read_csv(STAGE35A_SPECS)
    ledger_raw = read_csv(STAGE32C_LEDGER)
    stage33e_summary = read_json(STAGE33E_SUMMARY)
    stage35a_summary = read_json(STAGE35A_SUMMARY)
    ledger, colmap = normalize_ledger(ledger_raw)

    evaluations: List[Dict[str, Any]] = []
    gate_checks: List[Dict[str, Any]] = []
    if specs and ledger:
        for spec in specs:
            row, checks = evaluate_variant(spec, ledger, stage33e_summary)
            evaluations.append(row)
            gate_checks.extend(checks)

    ready = [r for r in evaluations if r.get("stage35b_decision") == "STRICT_VARIANT_REVIEW_READY_RESEARCH_ONLY"]
    pending = [r for r in evaluations if r.get("stage35b_decision") == "PENDING_FORWARD_CONFIRMATION_RESEARCH_ONLY"]
    accel = [r for r in evaluations if r.get("stage35b_decision") == "ACCELERATION_PENDING_MORE_EVIDENCE_RESEARCH_ONLY"]
    diag = [r for r in evaluations if str(r.get("stage35b_decision", "")).startswith("DIAGNOSTIC_ONLY")]
    kill = [r for r in evaluations if r.get("stage35b_decision") in {"KILL_OR_REPAIR_RESEARCH_ONLY", "KILL_OR_BACKGROUND_ONLY_RESEARCH_ONLY"}]

    if ready:
        decision = DECISION_READY
        recommended = "RUN_STRICT_PREPAPER_RESEARCH_DESIGN_FOR_READY_VARIANTS_NO_EA_NO_PAPER_LIVE"
    elif pending:
        decision = DECISION_PENDING
        recommended = "KEEP_STAGE33E_BACKGROUND_AND_RERUN_STAGE35B_AFTER_REQUIRED_NEW_EVENTS"
    elif accel:
        decision = DECISION_ACCEL
        recommended = "CHEAP_BACKGROUND_COLLECTION_ONLY_OR_RETURN_TO_TARGETED_INTAKE"
    else:
        decision = DECISION_NO_FAST_PATH
        recommended = "REPAIR_OR_TARGETED_INTAKE_EXPANSION_NO_EA_NO_PAPER_LIVE"

    action_plan: List[Dict[str, Any]] = []
    pr = 1
    for r in ready:
        action_plan.append({"priority": pr, "action": "PROMOTE_TO_STRICT_PREPAPER_RESEARCH_DESIGN", "variant_id": r["variant_id"], "rationale": "All strict gates passed in Stage35B.", "execution_status": "RESEARCH_ONLY"}); pr += 1
    for r in pending:
        action_plan.append({"priority": pr, "action": "COLLECT_FORWARD_CONFIRMATION_EVENTS", "variant_id": r["variant_id"], "rationale": f"New events after anchor are {r.get('new_signal_count')} and minimum is {r.get('min_required_new_events')}.", "execution_status": "RESEARCH_ONLY"}); pr += 1
    for r in accel:
        action_plan.append({"priority": pr, "action": "KEEP_CHEAP_BACKGROUND_ACCELERATION_ONLY", "variant_id": r["variant_id"], "rationale": "Not enough strict evidence for review; do not broaden discovery.", "execution_status": "RESEARCH_ONLY"}); pr += 1
    for r in diag:
        action_plan.append({"priority": pr, "action": "KEEP_DIAGNOSTIC_ONLY", "variant_id": r["variant_id"], "rationale": "Diagnostic variants must not be promoted directly.", "execution_status": "RESEARCH_ONLY"}); pr += 1
    for r in kill:
        action_plan.append({"priority": pr, "action": "KILL_OR_REPAIR_VARIANT", "variant_id": r["variant_id"], "rationale": "Strict gates failed; do not wait for N40 by default.", "execution_status": "RESEARCH_ONLY"}); pr += 1

    write_csv(REPORT_DIR / "strict_variant_evaluation.csv", evaluations)
    write_csv(REPORT_DIR / "variant_gate_checks.csv", gate_checks)
    write_csv(REPORT_DIR / "stage35b_action_plan.csv", action_plan)
    write_csv(REPORT_DIR / "strict_review_ready_queue.csv", ready)
    write_csv(REPORT_DIR / "pending_forward_confirmation_queue.csv", pending)

    summary = {
        "generated_utc": utc_now_iso(),
        "decision": decision,
        "execution_status": "RESEARCH_ONLY",
        "commercial_transition_authorized": False,
        "no_ea_change": True,
        "no_paper_live": True,
        "no_order_authorization": True,
        "primary_objective": "STRICT_TARGETED_VARIANT_EVALUATION_WITH_FORWARD_CONFIRMATION_SEPARATION",
        "recommended_next_stage": recommended,
        "stage35a_decision": stage35a_summary.get("decision", ""),
        "stage33e_decision": stage33e_summary.get("decision", ""),
        "spec_rows": len(specs),
        "ledger_available": bool(ledger),
        "ledger_rows": len(ledger_raw),
        "normalized_ledger_rows": len(ledger),
        "ledger_column_map": colmap,
        "strict_review_ready_rows": len(ready),
        "pending_forward_confirmation_rows": len(pending),
        "acceleration_pending_rows": len(accel),
        "diagnostic_only_rows": len(diag),
        "kill_or_repair_rows": len(kill),
        "stage35a_specs_path": str(STAGE35A_SPECS),
        "ledger_path": str(STAGE32C_LEDGER),
    }
    (REPORT_DIR / "stage35b_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    md = []
    md.append("# XAUUSD Stage35B — Strict Variant Backtest / Queue Evaluator\n")
    md.append(f"Generated UTC: {summary['generated_utc']}\n")
    md.append("## Decision\n")
    md.append("```text\n")
    for k in ["decision", "execution_status", "commercial_transition_authorized", "no_ea_change", "no_paper_live", "no_order_authorization", "primary_objective", "recommended_next_stage"]:
        md.append(f"{k.upper()} = {summary[k]}\n")
    md.append("```\n\n")
    md.append("## Why this stage exists\n\n")
    md.append("Stage35A produced targeted variants so the project does not wait passively for h13/h14 confirmation. Stage35B evaluates those variants with strict gates while separating forward-confirmation candidates from historical diagnostics. This stage is research-only and authorizes no EA, paper-live, or orders.\n\n")
    md.append("## Summary\n\n")
    md.append("```text\n")
    for k in ["stage35a_decision", "stage33e_decision", "spec_rows", "ledger_available", "normalized_ledger_rows", "strict_review_ready_rows", "pending_forward_confirmation_rows", "acceleration_pending_rows", "diagnostic_only_rows", "kill_or_repair_rows"]:
        md.append(f"{k} = {summary.get(k)}\n")
    md.append("```\n\n")
    md.append("## Strict variant evaluation\n\n")
    md.append(markdown_table(evaluations, ["priority", "variant_id", "variant_type", "full_signal_count", "full_pf_x4", "full_avg_net_x4", "full_win_rate_x4", "full_tail_pf_x4", "cost1_pf_x4", "last5_pf_x4", "new_signal_count", "fatal_failed_gates", "stage35b_decision", "next_action"]))
    md.append("\n## Action plan\n\n")
    md.append(markdown_table(action_plan, ["priority", "action", "variant_id", "rationale", "execution_status"]))
    md.append("\n## Operational interpretation\n\n")
    md.append("1. A Stage35A spec is not automatically tradable or paper-ready.\n")
    md.append("2. Recency-guard variants require new forward events after the Stage33E anchor before promotion.\n")
    md.append("3. Diagnostic-only variants cannot be promoted directly even if retrospective metrics look good.\n")
    md.append("4. If no strict review candidate exists, continue only cheap background collection and targeted intake; do not wait for single-variant N=40.\n")
    md.append("\n## Output files\n\n")
    for p in ["stage35b_strict_variant_backtest_queue_evaluator.md", "stage35b_summary.json", "strict_variant_evaluation.csv", "variant_gate_checks.csv", "stage35b_action_plan.csv", "strict_review_ready_queue.csv", "pending_forward_confirmation_queue.csv"]:
        md.append(f"- `{REPORT_DIR / p}`\n")
    (REPORT_DIR / "stage35b_strict_variant_backtest_queue_evaluator.md").write_text("".join(md), encoding="utf-8")

    print(f"DECISION={decision}")
    print(f"RECOMMENDED_NEXT_STAGE={recommended}")
    print(f"STRICT_REVIEW_READY_ROWS={len(ready)}")
    print(f"PENDING_FORWARD_CONFIRMATION_ROWS={len(pending)}")
    print(f"ACCELERATION_PENDING_ROWS={len(accel)}")
    print(f"DIAGNOSTIC_ONLY_ROWS={len(diag)}")
    print(f"KILL_OR_REPAIR_ROWS={len(kill)}")
    print(f"REPORT={REPORT_DIR / 'stage35b_strict_variant_backtest_queue_evaluator.md'}")
    print(f"SUMMARY={REPORT_DIR / 'stage35b_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
