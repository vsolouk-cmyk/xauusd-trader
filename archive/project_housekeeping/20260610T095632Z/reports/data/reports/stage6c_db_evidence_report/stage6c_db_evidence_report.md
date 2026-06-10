# Stage 6C DB Evidence Report

Generated UTC: `2026-06-09T12:01:44+00:00`
Tool version: `v1`
DB path: `data/local/xauusd_local_store.sqlite`

> Hard rule: read-only evidence report. This does not import data and does not authorize demo, paper, or live orders.

## DB counts
- bars: `1474092`
- dryrun_signals: `1`
- dryrun_outcomes: `1`
- import_runs: `20`

## Bars by source/timeframe
| Source | Symbol | TF | Rows | Start UTC | End UTC |
|---|---|---|---|---|---|
| amarkets_mt5 | XAUUSD | 1h | 24225 | 2022-05-01T23:00:00+00:00 | 2026-06-09T11:00:00+00:00 |
| amarkets_mt5 | XAUUSD | 1m | 1449867 | 2022-05-01T23:01:00+00:00 | 2026-06-09T11:44:00+00:00 |

## Dry-run outcome summary
- total_outcomes: `1`
- resolved: `1`
- open_or_unresolved: `0`
- total_net_usd: `-15.35`
- avg_net_usd: `-15.35`
- wins: `0`
- losses: `1`
- win_rate: `0.0`

## Outcomes by session
| Session | Trades | Resolved | Total net | Avg net |
|---|---|---|---|---|
| asia | 1 | 1 | -15.35 | -15.35 |

## Outcomes by reason
| Reason | Trades | Total net |
|---|---|---|
| stop_loss | 1 | -15.35 |

## no_asia live counterfactual
- excluded_trades: `1`
- excluded_net_usd: `-15.35`
- kept_trades: `0`
- kept_net_usd: `0`
- note: Live-only sample. Not statistically sufficient by itself.

## Recent signal/outcome join
| Closed H1 UTC | Session | Distance | Status | Reason | Entry UTC | Entry | Exit UTC | Exit | Net |
|---|---|---|---|---|---|---|---|---|---|
| 2026-06-09T06:00:00+00:00 | asia | 12.758 | RESOLVED | stop_loss | 2026-06-09T07:00:00+00:00 | 4343.26 | 2026-06-09T08:13:00+00:00 | 4328.26 | -15.35 |

## Latest import runs
| ID | Created UTC | Source | Dataset | TF | Rows seen | Rows inserted | Bad | End UTC |
|---|---|---|---|---|---|---|---|---|
| 20 | 2026-06-09T12:01:43+00:00 | stage5c | dryrun_outcomes | event | 1 | 1 | 0 | 2026-06-09T06:00:00+00:00 |
| 19 | 2026-06-09T12:01:43+00:00 | mt5_ea | dryrun_signals | event | 1 | 1 | 0 | 2026-06-09T06:00:00+00:00 |
| 18 | 2026-06-09T12:01:25+00:00 | amarkets_mt5 | bars | 1m | 1449867 | 1449867 | 0 | 2026-06-09T11:44:00+00:00 |
| 17 | 2026-06-09T11:59:10+00:00 | amarkets_mt5 | bars | 1h | 24225 | 24225 | 0 | 2026-06-09T11:00:00+00:00 |
| 16 | 2026-06-09T11:40:56+00:00 | stage5c | dryrun_outcomes | event | 1 | 1 | 0 | 2026-06-09T06:00:00+00:00 |
| 15 | 2026-06-09T11:40:56+00:00 | mt5_ea | dryrun_signals | event | 1 | 1 | 0 | 2026-06-09T06:00:00+00:00 |
| 14 | 2026-06-09T11:40:42+00:00 | amarkets_mt5 | bars | 1m | 1449867 | 1449867 | 0 | 2026-06-09T11:44:00+00:00 |
| 13 | 2026-06-09T11:38:54+00:00 | amarkets_mt5 | bars | 1h | 24225 | 24225 | 0 | 2026-06-09T11:00:00+00:00 |
| 12 | 2026-06-09T11:32:53+00:00 | stage5c | dryrun_outcomes | event | 1 | 1 | 0 | 2026-06-09T06:00:00+00:00 |
| 11 | 2026-06-09T11:32:53+00:00 | mt5_ea | dryrun_signals | event | 1 | 1 | 0 | 2026-06-09T06:00:00+00:00 |
| 10 | 2026-06-09T11:32:39+00:00 | amarkets_mt5 | bars | 1m | 1449867 | 1449867 | 0 | 2026-06-09T11:44:00+00:00 |
| 9 | 2026-06-09T11:30:45+00:00 | amarkets_mt5 | bars | 1h | 24225 | 24225 | 0 | 2026-06-09T11:00:00+00:00 |

## Warnings / blockers
- Only 1 resolved live dry-run outcome(s); live evidence is still too small for execution decisions.
- no_asia counterfactual would have excluded 1 live resolved trade(s), net=-15.35.

## Decision
- Local DB evidence store is readable and decision reports can now be generated from SQLite.
- Live evidence is still too small for any demo/paper/live authorization.
- Current working direction remains: keep v1 dry-run running; evaluate no_asia as v2 candidate in deeper validation.
