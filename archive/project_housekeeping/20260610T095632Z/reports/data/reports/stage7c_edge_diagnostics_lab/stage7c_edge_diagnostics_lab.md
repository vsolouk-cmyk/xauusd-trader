# Stage 7C Edge Diagnostics Lab

Generated UTC: `2026-06-09T13:18:00+00:00`
Tool version: `v1`

> Hard rule: research only. This does not authorize demo, paper, or live orders.

## Inputs
- db: `data/local/xauusd_local_store.sqlite`
- trades_csv: `data/reports/stage7b_strategy_redesign_lab/stage7b_strategy_trades.csv`
- m1_rows: `1449867`
- trades_loaded: `4469`
- horizons: `[3, 6, 12]`

## Summary ranking
| Family | Design | Guard | Horizon | Diagnosis | Trades | Median MFE | Median MAE | TP15 first | SL15 first | TP24 first | SL24 first | MFE-absMAE |
|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline_sma_distance_v1_control | control_v1_long | macro_blocked | 12 | EXIT_DESIGN_WEAK_ENTRY_HAS_SOME_MFE | 1105 | 18.25 | -17.29 | 0.404525 | 0.40181 | 0.277828 | 0.462443 | -1.66829 |
| baseline_sma_distance_v1_control | control_v1_long | unguarded | 12 | EXIT_DESIGN_WEAK_ENTRY_HAS_SOME_MFE | 1108 | 18.17 | -17.305 | 0.404332 | 0.402527 | 0.277076 | 0.463899 | -1.685298 |
| baseline_sma_distance_v1_control | control_v1_long | macro_blocked | 6 | ENTRY_OR_STOP_GEOMETRY_WEAK | 1105 | 13.25 | -13.12 | 0.356561 | 0.365611 | 0.21991 | 0.41448 | -0.430652 |
| baseline_sma_distance_v1_control | control_v1_long | unguarded | 6 | ENTRY_OR_STOP_GEOMETRY_WEAK | 1108 | 13.275 | -13.18 | 0.356498 | 0.365523 | 0.219314 | 0.415162 | -0.440162 |
| h4_trend_h1_pullback_continuation | balanced_pullback | macro_blocked | 12 | NO_CLEAR_EDGE | 699 | 9.4 | -8.59 | 0.286123 | 0.260372 | 0.16166 | 0.294707 | 0.167167 |
| h4_trend_h1_pullback_continuation | balanced_pullback | unguarded | 12 | NO_CLEAR_EDGE | 701 | 9.4 | -8.59 | 0.285307 | 0.261056 | 0.161198 | 0.295292 | 0.157047 |
| compression_expansion_confirmed | range16_pct18_expansion | macro_blocked | 12 | ENTRY_OR_STOP_GEOMETRY_WEAK | 428 | 9.0 | -10.495 | 0.28271 | 0.310748 | 0.142523 | 0.32243 | 0.545023 |
| compression_expansion_confirmed | range16_pct18_expansion | unguarded | 12 | ENTRY_OR_STOP_GEOMETRY_WEAK | 428 | 9.0 | -10.495 | 0.28271 | 0.310748 | 0.142523 | 0.32243 | 0.545023 |
| baseline_sma_distance_v1_control | control_v1_long | unguarded | 3 | ENTRY_OR_STOP_GEOMETRY_WEAK | 1108 | 9.78 | -9.42 | 0.281588 | 0.305054 | 0.16065 | 0.33574 | -0.870776 |
| baseline_sma_distance_v1_control | control_v1_long | macro_blocked | 3 | ENTRY_OR_STOP_GEOMETRY_WEAK | 1105 | 9.77 | -9.42 | 0.281448 | 0.304977 | 0.161086 | 0.334842 | -0.862434 |
| compression_expansion_confirmed | range16_pct18_expansion | macro_blocked | 6 | ENTRY_OR_STOP_GEOMETRY_WEAK | 428 | 6.895 | -7.915 | 0.207944 | 0.233645 | 0.102804 | 0.240654 | 0.418505 |
| compression_expansion_confirmed | range16_pct18_expansion | unguarded | 6 | ENTRY_OR_STOP_GEOMETRY_WEAK | 428 | 6.895 | -7.915 | 0.207944 | 0.233645 | 0.102804 | 0.240654 | 0.418505 |
| h4_trend_h1_pullback_continuation | balanced_pullback | macro_blocked | 6 | NO_CLEAR_EDGE | 699 | 6.62 | -5.82 | 0.197425 | 0.18598 | 0.091559 | 0.20887 | 0.482046 |
| h4_trend_h1_pullback_continuation | balanced_pullback | unguarded | 6 | NO_CLEAR_EDGE | 701 | 6.65 | -5.86 | 0.196862 | 0.185449 | 0.091298 | 0.208274 | 0.489001 |
| compression_expansion_confirmed | range16_pct18_expansion | macro_blocked | 3 | ENTRY_OR_STOP_GEOMETRY_WEAK | 428 | 5.06 | -5.78 | 0.142523 | 0.172897 | 0.065421 | 0.17757 | -0.056519 |
| compression_expansion_confirmed | range16_pct18_expansion | unguarded | 3 | ENTRY_OR_STOP_GEOMETRY_WEAK | 428 | 5.06 | -5.78 | 0.142523 | 0.172897 | 0.065421 | 0.17757 | -0.056519 |
| h4_trend_h1_pullback_continuation | balanced_pullback | macro_blocked | 3 | NO_CLEAR_EDGE | 699 | 4.19 | -4.14 | 0.128755 | 0.11731 | 0.062947 | 0.125894 | -0.092432 |
| h4_trend_h1_pullback_continuation | balanced_pullback | unguarded | 3 | NO_CLEAR_EDGE | 701 | 4.19 | -4.14 | 0.128388 | 0.116976 | 0.062767 | 0.125535 | -0.086819 |

## Interpretation
- `ENTRY_EDGE_WEAK`: price usually does not move favorably enough after entry.
- `ENTRY_OR_STOP_GEOMETRY_WEAK`: even 15/15 first-hit test does not favor TP.
- `EXIT_DESIGN_WEAK_ENTRY_HAS_SOME_MFE`: entry has some favorable excursion, but realized exit design is poor.
- `TP_TOO_FAR_CONSIDER_SMALLER_TARGET_RESEARCH_ONLY`: 24 USD target may be too far relative to signal quality.
- `WATCHLIST_ENTRY_EDGE_POSSIBLE`: only a research candidate; still requires Stage 7D validation.

## Decision
- Do not add more filters before reading this diagnosis.
- If all groups are weak, redesign entries from higher-level market structure or add discretionary/macro regime layer.
- No EA change is allowed from this report.
