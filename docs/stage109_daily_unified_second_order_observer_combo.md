# Stage109 Daily Unified Second-Order Observer Combo

## Role
Stage109 is the local daily operator combo after Stage108. It refreshes or reuses macro/COT inputs, runs the seven-rule unified observer bridge, validates the exported `unified_observer_signal.csv`, and optionally copies that CSV to the configured MT5 `MQL5/Files` directory.

## Seven-rule observer portfolio
- `K06_RESILIENT_GOLD_VS_DXY_H120`
- `K03_SAFE_HAVEN_REALYIELD_H120`
- `K07_DXY_TREND_RELIEF_GOLD_TREND_H120`
- `S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120`
- `S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120`
- `C96_07_CB_SUPPORT_NOT_CROWDED_H120`
- `S105_03_COT_DECROWDING_CB_SUPPORT_RY_RELIEF_H120`

## Child stages
- Stage67D6 macro rebuild
- Stage67E central-bank mapper
- Stage95 official COT dataset builder with `--no-download`
- Stage108 unified observer second-order expansion

Use `--skip-refresh` when source files have not changed and only the Stage108 observer CSV must be rebuilt/copied.

## Output
- `data/mt5_bridge/unified_observer_signal.csv`
- `reports/stage109_daily_unified_second_order_observer_combo/stage109_daily_unified_second_order_observer_combo_summary.json`
- `reports/stage109_daily_unified_second_order_observer_combo/stage109_daily_unified_second_order_observer_combo_report.md`

## Hard blocks
Stage109 cannot authorize orders, broker connection, paper-live, or live trading. It validates that the CSV remains `OBSERVER_ONLY_NO_TRADE`, `order_authorized=false`, and `broker_connection_allowed=false`.
