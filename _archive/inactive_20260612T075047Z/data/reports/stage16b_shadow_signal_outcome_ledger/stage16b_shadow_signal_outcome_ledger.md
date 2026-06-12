# Stage 16B Shadow Signal Outcome Ledger

Generated UTC: `2026-06-11T06:16:42+00:00`
Tool version: `v1`

> Hard rule: research outcome ledger only. No EA change, no automatic trading, no paper/live authorization.

## Inputs
- db: `data/local/xauusd_local_store.sqlite`
- signals_path: `data/reports/stage16a_macro_pressure_reversal_shadow_monitor/stage16a_shadow_signals.csv`
- cost_usd: `0.35`
- m1_first: `2022-05-01T23:01:00+00:00`
- m1_last: `2026-06-09T11:44:00+00:00`
- signals_loaded: `22`

## Final decision
- final_decision: `RECENT_HISTORY_SHADOW_POSITIVE_NOT_FORWARD_PROOF`

## Reasons
- Recent-history shadow outcomes are positive, but they are retrospective scans, not true-forward evidence.
- Next step is scheduled true-forward shadow collection only.

## Status counts
- closed_time_exit: `21`
- missing_m1_path: `1`

## Closed recent-history shadow outcomes
| Events | Total | Avg | Median | WR | PF | DD | Pos days |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 21 | 46.24 | 2.201905 | 6.05 | 0.666667 | 1.480017 | -37.81 | 9/13 |

## Latest closed shadow outcome
- event_utc: `2026-06-08 04:00:00+00:00`
- entry_utc: `2026-06-08 04:15:00+00:00`
- exit_target_utc: `2026-06-08 05:15:00+00:00`
- entry_price: `4313.07`
- exit_price: `4319.47`
- gross_ret: `6.4`
- net_ret_x1: `6.05`
- mfe: `7.05`
- mae: `9.87`
- sweep_depth: `2.5599999999994907`
- reclaim_above_pdl: `1.1199999999998909`
- real_yield_10y_chg5: `0.1`
- status: `closed_time_exit`

## Evidence classification
- Outcomes in this report are recent-history shadow outcomes because Stage 16A scanned an existing window.
- They are useful for sanity-checking the monitor implementation.
- They are not true-forward proof.
- True-forward evidence begins only after the monitor is scheduled and future signals are logged before outcome is known.

## Output files
- outcomes_csv: `data/reports/stage16b_shadow_signal_outcome_ledger/stage16b_shadow_outcome_ledger.csv`
- closed_csv: `data/reports/stage16b_shadow_signal_outcome_ledger/stage16b_closed_recent_history_outcomes.csv`
- json: `data/reports/stage16b_shadow_signal_outcome_ledger/stage16b_shadow_signal_outcome_ledger.json`
- md: `data/reports/stage16b_shadow_signal_outcome_ledger/stage16b_shadow_signal_outcome_ledger.md`
