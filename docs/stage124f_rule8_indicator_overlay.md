# Stage124F Rule-08 Same-Chart Indicator Overlay

Purpose: keep the existing `Unified_ObserverOnly_EA` seven-rule EA running and add Stage124/SPDR as rule 08 on the **same chart** through a custom indicator overlay.

Why indicator, not another EA:

- MT5 allows only one EA per chart.
- The existing seven-rule EA already shows detailed active/failure status.
- Stage124F therefore adds rule 08 as a visual overlay indicator, preserving the current EA and avoiding a second chart.

Outputs:

- `data/shadow_observer/stage124f_rule8_overlay_kv.csv`
- `reports/stage124f_rule8_indicator_overlay/stage124f_rule8_overlay_kv.csv`
- `MQL5/Files/xauusd_stage124f_rule8_overlay_kv.csv` when `--write-mt5-csv` is used
- `XAUUSD_Stage124F_Rule8OverlayIndicator.mq5` under MT5 Indicators when `--write-mql5-indicator` is used

Governance: no `OrderSend`, no `CTrade`, no broker, no paper/live, no EA replacement required.
