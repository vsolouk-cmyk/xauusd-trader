# Stage 5C Live Dry-run Outcome Tracker v3

Generated UTC: `2026-06-09T11:59:08+00:00`
Tool version: `v3`
Strategy ID: `xauusd_long_tp24_sl15_no_london_v1`

> Hard rule: this resolves dry-run signals only. It does not authorize demo, paper, or live orders.

## Inputs
- signals_csv: `/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/XAUUSD_DryRun_v1_signals.csv`
- m1_csv: `/Users/vahid/Downloads/amarkets_xauusd_1m.csv`
- server_utc_offset_hours: `2.0`

## M1 load quality
- status: `ok`
- rows_raw: `1449867`
- rows_parsed: `1449867`
- bad_time_rows: `0`
- start_utc: `2022-05-01T23:01:00+00:00`
- end_utc: `2026-06-09T11:44:00+00:00`

## Summary
- raw_signal_rows: `1`
- deduped_signals: `1`
- skipped_duplicate_rows: `0`
- resolved: `1`
- open_or_unresolved: `0`
- total_net_x1_resolved: `-15.35`

## Outcomes
| Row | Status | Reason | Session | Closed H1 UTC | Entry UTC | Entry | TP | SL | Exit UTC | Exit | Net x1 |
|---:|---|---|---|---|---|---:|---:|---:|---|---:|---:|
| 1 | RESOLVED | stop_loss | asia | 2026-06-09T06:00:00+00:00 | 2026-06-09T07:00:00+00:00 | 4343.26 | 4367.26 | 4328.26 | 2026-06-09T08:13:00+00:00 | 4328.26 | -15.35 |

## Decision
- Continue dry-run logging. Do not use this report to place orders.
