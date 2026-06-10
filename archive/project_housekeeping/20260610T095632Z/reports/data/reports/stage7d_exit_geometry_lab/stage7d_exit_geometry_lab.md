# Stage 7D Exit Geometry Lab

Generated UTC: `2026-06-09T13:23:08+00:00`
Tool version: `v1`

> Hard rule: research only. This does not authorize demo, paper, or live orders.

## Inputs
- db: `data/local/xauusd_local_store.sqlite`
- trades_csv: `data/reports/stage7b_strategy_redesign_lab/stage7b_strategy_trades.csv`
- m1_rows: `1449867`
- entries_loaded: `4469`
- geometries: `[{'name': 'tp10_sl8_h3', 'tp_usd': 10.0, 'sl_usd': 8.0, 'horizon_hours': 3}, {'name': 'tp12_sl8_h3', 'tp_usd': 12.0, 'sl_usd': 8.0, 'horizon_hours': 3}, {'name': 'tp12_sl10_h6', 'tp_usd': 12.0, 'sl_usd': 10.0, 'horizon_hours': 6}, {'name': 'tp15_sl10_h6', 'tp_usd': 15.0, 'sl_usd': 10.0, 'horizon_hours': 6}, {'name': 'tp15_sl12_h6', 'tp_usd': 15.0, 'sl_usd': 12.0, 'horizon_hours': 6}, {'name': 'tp18_sl12_h12', 'tp_usd': 18.0, 'sl_usd': 12.0, 'horizon_hours': 12}, {'name': 'tp18_sl15_h12', 'tp_usd': 18.0, 'sl_usd': 15.0, 'horizon_hours': 12}, {'name': 'tp24_sl15_h12_control', 'tp_usd': 24.0, 'sl_usd': 15.0, 'horizon_hours': 12}]`

## Ranking
| Family | Design | Guard | Geometry | Decision | Score | Trades | Total x4 | PF x4 | Median x4 | DD x1 | Pos years | Pos sessions |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| h4_trend_h1_pullback_continuation | balanced_pullback | macro_blocked | tp24_sl15_h12_control | KILL_COST_STRESS_X4_NEGATIVE | -0.476345 | 699 | -498.94 | 0.884899 | -1.79 | -367.39 | 2/5 | 1/5 |
| h4_trend_h1_pullback_continuation | balanced_pullback | unguarded | tp24_sl15_h12_control | KILL_COST_STRESS_X4_NEGATIVE | -0.50543 | 701 | -518.23 | 0.880978 | -1.8 | -367.39 | 2/5 | 1/5 |
| h4_trend_h1_pullback_continuation | balanced_pullback | macro_blocked | tp18_sl15_h12 | KILL_COST_STRESS_X4_NEGATIVE | -0.531605 | 699 | -550.7 | 0.865914 | -1.22 | -358.17 | 2/5 | 1/5 |
| h4_trend_h1_pullback_continuation | balanced_pullback | macro_blocked | tp18_sl12_h12 | KILL_COST_STRESS_X4_NEGATIVE | -0.545885 | 699 | -631.43 | 0.839836 | -2.16 | -277.56 | 2/5 | 1/5 |
| h4_trend_h1_pullback_continuation | balanced_pullback | unguarded | tp18_sl15_h12 | KILL_COST_STRESS_X4_NEGATIVE | -0.56054 | 701 | -569.99 | 0.861866 | -1.22 | -358.17 | 2/5 | 1/5 |
| h4_trend_h1_pullback_continuation | balanced_pullback | unguarded | tp18_sl12_h12 | KILL_COST_STRESS_X4_NEGATIVE | -0.57062 | 701 | -647.72 | 0.83638 | -2.18 | -277.56 | 2/5 | 1/5 |
| h4_trend_h1_pullback_continuation | balanced_pullback | macro_blocked | tp15_sl12_h6 | KILL_COST_STRESS_X4_NEGATIVE | -0.941905 | 699 | -672.33 | 0.782918 | -1.0 | -278.94 | 1/5 | 1/5 |
| h4_trend_h1_pullback_continuation | balanced_pullback | unguarded | tp15_sl12_h6 | KILL_COST_STRESS_X4_NEGATIVE | -0.96253 | 701 | -685.88 | 0.779508 | -1.02 | -278.94 | 1/5 | 1/5 |
| compression_expansion_confirmed | range16_pct18_expansion | macro_blocked | tp24_sl15_h12_control | KILL_COST_STRESS_X4_NEGATIVE | -0.996895 | 428 | -576.17 | 0.798165 | -2.2 | -299.76 | 1/5 | 0/5 |
| compression_expansion_confirmed | range16_pct18_expansion | unguarded | tp24_sl15_h12_control | KILL_COST_STRESS_X4_NEGATIVE | -0.996895 | 428 | -576.17 | 0.798165 | -2.2 | -299.76 | 1/5 | 0/5 |
| h4_trend_h1_pullback_continuation | balanced_pullback | macro_blocked | tp15_sl10_h6 | KILL_COST_STRESS_X4_NEGATIVE | -1.24696 | 699 | -818.73 | 0.732633 | -1.54 | -330.51 | 1/5 | 1/5 |
| h4_trend_h1_pullback_continuation | balanced_pullback | unguarded | tp15_sl10_h6 | KILL_COST_STRESS_X4_NEGATIVE | -1.269895 | 701 | -833.02 | 0.72923 | -1.64 | -330.51 | 1/5 | 1/5 |
| baseline_sma_distance_v1_control | control_v1_long | macro_blocked | tp24_sl15_h12_control | KILL_COST_STRESS_X4_NEGATIVE | -1.418735 | 1105 | -891.61 | 0.901559 | -6.22 | -658.68 | 2/5 | 2/5 |
| baseline_sma_distance_v1_control | control_v1_long | unguarded | tp24_sl15_h12_control | KILL_COST_STRESS_X4_NEGATIVE | -1.497635 | 1108 | -940.81 | 0.896688 | -6.56 | -658.68 | 2/5 | 2/5 |
| compression_expansion_confirmed | range16_pct18_expansion | macro_blocked | tp12_sl8_h3 | KILL_COST_STRESS_X4_NEGATIVE | -1.51851 | 428 | -657.0 | 0.633571 | -3.005 | -325.29 | 0/5 | 0/5 |
| compression_expansion_confirmed | range16_pct18_expansion | unguarded | tp12_sl8_h3 | KILL_COST_STRESS_X4_NEGATIVE | -1.51851 | 428 | -657.0 | 0.633571 | -3.005 | -325.29 | 0/5 | 0/5 |
| compression_expansion_confirmed | range16_pct18_expansion | macro_blocked | tp10_sl8_h3 | KILL_COST_STRESS_X4_NEGATIVE | -1.527795 | 428 | -680.82 | 0.615312 | -2.74 | -310.31 | 0/5 | 0/5 |
| compression_expansion_confirmed | range16_pct18_expansion | unguarded | tp10_sl8_h3 | KILL_COST_STRESS_X4_NEGATIVE | -1.527795 | 428 | -680.82 | 0.615312 | -2.74 | -310.31 | 0/5 | 0/5 |
| compression_expansion_confirmed | range16_pct18_expansion | macro_blocked | tp18_sl15_h12 | KILL_COST_STRESS_X4_NEGATIVE | -1.57158 | 428 | -672.05 | 0.759741 | -2.025 | -355.42 | 0/5 | 0/5 |
| compression_expansion_confirmed | range16_pct18_expansion | unguarded | tp18_sl15_h12 | KILL_COST_STRESS_X4_NEGATIVE | -1.57158 | 428 | -672.05 | 0.759741 | -2.025 | -355.42 | 0/5 | 0/5 |
| compression_expansion_confirmed | range16_pct18_expansion | macro_blocked | tp18_sl12_h12 | KILL_COST_STRESS_X4_NEGATIVE | -1.67064 | 428 | -670.88 | 0.751149 | -3.69 | -405.98 | 0/5 | 0/5 |
| compression_expansion_confirmed | range16_pct18_expansion | unguarded | tp18_sl12_h12 | KILL_COST_STRESS_X4_NEGATIVE | -1.67064 | 428 | -670.88 | 0.751149 | -3.69 | -405.98 | 0/5 | 0/5 |
| h4_trend_h1_pullback_continuation | balanced_pullback | unguarded | tp12_sl10_h6 | KILL_COST_STRESS_X4_NEGATIVE | -1.778175 | 701 | -846.72 | 0.715111 | -1.17 | -327.03 | 0/5 | 0/5 |
| h4_trend_h1_pullback_continuation | balanced_pullback | macro_blocked | tp12_sl10_h6 | KILL_COST_STRESS_X4_NEGATIVE | -1.78974 | 699 | -854.43 | 0.712238 | -1.17 | -327.03 | 0/5 | 0/5 |
| compression_expansion_confirmed | range16_pct18_expansion | macro_blocked | tp12_sl10_h6 | KILL_COST_STRESS_X4_NEGATIVE | -1.923105 | 428 | -796.3 | 0.643398 | -3.455 | -451.22 | 0/5 | 0/5 |
| compression_expansion_confirmed | range16_pct18_expansion | unguarded | tp12_sl10_h6 | KILL_COST_STRESS_X4_NEGATIVE | -1.923105 | 428 | -796.3 | 0.643398 | -3.455 | -451.22 | 0/5 | 0/5 |
| compression_expansion_confirmed | range16_pct18_expansion | macro_blocked | tp15_sl12_h6 | KILL_COST_STRESS_X4_NEGATIVE | -1.94766 | 428 | -821.23 | 0.65904 | -3.195 | -445.26 | 0/5 | 0/5 |
| compression_expansion_confirmed | range16_pct18_expansion | unguarded | tp15_sl12_h6 | KILL_COST_STRESS_X4_NEGATIVE | -1.94766 | 428 | -821.23 | 0.65904 | -3.195 | -445.26 | 0/5 | 0/5 |
| baseline_sma_distance_v1_control | control_v1_long | macro_blocked | tp18_sl12_h12 | KILL_COST_STRESS_X4_NEGATIVE | -2.060025 | 1105 | -940.85 | 0.877445 | -8.21 | -450.4 | 0/5 | 1/5 |
| h4_trend_h1_pullback_continuation | balanced_pullback | macro_blocked | tp10_sl8_h3 | KILL_COST_STRESS_X4_NEGATIVE | -2.070045 | 699 | -987.49 | 0.588878 | -1.58 | -376.74 | 0/5 | 0/5 |
| h4_trend_h1_pullback_continuation | balanced_pullback | unguarded | tp10_sl8_h3 | KILL_COST_STRESS_X4_NEGATIVE | -2.07759 | 701 | -992.52 | 0.587648 | -1.58 | -376.74 | 0/5 | 0/5 |
| compression_expansion_confirmed | range16_pct18_expansion | macro_blocked | tp15_sl10_h6 | KILL_COST_STRESS_X4_NEGATIVE | -2.130495 | 428 | -888.62 | 0.622692 | -4.525 | -486.46 | 0/5 | 0/5 |
| compression_expansion_confirmed | range16_pct18_expansion | unguarded | tp15_sl10_h6 | KILL_COST_STRESS_X4_NEGATIVE | -2.130495 | 428 | -888.62 | 0.622692 | -4.525 | -486.46 | 0/5 | 0/5 |
| h4_trend_h1_pullback_continuation | balanced_pullback | macro_blocked | tp12_sl8_h3 | KILL_COST_STRESS_X4_NEGATIVE | -2.17203 | 699 | -1029.28 | 0.585578 | -1.81 | -400.64 | 0/5 | 0/5 |
| baseline_sma_distance_v1_control | control_v1_long | macro_blocked | tp18_sl15_h12 | KILL_COST_STRESS_X4_NEGATIVE | -2.18376 | 1105 | -1049.99 | 0.874077 | -3.25 | -573.35 | 0/5 | 2/5 |
| h4_trend_h1_pullback_continuation | balanced_pullback | unguarded | tp12_sl8_h3 | KILL_COST_STRESS_X4_NEGATIVE | -2.18397 | 701 | -1034.31 | 0.584394 | -1.81 | -403.57 | 0/5 | 0/5 |
| baseline_sma_distance_v1_control | control_v1_long | unguarded | tp18_sl12_h12 | KILL_COST_STRESS_X4_NEGATIVE | -2.19135 | 1108 | -981.05 | 0.872874 | -9.24 | -487.45 | 0/5 | 1/5 |
| baseline_sma_distance_v1_control | control_v1_long | unguarded | tp18_sl15_h12 | KILL_COST_STRESS_X4_NEGATIVE | -2.276535 | 1108 | -1099.19 | 0.868949 | -3.285 | -585.65 | 0/5 | 2/5 |
| baseline_sma_distance_v1_control | control_v1_long | macro_blocked | tp12_sl10_h6 | KILL_COST_STRESS_X4_NEGATIVE | -2.40978 | 1105 | -1223.92 | 0.796574 | -3.29 | -349.7 | 0/5 | 0/5 |
| baseline_sma_distance_v1_control | control_v1_long | unguarded | tp12_sl10_h6 | KILL_COST_STRESS_X4_NEGATIVE | -2.42823 | 1108 | -1236.12 | 0.795322 | -3.3 | -349.7 | 0/5 | 0/5 |
| baseline_sma_distance_v1_control | control_v1_long | macro_blocked | tp12_sl8_h3 | KILL_COST_STRESS_X4_NEGATIVE | -2.57256 | 1105 | -1351.22 | 0.745668 | -4.67 | -317.12 | 0/5 | 0/5 |
| baseline_sma_distance_v1_control | control_v1_long | macro_blocked | tp10_sl8_h3 | KILL_COST_STRESS_X4_NEGATIVE | -2.597205 | 1105 | -1385.56 | 0.724273 | -3.24 | -313.51 | 0/5 | 0/5 |
| baseline_sma_distance_v1_control | control_v1_long | unguarded | tp12_sl8_h3 | KILL_COST_STRESS_X4_NEGATIVE | -2.61546 | 1108 | -1379.42 | 0.74173 | -4.71 | -317.12 | 0/5 | 0/5 |
| baseline_sma_distance_v1_control | control_v1_long | unguarded | tp10_sl8_h3 | KILL_COST_STRESS_X4_NEGATIVE | -2.639805 | 1108 | -1413.76 | 0.720231 | -3.26 | -313.51 | 0/5 | 0/5 |
| baseline_sma_distance_v1_control | control_v1_long | macro_blocked | tp15_sl12_h6 | KILL_COST_STRESS_X4_NEGATIVE | -2.75787 | 1105 | -1367.14 | 0.802984 | -3.52 | -536.24 | 0/5 | 1/5 |
| baseline_sma_distance_v1_control | control_v1_long | unguarded | tp15_sl12_h6 | KILL_COST_STRESS_X4_NEGATIVE | -2.76216 | 1108 | -1370.1 | 0.803028 | -3.51 | -536.24 | 0/5 | 1/5 |
| baseline_sma_distance_v1_control | control_v1_long | macro_blocked | tp15_sl10_h6 | KILL_COST_STRESS_X4_NEGATIVE | -2.901765 | 1105 | -1410.85 | 0.783943 | -6.22 | -461.46 | 0/5 | 0/5 |
| baseline_sma_distance_v1_control | control_v1_long | unguarded | tp15_sl10_h6 | KILL_COST_STRESS_X4_NEGATIVE | -2.97552 | 1108 | -1436.81 | 0.780839 | -6.26 | -484.27 | 0/5 | 0/5 |

## Interpretation
- This is a constrained exit-geometry test, not parameter optimization.
- If no geometry reaches WATCHLIST/PROMISING, entries are not commercially sufficient in this mechanical form.
- If one geometry improves x4 cost performance and robustness, it becomes a Stage 7E validation candidate only.

## Decision
- Do not modify EA from Stage 7D alone.
- Do not use session/side filters to rescue weak geometries.
- Candidate must pass Stage 7E robustness before any locked strategy proposal.
