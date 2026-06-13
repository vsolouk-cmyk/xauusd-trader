# Stage31A GitHub FRED Exogenous Workflow

This workflow downloads FRED macro/exogenous CSV files on GitHub Actions and runs Stage31A ingestion there. It avoids local VPN/SSL issues on macOS.

Workflow file:

```text
.github/workflows/xauusd_fred_exogenous.yml
```

Downloader:

```text
tools/download_fred_exogenous.py
```

Generated files:

```text
data/exogenous/dxy.csv
data/exogenous/us10y.csv
data/exogenous/real_yield.csv
data/exogenous/vix.csv
data/exogenous/spx.csv
data/exogenous/oil.csv
data/reports/stage31a_exogenous_feature_ingestion/
```

The workflow is manual only (`workflow_dispatch`) so it will not add scheduled load or unexpected commits.

After the workflow completes, download the artifact named `xauusd-fred-exogenous-<run_id>`, unzip it into the repository root, and re-run Stage31A locally if needed.
