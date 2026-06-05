# Stage 3E Forward Shadow Scan

## Problem

Stage 3D checked only the latest candle.

That is dangerous when GitHub Actions cadence is irregular. If the workflow misses several hours, a valid signal could occur between two runs and then disappear by the time the next run checks only the latest bar.

## Fix

The forward-shadow runner now keeps a cursor in:

```text
shadow_metadata.last_processed_bar_time_utc
```

Each run scans every new candle since the last processed candle.

It can now:

- close due shadow trades,
- detect signals on missed bars,
- open the first eligible shadow trade while respecting max_open_trades and cooldown,
- update the cursor.

## First-run behavior

If no shadow DB history exists, it starts from the latest available bar and does not backfill historical shadow trades.

If a prior shadow trade already exists, it initializes from the latest trade event to avoid duplicates.

## Local command

```bash
python3 -m app.xauusd_forward_shadow
```

## GitHub workflow

No workflow file change is required. The existing Stage 3D workflow calls the same module.

## Hard rule

Still no order placement, no paper-order, and no live trading.
