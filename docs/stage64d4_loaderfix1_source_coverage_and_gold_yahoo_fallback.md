# Stage64D4 LoaderFix1 - Source Coverage and Gold/DXY Fallback

## Purpose

This hotfix updates the local macro data fetcher and Stage64D4 source-file preflight.

## Changes

1. Adds Yahoo Finance chart fallback for gold daily OHLC:
   - `XAUUSD=X` preferred spot reference.
   - `GC=F` continuous COMEX gold futures reference fallback.
2. Adds Yahoo Finance chart source for exact US Dollar Index:
   - `DX-Y.NYB`.
3. Keeps FRED fallback for broad USD index only as a proxy and blocks it by default in preflight unless explicitly accepted.
4. Fixes the over-strict `2011-01-01` coverage check by allowing a 7-day grace window for market daily series, because 2011-01-01 is not a trading day.
5. Does not authorize validation, paper-order, paper-live, live, EA promotion, or broker connection.

## Expected usage

Run the local fetcher, then rerun Stage64D4 preflight. If P0 passes, rerun Stage64D to reassess data-contract readiness. Validation remains blocked until Stage64D explicitly unlocks the selected scope.
