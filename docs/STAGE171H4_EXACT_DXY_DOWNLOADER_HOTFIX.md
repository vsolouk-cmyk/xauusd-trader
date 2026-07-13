# Stage171H4 — Exact DXY Downloader Hotfix

## Purpose

Repair the only remaining Stage171H forward blocker: stale exact DXY data.

## Source policy

1. Yahoo Finance `DX-Y.NYB` delayed ICE U.S. Dollar Index series.
2. Stooq `DX.F` continuous ICE USDX futures series.
3. Formula reconstruction using the ICE six-currency weights and official FRED FX series.

`DTWEXBGS` remains excluded because it is a broad trade-weighted dollar index, not DXY.

## Safety controls

- Failed, HTML, rate-limited or bot-protection responses never overwrite history.
- Values must be in a plausible DXY range.
- Daily jumps must remain plausible.
- New data must agree with overlapping local exact-DXY history.
- The existing file is backed up before an atomic replacement.
- No threshold, signal, order, demo or live authorization is changed.

## Operational integration

The four-hour orchestrator now runs the exact-DXY downloader after the official macro batch and before the forward feature materializer.
