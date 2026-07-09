# Stage166D Offline Event Seed + Market-Implied Shock Panel

## Why this exists

Stage166B/166C proved that GDELT is not usable from the current environment: all historical fetches timed out and the generated event panel was all zeros. Stage167B correctly stopped because the event panel was not trainable.

Stage166D avoids another network dead end. It builds a Stage166-compatible event panel from two non-web sources:

1. Manual/current-event history CSV, when available.
2. A lagged market-implied post-shock proxy derived from AMarkets XAUUSD bars.

## How it works

1. Loads AMarkets M5 broker data and creates an hourly panel covering the full data period.
2. Reads optional manual event files from the event inbox, such as `manual_current_events.csv`.
3. Scores manual events by category, direction, severity, confidence, and decay window.
4. Detects extreme hourly XAUUSD shocks using train-only quantile thresholds, then shifts the shock state forward one hour to avoid same-hour lookahead.
5. Writes a Stage166-compatible panel that can be used by Stage167.
6. Emits a health decision indicating whether the panel is external-event-backed, market-implied-proxy-backed, or still not trainable.

## Manual event CSV schema

Create a file such as:

```text
~/Downloads/xauusd_fundamental_event_inbox/manual_current_events.csv
```

Columns:

```text
event_time_utc,event_end_utc,event_title,event_category,direction,severity_1_5,confidence_0_1,decay_hours,source,notes
```

Useful event categories:

- `geopolitical_escalation`
- `military_conflict`
- `sanctions`
- `systemic_risk`
- `deescalation`
- `ceasefire`
- `macro_policy_hawkish`
- `macro_policy_dovish`
- `inflation_energy_shock`
- `energy_shock`

Direction should be `LONG`, `SHORT`, or `NONE` from the perspective of gold.

## Decision meanings

- `STAGE166D_EXTERNAL_EVENT_PANEL_TRAINABLE_RERUN_STAGE167`: best case. Manual/external event history is usable.
- `STAGE166D_MARKET_IMPLIED_PROXY_TRAINABLE_RERUN_STAGE167_WITH_CAUTION`: usable only for post-shock regime discovery. It is not proof of external news edge.
- `STAGE166D_EVENT_PANEL_STILL_NOT_TRAINABLE_ADD_MANUAL_EVENT_HISTORY`: add manual event history or alternate local source before Stage167.

## Commercial caution

This stage does not authorize demo/live execution. If Stage167 passes using only market-implied proxy features, Stage168 must label the result as post-shock behavior, not news-predictive edge.
