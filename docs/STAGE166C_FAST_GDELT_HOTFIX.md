# Stage166C Fast GDELT Historical Event Panel Hotfix

Purpose: keep Stage166B's historical event-panel logic, but prevent long blocking runs when GDELT is slow or blocked.

## What changed

- Replaces sequential GDELT fetch with bounded parallel fetch using `ThreadPoolExecutor`.
- Lowers default GDELT timeout from 25s to 8s.
- Adds `--gdelt-max-workers` for parallelism.
- Adds `--gdelt-max-queries` to cap newest-first fetch tasks during quick probes.
- Fixes the pandas `'d' is deprecated` warning by using `1D`.
- Keeps trading disabled: no MT5 KV writes and no demo/live release.

## Recommended use

First run a bounded quick probe. If it returns enough event points and trainable health, rerun Stage167. If it does not, do not spend time on repeated full-history GDELT fetches; add a local/manual news-event CSV or alternate source.

## Output expectation

The key files are unchanged:

- `reports/stage166b_historical_current_event_panel_rebuild/stage166b_historical_current_event_panel_rebuild_summary.json`
- `reports/stage166b_historical_current_event_panel_rebuild/stage166b_fetch_status.csv`
- `reports/stage166b_historical_current_event_panel_rebuild/stage166b_current_event_intraday_panel.csv`

The important health fields are:

- `event_panel_health.event_overlay_trainable`
- `event_panel_health.train_active_event_bars`
- `gdelt_fetch_meta.fetch_ok_count`
- `gdelt_fetch_meta.fetch_point_count`
