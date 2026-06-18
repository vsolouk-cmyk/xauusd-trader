# Stage45B1A_EXTERNAL_CONTEXT_IMPORT_VALIDATE

## Purpose

Stage45B1 confirmed that all P0 external context files are still missing. Stage45B1A adds a local import/normalize/validate helper so manually acquired external CSVs can be converted into canonical project paths and checked before any alignment audit.

This stage does **not** create trading signals, does **not** shortlist candidates, and does **not** promote archived rows.

## Canonical P0 files

```text
data/external/dxy.csv
data/external/us10y_yield.csv
data/reference/cme_gc.csv
data/external/news_calendar.csv
```

## Optional files

```text
data/external/us02y_yield.csv
data/external/real_yield.csv
```

## Validation-only run

Use this after applying the patch or after manually placing files into canonical paths:

```bash
python3 scripts/stage45b1a_external_context_import_validate.py --print-summary
```

## Import run from Downloads

Put acquired external files in a local folder such as:

```text
~/Downloads/xauusd_external_context/
```

Then run:

```bash
python3 scripts/stage45b1a_external_context_import_validate.py \
  --dxy ~/Downloads/xauusd_external_context/dxy.csv \
  --us10y ~/Downloads/xauusd_external_context/us10y_yield.csv \
  --cme-gc ~/Downloads/xauusd_external_context/cme_gc.csv \
  --news-calendar ~/Downloads/xauusd_external_context/news_calendar.csv \
  --overwrite --print-summary
```

Optional additions:

```bash
python3 scripts/stage45b1a_external_context_import_validate.py \
  --us02y ~/Downloads/xauusd_external_context/us02y_yield.csv \
  --real-yield ~/Downloads/xauusd_external_context/real_yield.csv \
  --overwrite --print-summary
```

## Output files

```text
reports/stage45b1a/stage45b1a_external_context_import_validate_summary.json
reports/stage45b1a/stage45b1a_external_context_import_validate.md
reports/stage45b1a/stage45b1a_external_context_inventory.csv
reports/stage45b1a/stage45b1a_normalized_files_written.csv
```

## Decision logic

```text
If all P0 files are schema-valid:
  next_allowed_step = Stage45B2_EXTERNAL_CONTEXT_ALIGNMENT_AUDIT

Otherwise:
  next_allowed_step = Stage45B1_CONTINUE_EXTERNAL_CONTEXT_DATA_ACQUISITION
```

## Required schemas

### DXY

Accepted minimum:

```text
timestamp, close
```

Preferred:

```text
timestamp, open, high, low, close, volume, source
```

### US 10Y yield

Accepted minimum:

```text
timestamp, yield
```

or:

```text
timestamp, close
```

### CME GC/MGC reference

Accepted minimum:

```text
timestamp, open, high, low, close
```

Preferred:

```text
timestamp, open, high, low, close, volume, contract, source
```

### News calendar

Accepted minimum:

```text
timestamp, event
```

Preferred:

```text
timestamp, event, currency, impact, category, actual, forecast, previous, source
```

## Anti-overfit rule

Do not use imported external data to rescue Stage41/42/43 rows post hoc. The only valid next step after P0 readiness is a predefined alignment audit.
