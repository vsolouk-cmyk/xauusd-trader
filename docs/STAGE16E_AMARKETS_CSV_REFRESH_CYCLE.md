# Stage 16E v2 AMarkets CSV Refresh + True-Forward Cycle

## v2 fix

The existing local `bars` table may contain this required column:

```text
imported_utc
```

Stage 16E v1 inserted `ingested_at`, but did not populate `imported_utc`, causing:

```text
NOT NULL constraint failed: bars.imported_utc
```

v2 dynamically detects the existing schema and fills both `imported_utc` and `ingested_at` when present.

## Recommended run for known files

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage16e_amarkets_csv_refresh_cycle \
  --csv-file ~/Downloads/amarkets_xauusd_1h.csv \
  --csv-file ~/Downloads/amarkets_xauusd_1m.csv \
  --filename-contains ""
```

Then inspect:

```bash
cat data/reports/stage16e_amarkets_csv_refresh_cycle/stage16e_amarkets_csv_refresh_cycle.md
```

## Alternative directory run

```bash
python3 -m app.stage16e_amarkets_csv_refresh_cycle --csv-dir ~/Downloads --filename-contains amarkets_xauusd
```

## Expected signs of success

```text
files_imported > 0
rows_upserted > 0
after_latest_bar_utc changes if the CSVs contain newer data
```

If `files_imported > 0` but latest time does not change, the CSV files were imported but did not include newer bars.

## Hard rule

Data refresh + research shadow cycle only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to order
```
