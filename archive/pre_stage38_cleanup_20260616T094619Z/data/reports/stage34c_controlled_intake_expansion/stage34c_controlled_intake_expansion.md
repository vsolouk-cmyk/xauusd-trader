# XAUUSD Stage34C — Controlled Intake Expansion Plan

Generated UTC: 2026-06-15T21:16:09Z

## Decision

```text
DECISION = STAGE34C_CONTROLLED_INTAKE_EXPANSION_ACTIVE_RESEARCH_ONLY
EXECUTION_STATUS = RESEARCH_ONLY
COMMERCIAL_TRANSITION_AUTHORIZED = False
NO_EA_CHANGE = True
NO_PAPER_LIVE = True
NO_ORDER_AUTHORIZATION = True
PRIMARY_OBJECTIVE = CONTROLLED_INTAKE_EXPANSION_TO_REDUCE_TIME_TO_COMMERCIAL_DECISION
RECOMMENDED_NEXT_STAGE = BUILD_STAGE35A_TARGETED_VARIANT_GENERATOR_WHILE_STAGE33E_RUNS_BACKGROUND
```

## Why this stage exists

Stage33E is waiting for a short h13+h14 confirmation batch, and Stage34B found no pre-commercial repair-filter row. Stage34C prevents passive waiting by converting Stage34B's queues into a controlled, kill-switch driven intake expansion plan. It is not general discovery and it does not authorize EA, paper-live, or orders.

## Summary

```text
stage34b_decision = STAGE34B_HAS_SHORT_CONFIRMATION_REPAIR_FILTER_PATH_RESEARCH_ONLY
stage33e_decision = STAGE33E_SHORT_CONFIRMATION_SHADOW_ACTIVE_RESEARCH_ONLY
stage34b_precommercial_rows = 0
stage34b_short_confirmation_rows = 1
stage34b_accelerate_collection_rows = 7
stage34b_repair_or_kill_rows = 22
controlled_intake_spec_rows = 5
repair_or_kill_enforced_rows = 22
```

## Controlled intake plan

| priority | lane | target_family | target_set | action | min_required_new_events | expected_next_stage |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | PRIMARY_SHORT_CONFIRMATION_BACKGROUND | session_handoff_imbalance_v1 | handoff_h13_h14_repaired | KEEP_STAGE33E_CONFIRMATION_ACTIVE | 5 | RERUN_STAGE33D_STAGE33E |
| 2 | TARGETED_REPAIR_VARIANT_GENERATION | session_handoff_imbalance_v1 | handoff_h13_h14_recency_guard_variants | GENERATE_RECENCY_FILTER_TESTS | 5 | STAGE35A_TARGETED_VARIANT_GENERATOR |
| 3 | SECONDARY_ACCELERATION_REPAIR | volatility_transition_v1 | vol_trans_fade_h12_cost_tail_repair | GENERATE_COST_TAIL_FILTER_TESTS | 5 | STAGE35A_TARGETED_VARIANT_GENERATOR |
| 4 | LOW_PRIORITY_CALENDAR_REPAIR | calendar_time_risk_proxy_v1 | calendar_friday_only_hour_suppression | GENERATE_HOUR_SUPPRESSION_AND_FRIDAY_ONLY_TESTS | 8 | STAGE35A_TARGETED_VARIANT_GENERATOR |
| 5 | DIAGNOSTIC_ONLY_INVERSION_CHECK | volatility_transition_v1 | vol_trans_follow_inverted_diagnostic | DIAGNOSTIC_ONLY_DO_NOT_PROMOTE | 10 | OPTIONAL_DIAGNOSTIC_REPORT_ONLY |


## Kill / repair enforcement queue

| priority | set_name | reason | next_action |
| --- | --- | --- | --- |
| 1 | HANDOFF_SINGLE_MEMBER::handoff_align_follow_h14_tp06_sl065 | Single-member handoff is not enough for fast path; keep only through repaired h13+h14 family. | DO_NOT_WAIT_SINGLE_VARIANT_N40 |
| 2 | HANDOFF_SINGLE_MEMBER::handoff_align_follow_h13_tp06_sl065 | Single-member handoff is not enough for fast path; keep only through repaired h13+h14 family. | DO_NOT_WAIT_SINGLE_VARIANT_N40 |
| 3 | VOL_TRANS_FOLLOW_SINGLE_INVERTED::vol_trans_follow_h1_low_to_high_h12_tp06_sl065 | Near-miss but not robust enough for current fast path. | BACKGROUND_DIAGNOSTIC_ONLY |
| 4 | VOL_TRANS_FOLLOW_FULL_INVERTED | Near-miss but not robust enough for current fast path. | BACKGROUND_DIAGNOSTIC_ONLY |
| 5 | CALENDAR_SINGLE_RAW::calendar_drop_friday_h9_tp06_sl065 | Latest-window failure: last5_pf=0.852; no fast-path promotion. | REPAIR_ONLY_WITH_STRICT_RECENCY_FILTER |
| 6 | CALENDAR_MONDAY_ONLY_INVERTED | Near-miss but not robust enough for current fast path. | BACKGROUND_DIAGNOSTIC_ONLY |
| 7 | CALENDAR_SINGLE_INVERTED::calendar_drop_monday_h13_tp06_sl065 | Near-miss but not robust enough for current fast path. | BACKGROUND_DIAGNOSTIC_ONLY |
| 8 | VOL_TRANS_FOLLOW_SINGLE_INVERTED::vol_trans_follow_h1_low_to_high_h13_tp06_sl065 | Near-miss but not robust enough for current fast path. | BACKGROUND_DIAGNOSTIC_ONLY |
| 9 | CALENDAR_SINGLE_INVERTED::calendar_drop_friday_h13_tp06_sl065 | Near-miss but not robust enough for current fast path. | BACKGROUND_DIAGNOSTIC_ONLY |
| 10 | CALENDAR_SINGLE_RAW::calendar_drop_friday_h13_tp06_sl065 | Weak core metrics: pf=0.934, avg=-0.147, wr=0.542. | KILL_OR_REPAIR_ONLY |
| 11 | CALENDAR_FULL_INVERTED | Weak core metrics: pf=0.866, avg=-0.346, wr=0.396. | KILL_OR_REPAIR_ONLY |
| 12 | CALENDAR_FRIDAY_ONLY_INVERTED | Weak core metrics: pf=0.848, avg=-0.387, wr=0.395. | KILL_OR_REPAIR_ONLY |
| 13 | VOL_TRANS_FOLLOW_SINGLE_RAW::vol_trans_follow_h1_low_to_high_h13_tp06_sl065 | Weak core metrics: pf=0.844, avg=-0.474, wr=0.600. | KILL_OR_REPAIR_ONLY |
| 14 | CALENDAR_MONDAY_ONLY_RAW | Weak core metrics: pf=0.818, avg=-0.457, wr=0.500. | KILL_OR_REPAIR_ONLY |
| 15 | CALENDAR_SINGLE_RAW::calendar_drop_monday_h13_tp06_sl065 | Weak core metrics: pf=0.818, avg=-0.457, wr=0.500. | KILL_OR_REPAIR_ONLY |
| 16 | FAMILY_FULL_RAW::volatility_transition_v1 | Weak core metrics: pf=0.793, avg=-0.639, wr=0.586. | KILL_OR_REPAIR_ONLY |
| 17 | CALENDAR_SINGLE_INVERTED::calendar_drop_friday_h9_tp06_sl065 | Weak core metrics: pf=0.780, avg=-0.550, wr=0.458. | KILL_OR_REPAIR_ONLY |
| 18 | VOL_TRANS_FADE_FULL_INVERTED | Weak core metrics: pf=0.770, avg=-0.668, wr=0.316. | KILL_OR_REPAIR_ONLY |
| 19 | VOL_TRANS_FADE_SINGLE_INVERTED::vol_trans_fade_h1_low_to_high_h12_tp06_sl065 | Weak core metrics: pf=0.770, avg=-0.668, wr=0.316. | KILL_OR_REPAIR_ONLY |
| 20 | HANDOFF_SINGLE_MEMBER::handoff_align_follow_h15_tp06_sl065 | Single-member handoff is not enough for fast path; keep only through repaired h13+h14 family. | DO_NOT_WAIT_SINGLE_VARIANT_N40 |


## Background collection queue

| priority | queue | reason | next_check |
| --- | --- | --- | --- |
| 1 | stage33e_h13_h14_short_confirmation | Primary short confirmation path; run via scheduler/background only. | Rerun Stage33D/E after >=5 new h13/h14 events. |
| 2 | stage32f_scheduler | Background collection only; not the main decision path. | Only run wrapper when preflight indicates useful H1 target-hour progress. |


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
