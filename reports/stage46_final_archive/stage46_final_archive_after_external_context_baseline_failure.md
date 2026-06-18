# Stage46_FINAL_ARCHIVE_AFTER_EXTERNAL_CONTEXT_BASELINE_FAILURE

## Decision

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
status = STAGE46_FINAL_ARCHIVE_COMPLETE_NO_PROMOTION
recommended_next_stage = NEW_SESSION_OR_NEW_STRUCTURAL_THESIS_DECISION
```

Stage46 final archive closes the external-context baseline branch after the predefined Stage46A scan produced no strict or soft survivors and Stage46C recommended archive. This step does not create signals, shortlist candidates, or authorize promotion.

## Stage chain references

| stage_file | exists | status | next_allowed_step |
| :-- | :-- | :-- | :-- |
| reports/stage45b3/stage45b3_external_context_baseline_design_precheck_summary.json | True | EXTERNAL_CONTEXT_BASELINE_DESIGN_PRECHECK_READY_NO_PROMOTION | Stage46_EXTERNAL_CONTEXT_BASELINE_SCAN_DESIGN |
| reports/stage46/stage46_external_context_baseline_scan_design_summary.json | True | EXTERNAL_CONTEXT_BASELINE_SCAN_DESIGN_READY_NO_PROMOTION | Stage46A_EXTERNAL_CONTEXT_BASELINE_SCAN_IMPLEMENTATION |
| reports/stage46a/stage46a_external_context_baseline_scan_implementation_summary.json | True | EXTERNAL_CONTEXT_BASELINE_SCAN_IMPLEMENTED_NO_SURVIVORS_NO_PROMOTION | Stage46C_EXTERNAL_CONTEXT_FAILURE_ANALYSIS_OR_ARCHIVE |
| reports/stage46c/stage46c_external_context_failure_analysis_or_archive_summary.json | True | EXTERNAL_CONTEXT_BASELINE_FAILURE_ANALYSIS_COMPLETE_ARCHIVE_RECOMMENDED_NO_PROMOTION | Stage46_FINAL_ARCHIVE_AFTER_EXTERNAL_CONTEXT_BASELINE_FAILURE |

## Stage46A scan recap

```json
{
  "candidate_rows": 132,
  "strict_count": 0,
  "soft_count": 0,
  "classification_counts": {
    "FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY": 132
  },
  "event_sample_rows_written": 10000
}
```

## Triggered failure buckets

- `no_survivors`
- `no_positive_net_edge`
- `cost_overwhelms_gross_edge`
- `oos_negative`
- `quarter_stability_negative`
- `bootstrap_floor_negative`
- `benchmark_residual_too_small`

## Family summary

| family_id | candidates | best_candidate_id | best_mean_net_bps | best_oos_mean_net_bps | best_residual_bps |
| :-- | --: | :-- | --: | --: | --: |
| EXTCTX_A_DXY_YIELD_TREND_FILTER | 72 | EXTCTX_A_LONG_H8_Q0.75_avoid_exclude | -10.820 | -8.863 | 0.373 |
| EXTCTX_C_REFERENCE_FEED_SANITY | 12 | EXTCTX_C_LONG_H4_lagged_reference_sign_exclude | -11.531 | -10.077 | -0.044 |
| EXTCTX_D_COMPOSITE_CONTEXT_SCORE | 48 | EXTCTX_D_LONG_H4_T2_REAL1_exclude | -11.482 | -10.043 | 0.005 |

## Top diagnostic candidates

| candidate_id | family_id | mean_gross | mean_cost | mean_net | oos_mean | residual |
| :-- | :-- | --: | --: | --: | --: | --: |
| EXTCTX_A_LONG_H8_Q0.75_avoid_exclude | EXTCTX_A_DXY_YIELD_TREND_FILTER | 0.900 | 11.720 | -10.820 | -8.863 | 0.373 |
| EXTCTX_A_LONG_H8_Q0.75_avoid_tag_only | EXTCTX_A_DXY_YIELD_TREND_FILTER | 0.900 | 11.720 | -10.820 | -8.863 | 0.373 |
| EXTCTX_A_LONG_H4_Q0.75_avoid_exclude | EXTCTX_A_DXY_YIELD_TREND_FILTER | 0.464 | 11.470 | -11.006 | -9.687 | 0.481 |
| EXTCTX_A_LONG_H4_Q0.75_avoid_tag_only | EXTCTX_A_DXY_YIELD_TREND_FILTER | 0.464 | 11.470 | -11.006 | -9.687 | 0.481 |
| EXTCTX_A_LONG_H4_Q0.75_confirm_exclude | EXTCTX_A_DXY_YIELD_TREND_FILTER | -0.018 | 11.208 | -11.225 | -10.319 | 0.262 |
| EXTCTX_A_LONG_H4_Q0.75_confirm_tag_only | EXTCTX_A_DXY_YIELD_TREND_FILTER | -0.018 | 11.208 | -11.225 | -10.319 | 0.262 |
| EXTCTX_A_LONG_H4_Q0.50_avoid_exclude | EXTCTX_A_DXY_YIELD_TREND_FILTER | 0.332 | 11.631 | -11.299 | -9.919 | 0.188 |
| EXTCTX_A_LONG_H4_Q0.50_avoid_tag_only | EXTCTX_A_DXY_YIELD_TREND_FILTER | 0.332 | 11.631 | -11.299 | -9.919 | 0.188 |
| EXTCTX_A_LONG_H4_Q0.25_avoid_exclude | EXTCTX_A_DXY_YIELD_TREND_FILTER | 0.165 | 11.495 | -11.330 | -9.898 | 0.157 |
| EXTCTX_A_LONG_H4_Q0.25_avoid_tag_only | EXTCTX_A_DXY_YIELD_TREND_FILTER | 0.165 | 11.495 | -11.330 | -9.898 | 0.157 |

## Archive interpretation

The external-context branch was a fresh predefined pass. It did not overcome observed costs, did not produce positive OOS net evidence, did not pass worst-quarter or bootstrap lower-tail checks, and did not produce enough residual edge over benchmark. Therefore there is no Stage46B audit target.

## Not allowed

- `candidate_rescue_from_stage41_42_43`
- `post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets`
- `EA_paper_live_live_from_archived_rows`
- `ML_before_robust_cost_aware_baseline`
- `continuing_external_context_branch_after_archive_without_new_structural_thesis`

## Next valid action

Move to a new session/transfer package or define a genuinely new structural thesis. Do not continue this external-context branch by tuning bad buckets, event windows, archived rows, or post-hoc filters.
