# XAUUSD Cross-Asset Intraday Readiness V1.2

## Purpose

Repair the MT5 inventory writer after a real terminal run reported `rows=8` but produced a CSV with no readable data rows.

## Changes

- Replaces manual `FileWriteString` record assembly with MQL5 `FILE_CSV` + `FileWrite` records.
- Counts a row only when `FileWrite` reports success.
- Reopens the completed snapshot and validates the exact number of 25-column data records before publication.
- Never publishes a header-only or partially written snapshot.
- Preserves atomic canonical publication and valid-snapshot fallback.
- Adds raw file diagnostics (`size`, newline count, SHA256 and initial bytes) to Python inventory selection diagnostics.
- No order, position or trade-request path is present.

## Expected MT5 result

`PASS_CROSS_ASSET_MT5_INVENTORY_CREATED rows=<n> validated=<n> ...`

A mismatch produces `FAIL_SNAPSHOT_SELF_VALIDATION` and must not be collected.
