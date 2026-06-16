# Stage 14B Previous-Day Low Sweep Validation

Generated UTC: `2026-06-10T22:34:39+00:00`
Tool version: `v1`

> Hard rule: focused validation only. No EA change, no automatic trading, no paper/live authorization.

## Candidate
- mechanism: `prev_day_low_sweep_rejection`
- side: `LONG`
- horizon_bars: `4`
- cost_usd: `0.35`
- train_frac: `0.7`
- rolling_window: `50`

## Final decision
- final_decision: `COST_FRAGILE_CANDIDATE`

## Reasons
- Median edge disappears after x1 cost; candidate is entry/cost sensitive.

## Raw metrics
| Events | Total | Avg | Median | WR | PF | DD |
|---:|---:|---:|---:|---:|---:|---:|
| 377 | 240.56 | 0.63809 | 0.33 | 0.522546 | 1.276455 | -112.49 |

## Cost stress
| Cost x | Cost USD | Events | Total | Avg | Median | WR | PF | DD |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.0 | 0.0 | 377 | 240.56 | 0.63809 | 0.33 | 0.522546 | 1.276455 | -112.49 |
| 1.0 | 0.35 | 377 | 108.61 | 0.28809 | -0.02 | 0.496021 | 1.116218 | -117.64 |
| 2.0 | 0.7 | 377 | -23.34 | -0.06191 | -0.37 | 0.448276 | 0.976768 | -185.16 |
| 4.0 | 1.4 | 377 | -287.24 | -0.76191 | -1.07 | 0.387268 | 0.751832 | -354.79 |

## Chronological split - raw
| Segment | Events | Total | Avg | Median | WR | PF | DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| train | 263 | 29.43 | 0.111901 | -0.04 | 0.498099 | 1.067587 | -96.64 |
| test | 114 | 211.13 | 1.852018 | 1.77 | 0.578947 | 1.485669 | -112.49 |

## Chronological split - net x1 cost
| Segment | Events | Total | Avg | Median | WR | PF | DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| train | 263 | -62.62 | -0.238099 | -0.39 | 0.460076 | 0.870357 | -117.64 |
| test | 114 | 171.23 | 1.502018 | 1.42 | 0.578947 | 1.37923 | -113.89 |

## MFE/MAE quality
```json
{
  "avg_mfe": 11.689072,
  "avg_mae": 12.344907,
  "median_mfe": 7.54,
  "median_mae": 6.34,
  "mfe_gt_mae_rate": 0.530504,
  "avg_mfe_mae_ratio": 0.946874
}
```

## Year distribution
| Year | Events | Total | Avg | Median | WR | PF | DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2022 | 75 | -74.48 | -0.993067 | -0.4 | 0.4 | 0.583072 | -96.64 |
| 2023 | 98 | 35.02 | 0.357347 | 0.11 | 0.510204 | 1.268971 | -26.14 |
| 2024 | 86 | 65.04 | 0.756279 | 0.455 | 0.55814 | 1.536634 | -36.26 |
| 2025 | 78 | 191.06 | 2.449487 | 1.705 | 0.615385 | 2.182668 | -33.94 |
| 2026 | 40 | 23.92 | 0.598 | 1.64 | 0.525 | 1.085867 | -112.49 |

## Interpretation
- If decision is `COST_FRAGILE_CANDIDATE`, the behavior may exist but the raw edge is too small for direct execution.
- If decision is `FILTER_REQUIRED_COST_SENSITIVE_CANDIDATE`, the behavior may deserve one focused filter study, not EA/paper/live.
- If decision is `VALIDATION_PASS_FOCUSED_REPLAY_CANDIDATE`, the next stage may run exact replay/robustness for this single mechanism.
- Any negative result rejects this candidate definition, not the whole XAUUSD market.

## Output files
- candidate_csv: `data/reports/stage14b_prev_day_low_sweep_validation/stage14b_candidate_outcomes.csv`
- cost_csv: `data/reports/stage14b_prev_day_low_sweep_validation/stage14b_cost_stress.csv`
- year_csv: `data/reports/stage14b_prev_day_low_sweep_validation/stage14b_by_year.csv`
- quarter_csv: `data/reports/stage14b_prev_day_low_sweep_validation/stage14b_by_quarter.csv`
- month_csv: `data/reports/stage14b_prev_day_low_sweep_validation/stage14b_by_month.csv`
- rolling_csv: `data/reports/stage14b_prev_day_low_sweep_validation/stage14b_rolling_event_windows.csv`
- json: `data/reports/stage14b_prev_day_low_sweep_validation/stage14b_prev_day_low_sweep_validation.json`
- md: `data/reports/stage14b_prev_day_low_sweep_validation/stage14b_prev_day_low_sweep_validation.md`
