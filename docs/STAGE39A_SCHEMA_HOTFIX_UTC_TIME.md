# Stage39A schema hotfix: `utc_time` timestamp support

## Scope

This is a schema compatibility hotfix for:

```text
Stage39A_BENCHMARK_FIRST_REVERSAL_OR_MEAN_REVERSION_SCAN
```

It does **not** change the research decision policy:

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

## Issue

The project-local `bars` table has this timestamp column:

```text
utc_time
```

The first Stage39A script searched for timestamp columns such as `ts_utc`, `timestamp_utc`, `time_utc`, `datetime_utc`, etc., but missed `utc_time`.

The observed failure was:

```text
ValueError: Required column not found. Tried candidates=[...]; available=['source', 'symbol', 'timeframe', 'utc_time', ...]
```

## Fix

`utc_time` is now included near the top of `TIMESTAMP_CANDIDATES` in:

```text
scripts/stage39a_benchmark_first_reversal_mean_reversion_scan.py
```

The required-column error message was also made more diagnostic, so future schema mismatches point directly to the candidate-list location.

## Validation

The hotfix was smoke-tested with a synthetic SQLite database using the actual project column layout:

```text
source, symbol, timeframe, utc_time, open, high, low, close, tick_volume, spread, real_volume, source_time, imported_utc, raw_json, volume, ingested_at
```

Validation performed:

```text
python3 -m py_compile scripts/stage39a_benchmark_first_reversal_mean_reversion_scan.py
python3 scripts/stage39a_benchmark_first_reversal_mean_reversion_scan.py --db <synthetic_db> --table bars --symbol XAUUSD --source amarkets_mt5 --timeframe H1 --horizons 24,72,120 --cost-bps 8.0 --min-events 30 --output-dir <smoketest_reports>
```

Result:

```text
compile = PASS
schema load with utc_time = PASS
report generation = PASS
promotion = NO_GO
```

## Interpretation

This hotfix only restores execution against the real local schema. It does not improve, promote, or reinterpret any Stage39A result. Stage39A remains a research-stage benchmark-first reversal/mean-reversion scan.
