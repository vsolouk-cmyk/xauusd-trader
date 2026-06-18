# Stage46C_EXTERNAL_CONTEXT_FAILURE_ANALYSIS_OR_ARCHIVE

## Decision

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
status = EXTERNAL_CONTEXT_BASELINE_FAILURE_ANALYSIS_COMPLETE_ARCHIVE_RECOMMENDED_NO_PROMOTION
recommended_next_stage = Stage46_FINAL_ARCHIVE_AFTER_EXTERNAL_CONTEXT_BASELINE_FAILURE
```

Stage46C is failure analysis only. It does not create signals, rescue archived candidates, or authorize promotion.

## Failure buckets

| bucket | triggered | evidence | interpretation |
| :-- | :-- | :-- | :-- |
| no_survivors | True | strict_count=0; soft_count=0; candidate_rows=132 | No Stage46B audit is justified because there are no strict or soft survivors. |
| no_positive_net_edge | True | positive_mean_net_candidates=0; best_mean_net=-10.819902352342146 | The external-context rules do not overcome observed transaction costs. |
| cost_overwhelms_gross_edge | True | median_mean_gross=-0.5240225817385625; median_mean_cost=14.497748675966793; median_gross_minus_cost=-15.021771257705355 | The raw directional context is too weak relative to cost assumptions. |
| oos_negative | True | positive_oos_candidates=0; best_oos_mean_net=-8.862651965584801 | No candidate shows positive out-of-sample net performance. |
| quarter_stability_negative | True | positive_worst_quarter_candidates=0; best_worst_quarter=-17.840407295159622 | Quarter-level stability remains negative even for the best candidates. |
| bootstrap_floor_negative | True | positive_bootstrap_p05_candidates=0; best_bootstrap_p05=-11.540569046215914 | Bootstrap lower-tail evidence does not support promotion. |
| benchmark_residual_too_small | True | residual_ge_1bps_candidates=0; best_residual=0.4808644418521322 | Residual edge versus simple benchmark is too small to justify continuing this scan branch. |

## Family summary

| family_id | candidate_count | best_candidate_id | best_mean_net_bps | best_oos_mean_net_bps | best_residual_vs_benchmark_bps | best_bootstrap_mean_p05_bps |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| EXTCTX_A_DXY_YIELD_TREND_FILTER | 72 | EXTCTX_A_LONG_H8_Q0.75_avoid_exclude | -10.820 | -8.863 | 0.373 | -11.626 |
| EXTCTX_C_REFERENCE_FEED_SANITY | 12 | EXTCTX_C_LONG_H4_lagged_reference_sign_exclude | -11.531 | -10.077 | -0.044 | -12.159 |
| EXTCTX_D_COMPOSITE_CONTEXT_SCORE | 48 | EXTCTX_D_LONG_H4_T2_REAL1_exclude | -11.482 | -10.043 | 0.005 | -12.318 |

## Top diagnostic rows

| candidate_id | family_id | direction | hold_bars | mean_gross_bps | mean_cost_bps | mean_net_bps | oos_mean_net_bps | residual_vs_benchmark_bps | classification |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| EXTCTX_A_LONG_H8_Q0.75_avoid_exclude | EXTCTX_A_DXY_YIELD_TREND_FILTER | long | 8 | 0.8999311286625197 | 11.719833481004665 | -10.819902352342146 | -8.862651965584801 | 0.37336840908258395 | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY |
| EXTCTX_A_LONG_H8_Q0.75_avoid_tag_only | EXTCTX_A_DXY_YIELD_TREND_FILTER | long | 8 | 0.8999311286625197 | 11.719833481004665 | -10.819902352342146 | -8.862651965584801 | 0.37336840908258395 | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY |
| EXTCTX_A_LONG_H4_Q0.75_avoid_exclude | EXTCTX_A_DXY_YIELD_TREND_FILTER | long | 4 | 0.46352532740820385 | 11.469991027561472 | -11.006465700153269 | -9.687233309377131 | 0.4808644418521322 | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY |
| EXTCTX_A_LONG_H4_Q0.75_avoid_tag_only | EXTCTX_A_DXY_YIELD_TREND_FILTER | long | 4 | 0.46352532740820385 | 11.469991027561472 | -11.006465700153269 | -9.687233309377131 | 0.4808644418521322 | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY |
| EXTCTX_A_LONG_H4_Q0.75_confirm_exclude | EXTCTX_A_DXY_YIELD_TREND_FILTER | long | 4 | -0.017746116546051845 | 11.207748489302112 | -11.225494605848164 | -10.319418159984716 | 0.2618355361572373 | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY |
| EXTCTX_A_LONG_H4_Q0.75_confirm_tag_only | EXTCTX_A_DXY_YIELD_TREND_FILTER | long | 4 | -0.017746116546051845 | 11.207748489302112 | -11.225494605848164 | -10.319418159984716 | 0.2618355361572373 | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY |
| EXTCTX_A_LONG_H4_Q0.50_avoid_exclude | EXTCTX_A_DXY_YIELD_TREND_FILTER | long | 4 | 0.3320500371936321 | 11.631259140203674 | -11.299209103010044 | -9.91850021519331 | 0.18812103899535693 | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY |
| EXTCTX_A_LONG_H4_Q0.50_avoid_tag_only | EXTCTX_A_DXY_YIELD_TREND_FILTER | long | 4 | 0.3320500371936321 | 11.631259140203674 | -11.299209103010044 | -9.91850021519331 | 0.18812103899535693 | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY |
| EXTCTX_A_LONG_H4_Q0.25_avoid_exclude | EXTCTX_A_DXY_YIELD_TREND_FILTER | long | 4 | 0.1653262838928852 | 11.495234073844161 | -11.329907789951275 | -9.898161221516045 | 0.1574223520541267 | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY |
| EXTCTX_A_LONG_H4_Q0.25_avoid_tag_only | EXTCTX_A_DXY_YIELD_TREND_FILTER | long | 4 | 0.1653262838928852 | 11.495234073844161 | -11.329907789951275 | -9.898161221516045 | 0.1574223520541267 | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY |
| EXTCTX_A_LONG_H4_Q0.50_confirm_exclude | EXTCTX_A_DXY_YIELD_TREND_FILTER | long | 4 | -0.04795882876033832 | 11.331902272956421 | -11.37986110171676 | -10.48381065514916 | 0.10746904028864179 | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY |
| EXTCTX_A_LONG_H4_Q0.50_confirm_tag_only | EXTCTX_A_DXY_YIELD_TREND_FILTER | long | 4 | -0.04795882876033832 | 11.331902272956421 | -11.37986110171676 | -10.48381065514916 | 0.10746904028864179 | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY |
| EXTCTX_D_LONG_H4_T2_REAL1_exclude | EXTCTX_D_COMPOSITE_CONTEXT_SCORE | long | 4 | -0.03399077589285186 | 11.448203492397546 | -11.4821942682904 | -10.043389967951427 | 0.005135873715001793 | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY |
| EXTCTX_D_LONG_H4_T2_REAL1_tag_only | EXTCTX_D_COMPOSITE_CONTEXT_SCORE | long | 4 | -0.03399077589285186 | 11.448203492397546 | -11.4821942682904 | -10.043389967951427 | 0.005135873715001793 | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY |
| EXTCTX_C_LONG_H4_lagged_reference_sign_exclude | EXTCTX_C_REFERENCE_FEED_SANITY | long | 4 | 0.13822938810620186 | 11.669499406008967 | -11.531270017902765 | -10.07733827022114 | -0.04393987589736348 | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY |
| EXTCTX_C_LONG_H4_lagged_reference_sign_tag_only | EXTCTX_C_REFERENCE_FEED_SANITY | long | 4 | 0.13822938810620186 | 11.669499406008967 | -11.531270017902765 | -10.07733827022114 | -0.04393987589736348 | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY |
| EXTCTX_A_SHORT_H4_Q0.25_avoid_exclude | EXTCTX_A_DXY_YIELD_TREND_FILTER | short | 4 | -0.4308047042338002 | 11.32413267490877 | -11.754937379142566 | -11.137870974385002 | 0.43812192059900745 | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY |
| EXTCTX_A_SHORT_H4_Q0.25_avoid_tag_only | EXTCTX_A_DXY_YIELD_TREND_FILTER | short | 4 | -0.4308047042338002 | 11.32413267490877 | -11.754937379142566 | -11.137870974385002 | 0.43812192059900745 | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY |
| EXTCTX_D_LONG_H4_T3_REAL0_exclude | EXTCTX_D_COMPOSITE_CONTEXT_SCORE | long | 4 | -0.3328084436707414 | 11.435409746597104 | -11.768218190267845 | -11.821345539348494 | -0.28088804826244385 | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY |
| EXTCTX_D_LONG_H4_T3_REAL0_tag_only | EXTCTX_D_COMPOSITE_CONTEXT_SCORE | long | 4 | -0.3328084436707414 | 11.435409746597104 | -11.768218190267845 | -11.821345539348494 | -0.28088804826244385 | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY |

## Interpretation

The external-context branch was implemented as a fresh predefined scan. It did not produce a strict or soft survivor. The dominant interpretation is that the available context variables may slightly rank or tag regimes, but they do not create enough net edge after observed costs and stability checks.

## Not allowed

- `candidate_rescue_from_stage41_42_43`
- `post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets`
- `EA_paper_live_live_from_archived_rows`
- `ML_before_robust_cost_aware_baseline`
- `continuing_external_context_scan_without_failure_analysis_decision`

## Anti-overfit note

Do not tune event windows, bad hours, bad months, spread buckets, or archived candidate rows after seeing Stage46A failure. The valid next action is final archive/transfer or a genuinely new thesis decision outside this branch.
