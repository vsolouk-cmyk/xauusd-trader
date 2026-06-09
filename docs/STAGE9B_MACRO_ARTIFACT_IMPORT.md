# Stage 9B Macro Numeric Artifact Importer

Local FRED fetch can fail because of DNS/filtering/certificate issues. In that case:

1. Run `XAUUSD Macro Numeric Update` in GitHub Actions.
2. Download artifact `xauusd-macro-numeric-update`.
3. Extract/copy the artifact into the local repo.
4. Import the CSV into local SQLite.

## Expected artifact file

```text
data/macro/macro_numeric_observations.csv
```

## Run after copying artifact into local repo

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage9b_macro_numeric_import_artifact
cat data/reports/stage9b_macro_artifact_import/macro_artifact_import.md
```

## Run with a custom CSV path

```bash
python3 -m app.stage9b_macro_numeric_import_artifact \
  --csv ~/Downloads/xauusd-macro-numeric-update/data/macro/macro_numeric_observations.csv

cat data/reports/stage9b_macro_artifact_import/macro_artifact_import.md
```

## Tables written

```text
macro_numeric_observations
macro_update_runs
```

inside:

```text
data/local/xauusd_local_store.sqlite
```

## Important

This is data import only. No EA change, no demo, no paper, no live authorization.
