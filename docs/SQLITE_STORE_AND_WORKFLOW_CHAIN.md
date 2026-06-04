# SQLite Store and Workflow Chain

## Decision

The project now uses SQLite as the persistent candle store.

CSV snapshots are still useful for debugging, but SQLite is the primary store for Stage 2D and later.

## Why SQLite

SQLite gives us:

- one persistent database file,
- one table per timeframe,
- primary-key deduplication by timestamp,
- better incremental updates,
- easier migration to local/VPS later.

## Tables

Current tables:

```text
candles_1min
candles_5min
candles_15min
candles_1h
```

Each table uses `time_utc` as primary key.

## Workflow chain

The data workflow runs first:

```text
XAUUSD Persistent Data Store Refresh
```

It refreshes SQLite and commits:

```text
data/store/xauusd.sqlite
data/store/manifest.json
```

Then the Stage 2D workflow is triggered by `workflow_run`:

```text
XAUUSD Stage 2D Baseline Grid Lab
```

This avoids putting a schedule on every research stage.

## Manual commands

Local refresh:

```bash
python3 -m app.xauusd_store_refresh
```

Local Stage 2D:

```bash
python3 -m app.xauusd_stage2d_grid_lab --data-db data/store/xauusd.sqlite
```

## GitHub requirement

Repository settings must allow GitHub Actions to write contents:

```text
Settings → Actions → General → Workflow permissions → Read and write permissions
```

The workflow itself also declares:

```yaml
permissions:
  contents: write
```

## Warning

SQLite is fine for the current research store. If the database grows too large, move it out of Git and keep only summaries/artifacts in the repository.
