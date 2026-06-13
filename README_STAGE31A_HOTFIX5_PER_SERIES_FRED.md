# Stage31A Hotfix5 — Per-series FRED downloader workflow

## Scope
Research/shadow infrastructure only. No EA, paper/live, or order changes.

## Why this patch exists
The previous GitHub FRED workflow downloaded every source in one run. Because FRED occasionally returned 504 for individual series, one run could take 20+ minutes and still only yield a partial artifact. This hotfix lets us refresh one selected FRED series at a time.

## Files changed
- `.github/workflows/xauusd_fred_exogenous.yml`
- `tools/download_fred_exogenous.py`

## Main changes
- Adds workflow input `series`:
  - `all`
  - `dxy`
  - `us10y`
  - `real_yield`
  - `vix`
  - `spx`
  - `oil`
  - comma list, e.g. `us10y,vix`
- Adds workflow input `run_stage31a`, default `0`.
  - Local Stage31A is preferred because the GitHub runner does not have the user's full local Stage30A dataset/DB context.
- Adds curl `--http1.1` and keeps retry-all-errors fallback.
- Writes successful selected outputs to:
  - `data/exogenous/_artifact_success/<series>.csv`
- Uploads only selected successful files plus manifest, reducing the chance of accidentally overwriting local real files with templates.

## Install
```bash
cd ~/Desktop/xauusd-trader
unzip -o ~/Downloads/xauusd_stage31a_hotfix5_per_series_fred_patch.zip -d .
```

## Commit/push
```bash
git add -A
git commit -m "Add per-series FRED exogenous refresh workflow"
git pull --rebase origin main
git push
```

## Recommended GitHub runs
Run these manually, one at a time:

```text
Actions → XAUUSD FRED Exogenous Refresh → Run workflow
series = us10y
strict = 0
run_stage31a = 0
```

Then repeat for:

```text
series = vix
series = real_yield
series = spx
series = oil
```

## Safe local artifact install
For a per-series artifact, copy only `_artifact_success` files into the real local exogenous directory:

```bash
cd ~/Desktop/xauusd-trader
mkdir -p /tmp/xauusd_fred_artifact
rm -rf /tmp/xauusd_fred_artifact/*
unzip -o ~/Downloads/xauusd-fred-exogenous-*.zip -d /tmp/xauusd_fred_artifact
mkdir -p data/exogenous
cp -v /tmp/xauusd_fred_artifact/exogenous/_artifact_success/*.csv data/exogenous/
```

Then run Stage31A locally:

```bash
python3 -m app.stage31a_exogenous_feature_ingestion
cat data/reports/stage31a_exogenous_feature_ingestion/stage31a_exogenous_feature_ingestion.md
```
