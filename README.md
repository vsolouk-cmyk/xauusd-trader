# xauusd-trader

Commercial XAUUSD/gold trading research pipeline.

## Current stage

Stage 2L/2M: historical backfill validation with raised SQLite retention.

Telegram notification is enabled for pipeline reports only.

No ML. No trading bot. No paper order. No live order.

## Key definitions

- XAUUSD: spot gold quoted in US dollars.
- SQLite: a small SQL database stored as a single local file.
- Backfill: adding older historical data that was not previously stored.
- Retention cap: maximum number of rows kept per interval table.
- Workflow chain: one GitHub Actions workflow starts after another workflow completes.
- Baseline: a simple rule-based strategy used as the minimum benchmark before ML.
- Walk-forward validation: testing candidate behavior over chronological segments.

## Current data architecture

Persistent database:

```text
data/store/xauusd.sqlite
data/store/manifest.json
```

Current retention:

```text
max_rows_per_interval: 60000
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

Recommended next input:

```text
intervals: 1h
requests_per_interval: 1
include_run_link: false
```

## Hard rule

Passing Stage 2K/2L still does not authorize ML, paper-order, or live trading.

Next gate after repeated backfill passes is second-source validation / broker-feed validation.
