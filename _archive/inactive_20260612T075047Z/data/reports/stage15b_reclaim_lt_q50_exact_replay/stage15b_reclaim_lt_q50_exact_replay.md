# Stage 15B Reclaim-lt-q50 Exact Replay

Generated UTC: `2026-06-11T05:51:49+00:00`
Tool version: `v1`

> Hard rule: exact replay research only. No EA change, no automatic trading, no paper/live authorization.

## Candidate
- setup: `prev_day_low_sweep_rejection`
- side: `LONG`
- branch: `sweep_depth_ge_q50`
- regime: `reclaim_lt_q50`
- reclaim_q50: `1.55`
- events: `94`
- horizon_min: `60`
- cost_usd: `0.35`

## Final decision
- final_decision: `EXACT_REPLAY_VALIDATED_RESEARCH_CANDIDATE`

## Reasons
- Time-exit geometry remains acceptable or best among limited geometries.
- Exact replay preserves candidate quality. Still no EA/paper/live authorization.

## M15 original vs M1 exact replay
| Result set | Events | Total | Avg | Median | WR | PF | DD | Pos years | Pos quarters |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| original_m15_net_x1 | 94 | 145.33 | 1.546064 | 1.185 | 0.617021 | 1.972627 | -58.78 | 4/5 | 10/17 |
| exact_m1_time_exit_net_x1 | 94 | 143.48 | 1.526383 | 1.105 | 0.617021 | 1.960246 | -58.78 | 4/5 | 10/17 |
| exact_m1_time_exit_net_x2 | 94 | 110.58 | 1.176383 | 0.755 | 0.56383 | 1.678031 | -65.08 | 4/5 | 9/17 |
| exact_m1_time_exit_net_x4 | 94 | 44.78 | 0.476383 | 0.055 | 0.5 | 1.231601 | -77.68 | 4/5 | 7/17 |

## Current 2026 exact replay net x1
| Events | Total | Avg | Median | WR | PF | DD |
|---:|---:|---:|---:|---:|---:|---:|
| 8 | 46.9 | 5.8625 | 7.08 | 0.75 | 3.701613 | -15.94 |

## Chronological splits - exact M1 time-exit net x1
| Train frac | Segment | Events | Total | Avg | Median | WR | PF | DD |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 0.6 | train | 56 | 1.53 | 0.027321 | 0.06 | 0.5 | 1.014298 | -58.78 |
| 0.6 | test | 38 | 141.95 | 3.735526 | 1.72 | 0.789474 | 4.347088 | -15.94 |
| 0.7 | train | 65 | 16.51 | 0.254 | 0.44 | 0.538462 | 1.144407 | -58.78 |
| 0.7 | test | 29 | 126.97 | 4.378276 | 1.81 | 0.793103 | 4.61841 | -15.94 |
| 0.8 | train | 75 | 24.59 | 0.327867 | 0.98 | 0.56 | 1.201145 | -58.78 |
| 0.8 | test | 19 | 118.89 | 6.257368 | 2.64 | 0.842105 | 5.375782 | -15.94 |

## Limited geometry summary - M1 path, net x1
| Geometry | Events | Total | Avg | Median | WR | PF | DD | TP | SL | Time exit | Ambiguous |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| time_exit_60m | 94 | 143.48 | 1.526383 | 1.105 | 0.617021 | 1.960246 | -58.78 | 0 | 0 | 94 | 0 |
| tp15_sl12 | 94 | 91.74 | 0.975957 | 1.01 | 0.606383 | 1.505148 | -72.08 | 9 | 7 | 78 | 0 |
| tp8_sl6 | 94 | 50.32 | 0.535319 | 1.01 | 0.574468 | 1.289895 | -52.07 | 18 | 20 | 56 | 0 |
| tp12_sl10 | 94 | 45.11 | 0.479894 | 0.94 | 0.585106 | 1.236785 | -67.74 | 10 | 11 | 73 | 0 |
| tp6_sl6 | 94 | 20.99 | 0.223298 | 1.01 | 0.574468 | 1.120924 | -50.73 | 27 | 20 | 47 | 0 |
| tp10_sl8 | 94 | 19.17 | 0.203936 | 0.67 | 0.56383 | 1.096467 | -59.74 | 11 | 15 | 68 | 0 |

## Year distribution - exact M1 time-exit net x1
| Year | Events | Total | Avg | Median | WR | PF | DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2022 | 19 | -54.86 | -2.887368 | -2.41 | 0.263158 | 0.178127 | -58.78 |
| 2023 | 21 | 30.28 | 1.441905 | 1.18 | 0.666667 | 2.377616 | -11.93 |
| 2024 | 23 | 41.7 | 1.813043 | 1.63 | 0.652174 | 3.277444 | -10.51 |
| 2025 | 23 | 79.46 | 3.454783 | 1.19 | 0.782609 | 4.175859 | -9.81 |
| 2026 | 8 | 46.9 | 5.8625 | 7.08 | 0.75 | 3.701613 | -15.94 |

## Bootstrap - exact M1 time-exit net x1
```json
{
  "n": 500,
  "total_p05": 33.4725,
  "total_p50": 143.485,
  "total_p95": 262.7365,
  "pf_p05": 1.180472,
  "pf_p50": 1.981505,
  "median_p05": 0.15,
  "median_p50": 1.105,
  "prob_total_gt_0": 0.974,
  "prob_pf_gt_1": 0.974,
  "prob_median_gt_0": 0.988
}
```

## Interpretation
- `EXACT_REPLAY_VALIDATED_RESEARCH_CANDIDATE` permits the next research-only step: forward-shadow design, not orders.
- `EXACT_REPLAY_CANDIDATE_BUT_CURRENT_REGIME_FRAGILE` means historical edge exists but current-regime use remains unsafe.
- Any rejection closes this branch; it does not reject XAUUSD as a market.
- No EA/paper/live/order authorization is granted.

## Output files
- replay_csv: `data/reports/stage15b_reclaim_lt_q50_exact_replay/stage15b_exact_replay_trades.csv`
- geometry_csv: `data/reports/stage15b_reclaim_lt_q50_exact_replay/stage15b_geometry_summary.csv`
- year_csv: `data/reports/stage15b_reclaim_lt_q50_exact_replay/stage15b_by_year.csv`
- quarter_csv: `data/reports/stage15b_reclaim_lt_q50_exact_replay/stage15b_by_quarter.csv`
- month_csv: `data/reports/stage15b_reclaim_lt_q50_exact_replay/stage15b_by_month.csv`
- split_csv: `data/reports/stage15b_reclaim_lt_q50_exact_replay/stage15b_splits.csv`
- json: `data/reports/stage15b_reclaim_lt_q50_exact_replay/stage15b_reclaim_lt_q50_exact_replay.json`
- md: `data/reports/stage15b_reclaim_lt_q50_exact_replay/stage15b_reclaim_lt_q50_exact_replay.md`
