# Stage 17B PDH Breakout Continuation Exact Replay

Generated UTC: `2026-06-11T07:17:35+00:00`
Tool version: `v1`

> Hard rule: research validation only. No EA change, no automatic trading, no paper/live authorization.

## Candidate
- variant: `pdh_breakout_continuation_long_h32_cool4`
- side: `LONG`
- behavior: `previous-day high breakout continuation`
- horizon_bars: `32`
- horizon_minutes: `480`
- cooldown_bars: `4`
- buffer_usd: `0.2`
- close_above_pdh: `0.8`
- cost_usd: `0.35`

## Final decision
- final_decision: `EXACT_REPLAY_PROMOTE_TO_FORWARD_SHADOW_DESIGN`

## Reasons
- Exact M1 replay preserves Stage17A breakout-continuation edge.
- Allowed next step is research-only forward-shadow design for this behavior.

## Exact M1 time-exit replay
| Result set | Events | Total | Avg | Median | WR | PF | DD | Pos years | Pos quarters |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| net_x1 | 758 | 1171.09 | 1.544974 | 0.765 | 0.527704 | 1.256304 | -295.03 | 4/5 | 12/17 |
| net_x2 | 758 | 905.79 | 1.194974 | 0.415 | 0.514512 | 1.192869 | -303.43 | 2/5 | 8/17 |
| net_x4 | 758 | 375.19 | 0.494974 | -0.285 | 0.493404 | 1.075642 | -564.36 | 2/5 | 7/17 |

## Chronological splits
| Split | Segment | Events | Total | Avg | Median | WR | PF | DD |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 0.7 | train | 530 | 134.13 | 0.253075 | 0.185 | 0.511321 | 1.061186 | -150.97 |
| 0.7 | test | 228 | 1036.96 | 4.54807 | 4.19 | 0.565789 | 1.436251 | -295.03 |
| 0.8 | train | 606 | 453.16 | 0.747789 | 0.595 | 0.523102 | 1.169743 | -150.97 |
| 0.8 | test | 152 | 717.93 | 4.723224 | 4.875 | 0.546053 | 1.377965 | -295.03 |

## 2026 segment
| Events | Total | Avg | Median | WR | PF | DD |
|---:|---:|---:|---:|---:|---:|---:|
| 78 | 339.87 | 4.357308 | -0.225 | 0.5 | 1.289658 | -295.03 |

## Limited geometry summary - M1 path, net x1
| Geometry | Events | Total | Avg | Median | WR | PF | DD | TP | SL | Time exit | Ambiguous |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| time_exit_8h | 758 | 1171.09 | 1.544974 | 0.765 | 0.527704 | 1.256304 | -295.03 | 0 | 0 | 758 | 0 |
| tp50_sl30 | 758 | 804.94 | 1.061926 | 0.53 | 0.51715 | 1.18244 | -242.8 | 27 | 79 | 652 | 0 |
| tp40_sl25 | 758 | 700.01 | 0.923496 | 0.18 | 0.507916 | 1.162022 | -216.25 | 45 | 102 | 611 | 0 |
| tp24_sl15 | 758 | 535.59 | 0.706583 | -0.265 | 0.493404 | 1.14075 | -184.5 | 101 | 192 | 465 | 0 |
| tp20_sl15 | 758 | 520.01 | 0.686029 | 0.03 | 0.501319 | 1.140045 | -186.4 | 144 | 186 | 428 | 0 |
| tp30_sl20 | 758 | 571.31 | 0.753707 | 0.1 | 0.505277 | 1.136914 | -172.25 | 76 | 139 | 543 | 0 |

## Year distribution - exact M1 net x1
| Year | Events | Total | Avg | Median | WR | PF | DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2022 | 96 | -67.21 | -0.700104 | -0.235 | 0.5 | 0.807532 | -113.76 |
| 2023 | 168 | 44.46 | 0.264643 | -0.53 | 0.47619 | 1.06916 | -103.67 |
| 2024 | 199 | 19.05 | 0.095729 | 0.52 | 0.522613 | 1.020497 | -150.97 |
| 2025 | 217 | 834.92 | 3.847558 | 3.8 | 0.59447 | 1.566301 | -265.88 |
| 2026 | 78 | 339.87 | 4.357308 | -0.225 | 0.5 | 1.289658 | -295.03 |

## Bootstrap - exact M1 net x1
```json
{
  "n": 500,
  "total_p05": 167.6625,
  "total_p50": 1147.76,
  "total_p95": 2078.2515,
  "pf_p05": 1.033026,
  "pf_p50": 1.252801,
  "median_p05": -0.145,
  "median_p50": 0.77,
  "prob_total_gt_0": 0.972,
  "prob_pf_gt_1": 0.972,
  "prob_median_gt_0": 0.918
}
```

## Interpretation
- `EXACT_REPLAY_PROMOTE_TO_FORWARD_SHADOW_DESIGN` permits only research-only shadow design for this behavior.
- Any failure rejects or pauses this breakout candidate, not the broader XAUUSD project.
- Stage16 true-forward collector should continue in parallel.
- No EA/paper/live/order authorization is granted.

## Output files
- signals_csv: `data/reports/stage17b_pdh_breakout_exact_replay/stage17b_detected_signals.csv`
- trades_csv: `data/reports/stage17b_pdh_breakout_exact_replay/stage17b_exact_replay_trades.csv`
- geometry_csv: `data/reports/stage17b_pdh_breakout_exact_replay/stage17b_geometry_summary.csv`
- year_csv: `data/reports/stage17b_pdh_breakout_exact_replay/stage17b_by_year.csv`
- quarter_csv: `data/reports/stage17b_pdh_breakout_exact_replay/stage17b_by_quarter.csv`
- session_csv: `data/reports/stage17b_pdh_breakout_exact_replay/stage17b_by_session.csv`
- hour_csv: `data/reports/stage17b_pdh_breakout_exact_replay/stage17b_by_hour.csv`
- json: `data/reports/stage17b_pdh_breakout_exact_replay/stage17b_pdh_breakout_exact_replay.json`
- md: `data/reports/stage17b_pdh_breakout_exact_replay/stage17b_pdh_breakout_exact_replay.md`
