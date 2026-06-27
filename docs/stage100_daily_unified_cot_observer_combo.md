# Stage100 Daily Unified COT Observer Combo

## Purpose

Stage100 replaces the Stage88 daily combo after the Stage99 unified observer was expanded with the selected COT rule. It is the daily local operator runner for the 6-rule observer portfolio.

## Portfolio covered

- K06_RESILIENT_GOLD_VS_DXY_H120
- K03_SAFE_HAVEN_REALYIELD_H120
- K07_DXY_TREND_RELIEF_GOLD_TREND_H120
- S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120
- S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120
- C96_07_CB_SUPPORT_NOT_CROWDED_H120

## What it runs

1. Stage67D6 macro rebuild, unless `--skip-refresh` is used.
2. Stage67E central-bank mapper, unless `--skip-refresh` is used.
3. Stage95 COT official dataset builder with `--no-download`, unless `--skip-refresh` is used.
4. Stage99 unified observer COT expansion.
5. Validation of `data/mt5_bridge/unified_observer_signal.csv`.
6. Optional copy to MT5 `MQL5/Files` when `--copy-to-mt5-files` is passed.

## Operator modes

Use quick rebuild/copy when source data has not changed:

```bash
python3 app/stage100_daily_unified_cot_observer_combo.py \
  --root . \
  --config configs/stage100_daily_unified_cot_observer_combo.json \
  --out reports/stage100_daily_unified_cot_observer_combo \
  --skip-refresh \
  --copy-to-mt5-files
```

Use full local refresh when macro/COT source files have changed:

```bash
python3 app/stage100_daily_unified_cot_observer_combo.py \
  --root . \
  --config configs/stage100_daily_unified_cot_observer_combo.json \
  --out reports/stage100_daily_unified_cot_observer_combo \
  --copy-to-mt5-files
```

## Hard blocks

Stage100 is observer-only. It cannot authorize orders, cannot send broker commands, and does not change live/paper status.

