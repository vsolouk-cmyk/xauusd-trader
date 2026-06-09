# Stage 9B Macro Artifact Import v2 Schema Fix

This patch fixes:

```text
sqlite3.OperationalError: table macro_numeric_observations has no column named ssl_mode
```

Cause:

The local SQLite table was created by an older updater before the `ssl_mode` column existed.

Fix:

The importer now checks schema with:

```text
PRAGMA table_info(macro_numeric_observations)
```

and safely runs:

```text
ALTER TABLE macro_numeric_observations ADD COLUMN ssl_mode TEXT
```

if needed.

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage9b_macro_numeric_import_artifact
cat data/reports/stage9b_macro_artifact_import/macro_artifact_import.md
```

## Custom CSV path

```bash
python3 -m app.stage9b_macro_numeric_import_artifact \
  --csv ~/Downloads/xauusd-macro-numeric-update/data/macro/macro_numeric_observations.csv
```

## Hard rule

Data import only. No EA change, no demo, no paper, no live authorization.
