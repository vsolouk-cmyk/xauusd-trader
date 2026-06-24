# Stage38E Macro Context Diagnostic — Preliminary Review

## Status

```text
STAGE38E_MACRO_CONTEXT_DIAGNOSTIC_PRELIM = REVIEW_REQUIRED
PROMOTE_TO_BASELINE = NO
PROMOTE_TO_STAGE39 = NO
EA / paper-live / live = NO-GO
```

The first macro-context diagnostic completed successfully and produced event-level forward-return rows. However, the resulting summary shows a methodological warning: nearly every group reports one positive year and max positive year share of 1.0. That suggests the concentration calculation is not using the explicit `event_year` / `event_month` fields correctly.

Therefore, the current macro-context output must not be used for promotion decisions until a corrected era/year recheck is run.

## Observed issue

The first diagnostic output reported:

```text
status = PASS
joined_rows_loaded = 25,643
event_count = 1,073
returns_written = 3,219
summary_rows_written = 183
lookahead_violation_count = 0
```

But the summary rows repeatedly show:

```text
positive_year_count = 1
max_positive_year_share = 1.0
YEAR_CONCENTRATED_GT_55PCT
```

This is unlikely to be a valid year-split result for a dataset spanning 2022-05 to 2026-06. The likely cause is not the forward returns themselves, but the summary contribution logic.

## Decision

```text
MACRO_DATA_FOUNDATION = KEEP
MACRO_H1_JOIN = KEEP
MACRO_FORWARD_RETURNS = KEEP
MACRO_SUMMARY_DECISION = HOLD
NEXT_REQUIRED_STEP = corrected era/year recheck
```

No additional strategy, filter, baseline, ML, paper-live, or Stage39 work should be started from this preliminary diagnostic.

## Next artifact

```text
app/stage38e_macro_context_era_recheck.py
```

This script reads `stage38e_macro_forward_returns` and rebuilds the summary using explicit `event_year` and `event_month` fields.
