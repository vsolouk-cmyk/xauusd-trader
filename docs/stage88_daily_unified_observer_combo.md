# Stage88 Daily Unified Observer Combo

## Purpose
Stage88 replaces the earlier two-CSV observer routine with one daily operational path:

- rebuild/update macro inputs when requested;
- rebuild the Stage87 unified observer bridge;
- validate `data/mt5_bridge/unified_observer_signal.csv`;
- optionally copy it directly to MT5 `MQL5/Files`.

It is observer-only. It does not authorize orders, broker connection, paper-live, or live trading.

## Default MT5 files directory

```text
/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files/
```

## Full daily run

Use this after updating source macro files.

```bash
cd /Users/vahid/Desktop/xauusd-trader

python3 app/stage88_daily_unified_observer_combo.py \
  --root . \
  --config configs/stage88_daily_unified_observer_combo.json \
  --out reports/stage88_daily_unified_observer_combo \
  --copy-to-mt5-files
```

## Fast run

Use this when source files have not changed and only the unified observer CSV must be rebuilt/copied.

```bash
cd /Users/vahid/Desktop/xauusd-trader

python3 app/stage88_daily_unified_observer_combo.py \
  --root . \
  --config configs/stage88_daily_unified_observer_combo.json \
  --out reports/stage88_daily_unified_observer_combo \
  --skip-refresh \
  --copy-to-mt5-files
```

## Outputs

```text
reports/stage88_daily_unified_observer_combo/stage88_daily_unified_observer_combo_summary.json
reports/stage88_daily_unified_observer_combo/stage88_daily_unified_observer_combo_report.md
data/mt5_bridge/unified_observer_signal.csv
```

## Hard blocks

- `NO_AUTOMATED_ORDER`
- `NO_PAPER_ORDER`
- `NO_BROKER_CONNECTION`
- `NO_ORDER_SEND_IN_EA`
- `OBSERVER_ONLY_EA`
- `NO_PAPER_LIVE`
- `NO_LIVE`
- `NO_ORDER_AUTHORIZATION_FROM_STAGE88`
- `NO_THRESHOLD_TUNING_FROM_DAILY_UNIFIED_COMBO`

## Operator note

The unified EA is not a daily artifact. After it is compiled successfully, only this CSV is refreshed daily:

```text
data/mt5_bridge/unified_observer_signal.csv
```
