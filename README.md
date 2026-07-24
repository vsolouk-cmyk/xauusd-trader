# Stage116C FRED Core Release-History Repair

This repair fixes the exact historical event-coverage failure where Stage115
contained only four BLS and four BEA events from 2026 while the FED calendar
was complete.

## Root cause

The event bridge used the global `fred/releases/dates` endpoint as the
historical source. A current-year-only cache could be marked as complete after
pagination and then reused. Pagination did not solve the scope problem.

## Corrected source contract

The downloader now queries the official `fred/release/dates` endpoint
separately for the seven locked core release IDs:

- 10 — Consumer Price Index
- 11 — Employment Cost Index
- 46 — Producer Price Index
- 50 — Employment Situation
- 192 — Job Openings and Labor Turnover Survey
- 53 — Gross Domestic Product
- 54 — Personal Income and Outlays

The output is written to:

`~/Downloads/xauusd_fundamental_event_inbox/events/fred/fred_core_release_dates_2009_present.json`

The runtime remains within the existing Stage113–116 pipeline. No parallel
downloader and no manual event dataset are introduced.

## Important behavior

- `--event-core-only` downloads the per-release core bundle, BLS/BEA data, and
  FOMC pages.
- Existing current-year-only core caches are invalidated automatically.
- Streaming progress remains enabled.
- Stage115 records `FRED_CORE_RELEASE_DATES_API` provenance.
- Event-context coverage and demo/live guards are not weakened.
