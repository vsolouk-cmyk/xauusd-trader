# Stage 17D Broker-Time Forward Shadow Collector

Generated wall UTC: `2026-06-16T09:39:04+00:00`
Tool version: `v1`

> Hard rule: broker-time research shadow collection only. No EA change, no automatic trading, no paper/live authorization.

## Candidate
- variant: `pdh_breakout_continuation_long_h32_cool4`
- side: `LONG`
- clock_mode: `BROKER_BAR_TIME`
- horizon_bars: `32`
- horizon_minutes: `480`
- cooldown_bars: `4`
- close_above_pdh: `0.8`
- cost_usd: `0.35`

## Bar-time state
- m1_last_broker_time: `2026-06-16T12:18:00+00:00`
- latest_completed_m15_broker_time: `2026-06-16T12:15:00+00:00`
- collector_start_bar_time: `2026-06-11T09:15:00+00:00`
- data_after_collector_start: `True`

## Final decision
- final_decision: `BROKER_FORWARD_SIGNAL_OPEN`

## Reasons
- A valid broker-time forward shadow signal is open/pending resolution.

## Counts
- scan_candidates: `23`
- new_logged_this_run: `1`
- skipped_before_start: `22`
- late_detected_this_run: `0`
- resolved_this_run: `0`
- journal_rows: `1`
- valid_forward_rows: `1`
- open_valid_rows: `1`
- closed_valid_rows: `0`
- late_invalid_rows: `0`

## Status counts
- open_shadow: `1`

## Closed valid forward outcomes
| Events | Total | Avg | Median | WR | PF | DD |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## Evidence rule
- This collector uses broker bar time, not wall-clock UTC, for forward boundaries.
- Signals with `signal_dt <= collector_start_bar_time` are not forward evidence.
- Signals first detected after `exit_target_dt` are marked `not_forward_late_detected`.
- Because the horizon is 8 hours, a 24-hour refresh cadence will often create late-detected invalid records.
- No paper/live/order escalation is authorized.

## Output files
- state_json: `data/reports/stage17d_broker_time_forward_shadow_collector/stage17d_collector_state.json`
- journal_csv: `data/reports/stage17d_broker_time_forward_shadow_collector/stage17d_broker_time_forward_shadow_journal.csv`
- candidates_csv: `data/reports/stage17d_broker_time_forward_shadow_collector/stage17d_scan_candidates.csv`
- json: `data/reports/stage17d_broker_time_forward_shadow_collector/stage17d_broker_time_forward_shadow_collector.json`
- md: `data/reports/stage17d_broker_time_forward_shadow_collector/stage17d_broker_time_forward_shadow_collector.md`
