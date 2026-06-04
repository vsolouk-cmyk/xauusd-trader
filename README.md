# xauusd-trader

Commercial XAUUSD/gold trading research pipeline.

## Current stage

Stage 2L: manual historical backfill validation after Stage 2K passed.

Telegram notification is enabled for pipeline reports only.

No ML. No trading bot. No paper order. No live order.

## Key definitions

- XAUUSD: spot gold quoted in US dollars.
- SQLite: a small SQL database stored as a single local file.
- Backfill: adding older historical data that was not previously stored.
- Workflow chain: one GitHub Actions workflow starts after another workflow completes.
- Baseline: a simple rule-based strategy used as the minimum benchmark before ML.
- Walk-forward validation: testing candidate behavior over chronological segments.

## Current data architecture

Persistent database:

```text
data/store/xauusd.sqlite
data/store/manifest.json
```

## Routine workflow

```text
XAUUSD Persistent Data Store Refresh
```

This keeps recent data fresh.

## Manual backfill workflow

```text
XAUUSD Stage 2L Backfill Validation
```

Recommended first inputs:

```text
intervals: 15min,1h
requests_per_interval: 1
include_run_link: false
```

## Local backfill

```bash
cd ~/Desktop/xauusd-trader
export TWELVEDATA_API_KEY='PASTE_KEY_HERE'
python3 -m app.xauusd_store_backfill --intervals 15min,1h --requests-per-interval 1
```

Then rerun validation:

```bash
python3 -m app.xauusd_stage2d_grid_lab --data-db data/store/xauusd.sqlite
python3 -m app.xauusd_stage2j_candidate_analysis --data-db data/store/xauusd.sqlite
python3 -m app.xauusd_stage2k_walkforward --data-db data/store/xauusd.sqlite
```

## Hard rule

Passing Stage 2K/2L still does not authorize ML, paper-order, or live trading.

Next gate after repeated backfill passes is second-source validation / broker-feed validation.
