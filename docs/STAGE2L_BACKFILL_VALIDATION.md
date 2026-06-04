# Stage 2L Backfill Validation

## Purpose

Stage 2K passed on the current SQLite history. Stage 2L deepens history before trusting candidates.

This stage is manual because it consumes API credits.

## What it does

1. Backfills older candles into SQLite.
2. Commits the updated SQLite store.
3. Runs Stage 2D.
4. Runs Stage 2J.
5. Runs Stage 2K.
6. Sends Telegram report.

## Key definitions

- Backfill: adding older historical data that was not previously stored.
- Incremental backfill: requesting only an older time chunk instead of downloading everything again.
- Historical validation: testing the same candidate over a longer history.

## Default intervals

```text
15min,1h
```

Reason: current Stage 2 candidate family uses `1h`, and the grid also uses `15min` families. Backfilling 1min/5min now wastes API credits.

## Recommended first run

```text
intervals: 15min,1h
requests_per_interval: 1
include_run_link: false
```

## Local command

```bash
cd ~/Desktop/xauusd-trader
export TWELVEDATA_API_KEY='PASTE_KEY_HERE'
python3 -m app.xauusd_store_backfill --intervals 15min,1h --requests-per-interval 1
python3 -m app.xauusd_stage2d_grid_lab --data-db data/store/xauusd.sqlite
python3 -m app.xauusd_stage2j_candidate_analysis --data-db data/store/xauusd.sqlite
python3 -m app.xauusd_stage2k_walkforward --data-db data/store/xauusd.sqlite
```

## Warning

If Stage 2K fails after backfill, the previous candidate was overfit to the shorter period.

If Stage 2K passes after several backfill runs, the next gate is second-source validation, not live trading.
