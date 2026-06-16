# Stage 16C True-Forward Shadow Collector

Generated UTC: `2026-06-16T09:38:38+00:00`
Tool version: `v1`

> Hard rule: true-forward shadow collection only. No EA change, no automatic trading, no paper/live authorization.

## Collector boundary
- collector_start_utc: `2026-06-11T06:22:12+00:00`
- latest_m15_bar_utc: `2026-06-16T12:30:00+00:00`

## Research setup
- setup: `prev_day_low_sweep_rejection`
- side: `LONG` research direction
- sweep_depth_min: `1.62`
- reclaim_max: `1.55`
- macro context: `real_yield_10y_chg5_up`
- entry: `next M15 open`
- exit: `60 minutes after entry`

## Final decision
- final_decision: `TRUE_FORWARD_STARTED_NO_SIGNALS_YET`

## Reasons
- Collector state exists; no post-start signal has been logged yet.

## Counts
- scan_candidates: `1`
- new_logged_this_run: `0`
- skipped_before_collector_start: `1`
- resolved_this_run: `0`
- journal_rows: `0`
- valid_forward_rows: `0`
- closed_valid_forward_rows: `0`
- open_valid_forward_rows: `0`
- late_or_invalid_rows: `0`

## Status counts
- none

## Closed valid true-forward outcomes
| Events | Total | Avg | Median | WR | PF | DD |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## Evidence rule
- Signals with `event_utc <= collector_start_utc` are not true-forward.
- Signals detected after their `exit_target_utc` are marked invalid for forward proof.
- Closed true-forward outcomes are judged only after the journal records them before outcome is known.
- No paper/live/order escalation is authorized.

## Output files
- state_json: `data/reports/stage16c_true_forward_shadow_collector/stage16c_collector_state.json`
- journal_csv: `data/reports/stage16c_true_forward_shadow_collector/stage16c_true_forward_shadow_journal.csv`
- candidates_csv: `data/reports/stage16c_true_forward_shadow_collector/stage16c_scan_candidates.csv`
- json: `data/reports/stage16c_true_forward_shadow_collector/stage16c_true_forward_shadow_collector.json`
- md: `data/reports/stage16c_true_forward_shadow_collector/stage16c_true_forward_shadow_collector.md`
