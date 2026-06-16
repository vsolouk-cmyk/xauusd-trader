# Stage 5B Dry-run Log Validator v2

This patch updates only:

```text
app/stage5b_dryrun_log_validator.py
```

It does **not** change the deployed MT5 EA and does **not** authorize demo, paper, or live orders.

## Why v2 exists

The first validator used a preferred Stage 5B schema and comma-separated CSV assumptions. Real MT5/Wine CSV files may differ:

- file exists but is empty before the first market tick/log write;
- file has only a header;
- separator may be comma, semicolon, tab, or pipe;
- deployed EA may write native column names instead of the preferred future schema.

v2 treats these as diagnostics instead of automatically failing where safe. It still fails for real hard problems, such as rows with no usable time column or unparseable timestamps.

## Commands

Run on the real MT5 Common Files CSV:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage5b_dryrun_log_validator --csv "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/XAUUSD_DryRun_v1_signals.csv" --print-columns
```

Run strict mode later, after the real log format is stable:

```bash
python3 -m app.stage5b_dryrun_log_validator --csv "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/XAUUSD_DryRun_v1_signals.csv" --strict --print-columns
```

## Expected interpretation

- `PASS`: basic schema/consistency checks passed.
- `WARN`: tool/path/log is usable for inspection, but the log is not yet strong evidence; common before market opens or before first real signal/no-signal row.
- `FAIL`: do not rely on the log until the reported hard issue is fixed.

Stage 5B remains dry-run evidence collection only.
