# Stage 5B Validator v4

Purpose: validate the MT5 dry-run CSV produced by `XAUUSD_DryRun_v1.mq5` without approving demo, paper, or live orders.

## Why v4 exists

Validator v3 could map `dry_run_only` as a signal column. That is semantically wrong: `dry_run_only` is a safety flag, not a trading signal flag.

v4 recognizes the current EA-native signal-only schema:

```text
logged_at_gmt
symbol
chart_symbol
strategy_id
signal_closed_h1_time_server
signal_closed_h1_time_gmt_now
session_utc
close_h1
sma10
distance_usd
direction
planned_entry_model
tp_usd
sl_usd
time_exit_h1_bars
dry_run_only
```

If this schema is detected, each data row is treated as a dry-run signal record. `dry_run_only=true` is validated separately.

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage5b_dryrun_log_validator --csv "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/XAUUSD_DryRun_v1_signals.csv" --print-columns
```

## Expected status

- `PASS` or `PASS_WITH_WARNINGS`: acceptable for dry-run monitoring.
- `WARN` in `--strict` mode: not fatal; inspect report.
- `FAIL`: must be fixed before relying on the log.

Hard restriction remains unchanged: this tool never authorizes demo, paper, or live orders.
