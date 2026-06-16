# XAUUSD Stage36A — New Thesis Parallel Intake
Generated UTC: 2026-06-16T04:16:13Z

## Decision

DECISION = STAGE36A_START_NEW_THESIS_BRANCHES_WHILE_STAGE35C_WAITS_RESEARCH_ONLY
EXECUTION_STATUS = RESEARCH_ONLY
COMMERCIAL_TRANSITION_AUTHORIZED = False
NO_EA_CHANGE = True
NO_PAPER_LIVE = True
NO_ORDER_AUTHORIZATION = True
PRIMARY_OBJECTIVE = START_DISTINCT_THESIS_BRANCH_NOW_WHILE_PENDING_CONFIRMATION_RUNS_BACKGROUND
RECOMMENDED_NEXT_STAGE = BUILD_STAGE36B_SESSION_REGIME_BASELINE_SCOUT_AND_KEEP_STAGE35C_SCHEDULED

## Why this stage exists

Stage35C keeps the current h13/h14 path alive only as a background forward-confirmation trigger. Waiting several days without starting a distinct thesis branch is not aligned with the commercial fast path. Stage36A starts a separate, non-overlapping thesis intake now.

## Summary

stage35c_decision = STAGE35C_WAIT_FOR_MORE_FORWARD_EVENTS_RESEARCH_ONLY
stage35b_decision = STAGE35B_VARIANTS_PENDING_FORWARD_CONFIRMATION_RESEARCH_ONLY
stage34c_decision = STAGE34C_CONTROLLED_INTAKE_EXPANSION_ACTIVE_RESEARCH_ONLY
new_signal_count = 1
min_new_events = 5
current_branch_pending = True
promotion_allowed_now = False
thesis_branch_rows = 5

## Thesis branches

| priority | branch_id | thesis_family | first_test | next_stage | status |
| --- | --- | --- | --- | --- | --- |
| 1 | stage36_session_regime_baseline_scout | session_regime_baseline | London/NY/session close continuation vs reversal with ATR-normalized stops. | STAGE36B_SESSION_REGIME_BASELINE_SCOUT | START_NOW_PARALLEL |
| 2 | stage36_news_no_news_regime_guard | event_risk_regime | No-trade guard around high-impact windows; compare edge in clean vs event-risk sessions. | STAGE36B_EVENT_RISK_GUARD_SCOUT | START_NOW_AFTER_SESSION_BASELINE |
| 3 | stage36_volatility_compression_breakout | volatility_state_transition | ATR/range compression percentile breakout/fade baseline with strict cost stress. | STAGE36B_VOL_COMPRESSION_BREAKOUT_SCOUT | START_NOW_PARALLEL_IF_CHEAP |
| 4 | stage36_structure_sweep_reclaim | market_structure_sweep_reclaim | Prior high/low sweep then reclaim/continuation baseline; ATR stop and fixed horizon variants. | STAGE36B_STRUCTURE_SWEEP_RECLAIM_SCOUT | START_NOW_PARALLEL_IF_DATA_FIELDS_AVAILABLE |
| 5 | stage36_broker_cost_window_guard | execution_cost_microstructure | Hour/session cost guard overlay; compare existing candidates under strict spread/slippage penalty. | STAGE36B_COST_WINDOW_GUARD_SCOUT | START_NOW_PARALLEL |

## Scheduler plan

| priority | scheduler_item | cadence | condition | action_now |
| --- | --- | --- | --- | --- |
| 1 | stage35c_forward_confirmation_trigger | every scheduler run after useful wrapper refresh or low-cost check | new_signal_count >= min_new_events triggers rerun Stage33D/E/35B | KEEP_ACTIVE_BACKGROUND_TRIGGER |
| 2 | stage36a_new_thesis_parallel_intake | daily or first missing report | current branch pending or no strict review-ready candidate | START_NEW_THESIS_BRANCH_NOW |
| 3 | stage36b_first_branch_backtest | manual next patch or scheduled after Stage36B exists | Stage36A branch specs ready | BUILD_STAGE36B_SESSION_REGIME_BASELINE_SCOUT_NEXT |

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
