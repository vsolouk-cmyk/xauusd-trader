# Stage64N1B - A2 Non-Parametric Pass-Flag Reconciliation

Purpose: reconcile the Stage64N1 A2 pass/fail flag against the Stage64N2 consistency review and the underlying predeclared non-parametric diagnostics.

This stage does not run a new validation scan, does not tune rules, does not change hypotheses, does not use event-calendar historical filters, and does not authorize any order path.

Inputs:

- `reports/stage64n1_corrected_survivor_robustness_audit/stage64n1_corrected_survivor_robustness_audit_summary.json`
- `reports/stage64n2_robustness_downgrade_or_reconciliation_decision/stage64n2_robustness_downgrade_or_reconciliation_decision_summary.json`

The reconciliation checks are:

- sign-test p-value must be at or below the configured threshold.
- bootstrap probability of non-positive excess must be at or below the configured threshold.
- 5th percentile bootstrap excess must be non-negative.
- bootstrap iteration count must be sufficient.
- active days must be sufficient.

If A2 is reconciled as pass and A1/A3/A4/A5 remain pass, the survivor remains research-only and may continue only to a no-order replication/alignment decision step.
