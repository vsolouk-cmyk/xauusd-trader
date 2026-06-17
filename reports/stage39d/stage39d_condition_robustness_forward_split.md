# Stage39D_CONDITION_ROBUSTNESS_AND_FORWARD_SPLIT_AUDIT

## Decision

```text
scope = RESEARCH_STAGE_ONLY_NO_PROMOTION
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

Stage39D audits Stage39C condition-watch buckets for forward robustness. It is not a promotion gate.

## Classification counts

```json
{
  "STRICT_CONDITION_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION": 5,
  "FORWARD_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION": 3,
  "FAIL_CONDITION_ROBUSTNESS_NO_PROMOTION": 1
}
```

## Audited condition rows

| classification                                      | spec_type        | candidate                       | dimension               | bucket                    | dimension_a   | bucket_a     | dimension_b   | bucket_b   |   n |   mean_final_bps |   cost_stressed_mean_bps |   hit_rate_pct |   median_mae_bps |   median_mfe_bps |   ex2025_cost_mean_bps |   leave_one_year_out_min_cost_mean_bps |   second_half_cost_mean_bps |   q4_cost_mean_bps |   recent_third_cost_mean_bps |   touch_stop_100bps_pct |   touch_target_100bps_pct |   mean_after_cost_plus_slip_16bps |
|:----------------------------------------------------|:-----------------|:--------------------------------|:------------------------|:--------------------------|:--------------|:-------------|:--------------|:-----------|----:|-----------------:|-------------------------:|---------------:|-----------------:|-----------------:|-----------------------:|---------------------------------------:|----------------------------:|-------------------:|-----------------------------:|------------------------:|--------------------------:|----------------------------------:|
| FAIL_CONDITION_ROBUSTNESS_NO_PROMOTION              | single_condition | RANGE_BOTTOM_REV_LONG_W48_Q0.05 | atr24_bucket            | ATR24_MID                 |               |              |               |            |  52 |          40.3243 |                  32.3243 |        65.3846 |         -70.7837 |          120.694 |                9.23883 |                                9.23883 |                     44.0096 |            76.0082 |                      44.6687 |                 38.4615 |                   61.5385 |                           16.3243 |
| FORWARD_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION          | single_condition | RANGE_BOTTOM_REV_LONG_W48_Q0.05 | trigger_severity_bucket | SEVERITY_MID              |               |              |               |            |  52 |          50.5038 |                  42.5038 |        63.4615 |         -74.0646 |          120.694 |               36.0047  |                               36.0047  |                     65.4452 |            71.6928 |                      78.4523 |                 44.2308 |                   61.5385 |                           26.5038 |
| FORWARD_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION          | single_condition | RANGE_BOTTOM_REV_LONG_W48_Q0.05 | prior_ret72_regime      | DOWN_MODERATE_-200_-75BPS |               |              |               |            |  50 |          50.0735 |                  42.0735 |        66      |         -88.3889 |          117.711 |               32.1575  |                               32.1575  |                     69.1583 |            72.7188 |                      76.7036 |                 40      |                   62      |                           26.0735 |
| FORWARD_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION          | single_condition | RANGE_BOTTOM_REV_LONG_W48_Q0.05 | spread_regime           | NA                        |               |              |               |            | 156 |          42.3198 |                  34.3198 |        62.8205 |         -81.4042 |          114.919 |               16.9411  |                               16.9411  |                     57.1951 |            64.2375 |                      74.1962 |                 41.0256 |                   57.6923 |                           18.3198 |
| STRICT_CONDITION_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION | single_condition | RANGE_BOTTOM_REV_LONG_W48_Q0.05 | weekday                 | Monday                    |               |              |               |            |  38 |          83.9149 |                  75.9149 |        68.4211 |         -64.1315 |          125.032 |               65.8804  |                               44.9025  |                    113.176  |           180.913  |                     179.409  |                 34.2105 |                   65.7895 |                           59.9149 |
| STRICT_CONDITION_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION | single_condition | RANGE_BOTTOM_REV_LONG_W48_Q0.05 | session_utc             | LONDON_07_12              |               |              |               |            |  31 |          68.9223 |                  60.9223 |        61.2903 |         -76.4212 |          133.401 |               62.0975  |                               43.1976  |                     88.9042 |           181.642  |                      98.2726 |                 38.7097 |                   58.0645 |                           44.9223 |
| STRICT_CONDITION_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION | cross_condition  | RANGE_BOTTOM_REV_LONG_W48_Q0.05 |                         |                           | session_utc   | LONDON_07_12 | spread_regime | NA         |  31 |          68.9223 |                  60.9223 |        61.2903 |         -76.4212 |          133.401 |               62.0975  |                               43.1976  |                     88.9042 |           181.642  |                      98.2726 |                 38.7097 |                   58.0645 |                           44.9223 |
| STRICT_CONDITION_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION | single_condition | RANGE_BOTTOM_REV_LONG_W48_Q0.05 | prior_ret72_regime      | NEUTRAL_-75_75BPS         |               |              |               |            |  81 |          49.7499 |                  41.7499 |        62.963  |         -65.825  |          110.845 |               17.5253  |                               17.5253  |                     81.0639 |           131.388  |                      86.0407 |                 35.8025 |                   54.321  |                           25.7499 |
| STRICT_CONDITION_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION | single_condition | RANGE_BOTTOM_REV_LONG_W48_Q0.05 | trigger_severity_bucket | SEVERITY_LOW              |               |              |               |            |  52 |          48.4439 |                  40.4439 |        63.4615 |         -69.5785 |          127.888 |               17.2325  |                               17.2325  |                     84.814  |           117.595  |                     106.27   |                 30.7692 |                   63.4615 |                           24.4439 |

## Forward split rows

| candidate                       | spec_type        | dimension               | bucket                    | dimension_a   | bucket_a     | dimension_b   | bucket_b   | segment      |   n |    mean_bps |   cost_mean_bps |   hit_rate_pct |
|:--------------------------------|:-----------------|:------------------------|:--------------------------|:--------------|:-------------|:--------------|:-----------|:-------------|----:|------------:|----------------:|---------------:|
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | atr24_bucket            | ATR24_MID                 |               |              |               |            | first_half   |  26 |  28.639     |        20.639   |        61.5385 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | atr24_bucket            | ATR24_MID                 |               |              |               |            | second_half  |  26 |  52.0096    |        44.0096  |        69.2308 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | atr24_bucket            | ATR24_MID                 |               |              |               |            | q1           |  13 |  28.0641    |        20.0641  |        61.5385 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | atr24_bucket            | ATR24_MID                 |               |              |               |            | q2           |  13 |  29.2138    |        21.2138  |        61.5385 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | atr24_bucket            | ATR24_MID                 |               |              |               |            | q3           |  13 |  20.0111    |        12.0111  |        61.5385 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | atr24_bucket            | ATR24_MID                 |               |              |               |            | q4           |  13 |  84.0082    |        76.0082  |        76.9231 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | atr24_bucket            | ATR24_MID                 |               |              |               |            | recent_third |  18 |  52.6687    |        44.6687  |        72.2222 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | prior_ret72_regime      | DOWN_MODERATE_-200_-75BPS |               |              |               |            | first_half   |  25 |  22.9886    |        14.9886  |        52      |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | prior_ret72_regime      | DOWN_MODERATE_-200_-75BPS |               |              |               |            | second_half  |  25 |  77.1583    |        69.1583  |        80      |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | prior_ret72_regime      | DOWN_MODERATE_-200_-75BPS |               |              |               |            | q1           |  12 | -14.4254    |       -22.4254  |        50      |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | prior_ret72_regime      | DOWN_MODERATE_-200_-75BPS |               |              |               |            | q2           |  13 |  57.5247    |        49.5247  |        53.8462 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | prior_ret72_regime      | DOWN_MODERATE_-200_-75BPS |               |              |               |            | q3           |  12 |  73.3011    |        65.3011  |        83.3333 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | prior_ret72_regime      | DOWN_MODERATE_-200_-75BPS |               |              |               |            | q4           |  13 |  80.7188    |        72.7188  |        76.9231 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | prior_ret72_regime      | DOWN_MODERATE_-200_-75BPS |               |              |               |            | recent_third |  17 |  84.7036    |        76.7036  |        82.3529 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | prior_ret72_regime      | NEUTRAL_-75_75BPS         |               |              |               |            | first_half   |  40 |   9.45304   |         1.45304 |        52.5    |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | prior_ret72_regime      | NEUTRAL_-75_75BPS         |               |              |               |            | second_half  |  41 |  89.0639    |        81.0639  |        73.1707 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | prior_ret72_regime      | NEUTRAL_-75_75BPS         |               |              |               |            | q1           |  20 |  18.8872    |        10.8872  |        50      |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | prior_ret72_regime      | NEUTRAL_-75_75BPS         |               |              |               |            | q2           |  20 |   0.0189162 |        -7.98108 |        55      |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | prior_ret72_regime      | NEUTRAL_-75_75BPS         |               |              |               |            | q3           |  20 |  36.2233    |        28.2233  |        65      |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | prior_ret72_regime      | NEUTRAL_-75_75BPS         |               |              |               |            | q4           |  21 | 139.388     |       131.388   |        80.9524 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | prior_ret72_regime      | NEUTRAL_-75_75BPS         |               |              |               |            | recent_third |  27 |  94.0407    |        86.0407  |        70.3704 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | session_utc             | LONDON_07_12              |               |              |               |            | first_half   |  15 |  39.075     |        31.075   |        60      |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | session_utc             | LONDON_07_12              |               |              |               |            | second_half  |  16 |  96.9042    |        88.9042  |        62.5    |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | session_utc             | LONDON_07_12              |               |              |               |            | q1           |   7 |  19.9359    |        11.9359  |        42.8571 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | session_utc             | LONDON_07_12              |               |              |               |            | q2           |   8 |  55.8217    |        47.8217  |        75      |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | session_utc             | LONDON_07_12              |               |              |               |            | q3           |   8 |   4.16591   |        -3.83409 |        62.5    |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | session_utc             | LONDON_07_12              |               |              |               |            | q4           |   8 | 189.642     |       181.642   |        62.5    |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | session_utc             | LONDON_07_12              |               |              |               |            | recent_third |  11 | 106.273     |        98.2726  |        54.5455 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | spread_regime           | NA                        |               |              |               |            | first_half   |  78 |  19.4445    |        11.4445  |        56.4103 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | spread_regime           | NA                        |               |              |               |            | second_half  |  78 |  65.1951    |        57.1951  |        69.2308 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | spread_regime           | NA                        |               |              |               |            | q1           |  39 |  17.5331    |         9.53311 |        51.2821 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | spread_regime           | NA                        |               |              |               |            | q2           |  39 |  21.3558    |        13.3558  |        61.5385 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | spread_regime           | NA                        |               |              |               |            | q3           |  39 |  58.1527    |        50.1527  |        69.2308 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | spread_regime           | NA                        |               |              |               |            | q4           |  39 |  72.2375    |        64.2375  |        69.2308 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | spread_regime           | NA                        |               |              |               |            | recent_third |  52 |  82.1962    |        74.1962  |        75      |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | trigger_severity_bucket | SEVERITY_MID              |               |              |               |            | first_half   |  26 |  27.5624    |        19.5624  |        61.5385 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | trigger_severity_bucket | SEVERITY_MID              |               |              |               |            | second_half  |  26 |  73.4452    |        65.4452  |        65.3846 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | trigger_severity_bucket | SEVERITY_MID              |               |              |               |            | q1           |  13 |  36.0033    |        28.0033  |        61.5385 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | trigger_severity_bucket | SEVERITY_MID              |               |              |               |            | q2           |  13 |  19.1215    |        11.1215  |        61.5385 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | trigger_severity_bucket | SEVERITY_MID              |               |              |               |            | q3           |  13 |  67.1976    |        59.1976  |        61.5385 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | trigger_severity_bucket | SEVERITY_MID              |               |              |               |            | q4           |  13 |  79.6928    |        71.6928  |        69.2308 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | trigger_severity_bucket | SEVERITY_MID              |               |              |               |            | recent_third |  18 |  86.4523    |        78.4523  |        72.2222 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | trigger_severity_bucket | SEVERITY_LOW              |               |              |               |            | first_half   |  26 |   4.07373   |        -3.92627 |        46.1538 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | trigger_severity_bucket | SEVERITY_LOW              |               |              |               |            | second_half  |  26 |  92.814     |        84.814   |        80.7692 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | trigger_severity_bucket | SEVERITY_LOW              |               |              |               |            | q1           |  13 | -19.7181    |       -27.7181  |        30.7692 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | trigger_severity_bucket | SEVERITY_LOW              |               |              |               |            | q2           |  13 |  27.8655    |        19.8655  |        61.5385 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | trigger_severity_bucket | SEVERITY_LOW              |               |              |               |            | q3           |  13 |  60.0332    |        52.0332  |        84.6154 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | trigger_severity_bucket | SEVERITY_LOW              |               |              |               |            | q4           |  13 | 125.595     |       117.595   |        76.9231 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | trigger_severity_bucket | SEVERITY_LOW              |               |              |               |            | recent_third |  18 | 114.27      |       106.27    |        83.3333 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | weekday                 | Monday                    |               |              |               |            | first_half   |  19 |  46.6536    |        38.6536  |        63.1579 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | weekday                 | Monday                    |               |              |               |            | second_half  |  19 | 121.176     |       113.176   |        73.6842 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | weekday                 | Monday                    |               |              |               |            | q1           |   9 |   2.69266   |        -5.30734 |        44.4444 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | weekday                 | Monday                    |               |              |               |            | q2           |  10 |  86.2184    |        78.2184  |        80      |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | weekday                 | Monday                    |               |              |               |            | q3           |   9 |  45.9134    |        37.9134  |        66.6667 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | weekday                 | Monday                    |               |              |               |            | q4           |  10 | 188.913     |       180.913   |        80      |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | single_condition | weekday                 | Monday                    |               |              |               |            | recent_third |  13 | 187.409     |       179.409   |        84.6154 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | cross_condition  |                         |                           | session_utc   | LONDON_07_12 | spread_regime | NA         | first_half   |  15 |  39.075     |        31.075   |        60      |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | cross_condition  |                         |                           | session_utc   | LONDON_07_12 | spread_regime | NA         | second_half  |  16 |  96.9042    |        88.9042  |        62.5    |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | cross_condition  |                         |                           | session_utc   | LONDON_07_12 | spread_regime | NA         | q1           |   7 |  19.9359    |        11.9359  |        42.8571 |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | cross_condition  |                         |                           | session_utc   | LONDON_07_12 | spread_regime | NA         | q2           |   8 |  55.8217    |        47.8217  |        75      |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | cross_condition  |                         |                           | session_utc   | LONDON_07_12 | spread_regime | NA         | q3           |   8 |   4.16591   |        -3.83409 |        62.5    |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | cross_condition  |                         |                           | session_utc   | LONDON_07_12 | spread_regime | NA         | q4           |   8 | 189.642     |       181.642   |        62.5    |
| RANGE_BOTTOM_REV_LONG_W48_Q0.05 | cross_condition  |                         |                           | session_utc   | LONDON_07_12 | spread_regime | NA         | recent_third |  11 | 106.273     |        98.2726  |        54.5455 |

## Interpretation

- `STRICT_CONDITION_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION` means the bucket survives this strict research audit only; it is still not tradable.
- `FORWARD_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION` means the bucket has some forward robustness but still needs a separate out-of-sample/frozen-rule audit.
- `WEAK_FORWARD_ROBUSTNESS_NO_PROMOTION`, `FAIL_CONDITION_ROBUSTNESS_NO_PROMOTION`, `YEAR_SPLIT_WEAK_NO_PROMOTION`, and `ADVERSE_PATH_RISK_TOO_HIGH_NO_PROMOTION` should not be extended with more filters.
- All Stage39D rows remain `NO_GO` for EA, paper-live, and live.

## Next allowed step

Only if one or more rows are `STRICT_CONDITION_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION` or `FORWARD_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION`, the next step is `Stage39E_FROZEN_RULE_OUT_OF_SAMPLE_AUDIT`.

If no row survives, archive Stage39A-D and do not continue filtering.
