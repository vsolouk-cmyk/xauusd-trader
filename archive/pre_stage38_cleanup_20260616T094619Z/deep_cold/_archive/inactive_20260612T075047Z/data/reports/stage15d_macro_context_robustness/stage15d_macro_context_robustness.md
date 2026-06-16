# Stage 15D Macro Context Robustness

Generated UTC: `2026-06-11T06:07:52+00:00`
Tool version: `v1`

> Hard rule: macro context robustness only. No EA change, no automatic trading, no paper/live authorization.

## Context under validation
- top_context: `macro_daily_regime_real_yield_10y_chg5_up`
- context_column: `macro_daily_regime_real_yield_10y__chg5`
- selected_direction: `up`

## Final decision
- final_decision: `MACRO_CONTEXT_ROBUST_BUT_COUNTERINTUITIVE`

## Reasons
- Selected macro direction is counterintuitive for gold-supportive macro logic; interpret as pressure/reversal context, not bullish macro support.
- Allowed next step is forward-shadow research with this context logged, not automatic trading.

## Baseline vs selected/opposite direction
| Set | Events | Total | Avg | Median | WR | PF | DD | Pos years | Pos quarters |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline_all_stage15b | 94 | 143.48 | 1.526383 | 1.105 | 0.617021 | 1.960246 | -58.78 | 4/5 | 10/17 |
| selected_direction | 48 | 137.76 | 2.87 | 1.5 | 0.6875 | 3.446023 | -19.77 | 4/5 | 12/16 |
| opposite_direction | 40 | 22.18 | 0.5545 | 0.715 | 0.575 | 1.298962 | -25.63 | 4/5 | 8/16 |

## Context buckets
| Bucket | Events | Coverage | Total | Median | WR | PF | DD | Test total | Test PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| moderate_direction | 22 | 0.234043 | 138.89 | 3.685 | 0.818182 | 12.911664 | -11.66 | 101.74 | 999.0 |
| selected_direction | 48 | 0.510638 | 137.76 | 1.5 | 0.6875 | 3.446023 | -19.77 | 103.24 | 6.556512 |
| non_missing | 94 | 1.0 | 143.48 | 1.105 | 0.617021 | 1.960246 | -58.78 | 126.97 | 4.61841 |
| opposite_direction | 40 | 0.425532 | 22.18 | 0.715 | 0.575 | 1.298962 | -25.63 | 16.61 | 1.697899 |
| stronger_direction_tail | 26 | 0.276596 | -1.13 | 0.67 | 0.576923 | 0.974698 | -15.94 | -2.21 | 0.881055 |
| missing | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## Chronological splits - selected direction
| Train frac | Segment | Events | Total | Avg | Median | WR | PF | DD |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 0.6 | train | 28 | 22.8 | 0.814286 | 0.67 | 0.535714 | 1.604134 | -19.77 |
| 0.6 | test | 20 | 114.96 | 5.748 | 2.535 | 0.9 | 7.187298 | -15.94 |
| 0.7 | train | 33 | 34.52 | 1.046061 | 1.29 | 0.606061 | 1.914679 | -19.77 |
| 0.7 | test | 15 | 103.24 | 6.882667 | 2.86 | 0.866667 | 6.556512 | -15.94 |
| 0.8 | train | 38 | 43.81 | 1.152895 | 1.33 | 0.631579 | 2.084943 | -19.77 |
| 0.8 | test | 10 | 93.95 | 9.395 | 9.745 | 0.9 | 6.893977 | -15.94 |

## Year distribution - selected direction
| Year | Events | Total | Avg | Median | WR | PF | DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2022 | 6 | -15.85 | -2.641667 | -1.955 | 0.333333 | 0.250237 | -19.77 |
| 2023 | 13 | 10.01 | 0.77 | 0.44 | 0.538462 | 1.99602 | -8.35 |
| 2024 | 11 | 34.83 | 3.166364 | 2.35 | 0.727273 | 6.317557 | -5.18 |
| 2025 | 13 | 68.9 | 5.3 | 1.81 | 0.923077 | 27.098485 | -2.64 |
| 2026 | 5 | 39.87 | 7.974 | 11.64 | 0.8 | 3.501255 | -15.94 |

## Bootstrap - selected direction
```json
{
  "n": 500,
  "total_p05": 47.368,
  "total_p50": 135.97,
  "total_p95": 222.411,
  "pf_p05": 1.631015,
  "pf_p50": 3.615448,
  "median_p05": 0.44,
  "median_p50": 1.5,
  "prob_total_gt_0": 0.998,
  "prob_pf_gt_1": 0.998,
  "prob_median_gt_0": 1.0
}
```

## Interpretation
- `MACRO_CONTEXT_ROBUST_BUT_COUNTERINTUITIVE` means the context is statistically useful but should be interpreted as pressure/reversal, not bullish macro support.
- `MACRO_CONTEXT_ROBUST_FOR_FORWARD_SHADOW_RESEARCH` permits only research-forward-shadow design.
- Any failure rejects this macro context; it does not reject XAUUSD as a market.
- No EA/paper/live/order authorization is granted.

## Output files
- selected_csv: `data/reports/stage15d_macro_context_robustness/stage15d_selected_context_trades.csv`
- opposite_csv: `data/reports/stage15d_macro_context_robustness/stage15d_opposite_context_trades.csv`
- bucket_csv: `data/reports/stage15d_macro_context_robustness/stage15d_context_bucket_summary.csv`
- year_csv: `data/reports/stage15d_macro_context_robustness/stage15d_selected_by_year.csv`
- quarter_csv: `data/reports/stage15d_macro_context_robustness/stage15d_selected_by_quarter.csv`
- month_csv: `data/reports/stage15d_macro_context_robustness/stage15d_selected_by_month.csv`
- split_csv: `data/reports/stage15d_macro_context_robustness/stage15d_selected_splits.csv`
- json: `data/reports/stage15d_macro_context_robustness/stage15d_macro_context_robustness.json`
- md: `data/reports/stage15d_macro_context_robustness/stage15d_macro_context_robustness.md`
