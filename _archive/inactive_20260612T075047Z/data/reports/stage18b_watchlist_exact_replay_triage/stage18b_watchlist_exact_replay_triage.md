# Stage 18B Watchlist Exact M1 Replay Triage

Generated UTC: `2026-06-11T08:46:15+00:00`
Tool version: `v1`

> Hard rule: research discovery/triage only. No EA change, no automatic trading, no paper/live authorization.

## Purpose
- Continue discovery while Stage18A keeps active shadow candidates running.
- Exact-replay Stage17A watchlist candidates using AMarkets M1 path.
- Promote only candidates that survive costs, splits, 2026, year breadth, and bootstrap.

## Inputs
- db: `data/local/xauusd_local_store.sqlite`
- m1_rows: `1532063`
- m15_rows: `102403`
- h1_rows: `25765`
- m1_first: `2022-05-01T23:01:00+00:00`
- m1_last: `2026-06-11T10:58:00+00:00`
- cost_usd: `0.35`
- buffer_usd: `0.2`

## Final decision
- final_decision: `EXACT_WATCHLIST_POSITIVE_ONLY`

## Counts
- variants_tested: `12`
- promoted_to_stage18c: `0`
- exact_watchlist_positive: `10`

## Candidate ranking
| Rank | Variant | Side | Decision | Events | Freq/mo | PF x1 | Median x1 | Total x1 | PF x2 | PF x4 | Test20 events | Test20 total | Test20 PF | 2026 total | 2026 PF | Boot PF p05 | Score |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | `pdl_sweep_reclaim_long_controlled_h4_cool0` | LONG | `KEEP_WATCHLIST_EXACT_REPLAY_POSITIVE` | 155 | 3.369565 | 1.407722 | 0.28 | 143.4 | 1.235765 | 0.955531 | 31 | 140.95 | 2.757262 | 120.03 | 9.482686 | 1.032338 | 16.748955 |
| 2 | `pdl_sweep_reclaim_long_controlled_h4_cool4` | LONG | `KEEP_WATCHLIST_EXACT_REPLAY_POSITIVE` | 145 | 3.152174 | 1.36859 | 0.28 | 119.32 | 1.196735 | 0.918093 | 29 | 129.79 | 2.917418 | 107.07 | 32.215743 | 0.969823 | 16.564839 |
| 3 | `asia_high_breakout_long_h32_cool0` | LONG | `KEEP_WATCHLIST_EXACT_REPLAY_POSITIVE` | 625 | 12.755102 | 1.183658 | 0.29 | 592.57 | 1.112068 | 0.982125 | 125 | 479.84 | 1.590594 | 331.4 | 5.489298 | 1.010077 | 15.35808 |
| 4 | `asia_high_breakout_long_h32_cool4` | LONG | `KEEP_WATCHLIST_EXACT_REPLAY_POSITIVE` | 564 | 11.510204 | 1.139398 | 0.22 | 411.56 | 1.070194 | 0.944534 | 113 | 291.59 | 1.356637 | 280.9 | 5.480778 | 0.928994 | 13.88905 |
| 5 | `asia_low_breakdown_short_h32_cool0` | SHORT | `KEEP_WATCHLIST_EXACT_REPLAY_POSITIVE` | 475 | 9.693878 | 1.122676 | -0.76 | 318.84 | 1.056814 | 0.937216 | 95 | 180.64 | 1.232493 | 251.73 | 3.80792 | 0.910413 | 12.950181 |
| 6 | `asia_low_breakdown_short_h32_cool4` | SHORT | `KEEP_WATCHLIST_EXACT_REPLAY_POSITIVE` | 433 | 8.836735 | 1.125908 | -0.43 | 299.55 | 1.060218 | 0.94081 | 87 | 143.21 | 1.198635 | 303.99 | 9.130249 | 0.901744 | 12.517829 |
| 7 | `pdl_sweep_reclaim_long_controlled_h8_cool4` | LONG | `KEEP_WATCHLIST_EXACT_REPLAY_POSITIVE` | 138 | 3.0 | 1.25792 | -0.065 | 111.37 | 1.138136 | 0.933862 | 28 | 106.87 | 1.847368 | 70.97 | 2.522308 | 0.871177 | 12.316814 |
| 8 | `pdh_breakout_continuation_long_h32_cool0` | LONG | `KEEP_WATCHLIST_EXACT_REPLAY_POSITIVE` | 787 | 15.74 | 1.120258 | 0.52 | 604.12 | 1.063713 | 0.959135 | 158 | 353.44 | 1.177027 | 140.52 | 1.109898 | 0.917049 | 10.434061 |
| 9 | `pdl_sweep_reclaim_long_controlled_h8_cool0` | LONG | `KEEP_WATCHLIST_EXACT_REPLAY_POSITIVE` | 145 | 3.152174 | 1.164209 | -0.19 | 78.05 | 1.0544 | 0.866482 | 29 | 76.35 | 1.487423 | 40.45 | 1.524371 | 0.771175 | 10.299306 |
| 10 | `compressed_range_up_break_long_h8_cool4` | LONG | `KEEP_WATCHLIST_EXACT_REPLAY_POSITIVE` | 150 | 3.26087 | 1.240614 | 0.53 | 110.55 | 1.119832 | 0.912904 | 30 | 4.94 | 1.020983 | 13.36 | 1.068544 | 0.818182 | 10.206256 |
| 11 | `compressed_range_up_break_long_h8_cool0` | LONG | `REJECT_EXACT_REPLAY_WEAK` | 161 | 3.5 | 1.256063 | 0.53 | 123.22 | 1.13166 | 0.919098 | 33 | 14.98 | 1.06223 | 23.19 | 1.118978 | 0.774706 | 10.198367 |
| 12 | `pdl_breakdown_continuation_short_h32_cool0` | SHORT | `REJECT_EXACT_REPLAY_WEAK` | 614 | 12.28 | 1.066918 | -0.35 | 319.06 | 1.021354 | 0.936236 | 123 | 536.67 | 1.240252 | 520.98 | 1.335014 | 0.824941 | 9.962006 |

## Promoted candidates
- none

## Interpretation
- Stage18B is exact historical replay triage, not forward proof.
- Promoted candidates should go to Stage18C/Stage19 forward-shadow design.
- Positive-but-not-promoted candidates remain research watchlist only.
- Current Stage16C/Stage17D shadow collection should continue through Stage18A.
- No paper/live/order escalation is authorized.

## Output files
- summary_csv: `data/reports/stage18b_watchlist_exact_replay_triage/stage18b_watchlist_exact_summary.csv`
- promoted_csv: `data/reports/stage18b_watchlist_exact_replay_triage/stage18b_promoted_candidates.csv`
- trades_csv: `data/reports/stage18b_watchlist_exact_replay_triage/stage18b_watchlist_exact_trades.csv`
- by_year_csv: `data/reports/stage18b_watchlist_exact_replay_triage/stage18b_watchlist_exact_by_year.csv`
- by_quarter_csv: `data/reports/stage18b_watchlist_exact_replay_triage/stage18b_watchlist_exact_by_quarter.csv`
- json: `data/reports/stage18b_watchlist_exact_replay_triage/stage18b_watchlist_exact_replay_triage.json`
- md: `data/reports/stage18b_watchlist_exact_replay_triage/stage18b_watchlist_exact_replay_triage.md`
