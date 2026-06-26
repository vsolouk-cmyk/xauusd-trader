# Stage67 Manual Data Refresh + Multi-Readiness Runner

Stage67 is local-only. It does not download data from the internet.

The operator manually refreshes CSV files in `~/Downloads`. Stage67 then imports/copies those files into the local repo, rebuilds the local gold D1 and macro feature CSVs when possible, and runs Stage66J2 only if fresh data was imported.

## Required operating model

1. Manually download/update CSV files into `~/Downloads`.
2. Run Stage67 locally.
3. Stage67 imports/merges the data into local datasets.
4. Stage67 rebuilds `stage64k_full_scope_lag_safe_feature_dataset.csv`.
5. If new data was actually imported, Stage67 runs Stage66J2.
6. If no new data was imported, Stage67 writes a stale/unchanged report and does not count the run as a forward update.

## Minimum manual files

For the four readiness paths, use these files when available:

- `amarkets_xauusd_5m.csv` or a gold D1 CSV.
- `dxy.csv`
- `real_yield.csv`
- `vix.csv`
- `etf_flow.csv`
- `central_bank_demand.csv`

If only the gold file is refreshed, gold technical features may update but macro-driver conditions can remain stale. Stage67 reports coverage and issues; it does not invent signal data.

## Hard blocks

Stage67 cannot authorize orders, broker connections, EA promotion, paper-live, or live trading. It only refreshes local data and runs readiness checks.
