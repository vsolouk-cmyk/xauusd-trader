# Stage36B-HF3 — Schema Audit and Timestamp Fix

## Purpose

HF2 removed the immediate `KeyError: ts`, but Stage36B still selected zero OHLC rows because the source detector could treat `timeframe` as a timestamp-like column. HF3 fixes that class of bug and adds a direct schema/sample-row audit when OHLC cannot be loaded.

## Changes

- Excludes `timeframe`, `tf`, `period`, and `interval` from timestamp detection.
- Reads OHLC columns through explicit SQL aliases: `ts`, `open`, `high`, `low`, `close`.
- Supports common timestamp names and date/time column pairs.
- Supports numeric epoch timestamps.
- Resamples lower timeframe OHLC to H1.
- Writes `stage36b_data_source_audit.csv` with column names and sample-row JSON for direct debugging.

## Research-only guard

This patch does not authorize EA changes, paper-live, or orders.
