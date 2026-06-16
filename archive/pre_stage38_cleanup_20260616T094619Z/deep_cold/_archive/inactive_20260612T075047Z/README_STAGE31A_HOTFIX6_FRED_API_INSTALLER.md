# Stage31A Hotfix6 — FRED API Downloader + Safe Artifact Installer

Research/shadow infrastructure only. No EA, paper/live, or order behavior.

## Files changed

- `.github/workflows/xauusd_fred_exogenous.yml`
- `tools/download_fred_exogenous.py`
- `tools/install_fred_artifact.py`

## Why

The legacy `fredgraph.csv` endpoint can take 15–20 minutes for a single series such as `DGS10` because retries wait on 504/timeout responses. This hotfix adds the official FRED API endpoint path and makes it the default for the GitHub workflow.

## New workflow inputs

- `series`: `all`, `dxy`, `us10y`, `real_yield`, `vix`, `spx`, `oil`, or comma-list such as `us10y,vix`
- `endpoint_mode`: `api`, `graph`, or `auto`
- `graph_fallback`: `0` or `1`
- `attempts`: default `3`
- `request_delay`: default `2`
- `run_stage31a`: default `0`

## GitHub secret required for fast API mode

Set this repository secret before using `endpoint_mode=api`:

```text
FRED_API_KEY
```

The workflow validates this secret before running the downloader. If the secret is missing and `endpoint_mode=api`, the run fails immediately with a clear message instead of waiting 15–20 minutes.

## Recommended GitHub run for us10y

```text
series = us10y
endpoint_mode = api
graph_fallback = 0
strict = 0
attempts = 3
request_delay = 2
run_stage31a = 0
```

## Safe artifact install

Avoid zsh wildcard expansion over multiple zip files. Use an exact artifact zip path:

```bash
cd ~/Desktop/xauusd-trader
python3 tools/install_fred_artifact.py ~/Downloads/xauusd-fred-exogenous-us10y-27479778865.zip
```

Then run:

```bash
python3 -m app.stage31a_exogenous_feature_ingestion
cat data/reports/stage31a_exogenous_feature_ingestion/stage31a_exogenous_feature_ingestion.md
```

## Why the old artifact install command failed

This command is unsafe when more than one matching zip exists in `~/Downloads`:

```bash
unzip -o ~/Downloads/xauusd-fred-exogenous-*.zip -d /tmp/xauusd_fred_artifact
```

In zsh the wildcard expands into multiple filenames; `unzip` treats the second zip as an internal filename pattern and prints `filename not matched`. Use the installer with one exact zip filename instead.

The installer also skips template CSVs with fewer than 50 real numeric rows, so an older all-series artifact will not overwrite real local files with two-line templates.
