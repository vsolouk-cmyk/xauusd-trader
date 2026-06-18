# Stage45B3_EXTERNAL_CONTEXT_BASELINE_DESIGN_PRECHECK

## Decision

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
status = EXTERNAL_CONTEXT_BASELINE_DESIGN_PRECHECK_READY_NO_PROMOTION
recommended_next_stage = Stage46_EXTERNAL_CONTEXT_BASELINE_SCAN_DESIGN
```

Stage45B3 is a baseline-design precheck only. It does not create trading signals, shortlist candidates, or promote archived rows.

## Blockers and warnings

```json
{
  "blockers": [],
  "warnings": [
    "news_calendar_mixed_semantics_review_required"
  ]
}
```

## Precheck matrix

| area | metric | value | rule | ok | severity |
| :-- | :-- | :-- | :-- | :-- | :-- |
| stage_chain | stage45b2a_status | EXTERNAL_CONTEXT_ALIGNMENT_REPAIR_READY_NO_PROMOTION | == EXTERNAL_CONTEXT_ALIGNMENT_REPAIR_READY_NO_PROMOTION | True | blocker |
| p0 | required_external_context_schema_ready | ['cme_gc_reference', 'dxy', 'news_calendar', 'us10y_yield'] | superset ['cme_gc_reference', 'dxy', 'news_calendar', 'us10y_yield'] | True | blocker |
| daily_context | dxy_safe_lag_coverage_pct | 0.9984423676012462 | >= 0.95 | True | blocker |
| daily_context | us10y_yield_safe_lag_coverage_pct | 0.9984423676012462 | >= 0.95 | True | blocker |
| daily_context | real_yield_optional_safe_lag_coverage_pct | 0.9984423676012462 | >= 0.95 | True | warning |
| cme_reference | cme_overlap_pct_of_bar_days | 0.807632398753894 | >= 0.7 | True | blocker |
| cme_reference | cme_return_corr | 0.8445723130581777 | >= 0.65 | True | blocker |
| cme_reference | cme_return_sign_agreement_pct | 0.8658301158301158 | >= 0.6 | True | blocker |
| news_blackout | selected_blackout_variant | macro_usd_or_unknown | in macro_usd_or_unknown/macro_semantic_only | True | warning |
| news_blackout | selected_blackout_coverage_pct | 0.0792444362053994 | >= 0.001 | True | blocker |
| news_blackout | selected_blackout_coverage_pct | 0.0792444362053994 | <= 0.25 | True | blocker |
| news_semantics | mixed_numeric_backfill_or_shock_semantics | True | == False | False | warning |

## Feature contract

| feature_group | readiness | alignment_rule | reason |
| :-- | :-- | :-- | :-- |
| daily_macro_context | READY | daily_safe_lag_1d_forward_fill | safe_lag_coverage=0.9984423676012462 |
| nominal_yield_context | READY | daily_safe_lag_1d_forward_fill | safe_lag_coverage=0.9984423676012462 |
| real_yield_context_optional | READY_OPTIONAL | daily_safe_lag_1d_forward_fill | safe_lag_coverage=0.9984423676012462 |
| reference_feed_sanity | READY_REFERENCE_ONLY | daily_reference_overlap_only_not_execution_grade | return_corr=0.8445723130581777; source must stay reference_only |
| news_blackout | READY | interval_overlap_utc_predefined_window | selected_variant=macro_usd_or_unknown; selected_blackout_pct=0.0792444362053994; max_allowed=0.25 |

## Interpretation

The external context passes the design precheck. The next valid step is a predefined external-context baseline scan design, not candidate rescue.

## Not allowed

- `candidate_rescue_from_stage41_42_43`
- `post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets`
- `EA_paper_live_live_from_archived_rows`
- `ML_before_robust_cost_aware_baseline`
- `new_blind_megascan_before_external_context_baseline_design_precheck_is_clean`

## Anti-overfit note

Do not use this precheck to rescue Stage41/42/43 rows. If the precheck is blocked, repair the context design first. If it passes, the next step must still be a predefined baseline design.
