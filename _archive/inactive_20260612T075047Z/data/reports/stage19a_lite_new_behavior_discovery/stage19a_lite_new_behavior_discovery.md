# Stage 19A Lite New Behavior Discovery

Generated UTC: `2026-06-11T12:29:53+00:00`
Tool version: `v1`

> Hard rule: research discovery only. M15 proxy replay only. No EA change, no automatic trading, no paper/live authorization.

## Purpose
- Continue discovery without rerunning slow Stage18C-style exhaustive grids.
- Explore behavior families less redundant with current active candidates.
- Promote only promising M15-proxy candidates to later exact M1 replay.

## Inputs
- db: `data/local/xauusd_local_store.sqlite`
- m1_rows: `1532269`
- m15_rows: `102417`
- h1_rows: `25769`
- m1_first: `2022-05-01T23:01:00+00:00`
- m1_last: `2026-06-11T14:24:00+00:00`
- cost_usd: `0.35`
- buffer_usd: `0.2`
- variants_tested: `144`
- fast: `False`

## Final decision
- final_decision: `NEW_BEHAVIOR_CANDIDATES_FOR_EXACT_REPLAY`

## Counts
- promoted_to_stage19b: `1`
- lite_watchlist: `9`

## Top variants
| Rank | Variant | Family | Side | Decision | Events | Freq/mo | PF x1 | Median x1 | Total x1 | PF x4 | Test20 events | Test20 total | Test20 PF | 2026 total | 2026 PF | Score |
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | `compression_expansion_breakout_long_comp0.75_h8` | `compression_expansion_breakout_long` | LONG | `PROMOTE_STAGE19B_EXACT_REPLAY` | 134 | 2.913043 | 1.347901 | 0.725 | 138.83 | 0.995992 | 27 | 70.44 | 1.395042 | 41.31 | 1.247425 | 6.46684 |
| 2 | `london_ny_handoff_continuation_short_bias2_h8` | `london_ny_handoff_continuation_short` | SHORT | `KEEP_LITE_WATCHLIST` | 351 | 7.02 | 1.187452 | -0.52 | 311.7 | 0.969645 | 71 | 331.81 | 1.484918 | 134.38 | 1.234075 | 5.866357 |
| 3 | `compression_expansion_breakout_long_comp0.75_h16` | `compression_expansion_breakout_long` | LONG | `KEEP_LITE_WATCHLIST` | 125 | 2.717391 | 1.202584 | 1.56 | 119.18 | 0.9812 | 25 | 6.85 | 1.020779 | -72.78 | 0.779227 | 5.551528 |
| 4 | `london_ny_handoff_continuation_short_bias3_h8` | `london_ny_handoff_continuation_short` | SHORT | `KEEP_LITE_WATCHLIST` | 304 | 6.08 | 1.191879 | -0.64 | 293.2 | 0.984795 | 61 | 192.99 | 1.298566 | 102.74 | 1.178971 | 5.300797 |
| 5 | `london_ny_handoff_continuation_short_bias2_h24` | `london_ny_handoff_continuation_short` | SHORT | `KEEP_LITE_WATCHLIST` | 245 | 4.9 | 1.185251 | -0.85 | 347.52 | 1.044781 | 49 | 330.38 | 1.427854 | 73.88 | 1.117004 | 4.581209 |
| 6 | `london_ny_handoff_continuation_short_bias1_h8` | `london_ny_handoff_continuation_short` | SHORT | `KEEP_LITE_WATCHLIST` | 392 | 7.84 | 1.132111 | -0.57 | 243.74 | 0.919297 | 79 | 165.27 | 1.194252 | 61.63 | 1.095279 | 4.316231 |
| 7 | `london_ny_handoff_continuation_short_bias2_h16` | `london_ny_handoff_continuation_short` | SHORT | `KEEP_LITE_WATCHLIST` | 245 | 4.9 | 1.093498 | -0.88 | 165.5 | 0.952039 | 49 | 312.75 | 1.397744 | 12.1 | 1.019028 | 3.809261 |
| 8 | `london_ny_handoff_continuation_short_bias3_h24` | `london_ny_handoff_continuation_short` | SHORT | `KEEP_LITE_WATCHLIST` | 210 | 4.2 | 1.156635 | -1.14 | 269.98 | 1.026809 | 42 | 89.86 | 1.124934 | -6.31 | 0.990007 | 3.305239 |
| 9 | `london_ny_handoff_continuation_short_bias1_h16` | `london_ny_handoff_continuation_short` | SHORT | `KEEP_LITE_WATCHLIST` | 275 | 5.5 | 1.068408 | -0.7 | 133.7 | 0.926531 | 55 | 180.11 | 1.195995 | -75.42 | 0.895745 | 3.054913 |
| 10 | `london_ny_handoff_continuation_short_bias1_h24` | `london_ny_handoff_continuation_short` | SHORT | `KEEP_LITE_WATCHLIST` | 275 | 5.5 | 1.110962 | -0.76 | 237.81 | 0.97783 | 55 | 146.91 | 1.153728 | -48.72 | 0.935387 | 2.833897 |
| 11 | `compression_expansion_breakout_short_comp0.55_h32` | `compression_expansion_breakout_short` | SHORT | `REJECT_LITE_WEAK` | 13 | 1.0 | 2.08112 | 5.45 | 67.57 | 1.78865 | 3 | 42.75 | 4.882834 | 31.07 | 999.0 | 16.493025 |
| 12 | `compression_expansion_breakout_long_comp0.65_h16` | `compression_expansion_breakout_long` | LONG | `REJECT_LITE_WEAK` | 47 | 1.678571 | 1.831019 | 2.01 | 140.01 | 1.48226 | 10 | 133.61 | 3.946196 | 78.45 | 2.815552 | 13.540966 |
| 13 | `compression_expansion_breakout_long_comp0.55_h16` | `compression_expansion_breakout_long` | LONG | `REJECT_LITE_WEAK` | 11 | 1.1 | 1.606877 | 1.02 | 13.06 | 1.056343 | 3 | 20.88 | 6.340153 | 1.39 | 999.0 | 11.187617 |
| 14 | `compression_expansion_breakout_long_comp0.55_h8` | `compression_expansion_breakout_long` | LONG | `REJECT_LITE_WEAK` | 12 | 1.2 | 1.620573 | -0.88 | 16.47 | 1.117202 | 3 | 7.95 | 2.30972 | 4.06 | 999.0 | 7.458112 |
| 15 | `compression_expansion_breakout_long_comp0.65_h8` | `compression_expansion_breakout_long` | LONG | `REJECT_LITE_WEAK` | 48 | 1.714286 | 1.115781 | 0.42 | 20.0 | 0.84739 | 10 | 44.83 | 1.826969 | 18.28 | 1.358713 | 5.896856 |
| 16 | `asia_low_fakeout_reversal_long_fake1_range4-35_h4` | `asia_low_fakeout_reversal_long` | LONG | `REJECT_LITE_WEAK` | 467 | 9.729167 | 1.005733 | -0.16 | 6.26 | 0.645908 | 94 | 175.44 | 1.737887 | 38.56 | 2.917454 | 4.605913 |
| 17 | `pdh_sweep_reject_short_sweep3.5_reject2_london_new_york_h4` | `pdh_sweep_reject_short` | SHORT | `REJECT_LITE_WEAK` | 61 | 2.103448 | 0.700444 | -1.75 | -84.99 | 0.535773 | 13 | 52.59 | 2.43141 | -9.68 | 0.902419 | 4.480075 |
| 18 | `asia_low_fakeout_reversal_long_fake1.5_range4-35_h4` | `asia_low_fakeout_reversal_long` | LONG | `REJECT_LITE_WEAK` | 344 | 7.166667 | 0.995782 | -0.28 | -3.84 | 0.6705 | 69 | 96.14 | 1.444619 | 38.56 | 2.917454 | 4.404234 |
| 19 | `compression_expansion_breakout_long_comp0.75_h32` | `compression_expansion_breakout_long` | LONG | `REJECT_LITE_WEAK` | 125 | 2.717391 | 1.049118 | 0.63 | 54.52 | 0.934604 | 25 | 94.63 | 1.1961 | -27.84 | 0.942308 | 4.219745 |
| 20 | `compression_expansion_breakout_short_comp0.55_h8` | `compression_expansion_breakout_short` | SHORT | `REJECT_LITE_WEAK` | 13 | 1.0 | 0.876332 | -1.42 | -6.15 | 0.653118 | 3 | 1.35 | 1.103448 | 9.28 | 999.0 | 3.853452 |
| 21 | `compression_expansion_breakout_long_comp0.65_h32` | `compression_expansion_breakout_long` | LONG | `REJECT_LITE_WEAK` | 47 | 1.678571 | 0.833936 | 0.61 | -80.8 | 0.745483 | 10 | 59.86 | 1.35795 | -35.3 | 0.780691 | 3.824265 |
| 22 | `pdh_sweep_reject_short_sweep3.5_reject1_london_new_york_h4` | `pdh_sweep_reject_short` | SHORT | `REJECT_LITE_WEAK` | 36 | 1.714286 | 0.568745 | -2.7 | -89.77 | 0.445348 | 8 | 31.31 | 1.946207 | 1.28 | 1.020218 | 3.604523 |
| 23 | `asia_low_fakeout_reversal_long_fake0.5_range4-35_h4` | `asia_low_fakeout_reversal_long` | LONG | `REJECT_LITE_WEAK` | 629 | 13.104167 | 0.940773 | -0.21 | -84.09 | 0.585173 | 126 | 113.56 | 1.294617 | 34.15 | 2.392741 | 3.493883 |
| 24 | `pdh_sweep_reject_short_sweep3.5_reject1_london_new_york_h6` | `pdh_sweep_reject_short` | SHORT | `REJECT_LITE_WEAK` | 36 | 1.714286 | 0.65184 | -1.81 | -93.46 | 0.545514 | 8 | 30.66 | 1.55393 | 30.09 | 1.392512 | 3.44132 |
| 25 | `london_ny_handoff_continuation_long_bias3_h24` | `london_ny_handoff_continuation_long` | LONG | `REJECT_LITE_WEAK` | 264 | 5.387755 | 1.035021 | -0.395 | 69.52 | 0.902482 | 53 | -50.4 | 0.94792 | 28.96 | 1.055199 | 3.358733 |
| 26 | `pdh_sweep_reject_short_sweep3.5_reject2_london_new_york_h6` | `pdh_sweep_reject_short` | SHORT | `REJECT_LITE_WEAK` | 60 | 2.068966 | 0.672153 | -0.715 | -111.75 | 0.535054 | 12 | 40.61 | 1.826919 | -4.06 | 0.964548 | 3.316611 |
| 27 | `london_ny_handoff_reversal_short_bias3_h8` | `london_ny_handoff_reversal_short` | SHORT | `REJECT_LITE_WEAK` | 316 | 6.44898 | 1.026743 | -0.085 | 35.65 | 0.803637 | 64 | -57.87 | 0.905277 | 105.16 | 1.267256 | 3.252073 |
| 28 | `london_ny_handoff_reversal_short_bias2_h8` | `london_ny_handoff_reversal_short` | SHORT | `REJECT_LITE_WEAK` | 354 | 7.22449 | 1.03609 | 0.0 | 51.14 | 0.800962 | 71 | -104.89 | 0.84232 | 105.16 | 1.267256 | 3.219655 |
| 29 | `pdh_sweep_reject_short_sweep3.5_reject1_london_new_york_h8` | `pdh_sweep_reject_short` | SHORT | `REJECT_LITE_WEAK` | 36 | 1.714286 | 0.624591 | -1.67 | -96.36 | 0.517844 | 8 | 32.12 | 1.497907 | 21.75 | 1.271468 | 3.135063 |
| 30 | `london_ny_handoff_continuation_long_bias3_h16` | `london_ny_handoff_continuation_long` | LONG | `REJECT_LITE_WEAK` | 264 | 5.387755 | 1.012921 | -0.25 | 21.11 | 0.855941 | 53 | 73.19 | 1.113624 | 6.71 | 1.015562 | 3.096164 |

## Promoted to exact replay
- `compression_expansion_breakout_long_comp0.75_h8` (compression_expansion_breakout_long, LONG)

## Interpretation
- Stage19A is a fast M15 proxy discovery pass, not exact execution replay.
- Promoted candidates must go to Stage19B exact M1 replay before any forward-shadow design.
- Do not add Stage19A candidates to Stage18A directly.
- Continue Stage18A v2 separately for active forward-shadow tracking.
- No paper/live/order escalation is authorized.

## Output files
- summary_csv: `data/reports/stage19a_lite_new_behavior_discovery/stage19a_lite_new_behavior_summary.csv`
- promoted_csv: `data/reports/stage19a_lite_new_behavior_discovery/stage19a_promote_to_exact_replay.csv`
- trades_csv: `data/reports/stage19a_lite_new_behavior_discovery/stage19a_lite_new_behavior_trades.csv`
- json: `data/reports/stage19a_lite_new_behavior_discovery/stage19a_lite_new_behavior_discovery.json`
- md: `data/reports/stage19a_lite_new_behavior_discovery/stage19a_lite_new_behavior_discovery.md`
