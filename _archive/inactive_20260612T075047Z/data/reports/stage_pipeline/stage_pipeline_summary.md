# XAUUSD Stage Pipeline Summary

Generated UTC: `2026-06-09T10:46:01+00:00`
Tool version: `v2`
Mode: `live_only`
Strategy ID: `xauusd_long_tp24_sl15_no_london_v1`

> Hard rule: this pipeline runs research/dry-run validation only. It does not authorize demo, paper, or live orders.

## Inputs
- h1_csv: `/Users/vahid/Downloads/amarkets_xauusd_1h.csv`
- m1_csv: `/Users/vahid/Downloads/amarkets_xauusd_1m.csv`
- signals_csv: `/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/XAUUSD_DryRun_v1_signals.csv`
- server_utc_offset_hours: `2.0`

## Step summary
| # | Step | Status | Return code | Inferred report status | Main reports |
|---:|---|---|---:|---|---|
| 1 | stage5b_dryrun_signal_csv_validator | OK | 0 | PASS_WITH_WARNINGS | `data/reports/stage5b_dryrun_log_validator.md` |
| 2 | stage5c_live_outcome_tracker | OK | 0 | OPEN_OR_UNRESOLVED(1/1) | `data/reports/stage5c_live_outcome_tracker/stage5c_live_outcome_tracker.md` |

## Decision
- Pipeline completed. Use individual reports for research decisions. No order authorization.
- Current expected operational decision remains: continue live dry-run, keep EA unchanged unless a validated new locked strategy version is created.
