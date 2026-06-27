# Stage79B MT5 Auto-Copy Config

This patch updates `configs/stage79_daily_combo_runner.json` with the verified MT5 `MQL5/Files` directory:

`/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files/`

Stage79 can now copy both observer CSV files directly into MT5:

- `k06_observer_signal.csv`
- `portfolio_observer_signal.csv`

Hard blocks remain unchanged:

- `NO_AUTOMATED_ORDER`
- `NO_PAPER_ORDER`
- `NO_BROKER_CONNECTION`
- `NO_ORDER_SEND_IN_EA`
- `OBSERVER_ONLY_EA`
- `NO_LIVE`

## Daily usage

After refreshing source files, run:

```bash
python3 app/stage79_daily_combo_runner.py \
  --root . \
  --config configs/stage79_daily_combo_runner.json \
  --out reports/stage79_daily_combo_runner \
  --copy-to-mt5-files
```

If source files have not changed and only observer CSVs must be rebuilt/copied, run:

```bash
python3 app/stage79_daily_combo_runner.py \
  --root . \
  --config configs/stage79_daily_combo_runner.json \
  --out reports/stage79_daily_combo_runner \
  --skip-refresh \
  --copy-to-mt5-files
```
