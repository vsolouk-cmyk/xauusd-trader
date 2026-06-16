# Stage 21A Trend Pullback and Exhaustion Lite Discovery

Generated UTC: `2026-06-11T12:51:41+00:00`
Tool version: `v1`

> Hard rule: research discovery only. M15 proxy replay only. No EA change, no automatic trading, no paper/live authorization.

## Purpose
- Continue discovery after Stage20A produced watchlist-only results.
- Use fast M15 proxy replay, not exact execution replay.
- Explore trend pullback, impulse exhaustion, and NY continuation families.

## Inputs
- db: `data/local/xauusd_local_store.sqlite`
- m1_rows: `1532269`
- m15_rows: `102417`
- h1_rows: `25769`
- m1_first: `2022-05-01T23:01:00+00:00`
- m1_last: `2026-06-11T14:24:00+00:00`
- cost_usd: `0.35`
- variants_tested: `168`
- fast: `False`

## Final decision
- final_decision: `TREND_PULLBACK_CANDIDATES_FOR_EXACT_REPLAY`

## Counts
- promoted_to_stage21b: `1`
- lite_watchlist: `32`

## Top variants
| Rank | Variant | Family | Side | Decision | Events | Freq/mo | PF x1 | Median x1 | Total x1 | PF x4 | Test20 events | Test20 total | Test20 PF | 2026 total | 2026 PF | Score |
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | `trend_pullback_continuation_short_trend5_pull0.5_new_york_only_h8` | `trend_pullback_continuation_short` | SHORT | `PROMOTE_STAGE21B_EXACT_REPLAY` | 286 | 5.72 | 1.184984 | 0.06 | 284.97 | 0.990969 | 58 | 219.56 | 1.328368 | 115.59 | 1.178493 | 5.126737 |
| 2 | `ny_open_london_trend_continuation_short_bias6_h8` | `ny_open_london_trend_continuation_short` | SHORT | `KEEP_LITE_WATCHLIST` | 208 | 4.727273 | 1.397858 | -0.425 | 431.76 | 1.176744 | 42 | 127.64 | 1.304666 | 231.44 | 1.519669 | 7.603494 |
| 3 | `trend_pullback_continuation_long_trend5_pull1.5_london_new_york_h4` | `trend_pullback_continuation_long` | LONG | `KEEP_LITE_WATCHLIST` | 1016 | 20.32 | 1.11822 | -0.015 | 304.29 | 0.758886 | 204 | 342.89 | 1.350948 | 319.96 | 1.433491 | 7.514422 |
| 4 | `trend_pullback_continuation_long_trend5_pull0.5_london_new_york_h8` | `trend_pullback_continuation_long` | LONG | `KEEP_LITE_WATCHLIST` | 687 | 13.74 | 1.166606 | 0.09 | 460.09 | 0.91677 | 138 | 461.4 | 1.475822 | 403.81 | 1.474518 | 7.232948 |
| 5 | `trend_pullback_continuation_long_trend5_pull3_london_new_york_h4` | `trend_pullback_continuation_long` | LONG | `KEEP_LITE_WATCHLIST` | 1209 | 24.18 | 1.096068 | -0.07 | 305.42 | 0.75213 | 242 | 326.3 | 1.274839 | 296.39 | 1.34472 | 7.151554 |
| 6 | `trend_pullback_continuation_long_trend5_pull0.5_london_new_york_h4` | `trend_pullback_continuation_long` | LONG | `KEEP_LITE_WATCHLIST` | 816 | 16.32 | 1.112911 | 0.095 | 264.0 | 0.788354 | 164 | 228.08 | 1.268222 | 270.66 | 1.377058 | 6.991661 |
| 7 | `trend_pullback_continuation_short_trend0_pull0.5_new_york_only_h8` | `trend_pullback_continuation_short` | SHORT | `KEEP_LITE_WATCHLIST` | 489 | 9.78 | 1.108641 | -0.45 | 226.96 | 0.879216 | 98 | 279.94 | 1.309466 | 263.9 | 1.397967 | 6.752101 |
| 8 | `trend_pullback_continuation_long_trend0_pull0.5_london_new_york_h4` | `trend_pullback_continuation_long` | LONG | `KEEP_LITE_WATCHLIST` | 1429 | 28.58 | 1.055467 | -0.06 | 192.94 | 0.697774 | 286 | 544.07 | 1.459166 | 403.17 | 1.542194 | 6.613266 |
| 9 | `ny_open_london_trend_continuation_short_bias2_h8` | `ny_open_london_trend_continuation_short` | SHORT | `KEEP_LITE_WATCHLIST` | 359 | 7.18 | 1.208188 | -0.72 | 345.88 | 0.983434 | 72 | 370.7 | 1.574399 | 181.23 | 1.343733 | 6.597294 |
| 10 | `ny_open_london_trend_continuation_short_bias6_h24` | `ny_open_london_trend_continuation_short` | SHORT | `KEEP_LITE_WATCHLIST` | 138 | 3.136364 | 1.378052 | -0.795 | 446.77 | 1.240195 | 28 | 198.34 | 1.464736 | 166.39 | 1.362719 | 6.530409 |
| 11 | `trend_pullback_continuation_long_trend0_pull3_new_york_only_h4` | `trend_pullback_continuation_long` | LONG | `KEEP_LITE_WATCHLIST` | 1014 | 20.28 | 1.061949 | -0.04 | 159.77 | 0.714841 | 203 | 322.42 | 1.36687 | 245.14 | 1.44202 | 6.521777 |
| 12 | `trend_pullback_continuation_long_trend2_pull0.5_london_new_york_h8` | `trend_pullback_continuation_long` | LONG | `KEEP_LITE_WATCHLIST` | 977 | 19.54 | 1.078735 | -0.01 | 282.28 | 0.820109 | 196 | 586.63 | 1.467088 | 331.95 | 1.361794 | 6.50862 |
| 13 | `trend_pullback_continuation_short_trend5_pull3_london_new_york_h16` | `trend_pullback_continuation_short` | SHORT | `KEEP_LITE_WATCHLIST` | 540 | 10.8 | 1.10785 | -1.14 | 384.19 | 0.95283 | 108 | 303.33 | 1.193421 | 345.2 | 1.262468 | 6.501356 |
| 14 | `ny_open_london_trend_continuation_short_bias6_h4` | `ny_open_london_trend_continuation_short` | SHORT | `KEEP_LITE_WATCHLIST` | 252 | 5.727273 | 1.365477 | -0.7 | 351.87 | 1.078639 | 51 | 187.57 | 1.572803 | 111.59 | 1.340774 | 6.402222 |
| 15 | `ny_open_london_trend_continuation_short_bias4_h8` | `ny_open_london_trend_continuation_short` | SHORT | `KEEP_LITE_WATCHLIST` | 273 | 5.571429 | 1.272669 | -0.92 | 377.72 | 1.05881 | 55 | 177.38 | 1.323763 | 149.59 | 1.283739 | 6.360442 |
| 16 | `trend_pullback_continuation_long_trend5_pull3_new_york_only_h4` | `trend_pullback_continuation_long` | LONG | `KEEP_LITE_WATCHLIST` | 666 | 13.32 | 1.100836 | 0.04 | 189.52 | 0.774759 | 134 | 205.21 | 1.308216 | 185.4 | 1.351543 | 6.116414 |
| 17 | `m15_impulse_exhaustion_reversal_long_imp2_lb8_h16` | `m15_impulse_exhaustion_reversal_long` | LONG | `KEEP_LITE_WATCHLIST` | 768 | 15.36 | 1.12378 | 0.45 | 464.15 | 0.917679 | 154 | 360.32 | 1.230194 | 236.8 | 1.237942 | 5.760991 |
| 18 | `ny_open_london_trend_continuation_short_bias6_h16` | `ny_open_london_trend_continuation_short` | SHORT | `KEEP_LITE_WATCHLIST` | 138 | 3.136364 | 1.40603 | -0.615 | 430.64 | 1.250834 | 28 | 118.18 | 1.264403 | 93.68 | 1.198698 | 5.65998 |
| 19 | `trend_pullback_continuation_long_trend0_pull0.5_london_new_york_h8` | `trend_pullback_continuation_long` | LONG | `KEEP_LITE_WATCHLIST` | 1158 | 23.16 | 1.061487 | -0.08 | 253.74 | 0.79886 | 232 | 536.11 | 1.3718 | 277.41 | 1.278611 | 5.618592 |
| 20 | `trend_pullback_continuation_long_trend5_pull1.5_new_york_only_h4` | `trend_pullback_continuation_long` | LONG | `KEEP_LITE_WATCHLIST` | 580 | 11.6 | 1.070643 | -0.145 | 118.55 | 0.756476 | 116 | 157.73 | 1.272564 | 165.9 | 1.34613 | 5.490004 |
| 21 | `m15_impulse_exhaustion_reversal_long_imp2.5_lb4_h4` | `m15_impulse_exhaustion_reversal_long` | LONG | `KEEP_LITE_WATCHLIST` | 264 | 5.28 | 1.064248 | 0.075 | 64.37 | 0.815165 | 53 | 68.71 | 1.13229 | 152.94 | 1.568381 | 5.449955 |
| 22 | `trend_pullback_continuation_long_trend5_pull0.5_new_york_only_h4` | `trend_pullback_continuation_long` | LONG | `KEEP_LITE_WATCHLIST` | 472 | 9.44 | 1.055678 | -0.035 | 86.97 | 0.776949 | 95 | 142.43 | 1.272619 | 154.71 | 1.324285 | 5.372049 |
| 23 | `m15_impulse_exhaustion_reversal_long_imp2_lb4_h4` | `m15_impulse_exhaustion_reversal_long` | LONG | `KEEP_LITE_WATCHLIST` | 504 | 10.08 | 1.050052 | 0.17 | 77.35 | 0.7522 | 101 | 111.75 | 1.160771 | 132.23 | 1.359057 | 5.350161 |
| 24 | `ny_open_london_trend_continuation_short_bias4_h4` | `ny_open_london_trend_continuation_short` | SHORT | `KEEP_LITE_WATCHLIST` | 330 | 6.734694 | 1.19305 | -1.045 | 235.26 | 0.921748 | 66 | 184.57 | 1.391063 | 69.15 | 1.18283 | 5.169494 |
| 25 | `trend_pullback_continuation_short_trend5_pull3_london_new_york_h8` | `trend_pullback_continuation_short` | SHORT | `KEEP_LITE_WATCHLIST` | 696 | 13.92 | 1.104985 | -0.26 | 324.09 | 0.883481 | 140 | 185.56 | 1.136903 | 155.75 | 1.135507 | 5.093792 |
| 26 | `trend_pullback_continuation_short_trend2_pull0.5_new_york_only_h8` | `trend_pullback_continuation_short` | SHORT | `KEEP_LITE_WATCHLIST` | 408 | 8.16 | 1.114806 | -0.1 | 212.63 | 0.896272 | 82 | 170.11 | 1.199374 | 117.28 | 1.173204 | 4.621926 |
| 27 | `ny_open_london_trend_continuation_short_bias2_h24` | `ny_open_london_trend_continuation_short` | SHORT | `KEEP_LITE_WATCHLIST` | 246 | 4.92 | 1.203296 | -0.56 | 379.71 | 1.060473 | 50 | 301.3 | 1.376033 | 68.83 | 1.108142 | 4.566465 |
| 28 | `ny_open_london_trend_continuation_short_bias2_h4` | `ny_open_london_trend_continuation_short` | SHORT | `KEEP_LITE_WATCHLIST` | 431 | 8.62 | 1.091838 | -0.86 | 138.65 | 0.823155 | 87 | 183.3 | 1.302301 | 62.54 | 1.159998 | 4.297496 |
| 29 | `trend_pullback_continuation_short_trend5_pull0.5_london_new_york_h16` | `trend_pullback_continuation_short` | SHORT | `KEEP_LITE_WATCHLIST` | 434 | 8.68 | 1.129732 | -0.3 | 389.3 | 0.979518 | 87 | 234.25 | 1.165817 | 91.16 | 1.066698 | 4.192156 |
| 30 | `ny_open_london_trend_continuation_short_bias2_h16` | `ny_open_london_trend_continuation_short` | SHORT | `KEEP_LITE_WATCHLIST` | 246 | 4.92 | 1.119657 | -1.025 | 207.7 | 0.973057 | 50 | 298.72 | 1.373241 | 24.15 | 1.038711 | 4.007379 |

## Promoted to exact replay
- `trend_pullback_continuation_short_trend5_pull0.5_new_york_only_h8` (trend_pullback_continuation_short, SHORT)

## Interpretation
- Stage21A is M15 proxy discovery only, not exact M1 replay.
- Promoted candidates must go to Stage21B exact M1 replay before any forward-shadow design.
- Do not add Stage21A candidates to Stage18A directly.
- Continue Stage18A v2 separately for active forward-shadow tracking.
- No paper/live/order escalation is authorized.

## Output files
- summary_csv: `data/reports/stage21a_trend_pullback_lite_discovery/stage21a_trend_pullback_lite_summary.csv`
- promoted_csv: `data/reports/stage21a_trend_pullback_lite_discovery/stage21a_promote_to_exact_replay.csv`
- trades_csv: `data/reports/stage21a_trend_pullback_lite_discovery/stage21a_trend_pullback_lite_trades.csv`
- json: `data/reports/stage21a_trend_pullback_lite_discovery/stage21a_trend_pullback_lite_discovery.json`
- md: `data/reports/stage21a_trend_pullback_lite_discovery/stage21a_trend_pullback_lite_discovery.md`
