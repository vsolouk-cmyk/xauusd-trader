# Stage64G Walk-Forward Validation Design

Stage64G is a design-only stage. It predeclares the reduced-scope P0+VIX validation hypotheses, split design, benchmark structure, multiple-testing rule, and kill/pass discipline.

It does not run validation, does not create targets, does not generate signals, and does not authorize any execution path.

## Inputs

- `reports/stage64f_reduced_scope_lag_safe_feature_dataset_preflight/stage64f_reduced_scope_lag_safe_feature_dataset_preflight_summary.json`
- `data/macro_regime/normalized/stage64f_reduced_scope_lag_safe_feature_dataset.csv`

## Outputs

- `stage64g_predeclared_hypotheses.csv/json`
- `stage64g_walk_forward_split_design.csv/json`
- `stage64g_feature_to_rule_contract.csv/json`
- `stage64g_validation_protocol.json`
- `stage64g_walk_forward_validation_design_summary.json`
- `stage64g_walk_forward_validation_design_report.md`

## Safety

- No validation scan in Stage64G.
- No paper-order, paper-live, live, EA promotion, broker connection, or signal generation.
- Reduced scope remains a feasibility/proxy scope, not a full macro-regime validation.
- Gold D1 source is a COMEX continuous futures reference if sourced from `GC=F`; it must not be represented as broker spot XAUUSD.
