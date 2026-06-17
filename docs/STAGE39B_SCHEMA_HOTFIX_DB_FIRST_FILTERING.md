# Stage39B schema hotfix: DB-first tolerant filtering

## Problem

The first Stage39B patch queried SQLite with exact SQL predicates:

```sql
WHERE symbol = ? AND source = ? AND timeframe = ?
```

This can fail even when the data exists, because local MT5-derived stores may hold metadata values with different case, whitespace, or timeframe aliases such as `h1`, `1H`, or `60M`.

Observed failure:

```text
No rows loaded from data/local/xauusd_local_store.sqlite:bars for symbol=XAUUSD, source=amarkets_mt5, timeframe=H1
```

Stage39A had already proven that the same database and table were readable with 25,643 H1 rows. Therefore the failure was a Stage39B loader issue, not a missing-data issue.

## Fix

The loader now follows the Stage39A-compatible pattern:

1. inspect table schema with `PRAGMA table_info`,
2. detect timestamp/OHLC/source/symbol/timeframe columns,
3. read the table ordered by timestamp,
4. apply tolerant pandas-side filters:
   - symbol: case-insensitive,
   - source: case-insensitive and stripped,
   - timeframe: normalized aliases mapped to `H1`.

Supported H1 aliases include:

```text
H1, 1H, 60M, 60MIN, 60MINS, 60MINUTE, 60MINUTES, 1HR, 1HOUR, 1HOURS, M60
```

## Added diagnostics

If filtering still produces zero rows, the error now includes:

```text
pre_filter_rows
detected timestamp/symbol/source/timeframe columns
distinct symbol/source/timeframe sample values
filter step before/after counts
```

This makes the next schema mismatch immediately diagnosable.

## Decision status

This is a loader hotfix only.

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```
