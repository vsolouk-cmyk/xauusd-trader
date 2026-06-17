# Stage45_COST_AWARE_BASELINE_RECALIBRATION_OR_EXTERNAL_CONTEXT_DECISION

## Decision

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
recommended_next_stage = Stage45C_FEED_AND_TRANSACTION_COST_REALISM_AUDIT
```

Stage45 is a diagnostic and decision step. It does not create trading signals, does not promote any candidate, and does not authorize operational layers.

## Inputs

| stage | candidate_rows_csv | events_rows_written | strict_watch_count | soft_watch_count | promotion |
| :-- | :-- | :-- | :-- | :-- | :-- |
| stage41 | 180 | 19627 | 0 | 0 | NO_GO |
| stage42 | 168 | 103371 | 0 | 0 | NO_GO |
| stage43 | 336 | 49079 | 0 | 0 | NO_GO |


## Aggregate profile

```text
total_candidates_analyzed = 684
total_strict_watch_count = 0
total_soft_watch_count = 0
```

## Numeric profile

| metric | n | min | p10 | median | p90 | max | mean |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| cost_stressed_mean_bps | 684 | -117.162 | -21.205 | -7.383 | 8.820 | 121.588 | -6.275 |
| train_cost_mean_bps | 481 | -73.698 | -15.340 | -7.483 | 9.345 | 127.706 | -4.481 |
| oos_cost_mean_bps | 481 | -228.204 | -35.339 | -6.364 | 34.732 | 255.356 | -3.564 |
| worst_quarter_slip16_mean_bps | 481 | -351.708 | -184.564 | -58.554 | -30.868 | -22.951 | -89.119 |
| boot_p10_bps | 463 | -155.962 | -32.948 | -11.055 | -6.010 | 66.755 | -15.875 |
| event_clock_n | 684 | 1.000 | 19.300 | 115.500 | 611.800 | 3049.000 | 251.575 |
| top_year_event_share_pct | 481 | 21.260 | 24.940 | 29.630 | 40.708 | 100.000 | 31.675 |
| h1_benchmark_cost_adjusted_residual_bps | 180 | -113.358 | -14.707 | 4.864 | 38.495 | 112.857 | 8.166 |
| intraday_benchmark_cost_adjusted_residual_bps | 168 | -57.794 | -1.974 | 0.855 | 5.700 | 42.350 | 1.435 |
| context_benchmark_cost_adjusted_residual_bps | 133 | -16.881 | -4.222 | -0.679 | 3.622 | 6.434 | -0.671 |
| oos_touch_stop_100bps_pct | 180 | 9.091 | 21.869 | 44.808 | 66.667 | 100.000 | 43.450 |
| oos_touch_stop_50bps_pct | 301 | 0.000 | 7.292 | 26.437 | 52.083 | 100.000 | 29.489 |
| stage_residual_bps | 481 | -113.358 | -8.048 | 0.668 | 20.483 | 112.857 | 3.372 |


## Cost/slip sensitivity scenarios

| scenario | cost_saving_bps | pass_count | near_miss_count_failures_le_2 | pass_by_stage |
| :-- | :-- | :-- | :-- | :-- |
| observed_costs_current_strict | 0.000 | 0 | 23 | {} |
| realistic_cost_improvement_plus4 | 4.000 | 0 | 46 | {} |
| aggressive_cost_improvement_plus8 | 8.000 | 0 | 82 | {} |
| very_low_cost_plus16_diagnostic_only | 16.000 | 4 | 189 | {'stage42': 4} |
| minimal_edge_sanity_observed | 0.000 | 0 | 44 | {} |
| event_scarcity_probe_min40 | 0.000 | 0 | 36 | {} |


## Cost improvement needed

```json
{
  "eligible_rows_with_event_residual_concentration": 78,
  "required_uniform_bps_improvement_profile": {
    "n": 78,
    "min": 12.38547132850297,
    "p10": 16.455562689206612,
    "median": 27.188406848506986,
    "p90": 67.14166589945577,
    "max": 108.74588501975248,
    "mean": 33.77671306776575
  },
  "best_rows_by_required_improvement": [
    {
      "stage": "stage42",
      "family": "42D_INTRADAY_COMPRESSION_EXPANSION_CONFIRM",
      "candidate": "INTRADAY_COMP_EXPAND_LONG_C8H",
      "side": "LONG",
      "event_clock_n": 379.0,
      "stage_residual_bps": 4.821740550839101,
      "cost_stressed_mean_bps": -0.3854713285029687,
      "train_cost_mean_bps": -2.2883223059921693,
      "oos_cost_mean_bps": 4.037822610397368,
      "worst_quarter_slip16_mean_bps": -29.584096567195918,
      "boot_p10_bps": -3.896172768683452,
      "required_uniform_bps_improvement_to_pass_numeric_gates": 12.38547132850297
    },
    {
      "stage": "stage42",
      "family": "42D_INTRADAY_COMPRESSION_EXPANSION_CONFIRM",
      "candidate": "INTRADAY_COMP_EXPAND_LONG_C12H",
      "side": "LONG",
      "event_clock_n": 374.0,
      "stage_residual_bps": 4.341589752288924,
      "cost_stressed_mean_bps": -0.865622127053145,
      "train_cost_mean_bps": -1.345104505408001,
      "oos_cost_mean_bps": 0.2418548707399327,
      "worst_quarter_slip16_mean_bps": -30.61413198796384,
      "boot_p10_bps": -4.528841272524061,
      "required_uniform_bps_improvement_to_pass_numeric_gates": 12.865622127053145
    },
    {
      "stage": "stage42",
      "family": "42D_INTRADAY_COMPRESSION_EXPANSION_CONFIRM",
      "candidate": "INTRADAY_COMP_EXPAND_LONG_C4H",
      "side": "LONG",
      "event_clock_n": 510.0,
      "stage_residual_bps": 3.6948028934654626,
      "cost_stressed_mean_bps": -1.5124089858766065,
      "train_cost_mean_bps": -2.7223321350669023,
      "oos_cost_mean_bps": 1.3107450289007505,
      "worst_quarter_slip16_mean_bps": -31.877007794185914,
      "boot_p10_bps": -4.803554463782279,
      "required_uniform_bps_improvement_to_pass_numeric_gates": 13.512408985876606
    },
    {
      "stage": "stage42",
      "family": "42D_INTRADAY_COMPRESSION_EXPANSION_CONFIRM",
      "candidate": "INTRADAY_COMP_EXPAND_LONG_C8H",
      "side": "LONG",
      "event_clock_n": 413.0,
      "stage_residual_bps": 4.139428681511118,
      "cost_stressed_mean_bps": -2.466368900717116,
      "train_cost_mean_bps": -2.0276409188480655,
      "oos_cost_mean_bps": -3.4888881487828862,
      "worst_quarter_slip16_mean_bps": -28.572365907883082,
      "boot_p10_bps": -5.289756698594057,
      "required_uniform_bps_improvement_to_pass_numeric_gates": 14.466368900717116
    },
    {
      "stage": "stage42",
      "family": "42D_INTRADAY_COMPRESSION_EXPANSION_CONFIRM",
      "candidate": "INTRADAY_COMP_EXPAND_SHORT_C4H",
      "side": "SHORT",
      "event_clock_n": 413.0,
      "stage_residual_bps": 6.5687339644222,
      "cost_stressed_mean_bps": -4.224054156235732,
      "train_cost_mean_bps": -8.611303263947864,
      "oos_cost_mean_bps": 6.001066748028832,
      "worst_quarter_slip16_mean_bps": -31.864999943411465,
      "boot_p10_bps": -8.576212767183636,
      "required_uniform_bps_improvement_to_pass_numeric_gates": 16.22405415623573
    },
    {
      "stage": "stage42",
      "family": "42D_INTRADAY_COMPRESSION_EXPANSION_CONFIRM",
      "candidate": "INTRADAY_COMP_EXPAND_SHORT_C4H",
      "side": "SHORT",
      "event_clock_n": 443.0,
      "stage_residual_bps": 5.0060689275082915,
      "cost_stressed_mean_bps": -4.388133490263474,
      "train_cost_mean_bps": -8.184937925541615,
      "oos_cost_mean_bps": 4.461561058129182,
      "worst_quarter_slip16_mean_bps": -31.777316790856847,
      "boot_p10_bps": -7.298448482466704,
      "required_uniform_bps_improvement_to_pass_numeric_gates": 16.388133490263474
    },
    {
      "stage": "stage42",
      "family": "42F_MICROTREND_PULLBACK_HOLD",
      "candidate": "MICROTREND_PULLBACK_SHORT_P8",
  
```

## Dominant reasons

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


## Best rows by observed cost-stressed mean

| stage | family | candidate | side | event_clock_n | cost_stressed_mean_bps | stage_residual_bps | train_cost_mean_bps | oos_cost_mean_bps | worst_quarter_slip16_mean_bps | boot_p10_bps | failed_reasons |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_LONG_W72_HTF | LONG | 23.000 | 121.588 | 104.608 | 127.706 | 107.604 | -88.779 | 66.755 | event_clock_n_below_min;oos_n_too_small |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_LONG_W72_HTF | LONG | 23.000 | 83.304 | 74.378 | 104.199 | 35.546 | -22.951 | 43.674 | event_clock_n_below_min;oos_n_too_small |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_SHORT_W120_HTF | SHORT | 27.000 | 79.878 | 112.857 | -7.861 | 255.356 | -316.110 | 1.974 | event_clock_n_below_min;oos_n_too_small |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_LONG_W120_HTF | LONG | 38.000 | 74.133 | 57.154 | 72.635 | 77.381 | -124.229 | 38.530 | event_clock_n_below_min |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_SHORT_W168_HTF | SHORT | 32.000 | 74.084 | 107.064 | 23.254 | 185.911 | -316.110 | 8.978 | event_clock_n_below_min |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_SHORT_W72_HTF | SHORT | 24.000 | 73.711 | 106.691 | 10.116 | 200.902 | -316.110 | -11.021 | event_clock_n_below_min;oos_n_too_small |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_LONG_W168_HTF | LONG | 41.000 | 72.376 | 55.396 | 61.731 | 95.303 | -86.768 | 41.381 | worst_quarter_slip16_gt_minus10;oos_touch100_le_65 |
| stage41 | 41C_SHOCK_COOLDOWN_CONTINUATION | SHOCK_COOLDOWN_CONT_LONG_M2.4 | LONG | 5.000 | 66.916 | 57.990 | 42.107 | 104.130 | -184.417 |  | event_clock_n_below_min;train_n_too_small;oos_n_too_small |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_LONG_W120_NO_HTF | LONG | 59.000 | 63.007 | 46.027 | 23.262 | 153.536 | -154.470 | 30.709 | worst_quarter_slip16_gt_minus10 |
| stage43 | 43E_ASIA_RANGE_REGIME_ACCEPT_REJECT | ASIA_REGIME_REJECT_SHORT_TOL25 | SHORT | 5.000 | 48.814 |  |  |  |  |  | event_clock_n_lt_120 |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_LONG_W72_NO_HTF | LONG | 48.000 | 47.767 | 30.787 | 26.639 | 94.247 | -322.400 | 3.361 | worst_quarter_slip16_gt_minus10;oos_touch100_le_65 |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_LONG_W120_HTF | LONG | 38.000 | 47.210 | 38.284 | 48.486 | 44.446 | -226.192 | 11.851 | event_clock_n_below_min |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_LONG_W168_NO_HTF | LONG | 69.000 | 45.381 | 28.401 | 17.711 | 108.626 | -143.311 | 17.670 | worst_quarter_slip16_gt_minus10 |
| stage43 | 43F_NEUTRAL_REGIME_VALUE_ROTATION | NEUTRAL_VALUE_ROTATE_LONG_LDN_P55 | LONG | 3.000 | 35.984 |  |  |  |  |  | event_clock_n_lt_120 |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_LONG_W72_HTF | LONG | 25.000 | 35.403 | 34.901 | 53.041 | -2.077 | -120.436 | 9.550 | event_clock_n_below_min;oos_n_too_small |
| stage42 | 42B_NY_IMPULSE_PULLBACK_CONTINUATION | NY_IMPULSE_PULLBACK_SHORT_I70 | SHORT | 30.000 | 32.956 | 42.350 | 21.543 | 59.585 | -102.626 | 13.795 | event_clock_n_below_min;train_n_too_small;oos_n_too_small |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_SHORT_W72_NO_HTF | SHORT | 42.000 | 31.429 | 64.408 | -13.456 | 131.555 | -214.239 | -28.225 | train_gt_0;worst_quarter_slip16_gt_minus10;boot_p10_gt_minus5 |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_LONG_W72_NO_HTF | LONG | 48.000 | 31.151 | 22.225 | 31.421 | 30.557 | -281.480 | -8.135 | worst_quarter_slip16_gt_minus10;boot_p10_gt_minus5 |
| stage41 | 41A_MTF_STRUCTURE_BREAK_RETEST | MTF_BREAK_RETEST_LONG_W240_TOL20 | LONG | 79.000 | 30.089 | 29.587 | 10.259 | 75.534 | -173.274 | 13.744 | worst_quarter_slip16_gt_minus10 |
| stage41 | 41A_MTF_STRUCTURE_BREAK_RETEST | MTF_BREAK_RETEST_LONG_W240_TOL35 | LONG | 79.000 | 30.089 | 29.587 | 10.259 | 75.534 | -173.274 | 13.744 | worst_quarter_slip16_gt_minus10 |
| stage41 | 41A_MTF_STRUCTURE_BREAK_RETEST | MTF_BREAK_RETEST_LONG_W240_TOL50 | LONG | 79.000 | 30.089 | 29.587 | 10.259 | 75.534 | -173.274 | 13.744 | worst_quarter_slip16_gt_minus10 |
| stage43 | 43E_ASIA_RANGE_REGIME_ACCEPT_REJECT | ASIA_REGIME_REJECT_LONG_TOL40 | LONG | 4.000 | 28.094 |  |  |  |  |  | event_clock_n_lt_120 |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_LONG_W168_HTF | LONG | 45.000 | 27.397 | 18.471 | 25.930 | 30.646 | -173.238 | -1.769 | worst_quarter_slip16_gt_minus10 |
| stage41 | 41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION | MULTIBAR_VOL_EXPAND_SHORT_W168_HTF | SHORT | 35.000 | 25.485 | 41.987 | 2.569 | 75.484 | -150.300 | -1.760 | event_clock_n_below_min |
| stage41 | 41C_SHOCK_COOLDOWN_CONTINUATION | SHOCK_COOLDOWN_CONT_LONG_M2.0 | LONG | 11.000 | 24.595 | 15.669 | -18.383 | 99.808 | -184.417 | -83.139 | event_clock_n_below_min;train_n_too_small;oos_n_too_small |


## Recommendation

```text
archive_stage44_meta_diagnostic = True
do_not_build_stage41b_42b_43b = True
do_not_promote_any_recent_candidate = True
next_stage = Stage45C_FEED_AND_TRANSACTION_COST_REALISM_AUDIT
```

### Rationale

- Only very-low-cost diagnostic assumptions create pass rows; current broker-cost environment likely overwhelms these edges.
- Even minimal-edge sanity gates find no robust observed-cost rows.
- Cost-stressed p90 is only 8.82 bps, below a practical robust edge gate.
- Median cost-stressed mean is negative (-7.38 bps).
- Worst-quarter median is deeply negative (-58.55 bps), showing path fragility.
- Bootstrap p10 median is below gate (-11.06 bps).

### Allowed next options

- `Stage45B external-context decision: DXY/yields/news calendar/CME GC reference before new candle-only scans`
- `Stage45C broker/feed/spread/slippage realism audit using MT5 spread column and optional futures/reference feed`
- `Stage45D rare-event sample-size decision only if event-scarcity scenarios show economically meaningful rows`
- `Stage46 new scan only after Stage45 selects an evidence-based direction`

### Not allowed

- `post_hoc_removal_of_weak_hours_months_years_quarters_contexts`
- `candidate_rescue_from_stage41_42_43`
- `EA_paper_live_live_from_archived_rows`
- `ML_before_robust_cost_aware_baseline`

## Anti-overfit note

Do not use this diagnostic to rescue Stage41/42/43 rows by post-hoc filtering. Stage45 can only select a direction: external context, feed/cost realism, rare-event sample-size, or a future genuinely new scan.
