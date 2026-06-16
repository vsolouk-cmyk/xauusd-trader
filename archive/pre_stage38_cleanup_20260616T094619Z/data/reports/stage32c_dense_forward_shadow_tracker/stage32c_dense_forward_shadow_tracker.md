# XAUUSD Stage32C — Dense Forward Shadow Tracker

Generated UTC: 2026-06-16T09:41:23+00:00

## Decision

```text
DECISION = STAGE32C_HAS_DENSE_FORWARD_REVIEW_QUEUE_RESEARCH_ONLY
EXECUTION_STATUS = RESEARCH_SHADOW_ONLY
NO_EA_CHANGE = True
NO_PAPER_LIVE = True
NO_ORDER_AUTHORIZATION = True
COMMERCIAL_GOAL = FASTEST_SAFE_PATH_TO_COMMERCIALLY_USABLE_SYSTEM
PRIMARY_OBJECTIVE = COLLECT_FORWARD_OBSERVABLE_SAMPLES_FROM_DENSE_FAMILIES
```

## Why this stage exists

Stage32B produced a dense intake queue. Stage32C connects that queue to recurring signal collection so the project can move faster toward a commercially usable system without waiting on low-cadence watchlist candidates.

## Summary

```text
queue_rows = 17
selected_specs = 9
snapshot_signal_rows = 168
ledger_signal_rows = 188
candidate_summary_rows = 9
family_summary_rows = 3
review_queue_candidate_count = 1
lookback_days = 30
min_signals_before_review = 20
latest_m1_utc = 2026-06-16 12:18:00+00:00
latest_h1_utc = 2026-06-16 12:00:00+00:00
```

## Selected specs from Stage32B queue

| candidate | family | source | queue_rank | recent_opportunity_count_for_selection |
| --- | --- | --- | --- | --- |
| calendar_drop_friday_h13_tp06_sl065 | calendar_time_risk_proxy_v1 | exact_queue_variant |  |  |
| calendar_drop_monday_h13_tp06_sl065 | calendar_time_risk_proxy_v1 | exact_queue_variant |  |  |
| calendar_drop_friday_h9_tp06_sl065 | calendar_time_risk_proxy_v1 | exact_queue_variant |  |  |
| vol_trans_fade_h1_low_to_high_h12_tp06_sl065 | volatility_transition_v1 | exact_queue_variant |  |  |
| vol_trans_follow_h1_low_to_high_h12_tp06_sl065 | volatility_transition_v1 | exact_queue_variant |  |  |
| vol_trans_follow_h1_low_to_high_h13_tp06_sl065 | volatility_transition_v1 | exact_queue_variant |  |  |
| handoff_align_follow_h13_tp06_sl065 | session_handoff_imbalance_v1 | exact_queue_variant |  |  |
| handoff_align_follow_h14_tp06_sl065 | session_handoff_imbalance_v1 | exact_queue_variant |  |  |
| handoff_align_follow_h15_tp06_sl065 | session_handoff_imbalance_v1 | exact_queue_variant |  |  |

## Candidate forward-shadow summary

| candidate | family | signal_count | resolved_count | latest_signal_ts | pf_x4 | avg_net_x4 | readiness |
| --- | --- | --- | --- | --- | --- | --- | --- |
| calendar_drop_friday_h9_tp06_sl065 | calendar_time_risk_proxy_v1 | 27 | 25 | 2026-06-16 09:00:00+00:00 | 1.141681 | 0.297066 | DENSE_FORWARD_REVIEW_QUEUE_RESEARCH_ONLY |
| calendar_drop_friday_h13_tp06_sl065 | calendar_time_risk_proxy_v1 | 27 | 24 | 2026-06-16 12:15:00+00:00 | 0.933662 | -0.147248 | FORWARD_SAMPLE_COLLECTION_ACTIVE_RESEARCH_ONLY |
| calendar_drop_monday_h13_tp06_sl065 | calendar_time_risk_proxy_v1 | 25 | 24 | 2026-06-16 12:15:00+00:00 | 0.817511 | -0.456615 | FORWARD_SAMPLE_COLLECTION_ACTIVE_RESEARCH_ONLY |
| vol_trans_follow_h1_low_to_high_h13_tp06_sl065 | volatility_transition_v1 | 22 | 20 | 2026-06-15 13:00:00+00:00 | 0.843633 | -0.474349 | FORWARD_SAMPLE_COLLECTION_ACTIVE_RESEARCH_ONLY |
| vol_trans_fade_h1_low_to_high_h12_tp06_sl065 | volatility_transition_v1 | 21 | 19 | 2026-06-15 12:00:00+00:00 | 1.298189 | 0.668022 | FORWARD_SAMPLE_COLLECTION_ACTIVE_RESEARCH_ONLY |
| vol_trans_follow_h1_low_to_high_h12_tp06_sl065 | volatility_transition_v1 | 21 | 19 | 2026-06-15 12:00:00+00:00 | 0.468069 | -2.119478 | FORWARD_SAMPLE_COLLECTION_ACTIVE_RESEARCH_ONLY |
| handoff_align_follow_h14_tp06_sl065 | session_handoff_imbalance_v1 | 15 | 13 | 2026-06-16 12:15:00+00:00 | 3.043089 | 2.243025 | FORWARD_SAMPLE_COLLECTION_ACTIVE_RESEARCH_ONLY |
| handoff_align_follow_h13_tp06_sl065 | session_handoff_imbalance_v1 | 15 | 13 | 2026-06-16 12:15:00+00:00 | 2.612842 | 2.174892 | FORWARD_SAMPLE_COLLECTION_ACTIVE_RESEARCH_ONLY |
| handoff_align_follow_h15_tp06_sl065 | session_handoff_imbalance_v1 | 15 | 13 | 2026-06-16 12:15:00+00:00 | 0.748923 | -0.759812 | FORWARD_SAMPLE_COLLECTION_ACTIVE_RESEARCH_ONLY |

## Family summary

| family | candidate_count | signal_count | resolved_count | review_ready_candidate_count | recommendation |
| --- | --- | --- | --- | --- | --- |
| calendar_time_risk_proxy_v1 | 3 | 79 | 73 | 1 | REVIEW_DENSE_FORWARD_CANDIDATES |
| volatility_transition_v1 | 3 | 64 | 58 | 0 | KEEP_COLLECTING_FORWARD_SAMPLES |
| session_handoff_imbalance_v1 | 3 | 45 | 39 | 0 | KEEP_COLLECTING_FORWARD_SAMPLES |

## Latest signal snapshot

| entry_time | candidate | family | direction | outcome_status | exit_reason | net_x4 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-06-16 12:15:00+00:00 | calendar_drop_friday_h13_tp06_sl065 | calendar_time_risk_proxy_v1 | 1 | OPEN_OR_INCOMPLETE_M1_PATH |  |  |
| 2026-06-16 12:15:00+00:00 | calendar_drop_monday_h13_tp06_sl065 | calendar_time_risk_proxy_v1 | 1 | OPEN_OR_INCOMPLETE_M1_PATH |  |  |
| 2026-06-16 12:15:00+00:00 | handoff_align_follow_h13_tp06_sl065 | session_handoff_imbalance_v1 | 1 | OPEN_OR_INCOMPLETE_M1_PATH |  |  |
| 2026-06-16 12:15:00+00:00 | handoff_align_follow_h14_tp06_sl065 | session_handoff_imbalance_v1 | 1 | OPEN_OR_INCOMPLETE_M1_PATH |  |  |
| 2026-06-16 12:15:00+00:00 | handoff_align_follow_h15_tp06_sl065 | session_handoff_imbalance_v1 | 1 | OPEN_OR_INCOMPLETE_M1_PATH |  |  |
| 2026-06-16 09:00:00+00:00 | calendar_drop_friday_h9_tp06_sl065 | calendar_time_risk_proxy_v1 | 1 | RESOLVED_M1_REPLAY_SHADOW | sl | -5.7683250000003685 |
| 2026-06-15 15:00:00+00:00 | handoff_align_follow_h15_tp06_sl065 | session_handoff_imbalance_v1 | 1 | RESOLVED_M1_REPLAY_SHADOW | tp | 2.8123000000001412 |
| 2026-06-15 14:00:00+00:00 | handoff_align_follow_h14_tp06_sl065 | session_handoff_imbalance_v1 | 1 | RESOLVED_M1_REPLAY_SHADOW | tp | 2.727400000000307 |
| 2026-06-15 13:00:00+00:00 | calendar_drop_friday_h13_tp06_sl065 | calendar_time_risk_proxy_v1 | 1 | RESOLVED_M1_REPLAY_SHADOW | tp | 3.596799999999894 |
| 2026-06-15 13:00:00+00:00 | handoff_align_follow_h13_tp06_sl065 | session_handoff_imbalance_v1 | 1 | RESOLVED_M1_REPLAY_SHADOW | tp | 3.596799999999894 |
| 2026-06-15 13:00:00+00:00 | vol_trans_follow_h1_low_to_high_h13_tp06_sl065 | volatility_transition_v1 | 1 | RESOLVED_M1_REPLAY_SHADOW | tp | 3.596799999999894 |
| 2026-06-15 12:00:00+00:00 | vol_trans_fade_h1_low_to_high_h12_tp06_sl065 | volatility_transition_v1 | -1 | RESOLVED_M1_REPLAY_SHADOW | tp | 3.5506000000001223 |
| 2026-06-15 12:00:00+00:00 | vol_trans_follow_h1_low_to_high_h12_tp06_sl065 | volatility_transition_v1 | 1 | RESOLVED_M1_REPLAY_SHADOW | tp | 3.5506000000001223 |
| 2026-06-15 09:00:00+00:00 | calendar_drop_friday_h9_tp06_sl065 | calendar_time_risk_proxy_v1 | 1 | RESOLVED_M1_REPLAY_SHADOW | sl | -6.932474999999977 |
| 2026-06-12 23:45:00+00:00 | calendar_drop_friday_h13_tp06_sl065 | calendar_time_risk_proxy_v1 | 1 | RESOLVED_M1_REPLAY_SHADOW | horizon | -1.4 |
| 2026-06-12 23:45:00+00:00 | calendar_drop_friday_h13_tp06_sl065 | calendar_time_risk_proxy_v1 | 1 | RESOLVED_M1_REPLAY_SHADOW | horizon | -1.4 |
| 2026-06-12 23:45:00+00:00 | calendar_drop_friday_h9_tp06_sl065 | calendar_time_risk_proxy_v1 | 1 | RESOLVED_M1_REPLAY_SHADOW | horizon | -1.4 |
| 2026-06-12 23:45:00+00:00 | calendar_drop_friday_h9_tp06_sl065 | calendar_time_risk_proxy_v1 | 1 | RESOLVED_M1_REPLAY_SHADOW | horizon | -1.4 |
| 2026-06-12 23:45:00+00:00 | calendar_drop_monday_h13_tp06_sl065 | calendar_time_risk_proxy_v1 | 1 | RESOLVED_M1_REPLAY_SHADOW | horizon | -1.4 |
| 2026-06-12 23:45:00+00:00 | calendar_drop_monday_h13_tp06_sl065 | calendar_time_risk_proxy_v1 | 1 | RESOLVED_M1_REPLAY_SHADOW | horizon | -1.4 |
| 2026-06-12 13:00:00+00:00 | calendar_drop_monday_h13_tp06_sl065 | calendar_time_risk_proxy_v1 | 1 | RESOLVED_M1_REPLAY_SHADOW | sl | -8.172350000000188 |
| 2026-06-12 13:00:00+00:00 | vol_trans_follow_h1_low_to_high_h13_tp06_sl065 | volatility_transition_v1 | 1 | RESOLVED_M1_REPLAY_SHADOW | sl | -8.172350000000188 |
| 2026-06-12 12:00:00+00:00 | vol_trans_fade_h1_low_to_high_h12_tp06_sl065 | volatility_transition_v1 | -1 | RESOLVED_M1_REPLAY_SHADOW | tp | 4.781800000000294 |
| 2026-06-12 12:00:00+00:00 | vol_trans_follow_h1_low_to_high_h12_tp06_sl065 | volatility_transition_v1 | 1 | RESOLVED_M1_REPLAY_SHADOW | sl | -8.09695000000047 |
| 2026-06-11 15:00:00+00:00 | handoff_align_follow_h15_tp06_sl065 | session_handoff_imbalance_v1 | 1 | RESOLVED_M1_REPLAY_SHADOW | tp | 4.028499999999985 |
| 2026-06-11 14:00:00+00:00 | handoff_align_follow_h14_tp06_sl065 | session_handoff_imbalance_v1 | 1 | RESOLVED_M1_REPLAY_SHADOW | tp | 3.7257999999997993 |
| 2026-06-11 13:00:00+00:00 | calendar_drop_friday_h13_tp06_sl065 | calendar_time_risk_proxy_v1 | 1 | RESOLVED_M1_REPLAY_SHADOW | sl | -8.19509999999982 |
| 2026-06-11 13:00:00+00:00 | calendar_drop_monday_h13_tp06_sl065 | calendar_time_risk_proxy_v1 | 1 | RESOLVED_M1_REPLAY_SHADOW | sl | -8.19509999999982 |
| 2026-06-11 13:00:00+00:00 | handoff_align_follow_h13_tp06_sl065 | session_handoff_imbalance_v1 | 1 | RESOLVED_M1_REPLAY_SHADOW | sl | -8.19509999999982 |
| 2026-06-11 13:00:00+00:00 | vol_trans_follow_h1_low_to_high_h13_tp06_sl065 | volatility_transition_v1 | 1 | RESOLVED_M1_REPLAY_SHADOW | sl | -8.19509999999982 |
| 2026-06-11 12:00:00+00:00 | vol_trans_fade_h1_low_to_high_h12_tp06_sl065 | volatility_transition_v1 | 1 | RESOLVED_M1_REPLAY_SHADOW | sl | -8.044624999999906 |
| 2026-06-11 12:00:00+00:00 | vol_trans_follow_h1_low_to_high_h12_tp06_sl065 | volatility_transition_v1 | -1 | RESOLVED_M1_REPLAY_SHADOW | tp | 4.733499999999912 |
| 2026-06-11 09:00:00+00:00 | calendar_drop_friday_h9_tp06_sl065 | calendar_time_risk_proxy_v1 | 1 | RESOLVED_M1_REPLAY_SHADOW | tp | 7.333900000000176 |
| 2026-06-10 15:00:00+00:00 | handoff_align_follow_h15_tp06_sl065 | session_handoff_imbalance_v1 | -1 | RESOLVED_M1_REPLAY_SHADOW | sl | -9.999825000000238 |
| 2026-06-10 14:00:00+00:00 | handoff_align_follow_h14_tp06_sl065 | session_handoff_imbalance_v1 | -1 | RESOLVED_M1_REPLAY_SHADOW | tp | 5.672199999999611 |
| 2026-06-10 13:00:00+00:00 | calendar_drop_friday_h13_tp06_sl065 | calendar_time_risk_proxy_v1 | -1 | RESOLVED_M1_REPLAY_SHADOW | sl | -9.335199999999896 |
| 2026-06-10 13:00:00+00:00 | calendar_drop_monday_h13_tp06_sl065 | calendar_time_risk_proxy_v1 | -1 | RESOLVED_M1_REPLAY_SHADOW | sl | -9.335199999999896 |
| 2026-06-10 13:00:00+00:00 | handoff_align_follow_h13_tp06_sl065 | session_handoff_imbalance_v1 | -1 | RESOLVED_M1_REPLAY_SHADOW | sl | -9.335199999999896 |
| 2026-06-10 13:00:00+00:00 | vol_trans_follow_h1_low_to_high_h13_tp06_sl065 | volatility_transition_v1 | -1 | RESOLVED_M1_REPLAY_SHADOW | sl | -9.335199999999896 |
| 2026-06-10 12:00:00+00:00 | vol_trans_fade_h1_low_to_high_h12_tp06_sl065 | volatility_transition_v1 | 1 | RESOLVED_M1_REPLAY_SHADOW | tp | 5.026000000000385 |

## Operational interpretation

```text
1. This is still research/shadow only; no EA, paper/live, or order authorization.
2. If signal_count grows but review_queue_candidate_count remains zero, next step is repair/tightening of dense variants, not calendar enrichment.
3. If at least one candidate reaches the review queue, inspect its forward ledger before any commercial transition discussion.
4. Stage31 macro/exogenous candidates remain watchlist-only unless they become forward-active.
```

## Output files

- `data/reports/stage32c_dense_forward_shadow_tracker/stage32c_dense_forward_shadow_tracker.md`
- `data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_signal_snapshot.csv`
- `data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_signal_ledger.csv`
- `data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_candidate_summary.csv`
- `data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_family_summary.csv`
- `data/reports/stage32c_dense_forward_shadow_tracker/stage32c_summary.json`
