# Stage 18E Shortlist Broker-Time Forward Shadow Collector

Generated wall UTC: `2026-06-16T09:39:26+00:00`
Tool version: `v1`

> Hard rule: shortlist research shadow only. No EA change, no automatic trading, no paper/live authorization.

## Clock and bar-time state
- clock_mode: `BROKER_BAR_TIME`
- m1_last_broker_time: `2026-06-16T12:18:00+00:00`
- latest_completed_m15_broker_time: `2026-06-16T12:15:00+00:00`
- collector_start_bar_time: `2026-06-11T10:45:00+00:00`
- data_after_collector_start: `True`

## Final decision
- final_decision: `SHORTLIST_FORWARD_SIGNAL_OPEN`

## Reasons
- At least one shortlist candidate has an open valid forward-shadow signal.

## Counts
- scan_candidates: `14`
- new_logged_this_run: `1`
- skipped_before_start: `13`
- late_detected_this_run: `0`
- resolved_this_run: `0`
- journal_rows: `1`

## Candidate summary
| Candidate | Variant | Family | Horizon min | Journal | Valid | Open | Closed | Late | Closed total | Closed median | Closed PF |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `C1_PDL_RECLAIM_H6` | `pdl_sweep_reclaim_long_sweep2.5_reclaim2_london_new_york_h6_cool4` | `pdl_sweep_reclaim_refined` | 90 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | 0.0 |
| `C2_ASIA_HIGH_NY_H48` | `asia_high_breakout_long_close2_range4-35_new_york_only_h48_cool0` | `asia_high_breakout_refined` | 720 | 1 | 1 | 1 | 0 | 0 | 0.0 | 0.0 | 0.0 |

## Status counts
- open_shadow: `1`

## Evidence rule
- Signals with `signal_dt <= collector_start_bar_time` are not forward evidence.
- Signals first detected after `exit_target_dt` are marked `not_forward_late_detected`.
- C1 has 90-minute horizon, so manual daily refresh is usually too slow for valid forward proof.
- C2 has 12-hour horizon, still preferably needs sub-12-hour refresh.
- No paper/live/order escalation is authorized.

## Output files
- state_json: `data/reports/stage18e_shortlist_forward_shadow_collector/stage18e_collector_state.json`
- journal_csv: `data/reports/stage18e_shortlist_forward_shadow_collector/stage18e_shortlist_forward_shadow_journal.csv`
- candidates_csv: `data/reports/stage18e_shortlist_forward_shadow_collector/stage18e_scan_candidates.csv`
- candidate_summary_csv: `data/reports/stage18e_shortlist_forward_shadow_collector/stage18e_candidate_summary.csv`
- json: `data/reports/stage18e_shortlist_forward_shadow_collector/stage18e_shortlist_forward_shadow_collector.json`
- md: `data/reports/stage18e_shortlist_forward_shadow_collector/stage18e_shortlist_forward_shadow_collector.md`
