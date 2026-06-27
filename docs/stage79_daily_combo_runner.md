# Stage79 Daily Combo Runner

Stage79 is a local operator combo for the validated XAUUSD K06 / portfolio observer workflow.

It is not a research stage and cannot authorize orders.

## What it runs

Default sequence:

1. Stage67D6 macro/source rebuild
2. Stage67E central-bank changes mapper and macro refresh
3. Stage76E K06 observer CSV mode fix
4. Stage78 portfolio observer bridge

It then verifies the generated observer CSV files:

- `data/mt5_bridge/k06_observer_signal.csv`
- `data/mt5_bridge/portfolio_observer_signal.csv`

Optionally, it can copy both CSVs into the MT5 `MQL5/Files` folder if `mt5_files_dir` is set and `--copy-to-mt5-files` is passed.

## Daily usage

When source data has been refreshed:

```bash
python3 app/stage79_daily_combo_runner.py \
  --root . \
  --config configs/stage79_daily_combo_runner.json \
  --out reports/stage79_daily_combo_runner
```

When source data has not changed and only observer CSVs need rebuilding:

```bash
python3 app/stage79_daily_combo_runner.py \
  --root . \
  --config configs/stage79_daily_combo_runner.json \
  --out reports/stage79_daily_combo_runner \
  --skip-refresh
```

To copy CSVs to MT5 automatically, set `mt5_files_dir` in the config and run:

```bash
python3 app/stage79_daily_combo_runner.py \
  --root . \
  --config configs/stage79_daily_combo_runner.json \
  --out reports/stage79_daily_combo_runner \
  --copy-to-mt5-files
```

## Hard blocks

- No automated order
- No paper order
- No broker connection
- No order send in EA
- Observer-only EA
- No paper-live
- No live
- No order authorization from Stage79
- No threshold tuning from daily combo
