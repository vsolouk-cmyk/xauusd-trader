# XAUUSD Stage33B — Pre-Commercial Family Robustness Gate

Generated UTC: 2026-06-15T19:54:44Z

## Decision

```text
DECISION = STAGE33B_REPAIR_OR_KILL_FAMILY_RESEARCH_ONLY
EXECUTION_STATUS = RESEARCH_ONLY
COMMERCIAL_TRANSITION_AUTHORIZED = False
NO_EA_CHANGE = True
NO_PAPER_LIVE = True
NO_ORDER_AUTHORIZATION = True
PRIMARY_OBJECTIVE = STRICT_FAMILY_ROBUSTNESS_BEFORE_ANY_PRE_PAPER_STEP
RECOMMENDED_NEXT_STAGE = RETURN_TO_STAGE32B_INTAKE_EXPANSION_OR_REPAIR
```

## Why this stage exists

Stage33A reduced time-to-decision by promoting a dense sibling family for review. Stage33B stress-tests that family before any EA, paper-live, or order-routing work. It checks member consistency, deduplicated family events, hour/day splits, tail batches, drawdown, and cost sensitivity.

## Summary

```text
stage33a_decision = STAGE33A_HAS_FAMILY_PRE_COMMERCIAL_ACCELERATION_REVIEW_RESEARCH_ONLY
family_review_rows = 1
precommercial_research_candidate_rows = 0
repair_or_kill_rows = 1
ledger_available = True
ledger_rows = 182
min_effective_events = 36
min_good_members = 2
min_family_pf_x4 = 1.35
min_family_win_rate = 0.58
min_cost_stress_pf_x4 = 1.1
```

## Family diagnostics

| sibling_group                                                    | families                     | candidate_list                                                                                              |   member_count |   raw_ledger_rows |   effective_event_count |   family_pf_x4 |   family_avg_net_x4 |   family_win_rate_x4 |   family_tail_pf_x4 |   family_max_drawdown_x4 |   good_member_count |   secondary_member_count |   weak_member_count | stage33b_decision                            | next_action                                              | passes_precommercial_research_gate   | commercial_status                          |
|:-----------------------------------------------------------------|:-----------------------------|:------------------------------------------------------------------------------------------------------------|---------------:|------------------:|------------------------:|---------------:|--------------------:|---------------------:|--------------------:|-------------------------:|--------------------:|-------------------------:|--------------------:|:---------------------------------------------|:---------------------------------------------------------|:-------------------------------------|:-------------------------------------------|
| session_handoff_imbalance_v1::handoff_align_follow_hX_tp06_sl065 | session_handoff_imbalance_v1 | handoff_align_follow_h13_tp06_sl065;handoff_align_follow_h14_tp06_sl065;handoff_align_follow_h15_tp06_sl065 |              3 |                37 |                      37 |        1.59058 |             1.13556 |             0.756757 |            0.782163 |                 -30.6985 |                   2 |                        0 |                   1 | STAGE33B_FAMILY_REPAIR_OR_KILL_RESEARCH_ONLY | KILL_OR_REPAIR_FAMILY_DO_NOT_WAIT_FOR_SINGLE_VARIANT_N40 | False                                | RESEARCH_ONLY_NO_EA_NO_PAPER_LIVE_NO_ORDER |

## Member split summary

| candidate                           |   signal_count |    pf_x4 |   avg_net_x4 |   win_rate_x4 |   tail_pf_x4 |   max_drawdown_x4 | member_quality        | sibling_group                                                    |
|:------------------------------------|---------------:|---------:|-------------:|--------------:|-------------:|------------------:|:----------------------|:-----------------------------------------------------------------|
| handoff_align_follow_h14_tp06_sl065 |             12 | 2.85199  |      2.20266 |      0.833333 |     5.53663  |          -14.2722 | GOOD_MEMBER           | session_handoff_imbalance_v1::handoff_align_follow_hX_tp06_sl065 |
| handoff_align_follow_h13_tp06_sl065 |             13 | 2.61284  |      2.17489 |      0.846154 |     1.73466  |          -17.5303 | GOOD_MEMBER           | session_handoff_imbalance_v1::handoff_align_follow_hX_tp06_sl065 |
| handoff_align_follow_h15_tp06_sl065 |             12 | 0.677438 |     -1.05749 |      0.583333 |     0.725849 |          -18.8404 | WEAK_OR_REPAIR_MEMBER | session_handoff_imbalance_v1::handoff_align_follow_hX_tp06_sl065 |

## Cost sensitivity summary

|   cost_penalty_x4 |   signal_count |   pf_x4 |   avg_net_x4 |   win_rate_x4 |   tail_pf_x4 |   max_drawdown_x4 | sibling_group                                                    |
|------------------:|---------------:|--------:|-------------:|--------------:|-------------:|------------------:|:-----------------------------------------------------------------|
|              0    |             37 | 1.59058 |     1.13556  |      0.756757 |     0.782163 |          -30.6985 | session_handoff_imbalance_v1::handoff_align_follow_hX_tp06_sl065 |
|              0.25 |             37 | 1.44644 |     0.885559 |      0.756757 |     0.721095 |          -31.9485 | session_handoff_imbalance_v1::handoff_align_follow_hX_tp06_sl065 |
|              0.5  |             37 | 1.31088 |     0.635559 |      0.756757 |     0.66321  |          -33.1985 | session_handoff_imbalance_v1::handoff_align_follow_hX_tp06_sl065 |
|              0.75 |             37 | 1.18314 |     0.385559 |      0.756757 |     0.608265 |          -34.4485 | session_handoff_imbalance_v1::handoff_align_follow_hX_tp06_sl065 |
|              1    |             37 | 1.06258 |     0.135559 |      0.756757 |     0.556042 |          -35.6985 | session_handoff_imbalance_v1::handoff_align_follow_hX_tp06_sl065 |

## Tail batch summary

|   batch_index | start_ts             | end_ts               |   signal_count |    pf_x4 |   avg_net_x4 |   win_rate_x4 |   tail_pf_x4 |   max_drawdown_x4 | sibling_group                                                    |
|--------------:|:---------------------|:---------------------|---------------:|---------:|-------------:|--------------:|-------------:|------------------:|:-----------------------------------------------------------------|
|             1 | 2026-05-15T13:00:00Z | 2026-05-25T13:00:00Z |             10 | 1.34736  |     0.817322 |      0.7      |     1.34736  |         -12.6402  | session_handoff_imbalance_v1::handoff_align_follow_hX_tp06_sl065 |
|             2 | 2026-05-25T14:00:00Z | 2026-06-01T14:00:00Z |             10 | 5.96375  |     2.55739  |      0.9      |     5.96375  |          -5.15212 | session_handoff_imbalance_v1::handoff_align_follow_hX_tp06_sl065 |
|             3 | 2026-06-01T15:00:00Z | 2026-06-08T15:00:00Z |             10 | 2.25743  |     1.87754  |      0.8      |     2.25743  |          -8.84055 | session_handoff_imbalance_v1::handoff_align_follow_hX_tp06_sl065 |
|             4 | 2026-06-10T13:00:00Z | 2026-06-15T13:00:00Z |              7 | 0.618352 |    -1.50098  |      0.571429 |     0.618352 |         -21.8579  | session_handoff_imbalance_v1::handoff_align_follow_hX_tp06_sl065 |

## Operational interpretation

```text
1. This stage can accelerate decision-making, but it does not authorize commercial transition.
2. A passing family moves only to a stricter cost-aware pre-paper gate.
3. A failing family should be killed or repaired quickly; do not wait weeks for single-variant N=40.
4. Stage32F remains a background collector only.
```

## Output files

- `data/reports/stage33b_pre_commercial_family_robustness_gate/stage33b_pre_commercial_family_robustness_gate.md`
- `data/reports/stage33b_pre_commercial_family_robustness_gate/stage33b_summary.json`
- `data/reports/stage33b_pre_commercial_family_robustness_gate/family_robustness_diagnostics.csv`
- `data/reports/stage33b_pre_commercial_family_robustness_gate/member_split_summary.csv`
- `data/reports/stage33b_pre_commercial_family_robustness_gate/hour_split_summary.csv`
- `data/reports/stage33b_pre_commercial_family_robustness_gate/weekday_split_summary.csv`
- `data/reports/stage33b_pre_commercial_family_robustness_gate/tail_batch_summary.csv`
- `data/reports/stage33b_pre_commercial_family_robustness_gate/cost_sensitivity_summary.csv`
