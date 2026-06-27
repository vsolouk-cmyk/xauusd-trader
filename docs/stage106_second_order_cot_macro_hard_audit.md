# Stage106 Second-Order COT/Macro Hard Audit

Purpose: hard-audit the Stage105 second-order COT/macro shortlist before any portfolio review or observer expansion.

This stage is deliberately stricter than Stage105 discovery. It recomputes active-day contribution against the current 6-rule unified observer portfolio:

- K06
- K03
- K07
- S83_14
- S83_13
- C96_07

No order, broker connection, MT5/EA change, paper-live, or live action is allowed.

## Inputs

- `reports/stage105_second_order_cot_macro_thesis_discovery/stage105_second_order_cot_macro_thesis_discovery_summary.json`
- `reports/stage105_second_order_cot_macro_thesis_discovery/stage105_second_order_cot_macro_shortlist.csv`
- `data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv`
- `data/external_frontiers/cot_positioning_normalized.csv`

## Outputs

- `stage106_second_order_cot_macro_hard_audit_summary.json`
- `stage106_second_order_cot_macro_hard_audit_report.md`
- `stage106_second_order_cot_macro_hard_audit_metrics.csv`
- `stage106_selected_for_stage107.csv`

If a candidate survives, Stage107 should be a portfolio increment review, not an observer expansion.
