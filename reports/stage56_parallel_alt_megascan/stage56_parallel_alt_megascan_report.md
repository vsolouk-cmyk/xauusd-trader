# Stage56 Parallel Alternative Megascan

- status: `PARALLEL_ALT_MEGASCAN_COMPLETE_NO_PROMOTION`
- decision: `ALT_MEGASCAN_COMPLETE_NO_PASS_NO_PROMOTION`
- next_allowed_step: `ARCHIVE_ALT_MEGASCAN_OR_EXPAND_CONTEXT_NO_PROMOTION`
- promotion: `NO_GO`
- EA: `NO_GO`
- paper_live: `NO_GO`
- live: `NO_GO`

## Inputs
- db: `/Users/vahid/Desktop/xauusd-trader/data/broker_normalized/amarkets_multitf.sqlite`
- cost_model: `/Users/vahid/Desktop/xauusd-trader/reports/stage48f/stage48f_cost_model.json`
- families: `ALT_A_PULLBACK_AFTER_SQUEEZE_FAILURE, ALT_B_INTRADAY_TREND_PULLBACK_TO_M15_VALUE_AREA, ALT_C_SESSION_RANGE_REVERSION_AFTER_EXHAUSTION`

## Scan summary
- `ALT_A_PULLBACK_AFTER_SQUEEZE_FAILURE`: candidates=`216`, trades=`21602`, pass=`0`
- `ALT_B_INTRADAY_TREND_PULLBACK_TO_M15_VALUE_AREA`: candidates=`729`, trades=`1405689`, pass=`0`
- `ALT_C_SESSION_RANGE_REVERSION_AFTER_EXHAUSTION`: candidates=`72`, trades=`124630`, pass=`0`

- total_candidates: `1017`
- hard_audit_pass_count: `0`

## Top candidates
- `S56A_CW48_P30_B8_F3_M3040_H12` family=`ALT_A_PULLBACK_AFTER_SQUEEZE_FAILURE` status=`NO_PASS` trades=`25` mean=`9.705` wr=`0.520` oos_mean=`33.671` oos_wr=`0.800` failures=`trade_count_lt_min;oos_trade_count_lt_min;positive_years_lt_min;negative_years_gt_max;worst_year_lt_min`
- `S56A_CW48_P20_B8_F3_M3040_H12` family=`ALT_A_PULLBACK_AFTER_SQUEEZE_FAILURE` status=`NO_PASS` trades=`9` mean=`7.538` wr=`0.556` oos_mean=`24.539` oos_wr=`0.500` failures=`trade_count_lt_min;oos_trade_count_lt_min;oos_win_rate_lt_min;positive_years_lt_min;worst_year_lt_min`
- `S56A_CW48_P30_B8_F3_M3020_H12` family=`ALT_A_PULLBACK_AFTER_SQUEEZE_FAILURE` status=`NO_PASS` trades=`24` mean=`13.991` wr=`0.583` oos_mean=`22.362` oos_wr=`0.800` failures=`trade_count_lt_min;oos_trade_count_lt_min;positive_years_lt_min;negative_years_gt_max;worst_year_lt_min`
- `S56A_CW192_P30_B8_F1_M3020_H12` family=`ALT_A_PULLBACK_AFTER_SQUEEZE_FAILURE` status=`NO_PASS` trades=`15` mean=`-0.282` wr=`0.533` oos_mean=`22.262` oos_wr=`0.667` failures=`trade_count_lt_min;oos_trade_count_lt_min;mean_stress_lt_min;positive_years_lt_min;negative_years_gt_max;worst_year_lt_min;cost_x2_mean_lt_min`
- `S56A_CW48_P20_B5_F3_M3020_H12` family=`ALT_A_PULLBACK_AFTER_SQUEEZE_FAILURE` status=`NO_PASS` trades=`53` mean=`9.907` wr=`0.566` oos_mean=`21.565` oos_wr=`0.818` failures=`trade_count_lt_min;oos_trade_count_lt_min;negative_years_gt_max;worst_year_lt_min`
- `S56A_CW48_P20_B8_F3_M3040_H6` family=`ALT_A_PULLBACK_AFTER_SQUEEZE_FAILURE` status=`NO_PASS` trades=`9` mean=`3.672` wr=`0.444` oos_mean=`19.493` oos_wr=`0.500` failures=`trade_count_lt_min;oos_trade_count_lt_min;median_stress_lt_min;win_rate_lt_min;oos_win_rate_lt_min;positive_years_lt_min;worst_year_lt_min;declustered_mean_lt_min`
- `S56A_CW48_P30_B5_F3_M3020_H12` family=`ALT_A_PULLBACK_AFTER_SQUEEZE_FAILURE` status=`NO_PASS` trades=`120` mean=`6.820` wr=`0.508` oos_mean=`18.579` oos_wr=`0.708` failures=`trade_count_lt_min;oos_trade_count_lt_min;win_rate_lt_min;positive_years_lt_min;negative_years_gt_max;worst_year_lt_min`
- `S56A_CW192_P20_B8_F3_M3040_H12` family=`ALT_A_PULLBACK_AFTER_SQUEEZE_FAILURE` status=`NO_PASS` trades=`8` mean=`6.638` wr=`0.375` oos_mean=`17.523` oos_wr=`0.500` failures=`trade_count_lt_min;oos_trade_count_lt_min;median_stress_lt_min;win_rate_lt_min;oos_win_rate_lt_min;positive_years_lt_min`
- `S56A_CW96_P20_B8_F3_M3040_H12` family=`ALT_A_PULLBACK_AFTER_SQUEEZE_FAILURE` status=`NO_PASS` trades=`7` mean=`-4.761` wr=`0.429` oos_mean=`17.523` oos_wr=`0.500` failures=`trade_count_lt_min;oos_trade_count_lt_min;mean_stress_lt_min;median_stress_lt_min;win_rate_lt_min;oos_win_rate_lt_min;positive_years_lt_min;worst_year_lt_min;cost_x2_mean_lt_min;declustered_mean_lt_min`
- `S56A_CW48_P20_B5_F3_M3020_H6` family=`ALT_A_PULLBACK_AFTER_SQUEEZE_FAILURE` status=`NO_PASS` trades=`53` mean=`4.318` wr=`0.585` oos_mean=`17.084` oos_wr=`0.818` failures=`trade_count_lt_min;oos_trade_count_lt_min;negative_years_gt_max;worst_year_lt_min`
- `S56A_CW192_P30_B8_F1_M3020_H6` family=`ALT_A_PULLBACK_AFTER_SQUEEZE_FAILURE` status=`NO_PASS` trades=`15` mean=`5.276` wr=`0.667` oos_mean=`16.743` oos_wr=`1.000` failures=`trade_count_lt_min;oos_trade_count_lt_min;positive_years_lt_min;worst_year_lt_min`
- `S56A_CW192_P20_B5_F2_M3040_H12` family=`ALT_A_PULLBACK_AFTER_SQUEEZE_FAILURE` status=`NO_PASS` trades=`34` mean=`12.789` wr=`0.529` oos_mean=`15.593` oos_wr=`0.571` failures=`trade_count_lt_min;oos_trade_count_lt_min;positive_years_lt_min;negative_years_gt_max;worst_year_lt_min`
- `S56A_CW192_P20_B5_F2_M3040_H6` family=`ALT_A_PULLBACK_AFTER_SQUEEZE_FAILURE` status=`NO_PASS` trades=`34` mean=`6.067` wr=`0.441` oos_mean=`15.389` oos_wr=`0.857` failures=`trade_count_lt_min;oos_trade_count_lt_min;median_stress_lt_min;win_rate_lt_min;positive_years_lt_min;negative_years_gt_max;worst_year_lt_min`
- `S56A_CW48_P20_B5_F1_M3040_H12` family=`ALT_A_PULLBACK_AFTER_SQUEEZE_FAILURE` status=`NO_PASS` trades=`45` mean=`0.684` wr=`0.556` oos_mean=`15.082` oos_wr=`0.778` failures=`trade_count_lt_min;oos_trade_count_lt_min;mean_stress_lt_min;positive_years_lt_min;negative_years_gt_max;worst_year_lt_min;cost_x2_mean_lt_min`
- `S56A_CW48_P20_B5_F3_M3040_H6` family=`ALT_A_PULLBACK_AFTER_SQUEEZE_FAILURE` status=`NO_PASS` trades=`62` mean=`2.528` wr=`0.516` oos_mean=`14.621` oos_wr=`0.692` failures=`trade_count_lt_min;oos_trade_count_lt_min;win_rate_lt_min;positive_years_lt_min;negative_years_gt_max;worst_year_lt_min;cost_x2_mean_lt_min`
- `S56A_CW48_P20_B5_F3_M3040_H12` family=`ALT_A_PULLBACK_AFTER_SQUEEZE_FAILURE` status=`NO_PASS` trades=`62` mean=`5.234` wr=`0.532` oos_mean=`14.112` oos_wr=`0.538` failures=`trade_count_lt_min;oos_trade_count_lt_min;positive_years_lt_min;negative_years_gt_max;worst_year_lt_min`
- `S56A_CW48_P30_B5_F3_M3040_H12` family=`ALT_A_PULLBACK_AFTER_SQUEEZE_FAILURE` status=`NO_PASS` trades=`132` mean=`3.508` wr=`0.477` oos_mean=`13.805` oos_wr=`0.593` failures=`trade_count_lt_min;oos_trade_count_lt_min;median_stress_lt_min;win_rate_lt_min;positive_years_lt_min;negative_years_gt_max;worst_year_lt_min`
- `S56B_M3040_VAL32_IMP2_MIN18_PB6_H18` family=`ALT_B_INTRADAY_TREND_PULLBACK_TO_M15_VALUE_AREA` status=`NO_PASS` trades=`343` mean=`0.946` wr=`0.437` oos_mean=`13.631` oos_wr=`0.449` failures=`mean_stress_lt_min;median_stress_lt_min;win_rate_lt_min;oos_win_rate_lt_min;positive_years_lt_min;negative_years_gt_max;worst_year_lt_min;cost_x2_mean_lt_min;declustered_mean_lt_min`
- `S56A_CW96_P20_B5_F3_M3040_H6` family=`ALT_A_PULLBACK_AFTER_SQUEEZE_FAILURE` status=`NO_PASS` trades=`36` mean=`2.496` wr=`0.528` oos_mean=`12.944` oos_wr=`0.625` failures=`trade_count_lt_min;oos_trade_count_lt_min;positive_years_lt_min;negative_years_gt_max;worst_year_lt_min;cost_x2_mean_lt_min`
- `S56A_CW192_P20_B5_F3_M3040_H12` family=`ALT_A_PULLBACK_AFTER_SQUEEZE_FAILURE` status=`NO_PASS` trades=`37` mean=`2.880` wr=`0.514` oos_mean=`12.772` oos_wr=`0.500` failures=`trade_count_lt_min;oos_trade_count_lt_min;win_rate_lt_min;oos_win_rate_lt_min;positive_years_lt_min;negative_years_gt_max;worst_year_lt_min;cost_x2_mean_lt_min`

## Interpretation
Stage56 is a parallel historical megascan/audit only. It does not use historical results as forward evidence and does not authorize promotion, EA, paper-live, live trading, or order submission.
