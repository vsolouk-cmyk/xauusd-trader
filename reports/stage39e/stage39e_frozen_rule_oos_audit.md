# Stage39E_FROZEN_RULE_OUT_OF_SAMPLE_AUDIT

## Decision

```text
scope = RESEARCH_STAGE_ONLY_NO_PROMOTION
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

Stage39E freezes the surviving Stage39D condition rows and audits chronological held-out behavior. It is not a promotion gate.

## Input audit

```json
{
  "stage39d_summary": {
    "path": "reports/stage39d/stage39d_condition_robustness_summary.csv",
    "loaded_rows": 9,
    "survivor_rows": 8,
    "classification_counts": {
      "STRICT_CONDITION_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION": 5,
      "FORWARD_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION": 3,
      "FAIL_CONDITION_ROBUSTNESS_NO_PROMOTION": 1
    },
    "survivor_classifications": [
      "FORWARD_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION",
      "STRICT_CONDITION_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION"
    ]
  },
  "stage39c_events": {
    "path": "reports/stage39c/stage39c_condition_event_rows.csv",
    "loaded_rows_before_time_drop": 238,
    "loaded_rows": 238,
    "bad_time_rows_dropped": 0,
    "time_column": "entry_ts",
    "date_min": "2022-05-03T10:00:00+00:00",
    "date_max": "2026-06-11T01:00:00+00:00"
  },
  "stage39c_event_columns": [
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
    "trigger_severity_bucket",
    "_event_time"
  ]
}
```

## Classification counts

```json
{
  "STRICT_FROZEN_OOS_WATCH_ONLY_NO_PROMOTION": 5,
  "FAIL_FROZEN_OOS_NO_PROMOTION": 2,
  "FROZEN_OOS_WATCH_ONLY_NO_PROMOTION": 1
}
```

## Frozen-rule OOS summary

| classification                            | spec_type        | candidate                       | dimension               | bucket                    | dimension_a   | bucket_a     | dimension_b   | bucket_b   |   full_n |   full_cost_mean_bps |   oos_n |   oos_cost_mean_bps |   oos_hit_rate_pct |   ex2025_cost_mean_bps |   leave_one_year_out_min_cost_mean_bps |   q4_cost_mean_bps |   recent_third_cost_mean_bps |   full_median_mae_bps |   full_touch_stop_100bps_pct |   full_mean_after_cost_plus_slip_16bps |
|:------------------------------------------|:-----------------|:--------------------------------|:------------------------|:--------------------------|:--------------|:-------------|:--------------|:-----------|---------:|---------------------:|--------:|--------------------:|-------------------:|-----------------------:|---------------------------------------:|-------------------:|-----------------------------:|----------------------:|-----------------------------:|---------------------------------------:|
| STRICT_FROZEN_OOS_WATCH_ONLY_NO_PROMOTION | single_condition | RANGE_BOTTOM_REV_LONG_W48_Q0.05 | weekday                 | Monday                    |               | NA           |               | NA         |       38 |              75.9149 |      13 |            179.409  |            84.6154 |                65.8804 |                                44.9025 |           180.913  |                     179.409  |              -64.1315 |                      34.2105 |                                59.9149 |
| STRICT_FROZEN_OOS_WATCH_ONLY_NO_PROMOTION | single_condition | RANGE_BOTTOM_REV_LONG_W48_Q0.05 | prior_ret72_regime      | NEUTRAL_-75_75BPS         |               | NA           |               | NA         |       81 |              41.7499 |      27 |             86.0407 |            66.6667 |                17.5253 |                                17.5253 |           131.388  |                      86.0407 |              -65.825  |                      35.8025 |                                25.7499 |
| STRICT_FROZEN_OOS_WATCH_ONLY_NO_PROMOTION | single_condition | RANGE_BOTTOM_REV_LONG_W48_Q0.05 | trigger_severity_bucket | SEVERITY_MID              |               | NA           |               | NA         |       52 |              42.5038 |      18 |             78.4523 |            66.6667 |                36.0047 |                                36.0047 |            71.6928 |                      78.4523 |              -74.0646 |                      44.2308 |                                26.5038 |
| STRICT_FROZEN_OOS_WATCH_ONLY_NO_PROMOTION | single_condition | RANGE_BOTTOM_REV_LONG_W48_Q0.05 | prior_ret72_regime      | DOWN_MODERATE_-200_-75BPS |               | NA           |               | NA         |       50 |              42.0735 |      17 |             76.7036 |            82.3529 |                32.1575 |                                32.1575 |            72.7188 |                      76.7036 |              -88.3889 |                      40      |                                26.0735 |
| STRICT_FROZEN_OOS_WATCH_ONLY_NO_PROMOTION | single_condition | RANGE_BOTTOM_REV_LONG_W48_Q0.05 | spread_regime           | NA                        |               | NA           |               | NA         |      156 |              34.3198 |      52 |             74.1962 |            73.0769 |                16.9411 |                                16.9411 |            64.2375 |                      74.1962 |              -81.4042 |                      41.0256 |                                18.3198 |
| FROZEN_OOS_WATCH_ONLY_NO_PROMOTION        | single_condition | RANGE_BOTTOM_REV_LONG_W48_Q0.05 | trigger_severity_bucket | SEVERITY_LOW              |               | NA           |               | NA         |       52 |              40.4439 |      18 |            106.27   |            83.3333 |                17.2325 |                                17.2325 |           117.595  |                     106.27   |              -69.5785 |                      30.7692 |                                24.4439 |
| FAIL_FROZEN_OOS_NO_PROMOTION              | single_condition | RANGE_BOTTOM_REV_LONG_W48_Q0.05 | session_utc             | LONDON_07_12              |               | NA           |               | NA         |       31 |              60.9223 |      11 |             98.2726 |            54.5455 |                62.0975 |                                43.1976 |           181.642  |                      98.2726 |              -76.4212 |                      38.7097 |                                44.9223 |
| FAIL_FROZEN_OOS_NO_PROMOTION              | cross_condition  | RANGE_BOTTOM_REV_LONG_W48_Q0.05 |                         | NA                        | session_utc   | LONDON_07_12 | spread_regime | NA         |       31 |              60.9223 |      11 |             98.2726 |            54.5455 |                62.0975 |                                43.1976 |           181.642  |                      98.2726 |              -76.4212 |                      38.7097 |                                44.9223 |

## Split audit rows

|   spec_id | spec_label                                                                      | segment      |   n |   cost_mean_bps |   hit_rate_pct |   median_mae_bps |   touch_stop_100bps_pct |   mean_after_cost_plus_slip_16bps |
|----------:|:--------------------------------------------------------------------------------|:-------------|----:|----------------:|---------------:|-----------------:|------------------------:|----------------------------------:|
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
|         4 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: weekday=Monday                               | train        |  25 |        22.098   |        60      |         -62.7898 |                 36      |                           6.09797 |
|         4 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: weekday=Monday                               | oos          |  13 |       179.409   |        84.6154 |         -65.4732 |                 30.7692 |                         163.409   |
|         4 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: weekday=Monday                               | first_half   |  19 |        38.6536  |        63.1579 |         -61.5034 |                 31.5789 |                          22.6536  |
|         4 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: weekday=Monday                               | second_half  |  19 |       113.176   |        73.6842 |         -71.2575 |                 36.8421 |                          97.1763  |
|         4 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: weekday=Monday                               | q1           |   9 |        -5.30734 |        44.4444 |        -113.603  |                 55.5556 |                         -21.3073  |
|         4 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: weekday=Monday                               | q2           |  10 |        78.2184  |        80      |         -41.9487 |                 10      |                          62.2184  |
|         4 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: weekday=Monday                               | q3           |   9 |        37.9134  |        66.6667 |         -65.4732 |                 33.3333 |                          21.9134  |
|         4 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: weekday=Monday                               | q4           |  10 |       180.913   |        80      |         -75.3112 |                 40      |                         164.913   |
|         4 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: weekday=Monday                               | recent_third |  13 |       179.409   |        84.6154 |         -65.4732 |                 30.7692 |                         163.409   |
|         5 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: session_utc=LONDON_07_12                     | train        |  20 |        40.3796  |        65      |         -69.5468 |                 25      |                          24.3796  |
|         5 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: session_utc=LONDON_07_12                     | oos          |  11 |        98.2726  |        54.5455 |        -147.315  |                 63.6364 |                          82.2726  |
|         5 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: session_utc=LONDON_07_12                     | first_half   |  15 |        31.075   |        60      |         -73.2686 |                 20      |                          15.075   |
|         5 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: session_utc=LONDON_07_12                     | second_half  |  16 |        88.9042  |        62.5    |        -125.356  |                 56.25   |                          72.9042  |
|         5 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: session_utc=LONDON_07_12                     | q1           |   7 |        11.9359  |        42.8571 |         -86.1687 |                 28.5714 |                          -4.06412 |
|         5 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: session_utc=LONDON_07_12                     | q2           |   8 |        47.8217  |        75      |         -63.6642 |                 12.5    |                          31.8217  |
|         5 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: session_utc=LONDON_07_12                     | q3           |   8 |        -3.83409 |        62.5    |        -163.09   |                 62.5    |                         -19.8341  |
|         5 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: session_utc=LONDON_07_12                     | q4           |   8 |       181.642   |        62.5    |         -87.3272 |                 50      |                         165.642   |
|         5 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: session_utc=LONDON_07_12                     | recent_third |  11 |        98.2726  |        54.5455 |        -147.315  |                 63.6364 |                          82.2726  |
|         6 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: session_utc=LONDON_07_12 & spread_regime=NA  | train        |  20 |        40.3796  |        65      |         -69.5468 |                 25      |                          24.3796  |
|         6 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: session_utc=LONDON_07_12 & spread_regime=NA  | oos          |  11 |        98.2726  |        54.5455 |        -147.315  |                 63.6364 |                          82.2726  |
|         6 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: session_utc=LONDON_07_12 & spread_regime=NA  | first_half   |  15 |        31.075   |        60      |         -73.2686 |                 20      |                          15.075   |
|         6 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: session_utc=LONDON_07_12 & spread_regime=NA  | second_half  |  16 |        88.9042  |        62.5    |        -125.356  |                 56.25   |                          72.9042  |
|         6 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: session_utc=LONDON_07_12 & spread_regime=NA  | q1           |   7 |        11.9359  |        42.8571 |         -86.1687 |                 28.5714 |                          -4.06412 |
|         6 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: session_utc=LONDON_07_12 & spread_regime=NA  | q2           |   8 |        47.8217  |        75      |         -63.6642 |                 12.5    |                          31.8217  |
|         6 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: session_utc=LONDON_07_12 & spread_regime=NA  | q3           |   8 |        -3.83409 |        62.5    |        -163.09   |                 62.5    |                         -19.8341  |
|         6 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: session_utc=LONDON_07_12 & spread_regime=NA  | q4           |   8 |       181.642   |        62.5    |         -87.3272 |                 50      |                         165.642   |
|         6 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: session_utc=LONDON_07_12 & spread_regime=NA  | recent_third |  11 |        98.2726  |        54.5455 |        -147.315  |                 63.6364 |                          82.2726  |
|         7 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=NEUTRAL_-75_75BPS         | train        |  54 |        19.6045  |        59.2593 |         -72.3014 |                 37.037  |                           3.60446 |
|         7 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=NEUTRAL_-75_75BPS         | oos          |  27 |        86.0407  |        66.6667 |         -58.964  |                 33.3333 |                          70.0407  |
|         7 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=NEUTRAL_-75_75BPS         | first_half   |  40 |         1.45304 |        52.5    |         -77.9403 |                 42.5    |                         -14.547   |
|         7 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=NEUTRAL_-75_75BPS         | second_half  |  41 |        81.0639  |        70.7317 |         -54.8686 |                 29.2683 |                          65.0639  |
|         7 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=NEUTRAL_-75_75BPS         | q1           |  20 |        10.8872  |        50      |         -82.158  |                 45      |                          -5.11283 |
|         7 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=NEUTRAL_-75_75BPS         | q2           |  20 |        -7.98108 |        55      |         -77.9403 |                 40      |                         -23.9811  |
|         7 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=NEUTRAL_-75_75BPS         | q3           |  20 |        28.2233  |        65      |         -49.1879 |                 30      |                          12.2233  |
|         7 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=NEUTRAL_-75_75BPS         | q4           |  21 |       131.388   |        76.1905 |         -55.4683 |                 28.5714 |                         115.388   |
|         7 | RANGE_BOTTOM_REV_LONG_W48_Q0.05 :: prior_ret72_regime=NEUTRAL_-75_75BPS         | recent_third |  27 |        86.0407  |        66.6667 |         -58.964  |                 33.3333 |                          70.0407  |
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

- `STRICT_FROZEN_OOS_WATCH_ONLY_NO_PROMOTION` means the frozen row survived this research-only OOS audit, but it is still not tradable.
- `FROZEN_OOS_WATCH_ONLY_NO_PROMOTION` means it has partial held-out robustness but does not satisfy all strict risk and stress checks.
- `FAIL_FROZEN_OOS_NO_PROMOTION`, `INSUFFICIENT_EVENTS_NO_PROMOTION`, and `INSUFFICIENT_OOS_EVENTS_NO_PROMOTION` should not be extended with more filters.
- All rows remain `NO_GO` for EA, paper-live, and live.

## Next allowed step

Only if one or more rows are `STRICT_FROZEN_OOS_WATCH_ONLY_NO_PROMOTION`, the next step is a separate Stage39F rule-freeze package plus new-data observation protocol. That is still research-only and must not create trading alerts.

If no row is strict, archive Stage39A-E and do not continue filtering.