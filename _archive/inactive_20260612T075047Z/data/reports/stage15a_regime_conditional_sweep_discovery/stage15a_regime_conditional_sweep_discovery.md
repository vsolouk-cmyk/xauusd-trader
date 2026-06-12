# Stage 15A Regime-Conditional Liquidity Sweep Discovery

Generated UTC: `2026-06-11T05:46:38+00:00`
Tool version: `v1`

> Hard rule: research only. No EA change, no automatic trading, no paper/live authorization.

## Branch under diagnosis
- setup: `prev_day_low_sweep_rejection`
- side: `LONG`
- horizon_bars: `4`
- branch_filter: `sweep_depth_ge_q50`
- sweep_depth_q50: `1.62`
- branch_events: `189`
- cost_usd: `0.35`

## Final decision
- final_decision: `REGIME_CONDITION_CANDIDATE_FOUND`

## Reasons
- Top pre-trade regime `reclaim_lt_q50` passed strict diagnostic thresholds.
- This permits exact replay/robustness for that single regime-conditioned setup only.

## Baseline branch net x1
| Events | Total | Avg | Median | WR | PF | DD | Pos years | Pos quarters |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 189 | 176.36 | 0.933122 | 0.98 | 0.582011 | 1.311932 | -130.6 | 3/5 | 12/17 |

## Current 2026 segment net x1
| Events | Total | Avg | Median | WR | PF | DD |
|---:|---:|---:|---:|---:|---:|---:|
| 35 | -52.3 | -1.494286 | -1.42 | 0.485714 | 0.814532 | -130.6 |

## Top regime conditions
| Rank | Regime | Observable | Events | Coverage | Net total | Net median | WR | PF | DD | Test total | Test PF | Candidate |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | reclaim_lt_q50 | True | 94 | 0.497354 | 145.33 | 1.185 | 0.617021 | 1.972627 | -58.78 | 128.82 | 4.671131 | True |
| 2 | session_new_york | True | 86 | 0.455026 | 183.93 | 0.775 | 0.55814 | 1.747744 | -42.84 | 126.62 | 2.174147 | True |
| 3 | prior_range_lt_q50 | True | 94 | 0.497354 | 112.79 | 1.065 | 0.606383 | 1.657323 | -34.68 | 111.8 | 3.846232 | True |
| 4 | session_london_or_ny | True | 122 | 0.645503 | 138.04 | 0.355 | 0.557377 | 1.380317 | -97.97 | 66.48 | 1.347372 | True |
| 5 | close_below_prior_mid | True | 184 | 0.973545 | 170.81 | 0.985 | 0.586957 | 1.310541 | -130.6 | 44.26 | 1.134701 | True |
| 6 | sweep_depth_q50_to_q75 | True | 47 | 0.248677 | 166.35 | 2.14 | 0.595745 | 2.583984 | -20.81 | 151.44 | 6.565601 | False |
| 7 | deep_sweep_h4_slope_positive | True | 37 | 0.195767 | 139.81 | 1.84 | 0.621622 | 2.360681 | -43.41 | 26.14 | 1.372365 | False |
| 8 | h4_slope_positive | True | 77 | 0.407407 | 175.92 | 0.98 | 0.623377 | 2.082518 | -43.41 | 98.32 | 2.128817 | False |
| 9 | fast_reclaim_le_1bar | True | 47 | 0.248677 | 105.8 | 1.47 | 0.531915 | 1.670809 | -47.67 | 4.1 | 1.036778 | False |
| 10 | h4_up_and_slope_positive | True | 33 | 0.174603 | 42.46 | 0.4 | 0.606061 | 1.607613 | -20.74 | 35.94 | 2.058928 | False |
| 11 | h4_up_context | True | 38 | 0.201058 | 42.34 | 0.815 | 0.631579 | 1.523297 | -27.18 | 52.06 | 2.533883 | False |
| 12 | atr_low_lt_40 | True | 59 | 0.312169 | 68.85 | 1.03 | 0.59322 | 1.349315 | -80.32 | -27.14 | 0.814579 | False |
| 13 | deep_sweep_london_or_ny | True | 66 | 0.349206 | 86.88 | 1.515 | 0.560606 | 1.32046 | -97.97 | 19.86 | 1.122479 | False |
| 14 | atr_high_gt_85 | True | 66 | 0.349206 | 58.54 | 1.345 | 0.606061 | 1.300822 | -50.28 | -25.36 | 0.788137 | False |
| 15 | atr_mid_40_85 | True | 64 | 0.338624 | 48.97 | 0.11 | 0.546875 | 1.281955 | -52.83 | 67.57 | 2.17126 | False |
| 16 | not_h4_up_context | True | 151 | 0.798942 | 134.02 | 0.98 | 0.569536 | 1.276632 | -152.83 | 7.64 | 1.02593 | False |
| 17 | slow_reclaim_gt_1bar | True | 142 | 0.751323 | 70.56 | 0.97 | 0.598592 | 1.173085 | -105.16 | 41.05 | 1.187221 | False |
| 18 | prior_range_ge_q50 | True | 95 | 0.502646 | 63.57 | 0.6 | 0.557895 | 1.161431 | -130.6 | -32.28 | 0.865259 | False |
| 19 | lower_wick_ratio_ge_q50 | True | 95 | 0.502646 | 45.94 | 0.15 | 0.526316 | 1.125547 | -109.51 | 20.38 | 1.091831 | False |
| 20 | sweep_depth_ge_q50 | True | 95 | 0.502646 | 49.22 | 0.98 | 0.547368 | 1.112408 | -130.6 | -80.76 | 0.698454 | False |

## Year distribution - branch net x1
| Year | Events | Total | Avg | Median | WR | PF | DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2022 | 30 | -20.39 | -0.679667 | -1.11 | 0.433333 | 0.744005 | -41.37 |
| 2023 | 38 | 36.2 | 0.952632 | 0.515 | 0.631579 | 1.677649 | -18.09 |
| 2024 | 32 | 38.4 | 1.2 | 1.24 | 0.5625 | 1.766926 | -18.93 |
| 2025 | 54 | 174.45 | 3.230556 | 1.98 | 0.703704 | 2.74015 | -20.57 |
| 2026 | 35 | -52.3 | -1.494286 | -1.42 | 0.485714 | 0.814532 | -130.6 |

## Good years 2023-2025 vs failed 2026 feature deltas
| Feature | Median 2023-2025 | Median 2026 | Delta good minus 2026 |
|---|---:|---:|---:|
| h4_slope3 | -1.2905 | -4.1415 | 2.851 |
| ret_usd | 1.59 | -1.07 | 2.66 |
| net_x1 | 1.24 | -1.42 | 2.66 |
| bars_since_first_breach | 10.5 | 8.0 | 2.5 |
| atr_pct_rank_252 | 0.644841 | 0.444444 | 0.200397 |
| close_position_in_range | 0.841778 | 0.828244 | 0.013534 |
| lower_wick_to_range | 0.148474 | 0.17394 | -0.025467 |
| reclaim_above_ref | 1.28 | 5.17 | -3.89 |
| sweep_depth | 3.04 | 8.61 | -5.57 |
| prior_range | 27.405 | 97.72 | -70.315 |

## Interpretation
- `REGIME_CONDITION_CANDIDATE_FOUND` permits exact replay/robustness for the top pre-trade regime condition only.
- `CURRENT_REGIME_FAILURE_NOT_EXPLAINED` means the 2026 failure is visible but not explained by the tested pre-trade conditions.
- Retrospective year-based separation is diagnostic only and cannot be traded.
- No EA/paper/live/order authorization is granted.

## Output files
- features_csv: `data/reports/stage15a_regime_conditional_sweep_discovery/stage15a_filtered_branch_features.csv`
- regime_csv: `data/reports/stage15a_regime_conditional_sweep_discovery/stage15a_regime_summary.csv`
- goodbad_csv: `data/reports/stage15a_regime_conditional_sweep_discovery/stage15a_good_years_vs_2026_feature_compare.csv`
- year_csv: `data/reports/stage15a_regime_conditional_sweep_discovery/stage15a_by_year.csv`
- quarter_csv: `data/reports/stage15a_regime_conditional_sweep_discovery/stage15a_by_quarter.csv`
- json: `data/reports/stage15a_regime_conditional_sweep_discovery/stage15a_regime_conditional_sweep_discovery.json`
- md: `data/reports/stage15a_regime_conditional_sweep_discovery/stage15a_regime_conditional_sweep_discovery.md`
