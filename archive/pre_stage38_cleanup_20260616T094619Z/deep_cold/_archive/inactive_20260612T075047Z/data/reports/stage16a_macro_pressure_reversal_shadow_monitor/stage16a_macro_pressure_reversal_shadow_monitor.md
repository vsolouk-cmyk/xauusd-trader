# Stage 16A Macro Pressure/Reversal Forward-Shadow Monitor

Generated UTC: `2026-06-11T06:12:43+00:00`
Tool version: `v1`

> Hard rule: research shadow only. No EA change, no automatic trading, no paper/live authorization.

## Research setup
- setup: `prev_day_low_sweep_rejection`
- side: `LONG` research direction
- branch: `sweep_depth_ge_q50`
- regime: `reclaim_lt_q50`
- macro context: `real_yield_10y_chg5_up`
- interpretation: `pressure/reversal`, not classic bullish macro support

## Inputs
- db: `data/local/xauusd_local_store.sqlite`
- intraday_source: `m1_to_m15`
- m15_rows: `97633`
- scan_days: `120`
- sweep_depth_min: `1.62`
- reclaim_max: `1.55`
- buffer_usd: `0.2`

## Macro availability
- macro_status: `loaded`
- macro_source: `macro_daily_regime`
- real_yield_col: `real_yield_10y`
- macro_rows: `1613`
- reason: `preferred_daily_regime`

## Shadow status
- latest_bar_utc: `2026-06-09T11:45:00+00:00`
- latest_signal_status: `HISTORICAL_SIGNAL_IN_SCAN_WINDOW`
- latest_signal_utc: `2026-06-08T04:00:00+00:00`
- bars_since_latest_signal: `127`

## Counts
- technical_candidates_before_macro: `30`
- stage16a_macro_pressure_reversal_signals: `22`

## Latest signal
- event_utc: `2026-06-08 04:00:00+00:00`
- next_bar_theoretical_entry_utc: `2026-06-08 04:15:00+00:00`
- time_exit_target_utc: `2026-06-08 05:15:00+00:00`
- sweep_depth: `2.5599999999994907`
- reclaim_above_pdl: `1.1199999999998909`
- real_yield_10y: `2.21`
- real_yield_10y_chg5: `0.10000000000000009`
- authorization: `RESEARCH_SHADOW_ONLY_NO_ORDER`

## Interpretation rules
- This monitor can only create research shadow records.
- A signal here means: the validated research setup condition exists in data.
- It does not mean enter a trade.
- It does not authorize EA/paper/live orders.
- If the latest signal is historical, do not chase it.

## Output files
- signal_csv: `data/reports/stage16a_macro_pressure_reversal_shadow_monitor/stage16a_shadow_signals.csv`
- technical_candidates_csv: `data/reports/stage16a_macro_pressure_reversal_shadow_monitor/stage16a_technical_candidates_before_macro.csv`
- json: `data/reports/stage16a_macro_pressure_reversal_shadow_monitor/stage16a_macro_pressure_reversal_shadow_monitor.json`
- md: `data/reports/stage16a_macro_pressure_reversal_shadow_monitor/stage16a_macro_pressure_reversal_shadow_monitor.md`
