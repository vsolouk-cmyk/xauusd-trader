# Stage 5B — Dry-run Log Validator

Purpose: validate the MT5 Common Files CSV created by `XAUUSD_DryRun_v1`.

This validates dry-run evidence only. It does **not** authorize demo-order, paper-order, or live trading.

## First local test with sample CSV

```bash
python3 -m app.stage5b_dryrun_log_validator --csv samples/stage5b_mt5_dryrun_sample.csv
```

Expected result: `WARN` or `PASS` is acceptable for the sample path. `FAIL` means the validator itself or the sample file has a problem.

## Run against real MT5 dry-run log

After market opens and MT5 produces the real CSV, run one of these.

Explicit path:

```bash
python3 -m app.stage5b_dryrun_log_validator --csv "/FULL/PATH/TO/XAUUSD_DryRun_v1_signals.csv"
```

Search common Wine/MT5 locations:

```bash
python3 -m app.stage5b_dryrun_log_validator --search-root "$HOME/Library/Application Support"
```

Alternative Wine root:

```bash
python3 -m app.stage5b_dryrun_log_validator --search-root "$HOME/.wine"
```

## Output

Reports are written to:

```text
data/reports/stage5b_dryrun_log_validator.json
data/reports/stage5b_dryrun_log_validator.md
```

`data/reports/` is local evidence and should not be committed.

## Recommended CSV schema

The validator accepts partial schemas, but the recommended locked schema is:

```text
timestamp_utc
symbol
strategy_id
ea_version
chart_timeframe
signal_timeframe
closed_h1_time_utc
close
sma10
distance_usd
session_name
session_allowed
signal
reason
```

If the current EA log lacks some columns, do not patch immediately while the market is closed. First capture the real first output after market open, then patch the EA once based on observed evidence.
