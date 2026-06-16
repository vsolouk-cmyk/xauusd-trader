"""Stage34C Controlled Intake Expansion Planner for XAUUSD research pipeline.

This stage is intentionally research-only. It does not generate orders, paper/live
routing, EA changes, or execution instructions. Its purpose is to prevent passive
waiting while Stage33E short-confirmation shadow collects h13/h14 events.

Inputs are previous stage reports under data/reports. Outputs are a targeted,
kill-switch driven intake expansion plan for the next candidate-generation stage.
"""
from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ROOT = Path.cwd()
REPORT_DIR = ROOT / "data" / "reports" / "stage34c_controlled_intake_expansion"
STAGE34B_DIR = ROOT / "data" / "reports" / "stage34b_parallel_repair_filter_lab"
STAGE33E_DIR = ROOT / "data" / "reports" / "stage33e_short_confirmation_recency_filter"
STAGE32C_DIR = ROOT / "data" / "reports" / "stage32c_dense_forward_shadow_tracker"

STAGE34B_SUMMARY = STAGE34B_DIR / "stage34b_summary.json"
STAGE33E_SUMMARY = STAGE33E_DIR / "stage33e_summary.json"
PARALLEL_ACCEL_Q = STAGE34B_DIR / "parallel_acceleration_queue.csv"
SHORT_CONFIRM_Q = STAGE34B_DIR / "short_confirmation_repair_filter_queue.csv"
REPAIR_KILL_Q = STAGE34B_DIR / "repair_or_kill_queue.csv"
LEDGER = STAGE32C_DIR / "dense_forward_signal_ledger.csv"


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # defensive, report not crash
        return {"_error": f"failed_to_read_json:{exc}"}


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not fieldnames:
        keys: List[str] = []
        for row in rows:
            for k in row.keys():
                if k not in keys:
                    keys.append(k)
        fieldnames = keys or ["empty"]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def fnum(v: Any, default: float = 0.0) -> float:
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


def snum(v: Any, default: int = 0) -> int:
    try:
        if v is None or v == "":
            return default
        return int(float(v))
    except Exception:
        return default


@dataclass
class IntakeSpec:
    priority: int
    lane: str
    target_family: str
    target_set: str
    included_candidates: str
    excluded_candidates: str
    action: str
    generation_directive: str
    reason: str
    min_required_new_events: int
    kill_switch: str
    expected_next_stage: str
    commercial_status: str = "RESEARCH_ONLY_NO_EA_NO_PAPER_LIVE_NO_ORDER"


@dataclass
class KillRow:
    priority: int
    set_name: str
    candidate_list: str
    reason: str
    next_action: str
    commercial_status: str = "RESEARCH_ONLY_NO_EA_NO_PAPER_LIVE_NO_ORDER"


def contains(text: str, needle: str) -> bool:
    return needle.lower() in (text or "").lower()


def build_intake_specs(stage34b_summary: Dict[str, Any], stage33e_summary: Dict[str, Any], accel_rows: List[Dict[str, str]], short_rows: List[Dict[str, str]], repair_rows: List[Dict[str, str]]) -> List[IntakeSpec]:
    specs: List[IntakeSpec] = []
    # Lane 1: primary repaired handoff confirmation, already alive.
    last_ts = stage33e_summary.get("last_effective_event_ts", "")
    specs.append(IntakeSpec(
        priority=1,
        lane="PRIMARY_SHORT_CONFIRMATION_BACKGROUND",
        target_family="session_handoff_imbalance_v1",
        target_set="handoff_h13_h14_repaired",
        included_candidates="handoff_align_follow_h13_tp06_sl065;handoff_align_follow_h14_tp06_sl065",
        excluded_candidates="handoff_align_follow_h15_tp06_sl065",
        action="KEEP_STAGE33E_CONFIRMATION_ACTIVE",
        generation_directive="Do not add execution. Collect only new h13/h14 effective events after last_effective_event_ts and rerun Stage33D/E when >=5 new events exist.",
        reason=f"Stage33E active; core/cost strong but recent degradation blocked pre-paper. last_effective_event_ts={last_ts}",
        min_required_new_events=snum(stage33e_summary.get("short_confirmation_min_new_events"), 5),
        kill_switch="If next confirmation batch PF<1.25 or avg<0 or recovery_ratio<0.65, kill/repair h13+h14 fast path.",
        expected_next_stage="RERUN_STAGE33D_STAGE33E",
    ))

    # Lane 2: h13/h14 recency-filter variants, generated from same source but not execution.
    specs.append(IntakeSpec(
        priority=2,
        lane="TARGETED_REPAIR_VARIANT_GENERATION",
        target_family="session_handoff_imbalance_v1",
        target_set="handoff_h13_h14_recency_guard_variants",
        included_candidates="handoff_align_follow_h13_tp06_sl065;handoff_align_follow_h14_tp06_sl065",
        excluded_candidates="handoff_align_follow_h15_tp06_sl065",
        action="GENERATE_RECENCY_FILTER_TESTS",
        generation_directive="Create research-only variants that test last5/last10 recovery, exclude h15, and require confirmation after 2026-06-15T13:00:00Z. Compare raw h13+h14 vs recency-filtered h13+h14; no orders.",
        reason="The only strong path is h13+h14, but latest batch is weak. A recency guard can reduce time-to-decision without waiting for single-variant N=40.",
        min_required_new_events=5,
        kill_switch="If recency-filter variants reduce sample count below 20 effective historical events or fail cost1 PF>=1.15, discard.",
        expected_next_stage="STAGE35A_TARGETED_VARIANT_GENERATOR",
    ))

    # Lane 3: vol_trans_fade h12 acceleration, only if present in accel queue.
    has_fade = any(contains(r.get("set_name", "") + r.get("candidate_list", ""), "vol_trans_fade") for r in accel_rows)
    if has_fade:
        specs.append(IntakeSpec(
            priority=3,
            lane="SECONDARY_ACCELERATION_REPAIR",
            target_family="volatility_transition_v1",
            target_set="vol_trans_fade_h12_cost_tail_repair",
            included_candidates="vol_trans_fade_h1_low_to_high_h12_tp06_sl065",
            excluded_candidates="vol_trans_follow variants",
            action="GENERATE_COST_TAIL_FILTER_TESTS",
            generation_directive="Test fade-h12 only with stricter cost/tail filters: require tail_pf>=1 over latest window, avoid spread/cost stress failure, and compare h12-only vs volatility-regime-gated h12.",
            reason="Stage34B keeps vol_trans_fade in acceleration, but tail and cost1 are weak; targeted repair can be run in parallel cheaply.",
            min_required_new_events=5,
            kill_switch="If cost1_pf<1.1 or last5_avg<0 after repair, kill as primary candidate and keep only background observation.",
            expected_next_stage="STAGE35A_TARGETED_VARIANT_GENERATOR",
        ))

    # Lane 4: calendar Friday-only is not precommercial, but can be a cheap repair if constrained.
    has_calendar_friday = any(contains(r.get("set_name", "") + r.get("candidate_list", ""), "calendar") for r in accel_rows)
    if has_calendar_friday:
        specs.append(IntakeSpec(
            priority=4,
            lane="LOW_PRIORITY_CALENDAR_REPAIR",
            target_family="calendar_time_risk_proxy_v1",
            target_set="calendar_friday_only_hour_suppression",
            included_candidates="calendar_drop_friday_h9_tp06_sl065;calendar_drop_friday_h13_tp06_sl065",
            excluded_candidates="calendar_drop_monday_h13_tp06_sl065",
            action="GENERATE_HOUR_SUPPRESSION_AND_FRIDAY_ONLY_TESTS",
            generation_directive="Test Friday-only repairs with hour suppression and strict last5/cost guards. Do not promote unless last5_pf>=1 and cost1_pf>=1.1.",
            reason="Stage34B shows calendar Friday-only is positive but weak; it may be repaired cheaply but must not distract from h13/h14.",
            min_required_new_events=8,
            kill_switch="If Friday-only repair fails last5 or cost guard again, kill calendar fast path for now.",
            expected_next_stage="STAGE35A_TARGETED_VARIANT_GENERATOR",
        ))

    # Lane 5: inverted vol follow has tempting PF but low WR; treat as diagnostic only.
    has_inverted_follow = any(contains(r.get("set_name", ""), "VOL_TRANS_FOLLOW") and r.get("invert_net", "").lower() == "true" for r in repair_rows)
    if has_inverted_follow:
        specs.append(IntakeSpec(
            priority=5,
            lane="DIAGNOSTIC_ONLY_INVERSION_CHECK",
            target_family="volatility_transition_v1",
            target_set="vol_trans_follow_inverted_diagnostic",
            included_candidates="vol_trans_follow_h1_low_to_high_h12_tp06_sl065;vol_trans_follow_h1_low_to_high_h13_tp06_sl065",
            excluded_candidates="vol_trans_fade_h12",
            action="DIAGNOSTIC_ONLY_DO_NOT_PROMOTE",
            generation_directive="Keep inverted follow as diagnostic only because win-rate is weak despite some PF. Test whether edge is tail/outlier driven before any acceleration.",
            reason="Inverted follow appears in repair queue with some PF but insufficient robustness/win-rate; do not wait for N=40.",
            min_required_new_events=10,
            kill_switch="If win_rate remains <0.52 or result depends on one outlier batch, kill.",
            expected_next_stage="OPTIONAL_DIAGNOSTIC_REPORT_ONLY",
        ))
    return specs


def build_kill_rows(repair_rows: List[Dict[str, str]]) -> List[KillRow]:
    rows: List[KillRow] = []
    for i, r in enumerate(repair_rows, start=1):
        set_name = r.get("set_name", "")
        cand = r.get("candidate_list", "")
        pf = fnum(r.get("pf_x4"))
        avg = fnum(r.get("avg_net_x4"))
        wr = fnum(r.get("win_rate_x4"))
        last5 = fnum(r.get("last5_pf_x4"))
        if contains(set_name, "HANDOFF_SINGLE_MEMBER"):
            reason = "Single-member handoff is not enough for fast path; keep only through repaired h13+h14 family."
            next_action = "DO_NOT_WAIT_SINGLE_VARIANT_N40"
        elif pf < 1.0 or avg < 0:
            reason = f"Weak core metrics: pf={pf:.3f}, avg={avg:.3f}, wr={wr:.3f}."
            next_action = "KILL_OR_REPAIR_ONLY"
        elif last5 < 1.0:
            reason = f"Latest-window failure: last5_pf={last5:.3f}; no fast-path promotion."
            next_action = "REPAIR_ONLY_WITH_STRICT_RECENCY_FILTER"
        else:
            reason = "Near-miss but not robust enough for current fast path."
            next_action = "BACKGROUND_DIAGNOSTIC_ONLY"
        rows.append(KillRow(priority=i, set_name=set_name, candidate_list=cand, reason=reason, next_action=next_action))
    return rows


def md_table(rows: List[Dict[str, Any]], columns: List[str]) -> str:
    if not rows:
        return "No rows.\n"
    out = []
    out.append("| " + " | ".join(columns) + " |")
    out.append("| " + " | ".join(["---"] * len(columns)) + " |")
    for row in rows:
        out.append("| " + " | ".join(str(row.get(c, "")) for c in columns) + " |")
    return "\n".join(out) + "\n"


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stage34b = read_json(STAGE34B_SUMMARY)
    stage33e = read_json(STAGE33E_SUMMARY)
    accel = read_csv(PARALLEL_ACCEL_Q)
    short = read_csv(SHORT_CONFIRM_Q)
    repair = read_csv(REPAIR_KILL_Q)

    specs = build_intake_specs(stage34b, stage33e, accel, short, repair)
    kill_rows = build_kill_rows(repair)

    stage34b_decision = stage34b.get("decision", "UNKNOWN")
    precomm_rows = snum(stage34b.get("precommercial_repair_filter_rows"), 0)
    short_rows = snum(stage34b.get("short_confirmation_rows"), len(short))
    accel_rows = snum(stage34b.get("accelerate_collection_rows"), len(accel))
    repair_rows = snum(stage34b.get("repair_or_kill_rows"), len(repair))

    if precomm_rows > 0:
        decision = "STAGE34C_HAS_PRECOMMERCIAL_PATH_VALIDATE_STRICTLY_RESEARCH_ONLY"
        recommended = "RUN_STRICT_PREPAPER_GATE_FOR_REPAIR_FILTER_CANDIDATES_NO_EA_NO_PAPER_LIVE"
    elif short_rows > 0 and specs:
        decision = "STAGE34C_CONTROLLED_INTAKE_EXPANSION_ACTIVE_RESEARCH_ONLY"
        recommended = "BUILD_STAGE35A_TARGETED_VARIANT_GENERATOR_WHILE_STAGE33E_RUNS_BACKGROUND"
    else:
        decision = "STAGE34C_NO_FAST_PATH_START_CONTROLLED_INTAKE_EXPANSION_RESEARCH_ONLY"
        recommended = "BUILD_STAGE35A_TARGETED_VARIANT_GENERATOR_FROM_REPAIR_SPECS"

    specs_rows = [asdict(s) for s in specs]
    kill_dicts = [asdict(k) for k in kill_rows]

    background_rows = [
        {
            "priority": 1,
            "queue": "stage33e_h13_h14_short_confirmation",
            "reason": "Primary short confirmation path; run via scheduler/background only.",
            "next_check": "Rerun Stage33D/E after >=5 new h13/h14 events.",
        },
        {
            "priority": 2,
            "queue": "stage32f_scheduler",
            "reason": "Background collection only; not the main decision path.",
            "next_check": "Only run wrapper when preflight indicates useful H1 target-hour progress.",
        },
    ]

    write_csv(REPORT_DIR / "controlled_intake_plan.csv", specs_rows)
    write_csv(REPORT_DIR / "repair_or_kill_enforced_queue.csv", kill_dicts)
    write_csv(REPORT_DIR / "background_collection_queue.csv", background_rows)

    summary = {
        "generated_utc": now_utc(),
        "decision": decision,
        "execution_status": "RESEARCH_ONLY",
        "commercial_transition_authorized": False,
        "no_ea_change": True,
        "no_paper_live": True,
        "no_order_authorization": True,
        "primary_objective": "CONTROLLED_INTAKE_EXPANSION_TO_REDUCE_TIME_TO_COMMERCIAL_DECISION",
        "recommended_next_stage": recommended,
        "stage34b_decision": stage34b_decision,
        "stage33e_decision": stage33e.get("decision", "UNKNOWN"),
        "stage34b_precommercial_rows": precomm_rows,
        "stage34b_short_confirmation_rows": short_rows,
        "stage34b_accelerate_collection_rows": accel_rows,
        "stage34b_repair_or_kill_rows": repair_rows,
        "controlled_intake_spec_rows": len(specs_rows),
        "repair_or_kill_enforced_rows": len(kill_dicts),
        "background_queue_rows": len(background_rows),
        "stage34b_summary_path": str(STAGE34B_SUMMARY.relative_to(ROOT)),
        "stage33e_summary_path": str(STAGE33E_SUMMARY.relative_to(ROOT)),
    }

    (REPORT_DIR / "stage34c_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    md = f"""# XAUUSD Stage34C — Controlled Intake Expansion Plan

Generated UTC: {summary['generated_utc']}

## Decision

```text
DECISION = {decision}
EXECUTION_STATUS = RESEARCH_ONLY
COMMERCIAL_TRANSITION_AUTHORIZED = False
NO_EA_CHANGE = True
NO_PAPER_LIVE = True
NO_ORDER_AUTHORIZATION = True
PRIMARY_OBJECTIVE = {summary['primary_objective']}
RECOMMENDED_NEXT_STAGE = {recommended}
```

## Why this stage exists

Stage33E is waiting for a short h13+h14 confirmation batch, and Stage34B found no pre-commercial repair-filter row. Stage34C prevents passive waiting by converting Stage34B's queues into a controlled, kill-switch driven intake expansion plan. It is not general discovery and it does not authorize EA, paper-live, or orders.

## Summary

```text
stage34b_decision = {stage34b_decision}
stage33e_decision = {summary['stage33e_decision']}
stage34b_precommercial_rows = {precomm_rows}
stage34b_short_confirmation_rows = {short_rows}
stage34b_accelerate_collection_rows = {accel_rows}
stage34b_repair_or_kill_rows = {repair_rows}
controlled_intake_spec_rows = {len(specs_rows)}
repair_or_kill_enforced_rows = {len(kill_dicts)}
```

## Controlled intake plan

{md_table(specs_rows, ['priority','lane','target_family','target_set','action','min_required_new_events','expected_next_stage'])}

## Kill / repair enforcement queue

{md_table(kill_dicts[:20], ['priority','set_name','reason','next_action'])}

## Background collection queue

{md_table(background_rows, ['priority','queue','reason','next_check'])}

## Operational interpretation

```text
1. Stage33E remains active only as background short confirmation for h13+h14.
2. Stage34C does not wait passively; it prepares targeted Stage35A variant generation.
3. Weak paths are explicitly kill/repair, not single-variant N=40 waits.
4. No EA, paper-live, or order transition is authorized here.
```

## Output files

- `data/reports/stage34c_controlled_intake_expansion/stage34c_controlled_intake_expansion.md`
- `data/reports/stage34c_controlled_intake_expansion/stage34c_summary.json`
- `data/reports/stage34c_controlled_intake_expansion/controlled_intake_plan.csv`
- `data/reports/stage34c_controlled_intake_expansion/repair_or_kill_enforced_queue.csv`
- `data/reports/stage34c_controlled_intake_expansion/background_collection_queue.csv`
"""
    (REPORT_DIR / "stage34c_controlled_intake_expansion.md").write_text(md, encoding="utf-8")

    print(f"DECISION={decision}")
    print(f"CONTROLLED_INTAKE_SPEC_ROWS={len(specs_rows)}")
    print(f"RECOMMENDED_NEXT_STAGE={recommended}")
    print(f"REPORT={REPORT_DIR / 'stage34c_controlled_intake_expansion.md'}")


if __name__ == "__main__":
    main()
