# XAUUSD Stage32B — Dense Forward Shadow Intake Builder

Generated UTC: 2026-06-14T18:22:36+00:00

## Decision

```text
STAGE32B_DENSE_FORWARD_SHADOW_INTAKE_QUEUE_READY_RESEARCH_SHADOW_ONLY
EXECUTION_STATUS = RESEARCH_SHADOW_ONLY
NO_EA_CHANGE = TRUE
NO_PAPER_LIVE = TRUE
NO_ORDER_AUTHORIZATION = TRUE
COMMERCIAL_GOAL = FASTEST_SAFE_PATH_TO_COMMERCIALLY_USABLE_SYSTEM
PRIMARY_OBJECTIVE = INCREASE_FORWARD_OBSERVABLE_CANDIDATE_SUPPLY
```

## Why this stage exists

Stage32A-HF1 showed that the infrastructure is running, but commercial transition is blocked because there is no review-ready forward-active candidate. Stage32B therefore stops ranking by historical beauty alone and builds a dense forward-shadow intake queue from families that can realistically generate forward samples faster.

## Summary

```text
decision = STAGE32B_DENSE_FORWARD_SHADOW_INTAKE_QUEUE_READY_RESEARCH_SHADOW_ONLY
commercial_goal = FASTEST_SAFE_PATH_TO_COMMERCIALLY_USABLE_SYSTEM
candidate_supply_summary_path = data/reports/research_shadow_orchestrator/candidate_supply_summary.csv
candidate_registry_path = data/reports/research_shadow_orchestrator/candidate_registry.csv
candidate_registry_exists = True
commercial_summary_path = data/reports/research_shadow_orchestrator/commercial_readiness_summary.json
input_candidate_identity_rows = 433
enriched_candidate_rows = 433
family_count = 23
shadow_queue_rows = 17
primary_shadow_queue_rows = 7
secondary_repair_queue_rows = 10
dense_repair_review_rows = 19
exogenous_watchlist_rows = 360
min_event_count = 500
strong_event_count = 1000
max_variants_per_family = 4
max_total_queue = 24
target_forward_days = 30
min_forward_samples_before_review = 20
tier_counts = {"PRIMARY_DENSE": 7, "REJECT_LOW_DENSITY": 47, "SECONDARY_REPAIR": 19, "WATCHLIST_EXOGENOUS": 360}
classification_counts = {"STAGE32B_DENSE_REJECTED_REPAIR_QUEUE": 18, "STAGE32B_DENSE_SHADOW_INTAKE": 3, "STAGE32B_EXOGENOUS_WATCHLIST_ONLY": 360, "STAGE32B_GENERIC_AGGREGATE_ROW_REPAIR_FIRST": 1, "STAGE32B_LOW_DENSITY_REJECT_FOR_PRIMARY_INTAKE": 47, "STAGE32B_STRONG_DENSE_SHADOW_INTAKE": 4}
research_shadow_only = True
no_ea_change = True
no_paper_live = True
no_order_authorization = True
```

## Input commercial blocker context

```text
decision = COMMERCIAL_TRANSITION_BLOCKED_RESEARCH_SHADOW_ONLY
candidate_identity_count = 433
review_ready_candidate_count = 0
blocked_low_forward_cadence_count = 433
latest_bar_utc_seen = 2026-06-12T23:54:00+00:00
dominant_blockers = ["NO_REVIEW_READY_FORWARD_ACTIVE_CANDIDATE", "LOW_CADENCE_CANDIDATE_SUPPLY"]
```

## Shadow intake queue

| rank | group | tier | family | events | score | candidate_identity | action | rationale |
|---:|---|---|---|---:|---:|---|---|---|
| 1 | PRIMARY_DENSE_FORWARD_SHADOW | PRIMARY_DENSE | calendar_time_risk_proxy_v1 | 5570.0 | 311.6 | calendar_time_risk_proxy_v1 | ADD_TO_DENSE_FORWARD_SHADOW_INTAKE | Strong historical density; route to dense forward shadow intake. |
| 2 | PRIMARY_DENSE_FORWARD_SHADOW | PRIMARY_DENSE | volatility_transition_v1 | 4129.0 | 311.6 | volatility_transition_v1 | ADD_TO_DENSE_FORWARD_SHADOW_INTAKE | Strong historical density; route to dense forward shadow intake. |
| 3 | PRIMARY_DENSE_FORWARD_SHADOW | PRIMARY_DENSE | session_handoff_imbalance_v1 | 3186.0 | 311.6 | session_handoff_imbalance_v1 | ADD_TO_DENSE_FORWARD_SHADOW_INTAKE | Strong historical density; route to dense forward shadow intake. |
| 4 | PRIMARY_DENSE_FORWARD_SHADOW | PRIMARY_DENSE | session_compression_expansion_v1 | 1734.0 | 203.52 | session_compression_expansion_v1 | ADD_TO_DENSE_FORWARD_SHADOW_INTAKE | Strong historical density; route to dense forward shadow intake. |
| 5 | PRIMARY_DENSE_FORWARD_SHADOW | PRIMARY_DENSE | liquidity_sweep_regime_v1 | 931.0 | 137.9 | liquidity_sweep_regime_v1 | ADD_TO_DENSE_FORWARD_SHADOW_INTAKE | Dense enough for forward shadow intake. |
| 6 | PRIMARY_DENSE_FORWARD_SHADOW | PRIMARY_DENSE | high_range_london_continuation_v1 | 850.0 | 129.8 | high_range_london_continuation_v1 | ADD_TO_DENSE_FORWARD_SHADOW_INTAKE | Dense enough for forward shadow intake. |
| 7 | PRIMARY_DENSE_FORWARD_SHADOW | PRIMARY_DENSE | high_range_broad_pullback_continuation_v1 | 762.0 | 121.0 | high_range_broad_pullback_continuation_v1 | ADD_TO_DENSE_FORWARD_SHADOW_INTAKE | Dense enough for forward shadow intake. |
| 8 | SECONDARY_REPAIR_THEN_SHADOW | SECONDARY_REPAIR | stage30b | 3186.0 | 273.3 | data/reports/stage30b_ml_lite_feature_ranker/stage30b_family_holdout.csv | REPAIR_AND_RETEST_BEFORE_PRIMARY_INTAKE | Row is an aggregate/file-level identity; inspect family-level source before primary intake. |
| 9 | SECONDARY_REPAIR_THEN_SHADOW | SECONDARY_REPAIR | calendar_time_risk_proxy_v1 | 1288.0 | 136.24 | calendar_drop_friday_h13_tp06_sl065 \| calendar_time_risk_proxy_v1 | REPAIR_AND_RETEST_BEFORE_PRIMARY_INTAKE | Dense but rejected/error-tagged; repair/retest before forward intake. |
| 10 | SECONDARY_REPAIR_THEN_SHADOW | SECONDARY_REPAIR | calendar_time_risk_proxy_v1 | 1288.0 | 136.24 | calendar_drop_monday_h13_tp06_sl065 \| calendar_time_risk_proxy_v1 | REPAIR_AND_RETEST_BEFORE_PRIMARY_INTAKE | Dense but rejected/error-tagged; repair/retest before forward intake. |
| 11 | SECONDARY_REPAIR_THEN_SHADOW | SECONDARY_REPAIR | calendar_time_risk_proxy_v1 | 1288.0 | 134.64 | calendar_drop_friday_h9_tp06_sl065 \| calendar_time_risk_proxy_v1 | REPAIR_AND_RETEST_BEFORE_PRIMARY_INTAKE | Dense but rejected/error-tagged; repair/retest before forward intake. |
| 12 | SECONDARY_REPAIR_THEN_SHADOW | SECONDARY_REPAIR | volatility_transition_v1 | 809.0 | 94.1 | vol_trans_fade_h1_low_to_high_h12_tp06_sl065 \| volatility_transition_v1 | REPAIR_AND_RETEST_BEFORE_PRIMARY_INTAKE | Dense but rejected/error-tagged; repair/retest before forward intake. |
| 13 | SECONDARY_REPAIR_THEN_SHADOW | SECONDARY_REPAIR | volatility_transition_v1 | 809.0 | 94.1 | vol_trans_follow_h1_low_to_high_h12_tp06_sl065 \| volatility_transition_v1 | REPAIR_AND_RETEST_BEFORE_PRIMARY_INTAKE | Dense but rejected/error-tagged; repair/retest before forward intake. |
| 14 | SECONDARY_REPAIR_THEN_SHADOW | SECONDARY_REPAIR | volatility_transition_v1 | 808.0 | 94.0 | vol_trans_follow_h1_low_to_high_h13_tp06_sl065 \| volatility_transition_v1 | REPAIR_AND_RETEST_BEFORE_PRIMARY_INTAKE | Dense but rejected/error-tagged; repair/retest before forward intake. |
| 15 | SECONDARY_REPAIR_THEN_SHADOW | SECONDARY_REPAIR | session_handoff_imbalance_v1 | 540.0 | 67.2 | handoff_align_follow_h13_tp06_sl065 \| session_handoff_imbalance_v1 | REPAIR_AND_RETEST_BEFORE_PRIMARY_INTAKE | Dense but rejected/error-tagged; repair/retest before forward intake. |
| 16 | SECONDARY_REPAIR_THEN_SHADOW | SECONDARY_REPAIR | session_handoff_imbalance_v1 | 540.0 | 67.2 | handoff_align_follow_h14_tp06_sl065 \| session_handoff_imbalance_v1 | REPAIR_AND_RETEST_BEFORE_PRIMARY_INTAKE | Dense but rejected/error-tagged; repair/retest before forward intake. |
| 17 | SECONDARY_REPAIR_THEN_SHADOW | SECONDARY_REPAIR | session_handoff_imbalance_v1 | 540.0 | 65.6 | handoff_align_follow_h15_tp06_sl065 \| session_handoff_imbalance_v1 | REPAIR_AND_RETEST_BEFORE_PRIMARY_INTAKE | Dense but rejected/error-tagged; repair/retest before forward intake. |

## Family density triage

| rank | family | candidates | max_events | primary | repair | exogenous | recommendation |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | calendar_time_risk_proxy_v1 | 7 | 5570.0 | 1 | 6 | 0 | ROUTE_TOP_VARIANTS_TO_DENSE_FORWARD_SHADOW_INTAKE |
| 2 | volatility_transition_v1 | 7 | 4129.0 | 1 | 6 | 0 | ROUTE_TOP_VARIANTS_TO_DENSE_FORWARD_SHADOW_INTAKE |
| 3 | session_handoff_imbalance_v1 | 7 | 3186.0 | 1 | 6 | 0 | ROUTE_TOP_VARIANTS_TO_DENSE_FORWARD_SHADOW_INTAKE |
| 4 | session_compression_expansion_v1 | 7 | 1734.0 | 1 | 0 | 0 | ROUTE_TOP_VARIANTS_TO_DENSE_FORWARD_SHADOW_INTAKE |
| 5 | liquidity_sweep_regime_v1 | 7 | 931.0 | 1 | 0 | 0 | ROUTE_TOP_VARIANTS_TO_DENSE_FORWARD_SHADOW_INTAKE |
| 6 | high_range_london_continuation_v1 | 4 | 850.0 | 1 | 0 | 0 | ROUTE_TOP_VARIANTS_TO_DENSE_FORWARD_SHADOW_INTAKE |
| 7 | high_range_broad_pullback_continuation_v1 | 4 | 762.0 | 1 | 0 | 0 | ROUTE_TOP_VARIANTS_TO_DENSE_FORWARD_SHADOW_INTAKE |
| 8 | stage30b | 4 | 3186.0 | 0 | 1 | 0 | REPAIR_DENSE_VARIANTS_THEN_RETEST |
| 9 | high_range_asia_london_alignment_v1 | 3 | 284.0 | 0 | 0 | 0 | LOW_PRIORITY_FOR_COMMERCIAL_PATH_NOW |
| 10 | high_range_london_breakout_follow_v1 | 3 | 105.0 | 0 | 0 | 0 | LOW_PRIORITY_FOR_COMMERCIAL_PATH_NOW |
| 11 | london_oneway_continuation | 1 | 100.0 | 0 | 0 | 0 | LOW_PRIORITY_FOR_COMMERCIAL_PATH_NOW |
| 12 | stage27b | 3 | 99.0 | 0 | 0 | 0 | LOW_PRIORITY_FOR_COMMERCIAL_PATH_NOW |
| 13 | stage27c | 3 | 68.0 | 0 | 0 | 0 | LOW_PRIORITY_FOR_COMMERCIAL_PATH_NOW |
| 14 | exogenous_macro | 119 | 66.0 | 0 | 0 | 119 | KEEP_AS_LOW_CADENCE_WATCHLIST |
| 15 | stage28c | 3 | 61.0 | 0 | 0 | 0 | LOW_PRIORITY_FOR_COMMERCIAL_PATH_NOW |
| 16 | stage31c | 129 | 36.0 | 0 | 0 | 129 | KEEP_AS_LOW_CADENCE_WATCHLIST |
| 17 | stage31b | 112 | 0.0 | 0 | 0 | 112 | KEEP_AS_LOW_CADENCE_WATCHLIST |
| 18 | stage28b | 2 | 0.0 | 0 | 0 | 0 | LOW_PRIORITY_FOR_COMMERCIAL_PATH_NOW |
| 19 | pdl_sweep_reclaim_refined | 1 | 0.0 | 0 | 0 | 0 | LOW_PRIORITY_FOR_COMMERCIAL_PATH_NOW |
| 20 | asia_high_breakout_refined | 1 | 0.0 | 0 | 0 | 0 | LOW_PRIORITY_FOR_COMMERCIAL_PATH_NOW |
| 21 | stage25c | 2 | 0.0 | 0 | 0 | 0 | LOW_PRIORITY_FOR_COMMERCIAL_PATH_NOW |
| 22 | stage17d | 2 | 0.0 | 0 | 0 | 0 | LOW_PRIORITY_FOR_COMMERCIAL_PATH_NOW |
| 23 | stage16c | 2 | 0.0 | 0 | 0 | 0 | LOW_PRIORITY_FOR_COMMERCIAL_PATH_NOW |

## Dense but repair-first candidates

| rank | family | events | score | candidate_identity | blockers |
|---:|---|---:|---:|---|---|
| 1 | stage30b | 3186.0 | 273.3 | data/reports/stage30b_ml_lite_feature_ranker/stage30b_family_holdout.csv | CANDIDATE_SUPPLY_DENSITY_BLOCKER;REVIEW_READY_NOT_PROMOTED |
| 2 | calendar_time_risk_proxy_v1 | 1288.0 | 136.24 | calendar_drop_friday_h13_tp06_sl065 \| calendar_time_risk_proxy_v1 | REJECTED_OR_ERROR_SOURCE |
| 3 | calendar_time_risk_proxy_v1 | 1288.0 | 136.24 | calendar_drop_monday_h13_tp06_sl065 \| calendar_time_risk_proxy_v1 | REJECTED_OR_ERROR_SOURCE |
| 4 | calendar_time_risk_proxy_v1 | 1288.0 | 134.64 | calendar_drop_friday_h9_tp06_sl065 \| calendar_time_risk_proxy_v1 | REJECTED_OR_ERROR_SOURCE |
| 5 | calendar_time_risk_proxy_v1 | 1288.0 | 134.64 | calendar_drop_monday_h9_tp06_sl065 \| calendar_time_risk_proxy_v1 | REJECTED_OR_ERROR_SOURCE |
| 6 | volatility_transition_v1 | 809.0 | 94.1 | vol_trans_fade_h1_low_to_high_h12_tp06_sl065 \| volatility_transition_v1 | REJECTED_OR_ERROR_SOURCE |
| 7 | volatility_transition_v1 | 809.0 | 94.1 | vol_trans_follow_h1_low_to_high_h12_tp06_sl065 \| volatility_transition_v1 | REJECTED_OR_ERROR_SOURCE |
| 8 | volatility_transition_v1 | 808.0 | 94.0 | vol_trans_follow_h1_low_to_high_h13_tp06_sl065 \| volatility_transition_v1 | REJECTED_OR_ERROR_SOURCE |
| 9 | calendar_time_risk_proxy_v1 | 645.0 | 77.7 | calendar_keep_tue_wed_thu_h13_tp06_sl065 \| calendar_time_risk_proxy_v1 | REJECTED_OR_ERROR_SOURCE |
| 10 | calendar_time_risk_proxy_v1 | 645.0 | 76.1 | calendar_keep_tue_wed_thu_h9_tp06_sl065 \| calendar_time_risk_proxy_v1 | REJECTED_OR_ERROR_SOURCE |
| 11 | volatility_transition_v1 | 571.0 | 68.7 | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 \| volatility_transition_v1 | REJECTED_OR_ERROR_SOURCE |
| 12 | volatility_transition_v1 | 566.0 | 68.2 | vol_trans_fade_h1_high_cooling_h12_tp06_sl065 \| volatility_transition_v1 | REJECTED_OR_ERROR_SOURCE |
| 13 | volatility_transition_v1 | 566.0 | 68.2 | vol_trans_follow_h1_high_cooling_h12_tp06_sl065 \| volatility_transition_v1 | REJECTED_OR_ERROR_SOURCE |
| 14 | session_handoff_imbalance_v1 | 540.0 | 67.2 | handoff_align_follow_h13_tp06_sl065 \| session_handoff_imbalance_v1 | REJECTED_OR_ERROR_SOURCE |
| 15 | session_handoff_imbalance_v1 | 540.0 | 67.2 | handoff_align_follow_h14_tp06_sl065 \| session_handoff_imbalance_v1 | REJECTED_OR_ERROR_SOURCE |
| 16 | session_handoff_imbalance_v1 | 540.0 | 65.6 | handoff_align_follow_h15_tp06_sl065 \| session_handoff_imbalance_v1 | REJECTED_OR_ERROR_SOURCE |
| 17 | session_handoff_imbalance_v1 | 522.0 | 65.4 | handoff_divergence_fade_h15_tp06_sl065 \| session_handoff_imbalance_v1 | REJECTED_OR_ERROR_SOURCE |
| 18 | session_handoff_imbalance_v1 | 522.0 | 63.8 | handoff_divergence_fade_h13_tp06_sl065 \| session_handoff_imbalance_v1 | REJECTED_OR_ERROR_SOURCE |
| 19 | session_handoff_imbalance_v1 | 522.0 | 63.8 | handoff_divergence_fade_h14_tp06_sl065 \| session_handoff_imbalance_v1 | REJECTED_OR_ERROR_SOURCE |

## Operational interpretation

```text
1. Keep Stage31 macro/exogenous candidates as watchlist only unless they become forward-active.
2. Use the queue to focus forward-shadow observation on dense families first.
3. Secondary repair candidates are not promotion candidates; they are fast-path candidates for retest/repair because they have density.
4. No EA/paper/live/order transition is authorized by this report.
```

## Output files

- `data/reports/stage32b_dense_forward_shadow_intake/stage32b_dense_forward_shadow_intake.md`
- `data/reports/stage32b_dense_forward_shadow_intake/shadow_intake_queue.csv`
- `data/reports/stage32b_dense_forward_shadow_intake/shadow_intake_queue.json`
- `data/reports/stage32b_dense_forward_shadow_intake/family_density_triage.csv`
- `data/reports/stage32b_dense_forward_shadow_intake/family_density_triage.json`
- `data/reports/stage32b_dense_forward_shadow_intake/rejected_but_dense_review.csv`
- `data/reports/stage32b_dense_forward_shadow_intake/rejected_but_dense_review.json`
- `data/reports/stage32b_dense_forward_shadow_intake/stage32b_summary.json`

