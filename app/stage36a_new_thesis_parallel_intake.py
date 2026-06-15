from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path('.')
REPORT_DIR = ROOT / 'data' / 'reports' / 'stage36a_new_thesis_parallel_intake'
STAGE35C_SUMMARY = ROOT / 'data' / 'reports' / 'stage35c_forward_confirmation_trigger_queue_pruner' / 'stage35c_summary.json'
STAGE35B_SUMMARY = ROOT / 'data' / 'reports' / 'stage35b_strict_variant_backtest_queue_evaluator' / 'stage35b_summary.json'
STAGE34C_SUMMARY = ROOT / 'data' / 'reports' / 'stage34c_controlled_intake_expansion' / 'stage34c_summary.json'


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open('r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        f.write('\n')


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys: List[str] = []
        for r in rows:
            for k in r:
                if k not in keys:
                    keys.append(k)
        fieldnames = keys or ['empty']
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in fieldnames})


def md_table(rows: List[Dict[str, Any]], columns: List[str]) -> str:
    if not rows:
        return 'No rows.'
    out = ['| ' + ' | '.join(columns) + ' |', '| ' + ' | '.join(['---'] * len(columns)) + ' |']
    for r in rows:
        out.append('| ' + ' | '.join(str(r.get(c, '')) for c in columns) + ' |')
    return '\n'.join(out)


def build_thesis_branches(stage35c: Dict[str, Any]) -> List[Dict[str, Any]]:
    # These branches intentionally avoid continuing the same dense-family variant-mining branch.
    return [
        {
            'priority': 1,
            'branch_id': 'stage36_session_regime_baseline_scout',
            'thesis_family': 'session_regime_baseline',
            'why_distinct_from_current_branch': 'Uses session-state and day-close/session-close regimes, not handoff h13/h14 sibling mining.',
            'first_test': 'London/NY/session close continuation vs reversal with ATR-normalized stops.',
            'minimum_evidence_before_stage36b': '>= 80 historical events or explicit no-go report',
            'kill_switch': 'Kill if cost-stressed PF < 1.15 or month/period split is unstable.',
            'next_stage': 'STAGE36B_SESSION_REGIME_BASELINE_SCOUT',
            'status': 'START_NOW_PARALLEL',
        },
        {
            'priority': 2,
            'branch_id': 'stage36_news_no_news_regime_guard',
            'thesis_family': 'event_risk_regime',
            'why_distinct_from_current_branch': 'Separates news/no-news and high-impact time windows instead of raw time-of-day variants.',
            'first_test': 'No-trade guard around high-impact windows; compare edge in clean vs event-risk sessions.',
            'minimum_evidence_before_stage36b': '>= 60 clean-window events and explicit event-window exclusion result',
            'kill_switch': 'Kill if excluding event windows does not improve PF, drawdown, or tail behavior.',
            'next_stage': 'STAGE36B_EVENT_RISK_GUARD_SCOUT',
            'status': 'START_NOW_AFTER_SESSION_BASELINE',
        },
        {
            'priority': 3,
            'branch_id': 'stage36_volatility_compression_breakout',
            'thesis_family': 'volatility_state_transition',
            'why_distinct_from_current_branch': 'Uses volatility compression/expansion state, not the current low_to_high transition variants only.',
            'first_test': 'ATR/range compression percentile breakout/fade baseline with strict cost stress.',
            'minimum_evidence_before_stage36b': '>= 80 state-filtered events',
            'kill_switch': 'Kill if last-quartile or cost-stressed PF collapses below 1.10.',
            'next_stage': 'STAGE36B_VOL_COMPRESSION_BREAKOUT_SCOUT',
            'status': 'START_NOW_PARALLEL_IF_CHEAP',
        },
        {
            'priority': 4,
            'branch_id': 'stage36_structure_sweep_reclaim',
            'thesis_family': 'market_structure_sweep_reclaim',
            'why_distinct_from_current_branch': 'Uses previous-day/session high-low sweep and reclaim behavior, not calendar/hour repair.',
            'first_test': 'Prior high/low sweep then reclaim/continuation baseline; ATR stop and fixed horizon variants.',
            'minimum_evidence_before_stage36b': '>= 50 sweep/reclaim events',
            'kill_switch': 'Kill if sweep/reclaim does not outperform simple session baseline.',
            'next_stage': 'STAGE36B_STRUCTURE_SWEEP_RECLAIM_SCOUT',
            'status': 'START_NOW_PARALLEL_IF_DATA_FIELDS_AVAILABLE',
        },
        {
            'priority': 5,
            'branch_id': 'stage36_broker_cost_window_guard',
            'thesis_family': 'execution_cost_microstructure',
            'why_distinct_from_current_branch': 'Tests whether broker/spread/time windows are the blocker before more strategy mining.',
            'first_test': 'Hour/session cost guard overlay; compare existing candidates under strict spread/slippage penalty.',
            'minimum_evidence_before_stage36b': 'Use all existing ledger rows plus new forward rows',
            'kill_switch': 'Kill strategy branches whose edge disappears under realistic broker cost windows.',
            'next_stage': 'STAGE36B_COST_WINDOW_GUARD_SCOUT',
            'status': 'START_NOW_PARALLEL',
        },
    ]


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    generated = utc_now()
    stage35c = read_json(STAGE35C_SUMMARY)
    stage35b = read_json(STAGE35B_SUMMARY)
    stage34c = read_json(STAGE34C_SUMMARY)

    new_signal_count = int(stage35c.get('new_signal_count', 0) or 0)
    min_new_events = int(stage35c.get('min_new_events', 5) or 5)
    current_branch_pending = new_signal_count < min_new_events
    promotion_allowed_now = bool(stage35c.get('promotion_allowed_now', False))

    branches = build_thesis_branches(stage35c)
    kill_switches = [
        {
            'priority': r['priority'],
            'branch_id': r['branch_id'],
            'kill_switch': r['kill_switch'],
            'commercial_rule': 'NO_EA_NO_PAPER_NO_ORDER_UNTIL_STRICT_FORWARD_AND_COST_GATES_PASS',
        }
        for r in branches
    ]
    scheduler_plan = [
        {
            'priority': 1,
            'scheduler_item': 'stage35c_forward_confirmation_trigger',
            'cadence': 'every scheduler run after useful wrapper refresh or low-cost check',
            'condition': 'new_signal_count >= min_new_events triggers rerun Stage33D/E/35B',
            'action_now': 'KEEP_ACTIVE_BACKGROUND_TRIGGER',
        },
        {
            'priority': 2,
            'scheduler_item': 'stage36a_new_thesis_parallel_intake',
            'cadence': 'daily or first missing report',
            'condition': 'current branch pending or no strict review-ready candidate',
            'action_now': 'START_NEW_THESIS_BRANCH_NOW',
        },
        {
            'priority': 3,
            'scheduler_item': 'stage36b_first_branch_backtest',
            'cadence': 'manual next patch or scheduled after Stage36B exists',
            'condition': 'Stage36A branch specs ready',
            'action_now': 'BUILD_STAGE36B_SESSION_REGIME_BASELINE_SCOUT_NEXT',
        },
    ]

    if current_branch_pending and not promotion_allowed_now:
        decision = 'STAGE36A_START_NEW_THESIS_BRANCHES_WHILE_STAGE35C_WAITS_RESEARCH_ONLY'
        recommended = 'BUILD_STAGE36B_SESSION_REGIME_BASELINE_SCOUT_AND_KEEP_STAGE35C_SCHEDULED'
    elif promotion_allowed_now:
        decision = 'STAGE36A_DEFER_NEW_BRANCH_RERUN_CONFIRMATION_FIRST_RESEARCH_ONLY'
        recommended = 'RERUN_STAGE33D_STAGE33E_STAGE35B_BEFORE_STAGE36B'
    else:
        decision = 'STAGE36A_NEW_THESIS_BRANCHES_READY_RESEARCH_ONLY'
        recommended = 'BUILD_STAGE36B_SESSION_REGIME_BASELINE_SCOUT'

    summary = {
        'generated_utc': generated,
        'decision': decision,
        'execution_status': 'RESEARCH_ONLY',
        'commercial_transition_authorized': False,
        'no_ea_change': True,
        'no_paper_live': True,
        'no_order_authorization': True,
        'primary_objective': 'START_DISTINCT_THESIS_BRANCH_NOW_WHILE_PENDING_CONFIRMATION_RUNS_BACKGROUND',
        'recommended_next_stage': recommended,
        'stage35c_decision': stage35c.get('decision', ''),
        'stage35b_decision': stage35b.get('decision', ''),
        'stage34c_decision': stage34c.get('decision', ''),
        'new_signal_count': new_signal_count,
        'min_new_events': min_new_events,
        'current_branch_pending': current_branch_pending,
        'promotion_allowed_now': promotion_allowed_now,
        'thesis_branch_rows': len(branches),
        'scheduler_plan_rows': len(scheduler_plan),
        'next_branch_priority': 'stage36_session_regime_baseline_scout',
    }

    write_json(REPORT_DIR / 'stage36a_summary.json', summary)
    write_csv(REPORT_DIR / 'stage36a_thesis_branches.csv', branches)
    write_csv(REPORT_DIR / 'stage36a_kill_switches.csv', kill_switches)
    write_csv(REPORT_DIR / 'stage36a_scheduler_plan.csv', scheduler_plan)

    md = f"""# XAUUSD Stage36A — New Thesis Parallel Intake
Generated UTC: {generated}

## Decision

DECISION = {decision}
EXECUTION_STATUS = RESEARCH_ONLY
COMMERCIAL_TRANSITION_AUTHORIZED = False
NO_EA_CHANGE = True
NO_PAPER_LIVE = True
NO_ORDER_AUTHORIZATION = True
PRIMARY_OBJECTIVE = START_DISTINCT_THESIS_BRANCH_NOW_WHILE_PENDING_CONFIRMATION_RUNS_BACKGROUND
RECOMMENDED_NEXT_STAGE = {recommended}

## Why this stage exists

Stage35C keeps the current h13/h14 path alive only as a background forward-confirmation trigger. Waiting several days without starting a distinct thesis branch is not aligned with the commercial fast path. Stage36A starts a separate, non-overlapping thesis intake now.

## Summary

stage35c_decision = {summary['stage35c_decision']}
stage35b_decision = {summary['stage35b_decision']}
stage34c_decision = {summary['stage34c_decision']}
new_signal_count = {new_signal_count}
min_new_events = {min_new_events}
current_branch_pending = {current_branch_pending}
promotion_allowed_now = {promotion_allowed_now}
thesis_branch_rows = {len(branches)}

## Thesis branches

{md_table(branches, ['priority', 'branch_id', 'thesis_family', 'first_test', 'next_stage', 'status'])}

## Scheduler plan

{md_table(scheduler_plan, ['priority', 'scheduler_item', 'cadence', 'condition', 'action_now'])}

## Operational interpretation

1. The current h13/h14 branch is not killed; it stays in Stage35C background trigger mode.
2. A new thesis branch starts immediately because the current branch may take days and may still fail.
3. This is not a continuation of the same variant-mining branch.
4. No EA, paper-live, or order transition is authorized here.

## Output files

- `data/reports/stage36a_new_thesis_parallel_intake/stage36a_new_thesis_parallel_intake.md`
- `data/reports/stage36a_new_thesis_parallel_intake/stage36a_summary.json`
- `data/reports/stage36a_new_thesis_parallel_intake/stage36a_thesis_branches.csv`
- `data/reports/stage36a_new_thesis_parallel_intake/stage36a_kill_switches.csv`
- `data/reports/stage36a_new_thesis_parallel_intake/stage36a_scheduler_plan.csv`
"""
    (REPORT_DIR / 'stage36a_new_thesis_parallel_intake.md').write_text(md, encoding='utf-8')

    print(f"DECISION={decision}")
    print(f"RECOMMENDED_NEXT_STAGE={recommended}")
    print(f"CURRENT_BRANCH_PENDING={current_branch_pending}")
    print(f"NEW_SIGNAL_COUNT={new_signal_count}")
    print(f"MIN_NEW_EVENTS={min_new_events}")
    print(f"THESIS_BRANCH_ROWS={len(branches)}")
    print(f"REPORT={REPORT_DIR / 'stage36a_new_thesis_parallel_intake.md'}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
