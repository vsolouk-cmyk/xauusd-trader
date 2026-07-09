# Stage166B Historical Current-Event Panel Rebuild

## Purpose

Stage167B proved that the current Stage166 event panel is not trainable: it has only a few recent event rows and no active event bars in the train segment. Stage166B rebuilds a historical current-event panel so event-aware discovery is actually event-aware.

## What it does

1. Reads AMarkets M5 bars to define the historical range and the 20% newest holdout split.
2. Loads optional local/manual event-history CSVs from the fundamental event inbox.
3. Optionally fetches GDELT DOC TimelineVolRaw history in large chunks for five gold-relevant profiles:
   - geopolitical escalation
   - de-escalation
   - macro policy hawkish
   - macro policy dovish
   - inflation / energy shock
4. Converts article-volume counts into normalized hourly shock scores.
5. Emits a dense hourly panel with the same schema expected by Stage167.
6. Runs a health gate: panel rows, train active-event bars, and nonzero shock coverage.

## Expected outputs

```text
reports/stage166b_historical_current_event_panel_rebuild/stage166b_historical_current_event_panel_rebuild_summary.json
reports/stage166b_historical_current_event_panel_rebuild/stage166b_normalized_historical_events.csv
reports/stage166b_historical_current_event_panel_rebuild/stage166b_current_event_intraday_panel.csv
reports/stage166b_historical_current_event_panel_rebuild/stage166b_fetch_status.csv
```

If `--write-stage166-compatible-panel` is used, it also writes:

```text
reports/stage166_current_event_shock_overlay/stage166_current_event_intraday_panel.csv
```

## Decision logic

- `STAGE166B_HISTORICAL_EVENT_PANEL_TRAINABLE_RUN_STAGE167_AGAIN`: use the new panel and rerun Stage167.
- `STAGE166B_EVENT_PANEL_STILL_NOT_TRAINABLE_DO_NOT_RUN_STAGE167`: do not run Stage167 as event-aware; inspect fetch status and add manual or alternate event history.

## Trading safety

This stage never authorizes demo or live orders.
