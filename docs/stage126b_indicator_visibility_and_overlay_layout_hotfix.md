# Stage126B indicator visibility and overlay layout hotfix

This patch writes the Stage124F rule-8 and Stage126 rule-9 status-only indicators to both the repository and MT5 indicator folders.

It does not replace `Unified_ObserverOnly_EA`, does not call `OrderSend`, does not use `CTrade`, and does not enable paper/live trading.

Runtime layout:

- Keep `Unified_ObserverOnly_EA` on the chart.
- Remove `Stage124E` from the chart.
- Attach `XAUUSD_Stage124F_Rule8OverlayIndicator` as an indicator.
- Attach `XAUUSD_Stage126_Rule9FrontierOverlayIndicator` as an indicator.

Default y offsets:

- Rule 08 / Stage124F: `InpY=360`
- Rule 09 / Stage126: `InpY=450`

If an indicator is not visible in Navigator, open the `.mq5` file from MT5 `MQL5/Indicators` or `MQL5/Indicators/Advisors/XAUUSD` in MetaEditor, compile it, then refresh Navigator.
