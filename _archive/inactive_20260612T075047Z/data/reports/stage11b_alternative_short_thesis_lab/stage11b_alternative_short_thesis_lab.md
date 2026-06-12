# Stage 11B Alternative Short Thesis Lab

Generated UTC: `2026-06-10T19:04:57+00:00`
Tool version: `v2_fast_grid`

> Hard rule: research only. No EA change, no automatic trading, no paper/live authorization.

## Inputs
- db: `data/local/xauusd_local_store.sqlite`
- mode: `full`
- h1_rows: `24225`
- h4_rows: `6482`
- variants_tested: `11880`
- trades_generated: `256515`

## Decision
- decision: `short_candidate_found`
- robust_candidate_count: `114`

## Top candidates
| Rank | Definition | Variant | Trades | Total x4 | Test x4 | PF | WR | Median | DD | Pos years | Pos quarters | Robust |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | short_bearish_impulse_after_compression | short_bearish_impulse_after_compression_h4sma10_slope2_look12_comp6_2.8_rej6_imp0.8_h6_cool1_london | 48 | 1245.68 | 961.84 | 2.257856 | 0.604167 | 11.82 | -413.04 | 4/5 | 11/16 | True |
| 2 | short_bearish_impulse_after_compression | short_bearish_impulse_after_compression_h4sma10_slope2_look12_comp6_2.8_rej6_imp0.8_h6_cool4_london | 48 | 1245.68 | 961.84 | 2.257856 | 0.604167 | 11.82 | -413.04 | 4/5 | 11/16 | True |
| 3 | short_compression_breakdown | short_compression_breakdown_h4sma10_slope2_look12_comp6_2.8_rej6_imp1.2_h6_cool1_london | 77 | 1167.36 | 934.04 | 1.682124 | 0.545455 | 6.24 | -503.24 | 4/5 | 10/17 | True |
| 4 | short_compression_breakdown | short_compression_breakdown_h4sma10_slope2_look12_comp6_2.8_rej6_imp1.2_h6_cool4_london | 77 | 1167.36 | 934.04 | 1.682124 | 0.545455 | 6.24 | -503.24 | 4/5 | 10/17 | True |
| 5 | short_bearish_impulse_after_compression | short_bearish_impulse_after_compression_h4sma10_slope2_look6_comp6_2.8_rej6_imp0.8_h6_cool1_london | 82 | 1786.84 | 919.4 | 2.084774 | 0.585366 | 9.68 | -343.8 | 4/5 | 12/17 | True |
| 6 | short_bearish_impulse_after_compression | short_bearish_impulse_after_compression_h4sma10_slope2_look6_comp6_2.8_rej6_imp0.8_h6_cool4_london | 82 | 1786.84 | 919.4 | 2.084774 | 0.585366 | 9.68 | -343.8 | 4/5 | 12/17 | True |
| 7 | short_compression_breakdown | short_compression_breakdown_h4sma20_slope2_look12_comp6_2.8_rej6_imp1.2_h6_cool1_london | 67 | 1169.0 | 899.16 | 1.818215 | 0.597015 | 10.36 | -384.4 | 3/5 | 8/16 | True |
| 8 | short_compression_breakdown | short_compression_breakdown_h4sma20_slope2_look12_comp6_2.8_rej6_imp1.2_h6_cool4_london | 67 | 1169.0 | 899.16 | 1.818215 | 0.597015 | 10.36 | -384.4 | 3/5 | 8/16 | True |
| 9 | short_compression_breakdown | short_compression_breakdown_h4sma20_slope3_look12_comp6_2.8_rej6_imp1.2_h6_cool1_london | 66 | 1165.56 | 899.16 | 1.815807 | 0.590909 | 11.82 | -387.84 | 3/5 | 8/16 | True |
| 10 | short_compression_breakdown | short_compression_breakdown_h4sma20_slope3_look12_comp6_2.8_rej6_imp1.2_h6_cool4_london | 66 | 1165.56 | 899.16 | 1.815807 | 0.590909 | 11.82 | -387.84 | 3/5 | 8/16 | True |
| 11 | short_bearish_impulse_after_compression | short_bearish_impulse_after_compression_h4sma10_slope2_look12_comp6_2.8_rej6_imp0.8_h12_cool1_london | 48 | 1235.36 | 887.08 | 2.135191 | 0.604167 | 15.36 | -364.52 | 3/5 | 12/16 | True |
| 12 | short_bearish_impulse_after_compression | short_bearish_impulse_after_compression_h4sma10_slope2_look12_comp6_2.8_rej6_imp0.8_h12_cool4_london | 48 | 1235.36 | 887.08 | 2.135191 | 0.604167 | 15.36 | -364.52 | 3/5 | 12/16 | True |

## Interpretation
- Stage 11B v2 uses a cached fast grid by default.
- If `mode=fast` finds a promising candidate, run strict robustness next.
- If no candidate appears, do not run full-grid automatically on the MacBook.

## Outputs
- summary_csv: `data/reports/stage11b_alternative_short_thesis_lab/stage11b_short_candidate_summary.csv`
- trades_csv: `data/reports/stage11b_alternative_short_thesis_lab/stage11b_short_candidate_trades.csv`
- json: `data/reports/stage11b_alternative_short_thesis_lab/stage11b_alternative_short_thesis_lab.json`
