# Stage40B_SURVIVOR_PATH_STABILITY_AUDIT

## Decision

```text
scope = RESEARCH_STAGE_ONLY_NO_PROMOTION
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

Stage40B is a dedicated research-only audit for strict Stage40 parallel-megascan survivors. It is not a promotion gate.

## Input audit

```json
{
  "stage40_summary_json": {
    "path": "reports/stage40/stage40_parallel_thesis_megascan_summary.json",
    "loaded": true,
    "classification_counts": {
      "FAIL_BENCHMARK_OR_STABILITY_RESEARCH_ONLY": 259,
      "INSUFFICIENT_EVENTS_RESEARCH_ONLY": 40,
      "SOFT_PARALLEL_THESIS_WATCH_ONLY_NO_PROMOTION": 4,
      "STRICT_PARALLEL_THESIS_WATCH_ONLY_NO_PROMOTION": 1
    },
    "strict_parallel_thesis_watch_count": 1,
    "soft_parallel_thesis_watch_count": 4
  },
  "stage40_summary_source": {
    "source": "summary_csv",
    "loaded_rows": 304,
    "strict_rows": 1,
    "classification_counts": {
      "FAIL_BENCHMARK_OR_STABILITY_RESEARCH_ONLY": 259,
      "INSUFFICIENT_EVENTS_RESEARCH_ONLY": 40,
      "SOFT_PARALLEL_THESIS_WATCH_ONLY_NO_PROMOTION": 4,
      "STRICT_PARALLEL_THESIS_WATCH_ONLY_NO_PROMOTION": 1
    }
  },
  "stage40_events": {
    "path": "reports/stage40/stage40_parallel_thesis_megascan_events.csv",
    "loaded": true,
    "rows": 48248,
    "columns": [
      "stage",
      "decision_scope",
      "promotion",
      "ea",
      "paper_live",
      "live",
      "family",
      "candidate",
      "side",
      "trigger",
      "horizon_hours",
      "params_json",
      "year",
      "month",
      "hour_utc",
      "weekday",
      "session_utc",
      "atr24_bps",
      "ret24_bps",
      "ret72_bps",
      "spread",
      "entry_idx",
      "exit_idx",
      "entry_ts",
      "exit_ts",
      "entry_close",
      "exit_close",
      "final_bps",
      "mfe_bps",
      "mae_bps",
      "touch_target_50bps",
      "touch_target_100bps",
      "touch_target_150bps",
      "touch_stop_50bps",
      "touch_stop_100bps",
      "touch_stop_150bps",
      "cost_stressed_final_bps",
      "candidate_classification"
    ],
    "event_time_meta": {
      "time_column": "entry_ts",
      "mode": "timestamp_column",
      "bad_time_rows_dropped": 0
    }
  }
}
```

## Classification counts

```json
{
  "FAIL_STAGE40B_SURVIVOR_AUDIT_NO_PROMOTION": 1
}
```

## Survivor audit summary

| classification                            | family                    | candidate                         | side   |   horizon_hours |   full_n |   full_cost_mean_bps |   train_cost_mean_bps |   oos_cost_mean_bps |   worst_quarter_cost_mean_bps |   worst_quarter_slip16_mean_bps |   boot_p10_bps |   boot_prob_mean_gt_0_pct |   full_median_mae_bps |   oos_median_mae_bps |   full_touch_stop_100bps_pct |   oos_touch_stop_100bps_pct | hard_fail_reasons          | audit_flags   |
|:------------------------------------------|:--------------------------|:----------------------------------|:-------|----------------:|---------:|---------------------:|----------------------:|--------------------:|------------------------------:|--------------------------------:|---------------:|--------------------------:|----------------------:|---------------------:|-----------------------------:|----------------------------:|:---------------------------|:--------------|
| FAIL_STAGE40B_SURVIVOR_AUDIT_NO_PROMOTION | VOL_COMPRESSION_EXPANSION | VOL_COMP_EXP_LONG_L120_Q0.15_M2.0 | LONG   |              72 |       88 |              45.2044 |               37.7798 |             59.5588 |                       3.88516 |                        -12.1148 |         23.463 |                      99.8 |              -84.2959 |             -105.395 |                      44.3182 |                     53.3333 | worst_quarter_slip16_floor |               |

## Split audit

|   spec_id | candidate                         | segment      |   n |   cost_mean_bps |   hit_rate_pct |   median_mae_bps |   touch_stop_100bps_pct |   mean_after_cost_plus_slip16_bps |
|----------:|:----------------------------------|:-------------|----:|----------------:|---------------:|-----------------:|------------------------:|----------------------------------:|
|         1 | VOL_COMP_EXP_LONG_L120_Q0.15_M2.0 | train        |  58 |        37.7798  |        60.3448 |         -78.4271 |                 39.6552 |                           21.7798 |
|         1 | VOL_COMP_EXP_LONG_L120_Q0.15_M2.0 | oos          |  30 |        59.5588  |        70      |        -105.395  |                 53.3333 |                           43.5588 |
|         1 | VOL_COMP_EXP_LONG_L120_Q0.15_M2.0 | first_half   |  44 |        37.0064  |        63.6364 |         -78.4271 |                 38.6364 |                           21.0064 |
|         1 | VOL_COMP_EXP_LONG_L120_Q0.15_M2.0 | second_half  |  44 |        53.4025  |        63.6364 |         -96.9463 |                 50      |                           37.4025 |
|         1 | VOL_COMP_EXP_LONG_L120_Q0.15_M2.0 | q1           |  22 |         3.88516 |        59.0909 |        -103.756  |                 54.5455 |                          -12.1148 |
|         1 | VOL_COMP_EXP_LONG_L120_Q0.15_M2.0 | q2           |  22 |        70.1276  |        68.1818 |         -57.9203 |                 22.7273 |                           54.1276 |
|         1 | VOL_COMP_EXP_LONG_L120_Q0.15_M2.0 | q3           |  22 |        62.871   |        63.6364 |         -98.6184 |                 50      |                           46.871  |
|         1 | VOL_COMP_EXP_LONG_L120_Q0.15_M2.0 | q4           |  22 |        43.9341  |        63.6364 |         -95.4187 |                 50      |                           27.9341 |
|         1 | VOL_COMP_EXP_LONG_L120_Q0.15_M2.0 | recent_third |  30 |        59.5588  |        70      |        -105.395  |                 53.3333 |                           43.5588 |

## Worst year/session buckets

|   spec_id | dimension   | bucket   |   n |   cost_mean_bps |   hit_rate_pct |   median_mae_bps |   touch_stop_100bps_pct |   mean_after_cost_plus_slip16_bps |
|----------:|:------------|:---------|----:|----------------:|---------------:|-----------------:|------------------------:|----------------------------------:|
|         1 | hour_utc    | 7        |   1 |      -342.964   |         0      |        -471.897  |                100      |                        -358.964   |
|         1 | hour_utc    | 4        |   5 |      -108.873   |        20      |        -163.714  |                100      |                        -124.873   |
|         1 | hour_utc    | 14       |   2 |       -44.3014  |        50      |        -134.56   |                 50      |                         -60.3014  |
|         1 | month       | 10       |   7 |       -27.9619  |        42.8571 |        -163.837  |                 85.7143 |                         -43.9619  |
|         1 | weekday     | Tuesday  |  20 |       -25.1917  |        45      |        -102.892  |                 55      |                         -41.1917  |
|         1 | month       | 5        |   8 |       -19.7     |        37.5    |        -110.787  |                 87.5    |                         -35.7     |
|         1 | year        | 2022     |  13 |       -15.403   |        46.1538 |        -112.103  |                 69.2308 |                         -31.403   |
|         1 | year        | 2026     |  10 |         4.13844 |        60      |        -162.457  |                 80      |                         -11.8616  |
|         1 | month       | 4        |   6 |        11.6702  |        66.6667 |        -194.277  |                 66.6667 |                          -4.32975 |
|         1 | month       | 8        |  13 |        18.4768  |        38.4615 |         -84.4344 |                 30.7692 |                           2.47679 |
|         1 | month       | 6        |   8 |        20.4164  |        50      |         -89.1739 |                 37.5    |                           4.41641 |
|         1 | month       | 12       |   9 |        23.4563  |        55.5556 |         -45.9435 |                 44.4444 |                           7.45634 |
|         1 | weekday     | Thursday |  15 |        31.1655  |        53.3333 |         -89.3379 |                 46.6667 |                          15.1655  |
|         1 | hour_utc    | 10       |   3 |        33.9494  |        66.6667 |        -112.103  |                100      |                          17.9494  |
|         1 | hour_utc    | 17       |  14 |        34.8035  |        71.4286 |         -59.2818 |                 21.4286 |                          18.8035  |
|         1 | hour_utc    | 16       |  21 |        36.0604  |        52.381  |         -90.1697 |                 47.619  |                          20.0604  |
|         1 | year        | 2023     |  22 |        36.9832  |        68.1818 |         -61.7525 |                 31.8182 |                          20.9832  |
|         1 | session_utc | NY_13_17 |  58 |        38.1901  |        62.069  |         -78.4271 |                 37.931  |                          22.1901  |
|         1 | month       | 3        |   7 |        40.9255  |        85.7143 |        -107.304  |                 57.1429 |                          24.9255  |
|         1 | hour_utc    | 23       |   4 |        43.4841  |        75      |        -111.063  |                 75      |                          27.4841  |

## Interpretation

- `STRICT_STAGE40B_SURVIVOR_WATCH_ONLY_NO_PROMOTION` means a survivor remains research-watch only and may proceed to a separate execution-feasibility audit.
- `RECENCY_OR_CONCENTRATION_WATCH_ONLY_NO_PROMOTION` means the row still has positive behavior but is too dominated by recent/OOS or concentrated wins.
- `FAIL_STAGE40B_SURVIVOR_AUDIT_NO_PROMOTION` means archive that survivor; do not add filters to rescue it.
- All rows remain `NO_GO` for EA, paper-live, and live.

## Next allowed step

Only if one or more rows are `STRICT_STAGE40B_SURVIVOR_WATCH_ONLY_NO_PROMOTION`, run a separate Stage40C execution-feasibility / lower-timeframe confirmation audit. Otherwise archive Stage40.