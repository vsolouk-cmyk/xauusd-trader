# Stage 19B Compression Expansion Breakout Exact M1 Replay

Generated UTC: `2026-06-11T12:39:57+00:00`
Tool version: `v1`

> Hard rule: research validation only. No EA change, no automatic trading, no paper/live authorization.

## Candidate
- variant: `compression_expansion_breakout_long_comp0.75_h8`
- family: `compression_expansion_breakout_long`
- side: `LONG`
- condition: `compression6 <= 0.75` and M15 close breaks prior local high16 during London/New York
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
| net_x1 | 134 | 138.83 | 1.036045 | 0.725 | 0.552239 | 1.347901 | -76.37 | 3 | 5 | 11 | 17 |
| net_x2 | 134 | 91.93 | 0.686045 | 0.375 | 0.537313 | 1.218725 | -77.07 | 3 | 5 | 9 | 17 |
| net_x4 | 134 | -1.87 | -0.013955 | -0.325 | 0.485075 | 0.995992 | -107.6 | 2 | 5 | 8 | 17 |

## Chronological splits
| Split | Segment | Events | Total | Median | PF | DD |
|---|---|---:|---:|---:|---:|---:|
| 70/30 | train | 93 | 20.49 | 0.53 | 1.108579 | -36.79 |
| 70/30 | test | 41 | 118.34 | 4.08 | 1.562613 | -76.37 |
| 80/20 | train | 107 | 68.39 | 0.57 | 1.309822 | -36.79 |
| 80/20 | test | 27 | 70.44 | 4.08 | 1.395042 | -76.37 |

## 2026 segment
- events: `22`
- total: `41.31`
- median: `3.795`
- pf: `1.247425`
- dd: `-76.37`

## Bootstrap
- n: `300`
- total_p05: `-86.5785`
- total_p50: `134.17`
- pf_p05: `0.836647`
- pf_p50: `1.321236`
- median_p05: `-0.135`
- prob_total_gt_0: `0.85`
- prob_pf_gt_1: `0.85`
- prob_median_gt_0: `0.896667`

## Interpretation
- Stage19B is exact historical validation, not forward proof.
- Promotion here only allows later forward-shadow collector design.
- Do not add this candidate to Stage18A unless the final decision is promotion.
- No paper/live/order escalation is authorized.

## Output files
- trades_csv: `data/reports/stage19b_compression_breakout_exact_replay/stage19b_exact_trades.csv`
- by_year_csv: `data/reports/stage19b_compression_breakout_exact_replay/stage19b_exact_by_year.csv`
- by_quarter_csv: `data/reports/stage19b_compression_breakout_exact_replay/stage19b_exact_by_quarter.csv`
- by_month_csv: `data/reports/stage19b_compression_breakout_exact_replay/stage19b_exact_by_month.csv`
- json: `data/reports/stage19b_compression_breakout_exact_replay/stage19b_compression_breakout_exact_replay.json`
- md: `data/reports/stage19b_compression_breakout_exact_replay/stage19b_compression_breakout_exact_replay.md`
