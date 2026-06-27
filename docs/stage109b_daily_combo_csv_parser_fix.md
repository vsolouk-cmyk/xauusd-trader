# Stage109B Daily Combo CSV Parser Fix

## Purpose
Stage109B fixes the Stage109 validator, not the observer logic. Stage108 writes a wide CSV whose first row is a header and second row contains values. The original Stage109 validator interpreted the header as a key/value row, so it reported:

- `UNIFIED_CSV_MODE_NOT_OBSERVER_ONLY`
- `UNIFIED_CSV_SCHEMA_NOT_STAGE108_SECOND_ORDER`
- `UNIFIED_CSV_S105_03_KEYS_MISSING`
- `UNIFIED_CSV_C96_07_KEYS_MISSING`

## Fix
The bridge CSV parser now supports both:

1. wide CSV: header row = keys, second row = values;
2. key/value CSV: two columns per row.

## Hard blocks
No order, no broker connection, no MT5 trading action, no EA promotion, no paper-live, no live.
