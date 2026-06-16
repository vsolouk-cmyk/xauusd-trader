# Stage31G Exogenous Active-Suite Watchlist Status

Generated UTC: `2026-06-16T09:41:23.174895+00:00`

## Decision

```text
STAGE31G_LOW_CADENCE_WATCHLIST_REVIEW_ONLY
```

## Scope guardrails

- Research/shadow status only.
- No EA change, no automatic trading, no paper/live/order authorization.
- Consumes Stage31F/Stage31E reports only; no internet fetch is performed.
- A watchlist signal is an observation, not an instruction to trade.

## Summary

- reason: `Only the long lookback window has signals; cadence is too sparse for promotion.`
- short_recent_signal_rows: `0`
- mid_recent_signal_rows: `0`
- long_recent_signal_rows: `4`
- max_recent_signal_rows: `4`
- latest_recent_entry_ts: `2026-03-06 13:01:00+00:00`

## Stage31F run

```json
{
  "attempted": true,
  "returncode": 0,
  "stdout_tail": "{\"decision\": \"STAGE31F_LOW_CADENCE_WATCHLIST_REVIEW_ONLY\", \"lookbacks\": [336, 720, 2160, 4320]}\n",
  "stderr_tail": ""
}
```

## Cadence summary

| lookback_hours | stage31e_returncode | stage31e_decision | recent_signal_rows | recent_signal_gate_count | tracker_results | latest_recent_entry_ts | copied_md | copied_recent_signals_csv | copied_tracker_summary_csv |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 336 | 0 | STAGE31E_NO_RECENT_FORWARD_SHADOW_SIGNAL_RESEARCH_ONLY | 0 | 0 | 8 | nan | data/reports/stage31f_exogenous_tracker_cadence_audit/stage31e_lookback_336h.md | data/reports/stage31f_exogenous_tracker_cadence_audit/stage31e_lookback_336h_recent_signals.csv | data/reports/stage31f_exogenous_tracker_cadence_audit/stage31e_lookback_336h_tracker_summary.csv |
| 720 | 0 | STAGE31E_NO_RECENT_FORWARD_SHADOW_SIGNAL_RESEARCH_ONLY | 0 | 0 | 8 | nan | data/reports/stage31f_exogenous_tracker_cadence_audit/stage31e_lookback_720h.md | data/reports/stage31f_exogenous_tracker_cadence_audit/stage31e_lookback_720h_recent_signals.csv | data/reports/stage31f_exogenous_tracker_cadence_audit/stage31e_lookback_720h_tracker_summary.csv |
| 2160 | 0 | STAGE31E_NO_RECENT_FORWARD_SHADOW_SIGNAL_RESEARCH_ONLY | 0 | 0 | 8 | nan | data/reports/stage31f_exogenous_tracker_cadence_audit/stage31e_lookback_2160h.md | data/reports/stage31f_exogenous_tracker_cadence_audit/stage31e_lookback_2160h_recent_signals.csv | data/reports/stage31f_exogenous_tracker_cadence_audit/stage31e_lookback_2160h_tracker_summary.csv |
| 4320 | 0 | STAGE31E_FORWARD_SHADOW_ACTIVE_SIGNAL_REVIEW_ONLY | 4 | 8 | 8 | 2026-03-06 13:01:00+00:00 | data/reports/stage31f_exogenous_tracker_cadence_audit/stage31e_lookback_4320h.md | data/reports/stage31f_exogenous_tracker_cadence_audit/stage31e_lookback_4320h_recent_signals.csv | data/reports/stage31f_exogenous_tracker_cadence_audit/stage31e_lookback_4320h_tracker_summary.csv |

## Interpretation

- Low-cadence watchlist status should not change operational behavior.
- Integration into active reporting is for visibility only.
- Promotion would require sustained forward-shadow evidence in short/mid lookbacks.

## Output files

- `data/reports/stage31g_exogenous_active_suite_watchlist/stage31g_exogenous_active_suite_watchlist.json`
- `data/reports/stage31g_exogenous_active_suite_watchlist/stage31g_exogenous_active_suite_watchlist.md`
- `data/reports/stage31g_exogenous_active_suite_watchlist/stage31g_cadence_summary.csv`
