# README — Stage31A GitHub FRED Exogenous Workflow Patch

## Files included

- `.github/workflows/xauusd_fred_exogenous.yml`
- `tools/download_fred_exogenous.py`
- `docs/STAGE31A_GITHUB_FRED_EXOGENOUS_WORKFLOW.md`

## Purpose

Download FRED exogenous data through GitHub Actions instead of the local Mac/VPN environment, then run Stage31A ingestion and upload the exogenous CSVs plus Stage31A report as an artifact.

## Safety

- Manual workflow only.
- No EA, paper, live, or order action.
- No write permission to repository contents.
- Uses artifact output only.

## Run locally

```bash
python3 tools/download_fred_exogenous.py
python3 -m app.stage31a_exogenous_feature_ingestion
```

## Run in GitHub

Actions → XAUUSD FRED Exogenous Refresh → Run workflow

Then download artifact:

```text
xauusd-fred-exogenous-<run_id>
```
