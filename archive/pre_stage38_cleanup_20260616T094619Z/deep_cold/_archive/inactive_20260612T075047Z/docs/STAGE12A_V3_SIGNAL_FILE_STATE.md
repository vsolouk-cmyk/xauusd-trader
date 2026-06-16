# Stage 12A v3 Signal File State

Stage 12A v3 distinguishes signal file existence from signal rows.

This matters because MT5/EA may create a UTF-16 CSV file with only a BOM before any signal is logged.

## Long signal states

```text
no_signal_file_path_found
signal_file_found_zero_rows
signal_file_found_header_only
signal_file_found_with_rows
signal_file_found_unparsed_text
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage12a_consolidated_forward_shadow_report \
  --long-signal-csv "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/XAUUSD_DryRun_v2_regime_shadow_signals.csv"

cat data/reports/stage12a_consolidated_forward_shadow_report/stage12a_consolidated_forward_shadow_report.md
```

## Expected current result

If the EA file still contains only BOM:

```text
long_signal_file_found = True
long_signal_rows_available = False
state = signal_file_found_zero_rows
```

That means:

```text
EA file exists
no qualifying signal row has been logged yet
observe only
```

## Hard rule

Report only. No EA change, no automatic trading, no paper/live authorization.
