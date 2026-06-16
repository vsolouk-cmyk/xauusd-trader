# Stage 17C Time-Basis and Session Robustness Audit

Generated UTC: `2026-06-11T07:31:00+00:00`
Tool version: `v1`

> Hard rule: research audit only. No EA change, no automatic trading, no paper/live authorization.

## Candidate
- variant: `pdh_breakout_continuation_long_h32_cool4`
- side: `LONG`
- behavior: `previous-day high breakout continuation`
- horizon_bars: `32`
- horizon_minutes: `480`
- cooldown_bars: `4`

## Clock audit
- m1_first_raw: `2022-05-01T23:01:00+00:00`
- m1_last_raw: `2026-06-11T09:26:00+00:00`
- generated_utc: `2026-06-11T07:31:00+00:00`
- latest_raw_minus_generated_hours: `1.916667`
- bar_clock_likely_broker_server_time: `True`

## Final decision
- final_decision: `TIME_OFFSET_AWARE_FORWARD_DESIGN_REQUIRED`

## Reasons
- Latest bar timestamp is ahead of report wall-clock UTC; MT5 CSV timestamps are likely broker/server time, not true UTC.
- Candidate survives at least one plausible clock shift, but forward collection still needs broker-time boundary handling.

## Time-shift robustness summary
| Shift hours | Events | Total x1 | Median x1 | PF x1 | DD x1 | PF x2 | PF x4 | Test20 events | Test20 total | Test20 PF | 2026 total | 2026 PF |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| -4.0 | 795 | 1164.69 | 0.34 | 1.225368 | -347.9 | 1.167107 | 1.05903 | 159 | 393.16 | 1.164636 | 234.04 | 1.154201 |
| -3.0 | 790 | 855.29 | 0.63 | 1.163464 | -336.43 | 1.107835 | 1.004568 | 158 | 360.72 | 1.154077 | 235.46 | 1.160455 |
| -2.0 | 791 | 909.27 | 0.37 | 1.178954 | -334.33 | 1.121225 | 1.014307 | 159 | 580.18 | 1.284349 | 375.75 | 1.295924 |
| -1.0 | 771 | 817.64 | 0.51 | 1.173426 | -258.52 | 1.113015 | 1.00158 | 155 | 498.39 | 1.265579 | 194.71 | 1.171901 |
| 0.0 | 758 | 1171.09 | 0.765 | 1.256304 | -295.03 | 1.192869 | 1.075642 | 152 | 717.93 | 1.377965 | 339.87 | 1.289658 |

## Interpretation
- If bar timestamps are ahead of wall-clock UTC, forward collectors must use broker-time boundaries or a calibrated offset.
- If the candidate only works under raw broker clock, that is not automatically wrong, but the system must explicitly declare broker-time execution logic.
- If shifted variants also work, the behavior is less dependent on exact timestamp convention.
- No paper/live/order authorization is granted.

## Output files
- summary_csv: `data/reports/stage17c_time_basis_session_robustness/stage17c_time_shift_summary.csv`
- trades_csv: `data/reports/stage17c_time_basis_session_robustness/stage17c_time_shift_trades.csv`
- json: `data/reports/stage17c_time_basis_session_robustness/stage17c_time_basis_session_robustness.json`
- md: `data/reports/stage17c_time_basis_session_robustness/stage17c_time_basis_session_robustness.md`
