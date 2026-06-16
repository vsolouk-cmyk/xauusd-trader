# Stage32E — Extended Dense Shadow Monitor

Stage32E converts the Stage32D tightening plan into an operational extended-shadow monitor.

It is still research/shadow only:

```text
NO_EA_CHANGE = TRUE
NO_PAPER_LIVE = TRUE
NO_ORDER_AUTHORIZATION = TRUE
```

## Purpose

Stage32D found that the leading dense candidate is promising but needs extended shadow before any commercial review. Stage32E keeps that candidate in focus until it reaches the extended threshold, while suppressing weak sibling variants from primary attention.

## Default inputs

```text
data/reports/stage32d_dense_forward_review/dense_variant_tightening_plan.csv
data/reports/stage32d_dense_forward_review/dense_review_candidate_diagnostics.csv
data/reports/stage32d_dense_forward_review/dense_family_action_plan.csv
data/reports/stage32d_dense_forward_review/stage32d_summary.json
data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_signal_ledger.csv
```

## Default outputs

```text
data/reports/stage32e_extended_dense_shadow_monitor/stage32e_extended_dense_shadow_monitor.md
data/reports/stage32e_extended_dense_shadow_monitor/extended_shadow_focus_queue.csv
data/reports/stage32e_extended_dense_shadow_monitor/suppressed_variant_plan.csv
data/reports/stage32e_extended_dense_shadow_monitor/pre_commercial_robustness_queue.csv
data/reports/stage32e_extended_dense_shadow_monitor/stage32e_summary.json
```

## Interpretation

- `extended_shadow_focus_queue.csv` shows the variants that should keep collecting forward samples.
- `suppressed_variant_plan.csv` shows weak siblings that should not dilute primary attention.
- `pre_commercial_robustness_queue.csv` remains empty until a candidate reaches extended sample count and stability thresholds.

The default extended threshold is 40 resolved forward samples.
