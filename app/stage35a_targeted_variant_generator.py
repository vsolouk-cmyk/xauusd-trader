"""Stage35A Targeted Variant Generator for XAUUSD research pipeline.

Research-only generator. It consumes Stage34C controlled intake outputs and
creates concrete, kill-switch driven targeted variant specifications for the
next testing stage. It does not change EA/paper/live/order routing.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

REPORT_DIR = Path("data/reports/stage35a_targeted_variant_generator")
STAGE34C_DIR = Path("data/reports/stage34c_controlled_intake_expansion")
STAGE34B_DIR = Path("data/reports/stage34b_parallel_repair_filter_lab")
STAGE33E_DIR = Path("data/reports/stage33e_short_confirmation_recency_filter")

CONTROLLED_INTAKE_PLAN = STAGE34C_DIR / "controlled_intake_plan.csv"
STAGE34C_SUMMARY = STAGE34C_DIR / "stage34c_summary.json"
REPAIR_OR_KILL_QUEUE = STAGE34C_DIR / "repair_or_kill_enforced_queue.csv"
BACKGROUND_QUEUE = STAGE34C_DIR / "background_collection_queue.csv"
STAGE34B_DIAGNOSTICS = STAGE34B_DIR / "repair_filter_candidate_diagnostics.csv"
STAGE33E_SUMMARY = STAGE33E_DIR / "stage33e_summary.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: List[Dict], fieldnames: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys = []
        seen = set()
        for row in rows:
            for key in row.keys():
                if key not in seen:
                    seen.add(key)
                    keys.append(key)
        fieldnames = keys
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def fnum(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


@dataclass
class VariantSpec:
    priority: int
    variant_id: str
    lane: str
    source_stage: str
    target_family: str
    target_set: str
    base_candidates: str
    variant_type: str
    transformation: str
    entry_filter: str
    exclusion_rule: str
    min_required_new_events: int
    target_new_events: int
    min_total_events_for_review: int
    gate_pf_x4: float
    gate_avg_net_x4: float
    gate_win_rate_x4: float
    gate_tail_pf_x4: float
    gate_cost1_pf_x4: float
    gate_last5_pf_x4: float
    max_drawdown_x4: float
    kill_switch: str
    next_stage_if_pass: str
    next_stage_if_fail: str
    execution_status: str = "RESEARCH_ONLY"
    commercial_transition_authorized: bool = False
    no_ea_change: bool = True
    no_paper_live: bool = True
    no_order_authorization: bool = True


def default_variant_specs(stage34c_plan: List[Dict[str, str]], stage33e_summary: Dict) -> List[VariantSpec]:
    last_ts = stage33e_summary.get("last_effective_event_ts", "2026-06-15T13:00:00Z")
    specs: List[VariantSpec] = []

    # 1) Handoff h13+h14: do not invent new signal logic. Generate recency guard variants.
    specs.append(VariantSpec(
        priority=1,
        variant_id="stage35a_handoff_h13_h14_recency_guard_last5_recovery",
        lane="TARGETED_REPAIR_VARIANT_GENERATION",
        source_stage="STAGE34C",
        target_family="session_handoff_imbalance_v1",
        target_set="handoff_h13_h14_recency_guard_variants",
        base_candidates="handoff_align_follow_h13_tp06_sl065;handoff_align_follow_h14_tp06_sl065",
        variant_type="RECENCY_GUARD",
        transformation="Keep h13+h14 only; require next confirmation window after Stage33E anchor to recover before promotion.",
        entry_filter=f"entry_time > {last_ts}; include only h13/h14; exclude h15",
        exclusion_rule="Exclude if next >=5 effective events have PF<1.25 or avg_net<0 or recovery_ratio<0.65.",
        min_required_new_events=5,
        target_new_events=10,
        min_total_events_for_review=30,
        gate_pf_x4=1.75,
        gate_avg_net_x4=0.75,
        gate_win_rate_x4=0.65,
        gate_tail_pf_x4=1.25,
        gate_cost1_pf_x4=1.25,
        gate_last5_pf_x4=1.25,
        max_drawdown_x4=-25.0,
        kill_switch="If next 5-10 events fail recovery, downgrade h13+h14 to background-only or kill/repair; do not wait for N40.",
        next_stage_if_pass="RERUN_STAGE33D_THEN_STAGE35B_STRICT_VARIANT_BACKTEST",
        next_stage_if_fail="KILL_OR_BACKGROUND_ONLY_HANDOFF_REPAIRED_FAMILY",
    ))

    specs.append(VariantSpec(
        priority=2,
        variant_id="stage35a_handoff_h13_h14_exclude_recent_degradation_diagnostic",
        lane="TARGETED_REPAIR_VARIANT_GENERATION",
        source_stage="STAGE34C",
        target_family="session_handoff_imbalance_v1",
        target_set="handoff_h13_h14_recency_guard_variants",
        base_candidates="handoff_align_follow_h13_tp06_sl065;handoff_align_follow_h14_tp06_sl065",
        variant_type="DIAGNOSTIC_RECENCY_FILTER",
        transformation="Diagnostic only: compare full h13+h14 with last-degraded window excluded; never use exclusion alone as trade rule.",
        entry_filter="Compare FULL_H13_H14 versus EXCLUDE_LAST_5_EVENTS_DIAGNOSTIC_ONLY from Stage33E.",
        exclusion_rule="Do not promote if improvement depends only on deleting recent losses without a forward recovery rule.",
        min_required_new_events=5,
        target_new_events=10,
        min_total_events_for_review=30,
        gate_pf_x4=1.75,
        gate_avg_net_x4=0.75,
        gate_win_rate_x4=0.65,
        gate_tail_pf_x4=1.25,
        gate_cost1_pf_x4=1.25,
        gate_last5_pf_x4=1.25,
        max_drawdown_x4=-25.0,
        kill_switch="If only backward exclusion works and forward confirmation fails, do not promote.",
        next_stage_if_pass="STAGE35B_STRICT_VARIANT_BACKTEST",
        next_stage_if_fail="KILL_OR_BACKGROUND_ONLY_HANDOFF_REPAIRED_FAMILY",
    ))

    # 2) Volatility fade repair. Keep strict because Stage34B has weak tail/cost.
    specs.append(VariantSpec(
        priority=3,
        variant_id="stage35a_vol_trans_fade_h12_cost_tail_repair",
        lane="SECONDARY_ACCELERATION_REPAIR",
        source_stage="STAGE34C",
        target_family="volatility_transition_v1",
        target_set="vol_trans_fade_h12_cost_tail_repair",
        base_candidates="vol_trans_fade_h1_low_to_high_h12_tp06_sl065",
        variant_type="COST_TAIL_REPAIR",
        transformation="Keep raw fade direction; test stricter tail and cost guards before any review promotion.",
        entry_filter="volatility transition low_to_high; h12 fade only; require cost1_pf and tail_pf recovery in new sample.",
        exclusion_rule="Exclude if cost_1_pf<1.10 or tail_pf<1.0 or last5_avg<0 after new events.",
        min_required_new_events=5,
        target_new_events=10,
        min_total_events_for_review=24,
        gate_pf_x4=1.35,
        gate_avg_net_x4=0.25,
        gate_win_rate_x4=0.58,
        gate_tail_pf_x4=1.0,
        gate_cost1_pf_x4=1.10,
        gate_last5_pf_x4=1.0,
        max_drawdown_x4=-30.0,
        kill_switch="If cost/tail remains weak after cheap background collection, kill; do not expand broadly.",
        next_stage_if_pass="STAGE35B_STRICT_VARIANT_BACKTEST",
        next_stage_if_fail="KILL_VOL_TRANS_FADE_REPAIR",
    ))

    # 3) Calendar repair: low priority, strict filters only.
    specs.append(VariantSpec(
        priority=4,
        variant_id="stage35a_calendar_friday_hour_suppression_repair",
        lane="LOW_PRIORITY_CALENDAR_REPAIR",
        source_stage="STAGE34C",
        target_family="calendar_time_risk_proxy_v1",
        target_set="calendar_friday_only_hour_suppression",
        base_candidates="calendar_drop_friday_h9_tp06_sl065;calendar_drop_friday_h13_tp06_sl065",
        variant_type="HOUR_SUPPRESSION_AND_FRIDAY_ONLY_TEST",
        transformation="Test Friday-only repair with weak-hour suppression; no full-family promotion.",
        entry_filter="Friday-only calendar_drop variants; suppress hours whose last5_pf<1.0 and last5_avg<0.",
        exclusion_rule="Exclude Monday raw/inverted and calendar full variants unless new strict recency window recovers.",
        min_required_new_events=8,
        target_new_events=12,
        min_total_events_for_review=32,
        gate_pf_x4=1.35,
        gate_avg_net_x4=0.35,
        gate_win_rate_x4=0.60,
        gate_tail_pf_x4=1.0,
        gate_cost1_pf_x4=1.10,
        gate_last5_pf_x4=1.0,
        max_drawdown_x4=-25.0,
        kill_switch="If Friday-only cannot recover last5 and cost guard, kill calendar repair from fast path.",
        next_stage_if_pass="STAGE35B_STRICT_VARIANT_BACKTEST",
        next_stage_if_fail="KILL_CALENDAR_FAST_PATH_REPAIR",
    ))

    # 4) Follow inverted diagnostic only.
    specs.append(VariantSpec(
        priority=5,
        variant_id="stage35a_vol_trans_follow_inverted_diagnostic_only",
        lane="DIAGNOSTIC_ONLY_INVERSION_CHECK",
        source_stage="STAGE34C",
        target_family="volatility_transition_v1",
        target_set="vol_trans_follow_inverted_diagnostic",
        base_candidates="vol_trans_follow_h1_low_to_high_h12_tp06_sl065;vol_trans_follow_h1_low_to_high_h13_tp06_sl065",
        variant_type="INVERSION_DIAGNOSTIC_ONLY",
        transformation="Invert net direction only for diagnostics; do not promote from this stage.",
        entry_filter="Use inverted follow h12/h13 only as diagnostic; require new evidence before any candidate generation.",
        exclusion_rule="Never promote directly because WR and robustness are insufficient in Stage34B.",
        min_required_new_events=10,
        target_new_events=15,
        min_total_events_for_review=40,
        gate_pf_x4=1.45,
        gate_avg_net_x4=0.50,
        gate_win_rate_x4=0.55,
        gate_tail_pf_x4=1.0,
        gate_cost1_pf_x4=1.10,
        gate_last5_pf_x4=1.0,
        max_drawdown_x4=-30.0,
        kill_switch="If inversion edge is only a retrospective artifact, keep diagnostic-only and kill from fast path.",
        next_stage_if_pass="OPTIONAL_DIAGNOSTIC_REPORT_ONLY",
        next_stage_if_fail="KILL_INVERSION_FAST_PATH",
    ))

    return specs


def generate_priority_plan(specs: List[VariantSpec]) -> List[Dict]:
    rows = []
    for s in specs:
        rows.append({
            "priority": s.priority,
            "variant_id": s.variant_id,
            "lane": s.lane,
            "target_family": s.target_family,
            "target_set": s.target_set,
            "immediate_action": "GENERATE_AND_QUEUE_FOR_STAGE35B" if "DIAGNOSTIC_ONLY" not in s.lane else "KEEP_DIAGNOSTIC_ONLY",
            "min_required_new_events": s.min_required_new_events,
            "target_new_events": s.target_new_events,
            "kill_switch": s.kill_switch,
            "next_stage_if_pass": s.next_stage_if_pass,
            "next_stage_if_fail": s.next_stage_if_fail,
        })
    return rows


def make_markdown(summary: Dict, specs: List[VariantSpec], priority_plan: List[Dict], stage34c_summary: Dict) -> str:
    rows = []
    for s in specs:
        rows.append(
            f"| {s.priority} | {s.variant_id} | {s.lane} | {s.target_family} | {s.min_required_new_events} | {s.next_stage_if_pass} |"
        )
    table = "\n".join(rows)
    return f"""# XAUUSD Stage35A — Targeted Variant Generator

Generated UTC: {summary['generated_utc']}

## Decision

```text
DECISION = {summary['decision']}
EXECUTION_STATUS = {summary['execution_status']}
COMMERCIAL_TRANSITION_AUTHORIZED = {summary['commercial_transition_authorized']}
NO_EA_CHANGE = {summary['no_ea_change']}
NO_PAPER_LIVE = {summary['no_paper_live']}
NO_ORDER_AUTHORIZATION = {summary['no_order_authorization']}
PRIMARY_OBJECTIVE = {summary['primary_objective']}
RECOMMENDED_NEXT_STAGE = {summary['recommended_next_stage']}
```

## Why this stage exists

Stage34C converted the stalled short-confirmation state into a controlled intake expansion plan. Stage35A turns that plan into concrete targeted variant specifications. This is not broad discovery and it does not authorize EA, paper-live, or orders.

## Summary

```text
stage34c_decision = {summary.get('stage34c_decision')}
stage33e_background_active = {summary.get('stage33e_background_active')}
controlled_intake_spec_rows = {summary.get('controlled_intake_spec_rows')}
generated_variant_specs = {summary.get('generated_variant_specs')}
primary_variant_specs = {summary.get('primary_variant_specs')}
secondary_variant_specs = {summary.get('secondary_variant_specs')}
diagnostic_only_specs = {summary.get('diagnostic_only_specs')}
repair_or_kill_enforced_rows = {summary.get('repair_or_kill_enforced_rows')}
```

## Generated variant queue

| priority | variant_id | lane | target_family | min_new_events | next_stage_if_pass |
| --- | --- | --- | --- | ---: | --- |
{table}

## Operational interpretation

```text
1. Stage33E remains background confirmation for h13+h14.
2. Stage35A creates targeted specs now, so the project does not wait passively for a week.
3. Stage35A does not execute trades, paper-live, or EA changes.
4. The immediate next stage is Stage35B strict variant backtest / queue evaluator.
```

## Output files

- `data/reports/stage35a_targeted_variant_generator/stage35a_targeted_variant_generator.md`
- `data/reports/stage35a_targeted_variant_generator/stage35a_summary.json`
- `data/reports/stage35a_targeted_variant_generator/targeted_variant_specs.csv`
- `data/reports/stage35a_targeted_variant_generator/stage35a_priority_plan.csv`
- `data/reports/stage35a_targeted_variant_generator/stage35a_kill_switches.csv`
"""


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stage34c_summary = read_json(STAGE34C_SUMMARY)
    stage33e_summary = read_json(STAGE33E_SUMMARY)
    intake_plan = read_csv(CONTROLLED_INTAKE_PLAN)
    repair_queue = read_csv(REPAIR_OR_KILL_QUEUE)
    background_queue = read_csv(BACKGROUND_QUEUE)

    if stage34c_summary and stage34c_summary.get("decision") != "STAGE34C_CONTROLLED_INTAKE_EXPANSION_ACTIVE_RESEARCH_ONLY":
        decision = "STAGE35A_BLOCKED_STAGE34C_NOT_ACTIVE_RESEARCH_ONLY"
        recommended = "RERUN_STAGE34C_OR_RETURN_TO_STAGE34B_REPAIR_FILTER_LAB"
        specs: List[VariantSpec] = []
    else:
        specs = default_variant_specs(intake_plan, stage33e_summary)
        decision = "STAGE35A_TARGETED_VARIANT_SPECS_READY_RESEARCH_ONLY"
        recommended = "RUN_STAGE35B_STRICT_VARIANT_BACKTEST_QUEUE_EVALUATOR_NO_EA_NO_PAPER_LIVE"

    priority_plan = generate_priority_plan(specs)
    kill_rows = []
    for s in specs:
        kill_rows.append({
            "priority": s.priority,
            "variant_id": s.variant_id,
            "kill_switch": s.kill_switch,
            "fail_action": s.next_stage_if_fail,
            "no_wait_n40": True,
        })

    variant_rows = [asdict(s) for s in specs]
    write_csv(REPORT_DIR / "targeted_variant_specs.csv", variant_rows)
    write_csv(REPORT_DIR / "stage35a_priority_plan.csv", priority_plan)
    write_csv(REPORT_DIR / "stage35a_kill_switches.csv", kill_rows)

    primary = sum(1 for s in specs if s.priority <= 2)
    secondary = sum(1 for s in specs if s.priority in (3, 4))
    diagnostic = sum(1 for s in specs if "DIAGNOSTIC_ONLY" in s.lane or "DIAGNOSTIC" in s.variant_type)

    summary = {
        "generated_utc": utc_now(),
        "decision": decision,
        "execution_status": "RESEARCH_ONLY",
        "commercial_transition_authorized": False,
        "no_ea_change": True,
        "no_paper_live": True,
        "no_order_authorization": True,
        "primary_objective": "TARGETED_VARIANT_GENERATION_TO_AVOID_PASSIVE_WAITING",
        "recommended_next_stage": recommended,
        "stage34c_decision": stage34c_summary.get("decision"),
        "stage33e_background_active": bool(stage33e_summary),
        "controlled_intake_spec_rows": stage34c_summary.get("controlled_intake_spec_rows", len(intake_plan)),
        "generated_variant_specs": len(specs),
        "primary_variant_specs": primary,
        "secondary_variant_specs": secondary,
        "diagnostic_only_specs": diagnostic,
        "repair_or_kill_enforced_rows": stage34c_summary.get("repair_or_kill_enforced_rows", len(repair_queue)),
        "background_queue_rows": stage34c_summary.get("background_queue_rows", len(background_queue)),
        "input_paths": {
            "stage34c_summary": str(STAGE34C_SUMMARY),
            "controlled_intake_plan": str(CONTROLLED_INTAKE_PLAN),
            "stage33e_summary": str(STAGE33E_SUMMARY),
        },
    }

    (REPORT_DIR / "stage35a_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    (REPORT_DIR / "stage35a_targeted_variant_generator.md").write_text(
        make_markdown(summary, specs, priority_plan, stage34c_summary),
        encoding="utf-8",
    )

    print(f"DECISION={summary['decision']}")
    print(f"RECOMMENDED_NEXT_STAGE={summary['recommended_next_stage']}")
    print(f"GENERATED_VARIANT_SPECS={summary['generated_variant_specs']}")
    print(f"REPORT_DIR={REPORT_DIR}")


if __name__ == "__main__":
    main()
