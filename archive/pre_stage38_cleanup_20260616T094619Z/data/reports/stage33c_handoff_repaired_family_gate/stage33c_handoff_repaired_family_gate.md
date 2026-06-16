# XAUUSD Stage33C — Handoff Repaired Family Gate

Generated UTC: 2026-06-15T20:00:39Z

## Decision

```text
DECISION = STAGE33C_REPAIRED_FAMILY_PRE_PAPER_RESEARCH_CANDIDATE_ONLY
EXECUTION_STATUS = RESEARCH_ONLY
COMMERCIAL_TRANSITION_AUTHORIZED = False
NO_EA_CHANGE = True
NO_PAPER_LIVE = True
NO_ORDER_AUTHORIZATION = True
PRIMARY_OBJECTIVE = REPAIR_HANDED_OFF_H13_H14_FAMILY_TO_REDUCE_TIME_TO_DECISION
RECOMMENDED_NEXT_STAGE = RUN_STAGE33D_STRICT_COST_AWARE_PRE_PAPER_GATE_NO_EA_NO_PAPER_LIVE
```

## Why this stage exists

Stage33B rejected the full h13/h14/h15 family because the h15 sibling and the latest tail batch weakened robustness. Stage33C tests the repaired h13+h14 family only. It does not authorize EA, paper-live, or orders.

## Summary

```text
stage33b_decision = STAGE33B_REPAIR_OR_KILL_FAMILY_RESEARCH_ONLY
ledger_available = True
ledger_rows = 182
normalized_ledger_rows = 37
included_candidates = handoff_align_follow_h13_tp06_sl065, handoff_align_follow_h14_tp06_sl065
excluded_candidates = handoff_align_follow_h15_tp06_sl065
effective_event_count = 25
good_member_count = 2
weak_member_count = 0
family_pf_x4 = 2.720166
family_win_rate_x4 = 0.84
family_tail_pf_x4 = 2.124122
family_max_drawdown_x4 = -11.8581
cost_1_pf_x4 = 1.829706
last_batch_pf_x4 = 0.741277
```

## Repaired family diagnostics

| sibling_group                                                                  | family                       | included_candidates                                                     | excluded_candidates                 |   raw_repaired_rows |   effective_event_count |   family_pf_x4 |   family_avg_net_x4 |   family_win_rate_x4 |   family_tail_pf_x4 |   family_max_drawdown_x4 |   cost_1_pf_x4 |   cost_1_avg_net_x4 |   cost_1_win_rate_x4 |   last_batch_pf_x4 |   last_batch_avg_net_x4 |   last_batch_win_rate_x4 |   good_member_count |   weak_member_count | stage33c_decision                                          | next_stage                                                        | passes_repaired_prepaper_research_gate   | commercial_status                          |
|:-------------------------------------------------------------------------------|:-----------------------------|:------------------------------------------------------------------------|:------------------------------------|--------------------:|------------------------:|---------------:|--------------------:|---------------------:|--------------------:|-------------------------:|---------------:|--------------------:|---------------------:|-------------------:|------------------------:|-------------------------:|--------------------:|--------------------:|:-----------------------------------------------------------|:------------------------------------------------------------------|:-----------------------------------------|:-------------------------------------------|
| session_handoff_imbalance_v1::handoff_align_follow_h13_h14_repaired_tp06_sl065 | session_handoff_imbalance_v1 | handoff_align_follow_h13_tp06_sl065;handoff_align_follow_h14_tp06_sl065 | handoff_align_follow_h15_tp06_sl065 |                  25 |                      25 |        2.72017 |             2.18822 |                 0.84 |             2.12412 |                 -11.8581 |        1.82971 |             1.18822 |                 0.84 |           0.741277 |                 -0.9071 |                      0.6 |                   2 |                   0 | STAGE33C_REPAIRED_FAMILY_PRE_PAPER_RESEARCH_CANDIDATE_ONLY | RUN_STAGE33D_STRICT_COST_AWARE_PRE_PAPER_GATE_NO_EA_NO_PAPER_LIVE | True                                     | RESEARCH_ONLY_NO_EA_NO_PAPER_LIVE_NO_ORDER |

## Repaired member split summary

| candidate                           |   signal_count |   pf_x4 |   avg_net_x4 |   win_rate_x4 |   tail_pf_x4 |   max_drawdown_x4 | sibling_group                                                                  | member_quality   |
|:------------------------------------|---------------:|--------:|-------------:|--------------:|-------------:|------------------:|:-------------------------------------------------------------------------------|:-----------------|
| handoff_align_follow_h13_tp06_sl065 |             13 | 2.61284 |      2.17489 |      0.846154 |      1.73466 |          -17.5303 | session_handoff_imbalance_v1::handoff_align_follow_h13_h14_repaired_tp06_sl065 | GOOD_MEMBER      |
| handoff_align_follow_h14_tp06_sl065 |             12 | 2.85199 |      2.20266 |      0.833333 |      5.53662 |          -14.2722 | session_handoff_imbalance_v1::handoff_align_follow_h13_h14_repaired_tp06_sl065 | GOOD_MEMBER      |

## Cost sensitivity summary

|   cost_penalty_x4 |   signal_count |   pf_x4 |   avg_net_x4 |   win_rate_x4 |   tail_pf_x4 |   max_drawdown_x4 | sibling_group                                                                  |
|------------------:|---------------:|--------:|-------------:|--------------:|-------------:|------------------:|:-------------------------------------------------------------------------------|
|              0    |             25 | 2.72017 |      2.18822 |          0.84 |      2.12412 |          -11.8581 | session_handoff_imbalance_v1::handoff_align_follow_h13_h14_repaired_tp06_sl065 |
|              0.25 |             25 | 2.47719 |      1.93822 |          0.84 |      1.95429 |          -12.6081 | session_handoff_imbalance_v1::handoff_align_follow_h13_h14_repaired_tp06_sl065 |
|              0.5  |             25 | 2.24859 |      1.68822 |          0.84 |      1.79363 |          -13.3581 | session_handoff_imbalance_v1::handoff_align_follow_h13_h14_repaired_tp06_sl065 |
|              0.75 |             25 | 2.03313 |      1.43822 |          0.84 |      1.64141 |          -14.1081 | session_handoff_imbalance_v1::handoff_align_follow_h13_h14_repaired_tp06_sl065 |
|              1    |             25 | 1.82971 |      1.18822 |          0.84 |      1.49698 |          -14.8581 | session_handoff_imbalance_v1::handoff_align_follow_h13_h14_repaired_tp06_sl065 |

## Tail batch summary

|   batch_index | start_ts             | end_ts               |   signal_count |      pf_x4 |   avg_net_x4 |   win_rate_x4 |   tail_pf_x4 |   max_drawdown_x4 | sibling_group                                                                  |
|--------------:|:---------------------|:---------------------|---------------:|-----------:|-------------:|--------------:|-------------:|------------------:|:-------------------------------------------------------------------------------|
|             1 | 2026-05-15T13:00:00Z | 2026-05-26T14:00:00Z |             10 |   2.2759   |      1.82099 |           0.8 |     2.2759   |          -10.4927 | session_handoff_imbalance_v1::handoff_align_follow_h13_h14_repaired_tp06_sl065 |
|             2 | 2026-05-29T13:00:00Z | 2026-06-08T14:00:00Z |             10 | inf        |      4.10311 |           1   |   inf        |            0      | session_handoff_imbalance_v1::handoff_align_follow_h13_h14_repaired_tp06_sl065 |
|             3 | 2026-06-10T13:00:00Z | 2026-06-15T13:00:00Z |              5 |   0.741277 |     -0.9071  |           0.6 |     0.741277 |          -11.8581 | session_handoff_imbalance_v1::handoff_align_follow_h13_h14_repaired_tp06_sl065 |

## Operational interpretation

```text
1. If h13+h14 pass, move only to a stricter pre-paper research gate; no execution authorization.
2. If h13+h14 fail or only near-miss, do not wait for h15 or single-variant N=40.
3. Stage32F remains a background collector only.
4. This stage exists to reduce time-to-decision and enforce kill/repair discipline.
```

## Output files

- `data/reports/stage33c_handoff_repaired_family_gate/stage33c_handoff_repaired_family_gate.md`
- `data/reports/stage33c_handoff_repaired_family_gate/stage33c_summary.json`
- `data/reports/stage33c_handoff_repaired_family_gate/repaired_family_diagnostics.csv`
- `data/reports/stage33c_handoff_repaired_family_gate/repaired_member_split_summary.csv`
- `data/reports/stage33c_handoff_repaired_family_gate/repaired_cost_sensitivity_summary.csv`
- `data/reports/stage33c_handoff_repaired_family_gate/repaired_tail_batch_summary.csv`
