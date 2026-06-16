# Stage26D Artifact Mirror / Anti-Signal Diagnostic

Generated UTC: `2026-06-11T21:13:43.865063+00:00`

## Decision

```text
STAGE26D_NO_MIRROR_EDGE_KEEP_DISCOVERY_OPEN
```

## Scope guardrails

- Research/shadow diagnostic only.
- Stage18A v2 remains the active operational forward-shadow runner.
- Stage23D and Stage25D remain separate DB-first trackers.
- No EA change, no automatic trading, no paper/live/order authorization.
- Market candles are DB-first from SQLite; AMarkets CSV market fallback is disabled.
- Previous exact-trade CSV outputs are used only as research artifacts, not as market-data fallback.
- Hotfix 3 no longer requires a literal `timestamp` column and makes metrics duplicate-column-safe.
- Mirrored results are anti-signal diagnostics only and require a later DB-first exact replay before any forward-shadow tracker.

## DB source of truth

- db_path: `data/local/xauusd_local_store.sqlite`
- candle_table: `bars`
- db_first: `True`
- csv_fallback_enabled: `False`
- m1_rows: `0` | span: `unavailable`
- h1_rows: `0` | span: `unavailable`
- h1_mode: `not_found_or_derived_elsewhere`

## Counts

- input_files_configured: `3`
- input_files_loaded: `3`
- source_trade_rows: `4545`
- mirror_candidate_groups: `19`
- mirror_family_groups: `6`
- mirror_promotion_review_candidates: `0`
- mirror_watchlist_only_candidates: `0`

## Input artifact manifest

| source_stage   | path                                                                                   | exists   |   rows |   loaded_rows | status   | time_column_used   | net_column_mode                                                                                                                                               | columns                                                                                                                                                     |
|:---------------|:---------------------------------------------------------------------------------------|:---------|-------:|--------------:|:---------|:-------------------|:--------------------------------------------------------------------------------------------------------------------------------------------------------------|:------------------------------------------------------------------------------------------------------------------------------------------------------------|
| stage26a       | data/reports/stage26a_db_first_structured_behavior_discovery/stage26a_exact_trades.csv | True     |    604 |           604 | loaded   | entry_time         | original:net;mirror:gross_reversal;cols:{"net_x1": "net_x1", "net_x4": "net_x4", "net_x6": "net_x6", "gross_x1": "gross", "gross_x4": null, "gross_x6": null} | candidate,family,entry_time,direction,dir_mult,entry_price,atr,horizon_min,tp_atr,sl_atr,reason,exit_time,exit_price,exit_reason,gross,net_x1,net_x4,net_x6 |
| stage26b       | data/reports/stage26b_db_first_family_coverage_discovery/stage26b_exact_trades.csv     | True     |   2983 |          2983 | loaded   | entry_time         | original:net;mirror:gross_reversal;cols:{"net_x1": "net_x1", "net_x4": "net_x4", "net_x6": "net_x6", "gross_x1": "gross", "gross_x4": null, "gross_x6": null} | entry_time,entry_price,direction,atr,candidate,family,horizon_min,tp_atr,sl_atr,date,exit_time,exit_price,exit_reason,gross,net_x0,net_x1,net_x4,net_x6     |
| stage26c       | data/reports/stage26c_db_first_failure_reversal_discovery/stage26c_exact_trades.csv    | True     |    958 |           958 | loaded   | timestamp          | original:net;mirror:gross_reversal;cols:{"net_x1": "net_x1", "net_x4": "net_x4", "net_x6": "net_x6", "gross_x1": "gross", "gross_x4": null, "gross_x6": null} | timestamp,direction,entry_price,exit_ts,exit_price,exit_reason,gross,reason,horizon_min,tp_atr,sl_atr,net_x1,net_x4,net_x6,candidate,family                 |

## Top mirrored candidate diagnostics

| source_stage   | family                           | candidate                                                        |   events |   pf_x1 |   pf_x4 |   pf_x6 |   boot_pf_p05_x4 |   median_x4 |   total_x4 |   win_rate_x4 |   original_pf_x4 |   original_total_x4 |   mirror_minus_original_pf_x4 | decision        |
|:---------------|:---------------------------------|:-----------------------------------------------------------------|---------:|--------:|--------:|--------:|-----------------:|------------:|-----------:|--------------:|-----------------:|--------------------:|------------------------------:|:----------------|
| stage26b       | htf_bias_pullback_v2             | htf_pb_lm0.75_eff0.55_pb0.3_h180_tp08_sl08                       |       53 |  1.1341 |  0.5042 |  0.2851 |           0.2641 |     -0.0582 |   -46.3075 |        0.4906 |           0.2493 |           -102.093  |                        0.2549 | STAGE26D_REJECT |
| stage26b       | htf_bias_pullback_v2             | htf_pb_lm0.75_eff0.55_pb0.3_h90_tp08_sl08                        |       53 |  1.0679 |  0.4584 |  0.254  |           0.2143 |     -0.124  |   -50.9225 |        0.4717 |           0.2581 |            -97.4775 |                        0.2003 | STAGE26D_REJECT |
| stage26b       | htf_bias_pullback_v2             | htf_pb_lm1.0_eff0.55_pb0.3_h90_tp08_sl08                         |       53 |  1.0679 |  0.4584 |  0.254  |           0.2143 |     -0.124  |   -50.9225 |        0.4717 |           0.2581 |            -97.4775 |                        0.2003 | STAGE26D_REJECT |
| stage26b       | session_transition_imbalance_v2  | sess_imb_lm0.75_eff0.7_h180_tp08_sl08                            |      215 |  0.8591 |  0.4321 |  0.2805 |           0.2896 |     -2.521  |  -276.644  |        0.3721 |           0.3375 |           -325.356  |                        0.0946 | STAGE26D_REJECT |
| stage26b       | session_transition_imbalance_v2  | sess_imb_lm0.75_eff0.7_h90_tp08_sl08                             |      215 |  0.8591 |  0.4321 |  0.2805 |           0.2896 |     -2.521  |  -276.644  |        0.3721 |           0.3375 |           -325.356  |                        0.0946 | STAGE26D_REJECT |
| stage26b       | session_transition_imbalance_v2  | sess_imb_lm1.0_eff0.7_h180_tp08_sl08                             |      215 |  0.8591 |  0.4321 |  0.2805 |           0.2896 |     -2.521  |  -276.644  |        0.3721 |           0.3375 |           -325.356  |                        0.0946 | STAGE26D_REJECT |
| stage26b       | asia_breakout_pullback_v2        | asia_br_pb_ar0.45_hold0.15_h180_tp08_sl08                        |      547 |  0.8737 |  0.387  |  0.2255 |           0.3051 |     -0.394  |  -677.506  |        0.4205 |           0.3046 |           -854.094  |                        0.0824 | STAGE26D_REJECT |
| stage26b       | asia_breakout_pullback_v2        | asia_br_pb_ar0.45_hold0.15_h90_tp08_sl08                         |      547 |  0.8626 |  0.3771 |  0.2177 |           0.2941 |     -0.4142 |  -685.77   |        0.4168 |           0.3049 |           -845.83   |                        0.0722 | STAGE26D_REJECT |
| stage26b       | asia_breakout_pullback_v2        | asia_br_pb_ar0.7_hold0.15_h90_tp08_sl08                          |      547 |  0.8626 |  0.3771 |  0.2177 |           0.2941 |     -0.4142 |  -685.77   |        0.4168 |           0.3049 |           -845.83   |                        0.0722 | STAGE26D_REJECT |
| stage26c       | failed_asia_breakout_reversal_v1 | fail_asia_br_b0.15_r0.0_e12_tp0.8_sl0.8                          |      330 |  0.7414 |  0.3493 |  0.2178 |           0.2437 |     -2.1901 |  -494.048  |        0.3758 |           0.4006 |           -429.952  |                       -0.0513 | STAGE26D_REJECT |
| stage26c       | failed_asia_breakout_reversal_v1 | fail_asia_br_b0.15_r0.1_e12_tp0.8_sl0.8                          |      317 |  0.7357 |  0.3491 |  0.2195 |           0.2447 |     -2.2598 |  -478.495  |        0.3722 |           0.4017 |           -409.105  |                       -0.0526 | STAGE26D_REJECT |
| stage26c       | failed_asia_breakout_reversal_v1 | fail_asia_br_b0.15_r0.0_e13_tp0.8_sl0.8                          |      311 |  0.7222 |  0.3267 |  0.193  |           0.2442 |     -1.8    |  -472.019  |        0.3859 |           0.3933 |           -398.781  |                       -0.0666 | STAGE26D_REJECT |
| stage26b       | squeeze_release_continuation_v2  | squeeze_release_q0.3_lm1.0_h180_tp08_sl08                        |      154 |  0.7317 |  0.2809 |  0.1494 |           0.1816 |     -0.5349 |  -221.498  |        0.3636 |           0.3151 |           -209.702  |                       -0.0342 | STAGE26D_REJECT |
| stage26b       | squeeze_release_continuation_v2  | squeeze_release_q0.3_lm0.7_h180_tp08_sl08                        |      192 |  0.6724 |  0.2673 |  0.1429 |           0.1816 |     -1.4473 |  -300.554  |        0.3698 |           0.3709 |           -237.046  |                       -0.1036 | STAGE26D_REJECT |
| stage26b       | squeeze_release_continuation_v2  | squeeze_release_q0.3_lm0.7_h90_tp08_sl08                         |      192 |  0.6718 |  0.2671 |  0.143  |           0.1816 |     -1.235  |  -300.231  |        0.3646 |           0.3703 |           -237.369  |                       -0.1032 | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | htf_bias_pullback_cont_lm0.6_eff0.55_pb0.15_h180_e13_tp0.8_sl0.8 |      188 |  0.4771 |  0.2278 |  0.1288 |           0.1511 |     -2.8629 |  -420.205  |        0.367  |           0.6909 |           -106.195  |                       -0.4631 | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | htf_bias_pullback_cont_lm0.6_eff0.55_pb0.15_h90_e13_tp0.8_sl0.8  |      188 |  0.4541 |  0.2109 |  0.1168 |           0.1447 |     -2.8211 |  -426.365  |        0.3457 |           0.7007 |           -100.035  |                       -0.4898 | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | htf_bias_pullback_cont_lm0.6_eff0.7_pb0.15_h180_e13_tp0.8_sl0.8  |      114 |  0.41   |  0.1978 |  0.109  |           0.1177 |     -3.0783 |  -288.961  |        0.3596 |           0.8484 |            -30.2389 |                       -0.6506 | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | htf_bias_pullback_cont_lm0.6_eff0.7_pb0.15_h90_e13_tp0.8_sl0.8   |      114 |  0.3792 |  0.174  |  0.0905 |           0.1054 |     -2.9303 |  -295.374  |        0.3421 |           0.8755 |            -23.8263 |                       -0.7015 | STAGE26D_REJECT |

## Mirrored family diagnostics

| source_stage   | family                           |   events |   pf_x1 |   pf_x4 |   pf_x6 |   boot_pf_p05_x4 |   median_x4 |   total_x4 |   win_rate_x4 |   original_pf_x4 |   original_total_x4 |   mirror_minus_original_pf_x4 | decision        |
|:---------------|:---------------------------------|---------:|--------:|--------:|--------:|-----------------:|------------:|-----------:|--------------:|-----------------:|--------------------:|------------------------------:|:----------------|
| stage26b       | htf_bias_pullback_v2             |      159 |  1.09   |  0.4736 |  0.2643 |           0.3362 |     -0.124  |   -148.153 |        0.478  |           0.2551 |            -297.048 |                        0.2185 | STAGE26D_REJECT |
| stage26b       | session_transition_imbalance_v2  |      645 |  0.8591 |  0.4321 |  0.2805 |           0.352  |     -2.521  |   -829.932 |        0.3721 |           0.3375 |            -976.068 |                        0.0946 | STAGE26D_REJECT |
| stage26b       | asia_breakout_pullback_v2        |     1641 |  0.8663 |  0.3804 |  0.2203 |           0.3296 |     -0.3995 |  -2049.05  |        0.418  |           0.3048 |           -2545.75  |                        0.0756 | STAGE26D_REJECT |
| stage26c       | failed_asia_breakout_reversal_v1 |      958 |  0.7334 |  0.342  |  0.2105 |           0.2772 |     -2.1901 |  -1444.56  |        0.3779 |           0.3986 |           -1237.84  |                       -0.0566 | STAGE26D_REJECT |
| stage26b       | squeeze_release_continuation_v2  |      538 |  0.6882 |  0.271  |  0.1447 |           0.2207 |     -0.6113 |   -822.284 |        0.3662 |           0.3546 |            -684.116 |                       -0.0836 | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   |      604 |  0.4371 |  0.2061 |  0.1137 |           0.1672 |     -2.8686 |  -1430.91  |        0.3543 |           0.7564 |            -260.295 |                       -0.5503 | STAGE26D_REJECT |

## Mirrored reason diagnostics

| source_stage   | family                           | reason                  |   events |    pf_x1 |    pf_x4 |    pf_x6 |   boot_pf_p05_x4 |   median_x4 |   total_x4 |   win_rate_x4 |   original_pf_x4 |   original_total_x4 |   mirror_minus_original_pf_x4 | decision        |
|:---------------|:---------------------------------|:------------------------|---------:|---------:|---------:|---------:|-----------------:|------------:|-----------:|--------------:|-----------------:|--------------------:|------------------------------:|:----------------|
| stage26a       | htf_bias_pullback_continuation   | bias=-1;london_eff=0.97 |        4 | inf      | inf      | inf      |           0      |      5.7711 |    23.0846 |        1      |           0      |            -34.2846 |                      inf      | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | bias=1;london_eff=0.99  |        4 | inf      | inf      | inf      |           0      |      3.2571 |    13.0286 |        1      |           0      |            -24.2286 |                      inf      | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | bias=-1;london_eff=0.75 |        8 | inf      | inf      |  21      |           0      |      1.5971 |    12.7771 |        1      |           0      |            -35.1771 |                      inf      | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | bias=-1;london_eff=0.86 |        4 | inf      | inf      | inf      |           0      |      1.8251 |     7.3006 |        1      |           0      |            -18.5006 |                      inf      | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | bias=-1;london_eff=0.62 |        2 | inf      | inf      | inf      |           0      |      3.5731 |     7.1463 |        1      |           0      |            -12.7463 |                      inf      | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | bias=1;london_eff=0.58  |        6 | inf      | inf      | inf      |           0      |      0.932  |     6.4194 |        1      |           0      |            -23.2194 |                      inf      | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | bias=-1;london_eff=0.81 |        4 | inf      | inf      | inf      |           0      |      1.5069 |     6.0274 |        1      |           0      |            -17.2274 |                      inf      | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | bias=-1;london_eff=0.64 |        2 | inf      | inf      | inf      |           0      |      2.4291 |     4.8583 |        1      |           0      |            -10.4583 |                      inf      | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | bias=1;london_eff=0.96  |        8 | inf      | inf      |   0.4065 |           0      |      0.5911 |     4.7291 |        1      |           0      |            -27.1291 |                      inf      | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | bias=1;london_eff=0.59  |        4 | inf      | inf      |   4.9203 |           0      |      1.1357 |     4.5429 |        1      |           0      |            -15.7429 |                      inf      | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | bias=1;london_eff=0.64  |        2 | inf      | inf      |   0      |           0      |      0.632  |     1.264  |        1      |           0      |             -6.864  |                      inf      | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | bias=-1;london_eff=0.74 |       12 | inf      |   9.603  |   1.7183 |           3.7368 |      0.5789 |    11.7394 |        0.6667 |           0      |            -45.3394 |                        9.603  | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | bias=1;london_eff=0.78  |       20 |   5.9441 |   3.2339 |   2.1216 |           1.4392 |      1.5114 |    34.4251 |        0.8    |           0.0445 |            -90.4251 |                        3.1894 | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | bias=-1;london_eff=0.57 |        8 |   7.7487 |   2.5305 |   1.1488 |           0      |      1.2251 |     6.6206 |        0.75   |           0      |            -29.0206 |                        2.5305 | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | bias=-1;london_eff=0.67 |        4 |   3.3967 |   2.1991 |   1.7074 |           0      |      2.3111 |     9.2446 |        0.5    |           0.0935 |            -20.4446 |                        2.1056 | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | bias=-1;london_eff=0.69 |        4 |   3.0706 |   1.5944 |   1.0893 |           0      |      0.8606 |     3.4423 |        0.5    |           0.0129 |            -14.6423 |                        1.5815 | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | bias=1;london_eff=0.63  |        6 |   3.0307 |   1.3989 |   0.7946 |           0      |      2.1109 |     2.5829 |        0.6667 |           0.0432 |            -19.3829 |                        1.3557 | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | bias=1;london_eff=0.65  |        4 |   1.9188 |   1.0885 |   0.7556 |           0      |      0.1634 |     0.6537 |        0.5    |           0.1307 |            -11.8537 |                        0.9578 | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | bias=1;london_eff=0.83  |       20 |   2.3367 |   0.9887 |   0.5164 |           0.427  |      0.776  |    -0.2697 |        0.6    |           0.0264 |            -55.7303 |                        0.9623 | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | bias=1;london_eff=0.56  |        8 |   2.4144 |   0.9465 |   0.5268 |           0      |     -0.2234 |    -0.4606 |        0.25   |           0.0879 |            -21.9394 |                        0.8586 | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | bias=-1;london_eff=0.70 |        6 |   1.9161 |   0.6996 |   0.2364 |           0      |      1.1823 |    -2.0309 |        0.6667 |           0.0728 |            -14.7691 |                        0.6268 | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | bias=1;london_eff=0.80  |        8 |   0.9612 |   0.6104 |   0.4389 |           0      |     -1.1434 |    -9.1474 |        0.5    |           0.481  |            -13.2526 |                        0.1294 | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | bias=-1;london_eff=0.92 |        8 |   0.8982 |   0.5588 |   0.3927 |           0      |     -1.2954 |   -10.3634 |        0.5    |           0.5052 |            -12.0366 |                        0.0536 | STAGE26D_REJECT |
| stage26b       | htf_bias_pullback_v2             | unknown_reason          |      159 |   1.09   |   0.4736 |   0.2643 |           0.3362 |     -0.124  |  -148.153  |        0.478  |           0.2551 |           -297.048  |                        0.2185 | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | bias=1;london_eff=0.92  |        8 |   1.0069 |   0.4592 |   0.2345 |           0      |     -1.0403 |    -8.3223 |        0.5    |           0.2293 |            -14.0777 |                        0.2299 | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | bias=1;london_eff=0.69  |        8 |   0.9957 |   0.4422 |   0.2738 |           0      |     -1.5826 |    -8.4457 |        0.25   |           0.207  |            -13.9543 |                        0.2352 | STAGE26D_REJECT |
| stage26b       | session_transition_imbalance_v2  | unknown_reason          |      645 |   0.8591 |   0.4321 |   0.2805 |           0.352  |     -2.521  |  -829.932  |        0.3721 |           0.3375 |           -976.068  |                        0.0946 | STAGE26D_REJECT |
| stage26b       | asia_breakout_pullback_v2        | unknown_reason          |     1641 |   0.8663 |   0.3804 |   0.2203 |           0.3296 |     -0.3995 | -2049.05   |        0.418  |           0.3048 |          -2545.75   |                        0.0756 | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | bias=1;london_eff=0.84  |       20 |   1.0282 |   0.3637 |   0.0922 |           0.1685 |      0.6343 |   -20.336  |        0.6    |           0.2114 |            -35.664  |                        0.1523 | STAGE26D_REJECT |
| stage26c       | failed_asia_breakout_reversal_v1 | failed_asia_high_break  |      507 |   0.8238 |   0.3588 |   0.2092 |           0.2809 |     -0.4655 |  -667.986  |        0.4004 |           0.326  |           -751.614  |                        0.0328 | STAGE26D_REJECT |

## Mirrored direction/hour diagnostics

| source_stage   | family                           | direction_label   |   entry_hour |   events |   pf_x1 |   pf_x4 |   pf_x6 |   boot_pf_p05_x4 |   median_x4 |   total_x4 |   win_rate_x4 |   original_pf_x4 |   original_total_x4 |   mirror_minus_original_pf_x4 | decision        |
|:---------------|:---------------------------------|:------------------|-------------:|---------:|--------:|--------:|--------:|-----------------:|------------:|-----------:|--------------:|-----------------:|--------------------:|------------------------------:|:----------------|
| stage26b       | htf_bias_pullback_v2             | -1                |           13 |       66 |  1.1202 |  0.5992 |  0.3972 |           0.3269 |     -0.3238 |   -56.3235 |        0.4091 |           0.3218 |           -128.476  |                        0.2774 | STAGE26D_REJECT |
| stage26b       | asia_breakout_pullback_v2        | -1                |           13 |      723 |  0.9788 |  0.4806 |  0.301  |           0.3897 |     -0.5223 |  -782.987  |        0.4246 |           0.303  |          -1241.41   |                        0.1776 | STAGE26D_REJECT |
| stage26b       | session_transition_imbalance_v2  | 1                 |           13 |      384 |  1.0942 |  0.4782 |  0.2762 |           0.3749 |     -0.3695 |  -357.596  |        0.4297 |           0.1982 |           -717.605  |                        0.28   | STAGE26D_REJECT |
| stage26b       | squeeze_release_continuation_v2  | -1                |           13 |      248 |  1.0291 |  0.443  |  0.2504 |           0.3134 |     -0.3611 |  -250.97   |        0.4315 |           0.2396 |           -443.43   |                        0.2034 | STAGE26D_REJECT |
| stage26b       | session_transition_imbalance_v2  | -1                |           13 |      261 |  0.669  |  0.3913 |  0.2844 |           0.2757 |     -2.8217 |  -472.337  |        0.2874 |           0.5531 |           -258.464  |                       -0.1618 | STAGE26D_REJECT |
| stage26c       | failed_asia_breakout_reversal_v1 | -1                |           13 |      170 |  0.8472 |  0.3628 |  0.2063 |           0.2565 |     -0.45   |  -216.56   |        0.3941 |           0.3108 |           -259.44   |                        0.052  | STAGE26D_REJECT |
| stage26c       | failed_asia_breakout_reversal_v1 | -1                |           12 |      337 |  0.8126 |  0.3569 |  0.2105 |           0.2637 |     -0.4655 |  -451.426  |        0.4036 |           0.3338 |           -492.174  |                        0.0231 | STAGE26D_REJECT |
| stage26b       | htf_bias_pullback_v2             | 1                 |           13 |       93 |  1.0576 |  0.3484 |  0.1405 |           0.2219 |      0.0517 |   -91.829  |        0.5269 |           0.1947 |           -168.571  |                        0.1537 | STAGE26D_REJECT |
| stage26c       | failed_asia_breakout_reversal_v1 | 1                 |           12 |      310 |  0.6744 |  0.3423 |  0.2261 |           0.2221 |     -2.4272 |  -521.118  |        0.3419 |           0.4762 |           -346.882  |                       -0.1339 | STAGE26D_REJECT |
| stage26b       | asia_breakout_pullback_v2        | 1                 |           13 |      918 |  0.7702 |  0.2965 |  0.1543 |           0.2488 |     -0.374  | -1266.06   |        0.4129 |           0.3065 |          -1304.34   |                       -0.01   | STAGE26D_REJECT |
| stage26c       | failed_asia_breakout_reversal_v1 | 1                 |           13 |      141 |  0.6087 |  0.2928 |  0.18   |           0.187  |     -2.5302 |  -255.46   |        0.3759 |           0.5038 |           -139.34   |                       -0.211  | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | long              |           13 |      392 |  0.5347 |  0.2302 |  0.116  |           0.1829 |     -2.8629 |  -757.282  |        0.3776 |           0.5147 |           -340.318  |                       -0.2845 | STAGE26D_REJECT |
| stage26a       | htf_bias_pullback_continuation   | short             |           13 |      212 |  0.3293 |  0.177  |  0.1108 |           0.126  |     -2.9491 |  -673.623  |        0.3113 |           1.2178 |             80.0229 |                       -1.0408 | STAGE26D_REJECT |
| stage26b       | squeeze_release_continuation_v2  | 1                 |           13 |      290 |  0.4677 |  0.1565 |  0.073  |           0.1168 |     -2.566  |  -571.314  |        0.3103 |           0.4951 |           -240.686  |                       -0.3386 | STAGE26D_REJECT |

## Interpretation

- Stage26D checks whether rejected exact trades from Stage26A/B/C behave as anti-signals.
- Unlike earlier Stage26D versions, Stage26A/B artifacts are not skipped just because they lack a literal `timestamp` column, and original-vs-mirror grouping avoids duplicate pandas column labels.
- A positive mirror result is not enough for promotion because path-dependent TP/SL execution must be replayed directly from DB candles in the mirrored direction.
- If this stage finds a promotion-review mirror candidate, the next step is a dedicated DB-first exact replay for that mirrored rule.
- If no mirror edge appears after all three artifacts load, discovery should move away from Stage26A/B/C families rather than repeatedly mutating them.

## Operational reminder

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage18a_unified_shadow_ops_cycle
python3 -m app.stage23d_forward_shadow_candidate
python3 -m app.stage25d_db_first_filtered_forward_shadow
```

## Output files

- `data/reports/stage26d_artifact_mirror_diagnostic/stage26d_artifact_mirror_diagnostic.json`
- `data/reports/stage26d_artifact_mirror_diagnostic/stage26d_artifact_mirror_diagnostic.md`
- `data/reports/stage26d_artifact_mirror_diagnostic/stage26d_input_manifest.csv`
- `data/reports/stage26d_artifact_mirror_diagnostic/stage26d_normalized_source_trades.csv`
- `data/reports/stage26d_artifact_mirror_diagnostic/stage26d_mirror_by_candidate.csv`
- `data/reports/stage26d_artifact_mirror_diagnostic/stage26d_mirror_by_family.csv`
- `data/reports/stage26d_artifact_mirror_diagnostic/stage26d_mirror_by_reason.csv`
- `data/reports/stage26d_artifact_mirror_diagnostic/stage26d_mirror_by_direction_hour.csv`
- `data/reports/stage26d_artifact_mirror_diagnostic/stage26d_db_schema_diagnostic.csv`
