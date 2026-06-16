# Stage 18A Unified Shadow Ops Cycle

Generated UTC: `2026-06-16T09:32:00+00:00`
Tool version: `v2_with_stage18e`

> Hard rule: unified research-shadow operations only. No EA change, no automatic trading, no paper/live authorization.

## Final decision
- final_decision: `UNIFIED_FORWARD_SIGNAL_OPEN`

## Reasons
- At least one active candidate has open valid forward-shadow signal(s): open_total=2.

## Import once
- import_status: `ok`
- files_imported: `2`
- rows_upserted: `1481006`
- before_latest_bar_utc: `2026-06-16T12:18:00+00:00`
- after_latest_bar_utc: `2026-06-16T12:18:00+00:00`
- latest_changed: `False`

## Candidate A — Stage16C macro pressure/reversal sweep
- command_status: `ok`
- final_decision: `TRUE_FORWARD_STARTED_NO_SIGNALS_YET`
- counts: `{'scan_candidates': 1, 'new_logged_this_run': 0, 'skipped_before_collector_start': 1, 'resolved_this_run': 0, 'journal_rows': 0, 'valid_forward_rows': 0, 'closed_valid_forward_rows': 0, 'open_valid_forward_rows': 0, 'late_or_invalid_rows': 0, 'status_counts': {}}`

## Candidate B — Stage17D PDH breakout continuation
- command_status: `ok`
- final_decision: `BROKER_FORWARD_SIGNAL_OPEN`
- bar_state: `{'m1_first_broker_time': '2022-05-01T23:01:00+00:00', 'm1_last_broker_time': '2026-06-16T12:18:00+00:00', 'latest_completed_m15_broker_time': '2026-06-16T12:15:00+00:00', 'collector_start_bar_time': '2026-06-11T09:15:00+00:00', 'data_after_collector_start': True}`
- counts: `{'scan_candidates': 23, 'new_logged_this_run': 1, 'skipped_before_start': 22, 'late_detected_this_run': 0, 'resolved_this_run': 0, 'journal_rows': 1, 'valid_forward_rows': 1, 'open_valid_rows': 1, 'closed_valid_rows': 0, 'late_invalid_rows': 0, 'status_counts': {'open_shadow': 1}}`

## Candidate C/D — Stage18E shortlist collector
- command_status: `ok`
- final_decision: `SHORTLIST_FORWARD_SIGNAL_OPEN`
- bar_state: `{'m1_first_broker_time': '2022-05-01T23:01:00+00:00', 'm1_last_broker_time': '2026-06-16T12:18:00+00:00', 'latest_completed_m15_broker_time': '2026-06-16T12:15:00+00:00', 'collector_start_bar_time': '2026-06-11T10:45:00+00:00', 'data_after_collector_start': True}`
- counts: `{'scan_candidates': 14, 'new_logged_this_run': 1, 'skipped_before_start': 13, 'late_detected_this_run': 0, 'resolved_this_run': 0, 'journal_rows': 1, 'status_counts': {'open_shadow': 1}}`

### Stage18E candidate summary
| Candidate | Variant | Family | Horizon min | Journal | Valid | Open | Closed | Late | Closed total | Closed PF |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `C1_PDL_RECLAIM_H6` | `pdl_sweep_reclaim_long_sweep2.5_reclaim2_london_new_york_h6_cool4` | `pdl_sweep_reclaim_refined` | 90 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0.0 |
| `C2_ASIA_HIGH_NY_H48` | `asia_high_breakout_long_close2_range4-35_new_york_only_h48_cool0` | `asia_high_breakout_refined` | 720 | 1 | 1 | 1 | 0 | 0 | 0.0 | 0.0 |

## Interpretation
- Stage18A v2 is now the preferred manual loop: import once, then run Stage16C, Stage17D, and Stage18E.
- Stage18E adds only the Stage18D de-duplicated shortlist, not all Stage18C promotions.
- Signals remain research-shadow observations only.
- No paper/live/order escalation is authorized.

## Output files
- json: `data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.json`
- md: `data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.md`
- Stage16C report: `data/reports/stage16c_true_forward_shadow_collector/stage16c_true_forward_shadow_collector.md`
- Stage17D report: `data/reports/stage17d_broker_time_forward_shadow_collector/stage17d_broker_time_forward_shadow_collector.md`
- Stage18E report: `data/reports/stage18e_shortlist_forward_shadow_collector/stage18e_shortlist_forward_shadow_collector.md`
- Import report: `data/reports/stage16e_amarkets_csv_refresh_cycle/stage16e_amarkets_csv_refresh_cycle.md`
