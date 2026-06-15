# Stage33B-HF1 — Ledger Timestamp Column Fix

## Purpose

Fix Stage33B ledger normalization for the actual Stage32C dense forward ledger schema.

Stage32C writes signal timestamps as `entry_time`. The original Stage33B searched for generic timestamp columns such as `signal_ts_utc`, `timestamp`, or `ts_utc`, so it could report:

```text
ledger_available = False
ledger_rows > 0
ledger_column_map.error = missing_required_ledger_columns
```

This hotfix adds `entry_time`, `entry_time_utc`, and related aliases to the timestamp resolver.

## Files

- `app/stage33b_pre_commercial_family_robustness_gate.py`
- `docs/STAGE33B_HF1_LEDGER_TIMESTAMP_COLUMN_FIX.md`

## Install

```bash
cd ~/Downloads
unzip xauusd_stage33b_hf1_ledger_timestamp_fix_patch.zip -d stage33b_hf1_patch

cd ~/Desktop/xauusd-trader
cp ~/Downloads/stage33b_hf1_patch/app/stage33b_pre_commercial_family_robustness_gate.py app/
cp ~/Downloads/stage33b_hf1_patch/docs/STAGE33B_HF1_LEDGER_TIMESTAMP_COLUMN_FIX.md docs/
```

## Test

```bash
cd ~/Desktop/xauusd-trader
python3 -m py_compile app/stage33b_pre_commercial_family_robustness_gate.py
python3 -m app.stage33b_pre_commercial_family_robustness_gate
```

## Expected fix

The new `stage33b_summary.json` should show:

```text
ledger_available = true
normalized_ledger_rows > 0
ledger_column_map.timestamp_col = entry_time
```

No EA, paper-live, or order routing is authorized by this hotfix.
