# Stage 17E PDH Forward Refresh Cycle

Generated UTC: `2026-06-11T07:43:17+00:00`
Tool version: `v1`

> Hard rule: research shadow cycle only. No EA change, no automatic trading, no paper/live authorization.

## Final decision
- final_decision: `REFRESH_CYCLE_ACTIVE_NO_SIGNAL_YET`

## Reasons
- Fresh broker-time data exists; no valid PDH breakout signal yet.

## Import step
- status: `ok`
- returncode: `0`
- files_imported: `2`
- rows_upserted: `1476708`
- before_latest_bar_utc: `2026-06-11T09:26:00+00:00`
- after_latest_bar_utc: `2026-06-11T10:41:00+00:00`
- latest_changed: `True`

## Stage17D collector step
- status: `ok`
- returncode: `0`
- stage17d_final_decision: `BROKER_FORWARD_ACTIVE_NO_SIGNAL_YET`
- m1_last_broker_time: `2026-06-11T10:41:00+00:00`
- latest_completed_m15_broker_time: `2026-06-11T10:30:00+00:00`
- collector_start_bar_time: `2026-06-11T09:15:00+00:00`
- data_after_collector_start: `True`

## Journal counts
- scan_candidates: `27`
- new_logged_this_run: `0`
- skipped_before_start: `27`
- late_detected_this_run: `0`
- resolved_this_run: `0`
- journal_rows: `0`
- valid_forward_rows: `0`
- open_valid_rows: `0`
- closed_valid_rows: `0`
- late_invalid_rows: `0`

## Closed valid forward metrics
- events: `0`
- total: `0.0`
- median: `0.0`
- pf: `0.0`
- dd: `0.0`

## Interpretation
- This cycle imports the AMarkets CSVs and then runs the Stage17D broker-time collector.
- A 24-hour cadence can still be too slow for an 8-hour horizon; late-detected signals are not forward proof.
- Valid forward evidence requires the signal to be logged before its exit target is known.
- No paper/live/order escalation is authorized.

## Output files
- json: `data/reports/stage17e_pdh_forward_refresh_cycle/stage17e_pdh_forward_refresh_cycle.json`
- md: `data/reports/stage17e_pdh_forward_refresh_cycle/stage17e_pdh_forward_refresh_cycle.md`
