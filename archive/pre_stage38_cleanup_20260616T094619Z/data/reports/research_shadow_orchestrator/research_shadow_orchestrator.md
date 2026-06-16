# XAUUSD Stage32A-HF1 — Commercial Candidate Supply Orchestrator

Generated UTC: 2026-06-14T18:23:02+00:00

## Decision

```text
STAGE32A_HF1_LOW_DENSITY_CANDIDATE_SUPPLY_BLOCKER_RESEARCH_SHADOW_ONLY
EXECUTION_STATUS = RESEARCH_SHADOW_ONLY
NO_EA_CHANGE = TRUE
NO_PAPER_LIVE = TRUE
NO_ORDER_AUTHORIZATION = TRUE
COMMERCIAL_GOAL = FASTEST_SAFE_PATH_TO_COMMERCIALLY_USABLE_SYSTEM
PRIMARY_CURRENT_BOTTLENECK = CANDIDATE_SUPPLY_DENSITY_AND_FORWARD_CADENCE
```

## Commercial acceleration guardrail

This is not a research detour. The orchestrator keeps AMarkets/FRED data freshness, active observation, discovery, lineage validation, forward tracking, and candidate aggregation visible together so the system can move toward commercial use as soon as evidence supports it.

## Run configuration

```text
mode = aggregate
db = /Users/vahid/Desktop/xauusd-trader/data/local/xauusd_local_store.sqlite
skip_module_runs = False
run_data_refresh_arm = False
run_discovery_arms = False
skip_active_wrapper = False
skip_stage32b_intake = False
skip_stage32c_tracker = False
skip_stage32d_review = False
skip_stage32e_monitor = False
timeout_sec = 0
```

## Module runs

| group | arm | module | required | returncode | status | duration_sec | stdout | stderr |
|---|---|---|---:|---:|---|---:|---|---|
| shadow_intake | stage32b_dense_forward_shadow_intake | `app.stage32b_dense_forward_shadow_intake` | false | 0 | ok | 0.324 | `data/reports/research_shadow_orchestrator/stage32b_dense_forward_shadow_intake.stdout.log` | `data/reports/research_shadow_orchestrator/stage32b_dense_forward_shadow_intake.stderr.log` |
| forward_tracking | stage32c_dense_forward_shadow_tracker | `app.stage32c_dense_forward_shadow_tracker` | false | 0 | ok | 23.891 | `data/reports/research_shadow_orchestrator/stage32c_dense_forward_shadow_tracker.stdout.log` | `data/reports/research_shadow_orchestrator/stage32c_dense_forward_shadow_tracker.stderr.log` |
| forward_review | stage32d_dense_forward_review | `app.stage32d_dense_forward_review` | false | 0 | ok | 0.385 | `data/reports/research_shadow_orchestrator/stage32d_dense_forward_review.stdout.log` | `data/reports/research_shadow_orchestrator/stage32d_dense_forward_review.stderr.log` |
| extended_shadow_monitor | stage32e_extended_dense_shadow_monitor | `app.stage32e_extended_dense_shadow_monitor` | false | 0 | ok | 0.969 | `data/reports/research_shadow_orchestrator/stage32e_extended_dense_shadow_monitor.stdout.log` | `data/reports/research_shadow_orchestrator/stage32e_extended_dense_shadow_monitor.stderr.log` |

## Commercial readiness summary

```text
decision = COMMERCIAL_TRANSITION_BLOCKED_RESEARCH_SHADOW_ONLY
candidate_registry_rows = 8386
candidate_identity_count = 433
review_ready_candidate_count = 0
blocked_low_forward_cadence_count = 433
blocked_low_event_density_count = 0
required_module_errors = 0
optional_module_errors = 0
latest_bar_utc_seen = 2026-06-12T23:54:00+00:00
dominant_blockers = ["NO_REVIEW_READY_FORWARD_ACTIVE_CANDIDATE", "LOW_CADENCE_CANDIDATE_SUPPLY"]
density_bucket_counts = {"HAS_LATEST_SIGNAL_TS_NO_RECENT_COUNT": 21, "HISTORICAL_DENSITY_PRESENT_FORWARD_UNKNOWN": 80, "LOW_HISTORICAL_DENSITY": 790, "MODERATE_HISTORICAL_DENSITY": 161, "UNKNOWN_DENSITY": 7334}
commercial_blocker_counts = {"CANDIDATE_SUPPLY_DENSITY_BLOCKER": 762, "FORWARD_DENSITY_UNKNOWN": 622, "REJECTED_OR_ERROR_SOURCE": 6809, "REVIEW_READY_NOT_PROMOTED": 193}
stage_counts = {"stage16c": 4, "stage17d": 24, "stage18e": 15, "stage25c": 30, "stage27b": 52, "stage27c": 50, "stage28a": 50, "stage28b": 354, "stage28c": 739, "stage29a": 24, "stage30a": 13, "stage30b": 115, "stage31b": 5279, "stage31c": 1480, "stage31d": 70, "stage31e": 8, "stage31f": 32, "stage32b": 23, "stage32c": 12, "stage32d": 12}
family_counts = {"asia_high_breakout_refined": 6, "calendar_time_risk_proxy_v1": 20, "exogenous_macro": 2360, "high_range_asia_london_alignment_v1": 7, "high_range_broad_pullback_continuation_v1": 9, "high_range_london_breakout_follow_v1": 7, "high_range_london_continuation_v1": 9, "liquidity_sweep_regime_v1": 12, "london_oneway_continuation": 5, "pdl_sweep_reclaim_refined": 11, "session_compression_expansion_v1": 12, "session_handoff_imbalance_v1": 20, "stage16c": 5, "stage17d": 25, "stage25c": 31, "stage27b": 53, "stage27c": 51, "stage28b": 355, "stage28c": 740, "stage30b": 116, "stage31b": 3570, "stage31c": 926, "stage31d": 16, "volatility_transition_v1": 20}
```

## Candidate supply summary — aggregated by identity

| rank | readiness | best_score | identity | source_rows | max_recent | max_events | latest_signal_ts | blockers |
|---:|---|---:|---|---:|---:|---:|---|---|
| 1 | BLOCKED_LOW_FORWARD_CADENCE | 112.621963 | real_yield_rank250_le_q20 \| real_yield_rank250 | 49 |  | 56.0 |  | FORWARD_DENSITY_UNKNOWN;REJECTED_OR_ERROR_SOURCE;REVIEW_READY_NOT_PROMOTED |
| 2 | BLOCKED_LOW_FORWARD_CADENCE | 109.624973 | real_yield_z60_le_q20 \| real_yield_z60 | 46 |  | 66.0 |  | FORWARD_DENSITY_UNKNOWN;REJECTED_OR_ERROR_SOURCE;REVIEW_READY_NOT_PROMOTED |
| 3 | BLOCKED_LOW_FORWARD_CADENCE | 101.496952 | us10y_rank250_le_q20 \| us10y_rank250 | 29 |  | 38.0 |  | FORWARD_DENSITY_UNKNOWN;REJECTED_OR_ERROR_SOURCE;REVIEW_READY_NOT_PROMOTED |
| 4 | BLOCKED_LOW_FORWARD_CADENCE | 99.257865 | us10y_rank250_le_q30 \| us10y_rank250 | 38 |  | 50.0 |  | FORWARD_DENSITY_UNKNOWN;REJECTED_OR_ERROR_SOURCE;REVIEW_READY_NOT_PROMOTED |
| 5 | BLOCKED_LOW_FORWARD_CADENCE | 68.389363 | dxy_ret_5_le_q30 \| dxy_ret_5 | 25 |  | 30.0 |  | FORWARD_DENSITY_UNKNOWN;REJECTED_OR_ERROR_SOURCE;REVIEW_READY_NOT_PROMOTED |
| 6 | BLOCKED_LOW_FORWARD_CADENCE | 68.360573 | dxy_chg_5_le_q30 \| dxy_chg_5 | 25 |  | 30.0 |  | FORWARD_DENSITY_UNKNOWN;REJECTED_OR_ERROR_SOURCE;REVIEW_READY_NOT_PROMOTED |
| 7 | BLOCKED_LOW_FORWARD_CADENCE | 50.488952 | real_yield_ret_1_le_q30 \| real_yield_ret_1 | 25 |  | 28.0 |  | FORWARD_DENSITY_UNKNOWN;REJECTED_OR_ERROR_SOURCE |
| 8 | BLOCKED_LOW_FORWARD_CADENCE | 47.470362 | real_yield_chg_5_le_q30 \| real_yield_chg_5 | 27 |  | 30.0 |  | FORWARD_DENSITY_UNKNOWN;REJECTED_OR_ERROR_SOURCE;REVIEW_READY_NOT_PROMOTED |
| 9 | BLOCKED_LOW_FORWARD_CADENCE | 44.297348 | us10y_ret_5_le_q30 \| us10y_ret_5 | 27 |  | 30.0 |  | FORWARD_DENSITY_UNKNOWN;REJECTED_OR_ERROR_SOURCE;REVIEW_READY_NOT_PROMOTED |
| 10 | BLOCKED_LOW_FORWARD_CADENCE | 42.512201 | us10y_chg_5_le_q30 \| us10y_chg_5 | 23 |  | 28.0 |  | FORWARD_DENSITY_UNKNOWN;REJECTED_OR_ERROR_SOURCE |
| 11 | BLOCKED_LOW_FORWARD_CADENCE | 40.0 | calendar_drop_friday_h13_tp06_sl065 \| calendar_time_risk_proxy_v1 | 2 |  | 1288.0 |  | REJECTED_OR_ERROR_SOURCE |
| 12 | BLOCKED_LOW_FORWARD_CADENCE | 40.0 | calendar_drop_friday_h9_tp06_sl065 \| calendar_time_risk_proxy_v1 | 1 |  | 1288.0 |  | REJECTED_OR_ERROR_SOURCE |
| 13 | BLOCKED_LOW_FORWARD_CADENCE | 40.0 | calendar_drop_monday_h13_tp06_sl065 \| calendar_time_risk_proxy_v1 | 2 |  | 1288.0 |  | REJECTED_OR_ERROR_SOURCE |
| 14 | BLOCKED_LOW_FORWARD_CADENCE | 40.0 | calendar_drop_monday_h9_tp06_sl065 \| calendar_time_risk_proxy_v1 | 1 |  | 1288.0 |  | REJECTED_OR_ERROR_SOURCE |
| 15 | BLOCKED_LOW_FORWARD_CADENCE | 40.0 | calendar_time_risk_proxy_v1 | 11 |  | 5570.0 | 2026-06-12 13:00:00+00:00 | FORWARD_DENSITY_UNKNOWN;REVIEW_READY_NOT_PROMOTED |
| 16 | BLOCKED_LOW_FORWARD_CADENCE | 40.0 | data/reports/stage30b_ml_lite_feature_ranker/stage30b_family_holdout.csv | 18 |  | 3186.0 |  | CANDIDATE_SUPPLY_DENSITY_BLOCKER;REVIEW_READY_NOT_PROMOTED |
| 17 | BLOCKED_LOW_FORWARD_CADENCE | 40.0 | session_compression_expansion_v1 | 3 |  | 1734.0 |  | FORWARD_DENSITY_UNKNOWN;REVIEW_READY_NOT_PROMOTED |
| 18 | BLOCKED_LOW_FORWARD_CADENCE | 40.0 | session_handoff_imbalance_v1 | 11 |  | 3186.0 | 2026-06-11 15:00:00+00:00 | FORWARD_DENSITY_UNKNOWN;REVIEW_READY_NOT_PROMOTED |
| 19 | BLOCKED_LOW_FORWARD_CADENCE | 40.0 | volatility_transition_v1 | 11 |  | 4129.0 | 2026-06-12 13:00:00+00:00 | FORWARD_DENSITY_UNKNOWN;REVIEW_READY_NOT_PROMOTED |
| 20 | BLOCKED_LOW_FORWARD_CADENCE | 38.209081 | spx_chg_5_ge_q70 \| spx_chg_5 | 25 |  | 30.0 |  | FORWARD_DENSITY_UNKNOWN;REJECTED_OR_ERROR_SOURCE;REVIEW_READY_NOT_PROMOTED |
| 21 | BLOCKED_LOW_FORWARD_CADENCE | 37.24 | liquidity_sweep_regime_v1 | 3 |  | 931.0 |  | FORWARD_DENSITY_UNKNOWN;REVIEW_READY_NOT_PROMOTED |
| 22 | BLOCKED_LOW_FORWARD_CADENCE | 34.0 | high_range_london_continuation_v1 | 3 |  | 850.0 |  | FORWARD_DENSITY_UNKNOWN;REVIEW_READY_NOT_PROMOTED |
| 23 | BLOCKED_LOW_FORWARD_CADENCE | 32.36 | vol_trans_fade_h1_low_to_high_h12_tp06_sl065 \| volatility_transition_v1 | 2 |  | 809.0 |  | REJECTED_OR_ERROR_SOURCE |
| 24 | BLOCKED_LOW_FORWARD_CADENCE | 32.36 | vol_trans_follow_h1_low_to_high_h12_tp06_sl065 \| volatility_transition_v1 | 2 |  | 809.0 |  | REJECTED_OR_ERROR_SOURCE |
| 25 | BLOCKED_LOW_FORWARD_CADENCE | 32.32 | vol_trans_follow_h1_low_to_high_h13_tp06_sl065 \| volatility_transition_v1 | 2 |  | 808.0 |  | REJECTED_OR_ERROR_SOURCE |
| 26 | BLOCKED_LOW_FORWARD_CADENCE | 30.48 | high_range_broad_pullback_continuation_v1 | 3 |  | 762.0 |  | FORWARD_DENSITY_UNKNOWN;REVIEW_READY_NOT_PROMOTED |
| 27 | BLOCKED_LOW_FORWARD_CADENCE | 27.407567 | oil_rank250_le_q30 \| oil_rank250 | 35 |  | 36.0 |  | FORWARD_DENSITY_UNKNOWN;REJECTED_OR_ERROR_SOURCE;REVIEW_READY_NOT_PROMOTED |
| 28 | BLOCKED_LOW_FORWARD_CADENCE | 25.8 | calendar_keep_tue_wed_thu_h13_tp06_sl065 \| calendar_time_risk_proxy_v1 | 2 |  | 645.0 |  | REJECTED_OR_ERROR_SOURCE |
| 29 | BLOCKED_LOW_FORWARD_CADENCE | 25.8 | calendar_keep_tue_wed_thu_h9_tp06_sl065 \| calendar_time_risk_proxy_v1 | 1 |  | 645.0 |  | REJECTED_OR_ERROR_SOURCE |
| 30 | BLOCKED_LOW_FORWARD_CADENCE | 22.84 | vol_trans_follow_h1_high_cooling_h13_tp06_sl065 \| volatility_transition_v1 | 1 |  | 571.0 |  | REJECTED_OR_ERROR_SOURCE |

## Top candidate registry rows — review only

| rank | priority_score | density | blocker | candidate_identity | source_csv | decision | latest_recent_entry_ts | recent_signal_rows |
|---:|---:|---|---|---|---|---|---|---:|
| 1 | 112.621963 | MODERATE_HISTORICAL_DENSITY | REVIEW_READY_NOT_PROMOTED | real_yield_rank250_le_q20 \| real_yield_rank250 | `data/reports/stage31d_exogenous_candidate_confirmation/stage31d_candidate_review.csv` | STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY |  |  |
| 2 | 112.621963 | MODERATE_HISTORICAL_DENSITY | REVIEW_READY_NOT_PROMOTED | real_yield_rank250_le_q20 \| real_yield_rank250 | `data/reports/stage31d_exogenous_candidate_confirmation/stage31d_confirmation_results.csv` | STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY |  |  |
| 3 | 112.523415 | MODERATE_HISTORICAL_DENSITY | REVIEW_READY_NOT_PROMOTED | real_yield_rank250_le_q20 \| real_yield_rank250 | `data/reports/stage31d_exogenous_candidate_confirmation/stage31d_candidate_review.csv` | STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY |  |  |
| 4 | 112.523415 | MODERATE_HISTORICAL_DENSITY | REVIEW_READY_NOT_PROMOTED | real_yield_rank250_le_q20 \| real_yield_rank250 | `data/reports/stage31d_exogenous_candidate_confirmation/stage31d_confirmation_results.csv` | STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY |  |  |
| 5 | 109.624973 | MODERATE_HISTORICAL_DENSITY | REVIEW_READY_NOT_PROMOTED | real_yield_z60_le_q20 \| real_yield_z60 | `data/reports/stage31d_exogenous_candidate_confirmation/stage31d_candidate_review.csv` | STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY |  |  |
| 6 | 109.624973 | MODERATE_HISTORICAL_DENSITY | REVIEW_READY_NOT_PROMOTED | real_yield_z60_le_q20 \| real_yield_z60 | `data/reports/stage31d_exogenous_candidate_confirmation/stage31d_confirmation_results.csv` | STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY |  |  |
| 7 | 109.571344 | MODERATE_HISTORICAL_DENSITY | REVIEW_READY_NOT_PROMOTED | real_yield_z60_le_q20 \| real_yield_z60 | `data/reports/stage31d_exogenous_candidate_confirmation/stage31d_candidate_review.csv` | STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY |  |  |
| 8 | 109.571344 | MODERATE_HISTORICAL_DENSITY | REVIEW_READY_NOT_PROMOTED | real_yield_z60_le_q20 \| real_yield_z60 | `data/reports/stage31d_exogenous_candidate_confirmation/stage31d_confirmation_results.csv` | STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY |  |  |
| 9 | 104.653135 | MODERATE_HISTORICAL_DENSITY | REVIEW_READY_NOT_PROMOTED | real_yield_rank250_le_q20 \| real_yield_rank250 | `data/reports/stage31e_exogenous_forward_shadow_tracker/stage31e_tracker_summary.csv` |  |  |  |
| 10 | 104.653135 | MODERATE_HISTORICAL_DENSITY | REVIEW_READY_NOT_PROMOTED | real_yield_rank250_le_q20 \| real_yield_rank250 | `data/reports/stage31f_exogenous_tracker_cadence_audit/stage31e_lookback_2160h_tracker_summary.csv` |  |  |  |
| 11 | 104.653135 | MODERATE_HISTORICAL_DENSITY | REVIEW_READY_NOT_PROMOTED | real_yield_rank250_le_q20 \| real_yield_rank250 | `data/reports/stage31f_exogenous_tracker_cadence_audit/stage31e_lookback_336h_tracker_summary.csv` |  |  |  |
| 12 | 104.653135 | MODERATE_HISTORICAL_DENSITY | REVIEW_READY_NOT_PROMOTED | real_yield_rank250_le_q20 \| real_yield_rank250 | `data/reports/stage31f_exogenous_tracker_cadence_audit/stage31e_lookback_4320h_tracker_summary.csv` |  |  |  |
| 13 | 104.653135 | MODERATE_HISTORICAL_DENSITY | REVIEW_READY_NOT_PROMOTED | real_yield_rank250_le_q20 \| real_yield_rank250 | `data/reports/stage31f_exogenous_tracker_cadence_audit/stage31e_lookback_720h_tracker_summary.csv` |  |  |  |
| 14 | 104.554587 | MODERATE_HISTORICAL_DENSITY | REVIEW_READY_NOT_PROMOTED | real_yield_rank250_le_q20 \| real_yield_rank250 | `data/reports/stage31e_exogenous_forward_shadow_tracker/stage31e_tracker_summary.csv` |  |  |  |
| 15 | 104.554587 | MODERATE_HISTORICAL_DENSITY | REVIEW_READY_NOT_PROMOTED | real_yield_rank250_le_q20 \| real_yield_rank250 | `data/reports/stage31f_exogenous_tracker_cadence_audit/stage31e_lookback_2160h_tracker_summary.csv` |  |  |  |
| 16 | 104.554587 | MODERATE_HISTORICAL_DENSITY | REVIEW_READY_NOT_PROMOTED | real_yield_rank250_le_q20 \| real_yield_rank250 | `data/reports/stage31f_exogenous_tracker_cadence_audit/stage31e_lookback_336h_tracker_summary.csv` |  |  |  |
| 17 | 104.554587 | MODERATE_HISTORICAL_DENSITY | REVIEW_READY_NOT_PROMOTED | real_yield_rank250_le_q20 \| real_yield_rank250 | `data/reports/stage31f_exogenous_tracker_cadence_audit/stage31e_lookback_4320h_tracker_summary.csv` |  |  |  |
| 18 | 104.554587 | MODERATE_HISTORICAL_DENSITY | REVIEW_READY_NOT_PROMOTED | real_yield_rank250_le_q20 \| real_yield_rank250 | `data/reports/stage31f_exogenous_tracker_cadence_audit/stage31e_lookback_720h_tracker_summary.csv` |  |  |  |
| 19 | 103.682397 | MODERATE_HISTORICAL_DENSITY | REVIEW_READY_NOT_PROMOTED | real_yield_z60_le_q20 \| real_yield_z60 | `data/reports/stage31e_exogenous_forward_shadow_tracker/stage31e_tracker_summary.csv` |  |  |  |
| 20 | 103.682397 | MODERATE_HISTORICAL_DENSITY | REVIEW_READY_NOT_PROMOTED | real_yield_z60_le_q20 \| real_yield_z60 | `data/reports/stage31f_exogenous_tracker_cadence_audit/stage31e_lookback_2160h_tracker_summary.csv` |  |  |  |

## Data freshness / DB-first status

| area | item | status | row_count | first_utc | last_utc |
|---|---|---|---:|---|---|
| bars | `amarkets_mt5::1h` | ok | 25608 | 2022-05-01T23:00:00+00:00 | 2026-06-12T23:00:00+00:00 |
| bars | `amarkets_mt5::1m` | ok | 1534217 | 2022-05-01T23:01:00+00:00 | 2026-06-12T23:54:00+00:00 |
| table | `dryrun_signals` | ok | 1 | 2026-06-09T12:01:43+00:00 | 2026-06-09T12:01:43+00:00 |
| table | `dryrun_outcomes` | ok | 1 | 2026-06-09T12:01:43+00:00 | 2026-06-09T12:01:43+00:00 |
| table | `event_pipeline_runs` | ok | 2 | 2026-06-10T05:53:32+00:00 | 2026-06-10T05:54:02+00:00 |
| table | `event_pipeline_staging` | ok | 5 | 2026-06-10T05:54:02+00:00 | 2026-06-10T05:54:02+00:00 |
| table | `event_impact_validation_summary` | ok | 7 | 2026-06-10T09:08:21+00:00 | 2026-06-10T09:34:22+00:00 |

## Latest discovered reports

| modified_utc | path | decisions |
|---|---|---|
| 2026-06-14T18:23:02+00:00 | `data/reports/stage32e_extended_dense_shadow_monitor/stage32e_extended_dense_shadow_monitor.md` | COMMERCIAL_GOAL;DECISION;EXECUTION_STATUS;EXTENDED_DENSE_SHADOW_COLLECTION_WITH_WEAK_SIBLING_SUPPRESSION;FASTEST_SAFE_PATH_TO_COMMERCIALLY_USABLE_SYSTEM;KEEP_AS_SECONDARY_ONLY_UNTIL_METRICS_IMPROVE;KEEP_COLLECTING_UNTIL_40_RESOLVED_SAMPLES;KEEP_COLLECTING_UNTIL_MIN_REVIEW_SAMPLES_THEN_STAGE32D;MOVE_TO_REPAIR_QUEUE_TEST_INVERSION_HOUR_SUPPRESSION_OVERLAP;NO_EA_CHANGE;NO_ORDER_AUTHORIZATION;NO_PAPER_LIVE;PRIMARY_EXTENDED_SHADOW;PRIMARY_OBJECTIVE;PROMISING_LOW_N_ACCELERATION;RESEARCH_SHADOW_ONLY;SECONDARY_COLLECTION;STAGE32E_EXTENDED_DENSE_SHADOW_ACTIVE_RESEARCH_ONLY |
| 2026-06-14T18:23:01+00:00 | `data/reports/stage32d_dense_forward_review/stage32d_dense_forward_review.md` | ACCELERATE_COLLECTION_FOR_PROMISING_LOW_N_VARIANTS;ACCELERATE_FORWARD_SAMPLE_COLLECTION;COMMERCIAL_GOAL;DECISION;EXECUTION_STATUS;FASTEST_SAFE_PATH_TO_COMMERCIALLY_USABLE_SYSTEM;FOCUS_EXTENDED_SHADOW_ON_REVIEWABLE_VARIANT;KEEP_COLLECTING_FORWARD_SAMPLES;KEEP_COLLECTING_OR_REPAIR_RESEARCH_ONLY;KEEP_PRIMARY_EXTENDED_SHADOW_COLLECT_TO_40;KEEP_SECONDARY_COLLECTION;NEEDS_EXTENDED_DENSE_SHADOW_BEFORE_COMMERCIAL_REVIEW;NO_EA_CHANGE;NO_ORDER_AUTHORIZATION;NO_PAPER_LIVE;PAUSE_OR_REPAIR_BEFORE_PRIMARY_SHADOW;PAUSE_PRIMARY_SHADOW_OR_TEST_INVERSION;PRIMARY_OBJECTIVE;PROMISING_LOW_N_ACCELERATE_COLLECTION;RESEARCH_SHADOW_ONLY;RESEARCH_SHADOW_ONLY_NO_EA_NO_PAPER_LIVE;STAGE32D_HAS_REVIEW_CANDIDATE_NEEDS_EXTENDED_SHADOW_RESEARCH_ONLY;TIGHTEN_DENSE_FORWARD_REVIEW_CANDIDATES_WITHOUT_COMMERCIAL_PROMOTION |
| 2026-06-14T18:23:00+00:00 | `data/reports/stage32c_dense_forward_shadow_tracker/stage32c_dense_forward_shadow_tracker.md` | 026000000000385;028499999999985;044624999999906;09695000000047;161200000000099;172350000000188;180700000000433;19509999999982;243799999999828;286399999999594;333900000000176;335199999999896;361500000000342;378675000000294;472275000000446;537200000000302;612424999999712;672199999999611;7167999999997847;7257999999997993;733499999999912;781800000000294;840550000000258;915300000000025;999825000000238;COLLECT_FORWARD_OBSERVABLE_SAMPLES_FROM_DENSE_FAMILIES;COMMERCIAL_GOAL;DECISION;DENSE_FORWARD_REVIEW_QUEUE_RESEARCH_ONLY;EXECUTION_STATUS;FASTEST_SAFE_PATH_TO_COMMERCIALLY_USABLE_SYSTEM;FORWARD_SAMPLE_COLLECTION_ACTIVE_RESEARCH_ONLY;KEEP_COLLECTING_FORWARD_SAMPLES;NO_EA_CHANGE;NO_ORDER_AUTHORIZATION;NO_PAPER_LIVE;PRIMARY_OBJECTIVE;RESEARCH_SHADOW_ONLY;RESOLVED_M1_REPLAY_SHADOW;REVIEW_DENSE_FORWARD_CANDIDATES |
| 2026-06-14T18:22:36+00:00 | `data/reports/stage32b_dense_forward_shadow_intake/stage32b_dense_forward_shadow_intake.md` | ADD_TO_DENSE_FORWARD_SHADOW_INTAKE;CANDIDATE_SUPPLY_DENSITY_BLOCKER;COMMERCIAL_GOAL;COMMERCIAL_TRANSITION_BLOCKED_RESEARCH_SHADOW_ONLY;EXECUTION_STATUS;FASTEST_SAFE_PATH_TO_COMMERCIALLY_USABLE_SYSTEM;INCREASE_FORWARD_OBSERVABLE_CANDIDATE_SUPPLY;KEEP_AS_LOW_CADENCE_WATCHLIST;LOW_CADENCE_CANDIDATE_SUPPLY;LOW_PRIORITY_FOR_COMMERCIAL_PATH_NOW;NO_EA_CHANGE;NO_ORDER_AUTHORIZATION;NO_PAPER_LIVE;NO_REVIEW_READY_FORWARD_ACTIVE_CANDIDATE;PRIMARY_DENSE;PRIMARY_DENSE_FORWARD_SHADOW;PRIMARY_OBJECTIVE;REJECTED_OR_ERROR_SOURCE;REJECT_LOW_DENSITY;REPAIR_AND_RETEST_BEFORE_PRIMARY_INTAKE;REPAIR_DENSE_VARIANTS_THEN_RETEST;RESEARCH_SHADOW_ONLY;REVIEW_READY_NOT_PROMOTED;ROUTE_TOP_VARIANTS_TO_DENSE_FORWARD_SHADOW_INTAKE;SECONDARY_REPAIR;SECONDARY_REPAIR_THEN_SHADOW;STAGE32B_DENSE_FORWARD_SHADOW_INTAKE_QUEUE_READY_RESEARCH_SHADOW_ONLY;STAGE32B_DENSE_REJECTED_REPAIR_QUEUE;STAGE32B_DENSE_SHADOW_INTAKE;STAGE32B_EXOGENOUS_WATCHLIST_ONLY;STAGE32B_GENERIC_AGGREGATE_ROW_REPAIR_FIRST;STAGE32B_LOW_DENSITY_REJECT_FOR_PRIMARY_INTAKE;STAGE32B_STRONG_DENSE_SHADOW_INTAKE;WATCHLIST_EXOGENOUS |
| 2026-06-14T18:04:58+00:00 | `data/reports/stage30b_ml_lite_feature_ranker/stage30b_ml_lite_feature_ranker.md` | STAGE25C;STAGE28A;STAGE28B;STAGE29A;STAGE30B_ALLOW_DIRECTION;STAGE30B_NO_ML_LITE_PROMOTION_KEEP_RESEARCH_OPEN |
| 2026-06-14T18:04:31+00:00 | `data/reports/stage30a_candidate_pool_builder_ml_dataset/stage30a_candidate_pool_builder_ml_dataset.md` | STAGE25C;STAGE27B;STAGE27C;STAGE28A;STAGE28B;STAGE29A;STAGE30A_ML_META_DATASET_READY_FOR_STAGE30B_REVIEW_ONLY |
| 2026-06-14T18:04:06+00:00 | `data/reports/stage29a_high_range_regime_continuation_discovery/stage29a_high_range_regime_continuation_discovery.md` | STAGE29A_NO_PROMOTION_KEEP_DISCOVERY_OPEN;STAGE29A_REJECT |
| 2026-06-14T18:00:02+00:00 | `data/reports/stage28d_forward_safe_meta_gate_tracker/stage28d_forward_safe_meta_gate_tracker.md` | 43434343434343436;LATE_DETECTED_ALREADY_RESOLVED;STAGE28D_NO_ACTIVE_META_GATE_FORWARD_SIGNAL_RESEARCH_ONLY |
| 2026-06-14T17:59:27+00:00 | `data/reports/stage28c_forward_safe_meta_gate_validation/stage28c_forward_safe_meta_gate_validation.md` | 019999999999982;02600000000002;029999999999927;032000000000016;05600000000004;069999999999983;072000000000207;074000000000023;103000000000065;112000000000125;115000000000009;133999999999924;134999999999932;1400000000001;148000000000115;149999999999906;150000000000093;160000000000082;161999999999903;170000000000073;193999999999823;203999999999997;229999999999976;23000000000001;237999999999968;23800000000001;239999999999782;24000000000001;249999999999908;255999999999947;26200000000008;288000000000011;337999999999939;338000000000056;345999999999869;353999999999857;376999999999907;387999999999918;390000000000077;40500000000007 |
| 2026-06-14T17:58:59+00:00 | `data/reports/stage27c_db_first_h1_atr_gate_validation/stage27c_db_first_h1_atr_gate_validation.md` | 0293600000000005;578963613461408;653421789024173;72574332566553;851412305366161;STAGE27C_GATE_VALIDATED_REVIEW_ONLY;STAGE27C_H1_ATR_GATE_VALIDATED_REVIEW_ONLY |
| 2026-06-14T17:58:44+00:00 | `data/reports/stage27b_db_first_lineage_gate_discovery/stage27b_db_first_lineage_gate_discovery.md` | 0293600000000005;578963613461408;653421789024173;7789723241189819;851412305366161;STAGE27B_GATE_CANDIDATE_REVIEW_ONLY;STAGE27B_HAS_GATE_CANDIDATE_REVIEW_ONLY;STAGE27B_REJECT;STAGE27B_WATCHLIST_ONLY |
| 2026-06-14T17:58:27+00:00 | `data/reports/stage28a_discovery_factory_batch_runner/stage28a_discovery_factory_batch_runner.md` | STAGE28A_NO_PROMOTION_KEEP_DISCOVERY_OPEN;STAGE28A_REJECT |
| 2026-06-14T17:55:33+00:00 | `data/reports/active_shadow_suite_exogenous_watchlist/active_shadow_suite_exogenous_watchlist.md` | ACTIVE_SHADOW_SUITE_COMPLETED;ACTIVE_SHADOW_SUITE_WITH_EXOGENOUS_WATCHLIST_COMPLETED;STAGE31G_LOW_CADENCE_WATCHLIST_REVIEW_ONLY |
| 2026-06-14T17:55:33+00:00 | `data/reports/stage31e_exogenous_forward_shadow_tracker/stage31e_exogenous_forward_shadow_tracker.md` | STAGE31E_FORWARD_SHADOW_ACTIVE_SIGNAL_REVIEW_ONLY |
| 2026-06-14T17:55:33+00:00 | `data/reports/stage31g_exogenous_active_suite_watchlist/stage31g_exogenous_active_suite_watchlist.md` | STAGE31E_FORWARD_SHADOW_ACTIVE_SIGNAL_REVIEW_ONLY;STAGE31E_NO_RECENT_FORWARD_SHADOW_SIGNAL_RESEARCH_ONLY;STAGE31F_LOW_CADENCE_WATCHLIST_REVIEW_ONLY;STAGE31G_LOW_CADENCE_WATCHLIST_REVIEW_ONLY |
| 2026-06-14T17:55:33+00:00 | `data/reports/stage31f_exogenous_tracker_cadence_audit/stage31f_exogenous_tracker_cadence_audit.md` | STAGE31E_FORWARD_SHADOW_ACTIVE_SIGNAL_REVIEW_ONLY;STAGE31E_NO_RECENT_FORWARD_SHADOW_SIGNAL_RESEARCH_ONLY;STAGE31F_LOW_CADENCE_WATCHLIST_REVIEW_ONLY |
| 2026-06-14T17:55:33+00:00 | `data/reports/stage31f_exogenous_tracker_cadence_audit/stage31e_lookback_4320h.md` | STAGE31E_FORWARD_SHADOW_ACTIVE_SIGNAL_REVIEW_ONLY |
| 2026-06-14T17:55:31+00:00 | `data/reports/stage31f_exogenous_tracker_cadence_audit/stage31e_lookback_2160h.md` | STAGE31E_NO_RECENT_FORWARD_SHADOW_SIGNAL_RESEARCH_ONLY |
| 2026-06-14T17:55:29+00:00 | `data/reports/stage31f_exogenous_tracker_cadence_audit/stage31e_lookback_720h.md` | STAGE31E_NO_RECENT_FORWARD_SHADOW_SIGNAL_RESEARCH_ONLY |
| 2026-06-14T17:55:28+00:00 | `data/reports/stage31f_exogenous_tracker_cadence_audit/stage31e_lookback_336h.md` | STAGE31E_NO_RECENT_FORWARD_SHADOW_SIGNAL_RESEARCH_ONLY |
| 2026-06-14T17:55:24+00:00 | `data/reports/active_shadow_suite/active_shadow_suite.md` | ACTIVE_SHADOW_SUITE_COMPLETED;STAGE23D_NO_ACTIVE_FORWARD_SIGNAL_RESEARCH_ONLY;STAGE25D_NO_ACTIVE_FILTERED_FORWARD_SIGNAL_RESEARCH_ONLY;STAGE27D_NO_ACTIVE_H1_ATR_FILTERED_FORWARD_SIGNAL_RESEARCH_ONLY;UNIFIED_ACTIVE_NO_SIGNAL_YET |
| 2026-06-14T17:55:24+00:00 | `data/reports/stage27d_db_first_h1_atr_filtered_forward_shadow/stage27d_db_first_h1_atr_filtered_forward_shadow.md` | LATE_DETECTED_ALREADY_RESOLVED;STAGE27D_NO_ACTIVE_H1_ATR_FILTERED_FORWARD_SIGNAL_RESEARCH_ONLY |
| 2026-06-14T17:55:09+00:00 | `data/reports/stage25d_db_first_filtered_forward_shadow/stage25d_db_first_filtered_forward_shadow.md` | LATE_DETECTED_ALREADY_RESOLVED;STAGE25D_NO_ACTIVE_FILTERED_FORWARD_SIGNAL_RESEARCH_ONLY |
| 2026-06-14T17:54:55+00:00 | `data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_candidate.md` | FORWARD_OPEN_FIRST_SEEN_BEFORE_OUTCOME;LATE_DETECTED_ALREADY_RESOLVED;STAGE23D_NO_ACTIVE_FORWARD_SIGNAL_RESEARCH_ONLY |
| 2026-06-14T17:54:39+00:00 | `data/reports/stage18e_shortlist_forward_shadow_collector/stage18e_shortlist_forward_shadow_collector.md` | BROKER_BAR_TIME;C1_PDL_RECLAIM_H6;C2_ASIA_HIGH_NY_H48;SHORTLIST_ACTIVE_NO_SIGNAL_YET |
| 2026-06-14T17:54:39+00:00 | `data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.md` | BROKER_FORWARD_ACTIVE_NO_SIGNAL_YET;C1_PDL_RECLAIM_H6;C2_ASIA_HIGH_NY_H48;SHORTLIST_ACTIVE_NO_SIGNAL_YET;TRUE_FORWARD_STARTED_NO_SIGNALS_YET;UNIFIED_ACTIVE_NO_SIGNAL_YET |
| 2026-06-14T17:54:17+00:00 | `data/reports/stage16c_true_forward_shadow_collector/stage16c_true_forward_shadow_collector.md` | TRUE_FORWARD_STARTED_NO_SIGNALS_YET |
| 2026-06-14T17:54:03+00:00 | `data/reports/stage16e_amarkets_csv_refresh_cycle/stage16e_amarkets_csv_refresh_cycle.md` |  |
| 2026-06-13T22:55:11+00:00 | `data/reports/stage31e_exogenous_forward_shadow_tracker/stage31e_lookback_180d.md` | STAGE31E_FORWARD_SHADOW_ACTIVE_SIGNAL_REVIEW_ONLY |
| 2026-06-13T22:55:09+00:00 | `data/reports/stage31e_exogenous_forward_shadow_tracker/stage31e_lookback_90d.md` | STAGE31E_NO_RECENT_FORWARD_SHADOW_SIGNAL_RESEARCH_ONLY |
| 2026-06-13T22:55:07+00:00 | `data/reports/stage31e_exogenous_forward_shadow_tracker/stage31e_lookback_30d.md` | STAGE31E_NO_RECENT_FORWARD_SHADOW_SIGNAL_RESEARCH_ONLY |
| 2026-06-13T22:47:56+00:00 | `data/reports/stage31d_exogenous_candidate_confirmation/stage31d_exogenous_candidate_confirmation.md` | STAGE31D_FRAGILE_CONFIRMED_DIAGNOSTIC_ONLY;STAGE31D_HAS_CONFIRMED_EXOGENOUS_CANDIDATE_REVIEW_ONLY;STAGE31D_REJECT_CONFIRMATION |
| 2026-06-13T22:40:48+00:00 | `data/reports/stage31c_exogenous_edge_audit/stage31c_exogenous_edge_audit.md` | STAGE31C_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY;STAGE31C_FRAGILE_POSITIVE_DIAGNOSTIC_ONLY;STAGE31C_HAS_EXOGENOUS_AUDIT_CANDIDATE_REVIEW_ONLY |
| 2026-06-13T22:31:26+00:00 | `data/reports/stage31b_exogenous_gate_validation/stage31b_exogenous_gate_validation.md` | REJECT_NO_FORWARD_EDGE;REVIEW_WEAK_IMPROVEMENT_ONLY;STAGE31B_HAS_WEAK_EXOGENOUS_GATE_IMPROVEMENT_REVIEW_ONLY |
| 2026-06-13T22:22:32+00:00 | `data/reports/stage31a_exogenous_feature_ingestion/stage31a_exogenous_feature_ingestion.md` | 00242322;00770761;STAGE31A_EXOGENOUS_FEATURE_DATASET_READY_FOR_STAGE31B_REVIEW_ONLY |

## Database object manifest

| object | name | status | row_count | columns_sample |
|---|---|---|---:|---|
| table | `bars` | ok | 1559825 | source,symbol,timeframe,utc_time,open,high,low,close,tick_volume,spread,real_volume,source_time,imported_utc,raw_json,volume,ingested_at |
| table | `dryrun_outcomes` | ok | 1 | strategy_id,symbol,signal_closed_h1_utc,entry_utc,entry_price,tp_price,sl_price,exit_utc,exit_price,status,reason,session_utc,net_usd_x1,m1_bars_checked,imported_utc,raw_json |
| table | `dryrun_signals` | ok | 1 | strategy_id,symbol,signal_closed_h1_utc,signal_closed_h1_server,logged_at_gmt,session_utc,close_h1,sma10,distance_usd,direction,planned_entry_model,tp_usd,sl_usd,time_exit_h1_bars,dry_run_only,imported_utc,raw_json |
| table | `event_impact_validation_summary` | ok | 7 | event_class,event_channel,events_declustered,controls,avg_event_norm12,avg_control_norm12,avg_impact_lift,median_event_norm12,median_control_norm12,median_impact_lift,event_high_medium_rate,control_high_medium_rate,impact_rate_lift,event_noise_rate,control_noise_rate,event_direction_accuracy,control |
| table | `event_pipeline_runs` | ok | 2 | run_id,tool_version,status,scheduled_count,manual_count,shock_count,unified_count,generated_utc,warnings |
| table | `event_pipeline_staging` | ok | 5 | event_id,event_time_utc,event_end_utc,title,event_class,event_channel,expected_gold_direction,initial_importance,confidence,source_name,source_url_or_note,manual_tags,notes,source_kind,dedupe_key,imported_utc |
| table | `import_runs` | ok | 20 | id,created_utc,tool_version,source,dataset,timeframe,path,sha256,rows_seen,rows_inserted,rows_updated,rows_bad,start_utc,end_utc,metadata_json |
| table | `macro_context_h1` | ok | 24225 | utc_time,macro_score,macro_regime,active_event_count,active_event_ids,active_labels,has_block_event,generated_utc |
| table | `macro_daily_regime` | ok | 1620 | obs_date,real_yield_10y,nominal_yield_10y,nominal_yield_2y,usd_index,wti,brent,cpi,ppi,fedfunds,d_real_yield_5d,d_real_yield_20d,d_usd_5d_pct,d_usd_20d_pct,d_oil_5d_pct,d_oil_20d_pct,yield_curve_10y2y,rate_pressure_score,usd_pressure_score,oil_inflation_pressure_score,growth_fear_score,macro_score_l |
| table | `macro_events` | ok | 0 | event_id,event_time_utc,event_end_utc,window_start_utc,window_end_utc,label,category,impact,guard_before_min,guard_after_min,mode,event_gold_bias,safe_haven_score,real_yield_pressure,usd_pressure,oil_inflation_pressure,growth_fear_score,central_bank_demand_score,confidence,macro_score,macro_regime,s |
| table | `macro_numeric_observations` | ok | 8444 | source,series_id,obs_date,value,realtime_start,realtime_end,label,category,gold_driver,update_frequency,units_hint,fetched_utc,ssl_mode |
| table | `macro_update_runs` | ok | 8 | run_id,tool_version,source,status,series_requested,series_ok,observations_written,generated_utc,message |
| table | `news_event_class_weights` | ok | 7 | event_class,event_channel,events,avg_adaptive_score,avg_abs_impact_12h,avg_norm_impact_12h,direction_accuracy_12h,candidate_relevant_count,likely_noise_count,recommended_weight,generated_utc |
| table | `news_event_reactions` | ok | 510 | event_id,event_time_utc,title,event_class,event_channel,source_name,expected_gold_direction,initial_importance,confidence,macro_regime_numeric,macro_score_long_gold,anchor_bar_utc,anchor_price,ret_1h,ret_4h,ret_12h,ret_24h,mfe_12h,mae_12h,abs_impact_4h,abs_impact_12h,normalized_impact_4h,normalized_ |
| table | `news_events` | ok | 516 | event_id,event_time_utc,event_end_utc,title,event_class,event_channel,expected_gold_direction,initial_importance,confidence,source_name,source_url_or_note,manual_tags,notes,imported_utc |
| table | `numeric_shock_event_runs` | ok | 3 | run_id,tool_version,generated_events,merged_events,generated_utc |
| table | `numeric_shock_events` | ok | 500 | event_id,event_time_utc,event_end_utc,title,event_class,event_channel,expected_gold_direction,initial_importance,confidence,source_name,source_url_or_note,manual_tags,notes,generated_utc |
| table | `sqlite_sequence` | ok | 1 | name,seq |

## Operational interpretation

```text
1. Observation alone is insufficient if the candidate pool remains low-cadence.
2. Keep active/shadow tracking running, but use supply/full modes to keep discovery and lineage validation alive.
3. Treat low-cadence Stage31 candidates as watchlist/status, not as the primary commercial candidate pool.
4. Use candidate_supply_summary.csv/json to decide whether the next patch should expand density, repair a discovery arm, or enrich calendar events.
5. Any paper/live/EA transition still requires explicit evidence and explicit user authorization.
```

## Output files

- `data/reports/research_shadow_orchestrator/research_shadow_orchestrator.md`
- `data/reports/research_shadow_orchestrator/candidate_registry.csv`
- `data/reports/research_shadow_orchestrator/candidate_registry.json`
- `data/reports/research_shadow_orchestrator/candidate_supply_summary.csv`
- `data/reports/research_shadow_orchestrator/candidate_supply_summary.json`
- `data/reports/research_shadow_orchestrator/commercial_readiness_summary.json`
- `data/reports/research_shadow_orchestrator/db_data_freshness.csv`
- `data/reports/research_shadow_orchestrator/db_data_freshness.json`
- `data/reports/stage32b_dense_forward_shadow_intake/stage32b_dense_forward_shadow_intake.md`
- `data/reports/stage32b_dense_forward_shadow_intake/shadow_intake_queue.csv`
- `data/reports/stage32b_dense_forward_shadow_intake/family_density_triage.csv`
- `data/reports/stage32b_dense_forward_shadow_intake/stage32b_summary.json`
- `data/reports/stage32c_dense_forward_shadow_tracker/stage32c_dense_forward_shadow_tracker.md`
- `data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_signal_snapshot.csv`
- `data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_candidate_summary.csv`
- `data/reports/stage32c_dense_forward_shadow_tracker/stage32c_summary.json`
- `data/reports/stage32d_dense_forward_review/stage32d_dense_forward_review.md`
- `data/reports/stage32d_dense_forward_review/dense_variant_tightening_plan.csv`
- `data/reports/stage32d_dense_forward_review/dense_review_candidate_diagnostics.csv`
- `data/reports/stage32d_dense_forward_review/stage32d_summary.json`
- `data/reports/stage32e_extended_dense_shadow_monitor/stage32e_extended_dense_shadow_monitor.md`
- `data/reports/stage32e_extended_dense_shadow_monitor/extended_shadow_focus_queue.csv`
- `data/reports/stage32e_extended_dense_shadow_monitor/suppressed_variant_plan.csv`
- `data/reports/stage32e_extended_dense_shadow_monitor/pre_commercial_robustness_queue.csv`
- `data/reports/stage32e_extended_dense_shadow_monitor/stage32e_summary.json`
- `data/reports/research_shadow_orchestrator/module_runs.csv`
- `data/reports/research_shadow_orchestrator/report_manifest.csv`
- `data/reports/research_shadow_orchestrator/stage_status_manifest.csv`

