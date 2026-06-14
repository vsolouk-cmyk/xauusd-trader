# Stage31A Hotfix3 — Partial artifact upload + empty base dataset safety

## Scope
Research/shadow infrastructure only. No EA, paper/live, or order changes.

## Fixes
- `app/stage31a_exogenous_feature_ingestion.py`
  - Handles an existing but empty Stage30A dataset CSV without crashing (`pandas.errors.EmptyDataError`).
  - Emits `STAGE31A_BASE_DATASET_MISSING_REVIEW_ONLY` with a markdown report instead of failing.
- `.github/workflows/xauusd_fred_exogenous.yml`
  - Uploads FRED/exogenous artifacts with `if: always()` so partial downloads survive Stage31A failures.
  - Adds Stage30A report directory to the artifact for diagnosis.
- `tools/download_fred_exogenous.py`
  - Included for consistency with the current partial-safe FRED downloader.

## Expected behavior
A failed Stage31A step should no longer discard downloaded FRED CSVs silently. The workflow artifact should include whatever exists under `data/exogenous/`, including `fred_download_manifest.csv`.

## Commands
```bash
cd ~/Desktop/xauusd-trader
unzip -o ~/Downloads/xauusd_stage31a_hotfix3_partial_artifact_empty_dataset_patch.zip -d .
git add -A
git commit -m "Make Stage31A FRED workflow preserve partial artifacts"
git pull --rebase origin main
git push
```
