# Stage39F_RECENCY_BIAS_AND_RULE_STABILITY_AUDIT

## Decision

```text
scope = RESEARCH_STAGE_ONLY_NO_PROMOTION
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

Stage39F audits Stage39E frozen-rule survivors for recency bias, train/OOS asymmetry, quarter stability, slippage-16 survival, and adverse path risk. It is not a promotion gate.

## Input audit

```json
{
  "stage39e_summary_json": {
    "path": "reports/stage39e/stage39e_frozen_rule_oos_summary.json",
    "loaded_rows": 8,
    "survivor_rows": 6,
    "source_classification_counts": {
      "STRICT_FROZEN_OOS_WATCH_ONLY_NO_PROMOTION": 5,
      "FAIL_FROZEN_OOS_NO_PROMOTION": 2,
      "FROZEN_OOS_WATCH_ONLY_NO_PROMOTION": 1
    }
  },
  "stage39c_events": {
    "path": "reports/stage39c/stage39c_condition_event_rows.csv",
    "loaded": true,
    "rows_before_time_drop": 238,
    "columns": [
      "stage",
      "decision_scope",
      "promotion",
      "candidate",
      "family",
      "side",
      "horizon_hours",
      "horizon_bars",
      "lookback_hours",
      "trigger_type",
      "threshold",
      "event_source",
      "bar_index",
      "entry_ts",
      "exit_ts",
      "entry_close",
      "exit_close",
      "final_bps",
      "cost_stressed_final_bps",
      "mfe_bps",
      "mae_bps",
      "touch_target_50bps",
      "touch_target_100bps",
      "touch_target_150bps",
      "touch_stop_50bps",
      "touch_stop_100bps",
      "touch_stop_150bps",
      "trigger_severity",
      "hour_utc",
      "session_utc",
      "weekday",
      "year",
      "month",
      "spread",
      "spread_roll_median_24",
      "spread_roll_median_120",
      "spread_z240",
      "atr24_bps",
      "atr72_bps",
      "ret1_bps",
      "ret24_bps",
      "ret72_bps",
      "ret120_bps",
      "source_stage39b_residual_bps",
      "source_stage39b_event_clock_n",
      "source_stage39b_median_mae_bps",
      "source_stage39b_median_mfe_bps",
      "spread_regime",
      "prior_ret24_regime",
      "prior_ret72_regime",
      "atr24_bucket",
      "trigger_severity_bucket"
    ],
    "time_column": "entry_ts",
    "bad_time_rows_dropped": 0,
    "rows_after_time_drop": 238,
    "date_min": "2022-05-03T10:00:00+00:00",
    "date_max": "2026-06-11T01:00:00+00:00"
  }
}
```

## Classification counts

```json
{
  "RECENCY_BIASED_FROZEN_RULE_WATCH_ONLY_NO_PROMOTION": 6
}
```

## Frozen rule recency/stability summary

| classification                                     | spec_label                                                                      |   full_n |   train_n |   oos_n |   full_cost_mean_bps |   train_cost_mean_bps |   oos_cost_mean_bps |   worst_quarter_cost_mean_bps |   worst_quarter_slip16_mean_bps |   ex2025_cost_mean_bps |   leave_one_year_out_min_cost_mean_bps |   full_median_mae_bps |   oos_median_mae_bps |   full_touch_stop_100bps_pct |   oos_touch_stop_100bps_pct | recency_flags                                                                                                      | failed_hard_checks                                                                      |
|:---------------------------------------------------|:--------------------------------------------------------------------------------|---------:|----------:|--------:|---------------------:|----------------------:|--------------------:|------------------------------:|--------------------------------:|-----------------------:|---------------------------------------:|----------------------:|---------------------:|-----------------------------:|----------------------------:|:-------------------------------------------------------------------------------------------------------------------|:----------------------------------------------------------------------------------------|
| RECENCY_BIASED_FROZEN_RULE_WATCH_ONLY_NO_PROMOTION | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: weekday=Monday                               |       38 |        25 |      13 |              75.9149 |              22.098   |            179.409  |                      -5.30734 |                       -21.3073  |                65.8804 |                                44.9025 |              -64.1315 |             -65.4732 |                      34.2105 |                     30.7692 | oos_train_gap_high;oos_train_ratio_high;early_quarter_negative;early_quarter_slip16_negative                       | train_slip16_floor;worst_quarter_cost_floor;worst_quarter_slip16_floor                  |
| RECENCY_BIASED_FROZEN_RULE_WATCH_ONLY_NO_PROMOTION | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: trigger_severity_bucket=SEVERITY_LOW         |       52 |        34 |      18 |              40.4439 |               5.59479 |            106.27   |                     -27.7181  |                       -43.7181  |                17.2325 |                                17.2325 |              -69.5785 |             -55.9136 |                      30.7692 |                     22.2222 | oos_train_gap_high;oos_train_ratio_high;early_quarter_negative;early_quarter_slip16_negative                       | train_cost_floor;train_slip16_floor;worst_quarter_cost_floor;worst_quarter_slip16_floor |
| RECENCY_BIASED_FROZEN_RULE_WATCH_ONLY_NO_PROMOTION | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=NEUTRAL_-75_75BPS         |       81 |        54 |      27 |              41.7499 |              19.6045  |             86.0407 |                      -7.98108 |                       -23.9811  |                17.5253 |                                17.5253 |              -65.825  |             -58.964  |                      35.8025 |                     33.3333 | oos_train_gap_high;oos_train_ratio_high;q4_to_full_ratio_high;early_quarter_negative;early_quarter_slip16_negative | train_slip16_floor;worst_quarter_cost_floor;worst_quarter_slip16_floor                  |
| RECENCY_BIASED_FROZEN_RULE_WATCH_ONLY_NO_PROMOTION | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: trigger_severity_bucket=SEVERITY_MID         |       52 |        34 |      18 |              42.5038 |              23.4723  |             78.4523 |                      11.1215  |                        -4.8785  |                36.0047 |                                36.0047 |              -74.0646 |            -146.144  |                      44.2308 |                     55.5556 | oos_train_ratio_high;early_quarter_slip16_negative                                                                 | train_slip16_floor;worst_quarter_slip16_floor;oos_median_mae_cap;oos_stop100_cap        |
| RECENCY_BIASED_FROZEN_RULE_WATCH_ONLY_NO_PROMOTION | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=DOWN_MODERATE_-200_-75BPS |       50 |        33 |      17 |              42.0735 |              24.2337  |             76.7036 |                     -22.4254  |                       -38.4254  |                32.1575 |                                32.1575 |              -88.3889 |             -84.0533 |                      40      |                     41.1765 | oos_train_ratio_high;early_quarter_negative;early_quarter_slip16_negative                                          | train_slip16_floor;worst_quarter_cost_floor;worst_quarter_slip16_floor                  |
| RECENCY_BIASED_FROZEN_RULE_WATCH_ONLY_NO_PROMOTION | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: spread_regime=NA                             |      156 |       104 |      52 |              34.3198 |              14.3816  |             74.1962 |                       9.53311 |                        -6.46689 |                16.9411 |                                16.9411 |              -81.4042 |             -81.7091 |                      41.0256 |                     46.1538 | oos_train_ratio_high;early_quarter_slip16_negative                                                                 | train_cost_floor;train_slip16_floor;worst_quarter_slip16_floor                          |

## Split rows

|   spec_id | spec_label                                                                      | segment      |   n |   cost_mean_bps |   hit_rate_pct |   median_mae_bps |   touch_stop_100bps_pct |   mean_after_cost_plus_slip_16bps |
|----------:|:--------------------------------------------------------------------------------|:-------------|----:|----------------:|---------------:|-----------------:|------------------------:|----------------------------------:|
|         4 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: weekday=Monday                               | train        |  25 |        22.098   |        60      |         -62.7898 |                 36      |                           6.09797 |
|         4 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: weekday=Monday                               | oos          |  13 |       179.409   |        84.6154 |         -65.4732 |                 30.7692 |                         163.409   |
|         4 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: weekday=Monday                               | first_half   |  19 |        38.6536  |        63.1579 |         -61.5034 |                 31.5789 |                          22.6536  |
|         4 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: weekday=Monday                               | second_half  |  19 |       113.176   |        73.6842 |         -71.2575 |                 36.8421 |                          97.1763  |
|         4 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: weekday=Monday                               | q1           |   9 |        -5.30734 |        44.4444 |        -113.603  |                 55.5556 |                         -21.3073  |
|         4 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: weekday=Monday                               | q2           |  10 |        78.2184  |        80      |         -41.9487 |                 10      |                          62.2184  |
|         4 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: weekday=Monday                               | q3           |   9 |        37.9134  |        66.6667 |         -65.4732 |                 33.3333 |                          21.9134  |
|         4 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: weekday=Monday                               | q4           |  10 |       180.913   |        80      |         -75.3112 |                 40      |                         164.913   |
|         4 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: weekday=Monday                               | recent_third |  13 |       179.409   |        84.6154 |         -65.4732 |                 30.7692 |                         163.409   |
|         7 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=NEUTRAL_-75_75BPS         | train        |  54 |        19.6045  |        59.2593 |         -72.3014 |                 37.037  |                           3.60446 |
|         7 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=NEUTRAL_-75_75BPS         | oos          |  27 |        86.0407  |        66.6667 |         -58.964  |                 33.3333 |                          70.0407  |
|         7 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=NEUTRAL_-75_75BPS         | first_half   |  40 |         1.45304 |        52.5    |         -77.9403 |                 42.5    |                         -14.547   |
|         7 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=NEUTRAL_-75_75BPS         | second_half  |  41 |        81.0639  |        70.7317 |         -54.8686 |                 29.2683 |                          65.0639  |
|         7 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=NEUTRAL_-75_75BPS         | q1           |  20 |        10.8872  |        50      |         -82.158  |                 45      |                          -5.11283 |
|         7 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=NEUTRAL_-75_75BPS         | q2           |  20 |        -7.98108 |        55      |         -77.9403 |                 40      |                         -23.9811  |
|         7 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=NEUTRAL_-75_75BPS         | q3           |  20 |        28.2233  |        65      |         -49.1879 |                 30      |                          12.2233  |
|         7 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=NEUTRAL_-75_75BPS         | q4           |  21 |       131.388   |        76.1905 |         -55.4683 |                 28.5714 |                         115.388   |
|         7 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=NEUTRAL_-75_75BPS         | recent_third |  27 |        86.0407  |        66.6667 |         -58.964  |                 33.3333 |                          70.0407  |
|         1 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: trigger_severity_bucket=SEVERITY_MID         | train        |  34 |        23.4723  |        58.8235 |         -63.444  |                 38.2353 |                           7.47228 |
|         1 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: trigger_severity_bucket=SEVERITY_MID         | oos          |  18 |        78.4523  |        66.6667 |        -146.144  |                 55.5556 |                          62.4523  |
|         1 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: trigger_severity_bucket=SEVERITY_MID         | first_half   |  26 |        19.5624  |        61.5385 |         -74.0646 |                 38.4615 |                           3.56241 |
|         1 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: trigger_severity_bucket=SEVERITY_MID         | second_half  |  26 |        65.4452  |        61.5385 |         -88.7529 |                 50      |                          49.4452  |
|         1 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: trigger_severity_bucket=SEVERITY_MID         | q1           |  13 |        28.0033  |        61.5385 |         -86.1687 |                 38.4615 |                          12.0033  |
|         1 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: trigger_severity_bucket=SEVERITY_MID         | q2           |  13 |        11.1215  |        61.5385 |         -72.2735 |                 38.4615 |                          -4.8785  |
|         1 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: trigger_severity_bucket=SEVERITY_MID         | q3           |  13 |        59.1976  |        61.5385 |         -18.416  |                 30.7692 |                          43.1976  |
|         1 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: trigger_severity_bucket=SEVERITY_MID         | q4           |  13 |        71.6928  |        61.5385 |        -177.647  |                 69.2308 |                          55.6928  |
|         1 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: trigger_severity_bucket=SEVERITY_MID         | recent_third |  18 |        78.4523  |        66.6667 |        -146.144  |                 55.5556 |                          62.4523  |
|         2 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=DOWN_MODERATE_-200_-75BPS | train        |  33 |        24.2337  |        57.5758 |         -89.6299 |                 39.3939 |                           8.23369 |
|         2 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=DOWN_MODERATE_-200_-75BPS | oos          |  17 |        76.7036  |        82.3529 |         -84.0533 |                 41.1765 |                          60.7036  |
|         2 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=DOWN_MODERATE_-200_-75BPS | first_half   |  25 |        14.9886  |        52      |         -91.1998 |                 44      |                          -1.01136 |
|         2 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=DOWN_MODERATE_-200_-75BPS | second_half  |  25 |        69.1583  |        80      |         -82.7836 |                 36      |                          53.1583  |
|         2 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=DOWN_MODERATE_-200_-75BPS | q1           |  12 |       -22.4254  |        50      |        -121.114  |                 75      |                         -38.4254  |
|         2 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=DOWN_MODERATE_-200_-75BPS | q2           |  13 |        49.5247  |        53.8462 |         -73.1001 |                 15.3846 |                          33.5247  |
|         2 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=DOWN_MODERATE_-200_-75BPS | q3           |  12 |        65.3011  |        83.3333 |         -72.7867 |                 16.6667 |                          49.3011  |
|         2 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=DOWN_MODERATE_-200_-75BPS | q4           |  13 |        72.7188  |        76.9231 |        -112.932  |                 53.8462 |                          56.7188  |
|         2 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=DOWN_MODERATE_-200_-75BPS | recent_third |  17 |        76.7036  |        82.3529 |         -84.0533 |                 41.1765 |                          60.7036  |
|         3 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: spread_regime=NA                             | train        | 104 |        14.3816  |        56.7308 |         -81.4042 |                 38.4615 |                          -1.61842 |
|         3 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: spread_regime=NA                             | oos          |  52 |        74.1962  |        73.0769 |         -81.7091 |                 46.1538 |                          58.1962  |
|         3 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: spread_regime=NA                             | first_half   |  78 |        11.4445  |        56.4103 |         -83.0968 |                 38.4615 |                          -4.55555 |
|         3 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: spread_regime=NA                             | second_half  |  78 |        57.1951  |        67.9487 |         -81.0742 |                 43.5897 |                          41.1951  |
|         3 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: spread_regime=NA                             | q1           |  39 |         9.53311 |        51.2821 |         -95.2995 |                 46.1538 |                          -6.46689 |
|         3 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: spread_regime=NA                             | q2           |  39 |        13.3558  |        61.5385 |         -72.3294 |                 30.7692 |                          -2.6442  |
|         3 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: spread_regime=NA                             | q3           |  39 |        50.1527  |        69.2308 |         -61.4721 |                 33.3333 |                          34.1527  |
|         3 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: spread_regime=NA                             | q4           |  39 |        64.2375  |        66.6667 |        -112.932  |                 53.8462 |                          48.2375  |
|         3 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: spread_regime=NA                             | recent_third |  52 |        74.1962  |        73.0769 |         -81.7091 |                 46.1538 |                          58.1962  |
|         8 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: trigger_severity_bucket=SEVERITY_LOW         | train        |  34 |         5.59479 |        52.9412 |         -79.6024 |                 35.2941 |                         -10.4052  |
|         8 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: trigger_severity_bucket=SEVERITY_LOW         | oos          |  18 |       106.27    |        83.3333 |         -55.9136 |                 22.2222 |                          90.2699  |
|         8 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: trigger_severity_bucket=SEVERITY_LOW         | first_half   |  26 |        -3.92627 |        46.1538 |         -82.4805 |                 38.4615 |                         -19.9263  |
|         8 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: trigger_severity_bucket=SEVERITY_LOW         | second_half  |  26 |        84.814   |        80.7692 |         -58.2941 |                 23.0769 |                          68.814   |
|         8 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: trigger_severity_bucket=SEVERITY_LOW         | q1           |  13 |       -27.7181  |        30.7692 |         -88.5398 |                 46.1538 |                         -43.7181  |
|         8 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: trigger_severity_bucket=SEVERITY_LOW         | q2           |  13 |        19.8655  |        61.5385 |         -73.1001 |                 30.7692 |                           3.86553 |
|         8 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: trigger_severity_bucket=SEVERITY_LOW         | q3           |  13 |        52.0332  |        84.6154 |         -61.4721 |                 15.3846 |                          36.0332  |
|         8 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: trigger_severity_bucket=SEVERITY_LOW         | q4           |  13 |       117.595   |        76.9231 |         -56.3589 |                 30.7692 |                         101.595   |
|         8 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: trigger_severity_bucket=SEVERITY_LOW         | recent_third |  18 |       106.27    |        83.3333 |         -55.9136 |                 22.2222 |                          90.2699  |

## Interpretation

- `STRICT_STABLE_FROZEN_RULE_WATCH_ONLY_NO_PROMOTION` means the rule survived this stability audit, but it is still research-only.
- `RECENCY_BIASED_FROZEN_RULE_WATCH_ONLY_NO_PROMOTION` means the rule remains interesting but is dominated by recent/OOS behavior, weak early quarters, or weak train/slippage survival.
- `FAIL_RECENCY_STABILITY_NO_PROMOTION` means do not extend this row with more filters.
- All Stage39F rows remain `NO_GO` for EA, paper-live, and live.

## Next allowed step

No strict stable frozen rule survived this audit. The default decision is to archive Stage39A-F and not continue filter stacking. A future revisit is allowed only after materially more forward data exists.
