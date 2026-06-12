# Stage 20A London-to-NY Handoff Short Exact M1 Replay

Generated UTC: `2026-06-11T12:46:17+00:00`
Tool version: `v1`

> Hard rule: research validation only. No EA change, no automatic trading, no paper/live authorization.

## Purpose
- Exact-replay London-to-NY handoff continuation SHORT variants from Stage19A watchlist.
- Use exact M1 path before any forward-shadow design.

## Inputs
- db: `data/local/xauusd_local_store.sqlite`
- m1_rows: `1532269`
- m15_rows: `102417`
- m1_first: `2022-05-01T23:01:00+00:00`
- m1_last: `2026-06-11T14:24:00+00:00`
- cost_usd: `0.35`
- buffer_usd: `0.2`
- variants_tested: `8`

## Final decision
- final_decision: `HANDOFF_SHORT_WATCHLIST_ONLY`

## Counts
- promoted: `0`
- watchlist: `4`

## Variant ranking
| Rank | Variant | Decision | Events | Freq/mo | PF x1 | Median x1 | Total x1 | PF x2 | PF x4 | Test20 events | Test20 total | Test20 PF | 2026 total | 2026 PF | Boot PF p05 | Score |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | `london_ny_handoff_continuation_short_bias2_h8` | `KEEP_EXACT_WATCHLIST_ONLY` | 351 | 7.02 | 1.187452 | -0.52 | 311.7 | 1.109167 | 0.969645 | 71 | 331.81 | 1.484918 | 134.38 | 1.234075 | 0.855459 | 9.173025 |
| 2 | `london_ny_handoff_continuation_short_bias3_h8` | `KEEP_EXACT_WATCHLIST_ONLY` | 304 | 6.08 | 1.191879 | -0.64 | 293.2 | 1.117746 | 0.984795 | 61 | 192.99 | 1.298566 | 102.74 | 1.178971 | 0.826114 | 8.474129 |
| 3 | `london_ny_handoff_continuation_short_bias2_h24` | `KEEP_EXACT_WATCHLIST_ONLY` | 245 | 4.9 | 1.193195 | -0.85 | 360.01 | 1.143634 | 1.051295 | 49 | 348.21 | 1.461603 | 73.88 | 1.117004 | 0.874869 | 7.971692 |
| 4 | `london_ny_handoff_continuation_short_bias3_h24` | `KEEP_EXACT_WATCHLIST_ONLY` | 210 | 4.2 | 1.165078 | -1.14 | 282.47 | 1.119332 | 1.033805 | 42 | 107.69 | 1.153529 | -6.31 | 0.990007 | 0.833583 | 6.462571 |
| 5 | `london_ny_handoff_continuation_short_bias1_h8` | `REJECT_EXACT_WEAK` | 392 | 7.84 | 1.132111 | -0.57 | 243.74 | 1.055482 | 0.919297 | 79 | 165.27 | 1.194252 | 61.63 | 1.095279 | 0.839393 | 7.129562 |
| 6 | `london_ny_handoff_continuation_short_bias2_h16` | `REJECT_EXACT_WEAK` | 245 | 4.9 | 1.104624 | -0.88 | 183.33 | 1.054253 | 0.960996 | 49 | 330.58 | 1.430174 | 12.1 | 1.019028 | 0.783025 | 6.739053 |
| 7 | `london_ny_handoff_continuation_short_bias1_h16` | `REJECT_EXACT_WEAK` | 275 | 5.5 | 1.078245 | -0.7 | 151.53 | 1.027819 | 0.934425 | 55 | 197.94 | 1.21966 | -75.42 | 0.895745 | 0.769222 | 5.768334 |
| 8 | `london_ny_handoff_continuation_short_bias1_h24` | `REJECT_EXACT_WEAK` | 275 | 5.5 | 1.117474 | -0.76 | 250.3 | 1.070615 | 0.983175 | 55 | 164.74 | 1.175663 | -48.72 | 0.935387 | 0.804002 | 5.723079 |

## Promoted candidates
- none

## Interpretation
- Stage20A is exact historical validation, not forward proof.
- Promoted variants may go to a later forward-shadow collector design.
- Watchlist-only variants must not be added to Stage18A.
- No paper/live/order escalation is authorized.

## Output files
- summary_csv: `data/reports/stage20a_london_ny_handoff_short_exact_replay/stage20a_handoff_short_exact_summary.csv`
- promoted_csv: `data/reports/stage20a_london_ny_handoff_short_exact_replay/stage20a_handoff_short_promoted.csv`
- trades_csv: `data/reports/stage20a_london_ny_handoff_short_exact_replay/stage20a_handoff_short_exact_trades.csv`
- json: `data/reports/stage20a_london_ny_handoff_short_exact_replay/stage20a_london_ny_handoff_short_exact_replay.json`
- md: `data/reports/stage20a_london_ny_handoff_short_exact_replay/stage20a_london_ny_handoff_short_exact_replay.md`
