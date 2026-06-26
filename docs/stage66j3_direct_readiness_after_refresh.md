# Stage66J3 Direct Readiness After Refresh

Stage66J3 is a no-order direct readiness collector for the post-Stage67D6 state.

It exists because Stage67D6 successfully rebuilds the macro dataset from the real downloaded source formats, but the older Stage66J/Stage66K child runners can still return non-zero codes when the observed state is simply WAIT / BLOCKED / no-ticket. Stage66J3 does not invoke those children. It reads the lag-safe macro feature dataset directly and evaluates the locked rule conditions.

## Scope

- Reads `data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv`.
- Evaluates H64L v2, D3 H60, D1 backup, and D4 backup.
- Writes summary/report/ledger.
- Does not generate orders.
- Does not connect to broker.
- Does not invoke EA, paper-live, or live paths.

## Known data limitation

The current World Gold Council central-bank workbook is a latest holdings cross-section, not a 3-month demand time series. Therefore `central_bank_demand_tonnes_3m` remains unavailable unless a true historical demand source is provided. Stage66J3 treats this as nonfatal data-wait for H64L, not as a pipeline failure.
