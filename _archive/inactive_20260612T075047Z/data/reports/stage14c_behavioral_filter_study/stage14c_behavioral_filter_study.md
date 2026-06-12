# Stage 14C Behavioral Filter Study

Generated UTC: `2026-06-11T05:35:28+00:00`
Tool version: `v1`

> Hard rule: research only. No EA change, no automatic trading, no paper/live authorization.

## Inputs
- db: `data/local/xauusd_local_store.sqlite`
- candidate_csv: `data/reports/stage14b_prev_day_low_sweep_validation/stage14b_candidate_outcomes.csv`
- intraday_source: `m1_to_m15`
- candidate_rows: `377`
- cost_usd: `0.35`
- min_events: `80`
- filters_tested: `27`

## Final decision
- final_decision: `FILTER_CANDIDATE_FOUND`

## Reasons
- Top filter `sweep_depth_ge_q50` passed net-after-cost basic checks.
- This permits one focused robustness/replay validation, not EA/paper/live.

## Baseline before filters
| Metric set | Events | Total | Avg | Median | WR | PF | DD | Pos years |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| raw | 377 | 240.56 | 0.63809 | 0.33 | 0.522546 | 1.276455 | -112.49 | 4/5 |
| net_x1 | 377 | 108.61 | 0.28809 | -0.02 | 0.496021 | 1.116218 | -117.64 | 4/5 |

## Top filters
| Rank | Filter | Events | Coverage | Net total | Net avg | Net median | Net WR | Net PF | Net DD | Test PF | Test total | Candidate |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | sweep_depth_ge_q50 | 189 | 0.501326 | 176.36 | 0.933122 | 0.98 | 0.582011 | 1.311932 | -130.6 | 1.178678 | 58.71 | True |
| 2 | deep_sweep_fast_reclaim | 47 | 0.124668 | 105.8 | 2.251064 | 1.47 | 0.531915 | 1.670809 | -47.67 | 1.036778 | 4.1 | False |
| 3 | session_new_york | 126 | 0.334218 | 184.31 | 1.462778 | 0.03 | 0.5 | 1.543271 | -61.78 | 2.570591 | 190.23 | False |
| 4 | h4_slope_positive | 152 | 0.403183 | 118.31 | 0.778355 | -0.01 | 0.5 | 1.390539 | -56.09 | 2.191699 | 142.98 | False |
| 5 | london_or_ny_fast_reclaim | 78 | 0.206897 | 65.52 | 0.84 | -0.42 | 0.474359 | 1.280888 | -58.5 | 1.599296 | 59.63 | False |
| 6 | sweep_depth_between_q25_q75 | 190 | 0.503979 | 70.94 | 0.373368 | -0.015 | 0.494737 | 1.205957 | -128.88 | 3.902577 | 184.72 | False |
| 7 | h4_up_london_or_ny | 47 | 0.124668 | 15.26 | 0.324681 | -0.5 | 0.425532 | 1.172041 | -60.02 | 9.264493 | 68.43 | False |
| 8 | fast_reclaim_le_1bar | 124 | 0.328912 | 50.06 | 0.40371 | -0.425 | 0.467742 | 1.140986 | -61.5 | 1.237848 | 41.3 | False |
| 9 | atr_pct_not_extreme_high | 276 | 0.732095 | 89.71 | 0.325036 | -0.04 | 0.48913 | 1.13552 | -107.43 | 1.63726 | 183.55 | False |
| 10 | close_below_prior_mid | 366 | 0.970822 | 120.46 | 0.329126 | -0.015 | 0.497268 | 1.134693 | -113.89 | 1.30745 | 138.82 | False |
| 11 | session_london_or_ny | 225 | 0.596817 | 70.76 | 0.314489 | -0.23 | 0.48 | 1.119709 | -110.41 | 1.530084 | 131.18 | False |
| 12 | sweep_depth_ge_q75 | 95 | 0.251989 | 49.22 | 0.518105 | 0.98 | 0.547368 | 1.112408 | -130.6 | 0.698454 | -80.76 | False |
| 13 | atr_pct_40_85 | 127 | 0.33687 | 31.64 | 0.249134 | -0.45 | 0.472441 | 1.100263 | -114.54 | 2.727218 | 144.62 | False |
| 14 | reclaim_ge_q50 | 189 | 0.501326 | 61.39 | 0.324815 | 0.01 | 0.502646 | 1.093758 | -97.95 | 1.118838 | 38.11 | False |
| 15 | atr_pct_mid_high | 228 | 0.604775 | 50.54 | 0.221667 | -0.145 | 0.491228 | 1.085932 | -110.75 | 1.508774 | 127.28 | False |
| 16 | h4_up_and_slope_positive | 69 | 0.183024 | 1.72 | 0.024928 | -0.45 | 0.434783 | 1.012464 | -63.68 | 2.658215 | 65.4 | False |
| 17 | h4_up_fast_reclaim | 44 | 0.116711 | -0.32 | -0.007273 | -0.945 | 0.386364 | 0.996714 | -49.26 | 1.773396 | 24.71 | False |
| 18 | h4_up_context | 85 | 0.225464 | -8.04 | -0.094588 | -0.5 | 0.435294 | 0.951308 | -83.08 | 2.843282 | 75.04 | False |
| 19 | reclaim_ge_q75 | 96 | 0.254642 | -23.58 | -0.245625 | -0.665 | 0.46875 | 0.947268 | -122.51 | 0.851316 | -36.78 | False |
| 20 | lower_wick_ratio_ge_q50 | 189 | 0.501326 | -32.4 | -0.171429 | -0.62 | 0.444444 | 0.943211 | -122.99 | 1.243082 | 67.64 | False |

## Interpretation
- `FILTER_CANDIDATE_FOUND` permits one focused robustness/replay validation for the top filter only.
- `WEAK_FILTER_IMPROVEMENT_ONLY` means the behavior may exist but is still not strong enough after cost.
- `NO_FILTER_IMPROVEMENT` rejects this candidate/filter set, not XAUUSD as a market.
- Do not convert any filter directly to EA/paper/live.

## Output files
- feature_csv: `data/reports/stage14c_behavioral_filter_study/stage14c_candidate_features.csv`
- filter_csv: `data/reports/stage14c_behavioral_filter_study/stage14c_filter_summary.csv`
- json: `data/reports/stage14c_behavioral_filter_study/stage14c_behavioral_filter_study.json`
- md: `data/reports/stage14c_behavioral_filter_study/stage14c_behavioral_filter_study.md`
