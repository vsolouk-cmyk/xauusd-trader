# Stage36C — Event Risk / No-News Guard Scout

Stage36C starts the second distinct Stage36 thesis branch after Stage36B produced no strict session/regime candidate.

It compares simple event-risk and clean/no-news regimes using local OHLC and event tables. It is research-only and does not authorize EA, paper-live, or orders.

## Inputs

- `data/local/xauusd_local_store.sqlite`
- OHLC table, usually `bars`
- Event tables when available:
  - `news_events`
  - `numeric_shock_events`
  - `event_pipeline_staging`
  - `macro_events`

## Outputs

- `data/reports/stage36c_event_risk_guard_scout/stage36c_event_risk_guard_scout.md`
- `data/reports/stage36c_event_risk_guard_scout/stage36c_summary.json`
- `stage36c_candidate_summary.csv`
- `stage36c_event_regime_diagnostics.csv`
- `stage36c_strict_review_queue.csv`
- `stage36c_background_queue.csv`
- `stage36c_kill_or_repair_queue.csv`

## Decision rule

A strict review candidate only permits a stricter research review. It does not permit EA, paper-live, or orders.

If no strict candidate is found, move to the next Stage36 thesis branch quickly instead of mining unlimited variants inside this branch.
