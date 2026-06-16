# Stage28C Forward-Safe Meta-Gate Validation

## Decision

```text
STAGE28C_HAS_FORWARD_SAFE_META_GATE_VALIDATION_CANDIDATE_REVIEW_ONLY
```

## Scope guardrails

- Research/shadow validation only.
- No EA change, no automatic trading, no paper/live/order authorization.
- Stage18A/Stage23D/Stage25D/Stage27D remain unchanged.
- Validates Stage28B Hotfix2 strict forward-safe meta-gates; it does not invent a new raw entry.
- Full-sample static thresholds are diagnostic only; expanding and yearly walk-forward validation are the main anti-selection checks.
- DB candle access is sanity-only via Stage25C loader; trade artifacts remain research artifacts, not market-data fallback.

## DB source of truth

- loader_mode: `reused:app.stage25c_deduped_filter_validation.load_bars_from_db`
- db_path: `data/local/xauusd_local_store.sqlite`
- db_first: `True`
- csv_fallback_enabled: `False`
- m1_rows: `1534217`
- h1_rows: `25608`

## Trade artifact

- selected_artifact: `data/reports/stage28b_ml_meta_feature_screen/stage28b_normalized_lineage_trades.csv`
- rows: `100`
- rows_after_event_dedup: `100`
- time_column_used: `entry_ts_norm`

## Base metrics

```json
{
  "events": 100,
  "pf_x1": 5.578964,
  "pf_x4": 2.851412,
  "pf_x6": 1.653422,
  "boot_pf_p05_x4": 1.818163,
  "median_x4": 1.02936,
  "total_x4": 127.61561,
  "win_rate_x4": 0.81,
  "years_positive_x4": 4,
  "year_count": 5
}
```

## Counts

- gate_defs_total: `16`
- gate_defs_available: `16`
- min_calib_events: `25`
- min_events: `25`
- validated_count: `16`
- watchlist_only_count: `0`

## Gate validation diagnostics

| decision                                 | gate_name                     | gate_kind   |   static_events |   static_pf_x4 |   static_pf_x6 |   static_total_x4 |   expanding_events |   expanding_pf_x4 |   expanding_pf_x6 |   expanding_boot_pf_p05_x4 |   expanding_total_x4 |   expanding_win_rate_x4 |   ywf_events |   ywf_pf_x4 |   ywf_pf_x6 |   ywf_total_x4 |   ywf_win_rate_x4 |   rank_score |
|:-----------------------------------------|:------------------------------|:------------|----------------:|---------------:|---------------:|------------------:|-------------------:|------------------:|------------------:|---------------------------:|---------------------:|------------------------:|-------------:|------------:|------------:|---------------:|------------------:|-------------:|
| STAGE28C_META_GATE_VALIDATED_REVIEW_ONLY | london_q60_prior_q25          | pairwise    |              32 |       28.0148  |       20.5394  |           140.456 |                 42 |          16.4192  |          11.3142  |                    5.77538 |              145.66  |                0.952381 |           46 |    31.0879  |    20.6437  |        156.434 |          0.978261 |      6.692   |
| STAGE28C_META_GATE_VALIDATED_REVIEW_ONLY | london_q60_prior_q30          | pairwise    |              32 |       28.0148  |       20.5394  |           140.456 |                 40 |          29.4398  |          19.9529  |                    8.41207 |              147.865 |                0.975    |           46 |    31.0879  |    20.6437  |        156.434 |          0.978261 |      6.69    |
| STAGE28C_META_GATE_VALIDATED_REVIEW_ONLY | london_q40_prior_q30          | pairwise    |              43 |       30.1214  |       20.353   |           151.409 |                 51 |           9.41335 |           6.17185 |                    4.37069 |              144.899 |                0.921569 |           53 |     9.59878 |     6.2568  |        148.092 |          0.924528 |      5.91177 |
| STAGE28C_META_GATE_VALIDATED_REVIEW_ONLY | london_q40_prior_q35          | pairwise    |              41 |       28.2015  |       19.0716  |           141.427 |                 48 |           8.72211 |           5.75789 |                    4.07788 |              132.994 |                0.916667 |           48 |     8.72211 |     5.75789 |        132.994 |          0.916667 |      5.50579 |
| STAGE28C_META_GATE_VALIDATED_REVIEW_ONLY | london_q40_prior_q40          | pairwise    |              39 |       27.2413  |       18.9787  |           136.435 |                 45 |           8.40954 |           5.70813 |                    4.07418 |              127.611 |                0.911111 |           46 |     8.44842 |     5.69963 |        128.28  |          0.913043 |      5.38021 |
| STAGE28C_META_GATE_VALIDATED_REVIEW_ONLY | london_range_q60              | single      |              40 |        9.59536 |        7.09865 |           143.482 |                 48 |           7.90191 |           5.59038 |                    3.74479 |              144.529 |                0.916667 |           51 |    10.2345  |     7.16355 |        154.152 |          0.941176 |      5.11022 |
| STAGE28C_META_GATE_VALIDATED_REVIEW_ONLY | london_range_q65              | single      |              35 |        8.96377 |        6.7267  |           132.939 |                 48 |           7.90191 |           5.59038 |                    3.74479 |              144.529 |                0.916667 |           50 |    10.1633  |     7.13813 |        152.963 |          0.94     |      5.11022 |
| STAGE28C_META_GATE_VALIDATED_REVIEW_ONLY | london_range_q70              | single      |              30 |       12.1921  |        9.41282 |           131.996 |                 42 |           7.61882 |           5.5714  |                    3.70079 |              138.601 |                0.904762 |           47 |     9.91251 |     7.02955 |        148.777 |          0.93617  |      4.9916  |
| STAGE28C_META_GATE_VALIDATED_REVIEW_ONLY | s28b_top_london_q40_prior_q25 | pairwise    |              44 |       30.3197  |       20.4059  |           152.441 |                 54 |           7.65701 |           4.96259 |                    3.47872 |              142.926 |                0.907407 |           54 |     9.61225 |     6.12113 |        148.324 |          0.925926 |      4.81635 |
| STAGE28C_META_GATE_VALIDATED_REVIEW_ONLY | london_q35_prior_q30          | pairwise    |              47 |       11.6211  |        7.95361 |           144.999 |                 53 |           7.32575 |           4.75214 |                    3.46831 |              139.991 |                0.886792 |           55 |     7.47005 |     4.81755 |        143.184 |          0.890909 |      4.64571 |
| STAGE28C_META_GATE_VALIDATED_REVIEW_ONLY | asia_q30_prior_q25            | pairwise    |              51 |        7.16773 |        4.81457 |           138.6   |                 54 |           7.30551 |           4.7999  |                    3.20493 |              142.973 |                0.888889 |           56 |     9.10124 |     5.74035 |        149.28  |          0.910714 |      4.59789 |
| STAGE28C_META_GATE_VALIDATED_REVIEW_ONLY | asia_q35_prior_q25            | pairwise    |              47 |        7.01615 |        4.83838 |           135.194 |                 54 |           7.30551 |           4.7999  |                    3.20493 |              142.973 |                0.888889 |           54 |     9.05194 |     5.86449 |        148.372 |          0.907407 |      4.59789 |
| STAGE28C_META_GATE_VALIDATED_REVIEW_ONLY | london_q40_asia_q30           | pairwise    |              49 |        8.10624 |        5.81715 |           148.808 |                 54 |           6.72873 |           4.68995 |                    3.16569 |              147.471 |                0.907407 |           56 |     7.00665 |     4.75391 |        149.27  |          0.910714 |      4.36068 |
| STAGE28C_META_GATE_VALIDATED_REVIEW_ONLY | london_q35_prior_q25          | pairwise    |              48 |       11.6967  |        7.97417 |           146.03  |                 56 |           6.23234 |           4.00931 |                    2.84395 |              138.018 |                0.875    |           56 |     7.48054 |     4.73671 |        143.416 |          0.892857 |      3.95244 |
| STAGE28C_META_GATE_VALIDATED_REVIEW_ONLY | london_q40_asia_q25           | pairwise    |              52 |        8.23096 |        5.79262 |           151.42  |                 57 |           5.92388 |           4.03289 |                    3.00394 |              144.728 |                0.894737 |           57 |     6.10915 |     4.13965 |        145.62  |          0.894737 |      3.88237 |
| STAGE28C_META_GATE_VALIDATED_REVIEW_ONLY | london_range_q40              | single      |              60 |        8.51255 |        5.65752 |           157.316 |                 61 |           5.33953 |           3.54537 |                    2.9455  |              143.047 |                0.885246 |           61 |     5.48793 |     3.62739 |        143.938 |          0.885246 |      3.54428 |

## Yearly walk-forward diagnostics

| gate_name                     |   year | status                                 |   train_events |   test_events |   kept_events |     pf_x4 |      pf_x6 |   total_x4 |   win_rate_x4 | thresholds                                                                  |
|:------------------------------|-------:|:---------------------------------------|---------------:|--------------:|--------------:|----------:|-----------:|-----------:|--------------:|:----------------------------------------------------------------------------|
| s28b_top_london_q40_prior_q25 |   2022 | skipped_insufficient_prior_calibration |              0 |            27 |             0 |   0       |   0        |    0       |      0        | {}                                                                          |
| s28b_top_london_q40_prior_q25 |   2023 | tested                                 |             27 |            25 |            15 |   4.26714 |   1.2135   |   11.6655  |      0.933333 | {"london_range": 9.032000000000016, "prior_day_range": 5.455000000000041}   |
| s28b_top_london_q40_prior_q25 |   2024 | tested                                 |             52 |            25 |            22 |   3.18693 |   1.54974  |   21.8716  |      0.909091 | {"london_range": 9.229999999999976, "prior_day_range": 10.134999999999932}  |
| s28b_top_london_q40_prior_q25 |   2025 | tested                                 |             77 |            19 |            13 |  16.4116  |  11.8405   |   56.2656  |      0.923077 | {"london_range": 10.66599999999994, "prior_day_range": 12.740000000000007}  |
| s28b_top_london_q40_prior_q25 |   2026 | tested                                 |             96 |             4 |             4 | inf       | inf        |   58.5216  |      1        | {"london_range": 11.519999999999982, "prior_day_range": 13.519999999999982} |
| london_q40_prior_q30          |   2022 | skipped_insufficient_prior_calibration |              0 |            27 |             0 |   0       |   0        |    0       |      0        | {}                                                                          |
| london_q40_prior_q30          |   2023 | tested                                 |             27 |            25 |            14 |   4.20217 |   1.32729  |   11.4335  |      0.928571 | {"london_range": 9.032000000000016, "prior_day_range": 9.387999999999918}   |
| london_q40_prior_q30          |   2024 | tested                                 |             52 |            25 |            22 |   3.18693 |   1.54974  |   21.8716  |      0.909091 | {"london_range": 9.229999999999976, "prior_day_range": 11.930999999999973}  |
| london_q40_prior_q30          |   2025 | tested                                 |             77 |            19 |            13 |  16.4116  |  11.8405   |   56.2656  |      0.923077 | {"london_range": 10.66599999999994, "prior_day_range": 15.193999999999823}  |
| london_q40_prior_q30          |   2026 | tested                                 |             96 |             4 |             4 | inf       | inf        |   58.5216  |      1        | {"london_range": 11.519999999999982, "prior_day_range": 15.579999999999927} |
| london_q40_prior_q35          |   2022 | skipped_insufficient_prior_calibration |              0 |            27 |             0 |   0       |   0        |    0       |      0        | {}                                                                          |
| london_q40_prior_q35          |   2023 | tested                                 |             27 |            25 |            11 |   2.71512 |   0.684208 |    6.12389 |      0.909091 | {"london_range": 9.032000000000016, "prior_day_range": 13.90699999999997}   |
| london_q40_prior_q35          |   2024 | tested                                 |             52 |            25 |            21 |   3.13931 |   1.57976  |   21.3954  |      0.904762 | {"london_range": 9.229999999999976, "prior_day_range": 14.103000000000065}  |
| london_q40_prior_q35          |   2025 | tested                                 |             77 |            19 |            13 |  16.4116  |  11.8405   |   56.2656  |      0.923077 | {"london_range": 10.66599999999994, "prior_day_range": 16.353999999999857}  |
| london_q40_prior_q35          |   2026 | tested                                 |             96 |             4 |             3 | inf       | inf        |   49.209   |      1        | {"london_range": 11.519999999999982, "prior_day_range": 17.83000000000004}  |
| london_q40_prior_q40          |   2022 | skipped_insufficient_prior_calibration |              0 |            27 |             0 |   0       |   0        |    0       |      0        | {}                                                                          |
| london_q40_prior_q40          |   2023 | tested                                 |             27 |            25 |            10 |   2.64402 |   0.751372 |    5.87003 |      0.9      | {"london_range": 9.032000000000016, "prior_day_range": 15.237999999999968}  |
| london_q40_prior_q40          |   2024 | tested                                 |             52 |            25 |            21 |   3.13931 |   1.57976  |   21.3954  |      0.904762 | {"london_range": 9.229999999999976, "prior_day_range": 15.345999999999869}  |
| london_q40_prior_q40          |   2025 | tested                                 |             77 |            19 |            12 |  15.19    |  10.9764   |   51.8057  |      0.916667 | {"london_range": 10.66599999999994, "prior_day_range": 19.786000000000012}  |
| london_q40_prior_q40          |   2026 | tested                                 |             96 |             4 |             3 | inf       | inf        |   49.209   |      1        | {"london_range": 11.519999999999982, "prior_day_range": 20.42000000000008}  |
| london_q35_prior_q25          |   2022 | skipped_insufficient_prior_calibration |              0 |            27 |             0 |   0       |   0        |    0       |      0        | {}                                                                          |
| london_q35_prior_q25          |   2023 | tested                                 |             27 |            25 |            15 |   4.26714 |   1.2135   |   11.6655  |      0.933333 | {"london_range": 8.288000000000011, "prior_day_range": 5.455000000000041}   |
| london_q35_prior_q25          |   2024 | tested                                 |             52 |            25 |            23 |   3.11359 |   1.43565  |   21.6361  |      0.869565 | {"london_range": 8.546000000000117, "prior_day_range": 10.134999999999932}  |
| london_q35_prior_q25          |   2025 | tested                                 |             77 |            19 |            14 |   7.19877 |   5.29833  |   51.5933  |      0.857143 | {"london_range": 9.986000000000011, "prior_day_range": 12.740000000000007}  |
| london_q35_prior_q25          |   2026 | tested                                 |             96 |             4 |             4 | inf       | inf        |   58.5216  |      1        | {"london_range": 10.754999999999995, "prior_day_range": 13.519999999999982} |
| london_q35_prior_q30          |   2022 | skipped_insufficient_prior_calibration |              0 |            27 |             0 |   0       |   0        |    0       |      0        | {}                                                                          |
| london_q35_prior_q30          |   2023 | tested                                 |             27 |            25 |            14 |   4.20217 |   1.32729  |   11.4335  |      0.928571 | {"london_range": 8.288000000000011, "prior_day_range": 9.387999999999918}   |
| london_q35_prior_q30          |   2024 | tested                                 |             52 |            25 |            23 |   3.11359 |   1.43565  |   21.6361  |      0.869565 | {"london_range": 8.546000000000117, "prior_day_range": 11.930999999999973}  |
| london_q35_prior_q30          |   2025 | tested                                 |             77 |            19 |            14 |   7.19877 |   5.29833  |   51.5933  |      0.857143 | {"london_range": 9.986000000000011, "prior_day_range": 15.193999999999823}  |
| london_q35_prior_q30          |   2026 | tested                                 |             96 |             4 |             4 | inf       | inf        |   58.5216  |      1        | {"london_range": 10.754999999999995, "prior_day_range": 15.579999999999927} |
| london_q60_prior_q25          |   2022 | skipped_insufficient_prior_calibration |              0 |            27 |             0 |   0       |   0        |    0       |      0        | {}                                                                          |
| london_q60_prior_q25          |   2023 | tested                                 |             27 |            25 |             9 | inf       |  94.0161   |   11.3229  |      1        | {"london_range": 11.525999999999977, "prior_day_range": 5.455000000000041}  |
| london_q60_prior_q25          |   2024 | tested                                 |             52 |            25 |            21 |   6.13025 |   2.90953  |   26.6735  |      0.952381 | {"london_range": 11.255999999999947, "prior_day_range": 10.134999999999932} |
| london_q60_prior_q25          |   2025 | tested                                 |             77 |            19 |            12 | inf       | inf        |   59.9164  |      1        | {"london_range": 12.944000000000141, "prior_day_range": 12.740000000000007} |
| london_q60_prior_q25          |   2026 | tested                                 |             96 |             4 |             4 | inf       | inf        |   58.5216  |      1        | {"london_range": 15.150000000000093, "prior_day_range": 13.519999999999982} |
| london_q60_prior_q30          |   2022 | skipped_insufficient_prior_calibration |              0 |            27 |             0 |   0       |   0        |    0       |      0        | {}                                                                          |
| london_q60_prior_q30          |   2023 | tested                                 |             27 |            25 |             9 | inf       |  94.0161   |   11.3229  |      1        | {"london_range": 11.525999999999977, "prior_day_range": 9.387999999999918}  |
| london_q60_prior_q30          |   2024 | tested                                 |             52 |            25 |            21 |   6.13025 |   2.90953  |   26.6735  |      0.952381 | {"london_range": 11.255999999999947, "prior_day_range": 11.930999999999973} |
| london_q60_prior_q30          |   2025 | tested                                 |             77 |            19 |            12 | inf       | inf        |   59.9164  |      1        | {"london_range": 12.944000000000141, "prior_day_range": 15.193999999999823} |
| london_q60_prior_q30          |   2026 | tested                                 |             96 |             4 |             4 | inf       | inf        |   58.5216  |      1        | {"london_range": 15.150000000000093, "prior_day_range": 15.579999999999927} |
| london_q40_asia_q25           |   2022 | skipped_insufficient_prior_calibration |              0 |            27 |             0 |   0       |   0        |    0       |      0        | {}                                                                          |
| london_q40_asia_q25           |   2023 | tested                                 |             27 |            25 |            14 |   4.46424 |   1.38057  |   11.6261  |      0.928571 | {"london_range": 9.032000000000016, "asia_range": 5.71000000000015}         |
| london_q40_asia_q25           |   2024 | tested                                 |             52 |            25 |            22 |   3.22593 |   1.59002  |   22.2616  |      0.909091 | {"london_range": 9.229999999999976, "asia_range": 5.947500000000048}        |
| london_q40_asia_q25           |   2025 | tested                                 |             77 |            19 |            17 |   4.51348 |   3.39555  |   53.2103  |      0.823529 | {"london_range": 10.66599999999994, "asia_range": 6.1400000000001}          |
| london_q40_asia_q25           |   2026 | tested                                 |             96 |             4 |             4 | inf       | inf        |   58.5216  |      1        | {"london_range": 11.519999999999982, "asia_range": 6.605000000000132}       |
| london_q40_asia_q30           |   2022 | skipped_insufficient_prior_calibration |              0 |            27 |             0 |   0       |   0        |    0       |      0        | {}                                                                          |
| london_q40_asia_q30           |   2023 | tested                                 |             27 |            25 |            14 |   4.46424 |   1.38057  |   11.6261  |      0.928571 | {"london_range": 9.032000000000016, "asia_range": 5.976000000000022}        |
| london_q40_asia_q30           |   2024 | tested                                 |             52 |            25 |            22 |   3.22593 |   1.59002  |   22.2616  |      0.909091 | {"london_range": 9.229999999999976, "asia_range": 6.112000000000125}        |
| london_q40_asia_q30           |   2025 | tested                                 |             77 |            19 |            16 |   5.94713 |   4.54134  |   56.8611  |      0.875    | {"london_range": 10.66599999999994, "asia_range": 6.606000000000131}        |
| london_q40_asia_q30           |   2026 | tested                                 |             96 |             4 |             4 | inf       | inf        |   58.5216  |      1        | {"london_range": 11.519999999999982, "asia_range": 7.115000000000009}       |
| asia_q30_prior_q25            |   2022 | skipped_insufficient_prior_calibration |              0 |            27 |             0 |   0       |   0        |    0       |      0        | {}                                                                          |
| asia_q30_prior_q25            |   2023 | tested                                 |             27 |            25 |            18 |   4.54734 |   1.11494  |   13.3149  |      0.888889 | {"asia_range": 5.976000000000022, "prior_day_range": 5.455000000000041}     |
| asia_q30_prior_q25            |   2024 | tested                                 |             52 |            25 |            20 |   3.02342 |   1.53625  |   20.2364  |      0.9      | {"asia_range": 6.112000000000125, "prior_day_range": 10.134999999999932}    |
| asia_q30_prior_q25            |   2025 | tested                                 |             77 |            19 |            14 |  13.244   |   9.82446  |   57.2076  |      0.928571 | {"asia_range": 6.606000000000131, "prior_day_range": 12.740000000000007}    |
| asia_q30_prior_q25            |   2026 | tested                                 |             96 |             4 |             4 | inf       | inf        |   58.5216  |      1        | {"asia_range": 7.115000000000009, "prior_day_range": 13.519999999999982}    |
| asia_q35_prior_q25            |   2022 | skipped_insufficient_prior_calibration |              0 |            27 |             0 |   0       |   0        |    0       |      0        | {}                                                                          |
| asia_q35_prior_q25            |   2023 | tested                                 |             27 |            25 |            16 |   4.30532 |   1.21061  |   12.4065  |      0.875    | {"asia_range": 6.148000000000115, "prior_day_range": 5.455000000000041}     |
| asia_q35_prior_q25            |   2024 | tested                                 |             52 |            25 |            20 |   3.02342 |   1.53625  |   20.2364  |      0.9      | {"asia_range": 6.528999999999905, "prior_day_range": 10.134999999999932}    |
| asia_q35_prior_q25            |   2025 | tested                                 |             77 |            19 |            14 |  13.244   |   9.82446  |   57.2076  |      0.928571 | {"asia_range": 7.05600000000004, "prior_day_range": 12.740000000000007}     |
| asia_q35_prior_q25            |   2026 | tested                                 |             96 |             4 |             4 | inf       | inf        |   58.5216  |      1        | {"asia_range": 7.780000000000086, "prior_day_range": 13.519999999999982}    |
| london_range_q40              |   2022 | skipped_insufficient_prior_calibration |              0 |            27 |             0 |   0       |   0        |    0       |      0        | {}                                                                          |
| london_range_q40              |   2023 | tested                                 |             27 |            25 |            16 |   2.19964 |   0.696209 |    8.30943 |      0.875    | {"london_range": 9.032000000000016}                                         |
| london_range_q40              |   2024 | tested                                 |             52 |            25 |            24 |   3.38944 |   1.60286  |   23.8969  |      0.916667 | {"london_range": 9.229999999999976}                                         |
| london_range_q40              |   2025 | tested                                 |             77 |            19 |            17 |   4.51348 |   3.39555  |   53.2103  |      0.823529 | {"london_range": 10.66599999999994}                                         |
| london_range_q40              |   2026 | tested                                 |             96 |             4 |             4 | inf       | inf        |   58.5216  |      1        | {"london_range": 11.519999999999982}                                        |
| london_range_q60              |   2022 | skipped_insufficient_prior_calibration |              0 |            27 |             0 |   0       |   0        |    0       |      0        | {}                                                                          |
| london_range_q60              |   2023 | tested                                 |             27 |            25 |             9 | inf       |  94.0161   |   11.3229  |      1        | {"london_range": 11.525999999999977}                                        |
| london_range_q60              |   2024 | tested                                 |             52 |            25 |            22 |   6.2789  |   2.92115  |   27.4463  |      0.954545 | {"london_range": 11.255999999999947}                                        |
| london_range_q60              |   2025 | tested                                 |             77 |            19 |            16 |   5.94713 |   4.54134  |   56.8611  |      0.875    | {"london_range": 12.944000000000141}                                        |
| london_range_q60              |   2026 | tested                                 |             96 |             4 |             4 | inf       | inf        |   58.5216  |      1        | {"london_range": 15.150000000000093}                                        |
| london_range_q65              |   2022 | skipped_insufficient_prior_calibration |              0 |            27 |             0 |   0       |   0        |    0       |      0        | {}                                                                          |
| london_range_q65              |   2023 | tested                                 |             27 |            25 |             9 | inf       |  94.0161   |   11.3229  |      1        | {"london_range": 11.727999999999998}                                        |
| london_range_q65              |   2024 | tested                                 |             52 |            25 |            21 |   6.0503  |   2.84323  |   26.2578  |      0.952381 | {"london_range": 11.76049999999999}                                         |
| london_range_q65              |   2025 | tested                                 |             77 |            19 |            16 |   5.94713 |   4.54134  |   56.8611  |      0.875    | {"london_range": 14.074000000000023}                                        |
| london_range_q65              |   2026 | tested                                 |             96 |             4 |             4 | inf       | inf        |   58.5216  |      1        | {"london_range": 16.514999999999986}                                        |
| london_range_q70              |   2022 | skipped_insufficient_prior_calibration |              0 |            27 |             0 |   0       |   0        |    0       |      0        | {}                                                                          |
| london_range_q70              |   2023 | tested                                 |             27 |            25 |             9 | inf       |  94.0161   |   11.3229  |      1        | {"london_range": 11.819999999999936}                                        |
| london_range_q70              |   2024 | tested                                 |             52 |            25 |            18 |   5.24504 |   2.51044  |   22.071   |      0.944444 | {"london_range": 12.337999999999939}                                        |
| london_range_q70              |   2025 | tested                                 |             77 |            19 |            16 |   5.94713 |   4.54134  |   56.8611  |      0.875    | {"london_range": 15.133999999999924}                                        |
| london_range_q70              |   2026 | tested                                 |             96 |             4 |             4 | inf       | inf        |   58.5216  |      1        | {"london_range": 17.24000000000001}                                         |

## Leave-one-year-out diagnostics

| gate_name                     |   holdout_year | status   |   holdout_events |   kept_events |      pf_x4 |      pf_x6 |   total_x4 |   win_rate_x4 | thresholds                                                                  |
|:------------------------------|---------------:|:---------|-----------------:|--------------:|-----------:|-----------:|-----------:|--------------:|:----------------------------------------------------------------------------|
| s28b_top_london_q40_prior_q25 |           2022 | tested   |               27 |             2 | inf        |   4.27881  |    1.94943 |      1        | {"london_range": 13.072000000000207, "prior_day_range": 15.759999999999993} |
| s28b_top_london_q40_prior_q25 |           2023 | tested   |               25 |             6 | inf        |  34.5794   |    6.01329 |      1        | {"london_range": 12.249999999999908, "prior_day_range": 15.579999999999927} |
| s28b_top_london_q40_prior_q25 |           2024 | tested   |               25 |            22 |   3.18693  |   1.54974  |   21.8716  |      0.909091 | {"london_range": 10.629999999999791, "prior_day_range": 11.705000000000041} |
| s28b_top_london_q40_prior_q25 |           2025 | tested   |               19 |            13 |  16.4116   |  11.8405   |   56.2656  |      0.923077 | {"london_range": 10.8599999999999, "prior_day_range": 13.779999999999973}   |
| s28b_top_london_q40_prior_q25 |           2026 | tested   |                4 |             4 | inf        | inf        |   58.5216  |      1        | {"london_range": 11.519999999999982, "prior_day_range": 13.519999999999982} |
| london_q40_prior_q30          |           2022 | tested   |               27 |             2 | inf        |   4.27881  |    1.94943 |      1        | {"london_range": 13.072000000000207, "prior_day_range": 17.474000000000068} |
| london_q40_prior_q30          |           2023 | tested   |               25 |             5 | inf        |  79.2232   |    5.34372 |      1        | {"london_range": 12.249999999999908, "prior_day_range": 18.498}             |
| london_q40_prior_q30          |           2024 | tested   |               25 |            21 |   3.13931  |   1.57976  |   21.3954  |      0.904762 | {"london_range": 10.629999999999791, "prior_day_range": 14.338000000000056} |
| london_q40_prior_q30          |           2025 | tested   |               19 |            13 |  16.4116   |  11.8405   |   56.2656  |      0.923077 | {"london_range": 10.8599999999999, "prior_day_range": 15.519999999999982}   |
| london_q40_prior_q30          |           2026 | tested   |                4 |             4 | inf        | inf        |   58.5216  |      1        | {"london_range": 11.519999999999982, "prior_day_range": 15.579999999999927} |
| london_q40_prior_q35          |           2022 | tested   |               27 |             1 | inf        | inf        |    1.417   |      1        | {"london_range": 13.072000000000207, "prior_day_range": 20.974000000000025} |
| london_q40_prior_q35          |           2023 | tested   |               25 |             5 | inf        |  79.2232   |    5.34372 |      1        | {"london_range": 12.249999999999908, "prior_day_range": 20.40500000000007}  |
| london_q40_prior_q35          |           2024 | tested   |               25 |            21 |   3.13931  |   1.57976  |   21.3954  |      0.904762 | {"london_range": 10.629999999999791, "prior_day_range": 15.735999999999992} |
| london_q40_prior_q35          |           2025 | tested   |               19 |            13 |  16.4116   |  11.8405   |   56.2656  |      0.923077 | {"london_range": 10.8599999999999, "prior_day_range": 16.889999999999418}   |
| london_q40_prior_q35          |           2026 | tested   |                4 |             3 | inf        | inf        |   49.209   |      1        | {"london_range": 11.519999999999982, "prior_day_range": 17.83000000000004}  |
| london_q40_prior_q40          |           2022 | tested   |               27 |             1 | inf        | inf        |    1.417   |      1        | {"london_range": 13.072000000000207, "prior_day_range": 22.66799999999994}  |
| london_q40_prior_q40          |           2023 | tested   |               25 |             4 | inf        |  71.1498   |    4.45343 |      1        | {"london_range": 12.249999999999908, "prior_day_range": 21.78400000000001}  |
| london_q40_prior_q40          |           2024 | tested   |               25 |            20 |   3.02046  |   1.53746  |   20.2068  |      0.9      | {"london_range": 10.629999999999791, "prior_day_range": 18.02600000000002}  |
| london_q40_prior_q40          |           2025 | tested   |               19 |            12 |  15.19     |  10.9764   |   51.8057  |      0.916667 | {"london_range": 10.8599999999999, "prior_day_range": 20.23000000000001}    |
| london_q40_prior_q40          |           2026 | tested   |                4 |             3 | inf        | inf        |   49.209   |      1        | {"london_range": 11.519999999999982, "prior_day_range": 20.42000000000008}  |
| london_q35_prior_q25          |           2022 | tested   |               27 |             2 | inf        |   4.27881  |    1.94943 |      1        | {"london_range": 12.149999999999906, "prior_day_range": 15.759999999999993} |
| london_q35_prior_q25          |           2023 | tested   |               25 |             6 | inf        |  34.5794   |    6.01329 |      1        | {"london_range": 11.819999999999936, "prior_day_range": 15.579999999999927} |
| london_q35_prior_q25          |           2024 | tested   |               25 |            22 |   3.18693  |   1.54974  |   21.8716  |      0.909091 | {"london_range": 9.989000000000008, "prior_day_range": 11.705000000000041}  |
| london_q35_prior_q25          |           2025 | tested   |               19 |            14 |   7.19877  |   5.29833  |   51.5933  |      0.857143 | {"london_range": 10.160000000000082, "prior_day_range": 13.779999999999973} |
| london_q35_prior_q25          |           2026 | tested   |                4 |             4 | inf        | inf        |   58.5216  |      1        | {"london_range": 10.754999999999995, "prior_day_range": 13.519999999999982} |
| london_q35_prior_q30          |           2022 | tested   |               27 |             2 | inf        |   4.27881  |    1.94943 |      1        | {"london_range": 12.149999999999906, "prior_day_range": 17.474000000000068} |
| london_q35_prior_q30          |           2023 | tested   |               25 |             5 | inf        |  79.2232   |    5.34372 |      1        | {"london_range": 11.819999999999936, "prior_day_range": 18.498}             |
| london_q35_prior_q30          |           2024 | tested   |               25 |            21 |   3.13931  |   1.57976  |   21.3954  |      0.904762 | {"london_range": 9.989000000000008, "prior_day_range": 14.338000000000056}  |
| london_q35_prior_q30          |           2025 | tested   |               19 |            14 |   7.19877  |   5.29833  |   51.5933  |      0.857143 | {"london_range": 10.160000000000082, "prior_day_range": 15.519999999999982} |
| london_q35_prior_q30          |           2026 | tested   |                4 |             4 | inf        | inf        |   58.5216  |      1        | {"london_range": 10.754999999999995, "prior_day_range": 15.579999999999927} |
| london_q60_prior_q25          |           2022 | tested   |               27 |             1 | inf        | inf        |    1.417   |      1        | {"london_range": 17.77199999999984, "prior_day_range": 15.759999999999993}  |
| london_q60_prior_q25          |           2023 | tested   |               25 |             1 | inf        | inf        |    1.62443 |      1        | {"london_range": 17.203999999999997, "prior_day_range": 15.579999999999927} |
| london_q60_prior_q25          |           2024 | tested   |               25 |            14 |   4.64996  |   2.51888  |   18.977   |      0.928571 | {"london_range": 14.926000000000068, "prior_day_range": 11.705000000000041} |
| london_q60_prior_q25          |           2025 | tested   |               19 |            12 | inf        | inf        |   59.9164  |      1        | {"london_range": 13.889999999999873, "prior_day_range": 13.779999999999973} |
| london_q60_prior_q25          |           2026 | tested   |                4 |             4 | inf        | inf        |   58.5216  |      1        | {"london_range": 15.150000000000093, "prior_day_range": 13.519999999999982} |
| london_q60_prior_q30          |           2022 | tested   |               27 |             1 | inf        | inf        |    1.417   |      1        | {"london_range": 17.77199999999984, "prior_day_range": 17.474000000000068}  |
| london_q60_prior_q30          |           2023 | tested   |               25 |             1 | inf        | inf        |    1.62443 |      1        | {"london_range": 17.203999999999997, "prior_day_range": 18.498}             |
| london_q60_prior_q30          |           2024 | tested   |               25 |            14 |   4.64996  |   2.51888  |   18.977   |      0.928571 | {"london_range": 14.926000000000068, "prior_day_range": 14.338000000000056} |
| london_q60_prior_q30          |           2025 | tested   |               19 |            12 | inf        | inf        |   59.9164  |      1        | {"london_range": 13.889999999999873, "prior_day_range": 15.519999999999982} |
| london_q60_prior_q30          |           2026 | tested   |                4 |             4 | inf        | inf        |   58.5216  |      1        | {"london_range": 15.150000000000093, "prior_day_range": 15.579999999999927} |
| london_q40_asia_q25           |           2022 | tested   |               27 |             5 |   1.07957  |   0.360878 |    0.33797 |      0.8      | {"london_range": 13.072000000000207, "asia_range": 7.730000000000018}       |
| london_q40_asia_q25           |           2023 | tested   |               25 |             7 | inf        | 155.43     |    9.5993  |      1        | {"london_range": 12.249999999999908, "asia_range": 7.115000000000009}       |
| london_q40_asia_q25           |           2024 | tested   |               25 |            21 |   3.1007   |   1.54252  |   21.0092  |      0.904762 | {"london_range": 10.629999999999791, "asia_range": 6.464999999999918}       |
| london_q40_asia_q25           |           2025 | tested   |               19 |            17 |   4.51348  |   3.39555  |   53.2103  |      0.823529 | {"london_range": 10.8599999999999, "asia_range": 6.239999999999782}         |
| london_q40_asia_q25           |           2026 | tested   |                4 |             4 | inf        | inf        |   58.5216  |      1        | {"london_range": 11.519999999999982, "asia_range": 6.605000000000132}       |
| london_q40_asia_q30           |           2022 | tested   |               27 |             4 |   0.897915 |   0.346412 |   -0.4336  |      0.75     | {"london_range": 13.072000000000207, "asia_range": 8.734000000000014}       |
| london_q40_asia_q30           |           2023 | tested   |               25 |             6 | inf        | 140.599    |    8.44801 |      1        | {"london_range": 12.249999999999908, "asia_range": 7.770000000000072}       |
| london_q40_asia_q30           |           2024 | tested   |               25 |            21 |   3.1007   |   1.54252  |   21.0092  |      0.904762 | {"london_range": 10.629999999999791, "asia_range": 6.876000000000112}       |
| london_q40_asia_q30           |           2025 | tested   |               19 |            16 |   5.94713  |   4.54134  |   56.8611  |      0.875    | {"london_range": 10.8599999999999, "asia_range": 6.830000000000155}         |
| london_q40_asia_q30           |           2026 | tested   |                4 |             4 | inf        | inf        |   58.5216  |      1        | {"london_range": 11.519999999999982, "asia_range": 7.115000000000009}       |
| asia_q30_prior_q25            |           2022 | tested   |               27 |             2 |   0.346684 |   0.149772 |   -2.67029 |      0.5      | {"asia_range": 8.734000000000014, "prior_day_range": 15.759999999999993}    |
| asia_q30_prior_q25            |           2023 | tested   |               25 |            10 |   2.54033  |   0.724685 |    5.7165  |      0.9      | {"asia_range": 7.770000000000072, "prior_day_range": 15.579999999999927}    |
| asia_q30_prior_q25            |           2024 | tested   |               25 |            20 |   3.02342  |   1.53625  |   20.2364  |      0.9      | {"asia_range": 6.876000000000112, "prior_day_range": 11.705000000000041}    |
| asia_q30_prior_q25            |           2025 | tested   |               19 |            14 |  13.244    |   9.82446  |   57.2076  |      0.928571 | {"asia_range": 6.830000000000155, "prior_day_range": 13.779999999999973}    |
| asia_q30_prior_q25            |           2026 | tested   |                4 |             4 | inf        | inf        |   58.5216  |      1        | {"asia_range": 7.115000000000009, "prior_day_range": 13.519999999999982}    |
| asia_q35_prior_q25            |           2022 | tested   |               27 |             2 |   0.346684 |   0.149772 |   -2.67029 |      0.5      | {"asia_range": 9.23800000000001, "prior_day_range": 15.759999999999993}     |
| asia_q35_prior_q25            |           2023 | tested   |               25 |            10 |   2.54033  |   0.724685 |    5.7165  |      0.9      | {"asia_range": 8.390000000000077, "prior_day_range": 15.579999999999927}    |
| asia_q35_prior_q25            |           2024 | tested   |               25 |            17 |   2.76227  |   1.50211  |   17.6246  |      0.882353 | {"asia_range": 7.376999999999907, "prior_day_range": 11.705000000000041}    |
| asia_q35_prior_q25            |           2025 | tested   |               19 |            14 |  13.244    |   9.82446  |   57.2076  |      0.928571 | {"asia_range": 7.170000000000073, "prior_day_range": 13.779999999999973}    |
| asia_q35_prior_q25            |           2026 | tested   |                4 |             4 | inf        | inf        |   58.5216  |      1        | {"asia_range": 7.780000000000086, "prior_day_range": 13.519999999999982}    |
| london_range_q40              |           2022 | tested   |               27 |             7 |   1.33017  |   0.337956 |    1.4024  |      0.857143 | {"london_range": 13.072000000000207}                                        |
| london_range_q40              |           2023 | tested   |               25 |             9 | inf        |  94.0161   |   11.3229  |      1        | {"london_range": 12.249999999999908}                                        |
| london_range_q40              |           2024 | tested   |               25 |            23 |   3.26421  |   1.55593  |   22.6445  |      0.913043 | {"london_range": 10.629999999999791}                                        |
| london_range_q40              |           2025 | tested   |               19 |            17 |   4.51348  |   3.39555  |   53.2103  |      0.823529 | {"london_range": 10.8599999999999}                                          |
| london_range_q40              |           2026 | tested   |                4 |             4 | inf        | inf        |   58.5216  |      1        | {"london_range": 11.519999999999982}                                        |
| london_range_q60              |           2022 | tested   |               27 |             1 | inf        | inf        |    1.417   |      1        | {"london_range": 17.77199999999984}                                         |
| london_range_q60              |           2023 | tested   |               25 |             3 | inf        | inf        |    4.81801 |      1        | {"london_range": 17.203999999999997}                                        |
| london_range_q60              |           2024 | tested   |               25 |            14 |   4.64996  |   2.51888  |   18.977   |      0.928571 | {"london_range": 14.926000000000068}                                        |
| london_range_q60              |           2025 | tested   |               19 |            16 |   5.94713  |   4.54134  |   56.8611  |      0.875    | {"london_range": 13.889999999999873}                                        |
| london_range_q60              |           2026 | tested   |                4 |             4 | inf        | inf        |   58.5216  |      1        | {"london_range": 15.150000000000093}                                        |
| london_range_q65              |           2022 | tested   |               27 |             1 | inf        | inf        |    1.417   |      1        | {"london_range": 19.49800000000005}                                         |
| london_range_q65              |           2023 | tested   |               25 |             3 | inf        | inf        |    4.81801 |      1        | {"london_range": 19.161999999999903}                                        |
| london_range_q65              |           2024 | tested   |               25 |            14 |   4.64996  |   2.51888  |   18.977   |      0.928571 | {"london_range": 16.069999999999983}                                        |
| london_range_q65              |           2025 | tested   |               19 |            16 |   5.94713  |   4.54134  |   56.8611  |      0.875    | {"london_range": 14.790000000000193}                                        |
| london_range_q65              |           2026 | tested   |                4 |             4 | inf        | inf        |   58.5216  |      1        | {"london_range": 16.514999999999986}                                        |
| london_range_q70              |           2022 | tested   |               27 |             0 |   0        |   0        |    0       |      0        | {"london_range": 20.744000000000145}                                        |
| london_range_q70              |           2023 | tested   |               25 |             2 | inf        | inf        |    2.77572 |      1        | {"london_range": 20.029999999999927}                                        |
| london_range_q70              |           2024 | tested   |               25 |            10 |   3.03085  |   1.58903  |   10.5589  |      0.9      | {"london_range": 17.26200000000008}                                         |
| london_range_q70              |           2025 | tested   |               19 |            16 |   5.94713  |   4.54134  |   56.8611  |      0.875    | {"london_range": 16.019999999999982}                                        |
| london_range_q70              |           2026 | tested   |                4 |             4 | inf        | inf        |   58.5216  |      1        | {"london_range": 17.24000000000001}                                         |

## Gate split diagnostics

| gate_name                     | mode                          | split      |   bucket |   events |      pf_x4 |       pf_x6 |   total_x4 |   win_rate_x4 |
|:------------------------------|:------------------------------|:-----------|---------:|---------:|-----------:|------------:|-----------:|--------------:|
| s28b_top_london_q40_prior_q25 | static_full_sample_diagnostic | year       |     2022 |        3 | inf        |    6.25583  |    2.98072 |      1        |
| s28b_top_london_q40_prior_q25 | static_full_sample_diagnostic | year       |     2023 |        6 | inf        |   34.5794   |    6.01329 |      1        |
| s28b_top_london_q40_prior_q25 | static_full_sample_diagnostic | year       |     2024 |       19 |   5.81004  |    2.93637  |   25.0086  |      0.947368 |
| s28b_top_london_q40_prior_q25 | static_full_sample_diagnostic | year       |     2025 |       12 | inf        |  inf        |   59.9164  |      1        |
| s28b_top_london_q40_prior_q25 | static_full_sample_diagnostic | year       |     2026 |        4 | inf        |  inf        |   58.5216  |      1        |
| s28b_top_london_q40_prior_q25 | static_full_sample_diagnostic | entry_hour |       13 |       44 |  30.3197   |   20.4059   |  152.441   |      0.977273 |
| s28b_top_london_q40_prior_q25 | static_full_sample_diagnostic | dow        |        0 |        3 | inf        |  inf        |   17.4051  |      1        |
| s28b_top_london_q40_prior_q25 | static_full_sample_diagnostic | dow        |        1 |        8 | inf        |  inf        |   53.4774  |      1        |
| s28b_top_london_q40_prior_q25 | static_full_sample_diagnostic | dow        |        2 |        9 | inf        |  102.735    |   23.8269  |      1        |
| s28b_top_london_q40_prior_q25 | static_full_sample_diagnostic | dow        |        3 |       12 |   3.31256  |    1.59443  |   12.0236  |      0.916667 |
| s28b_top_london_q40_prior_q25 | static_full_sample_diagnostic | dow        |        4 |       12 | inf        |  inf        |   45.7076  |      1        |
| s28b_top_london_q40_prior_q25 | static_full_sample_diagnostic | month      |        1 |        2 | inf        |   73.7028   |    1.74243 |      1        |
| s28b_top_london_q40_prior_q25 | static_full_sample_diagnostic | month      |        2 |        2 | inf        |  inf        |    4.73814 |      1        |
| s28b_top_london_q40_prior_q25 | static_full_sample_diagnostic | month      |        3 |        7 | inf        | 1495.06     |   50.3642  |      1        |
| s28b_top_london_q40_prior_q25 | static_full_sample_diagnostic | month      |        4 |        4 | inf        |  329.402    |   10.5404  |      1        |
| s28b_top_london_q40_prior_q25 | static_full_sample_diagnostic | month      |        5 |        5 | inf        |  inf        |   24.2686  |      1        |
| s28b_top_london_q40_prior_q25 | static_full_sample_diagnostic | month      |        6 |        5 | inf        |   50.2387   |   10.5268  |      1        |
| s28b_top_london_q40_prior_q25 | static_full_sample_diagnostic | month      |        7 |        3 | inf        |  inf        |    6.99    |      1        |
| s28b_top_london_q40_prior_q25 | static_full_sample_diagnostic | month      |        8 |        3 | inf        |  inf        |    5.58429 |      1        |
| s28b_top_london_q40_prior_q25 | static_full_sample_diagnostic | month      |        9 |        4 | inf        |   29.8366   |    7.63215 |      1        |
| s28b_top_london_q40_prior_q25 | static_full_sample_diagnostic | month      |       10 |        5 | inf        |  inf        |   18.3624  |      1        |
| s28b_top_london_q40_prior_q25 | static_full_sample_diagnostic | month      |       11 |        3 |   2.22722  |    1.72562  |    6.38061 |      0.666667 |
| s28b_top_london_q40_prior_q25 | static_full_sample_diagnostic | month      |       12 |        1 | inf        |  inf        |    5.31057 |      1        |
| s28b_top_london_q40_prior_q25 | expanding_event_oos           | year       |     2022 |        1 |   0        |    0        |   -4.24746 |      0        |
| s28b_top_london_q40_prior_q25 | expanding_event_oos           | year       |     2023 |       14 |   3.9447   |    1.13083  |   10.5142  |      0.928571 |
| s28b_top_london_q40_prior_q25 | expanding_event_oos           | year       |     2024 |       22 |   3.18693  |    1.54974  |   21.8716  |      0.909091 |
| s28b_top_london_q40_prior_q25 | expanding_event_oos           | year       |     2025 |       13 |  16.4116   |   11.8405   |   56.2656  |      0.923077 |
| s28b_top_london_q40_prior_q25 | expanding_event_oos           | year       |     2026 |        4 | inf        |  inf        |   58.5216  |      1        |
| s28b_top_london_q40_prior_q25 | expanding_event_oos           | entry_hour |       13 |       54 |   7.65701  |    4.96259  |  142.926   |      0.907407 |
| s28b_top_london_q40_prior_q25 | expanding_event_oos           | dow        |        0 |        6 |   5.07678  |    3.65105  |   17.316   |      0.833333 |
| s28b_top_london_q40_prior_q25 | expanding_event_oos           | dow        |        1 |       12 | inf        |   54.3353   |   55.8759  |      1        |
| s28b_top_london_q40_prior_q25 | expanding_event_oos           | dow        |        2 |        7 | inf        | 3687.44     |   22.2631  |      1        |
| s28b_top_london_q40_prior_q25 | expanding_event_oos           | dow        |        3 |       13 |   2.01974  |    0.984847 |    8.94292 |      0.846154 |
| s28b_top_london_q40_prior_q25 | expanding_event_oos           | dow        |        4 |       16 |   5.55804  |    3.64785  |   38.5276  |      0.875    |
| s28b_top_london_q40_prior_q25 | expanding_event_oos           | month      |        1 |        4 |   0.607725 |    0.075807 |   -1.43214 |      0.75     |
| s28b_top_london_q40_prior_q25 | expanding_event_oos           | month      |        2 |        2 | inf        |  inf        |    4.73814 |      1        |
| s28b_top_london_q40_prior_q25 | expanding_event_oos           | month      |        3 |       10 | inf        |   96.3901   |   54.5453  |      1        |
| s28b_top_london_q40_prior_q25 | expanding_event_oos           | month      |        4 |        5 | inf        |  389.478    |   12.6564  |      1        |
| s28b_top_london_q40_prior_q25 | expanding_event_oos           | month      |        5 |        5 | inf        |  inf        |   24.2686  |      1        |
| s28b_top_london_q40_prior_q25 | expanding_event_oos           | month      |        6 |        6 | inf        |   53.6622   |   11.7154  |      1        |
| s28b_top_london_q40_prior_q25 | expanding_event_oos           | month      |        7 |        2 | inf        |  inf        |    5.573   |      1        |
| s28b_top_london_q40_prior_q25 | expanding_event_oos           | month      |        8 |        4 | inf        |    7.80986  |    5.83815 |      1        |
| s28b_top_london_q40_prior_q25 | expanding_event_oos           | month      |        9 |        3 | inf        |  inf        |    7.09972 |      1        |
| s28b_top_london_q40_prior_q25 | expanding_event_oos           | month      |       10 |        6 |   3.70919  |    2.53947  |   13.009   |      0.833333 |
| s28b_top_london_q40_prior_q25 | expanding_event_oos           | month      |       11 |        5 |   0.889578 |    0.673394 |   -1.43739 |      0.4      |
| s28b_top_london_q40_prior_q25 | expanding_event_oos           | month      |       12 |        2 | inf        |  inf        |    6.35128 |      1        |
| london_q40_prior_q30          | static_full_sample_diagnostic | year       |     2022 |        2 | inf        |    4.27881  |    1.94943 |      1        |
| london_q40_prior_q30          | static_full_sample_diagnostic | year       |     2023 |        6 | inf        |   34.5794   |    6.01329 |      1        |
| london_q40_prior_q30          | static_full_sample_diagnostic | year       |     2024 |       19 |   5.81004  |    2.93637  |   25.0086  |      0.947368 |
| london_q40_prior_q30          | static_full_sample_diagnostic | year       |     2025 |       12 | inf        |  inf        |   59.9164  |      1        |
| london_q40_prior_q30          | static_full_sample_diagnostic | year       |     2026 |        4 | inf        |  inf        |   58.5216  |      1        |
| london_q40_prior_q30          | static_full_sample_diagnostic | entry_hour |       13 |       43 |  30.1214   |   20.353    |  151.409   |      0.976744 |
| london_q40_prior_q30          | static_full_sample_diagnostic | dow        |        0 |        3 | inf        |  inf        |   17.4051  |      1        |
| london_q40_prior_q30          | static_full_sample_diagnostic | dow        |        1 |        8 | inf        |  inf        |   53.4774  |      1        |
| london_q40_prior_q30          | static_full_sample_diagnostic | dow        |        2 |        8 | inf        |  100.812    |   22.7956  |      1        |
| london_q40_prior_q30          | static_full_sample_diagnostic | dow        |        3 |       12 |   3.31256  |    1.59443  |   12.0236  |      0.916667 |
| london_q40_prior_q30          | static_full_sample_diagnostic | dow        |        4 |       12 | inf        |  inf        |   45.7076  |      1        |
| london_q40_prior_q30          | static_full_sample_diagnostic | month      |        1 |        2 | inf        |   73.7028   |    1.74243 |      1        |
| london_q40_prior_q30          | static_full_sample_diagnostic | month      |        2 |        2 | inf        |  inf        |    4.73814 |      1        |
| london_q40_prior_q30          | static_full_sample_diagnostic | month      |        3 |        7 | inf        | 1495.06     |   50.3642  |      1        |
| london_q40_prior_q30          | static_full_sample_diagnostic | month      |        4 |        4 | inf        |  329.402    |   10.5404  |      1        |
| london_q40_prior_q30          | static_full_sample_diagnostic | month      |        5 |        5 | inf        |  inf        |   24.2686  |      1        |
| london_q40_prior_q30          | static_full_sample_diagnostic | month      |        6 |        5 | inf        |   50.2387   |   10.5268  |      1        |
| london_q40_prior_q30          | static_full_sample_diagnostic | month      |        7 |        3 | inf        |  inf        |    6.99    |      1        |
| london_q40_prior_q30          | static_full_sample_diagnostic | month      |        8 |        3 | inf        |  inf        |    5.58429 |      1        |
| london_q40_prior_q30          | static_full_sample_diagnostic | month      |        9 |        4 | inf        |   29.8366   |    7.63215 |      1        |
| london_q40_prior_q30          | static_full_sample_diagnostic | month      |       10 |        4 | inf        |  inf        |   17.3312  |      1        |
| london_q40_prior_q30          | static_full_sample_diagnostic | month      |       11 |        3 |   2.22722  |    1.72562  |    6.38061 |      0.666667 |
| london_q40_prior_q30          | static_full_sample_diagnostic | month      |       12 |        1 | inf        |  inf        |    5.31057 |      1        |
| london_q40_prior_q30          | expanding_event_oos           | year       |     2023 |       12 |   3.30774  |    0.96792  |    8.23989 |      0.916667 |
| london_q40_prior_q30          | expanding_event_oos           | year       |     2024 |       22 |   3.18693  |    1.54974  |   21.8716  |      0.909091 |
| london_q40_prior_q30          | expanding_event_oos           | year       |     2025 |       13 |  16.4116   |   11.8405   |   56.2656  |      0.923077 |
| london_q40_prior_q30          | expanding_event_oos           | year       |     2026 |        4 | inf        |  inf        |   58.5216  |      1        |
| london_q40_prior_q30          | expanding_event_oos           | entry_hour |       13 |       51 |   9.41335  |    6.17185  |  144.899   |      0.921569 |
| london_q40_prior_q30          | expanding_event_oos           | dow        |        0 |        4 | inf        |  inf        |   19.5211  |      1        |
| london_q40_prior_q30          | expanding_event_oos           | dow        |        1 |       12 | inf        |   54.3353   |   55.8759  |      1        |
| london_q40_prior_q30          | expanding_event_oos           | dow        |        2 |        7 | inf        | 3687.44     |   22.2631  |      1        |
| london_q40_prior_q30          | expanding_event_oos           | dow        |        3 |       13 |   2.01974  |    0.984847 |    8.94292 |      0.846154 |
| london_q40_prior_q30          | expanding_event_oos           | dow        |        4 |       15 |   5.53059  |    3.82112  |   38.2956  |      0.866667 |
| london_q40_prior_q30          | expanding_event_oos           | month      |        1 |        4 |   0.607725 |    0.075807 |   -1.43214 |      0.75     |

## Interpretation

- Stage28C is stricter than Stage28B: global quantile thresholds are no longer enough for validation.
- A validated result here is still review-only; it requires a separate forward-shadow tracker before operational consideration.
- If expanding validation survives but yearly walk-forward weakens, keep the gate as research watchlist only.
- If no meta-gate survives, the next useful step is exogenous/macro/news feature integration rather than more OHLC-only gate mining.

## Operational reminder

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.run_active_shadow_suite
python3 -m app.stage28b_ml_meta_feature_screen
python3 -m app.stage28c_forward_safe_meta_gate_validation
```

## Output files

- `data/reports/stage28c_forward_safe_meta_gate_validation/stage28c_forward_safe_meta_gate_validation.md`
- `data/reports/stage28c_forward_safe_meta_gate_validation/stage28c_forward_safe_meta_gate_validation.json`
- `data/reports/stage28c_forward_safe_meta_gate_validation/stage28c_gate_validation.csv`
- `data/reports/stage28c_forward_safe_meta_gate_validation/stage28c_yearly_walk_forward.csv`
- `data/reports/stage28c_forward_safe_meta_gate_validation/stage28c_leave_one_year_out.csv`
- `data/reports/stage28c_forward_safe_meta_gate_validation/stage28c_gate_splits.csv`
- `data/reports/stage28c_forward_safe_meta_gate_validation/stage28c_db_schema_diagnostic.json`
