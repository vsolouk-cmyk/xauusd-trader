# Stage166E Event Data Failover Intake

## Why this exists

GDELT timed out even with VPN in the user's environment. Stage166E removes GDELT from the critical path and makes event/news intake source-agnostic:

1. Manual current-event CSV if the user has urgent high-impact events.
2. Browser/downloaded local raw files placed in `~/Downloads/xauusd_fundamental_event_inbox/news_raw`.
3. Optional bounded network fetch using both `urllib` and `curl`, with short timeouts.

## What it produces

- `stage166e_normalized_external_events.csv`
- `stage166e_current_event_intraday_panel.csv`
- `stage166e_event_panel_health.json`
- Stage166-compatible panel at:
  `reports/stage166_current_event_shock_overlay/stage166_current_event_intraday_panel.csv`

## Interpretation

- `EXTERNAL_EVENT_PANEL_HISTORICALLY_TRAINABLE`: enough historical external events exist for Stage167-style discovery.
- `CURRENT_EVENT_PANEL_READY_NOT_HISTORICAL_TRAINABLE`: useful for current regime guard, not enough for historical discovery.
- `EXTERNAL_EVENT_INTAKE_FAILED_OR_EMPTY`: add manual/browser-downloaded files and rerun.

## Important limitation

Recent news data alone cannot backtest historical event-aware rules. For discovery, combine either a real historical event panel or Stage166D market-implied post-shock proxy. For operational gating, current news data is still useful.
