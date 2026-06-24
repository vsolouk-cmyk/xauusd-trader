# Stage64D Macro-Regime Data Contract and Loader Audit

Stage64D is a report-only gate between the Stage64C thesis specification and any historical regime validation. It audits whether the data required by the Daily/Weekly Macro-Regime Gold Thesis is present, timestamped, sufficiently long, and enforceable under a no-lookahead lag policy.

## Scope

- Reads the Stage64C feature contract.
- Audits broker OHLCV SQLite coverage for deriving D1/W1 gold features.
- Audits configured exogenous CSV files under `data/exogenous`.
- Checks feature-level data availability, minimum-history coverage, and lag-policy enforceability.
- Checks whether all validation splits can be supported.
- Produces report-only outputs.

## Non-scope

- No historical validation scan.
- No parameter search.
- No intraday rescue filtering.
- No paper order, paper-live, live, or EA promotion.
- No DB mutation.

## Expected outputs

- `stage64d_macro_regime_data_contract_loader_audit_summary.json`
- `stage64d_macro_regime_data_contract_loader_audit_report.md`
- `stage64d_macro_regime_data_inventory.csv/json`
- `stage64d_feature_lag_policy_audit.csv/json`
- `stage64d_validation_split_coverage_audit.csv/json`

## Interpretation

If Stage64D blocks validation, the next step is data-gap remediation, not a validation scan. Typical blockers are insufficient pre-2023 broker history, missing ETF/central-bank demand files, and macro data without explicit release-lag or availability timestamps.
