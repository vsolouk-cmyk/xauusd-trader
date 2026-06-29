# Stage126D fixed dashboard overlay hotfix

This patch fixes the visual overlay only.

- Keeps the 7-rule Unified_ObserverOnly_EA unchanged.
- Rewrites Stage124F and Stage126 indicators as bottom-left fixed-pixel dashboards.
- Re-renders on `CHARTEVENT_CHART_CHANGE` so chart zoom, resize, scroll, or timeframe changes do not leave stale font/position settings.
- Uses smaller default font and wider line spacing.
- Does not send orders, does not use CTrade, and does not modify any EA.

Recommended runtime:

- Keep `Unified_ObserverOnly_EA` on the chart.
- Remove Stage124E/Stage124D EAs.
- Attach these two indicators:
  - `XAUUSD_Stage124F_Rule8OverlayIndicator`
  - `XAUUSD_Stage126_Rule9FrontierOverlayIndicator`
