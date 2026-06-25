# Stage64K - Full-Scope Lag-Safe Feature Dataset Preflight

Purpose: build a feature-only, lag-safe full-scope research dataset after Stage64J5 accepted event-calendar forward-only governance and after Stage64J4 mapped WGC ETF/central-bank sources.

This stage does not run validation, does not create labels/targets/signals, does not connect to a broker, and does not authorize paper/live/EA promotion.

Inputs:

- `data/macro_regime/normalized/stage64f_reduced_scope_lag_safe_feature_dataset.csv`
- `data/macro_regime/raw/gold_etf_holdings_or_flows.csv`
- `data/macro_regime/raw/central_bank_gold_demand_monthly_quarterly.csv`
- `reports/stage64j5_event_calendar_forward_governance_acceptance/stage64j5_event_calendar_forward_governance_acceptance_summary.json`

Outputs:

- `data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv`
- `data/macro_regime/manifests/stage64k_full_scope_lag_safe_feature_dataset_manifest.json`
- Stage64K report and summary under `reports/stage64k_full_scope_lag_safe_feature_dataset_preflight/`

Lag policy:

- ETF and central-bank rows are joined as-of using `available_after_utc <= sample_available_after_utc`.
- Event calendar remains forward-only governance only; it is not a historical feature.
- Broker/spot alignment remains required before commercialization and does not authorize broker connection.
