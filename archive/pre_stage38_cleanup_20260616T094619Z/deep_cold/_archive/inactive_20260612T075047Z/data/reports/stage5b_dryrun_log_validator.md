# Stage 5B Dry-run Log Validator

Generated UTC: `2026-06-09T11:58:29Z`
Tool version: `v5`
Strict mode: `False`
Overall status: **PASS_WITH_WARNINGS**

> Hard rule: this validates dry-run logs only. It does not authorize demo, paper, or live orders.

## Stats

- CSV path: `/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/XAUUSD_DryRun_v1_signals.csv`
- file_size_bytes: `405`
- encoding: `utf-8-sig`
- detected_delimiter: `TAB`
- rows: `1`
- signals: `1`
- blocked_skipped_rows: `0`
- no_signal_rows: `0`
- native_signal_only_schema: `True`

## Detected columns

- `logged_at_gmt`
- `symbol`
- `chart_symbol`
- `strategy_id`
- `signal_closed_h1_time_server`
- `signal_closed_h1_time_gmt_now`
- `session_utc`
- `close_h1`
- `sma10`
- `distance_usd`
- `direction`
- `planned_entry_model`
- `tp_usd`
- `sl_usd`
- `time_exit_h1_bars`
- `dry_run_only`

## Resolved columns

- `timestamp_utc`: `logged_at_gmt`
- `closed_h1_time_utc`: `signal_closed_h1_time_gmt_now`
- `symbol`: `symbol`
- `strategy_id`: `strategy_id`
- `session_name`: `session_utc`
- `distance_usd`: `distance_usd`
- `close`: `close_h1`
- `sma10`: `sma10`
- `take_profit_usd`: `tp_usd`
- `stop_loss_usd`: `sl_usd`
- `direction`: `direction`
- `dry_run_only`: `dry_run_only`
- `time_exit_h1_bars`: `time_exit_h1_bars`

## Checks

| Status | Check | Detail |
|---|---|---|
| PASS | CSV header | Detected 16 column(s). |
| PASS | CSV delimiter | Detected delimiter: TAB. |
| PASS | CSV rows | Detected 1 data row(s). |
| PASS | CSV encoding | Decoded as utf-8-sig. |
| PASS | EA-native signal-only schema | Detected Stage 5A EA signal-log schema. Rows are treated as dry-run signal records. |
| PASS | Usable time column | timestamp=logged_at_gmt, closed_h1=signal_closed_h1_time_gmt_now |
| PASS | Signal/event column | No explicit signal column, but EA-native schema is signal-only; each data row is treated as a dry-run signal. |
| WARN | Reason/status column | No reason/status column in current EA-native schema. Acceptable for signal-only logs, but less informative. |
| PASS | Dry-run-only flag | All rows have dry_run_only=true. |
| PASS | Strategy ID consistency | All rows match xauusd_long_tp24_sl15_no_london_v1. |
| PASS | Long-only direction | All rows are long/buy. |
| PASS | TP USD | All rows match expected 24.0. |
| PASS | SL USD | All rows match expected 15.0. |
| PASS | Time exit H1 bars | All rows match expected 12.0. |
| PASS | Distance arithmetic | Checked 1 row(s): close - sma10 ≈ distance_usd. |
| PASS | No-London filter | No signal rows are in the blocked standalone London session. Allowed overlap sessions such as london_ny_overlap are not blocked. |

Decision: **Usable for Stage 5B dry-run monitoring with warnings; not authorization for demo/paper/live orders.**
