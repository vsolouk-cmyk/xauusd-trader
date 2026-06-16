# Stage31A Hotfix2 — GitHub base dataset safe

## Purpose

Fixes GitHub Action failure:

```text
KeyError: 'entry_ts_norm'
```

The failure occurs when FRED files are downloaded successfully but Stage31A runs before a Stage30A ML dataset with `entry_ts_norm` exists in the GitHub runner. Stage31A now creates a readiness report rather than crashing, and the FRED workflow tries to build Stage30A before Stage31A.

## Files

- `app/stage31a_exogenous_feature_ingestion.py`
- `.github/workflows/xauusd_fred_exogenous.yml`
- `tools/download_fred_exogenous.py`
- `docs/STAGE31A_GITHUB_FRED_EXOGENOUS_WORKFLOW.md`

## Install

```bash
cd ~/Desktop/xauusd-trader
unzip -o ~/Downloads/xauusd_stage31a_hotfix2_github_base_dataset_safe_patch.zip -d .
```

## Commit

```bash
git add -A
git commit -m "Make Stage31A GitHub FRED workflow dataset-safe"
git pull --rebase origin main
git push
```

Then run `XAUUSD FRED Exogenous Refresh` manually with `strict=0`.
