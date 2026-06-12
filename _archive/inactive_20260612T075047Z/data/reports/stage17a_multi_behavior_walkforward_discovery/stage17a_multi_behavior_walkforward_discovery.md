# Stage 17A Multi-Behavior Walk-Forward Discovery

Generated UTC: `2026-06-11T07:10:28+00:00`
Tool version: `v1`

> Hard rule: research discovery only. No EA change, no automatic trading, no paper/live authorization.

## Purpose
- Keep Stage16 true-forward collection running.
- Expand discovery to multiple independent behavior families.
- Promote only behavior variants that pass strict historical walk-forward checks.

## Inputs
- db: `data/local/xauusd_local_store.sqlite`
- intraday_source: `m1_to_m15_h1`
- m15_rows: `102397`
- h1_rows: `25764`
- m15_first: `2022-05-01T23:15:00+00:00`
- m15_last: `2026-06-11T09:30:00+00:00`
- cost_usd: `0.35`
- buffer_usd: `0.2`

## Final decision
- final_decision: `MULTI_BEHAVIOR_CANDIDATES_FOUND`

## Counts
- behaviors_tested: `14`
- variants_tested: `112`
- promoted_to_stage17b: `1`
- watchlist_only: `12`

## Top promoted candidates
| Rank | Variant | Side | Events | Freq/mo | PF x1 | Median x1 | Total x1 | PF x2 | PF x4 | Test20 events | Test20 total | Test20 PF | 2026 total | 2026 PF | Score |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | `pdh_breakout_continuation_long_h32_cool4` | LONG | 758 | 15.16 | 1.256304 | 0.765 | 1171.09 | 1.192869 | 1.075642 | 152 | 717.93 | 1.377965 | 339.87 | 1.289658 | 14.722042 |

## Top watchlist candidates
| Rank | Variant | Side | Decision | Events | PF x1 | Median x1 | Test20 PF | 2026 PF | Reason |
|---:|---|---|---|---:|---:|---:|---:|---:|---|
| 1 | `asia_high_breakout_long_h32_cool0` | LONG | WATCHLIST_ONLY | 625 | 1.195696 | 0.29 | 1.600019 | 3.871079 | Positive but not strong enough for promotion. |
| 2 | `pdl_sweep_reclaim_long_controlled_h4_cool0` | LONG | WATCHLIST_ONLY | 155 | 1.407722 | 0.28 | 2.757262 | 9.482686 | Positive but not strong enough for promotion. |
| 3 | `pdl_sweep_reclaim_long_controlled_h4_cool4` | LONG | WATCHLIST_ONLY | 145 | 1.36859 | 0.28 | 2.917418 | 32.215743 | Positive but not strong enough for promotion. |
| 4 | `asia_high_breakout_long_h32_cool4` | LONG | WATCHLIST_ONLY | 564 | 1.137518 | 0.22 | 1.354325 | 5.480778 | Positive but not strong enough for promotion. |
| 5 | `asia_low_breakdown_short_h32_cool0` | SHORT | WATCHLIST_ONLY | 475 | 1.099151 | -0.76 | 1.201247 | 3.703406 | Positive but not strong enough for promotion. |
| 6 | `asia_low_breakdown_short_h32_cool4` | SHORT | WATCHLIST_ONLY | 433 | 1.101502 | -0.43 | 1.162019 | 9.130249 | Positive but not strong enough for promotion. |
| 7 | `pdl_sweep_reclaim_long_controlled_h8_cool4` | LONG | WATCHLIST_ONLY | 138 | 1.25792 | -0.065 | 1.847368 | 2.522308 | Positive but not strong enough for promotion. |
| 8 | `pdl_breakdown_continuation_short_h32_cool0` | SHORT | WATCHLIST_ONLY | 613 | 1.090117 | -0.34 | 1.323159 | 1.450883 | Positive but not strong enough for promotion. |
| 9 | `compressed_range_up_break_long_h8_cool0` | LONG | WATCHLIST_ONLY | 161 | 1.256063 | 0.53 | 1.06223 | 1.118978 | Positive but not strong enough for promotion. |
| 10 | `pdl_sweep_reclaim_long_controlled_h8_cool0` | LONG | WATCHLIST_ONLY | 145 | 1.164209 | -0.19 | 1.487423 | 1.524371 | Positive but not strong enough for promotion. |
| 11 | `compressed_range_up_break_long_h8_cool4` | LONG | WATCHLIST_ONLY | 150 | 1.240614 | 0.53 | 1.020983 | 1.068544 | Positive but not strong enough for promotion. |
| 12 | `pdh_breakout_continuation_long_h32_cool0` | LONG | WATCHLIST_ONLY | 787 | 1.103088 | 0.54 | 1.135316 | 1.036164 | Positive but not strong enough for promotion. |

## Behavior families tested
- `asia_high_breakout_long`
- `asia_high_fakeout_reject_short`
- `asia_low_breakdown_short`
- `asia_low_fakeout_reclaim_long`
- `compressed_range_down_break_short`
- `compressed_range_up_break_long`
- `h4_down_sma_reject_short`
- `h4_up_sma_reclaim_long`
- `pdh_breakout_continuation_long`
- `pdh_sweep_reject_short_controlled`
- `pdh_sweep_reject_short_loose`
- `pdl_breakdown_continuation_short`
- `pdl_sweep_reclaim_long_controlled`
- `pdl_sweep_reclaim_long_loose`

## Interpretation
- Stage17A is a broad historical discovery lab.
- Promoted candidates are not tradable yet; they require Stage17B exact M1 replay/robustness.
- Watchlist candidates can be revisited but should not enter forward shadow directly.
- Stage16 true-forward collector should continue in parallel.
- No paper/live/order authorization is granted.

## Output files
- summary_csv: `data/reports/stage17a_multi_behavior_walkforward_discovery/stage17a_behavior_summary.csv`
- promoted_csv: `data/reports/stage17a_multi_behavior_walkforward_discovery/stage17a_promoted_candidates.csv`
- trades_csv: `data/reports/stage17a_multi_behavior_walkforward_discovery/stage17a_all_behavior_trades.csv`
- years_csv: `data/reports/stage17a_multi_behavior_walkforward_discovery/stage17a_year_breakdown.csv`
- json: `data/reports/stage17a_multi_behavior_walkforward_discovery/stage17a_multi_behavior_walkforward_discovery.json`
- md: `data/reports/stage17a_multi_behavior_walkforward_discovery/stage17a_multi_behavior_walkforward_discovery.md`
