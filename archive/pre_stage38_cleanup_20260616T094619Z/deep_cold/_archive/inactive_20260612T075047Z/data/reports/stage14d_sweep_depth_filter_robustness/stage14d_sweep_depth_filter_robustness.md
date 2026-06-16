# Stage 14D Sweep-Depth Filter Robustness

Generated UTC: `2026-06-11T05:40:02+00:00`
Tool version: `v1`

> Hard rule: focused validation only. No EA change, no automatic trading, no paper/live authorization.

## Candidate
- mechanism: `prev_day_low_sweep_rejection`
- side: `LONG`
- horizon_bars: `4`
- filter: `sweep_depth_ge_q50`
- sweep_depth_threshold: `1.62`
- cost_usd: `0.35`

## Final decision
- final_decision: `SPLIT_FRAGILE_FILTER`

## Reasons
- Chronological split 0.8 test segment is not independently positive enough.

## Baseline vs filtered
| Set | Events | Total | Avg | Median | WR | PF | DD | Pos years | Pos quarters |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline_net_x1_all_candidate | 377 | 108.61 | 0.28809 | -0.02 | 0.496021 | 1.116218 | -117.64 | 4/5 | 9/17 |
| filtered_net_x1 | 189 | 176.36 | 0.933122 | 0.98 | 0.582011 | 1.311932 | -130.6 | 3/5 | 12/17 |

## Cost stress
| Cost x | Cost USD | Events | Total | Avg | Median | WR | PF | DD |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 0.0 | 189 | 242.51 | 1.283122 | 1.33 | 0.603175 | 1.450218 | -128.5 |
| 1 | 0.35 | 189 | 176.36 | 0.933122 | 0.98 | 0.582011 | 1.311932 | -130.6 |
| 2 | 0.7 | 189 | 110.21 | 0.583122 | 0.63 | 0.539683 | 1.185274 | -132.7 |
| 4 | 1.4 | 189 | -22.09 | -0.116878 | -0.07 | 0.486772 | 0.966475 | -136.9 |

## Chronological splits - net x1
| Train frac | Segment | Events | Total | Avg | Median | WR | PF | DD |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 0.6 | train | 113 | 80.07 | 0.708584 | 0.59 | 0.566372 | 1.381104 | -41.37 |
| 0.6 | test | 76 | 96.29 | 1.266974 | 1.74 | 0.605263 | 1.271026 | -130.6 |
| 0.7 | train | 132 | 117.65 | 0.891288 | 0.97 | 0.583333 | 1.496833 | -41.37 |
| 0.7 | test | 57 | 58.71 | 1.03 | 1.67 | 0.578947 | 1.178678 | -130.6 |
| 0.8 | train | 151 | 180.54 | 1.195629 | 0.99 | 0.602649 | 1.657729 | -41.37 |
| 0.8 | test | 38 | -4.18 | -0.11 | -0.49 | 0.5 | 0.98563 | -130.6 |

## Year distribution - net x1
| Year | Events | Total | Avg | Median | WR | PF | DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2022 | 30 | -20.39 | -0.679667 | -1.11 | 0.433333 | 0.744005 | -41.37 |
| 2023 | 38 | 36.2 | 0.952632 | 0.515 | 0.631579 | 1.677649 | -18.09 |
| 2024 | 32 | 38.4 | 1.2 | 1.24 | 0.5625 | 1.766926 | -18.93 |
| 2025 | 54 | 174.45 | 3.230556 | 1.98 | 0.703704 | 2.74015 | -20.57 |
| 2026 | 35 | -52.3 | -1.494286 | -1.42 | 0.485714 | 0.814532 | -130.6 |

## MFE/MAE quality
```json
{
  "avg_mfe": 14.83455,
  "avg_mae": 16.856561,
  "median_mfe": 9.85,
  "median_mae": 8.31,
  "mfe_gt_mae_rate": 0.544974,
  "avg_mfe_mae_ratio": 0.880046
}
```

## Bootstrap - net x1
```json
{
  "n": 500,
  "total_p05": -49.394,
  "total_p50": 171.24,
  "total_p95": 411.8495,
  "median_p05": 0.09,
  "median_p50": 0.98,
  "pf_p05": 0.927078,
  "pf_p50": 1.308878,
  "prob_total_gt_0": 0.9,
  "prob_median_gt_0": 0.986,
  "prob_pf_gt_1": 0.9
}
```

## Interpretation
- `ROBUST_FILTER_CANDIDATE_FOR_EXACT_REPLAY` permits exact replay validation for this single filtered mechanism only.
- `ROBUST_ENOUGH_FOR_EXACT_REPLAY_BUT_COST_SENSITIVE` permits exact replay but requires strict execution-cost awareness.
- Any failure rejects this filtered candidate definition, not XAUUSD as a market.
- No EA/paper/live/order authorization is granted by this report.

## Output files
- filtered_csv: `data/reports/stage14d_sweep_depth_filter_robustness/stage14d_filtered_outcomes.csv`
- cost_csv: `data/reports/stage14d_sweep_depth_filter_robustness/stage14d_cost_stress.csv`
- split_csv: `data/reports/stage14d_sweep_depth_filter_robustness/stage14d_chronological_splits.csv`
- year_csv: `data/reports/stage14d_sweep_depth_filter_robustness/stage14d_by_year.csv`
- quarter_csv: `data/reports/stage14d_sweep_depth_filter_robustness/stage14d_by_quarter.csv`
- month_csv: `data/reports/stage14d_sweep_depth_filter_robustness/stage14d_by_month.csv`
- rolling_csv: `data/reports/stage14d_sweep_depth_filter_robustness/stage14d_rolling_windows.csv`
- json: `data/reports/stage14d_sweep_depth_filter_robustness/stage14d_sweep_depth_filter_robustness.json`
- md: `data/reports/stage14d_sweep_depth_filter_robustness/stage14d_sweep_depth_filter_robustness.md`
