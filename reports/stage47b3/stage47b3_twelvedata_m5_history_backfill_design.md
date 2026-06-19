# Stage47B3 — TwelveData M5 History Backfill

## Purpose

Stage47B and Stage47B2 proved that the Stage47B scanner and loader can run, but the available M5 history is too short for a meaningful rerun.

Stage47B2 found only 500 unique M5 candles after deduplication, covering about 1.73 days. That is enough for a pipeline smoke run, but not enough for thesis evaluation.

## Scope

This patch adds a research-only TwelveData M5 historical backfill script:

```text
app/stage47b3_twelvedata_m5_history_backfill.py
```

It fetches windowed `XAU/USD` `5min` candles, normalizes them to the current project CSV schema, merges them with existing normalized M5 files, deduplicates by UTC timestamp, and writes a longer normalized CSV.

## Hard restrictions

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

This stage does not create trading permission. Its only valid purpose is to build enough historical candles for a Stage47B rerun.

## Required environment

```text
TWELVEDATA_API_KEY
```

If this environment variable is not present, the script stops with:

```text
NO_API_KEY_STOP_NO_PROMOTION
```

## Main command

```bash
python3 app/stage47b3_twelvedata_m5_history_backfill.py \
  --days 90 \
  --chunk-days 7 \
  --sleep-sec 8 \
  --min-rows 5000 \
  --min-days 20 \
  --out reports/stage47b3
```

## Output

The script writes:

```text
data/normalized/normalized_twelvedata_XAU_USD_5min_backfill_<UTC>.csv
reports/stage47b3/stage47b3_twelvedata_m5_history_backfill_summary.json
reports/stage47b3/stage47b3_twelvedata_m5_history_backfill_report.md
```

## Valid next step

Only if the summary status is:

```text
DATA_HORIZON_READY_FOR_STAGE47B_RERUN_NO_PROMOTION
```

then rerun Stage47B using the generated normalized CSV.

If the status is still:

```text
INSUFFICIENT_HISTORY_STOP_NO_PROMOTION
```

then do not rerun Stage47B. Extend data history first or change data source.
