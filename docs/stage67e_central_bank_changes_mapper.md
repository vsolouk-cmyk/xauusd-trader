# Stage67E Central Bank Changes Mapper

Stage67E adds the WGC central-bank changes workbook into the local macro dataset.

It is local-only and does not download anything. It reads `Changes_latest*.xlsx` from `~/Downloads`, parses the `Monthly` sheet, sums country-level monthly reserve changes into a global monthly net-change series, computes a rolling 3-month sum, and updates:

- `data/exogenous/central_bank_demand.csv`
- `data/exogenous/wgc_raw_extracted/central_bank_changes_monthly_global.csv`
- `data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv`

Important design choice: WGC month headers are treated as month starts, but the feature is aligned to month-end before daily forward-fill to avoid assuming the full-month change was known at the start of the month.

Stage67E cannot authorize any order, paper order, broker, EA, paper-live, or live path.
