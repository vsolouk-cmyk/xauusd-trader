# Stage124E Unified Combo 8-Rule Chart Status

Purpose: replace the temporary separate Stage124C/Stage124D visual check with one observer-only 8-rule status surface that displays the legacy 7 rules plus Stage124 as rule 08 on the chart.

This package writes:

- normalized 8-rule status table under `data/shadow_observer/` and `reports/`
- MT5 key/value chart-status CSV under `MQL5/Files` when `--write-mt5-csv` is used
- `XAUUSD_Stage124E_UnifiedCombo8RuleChartStatus.mq5` under the correct MT5 Advisors/XAUUSD path when `--write-mql5-ea` is used

It does not use `CTrade`, `OrderSend`, broker connections, paper-live, or live trading.
