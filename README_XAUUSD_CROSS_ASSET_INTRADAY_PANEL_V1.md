# XAUUSD Cross-Asset Intraday Panel V1.1 — Symbol-Specific History Start Repair

This repair addresses MT5 error 4401 for symbols whose broker history starts after the global 2016-01-01 request.

## Changes

- Resolves the effective export start per symbol/timeframe from `SERIES_FIRSTDATE` and `SERIES_SERVER_FIRSTDATE`.
- Defaults to repair-only export for `WTI` and `DXY` (M15/H1), preserving the 12 already-valid canonical files.
- Logs requested, series-first, server-first, and effective start times.
- Keeps the existing CSV schema, causal panel contract, targets, and no-order contract unchanged.
- Set `InpRepairOnlyLateHistorySymbols=false` only when a future full 16-file refresh is explicitly needed.

## Expected repair completion

`PASS_CROSS_ASSET_HISTORY_EXPORT_COMPLETE files=4 scope=WTI_DXY_REPAIR_ONLY ...`

No paper, demo, or live order path exists in this package.
