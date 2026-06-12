# Stage 3A Second-Source Validation

## Purpose

Validate the fixed candidate on a second independent source before any ML, paper-order, or live trading.

## Fixed candidate

```text
sma10_h12_dist10_cool1
```

Meaning:

- `sma10`: 10-period simple moving average.
- `h12`: hold for 12 candles.
- `dist10`: enter only if close is at least $10 away from SMA.
- `cool1`: wait one candle after exit before a new entry.

## What this stage does

1. Evaluates the fixed candidate on the primary Twelve Data SQLite store.
2. If available, evaluates the same candidate on a second-source SQLite store.
3. Compares total net, PF, cost stress, long/short behavior, folds, and months.
4. Does not run grid search.
5. Does not train ML.
6. Does not send orders.

## Importing second-source CSV locally

Expected CSV columns can be flexible:

```text
time_utc or datetime or date or time or timestamp
open
high
low
close
volume optional
```

Command:

```bash
python3 -m app.xauusd_second_source_import \
  --csv /path/to/second_source_1h.csv \
  --db data/second_source/second_source.sqlite \
  --interval 1h \
  --provider mt5_or_other
```

Then validate:

```bash
python3 -m app.xauusd_stage3a_second_source_validate
```

## GitHub workflow

Run manually:

```text
XAUUSD Stage 3A Second-Source Validation
```

If no second-source DB is committed yet, the workflow returns:

```text
pending_second_source
```

That is not a failure. It means the skeleton is ready but secondary data has not been imported.

## Hard rule

Passing Stage 3A is not paper-order permission.

After Stage 3A, the next gate is forward shadow design and then strict forward shadow execution.
