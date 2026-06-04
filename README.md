# xauusd-trader

Commercial XAUUSD/gold trading research pipeline.

## Current stage

Stage 2L/2N: historical backfill validation with synchronized SQLite manifests.

Telegram notification is enabled for pipeline reports only.

No ML. No trading bot. No paper order. No live order.

## Key definitions

- XAUUSD: spot gold quoted in US dollars.
- SQLite: a small SQL database stored as a single local file.
- Backfill: adding older historical data that was not previously stored.
- Manifest: a JSON status file describing current data-store state.
- Baseline: a simple rule-based strategy used as the minimum benchmark before ML.
- Walk-forward validation: testing candidate behavior over chronological segments.

## Current data architecture

Persistent database:

```text
data/store/xauusd.sqlite
```

Primary manifest:

```text
data/store/manifest.json
```

Backfill-specific manifest:

```text
data/store/backfill_manifest.json
```

## Manual backfill workflow

```text
XAUUSD Stage 2L Backfill Validation
```

Recommended next input only if more backfill is needed:

```text
intervals: 1h
requests_per_interval: 1
include_run_link: false
```

## Hard rule

Passing Stage 2K/2L still does not authorize ML, paper-order, or live trading.

Next gate after repeated backfill passes is second-source validation / broker-feed validation.
