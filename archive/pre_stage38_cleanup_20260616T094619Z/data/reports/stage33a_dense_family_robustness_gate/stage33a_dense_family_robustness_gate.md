# XAUUSD Stage33A — Dense Family Robustness & Sample Acceleration Gate

Generated UTC: 2026-06-15T19:42:49Z

## Decision

```text
DECISION = STAGE33A_HAS_FAMILY_PRE_COMMERCIAL_ACCELERATION_REVIEW_RESEARCH_ONLY
EXECUTION_STATUS = RESEARCH_ONLY
COMMERCIAL_TRANSITION_AUTHORIZED = False
NO_EA_CHANGE = True
NO_PAPER_LIVE = True
NO_ORDER_AUTHORIZATION = True
PRIMARY_OBJECTIVE = REDUCE_TIME_TO_DECISION_USING_DENSE_FAMILY_ROBUSTNESS_NOT_SINGLE_VARIANT_WAITING
RECOMMENDED_NEXT_STAGE = RUN_STAGE33B_PRE_COMMERCIAL_FAMILY_ROBUSTNESS_GATE
```

## Why this stage exists

Stage32F is intentionally slow because it waits for single-variant forward samples. Stage33A tests whether sibling variants can be treated as a robust family so the project can reduce time-to-decision without authorizing execution.

## Summary

```text
candidate_rows = 9
family_group_rows = 4
acceleration_queue_rows = 1
pre_commercial_family_review_rows = 1
accelerate_diagnostics_rows = 0
repair_or_kill_rows = 2
min_family_effective_signals = 24
min_good_siblings = 2
min_family_pf_x4 = 1.35
min_family_win_rate = 0.58
```

## Family robustness summary

|   rank | sibling_group                                                           | families                     |   member_count | candidate_list                                                                                   | hours    | weekdays      |   raw_signal_sum |   max_member_signals |   effective_signal_count | evidence_basis                   |   good_sibling_count |   secondary_sibling_count |   weak_or_repair_count |   family_pf_x4 |   family_avg_net_x4 |   family_win_rate_x4 |   family_tail_pf_x4 |   family_max_drawdown_x4 | stage33a_decision                                       | next_action                                                          |
|-------:|:------------------------------------------------------------------------|:-----------------------------|---------------:|:-------------------------------------------------------------------------------------------------|:---------|:--------------|-----------------:|---------------------:|-------------------------:|:---------------------------------|---------------------:|--------------------------:|-----------------------:|---------------:|--------------------:|---------------------:|--------------------:|-------------------------:|:--------------------------------------------------------|:---------------------------------------------------------------------|
|      1 | session_handoff_imbalance_v1::handoff_align_follow_hX_tp06_sl065        | session_handoff_imbalance_v1 |              3 | handoff_align_follow_h13_tp06_sl065;handoff_align_follow_h14_tp06_sl065;handoff_align_follow_... | 13,14,15 | none          |               42 |                   14 |                       42 | ledger_dedup_timestamp_direction |                    2 |                         0 |                      1 |       2.04742  |            1.10669  |             0.754273 |            2.66571  |                 -18.8404 | FAMILY_PRE_COMMERCIAL_ACCELERATION_REVIEW_RESEARCH_ONLY | RUN_STAGE33B_PRE_COMMERCIAL_ROBUSTNESS_ON_FAMILY_NO_EA_NO_PAPER_LIVE |
|      2 | volatility_transition_v1::vol_trans_fade_hX_low_to_high_hX_tp06_sl065   | volatility_transition_v1     |              1 | vol_trans_fade_h1_low_to_high_h12_tp06_sl065                                                     | 1        | none          |               21 |                   21 |                       21 | ledger_dedup_timestamp_direction |                    0 |                         1 |                      0 |       1.29819  |            0.668022 |             0.684211 |            0.564206 |                 -30.6835 | KEEP_BACKGROUND_COLLECTION_ONLY                         | DO_NOT_WAIT_FOR_THIS_FAMILY_AS_PRIMARY_FAST_PATH                     |
|      3 | calendar_time_risk_proxy_v1::calendar_drop_WEEKDAY_hX_tp06_sl065        | calendar_time_risk_proxy_v1  |              3 | calendar_drop_friday_h13_tp06_sl065;calendar_drop_friday_h9_tp06_sl065;calendar_drop_monday_h... | 9,13     | friday,monday |               76 |                   26 |                       76 | ledger_dedup_timestamp_direction |                    0 |                         1 |                      2 |       1.01644  |           -0.006482 |             0.528509 |            1.15843  |                 -33.0784 | FAMILY_REPAIR_OR_KILL_CANDIDATE                         | MOVE_TO_REPAIR_OR_KILL_IF_NEXT_BATCH_NOT_IMPROVED                    |
|      4 | volatility_transition_v1::vol_trans_follow_hX_low_to_high_hX_tp06_sl065 | volatility_transition_v1     |              2 | vol_trans_follow_h1_low_to_high_h12_tp06_sl065;vol_trans_follow_h1_low_to_high_h13_tp06_sl065    | 1        | none          |               43 |                   22 |                       43 | ledger_dedup_timestamp_direction |                    0 |                         0 |                      2 |       0.660218 |           -1.27778  |             0.538311 |            0.548143 |                 -45.0342 | FAMILY_REPAIR_OR_KILL_CANDIDATE                         | MOVE_TO_REPAIR_OR_KILL_IF_NEXT_BATCH_NOT_IMPROVED                    |

## Pre-commercial acceleration queue

|   queue_rank |   rank | sibling_group                                                    | families                     |   member_count | candidate_list                                                                                   | hours    | weekdays   |   raw_signal_sum |   max_member_signals |   effective_signal_count | evidence_basis                   |   good_sibling_count |   secondary_sibling_count |   weak_or_repair_count |   family_pf_x4 |   family_avg_net_x4 |   family_win_rate_x4 |   family_tail_pf_x4 |   family_max_drawdown_x4 | stage33a_decision                                       | next_action                                                          | commercial_status                          |
|-------------:|-------:|:-----------------------------------------------------------------|:-----------------------------|---------------:|:-------------------------------------------------------------------------------------------------|:---------|:-----------|-----------------:|---------------------:|-------------------------:|:---------------------------------|---------------------:|--------------------------:|-----------------------:|---------------:|--------------------:|---------------------:|--------------------:|-------------------------:|:--------------------------------------------------------|:---------------------------------------------------------------------|:-------------------------------------------|
|            1 |      1 | session_handoff_imbalance_v1::handoff_align_follow_hX_tp06_sl065 | session_handoff_imbalance_v1 |              3 | handoff_align_follow_h13_tp06_sl065;handoff_align_follow_h14_tp06_sl065;handoff_align_follow_... | 13,14,15 | none       |               42 |                   14 |                       42 | ledger_dedup_timestamp_direction |                    2 |                         0 |                      1 |        2.04742 |             1.10669 |             0.754273 |             2.66571 |                 -18.8404 | FAMILY_PRE_COMMERCIAL_ACCELERATION_REVIEW_RESEARCH_ONLY | RUN_STAGE33B_PRE_COMMERCIAL_ROBUSTNESS_ON_FAMILY_NO_EA_NO_PAPER_LIVE | RESEARCH_ONLY_NO_EA_NO_PAPER_LIVE_NO_ORDER |

## Operational interpretation

```text
1. Stage32F remains useful only as automated sample collection, not as the sole decision path.
2. Family-level candidates can move to Stage33B diagnostics before any EA/paper/live decision.
3. If a family fails Stage33B, kill or repair it quickly instead of waiting weeks for single-variant N=40.
4. No EA/paper/live/order transition is authorized by Stage33A.
```

## Output files

- `data/reports/stage33a_dense_family_robustness_gate/stage33a_dense_family_robustness_gate.md`
- `data/reports/stage33a_dense_family_robustness_gate/family_robustness_summary.csv`
- `data/reports/stage33a_dense_family_robustness_gate/candidate_family_membership.csv`
- `data/reports/stage33a_dense_family_robustness_gate/pre_commercial_acceleration_queue.csv`
- `data/reports/stage33a_dense_family_robustness_gate/stage33a_summary.json`
