# Stage36B HF1 — OHLC Source Detection / Resample Fix

This hotfix repairs Stage36B when the local SQLite `bars` table exists but the previous selector returns zero H1 rows.

## What changed

- Inspects SQLite table schema dynamically.
- Detects timestamp/open/high/low/close columns using aliases.
- Accepts missing/blank timeframe columns.
- Infers median source cadence from timestamps.
- Resamples lower-timeframe OHLC bars to H1.
- Writes a richer `stage36b_data_source_audit.csv`.

## Safety

Research only. No EA change. No paper-live. No order authorization.
