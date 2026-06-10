# Stage 6A Local Persistent Data Store

Generated UTC: `2026-06-09T12:01:43+00:00`
Tool version: `v2`

> Hard rule: this imports local/reference data into SQLite only. It does not authorize demo, paper, or live orders.

## Database
- path: `data/local/xauusd_local_store.sqlite`

## Import results
| Dataset | Source | Timeframe | Status | Rows seen | Rows inserted/replaced | Rows bad | Start UTC | End UTC | Error |
|---|---|---|---|---:|---:|---:|---|---|---|
| bars | amarkets_mt5 | 1h | ok | 24225 | 24225 | 0 | 2022-05-01T23:00:00+00:00 | 2026-06-09T11:00:00+00:00 |  |
| bars | amarkets_mt5 | 1m | ok | 1449867 | 1449867 | 0 | 2022-05-01T23:01:00+00:00 | 2026-06-09T11:44:00+00:00 |  |
| dryrun_signals | mt5_ea |  | ok | 1 | 1 | 0 | 2026-06-09T06:00:00+00:00 | 2026-06-09T06:00:00+00:00 |  |
| dryrun_outcomes | stage5c |  | ok | 1 | 1 | 0 | 2026-06-09T06:00:00+00:00 | 2026-06-09T06:00:00+00:00 |  |

## DB counts
- bars: `1474092`
- dryrun_signals: `1`
- dryrun_outcomes: `1`
- import_runs: `20`

## Decision
- Use this SQLite store as local persistent evidence.
- AMarkets/MT5 remains the execution feed. Twelve Data is reference/secondary unless later explicitly validated.
- Twelve fetch failures should not block local broker persistence.
