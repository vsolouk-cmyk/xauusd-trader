# Stage 21B Trend Pullback Continuation Short Exact M1 Replay

Generated UTC: `2026-06-11T12:58:08+00:00`
Tool version: `v1`

> Hard rule: research validation only. No EA change, no automatic trading, no paper/live authorization.

## Candidate
- variant: `trend_pullback_continuation_short_trend5_pull0.5_new_york_only_h8`
- family: `trend_pullback_continuation_short`
- side: `SHORT`
- condition: `H1 downtrend + New York-only M15 pullback/rejection below EMA20`
- trend_dist: `5.0`
- pullback: `0.5`
- horizon_bars: `8`
- horizon_minutes: `120`
- cooldown_bars: `4`
- cost_usd: `0.35`

## Source
- db: `data/local/xauusd_local_store.sqlite`
- m1_rows: `1532269`
- m15_rows: `102417`
- h1_rows: `25769`
- m1_first: `2022-05-01T23:01:00+00:00`
- m1_last: `2026-06-11T14:24:00+00:00`

## Final decision
- final_decision: `EXACT_REPLAY_KEEP_WATCHLIST_ONLY`

## Reasons
- Exact M1 replay is positive but not strong enough for forward-shadow design.

## Exact M1 time-exit metrics
| Cost model | Events | Total | Avg | Median | WR | PF | DD | Pos years | Years | Pos quarters | Quarters |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| net_x1 | 286 | 284.97 | 0.996399 | 0.06 | 0.506993 | 1.184984 | -269.03 | 4 | 5 | 9 | 17 |
| net_x2 | 286 | 184.87 | 0.646399 | -0.29 | 0.479021 | 1.116178 | -274.28 | 4 | 5 | 9 | 17 |
| net_x4 | 286 | -15.33 | -0.053601 | -0.99 | 0.458042 | 0.990969 | -284.97 | 2 | 5 | 8 | 17 |

## Chronological splits
| Split | Segment | Events | Total | Median | PF | DD |
|---|---|---:|---:|---:|---:|---:|
| 70/30 | train | 200 | 147.19 | 0.305 | 1.229722 | -66.36 |
| 70/30 | test | 86 | 137.78 | -1.585 | 1.153126 | -269.03 |
| 80/20 | train | 228 | 65.41 | 0.11 | 1.075023 | -111.17 |
| 80/20 | test | 58 | 219.56 | -0.605 | 1.328368 | -269.03 |

## 2026 segment
- events: `55`
- total: `115.59`
- median: `-0.1`
- pf: `1.178493`
- dd: `-269.03`

## Bootstrap
- n: `300`
- total_p05: `-272.7955`
- total_p50: `242.375`
- pf_p05: `0.857596`
- pf_p50: `1.16161`
- median_p05: `-0.7785`
- prob_total_gt_0: `0.776667`
- prob_pf_gt_1: `0.776667`
- prob_median_gt_0: `0.566667`

## Interpretation
- Stage21B is exact historical validation, not forward proof.
- Promotion here only allows later forward-shadow collector design.
- Do not add this candidate to Stage18A unless the final decision is promotion.
- No paper/live/order escalation is authorized.

## Output files
- trades_csv: `data/reports/stage21b_trend_pullback_short_exact_replay/stage21b_exact_trades.csv`
- by_year_csv: `data/reports/stage21b_trend_pullback_short_exact_replay/stage21b_exact_by_year.csv`
- by_quarter_csv: `data/reports/stage21b_trend_pullback_short_exact_replay/stage21b_exact_by_quarter.csv`
- by_month_csv: `data/reports/stage21b_trend_pullback_short_exact_replay/stage21b_exact_by_month.csv`
- json: `data/reports/stage21b_trend_pullback_short_exact_replay/stage21b_trend_pullback_short_exact_replay.json`
- md: `data/reports/stage21b_trend_pullback_short_exact_replay/stage21b_trend_pullback_short_exact_replay.md`
