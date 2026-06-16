# Stage 2N Backfill Manifest Fix

## Problem

Stage 2L backfill correctly updates SQLite and writes:

```text
data/store/backfill_manifest.json
```

But the primary manifest:

```text
data/store/manifest.json
```

was still showing an older refresh snapshot.

This was confusing because Stage 2L artifacts contained a stale `manifest.json`.

## Fix

Backfill now writes both:

```text
data/store/backfill_manifest.json
data/store/manifest.json
```

The primary manifest now summarizes current SQLite table state after backfill.

## Important

This does not change strategy logic.

It only fixes reporting/persistence visibility.
