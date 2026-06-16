# XAUUSD Stage34A — Parallel Fast-Path Repair / Intake Gate

Generated UTC: 2026-06-15T20:41:59Z

## Decision

```text
DECISION = STAGE34A_HAS_SHORT_CONFIRMATION_FAST_PATH_RESEARCH_ONLY
EXECUTION_STATUS = RESEARCH_ONLY
COMMERCIAL_TRANSITION_AUTHORIZED = False
NO_EA_CHANGE = True
NO_PAPER_LIVE = True
NO_ORDER_AUTHORIZATION = True
PRIMARY_OBJECTIVE = PARALLEL_REPAIR_INTAKE_TO_REDUCE_TIME_TO_COMMERCIAL_DECISION
RECOMMENDED_NEXT_STAGE = CONTINUE_STAGE33E_CONFIRMATION_AND_REPAIR_FILTERS_IN_PARALLEL
```

## Why this stage exists

Stage33E waits for a short h13+h14 confirmation batch. This stage prevents passive waiting by evaluating repaired sibling groups and alternative dense-family paths in parallel. It is research-only and does not authorize EA, paper-live, or orders.

## Summary

```text
ledger_available = True
ledger_rows = 182
normalized_ledger_rows = 167
member_rows = 9
candidate_set_rows = 8
precommercial_review_rows = 0
short_confirmation_rows = 1
accelerate_collection_rows = 4
repair_or_kill_rows = 4
```

## Parallel acceleration queue

| set_name                                                                    | sibling_group                                                         | candidate_list                                                                                              |   effective_event_count |   good_member_count |   weak_member_count |   pf_x4 |   avg_net_x4 |   win_rate_x4 |   tail_pf_x4 |   cost_1_pf_x4 |   last5_pf_x4 | stage34a_decision                       | next_action                                      |
|:----------------------------------------------------------------------------|:----------------------------------------------------------------------|:------------------------------------------------------------------------------------------------------------|------------------------:|--------------------:|--------------------:|--------:|-------------:|--------------:|-------------:|---------------:|--------------:|:----------------------------------------|:-------------------------------------------------|
| FULL_SIBLING_GROUP                                                          | session_handoff_imbalance_v1::handoff_align_follow_hX_tp06_sl065      | handoff_align_follow_h13_tp06_sl065;handoff_align_follow_h14_tp06_sl065;handoff_align_follow_h15_tp06_sl065 |                      37 |                   2 |                   1 | 1.59058 |     1.13556  |      0.756757 |     0.782163 |       1.06258  |      0.623861 | ACCELERATE_COLLECTION_RESEARCH_ONLY     | KEEP_IN_PARALLEL_COLLECTION_QUEUE                |
| FULL_SIBLING_GROUP                                                          | volatility_transition_v1::vol_trans_fade_hX_low_to_high_hX_tp06_sl065 | vol_trans_fade_h1_low_to_high_h12_tp06_sl065                                                                |                      19 |                   1 |                   0 | 1.29819 |     0.668022 |      0.684211 |     0.564206 |       0.870121 |      0.787645 | ACCELERATE_COLLECTION_RESEARCH_ONLY     | KEEP_IN_PARALLEL_COLLECTION_QUEUE                |
| SINGLE_GOOD_MEMBER_DIAGNOSTIC::vol_trans_fade_h1_low_to_high_h12_tp06_sl065 | volatility_transition_v1::vol_trans_fade_hX_low_to_high_hX_tp06_sl065 | vol_trans_fade_h1_low_to_high_h12_tp06_sl065                                                                |                      19 |                   1 |                   0 | 1.29819 |     0.668022 |      0.684211 |     0.564206 |       0.870121 |      0.787645 | ACCELERATE_COLLECTION_RESEARCH_ONLY     | KEEP_IN_PARALLEL_COLLECTION_QUEUE                |
| GOOD_MEMBERS_ONLY_REPAIR                                                    | session_handoff_imbalance_v1::handoff_align_follow_hX_tp06_sl065      | handoff_align_follow_h13_tp06_sl065;handoff_align_follow_h14_tp06_sl065                                     |                      25 |                   2 |                   0 | 2.72017 |     2.18822  |      0.84     |     2.12412  |       1.82971  |      0.741277 | SHORT_CONFIRMATION_SHADOW_RESEARCH_ONLY | COLLECT_5_TO_10_NEW_EVENTS_THEN_RERUN_STAGE33D_E |

## Repair / kill queue

| set_name                                                           | sibling_group                                                           | candidate_list                                                                                             |   effective_event_count |   pf_x4 |   avg_net_x4 |   win_rate_x4 |   last5_pf_x4 | stage34a_decision            | next_action                        |
|:-------------------------------------------------------------------|:------------------------------------------------------------------------|:-----------------------------------------------------------------------------------------------------------|------------------------:|--------:|-------------:|--------------:|--------------:|:-----------------------------|:-----------------------------------|
| SINGLE_GOOD_MEMBER_DIAGNOSTIC::handoff_align_follow_h14_tp06_sl065 | session_handoff_imbalance_v1::handoff_align_follow_hX_tp06_sl065        | handoff_align_follow_h14_tp06_sl065                                                                        |                      12 | 2.85199 |     2.20266  |      0.833333 |    inf        | REPAIR_OR_KILL_RESEARCH_ONLY | MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT |
| SINGLE_GOOD_MEMBER_DIAGNOSTIC::handoff_align_follow_h13_tp06_sl065 | session_handoff_imbalance_v1::handoff_align_follow_hX_tp06_sl065        | handoff_align_follow_h13_tp06_sl065                                                                        |                      13 | 2.61284 |     2.17489  |      0.846154 |      0.856859 | REPAIR_OR_KILL_RESEARCH_ONLY | MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT |
| FULL_SIBLING_GROUP                                                 | calendar_time_risk_proxy_v1::calendar_drop_WEEKDAY_hX_tp06_sl065        | calendar_drop_friday_h13_tp06_sl065;calendar_drop_friday_h9_tp06_sl065;calendar_drop_monday_h13_tp06_sl065 |                      48 | 1.15448 |     0.345883 |      0.604167 |      0.14562  | REPAIR_OR_KILL_RESEARCH_ONLY | MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT |
| FULL_SIBLING_GROUP                                                 | volatility_transition_v1::vol_trans_follow_hX_low_to_high_hX_tp06_sl065 | vol_trans_follow_h1_low_to_high_h12_tp06_sl065;vol_trans_follow_h1_low_to_high_h13_tp06_sl065              |                      39 | 0.63515 |    -1.27582  |      0.538462 |      0.292155 | REPAIR_OR_KILL_RESEARCH_ONLY | MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT |

## Operational interpretation

```text
1. Do not wait passively for Stage33E; keep scanning repaired sibling groups in parallel.
2. Stage32F remains background collection only.
3. Families that fail this gate should be killed or repaired quickly; no single-variant N=40 waiting by default.
4. No EA/paper-live/order transition is authorized here.
```

## Output files

- `data/reports/stage34a_parallel_fast_path_repair_intake/stage34a_parallel_fast_path_repair_intake.md`
- `data/reports/stage34a_parallel_fast_path_repair_intake/stage34a_summary.json`
- `data/reports/stage34a_parallel_fast_path_repair_intake/candidate_set_diagnostics.csv`
- `data/reports/stage34a_parallel_fast_path_repair_intake/parallel_acceleration_queue.csv`
- `data/reports/stage34a_parallel_fast_path_repair_intake/repair_or_kill_queue.csv`
- `data/reports/stage34a_parallel_fast_path_repair_intake/member_quality_summary.csv`
