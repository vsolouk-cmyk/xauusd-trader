# Stage32D — Dense Forward Review / Tightening Plan

Stage32D reviews the Stage32C dense forward-shadow ledger and converts any research review candidate into a concrete tightening plan.

It is still research/shadow only:

```text
NO_EA_CHANGE = TRUE
NO_PAPER_LIVE = TRUE
NO_ORDER_AUTHORIZATION = TRUE
```

## Why it exists

Stage32C can identify candidates with enough dense forward samples for research review. Stage32D prevents premature commercial transition by checking sample count, PF, average net, win rate, tail stability, drawdown, direction split, and family-level context.

## Default inputs

```text
data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_candidate_summary.csv
data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_family_summary.csv
data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_signal_ledger.csv
data/reports/stage32c_dense_forward_shadow_tracker/stage32c_summary.json
```

## Default outputs

```text
data/reports/stage32d_dense_forward_review/stage32d_dense_forward_review.md
data/reports/stage32d_dense_forward_review/dense_review_candidate_diagnostics.csv
data/reports/stage32d_dense_forward_review/dense_variant_tightening_plan.csv
data/reports/stage32d_dense_forward_review/dense_family_action_plan.csv
data/reports/stage32d_dense_forward_review/stage32d_summary.json
```

## Interpretation

A candidate that passes Stage32D is not a live candidate. It only becomes eligible for extended dense shadow review. The default extended threshold is 40 resolved forward samples.
