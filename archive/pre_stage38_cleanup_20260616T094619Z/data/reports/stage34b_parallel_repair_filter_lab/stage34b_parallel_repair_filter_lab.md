# XAUUSD Stage34B — Parallel Repair / Filter Lab

Generated UTC: 2026-06-15T21:03:03Z

## Decision

```text
DECISION = STAGE34B_HAS_SHORT_CONFIRMATION_REPAIR_FILTER_PATH_RESEARCH_ONLY
EXECUTION_STATUS = RESEARCH_ONLY
COMMERCIAL_TRANSITION_AUTHORIZED = False
NO_EA_CHANGE = True
NO_PAPER_LIVE = True
NO_ORDER_AUTHORIZATION = True
PRIMARY_OBJECTIVE = PARALLEL_REPAIR_FILTER_LAB_TO_REDUCE_TIME_TO_COMMERCIAL_DECISION
RECOMMENDED_NEXT_STAGE = CONTINUE_SHORT_CONFIRMATION_AND_PARALLEL_ACCELERATION_NO_EA_NO_PAPER_LIVE
```

## Why this stage exists

Stage33E waits for short confirmation on h13+h14. Stage34B prevents passive waiting by testing repaired subsets, inversion ideas, and alternative dense-family filters from the existing ledger. This is research-only and does not authorize EA, paper-live, or orders.

## Summary

```text
ledger_available = True
ledger_rows = 167
candidate_set_rows = 30
precommercial_repair_filter_rows = 0
short_confirmation_rows = 1
accelerate_collection_rows = 7
repair_or_kill_rows = 22
```

## Pre-commercial repair-filter queue

No rows.

## Short confirmation repair-filter queue

| set_name                              | purpose                      | candidate_list                                                          | invert_net   |   effective_event_count |   good_member_count |   weak_member_count |   pf_x4 |   avg_net_x4 |   win_rate_x4 |   tail_pf_x4 |   cost_1_pf_x4 |   last5_pf_x4 |   last5_avg_net_x4 |   max_drawdown_x4 | stage34b_decision                       | next_action                                        |
|:--------------------------------------|:-----------------------------|:------------------------------------------------------------------------|:-------------|------------------------:|--------------------:|--------------------:|--------:|-------------:|--------------:|-------------:|---------------:|--------------:|-------------------:|------------------:|:----------------------------------------|:---------------------------------------------------|
| HANDOFF_REPAIRED_H13_H14_CONFIRMATION | short_confirmation_reference | handoff_align_follow_h13_tp06_sl065;handoff_align_follow_h14_tp06_sl065 | False        |                      25 |                   2 |                   0 | 2.72017 |      2.18822 |          0.84 |      2.12412 |        1.82971 |      0.741277 |            -0.9071 |          -11.8581 | SHORT_CONFIRMATION_SHADOW_RESEARCH_ONLY | COLLECT_SHORT_CONFIRMATION_OR_APPLY_RECENCY_FILTER |

## Parallel acceleration queue

| set_name                                                                | purpose           | candidate_list                                                                                              | invert_net   |   effective_event_count |   good_member_count |   weak_member_count |   pf_x4 |   avg_net_x4 |   win_rate_x4 |   tail_pf_x4 |   cost_1_pf_x4 |   last5_pf_x4 |   last5_avg_net_x4 |   max_drawdown_x4 | stage34b_decision                   | next_action                       |
|:------------------------------------------------------------------------|:------------------|:------------------------------------------------------------------------------------------------------------|:-------------|------------------------:|--------------------:|--------------------:|--------:|-------------:|--------------:|-------------:|---------------:|--------------:|-------------------:|------------------:|:------------------------------------|:----------------------------------|
| HANDOFF_FULL_H13_H14_H15                                                | monitor_reference | handoff_align_follow_h13_tp06_sl065;handoff_align_follow_h14_tp06_sl065;handoff_align_follow_h15_tp06_sl065 | False        |                      37 |                   2 |                   1 | 1.59058 |     1.13556  |      0.756757 |     0.782163 |       1.06258  |      0.623861 |          -1.36877  |          -30.6985 | ACCELERATE_COLLECTION_RESEARCH_ONLY | KEEP_IN_PARALLEL_COLLECTION_QUEUE |
| FAMILY_FULL_RAW::session_handoff_imbalance_v1                           | family_reference  | handoff_align_follow_h13_tp06_sl065;handoff_align_follow_h14_tp06_sl065;handoff_align_follow_h15_tp06_sl065 | False        |                      37 |                   2 |                   1 | 1.59058 |     1.13556  |      0.756757 |     0.782163 |       1.06258  |      0.623861 |          -1.36877  |          -30.6985 | ACCELERATE_COLLECTION_RESEARCH_ONLY | KEEP_IN_PARALLEL_COLLECTION_QUEUE |
| VOL_TRANS_FADE_FULL_RAW                                                 | volatility_repair | vol_trans_fade_h1_low_to_high_h12_tp06_sl065                                                                | False        |                      19 |                   1 |                   0 | 1.29819 |     0.668022 |      0.684211 |     0.564206 |       0.870121 |      0.787645 |          -0.720305 |          -30.6835 | ACCELERATE_COLLECTION_RESEARCH_ONLY | KEEP_IN_PARALLEL_COLLECTION_QUEUE |
| VOL_TRANS_FADE_SINGLE_RAW::vol_trans_fade_h1_low_to_high_h12_tp06_sl065 | volatility_single | vol_trans_fade_h1_low_to_high_h12_tp06_sl065                                                                | False        |                      19 |                   1 |                   0 | 1.29819 |     0.668022 |      0.684211 |     0.564206 |       0.870121 |      0.787645 |          -0.720305 |          -30.6835 | ACCELERATE_COLLECTION_RESEARCH_ONLY | KEEP_IN_PARALLEL_COLLECTION_QUEUE |
| CALENDAR_FRIDAY_ONLY_RAW                                                | calendar_repair   | calendar_drop_friday_h13_tp06_sl065;calendar_drop_friday_h9_tp06_sl065                                      | False        |                      43 |                   0 |                   1 | 1.1793  |     0.387466 |      0.604651 |     0.807625 |       0.760385 |      0.661361 |          -1.11937  |          -21.4815 | ACCELERATE_COLLECTION_RESEARCH_ONLY | KEEP_IN_PARALLEL_COLLECTION_QUEUE |
| CALENDAR_FULL_RAW                                                       | calendar_repair   | calendar_drop_friday_h13_tp06_sl065;calendar_drop_friday_h9_tp06_sl065;calendar_drop_monday_h13_tp06_sl065  | False        |                      48 |                   0 |                   2 | 1.15448 |     0.345883 |      0.604167 |     0.492105 |       0.751745 |      0.14562  |          -4.22063  |          -26.7012 | ACCELERATE_COLLECTION_RESEARCH_ONLY | KEEP_IN_PARALLEL_COLLECTION_QUEUE |
| FAMILY_FULL_RAW::calendar_time_risk_proxy_v1                            | family_reference  | calendar_drop_friday_h13_tp06_sl065;calendar_drop_friday_h9_tp06_sl065;calendar_drop_monday_h13_tp06_sl065  | False        |                      48 |                   0 |                   2 | 1.15448 |     0.345883 |      0.604167 |     0.492105 |       0.751745 |      0.14562  |          -4.22063  |          -26.7012 | ACCELERATE_COLLECTION_RESEARCH_ONLY | KEEP_IN_PARALLEL_COLLECTION_QUEUE |

## Repair / kill queue

| set_name                                                                         | candidate_list                                                                                                                             | invert_net   |   effective_event_count |    pf_x4 |   avg_net_x4 |   win_rate_x4 |   last5_pf_x4 | stage34b_decision            | next_action                        |
|:---------------------------------------------------------------------------------|:-------------------------------------------------------------------------------------------------------------------------------------------|:-------------|------------------------:|---------:|-------------:|--------------:|--------------:|:-----------------------------|:-----------------------------------|
| HANDOFF_SINGLE_MEMBER::handoff_align_follow_h14_tp06_sl065                       | handoff_align_follow_h14_tp06_sl065                                                                                                        | False        |                      12 | 2.85199  |     2.20266  |      0.833333 |    inf        | REPAIR_OR_KILL_RESEARCH_ONLY | MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT |
| HANDOFF_SINGLE_MEMBER::handoff_align_follow_h13_tp06_sl065                       | handoff_align_follow_h13_tp06_sl065                                                                                                        | False        |                      13 | 2.61284  |     2.17489  |      0.846154 |      0.856859 | REPAIR_OR_KILL_RESEARCH_ONLY | MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT |
| VOL_TRANS_FOLLOW_SINGLE_INVERTED::vol_trans_follow_h1_low_to_high_h12_tp06_sl065 | vol_trans_follow_h1_low_to_high_h12_tp06_sl065                                                                                             | True         |                      19 | 2.13644  |     2.11948  |      0.526316 |      1.1908   | REPAIR_OR_KILL_RESEARCH_ONLY | MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT |
| VOL_TRANS_FOLLOW_FULL_INVERTED                                                   | vol_trans_follow_h1_low_to_high_h12_tp06_sl065;vol_trans_follow_h1_low_to_high_h13_tp06_sl065                                              | True         |                      39 | 1.57443  |     1.27582  |      0.461538 |      3.42284  | REPAIR_OR_KILL_RESEARCH_ONLY | MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT |
| CALENDAR_SINGLE_RAW::calendar_drop_friday_h9_tp06_sl065                          | calendar_drop_friday_h9_tp06_sl065                                                                                                         | False        |                      24 | 1.28285  |     0.549791 |      0.541667 |      0.852449 | REPAIR_OR_KILL_RESEARCH_ONLY | MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT |
| CALENDAR_MONDAY_ONLY_INVERTED                                                    | calendar_drop_monday_h13_tp06_sl065                                                                                                        | True         |                      24 | 1.22322  |     0.456615 |      0.5      |      7.29193  | REPAIR_OR_KILL_RESEARCH_ONLY | MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT |
| CALENDAR_SINGLE_INVERTED::calendar_drop_monday_h13_tp06_sl065                    | calendar_drop_monday_h13_tp06_sl065                                                                                                        | True         |                      24 | 1.22322  |     0.456615 |      0.5      |      7.29193  | REPAIR_OR_KILL_RESEARCH_ONLY | MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT |
| VOL_TRANS_FOLLOW_SINGLE_INVERTED::vol_trans_follow_h1_low_to_high_h13_tp06_sl065 | vol_trans_follow_h1_low_to_high_h13_tp06_sl065                                                                                             | True         |                      20 | 1.18535  |     0.474349 |      0.4      |      9.81847  | REPAIR_OR_KILL_RESEARCH_ONLY | MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT |
| CALENDAR_SINGLE_INVERTED::calendar_drop_friday_h13_tp06_sl065                    | calendar_drop_friday_h13_tp06_sl065                                                                                                        | True         |                      24 | 1.07105  |     0.147248 |      0.458333 |      2.58837  | REPAIR_OR_KILL_RESEARCH_ONLY | MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT |
| CALENDAR_SINGLE_RAW::calendar_drop_friday_h13_tp06_sl065                         | calendar_drop_friday_h13_tp06_sl065                                                                                                        | False        |                      24 | 0.933662 |    -0.147248 |      0.541667 |      0.386344 | REPAIR_OR_KILL_RESEARCH_ONLY | MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT |
| CALENDAR_FULL_INVERTED                                                           | calendar_drop_friday_h13_tp06_sl065;calendar_drop_friday_h9_tp06_sl065;calendar_drop_monday_h13_tp06_sl065                                 | True         |                      48 | 0.866191 |    -0.345883 |      0.395833 |      6.86719  | REPAIR_OR_KILL_RESEARCH_ONLY | MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT |
| CALENDAR_FRIDAY_ONLY_INVERTED                                                    | calendar_drop_friday_h13_tp06_sl065;calendar_drop_friday_h9_tp06_sl065                                                                     | True         |                      43 | 0.84796  |    -0.387466 |      0.395349 |      1.51203  | REPAIR_OR_KILL_RESEARCH_ONLY | MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT |
| VOL_TRANS_FOLLOW_SINGLE_RAW::vol_trans_follow_h1_low_to_high_h13_tp06_sl065      | vol_trans_follow_h1_low_to_high_h13_tp06_sl065                                                                                             | False        |                      20 | 0.843633 |    -0.474349 |      0.6      |      0.101849 | REPAIR_OR_KILL_RESEARCH_ONLY | MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT |
| CALENDAR_MONDAY_ONLY_RAW                                                         | calendar_drop_monday_h13_tp06_sl065                                                                                                        | False        |                      24 | 0.817511 |    -0.456615 |      0.5      |      0.137138 | REPAIR_OR_KILL_RESEARCH_ONLY | MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT |
| CALENDAR_SINGLE_RAW::calendar_drop_monday_h13_tp06_sl065                         | calendar_drop_monday_h13_tp06_sl065                                                                                                        | False        |                      24 | 0.817511 |    -0.456615 |      0.5      |      0.137138 | REPAIR_OR_KILL_RESEARCH_ONLY | MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT |
| FAMILY_FULL_RAW::volatility_transition_v1                                        | vol_trans_fade_h1_low_to_high_h12_tp06_sl065;vol_trans_follow_h1_low_to_high_h12_tp06_sl065;vol_trans_follow_h1_low_to_high_h13_tp06_sl065 | False        |                      58 | 0.792868 |    -0.639045 |      0.586207 |      0.657557 | REPAIR_OR_KILL_RESEARCH_ONLY | MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT |
| CALENDAR_SINGLE_INVERTED::calendar_drop_friday_h9_tp06_sl065                     | calendar_drop_friday_h9_tp06_sl065                                                                                                         | True         |                      24 | 0.779513 |    -0.549791 |      0.458333 |      1.17309  | REPAIR_OR_KILL_RESEARCH_ONLY | MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT |
| VOL_TRANS_FADE_FULL_INVERTED                                                     | vol_trans_fade_h1_low_to_high_h12_tp06_sl065                                                                                               | True         |                      19 | 0.770304 |    -0.668022 |      0.315789 |      1.26961  | REPAIR_OR_KILL_RESEARCH_ONLY | MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT |
| VOL_TRANS_FADE_SINGLE_INVERTED::vol_trans_fade_h1_low_to_high_h12_tp06_sl065     | vol_trans_fade_h1_low_to_high_h12_tp06_sl065                                                                                               | True         |                      19 | 0.770304 |    -0.668022 |      0.315789 |      1.26961  | REPAIR_OR_KILL_RESEARCH_ONLY | MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT |
| HANDOFF_SINGLE_MEMBER::handoff_align_follow_h15_tp06_sl065                       | handoff_align_follow_h15_tp06_sl065                                                                                                        | False        |                      12 | 0.677438 |    -1.05749  |      0.583333 |      0.567823 | REPAIR_OR_KILL_RESEARCH_ONLY | MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT |
| VOL_TRANS_FOLLOW_FULL_RAW                                                        | vol_trans_follow_h1_low_to_high_h12_tp06_sl065;vol_trans_follow_h1_low_to_high_h13_tp06_sl065                                              | False        |                      39 | 0.63515  |    -1.27582  |      0.538462 |      0.292155 | REPAIR_OR_KILL_RESEARCH_ONLY | MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT |
| VOL_TRANS_FOLLOW_SINGLE_RAW::vol_trans_follow_h1_low_to_high_h12_tp06_sl065      | vol_trans_follow_h1_low_to_high_h12_tp06_sl065                                                                                             | False        |                      19 | 0.468069 |    -2.11948  |      0.473684 |      0.839769 | REPAIR_OR_KILL_RESEARCH_ONLY | MOVE_TO_REPAIR_OR_KILL_DO_NOT_WAIT |

## Action plan

|   priority | action                               | rationale                                                                       | execution_status   |
|-----------:|:-------------------------------------|:--------------------------------------------------------------------------------|:-------------------|
|          2 | KEEP_SHORT_CONFIRMATION_PATHS_ACTIVE | Core metrics are promising but recency/last5 is not yet safe.                   | RESEARCH_ONLY      |
|          3 | KEEP_PARALLEL_ACCELERATION_QUEUE     | Some paths are positive but not review-ready; collect only if cheap/background. | RESEARCH_ONLY      |
|          4 | KILL_OR_REPAIR_WEAK_PATHS            | Do not wait for weak or single-variant paths to reach N=40 by default.          | RESEARCH_ONLY      |

## Operational interpretation

```text
1. Stage33E remains the main confirmation path for h13+h14, but Stage34B runs repair/intake diagnostics in parallel.
2. No path here authorizes EA, paper-live, or orders.
3. If no pre-commercial repair-filter candidate exists, do not wait passively; keep only cheap background collection and start controlled intake expansion.
4. Weak paths should be killed or repaired quickly; no default single-variant N=40 waiting.
```

## Output files

- `data/reports/stage34b_parallel_repair_filter_lab/stage34b_parallel_repair_filter_lab.md`
- `data/reports/stage34b_parallel_repair_filter_lab/stage34b_summary.json`
- `data/reports/stage34b_parallel_repair_filter_lab/repair_filter_candidate_diagnostics.csv`
- `data/reports/stage34b_parallel_repair_filter_lab/precommercial_repair_filter_queue.csv`
- `data/reports/stage34b_parallel_repair_filter_lab/short_confirmation_repair_filter_queue.csv`
- `data/reports/stage34b_parallel_repair_filter_lab/parallel_acceleration_queue.csv`
- `data/reports/stage34b_parallel_repair_filter_lab/repair_or_kill_queue.csv`
- `data/reports/stage34b_parallel_repair_filter_lab/stage34b_action_plan.csv`
