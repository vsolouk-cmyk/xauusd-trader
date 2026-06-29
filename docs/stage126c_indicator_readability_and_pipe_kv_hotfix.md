# Stage126C indicator readability and pipe-KV hotfix

This hotfix updates the Stage124F rule-8 and Stage126 rule-9 indicators only.

It fixes two operational issues:

1. The overlay text was too large and line spacing was too tight.
2. Stage126 could read a KV file but show `UNKNOWN` because Stage126 writes pipe-separated KV while the prior indicator expected comma-separated KV.

Runtime layout:

- Keep `Unified_ObserverOnly_EA` on the chart.
- Attach `XAUUSD_Stage124F_Rule8OverlayIndicator` as an indicator.
- Attach `XAUUSD_Stage126_Rule9FrontierOverlayIndicator` as an indicator.

Defaults:

- Rule 08 / Stage124F: `InpY=430`, `InpFontSize=7`, `InpLineHeight=22`
- Rule 09 / Stage126: `InpY=540`, `InpFontSize=7`, `InpLineHeight=22`

Both indicators support pipe and comma KV status files.

No EA is replaced. No `OrderSend`, no `CTrade`, no paper/live path.
