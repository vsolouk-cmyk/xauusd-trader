# Stage31A GitHub FRED Exogenous Workflow Hotfix

This workflow downloads FRED exogenous CSVs on GitHub Actions and runs Stage31A.
The downloader is partial-safe: one transient FRED HTTP failure, such as 504, no longer aborts the whole run.

Outputs:

- `data/exogenous/dxy.csv`
- `data/exogenous/us10y.csv`
- `data/exogenous/real_yield.csv`
- `data/exogenous/vix.csv`
- `data/exogenous/spx.csv`
- `data/exogenous/oil.csv`
- `data/exogenous/fred_download_manifest.csv`
- `data/reports/stage31a_exogenous_feature_ingestion/`

Run manually from GitHub Actions. Keep `strict=0` unless you intentionally want the workflow to fail on any missing source.
