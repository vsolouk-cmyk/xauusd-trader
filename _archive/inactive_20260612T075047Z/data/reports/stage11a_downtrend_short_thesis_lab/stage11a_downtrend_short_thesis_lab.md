# Stage 11A Downtrend Short-Side Thesis Lab

Generated UTC: `2026-06-10T10:53:08+00:00`
Tool version: `v2_warning_fix`

> Hard rule: research only. No EA change, no automatic trading, no paper/live authorization.

## Inputs
- db: `data/local/xauusd_local_store.sqlite`
- h1_rows: `24225`
- h4_rows: `6482`
- variants_tested: `576`
- trades_generated: `6536`

## Decision
- decision: `no_short_candidate_yet`
- robust_candidate_count: `0`

## Top candidates
| Rank | Variant | Trades | Total x4 | Test x4 | PF | WR | Median | DD | Pos years | Pos quarters | Robust |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | h4sma20_slope3_break6_comp6_2.2_cool1_all | 153 | 694.92 | 305.2 | 1.132886 | 0.424837 | -6.6 | -827.44 | 3/5 | 9/17 | False |
| 2 | h4sma20_slope3_break6_comp6_2.2_cool1_ny_only | 22 | 227.52 | 261.44 | 1.265175 | 0.363636 | -9.64 | -242.92 | 2/5 | 4/12 | False |
| 3 | h4sma20_slope3_break6_comp6_2.2_cool4_ny_only | 22 | 227.52 | 261.44 | 1.265175 | 0.363636 | -9.64 | -242.92 | 2/5 | 4/12 | False |
| 4 | h4sma10_slope3_break6_comp6_2.2_cool1_ny_only | 19 | -55.56 | 31.12 | 0.90254 | 0.368421 | -13.04 | -357.2 | 2/5 | 4/13 | False |
| 5 | h4sma10_slope3_break6_comp6_2.2_cool4_ny_only | 19 | -55.56 | 31.12 | 0.90254 | 0.368421 | -13.04 | -357.2 | 2/5 | 4/13 | False |
| 6 | h4sma20_slope2_break6_comp6_2.2_cool1_ny_only | 21 | -26.64 | 7.28 | 0.968951 | 0.333333 | -13.04 | -364.32 | 1/5 | 3/12 | False |
| 7 | h4sma20_slope2_break6_comp6_2.2_cool4_ny_only | 21 | -26.64 | 7.28 | 0.968951 | 0.333333 | -13.04 | -364.32 | 1/5 | 3/12 | False |
| 8 | h4sma10_slope3_break18_comp12_2.2_cool1_all | 3 | 121.56 | 0.0 | 999.0 | 1.0 | 28.84 | 0.0 | 2/2 | 3/3 | False |
| 9 | h4sma10_slope3_break18_comp12_2.2_cool4_all | 3 | 121.56 | 0.0 | 999.0 | 1.0 | 28.84 | 0.0 | 2/2 | 3/3 | False |
| 10 | h4sma10_slope2_break18_comp12_2.2_cool1_all | 2 | 92.72 | 0.0 | 999.0 | 1.0 | 46.36 | 0.0 | 2/2 | 2/2 | False |

## Interpretation
- This lab tests a short-side counterpart to the long-only Stage 8D candidate.
- A candidate is useful only if test-period performance is positive and robustness metrics are acceptable.
- If no robust candidate appears, do not force a short EA; move to alternate short thesis geometry.

## Outputs
- summary_csv: `data/reports/stage11a_downtrend_short_thesis_lab/stage11a_short_candidate_summary.csv`
- trades_csv: `data/reports/stage11a_downtrend_short_thesis_lab/stage11a_short_candidate_trades.csv`
- json: `data/reports/stage11a_downtrend_short_thesis_lab/stage11a_downtrend_short_thesis_lab.json`

## Decision rule
- `short_candidate_found` permits Stage 11B robustness/execution-replay research only.
- It does not permit EA order code, paper order, or live execution.
