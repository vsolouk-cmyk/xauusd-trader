# Stage46A_EXTERNAL_CONTEXT_BASELINE_SCAN_IMPLEMENTATION

## Decision

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
status = EXTERNAL_CONTEXT_BASELINE_SCAN_IMPLEMENTED_NO_SURVIVORS_NO_PROMOTION
recommended_next_stage = Stage46C_EXTERNAL_CONTEXT_FAILURE_ANALYSIS_OR_ARCHIVE
```

Stage46A implements the predefined Stage46 external-context baseline design in a fresh cost-aware scan. It does not rescue Stage41/42/43 rows and does not authorize EA, paper-live, or live trading.

## Scan summary

```json
{
  "candidate_rows": 132,
  "strict_count": 0,
  "soft_count": 0,
  "fail_or_insufficient_count": 132,
  "classification_counts": {
    "FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY": 132
  },
  "event_sample_rows_written": 10000
}
```

## Top candidates by mean net bps

| candidate_id | class | n | mean_net | oos_mean | worst_q | residual |
| :-- | :-- | --: | --: | --: | --: | --: |
| EXTCTX_A_LONG_H8_Q0.75_avoid_exclude | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY | 11077 | -10.820 | -8.863 | -21.448 | 0.373 |
| EXTCTX_A_LONG_H8_Q0.75_avoid_tag_only | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY | 11077 | -10.820 | -8.863 | -21.448 | 0.373 |
| EXTCTX_A_LONG_H4_Q0.75_avoid_exclude | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY | 22115 | -11.006 | -9.687 | -19.260 | 0.481 |
| EXTCTX_A_LONG_H4_Q0.75_avoid_tag_only | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY | 22115 | -11.006 | -9.687 | -19.260 | 0.481 |
| EXTCTX_A_LONG_H4_Q0.75_confirm_exclude | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY | 10372 | -11.225 | -10.319 | -18.662 | 0.262 |
| EXTCTX_A_LONG_H4_Q0.75_confirm_tag_only | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY | 10372 | -11.225 | -10.319 | -18.662 | 0.262 |
| EXTCTX_A_LONG_H4_Q0.50_avoid_exclude | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY | 18751 | -11.299 | -9.919 | -19.221 | 0.188 |
| EXTCTX_A_LONG_H4_Q0.50_avoid_tag_only | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY | 18751 | -11.299 | -9.919 | -19.221 | 0.188 |
| EXTCTX_A_LONG_H4_Q0.25_avoid_exclude | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY | 15984 | -11.330 | -9.898 | -19.336 | 0.157 |
| EXTCTX_A_LONG_H4_Q0.25_avoid_tag_only | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY | 15984 | -11.330 | -9.898 | -19.336 | 0.157 |
| EXTCTX_A_LONG_H4_Q0.50_confirm_exclude | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY | 7363 | -11.380 | -10.484 | -20.028 | 0.107 |
| EXTCTX_A_LONG_H4_Q0.50_confirm_tag_only | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY | 7363 | -11.380 | -10.484 | -20.028 | 0.107 |
| EXTCTX_D_LONG_H4_T2_REAL1_exclude | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY | 9594 | -11.482 | -10.043 | -19.303 | 0.005 |
| EXTCTX_D_LONG_H4_T2_REAL1_tag_only | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY | 9594 | -11.482 | -10.043 | -19.303 | 0.005 |
| EXTCTX_C_LONG_H4_lagged_reference_sign_exclude | FAIL_EXTERNAL_CONTEXT_BASELINE_RESEARCH_ONLY | 13993 | -11.531 | -10.077 | -20.430 | -0.044 |

## Guardrails

- `candidate_rescue_from_stage41_42_43`
- `post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets`
- `EA_paper_live_live_from_archived_rows`
- `ML_before_robust_cost_aware_baseline`
- `running_uncontracted_external_context_scan`

## Anti-overfit note

This implementation is a fresh predefined external-context baseline pass. Any strict or soft row must still pass a separate Stage46B audit before any promotion discussion.
