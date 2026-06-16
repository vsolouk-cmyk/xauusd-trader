# Stage 2M Store Retention Fix

## Problem

Stage 2L backfill reached the previous SQLite cap:

```text
max_rows_per_interval: 20000
```

After the latest 1h backfill, the store reached 20000 rows and trimmed 123 rows.

That is a warning. Further backfill with the old cap could add older candles and then immediately delete the oldest candles again.

## Decision

Raise store retention to:

```text
max_rows_per_interval: 60000
```

This applies to both:

```text
configs/persistent_store.yaml
configs/backfill.yaml
```

## Why 60000

For 1h candles, 60000 rows is roughly 6+ years of data.

That is enough for the current Stage 2 validation without making the SQLite file unreasonably large.

## Next action

After applying this patch, run Stage 2L again with:

```text
intervals: 1h
requests_per_interval: 1
include_run_link: false
```

The expected start date should move earlier than the current 2023-05-22.
