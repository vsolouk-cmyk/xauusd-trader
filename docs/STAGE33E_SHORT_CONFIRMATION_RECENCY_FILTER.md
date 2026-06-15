# Stage33E — Short Confirmation Shadow & Recency Filter Diagnostics

Purpose: keep the repaired `handoff_align_follow_h13/h14` family alive only as a short confirmation shadow after Stage33D blocks pre-paper planning due to recent degradation.

This stage does **not** authorize EA, paper-live, or orders.

## Inputs

- `data/reports/stage33d_strict_cost_aware_pre_paper_gate/stage33d_summary.json`
- `data/reports/stage33c_handoff_repaired_family_gate/stage33c_summary.json`
- `data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_signal_ledger.csv`

## Command

```bash
python3 -m app.stage33e_short_confirmation_recency_filter
```

## Outputs

- `data/reports/stage33e_short_confirmation_recency_filter/stage33e_short_confirmation_recency_filter.md`
- `data/reports/stage33e_short_confirmation_recency_filter/stage33e_summary.json`
- `data/reports/stage33e_short_confirmation_recency_filter/short_confirmation_plan.csv`
- `data/reports/stage33e_short_confirmation_recency_filter/short_confirmation_batch_summary.csv`
- `data/reports/stage33e_short_confirmation_recency_filter/short_confirmation_cost_summary.csv`
- `data/reports/stage33e_short_confirmation_recency_filter/recency_filter_diagnostics.csv`
- `data/reports/stage33e_short_confirmation_recency_filter/repaired_family_effective_ledger.csv`

## Decision logic

If Stage33D shows strong core/cost metrics but blocks due to recent degradation, Stage33E keeps the family in short confirmation shadow:

- collect at least 5 new effective h13/h14 events;
- target 10 new effective events;
- require the next confirmation batch to recover PF, average net, win-rate, and drawdown;
- if the next batch remains weak, kill/repair the family and return to intake expansion.

## Commercial status

Research only. No EA change. No paper-live. No order authorization.
