# Stage44_THESIS_SPACE_FAILURE_META_DIAGNOSTIC

## Decision

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

Stage44 is a meta-diagnostic only. It does not create signals, does not shortlist candidates, and cannot promote any prior row.

## Inputs analyzed

| stage | reported_stage | candidate_rows_csv | events_rows_written | strict_watch_count | soft_watch_count | promotion |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| stage41 | Stage41_PARALLEL_THESIS_MEGASCAN_V2 | 180 | 19627 | 0 | 0 | NO_GO |
| stage42 | Stage42_PARALLEL_INTRADAY_EXECUTION_MEGASCAN_V3 | 168 | 103371 | 0 | 0 | NO_GO |
| stage43 | Stage43_PARALLEL_CONTEXT_REGIME_MEGASCAN_V4 | 336 | 49079 | 0 | 0 | NO_GO |


## Aggregate result

```text
total_candidates_analyzed = 684
total_strict_watch_count = 0
total_soft_watch_count = 0
```

## Classification counts

| key | n |
| :-- | :-- |
| INSUFFICIENT_EVENTS_RESEARCH_ONLY | 287 |
| FAIL_BENCHMARK_OR_STABILITY_RESEARCH_ONLY | 136 |
| FAIL_BENCHMARK_OR_CONTEXT_STABILITY_RESEARCH_ONLY | 133 |
| FAIL_BENCHMARK_OR_INTRADAY_STABILITY_RESEARCH_ONLY | 128 |


## Failed reason bucket counts

| key | n |
| :-- | :-- |
| bootstrap_stability | 730 |
| quarter_stability | 726 |
| other | 684 |
| train_segment | 372 |
| oos_segment | 357 |
| cost_or_mean_edge | 357 |
| event_scarcity | 287 |
| benchmark_residual | 207 |
| concentration | 8 |


## Most frequent raw failed reasons

| key | n |
| :-- | :-- |
| boot_p10_gt_minus5 | 368 |
| train_gt_0 | 334 |
| oos_gt_0 | 294 |
| INSUFFICIENT_EVENTS_RESEARCH_ONLY | 287 |
| worst_quarter_slip16_gt_minus20 | 261 |
| boot_prob_gt_65 | 261 |
| positive_quarter_pct_ge_45 | 261 |
| event_clock_n_lt_120 | 203 |
| FAIL_BENCHMARK_OR_STABILITY_RESEARCH_ONLY | 136 |
| worst_quarter_slip16_gt_minus10 | 136 |
| FAIL_BENCHMARK_OR_CONTEXT_STABILITY_RESEARCH_ONLY | 133 |
| cost_mean_gt_12 | 133 |
| FAIL_BENCHMARK_OR_INTRADAY_STABILITY_RESEARCH_ONLY | 128 |
| cost_mean_gt_15 | 128 |
| residual_gt_3 | 116 |
| boot_prob_gt_70 | 101 |
| cost_mean_gt_8 | 96 |
| residual_gt_0 | 91 |
| event_clock_n_below_min | 84 |
| positive_quarter_pct_ge_50 | 68 |
| oos_n_too_small | 61 |
| train_n_too_small | 38 |
| top_year_event_share_le_38 | 8 |
| oos_touch100_le_65 | 2 |


## Dominant blockers

```text
no_shortlist_across_recent_scans
cost_adjusted_mean_edge_not_sufficient
worst_quarter_or_quarter_stability_fragility
bootstrap_tail_or_probability_weakness
event_scarcity_for_context_filtered_theses
weak_or_negative_residual_vs_benchmark
train_oos_instability
year_or_event_concentration_risk
```

## Numeric profile

| metric | n | min | p10 | median | p90 | max | mean |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| cost_stressed_mean_bps | 684 | -117.162 | -21.205 | -7.383 | 8.820 | 121.588 | -6.275 |
| h1_benchmark_cost_adjusted_residual_bps | 180 | -113.358 | -14.707 | 4.864 | 38.495 | 112.857 | 8.166 |
| intraday_benchmark_cost_adjusted_residual_bps | 168 | -57.794 | -1.974 | 0.855 | 5.700 | 42.350 | 1.435 |
| context_benchmark_cost_adjusted_residual_bps | 133 | -16.881 | -4.222 | -0.679 | 3.622 | 6.434 | -0.671 |
| train_cost_mean_bps | 481 | -73.698 | -15.340 | -7.483 | 9.345 | 127.706 | -4.481 |
| oos_cost_mean_bps | 481 | -228.204 | -35.339 | -6.364 | 34.732 | 255.356 | -3.564 |
| worst_quarter_slip16_mean_bps | 481 | -351.708 | -184.564 | -58.554 | -30.868 | -22.951 | -89.119 |
| boot_p10_bps | 463 | -155.962 | -32.948 | -11.055 | -6.010 | 66.755 | -15.875 |
| oos_touch_stop_100bps_pct | 180 | 9.091 | 21.869 | 44.808 | 66.667 | 100.000 | 43.450 |
| oos_touch_stop_50bps_pct | 301 | 0.000 | 7.292 | 26.437 | 52.083 | 100.000 | 29.489 |
| top_year_event_share_pct | 481 | 21.260 | 24.940 | 29.630 | 40.708 | 100.000 | 31.675 |
| event_clock_n | 684 | 1.000 | 19.300 | 115.500 | 611.800 | 3049.000 | 251.575 |
| horizon_h | 180 | 12.000 | 12.000 | 36.000 | 72.000 | 72.000 | 38.000 |
| horizon_minutes | 504 | 60.000 | 60.000 | 120.000 | 480.000 | 480.000 | 216.905 |


## Best rows by cost-stressed mean

| stage | family | candidate | side | event_clock_n | cost_stressed_mean_bps | train_cost_mean_bps | oos_cost_mean_bps | worst_quarter_slip16_mean_bps | boot_p10_bps | failed_reasons |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_LONG_W72_HTF | LONG | 23 | 121.588 | 127.706 | 107.604 | -88.779 | 66.755 | event_clock_n_below_min;oos_n_too_small |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_LONG_W72_HTF | LONG | 23 | 83.304 | 104.199 | 35.546 | -22.951 | 43.674 | event_clock_n_below_min;oos_n_too_small |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_SHORT_W120_HTF | SHORT | 27 | 79.878 | -7.861 | 255.356 | -316.110 | 1.974 | event_clock_n_below_min;oos_n_too_small |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_LONG_W120_HTF | LONG | 38 | 74.133 | 72.635 | 77.381 | -124.229 | 38.530 | event_clock_n_below_min |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_SHORT_W168_HTF | SHORT | 32 | 74.084 | 23.254 | 185.911 | -316.110 | 8.978 | event_clock_n_below_min |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_SHORT_W72_HTF | SHORT | 24 | 73.711 | 10.116 | 200.902 | -316.110 | -11.021 | event_clock_n_below_min;oos_n_too_small |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_LONG_W168_HTF | LONG | 41 | 72.376 | 61.731 | 95.303 | -86.768 | 41.381 | worst_quarter_slip16_gt_minus10;oos_touch100_le_65 |
| stage41 | 41C_SHOCK_COOLDOWN_CONTINUATION | SHOCK_COOLDOWN_CONT_LONG_M2.4 | LONG | 5 | 66.916 | 42.107 | 104.130 | -184.417 |  | event_clock_n_below_min;train_n_too_small;oos_n_too_small |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_LONG_W120_NO_HTF | LONG | 59 | 63.007 | 23.262 | 153.536 | -154.470 | 30.709 | worst_quarter_slip16_gt_minus10 |
| stage43 | 43E_ASIA_RANGE_REGIME_ACCEPT_REJECT | ASIA_REGIME_REJECT_SHORT_TOL25 | SHORT | 5 | 48.814 |  |  |  |  | event_clock_n_lt_120 |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_LONG_W72_NO_HTF | LONG | 48 | 47.767 | 26.639 | 94.247 | -322.400 | 3.361 | worst_quarter_slip16_gt_minus10;oos_touch100_le_65 |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_LONG_W120_HTF | LONG | 38 | 47.210 | 48.486 | 44.446 | -226.192 | 11.851 | event_clock_n_below_min |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_LONG_W168_NO_HTF | LONG | 69 | 45.381 | 17.711 | 108.626 | -143.311 | 17.670 | worst_quarter_slip16_gt_minus10 |
| stage43 | 43F_NEUTRAL_REGIME_VALUE_ROTATION | NEUTRAL_VALUE_ROTATE_LONG_LDN_P55 | LONG | 3 | 35.984 |  |  |  |  | event_clock_n_lt_120 |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_LONG_W72_HTF | LONG | 25 | 35.403 | 53.041 | -2.077 | -120.436 | 9.550 | event_clock_n_below_min;oos_n_too_small |
| stage42 | 42B_NY_IMPULSE_PULLBACK_CONTINUATION | NY_IMPULSE_PULLBACK_SHORT_I70 | SHORT | 30 | 32.956 | 21.543 | 59.585 | -102.626 | 13.795 | event_clock_n_below_min;train_n_too_small;oos_n_too_small |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_SHORT_W72_NO_HTF | SHORT | 42 | 31.429 | -13.456 | 131.555 | -214.239 | -28.225 | train_gt_0;worst_quarter_slip16_gt_minus10;boot_p10_gt_minus5 |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_LONG_W72_NO_HTF | LONG | 48 | 31.151 | 31.421 | 30.557 | -281.480 | -8.135 | worst_quarter_slip16_gt_minus10;boot_p10_gt_minus5 |
| stage41 | 41A_MTF_STRUCTURE_BREAK_RETEST | MTF_BREAK_RETEST_LONG_W240_TOL20 | LONG | 79 | 30.089 | 10.259 | 75.534 | -173.274 | 13.744 | worst_quarter_slip16_gt_minus10 |
| stage41 | 41A_MTF_STRUCTURE_BREAK_RETEST | MTF_BREAK_RETEST_LONG_W240_TOL35 | LONG | 79 | 30.089 | 10.259 | 75.534 | -173.274 | 13.744 | worst_quarter_slip16_gt_minus10 |
| stage41 | 41A_MTF_STRUCTURE_BREAK_RETEST | MTF_BREAK_RETEST_LONG_W240_TOL50 | LONG | 79 | 30.089 | 10.259 | 75.534 | -173.274 | 13.744 | worst_quarter_slip16_gt_minus10 |
| stage43 | 43E_ASIA_RANGE_REGIME_ACCEPT_REJECT | ASIA_REGIME_REJECT_LONG_TOL40 | LONG | 4 | 28.094 |  |  |  |  | event_clock_n_lt_120 |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_LONG_W168_HTF | LONG | 45 | 27.397 | 25.930 | 30.646 | -173.238 | -1.769 | worst_quarter_slip16_gt_minus10 |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_SHORT_W168_HTF | SHORT | 35 | 25.485 | 2.569 | 75.484 | -150.300 | -1.760 | event_clock_n_below_min |
| stage41 | 41C_SHOCK_COOLDOWN_CONTINUATION | SHOCK_COOLDOWN_CONT_LONG_M2.0 | LONG | 11 | 24.595 | -18.383 | 99.808 | -184.417 | -83.139 | event_clock_n_below_min;train_n_too_small;oos_n_too_small |


## Best rows by worst-quarter slip16

| stage | family | candidate | side | event_clock_n | worst_quarter_slip16_mean_bps | cost_stressed_mean_bps | failed_reasons |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_LONG_W72_HTF | LONG | 23 | -22.951 | 83.304 | event_clock_n_below_min;oos_n_too_small |
| stage42 | 42F_MICROTREND_PULLBACK_HOLD | MICROTREND_PULLBACK_SHORT_P8 | SHORT | 1077 | -25.045 | -4.444 | cost_mean_gt_15;train_gt_0;oos_gt_0;worst_quarter_slip16_gt_minus20;boot_p10_gt_minus5;boot_prob_gt_65;positive_quart... |
| stage42 | 42F_MICROTREND_PULLBACK_HOLD | MICROTREND_PULLBACK_SHORT_P15 | SHORT | 1137 | -25.525 | -4.457 | cost_mean_gt_15;train_gt_0;oos_gt_0;worst_quarter_slip16_gt_minus20;boot_p10_gt_minus5;boot_prob_gt_65;positive_quart... |
| stage42 | 42F_MICROTREND_PULLBACK_HOLD | MICROTREND_PULLBACK_SHORT_P25 | SHORT | 1167 | -26.235 | -4.864 | cost_mean_gt_15;train_gt_0;oos_gt_0;worst_quarter_slip16_gt_minus20;boot_p10_gt_minus5;boot_prob_gt_65;positive_quart... |
| stage42 | 42C_PREVDAY_LIQUIDITY_SWEEP_REVERSAL | PREVDAY_HIGH_SWEEP_REJECT_SHORT_TOL35 | SHORT | 2 | -26.749 | -0.296 | event_clock_n_below_min;train_n_too_small;oos_n_too_small |
| stage42 | 42D_INTRADAY_COMPRESSION_EXPANSION_CONFIRM | INTRADAY_COMP_EXPAND_LONG_C24H | LONG | 868 | -26.763 | -8.053 | cost_mean_gt_15;residual_gt_0;train_gt_0;oos_gt_0;worst_quarter_slip16_gt_minus20;boot_p10_gt_minus5;boot_prob_gt_65;... |
| stage42 | 42F_MICROTREND_PULLBACK_HOLD | MICROTREND_PULLBACK_SHORT_P25 | SHORT | 2283 | -26.976 | -7.055 | cost_mean_gt_15;train_gt_0;oos_gt_0;worst_quarter_slip16_gt_minus20;boot_p10_gt_minus5;boot_prob_gt_65;positive_quart... |
| stage42 | 42F_MICROTREND_PULLBACK_HOLD | MICROTREND_PULLBACK_LONG_P40 | LONG | 3049 | -27.032 | -8.050 | cost_mean_gt_15;residual_gt_0;train_gt_0;oos_gt_0;worst_quarter_slip16_gt_minus20;boot_p10_gt_minus5;boot_prob_gt_65;... |
| stage42 | 42F_MICROTREND_PULLBACK_HOLD | MICROTREND_PULLBACK_SHORT_P40 | SHORT | 2304 | -27.039 | -6.985 | cost_mean_gt_15;train_gt_0;oos_gt_0;worst_quarter_slip16_gt_minus20;boot_p10_gt_minus5;boot_prob_gt_65;positive_quart... |
| stage42 | 42F_MICROTREND_PULLBACK_HOLD | MICROTREND_PULLBACK_LONG_P15 | LONG | 2911 | -27.132 | -8.028 | cost_mean_gt_15;residual_gt_0;train_gt_0;oos_gt_0;worst_quarter_slip16_gt_minus20;boot_p10_gt_minus5;boot_prob_gt_65;... |
| stage42 | 42F_MICROTREND_PULLBACK_HOLD | MICROTREND_PULLBACK_SHORT_P40 | SHORT | 1178 | -27.275 | -4.855 | cost_mean_gt_15;train_gt_0;oos_gt_0;worst_quarter_slip16_gt_minus20;boot_p10_gt_minus5;boot_prob_gt_65;positive_quart... |
| stage42 | 42F_MICROTREND_PULLBACK_HOLD | MICROTREND_PULLBACK_SHORT_P15 | SHORT | 2203 | -27.384 | -6.999 | cost_mean_gt_15;train_gt_0;oos_gt_0;worst_quarter_slip16_gt_minus20;boot_p10_gt_minus5;boot_prob_gt_65;positive_quart... |
| stage42 | 42F_MICROTREND_PULLBACK_HOLD | MICROTREND_PULLBACK_LONG_P8 | LONG | 2608 | -27.474 | -8.003 | cost_mean_gt_15;residual_gt_0;train_gt_0;oos_gt_0;worst_quarter_slip16_gt_minus20;boot_p10_gt_minus5;boot_prob_gt_65;... |
| stage42 | 42F_MICROTREND_PULLBACK_HOLD | MICROTREND_PULLBACK_LONG_P25 | LONG | 3020 | -27.660 | -8.171 | cost_mean_gt_15;residual_gt_0;train_gt_0;oos_gt_0;worst_quarter_slip16_gt_minus20;boot_p10_gt_minus5;boot_prob_gt_65;... |
| stage42 | 42F_MICROTREND_PULLBACK_HOLD | MICROTREND_PULLBACK_SHORT_P15 | SHORT | 1600 | -27.728 | -6.052 | cost_mean_gt_15;train_gt_0;oos_gt_0;worst_quarter_slip16_gt_minus20;boot_p10_gt_minus5;boot_prob_gt_65;positive_quart... |
| stage42 | 42F_MICROTREND_PULLBACK_HOLD | MICROTREND_PULLBACK_SHORT_P8 | SHORT | 2018 | -27.816 | -6.917 | cost_mean_gt_15;train_gt_0;oos_gt_0;worst_quarter_slip16_gt_minus20;boot_p10_gt_minus5;boot_prob_gt_65;positive_quart... |
| stage42 | 42A_LONDON_ASIA_RANGE_MICRO_RETEST | LONDON_ASIA_BREAK_HOLD_LONG_TOL15 | LONG | 602 | -28.012 | -6.643 | cost_mean_gt_15;train_gt_0;oos_gt_0;worst_quarter_slip16_gt_minus20;boot_p10_gt_minus5;boot_prob_gt_65;positive_quart... |
| stage42 | 42F_MICROTREND_PULLBACK_HOLD | MICROTREND_PULLBACK_SHORT_P8 | SHORT | 1493 | -28.025 | -6.102 | cost_mean_gt_15;train_gt_0;oos_gt_0;worst_quarter_slip16_gt_minus20;boot_p10_gt_minus5;boot_prob_gt_65;positive_quart... |
| stage42 | 42D_INTRADAY_COMPRESSION_EXPANSION_CONFIRM | INTRADAY_COMP_EXPAND_LONG_C12H | LONG | 492 | -28.078 | -7.222 | cost_mean_gt_15;train_gt_0;oos_gt_0;worst_quarter_slip16_gt_minus20;boot_p10_gt_minus5;boot_prob_gt_65;positive_quart... |
| stage42 | 42D_INTRADAY_COMPRESSION_EXPANSION_CONFIRM | INTRADAY_COMP_EXPAND_LONG_C12H | LONG | 451 | -28.269 | -5.686 | cost_mean_gt_15;train_gt_0;oos_gt_0;worst_quarter_slip16_gt_minus20;boot_p10_gt_minus5;boot_prob_gt_65;positive_quart... |


## Recommendation

```text
archive_recent_blind_megascans = True
do_not_build_stage41b_42b_43b = True
do_not_promote_any_recent_candidate = True
next_stage = Stage45_COST_AWARE_BASELINE_RECALIBRATION_OR_EXTERNAL_CONTEXT_DECISION
```

Recent parallel thesis scans produced no strict or soft shortlist. The failure pattern should be treated as thesis-space evidence, not as a prompt for post-hoc filtering. The next efficient step is to recalibrate what edge must beat under realistic cost/spread/slip and decide whether external macro/news/yields context is required before more thesis scanning.

## Allowed next options

- `Stage45A cost/spread/slip sensitivity and threshold recalibration using existing candidate/event outputs`
- `Stage45B external-context decision document: DXY/yields/news calendar/CME GC reference before new scans`
- `Stage45C data-source/feed comparison if broker CFD microstructure appears too noisy for intraday edges`

## Not allowed

- `Stage41B/Stage42B/Stage43B without strict shortlist`
- `post-hoc removal of weak hours/months/years/quarters/context states`
- `EA/paper-live/live from archived rows`
- `ML model before a robust cost-aware baseline exists`

## Anti-overfit note

Do not rescue Stage41/42/43 rows by post-hoc filtering. Any future scan must be a genuinely new pre-defined thesis or a cost/data-source/external-context decision phase.
