# Stage58A Context-Aware Stage51 Regime Audit

- status: `CONTEXT_AWARE_STAGE51_AUDIT_COMPLETE_NO_PROMOTION`
- decision: `CONTEXT_AWARE_STAGE51_AUDIT_PASS_NEEDS_FORWARD_SHADOW_DESIGN_NO_PROMOTION`
- next_allowed_step: `DESIGN_STAGE58B_CONTEXT_FORWARD_SHADOW_NO_PROMOTION`
- promotion: `NO_GO`
- EA: `NO_GO`
- paper_live: `NO_GO`
- live: `NO_GO`

## Inputs
- db: `/Users/vahid/Desktop/xauusd-trader/data/broker_normalized/amarkets_multitf.sqlite`
- cost_model: `/Users/vahid/Desktop/xauusd-trader/reports/stage48f/stage48f_cost_model.json`
- stage51_candidates: `/Users/vahid/Desktop/xauusd-trader/reports/stage51_volatility_squeeze/stage51_volatility_squeeze_breakout_candidates.csv`
- M15 context: `/Users/vahid/Desktop/xauusd-trader/reports/stage57_context_precheck/stage57a_m15_context_regime_table.csv`
- M5 context: `/Users/vahid/Desktop/xauusd-trader/reports/stage57_context_precheck/stage57a_m5_context_regime_table.csv`

## Audit summary
- base_candidates_loaded: `12`
- context_audit_candidates: `156`
- hard_audit_pass_count: `4`
- costs: `{'stress_cost_bps': 2.982003733153722, 'extreme_cost_bps': 3.0380209087577326}`

## Signal counts by base Stage51 candidate
- `S51_VSQ_CW48_P20_B5_M3020_H24`: `2535`
- `S51_VSQ_CW48_P20_B5_M3040_H24`: `2307`
- `S51_VSQ_CW96_P20_B3_M3020_H24`: `3748`
- `S51_VSQ_CW96_P20_B3_M3040_H24`: `3373`
- `S51_VSQ_CW96_P20_B5_M3020_H12`: `2446`
- `S51_VSQ_CW96_P20_B5_M3040_H12`: `2193`
- `S51_VSQ_CW96_P20_B5_M3020_H24`: `2446`
- `S51_VSQ_CW96_P20_B5_M3040_H24`: `2193`
- `S51_VSQ_CW48_P20_B5_M3040_H12`: `2307`
- `S51_VSQ_CW48_P20_B5_M3020_H12`: `2535`
- `S51_VSQ_CW48_P20_B3_M3020_H24`: `3883`
- `S51_VSQ_CW96_P20_B3_M3020_H12`: `3749`

## Top context candidates
- `S58A_S51_VSQ_CW48_P20_B5_M3040_H12_CTX_RANGE_GT50` status=`CONTEXT_AWARE_HARD_AUDIT_PASS_NEEDS_FORWARD_SHADOW_DESIGN` trades=`1861` mean=`4.110` wr=`0.534` oos_mean=`5.678457068742172` failures=``
- `S58A_S51_VSQ_CW96_P20_B5_M3040_H12_CTX_SPREAD_LE75` status=`CONTEXT_AWARE_HARD_AUDIT_PASS_NEEDS_FORWARD_SHADOW_DESIGN` trades=`1742` mean=`3.860` wr=`0.532` oos_mean=`4.839976821464046` failures=``
- `S58A_S51_VSQ_CW48_P20_B5_M3020_H12_CTX_RANGE_GT50` status=`CONTEXT_AWARE_HARD_AUDIT_PASS_NEEDS_FORWARD_SHADOW_DESIGN` trades=`2032` mean=`3.743` wr=`0.531` oos_mean=`3.9670621115596707` failures=``
- `S58A_S51_VSQ_CW96_P20_B5_M3020_H12_CTX_RANGE_GT50` status=`CONTEXT_AWARE_HARD_AUDIT_PASS_NEEDS_FORWARD_SHADOW_DESIGN` trades=`1948` mean=`3.598` wr=`0.533` oos_mean=`3.4037630926842444` failures=``
- `S58A_S51_VSQ_CW48_P20_B5_M3040_H24_CTX_OVERLAP_NY` status=`NO_PASS` trades=`903` mean=`1.480` wr=`0.462` oos_mean=`10.796925675994663` failures=`mean_stress_lt_min;median_stress_lt_min;win_rate_lt_min;positive_years_lt_min;negative_years_gt_max;worst_year_lt_min;cost_x2_mean_lt_min;declustered_win_rate_lt_min`
- `S58A_S51_VSQ_CW48_P20_B5_M3040_H24_CTX_ALL` status=`NO_PASS` trades=`2307` mean=`3.721` wr=`0.498` oos_mean=`10.785899092383328` failures=`median_stress_lt_min;win_rate_lt_min;worst_year_lt_min`
- `S58A_S51_VSQ_CW48_P20_B5_M3020_H24_CTX_OVERLAP_NY` status=`NO_PASS` trades=`975` mean=`1.524` wr=`0.453` oos_mean=`10.353145150853452` failures=`mean_stress_lt_min;median_stress_lt_min;win_rate_lt_min;positive_years_lt_min;negative_years_gt_max;worst_year_lt_min;cost_x2_mean_lt_min;declustered_win_rate_lt_min`
- `S58A_S51_VSQ_CW48_P20_B5_M3040_H24_CTX_NO_ROLLOVER` status=`NO_PASS` trades=`1821` mean=`3.372` wr=`0.492` oos_mean=`9.621440809752151` failures=`median_stress_lt_min;win_rate_lt_min;worst_year_lt_min`
- `S58A_S51_VSQ_CW48_P20_B5_M3020_H12_CTX_OVERLAP_NY` status=`NO_PASS` trades=`975` mean=`1.860` wr=`0.491` oos_mean=`9.14380694196786` failures=`mean_stress_lt_min;median_stress_lt_min;win_rate_lt_min;positive_years_lt_min;negative_years_gt_max;worst_year_lt_min;cost_x2_mean_lt_min;declustered_win_rate_lt_min`
- `S58A_S51_VSQ_CW48_P20_B5_M3040_H12_CTX_ALL` status=`NO_PASS` trades=`2307` mean=`3.274` wr=`0.522` oos_mean=`9.12898200723291` failures=`win_rate_lt_min`
- `S58A_S51_VSQ_CW48_P20_B5_M3040_H24_CTX_SPREAD_LE90` status=`NO_PASS` trades=`2096` mean=`4.331` wr=`0.508` oos_mean=`9.017552418008098` failures=`win_rate_lt_min;worst_year_lt_min`
- `S58A_S51_VSQ_CW48_P20_B5_M3040_H12_CTX_NO_ROLLOVER` status=`NO_PASS` trades=`1821` mean=`3.201` wr=`0.516` oos_mean=`8.92430006024207` failures=`win_rate_lt_min;worst_year_lt_min`
- `S58A_S51_VSQ_CW48_P20_B5_M3020_H24_CTX_NO_ROLLOVER` status=`NO_PASS` trades=`1965` mean=`3.028` wr=`0.490` oos_mean=`8.74023942354275` failures=`median_stress_lt_min;win_rate_lt_min;worst_year_lt_min`
- `S58A_S51_VSQ_CW48_P20_B5_M3020_H24_CTX_ALL` status=`NO_PASS` trades=`2535` mean=`3.015` wr=`0.496` oos_mean=`8.697375421981496` failures=`median_stress_lt_min;win_rate_lt_min;worst_year_lt_min`
- `S58A_S51_VSQ_CW96_P20_B5_M3040_H24_CTX_OVERLAP_NY` status=`NO_PASS` trades=`571` mean=`1.872` wr=`0.468` oos_mean=`8.461293216523798` failures=`mean_stress_lt_min;median_stress_lt_min;win_rate_lt_min;positive_years_lt_min;negative_years_gt_max;worst_year_lt_min;cost_x2_mean_lt_min;declustered_win_rate_lt_min`
- `S58A_S51_VSQ_CW48_P20_B5_M3020_H12_CTX_NO_ROLLOVER` status=`NO_PASS` trades=`1965` mean=`2.999` wr=`0.512` oos_mean=`8.31018126529357` failures=`win_rate_lt_min;worst_year_lt_min`
- `S58A_S51_VSQ_CW48_P20_B5_M3020_H12_CTX_ALL` status=`NO_PASS` trades=`2535` mean=`2.929` wr=`0.519` oos_mean=`8.21283685537458` failures=`win_rate_lt_min;cost_x2_mean_lt_min`
- `S58A_S51_VSQ_CW96_P20_B3_M3020_H12_CTX_OVERLAP_NY` status=`NO_PASS` trades=`1004` mean=`0.609` wr=`0.453` oos_mean=`8.043516145052216` failures=`mean_stress_lt_min;median_stress_lt_min;win_rate_lt_min;positive_years_lt_min;negative_years_gt_max;worst_year_lt_min;cost_x2_mean_lt_min;declustered_win_rate_lt_min`
- `S58A_S51_VSQ_CW96_P20_B5_M3040_H24_CTX_RANGE_50_90` status=`NO_PASS` trades=`1388` mean=`3.406` wr=`0.518` oos_mean=`7.993970492682091` failures=`win_rate_lt_min;worst_year_lt_min`
- `S58A_S51_VSQ_CW96_P20_B5_M3040_H12_CTX_ALL` status=`NO_PASS` trades=`2193` mean=`3.096` wr=`0.523` oos_mean=`7.864543984245091` failures=`win_rate_lt_min;worst_year_lt_min`

## Interpretation
Stage58A is a historical context/regime overlay audit only. It does not use historical context results as forward evidence and does not authorize promotion, EA, paper-live, live trading, or order submission.
