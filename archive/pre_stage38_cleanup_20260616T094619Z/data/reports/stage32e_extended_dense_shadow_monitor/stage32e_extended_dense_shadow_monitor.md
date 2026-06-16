# XAUUSD Stage32E — Extended Dense Shadow Monitor

Generated UTC: 2026-06-16T09:41:50+00:00

## Decision

```text
DECISION = STAGE32E_PROMISING_LOW_N_COLLECTION_ACTIVE_RESEARCH_ONLY
EXECUTION_STATUS = RESEARCH_SHADOW_ONLY
NO_EA_CHANGE = True
NO_PAPER_LIVE = True
NO_ORDER_AUTHORIZATION = True
COMMERCIAL_GOAL = FASTEST_SAFE_PATH_TO_COMMERCIALLY_USABLE_SYSTEM
PRIMARY_OBJECTIVE = EXTENDED_DENSE_SHADOW_COLLECTION_WITH_WEAK_SIBLING_SUPPRESSION
```

## Why this stage exists

Stage32D found one reviewable candidate that still needs extended shadow, plus two promising low-N siblings. Stage32E turns that plan into a repeatable monitor so the project keeps collecting the samples needed for the fastest safe commercial path without prematurely authorizing EA, paper/live, or orders.

## Summary

```text
leading_candidate = handoff_align_follow_h14_tp06_sl065
focus_queue_rows = 5
primary_extended_rows = 0
promising_low_n_rows = 2
secondary_collection_rows = 2
suppressed_variant_rows = 4
pre_commercial_robustness_queue_rows = 0
extended_min_signals = 40
leading_remaining_to_extended_min = 25
```

## Extended shadow focus queue

| priority | monitor_role | candidate | family | signal_count | remaining_to_extended_min | pf_x4 | win_rate_x4 | tail_pf_x4 | max_drawdown_x4 | next_action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | PROMISING_LOW_N_ACCELERATION | handoff_align_follow_h13_tp06_sl065 | session_handoff_imbalance_v1 | 15 | 25 | 2.612842 | 0.846154 | 1.734659 | -17.5303 | KEEP_COLLECTING_UNTIL_MIN_REVIEW_SAMPLES_THEN_STAGE32D |
| 2 | PROMISING_LOW_N_ACCELERATION | handoff_align_follow_h14_tp06_sl065 | session_handoff_imbalance_v1 | 15 | 25 | 3.043089 | 0.846154 | inf | -14.272175 | KEEP_COLLECTING_UNTIL_MIN_REVIEW_SAMPLES_THEN_STAGE32D |
| 3 | SECONDARY_COLLECTION | calendar_drop_friday_h9_tp06_sl065 | calendar_time_risk_proxy_v1 | 27 | 13 | 1.141681 | 0.52 | 1.159715 | -17.73745 | KEEP_AS_SECONDARY_ONLY_UNTIL_METRICS_IMPROVE |
| 3 | SECONDARY_COLLECTION | vol_trans_fade_h1_low_to_high_h12_tp06_sl065 | volatility_transition_v1 | 21 | 19 | 1.298189 | 0.684211 | 0.564206 | -30.683475 | KEEP_AS_SECONDARY_ONLY_UNTIL_METRICS_IMPROVE |
| 9 | BACKGROUND_COLLECTION | calendar_drop_friday_h13_tp06_sl065 | calendar_time_risk_proxy_v1 | 27 | 13 | 0.933662 | 0.541667 | 1.197193 | -18.9303 | KEEP_BACKGROUND_ONLY |

## Suppressed / repair queue

| candidate | family | signal_count | pf_x4 | avg_net_x4 | win_rate_x4 | tail_pf_x4 | max_drawdown_x4 | next_action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| calendar_drop_monday_h13_tp06_sl065 | calendar_time_risk_proxy_v1 | 25 | 0.817511 | -0.456615 | 0.5 | 0.417467 | -33.07835 | MOVE_TO_REPAIR_QUEUE_TEST_INVERSION_HOUR_SUPPRESSION_OVERLAP |
| handoff_align_follow_h15_tp06_sl065 | session_handoff_imbalance_v1 | 15 | 0.748923 | -0.759812 | 0.615385 | 0.711997 | -18.840375 | MOVE_TO_REPAIR_QUEUE_TEST_INVERSION_HOUR_SUPPRESSION_OVERLAP |
| vol_trans_follow_h1_low_to_high_h12_tp06_sl065 | volatility_transition_v1 | 21 | 0.468069 | -2.119478 | 0.473684 | 0.779321 | -43.820675 | MOVE_TO_REPAIR_QUEUE_TEST_INVERSION_HOUR_SUPPRESSION_OVERLAP |
| vol_trans_follow_h1_low_to_high_h13_tp06_sl065 | volatility_transition_v1 | 22 | 0.843633 | -0.474349 | 0.6 | 0.327474 | -45.034175 | MOVE_TO_REPAIR_QUEUE_TEST_INVERSION_HOUR_SUPPRESSION_OVERLAP |

## Pre-commercial robustness queue

No candidate has met extended sample/stability thresholds yet.


## Operational interpretation

```text
1. Continue active/shadow observation and Stage32C/32D/32E after each AMarkets data refresh.
2. Keep the leading candidate in extended shadow until at least 40 resolved samples are reached.
3. Suppress weak siblings from primary attention; repair/inversion tests can run later but should not dilute the fast path.
4. No EA/paper/live/order transition is authorized by this stage.
```

## Output files

- `data/reports/stage32e_extended_dense_shadow_monitor/stage32e_extended_dense_shadow_monitor.md`
- `data/reports/stage32e_extended_dense_shadow_monitor/extended_shadow_focus_queue.csv`
- `data/reports/stage32e_extended_dense_shadow_monitor/suppressed_variant_plan.csv`
- `data/reports/stage32e_extended_dense_shadow_monitor/pre_commercial_robustness_queue.csv`
- `data/reports/stage32e_extended_dense_shadow_monitor/stage32e_summary.json`
