# Stage64L - Full-Scope Walk-Forward Validation Design (No Scan)

Stage64L predeclares the validation protocol for the Stage64K full-scope lag-safe feature dataset. It inspects dataset schema, split coverage, required feature availability, and forbidden target/signal/outcome columns.

It does not run validation. It does not compute forward returns. It does not generate signals. It does not connect to a broker and does not authorize paper/live/order execution.

## Inputs

- `reports/stage64k_full_scope_lag_safe_feature_dataset_preflight/stage64k_full_scope_lag_safe_feature_dataset_preflight_summary.json`
- `data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv`

## Design principles

- Primary benchmark remains gold trend-only (`H64L_B1_GOLD_TREND_ONLY_REFERENCE`).
- Reduced-scope P0 logic is retained only as a reference control after Stage64H failure.
- Candidate hypotheses must include ETF and/or central-bank full-scope P1 features.
- Historical event-calendar filtering is forbidden because the archive is not available.
- Broker/spot alignment remains required before commercialization claims.

## Next stage

Only if Stage64L passes, Stage64M may run the predeclared full-scope walk-forward validation. Stage64M still must not authorize orders.
