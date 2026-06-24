# Stage35C — Forward Confirmation Trigger & Queue Pruner

Purpose: prevent passive waiting after Stage35B by turning the h13/h14 pending-forward state into an explicit trigger and queue-pruning report.

This stage is research-only. It does not authorize EA changes, paper-live, or orders.

Inputs:

- `data/reports/stage35b_strict_variant_backtest_queue_evaluator/stage35b_summary.json`
- `data/reports/stage35b_strict_variant_backtest_queue_evaluator/strict_variant_evaluation.csv`
- `data/reports/stage33e_short_confirmation_recency_filter/stage33e_summary.json`
- `data/reports/stage32c_dense_forward_shadow_tracker/dense_forward_signal_ledger.csv`

Outputs:

- `data/reports/stage35c_forward_confirmation_trigger_queue_pruner/stage35c_forward_confirmation_trigger_queue_pruner.md`
- `data/reports/stage35c_forward_confirmation_trigger_queue_pruner/stage35c_summary.json`
- `data/reports/stage35c_forward_confirmation_trigger_queue_pruner/forward_confirmation_state.csv`
- `data/reports/stage35c_forward_confirmation_trigger_queue_pruner/forward_confirmation_gate_checks.csv`
- `data/reports/stage35c_forward_confirmation_trigger_queue_pruner/queue_pruner.csv`
- `data/reports/stage35c_forward_confirmation_trigger_queue_pruner/rerun_trigger_plan.csv`
- `data/reports/stage35c_forward_confirmation_trigger_queue_pruner/new_forward_events_audit.csv`

Decision rules:

- If new h13/h14 events after the Stage33E anchor are below the minimum, wait with background collection only and do not create another analysis stage.
- If enough new events exist and confirmation gates pass, rerun Stage33D, Stage33E, and Stage35B.
- If enough new events exist and confirmation gates fail, kill or repair the h13/h14 recency-guard fast path.

