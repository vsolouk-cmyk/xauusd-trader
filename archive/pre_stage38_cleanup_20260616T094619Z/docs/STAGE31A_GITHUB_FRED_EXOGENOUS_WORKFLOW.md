# Stage31A GitHub FRED Exogenous Workflow Hotfix 2

This hotfix makes Stage31A robust when GitHub refreshes FRED data before a Stage30A ML dataset is available in the runner. It also updates the FRED workflow to attempt Stage30A dataset construction before Stage31A.

## Changes

- `app/stage31a_exogenous_feature_ingestion.py`
  - Skips numeric asof joins when the base dataset is empty or has no normalized entry timestamp.
  - Skips calendar proximity computation when the base dataset is empty or has no normalized entry timestamp.
  - Accepts additional time column aliases such as `entry_time`, `entry_ts`, `signal_time`, `opened_ts`, `ts_utc`, and `time_utc`.
  - Reports `time_column_used` in the dataset diagnostics.
- `.github/workflows/xauusd_fred_exogenous.yml`
  - Runs Stage30A first when available.
  - Then runs Stage31A.
  - Still uploads FRED CSVs and Stage31A reports as artifacts.
- `tools/download_fred_exogenous.py`
  - Carries forward the partial-safe FRED downloader.

## Scope

Research/shadow only. No EA, paper/live, or order changes.
