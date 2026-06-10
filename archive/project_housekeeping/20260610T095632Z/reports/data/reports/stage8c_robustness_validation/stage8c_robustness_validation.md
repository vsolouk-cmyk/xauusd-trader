# Stage 8C Robustness Validation

Generated UTC: `2026-06-09T13:48:13+00:00`
Tool version: `v1`

> Hard rule: research only. This does not authorize demo, paper, or live orders.

## Inputs
- db: `data/local/xauusd_local_store.sqlite`
- trades_csv: `data/reports/stage8b_single_regime_thesis_lab/stage8b_single_regime_trades.csv`
- summaries_csv: `data/reports/stage8b_single_regime_thesis_lab/stage8b_single_regime_summaries.csv`
- m1_rows: `1449867`
- stage8b_trades_loaded: `64474`
- selected_candidate_keys: `[['liquidity_session', 'unguarded_nonoverlap', 'time_exit_12h'], ['liquidity_session', 'macro_blocked_nonoverlap', 'time_exit_12h'], ['base_h4up_compression_mid_high', 'unguarded_nonoverlap', 'time_exit_12h'], ['base_h4up_compression_mid_high', 'macro_blocked_nonoverlap', 'time_exit_12h'], ['liquidity_session', 'unguarded_nonoverlap', 'tp24_sl15_h12_control'], ['liquidity_session', 'macro_blocked_nonoverlap', 'tp24_sl15_h12_control'], ['confirmed_h1', 'unguarded_nonoverlap', 'time_exit_12h'], ['confirmed_h1', 'macro_blocked_nonoverlap', 'time_exit_12h'], ['confirmed_session', 'unguarded_nonoverlap', 'time_exit_12h'], ['confirmed_session', 'macro_blocked_nonoverlap', 'time_exit_12h'], ['base_h4up_compression_mid_high', 'unguarded_nonoverlap', 'tp24_sl15_h12_control'], ['base_h4up_compression_mid_high', 'macro_blocked_nonoverlap', 'tp24_sl15_h12_control'], ['liquidity_session', 'unguarded_nonoverlap', 'tp18_sl12_h12'], ['liquidity_session', 'macro_blocked_nonoverlap', 'tp18_sl12_h12'], ['confirmed_session', 'unguarded_nonoverlap', 'tp24_sl15_h12_control'], ['confirmed_session', 'macro_blocked_nonoverlap', 'tp24_sl15_h12_control'], ['confirmed_h1', 'unguarded_nonoverlap', 'tp24_sl15_h12_control'], ['confirmed_h1', 'macro_blocked_nonoverlap', 'tp24_sl15_h12_control'], ['base_h4up_compression_mid_high', 'unguarded_nonoverlap', 'tp18_sl12_h12'], ['base_h4up_compression_mid_high', 'macro_blocked_nonoverlap', 'tp18_sl12_h12'], ['liquidity_session', 'unguarded_nonoverlap', 'tp15_sl12_h12'], ['liquidity_session', 'macro_blocked_nonoverlap', 'tp15_sl12_h12']]`
- emergency_stops: `['none', 20.0, 25.0, 30.0]`

## Ranking
| Definition | Guard | Geometry | Emergency SL | Decision | Score | Trades | Total x4 | Total x6 | PF x4 | Median x4 | DD x1 | Pos years | Pos quarters | Worst month |
|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| liquidity_session | unguarded_nonoverlap | time_exit_12h | none | PASS_STAGE8C_RESEARCH_ONLY | 13.04209 | 262 | 1205.14 | 1021.74 | 1.920727 | 2.06 | -193.22 | 4/5 | 13/17 | -76.33 |
| liquidity_session | macro_blocked_nonoverlap | time_exit_12h | none | PASS_STAGE8C_RESEARCH_ONLY | 13.04209 | 262 | 1205.14 | 1021.74 | 1.920727 | 2.06 | -193.22 | 4/5 | 13/17 | -76.33 |
| liquidity_session | unguarded_nonoverlap | time_exit_12h | 30 | PASS_STAGE8C_RESEARCH_ONLY | 12.42386 | 262 | 1090.16 | 906.76 | 1.862694 | 1.96 | -155.76 | 4/5 | 13/17 | -58.98 |
| liquidity_session | macro_blocked_nonoverlap | time_exit_12h | 30 | PASS_STAGE8C_RESEARCH_ONLY | 12.42386 | 262 | 1090.16 | 906.76 | 1.862694 | 1.96 | -155.76 | 4/5 | 13/17 | -58.98 |
| liquidity_session | unguarded_nonoverlap | time_exit_12h | 25 | PASS_STAGE8C_RESEARCH_ONLY | 9.46774 | 262 | 801.32 | 617.92 | 1.623736 | 1.59 | -152.66 | 4/5 | 13/17 | -72.98 |
| liquidity_session | macro_blocked_nonoverlap | time_exit_12h | 25 | PASS_STAGE8C_RESEARCH_ONLY | 9.46774 | 262 | 801.32 | 617.92 | 1.623736 | 1.59 | -152.66 | 4/5 | 13/17 | -72.98 |
| liquidity_session | unguarded_nonoverlap | tp24_sl15_h12_control | none | PASS_STAGE8C_RESEARCH_ONLY | 8.95845 | 331 | 857.05 | 625.35 | 1.555829 | 1.75 | -156.65 | 4/5 | 12/17 | -45.97 |
| liquidity_session | macro_blocked_nonoverlap | tp24_sl15_h12_control | none | PASS_STAGE8C_RESEARCH_ONLY | 8.95845 | 331 | 857.05 | 625.35 | 1.555829 | 1.75 | -156.65 | 4/5 | 12/17 | -45.97 |
| liquidity_session | unguarded_nonoverlap | tp24_sl15_h12_control | 30 | PASS_STAGE8C_RESEARCH_ONLY | 8.79356 | 331 | 842.05 | 610.35 | 1.54084 | 1.75 | -156.65 | 4/5 | 12/17 | -45.97 |
| liquidity_session | macro_blocked_nonoverlap | tp24_sl15_h12_control | 30 | PASS_STAGE8C_RESEARCH_ONLY | 8.79356 | 331 | 842.05 | 610.35 | 1.54084 | 1.75 | -156.65 | 4/5 | 12/17 | -45.97 |
| liquidity_session | unguarded_nonoverlap | tp24_sl15_h12_control | 25 | PASS_STAGE8C_RESEARCH_ONLY | 8.52505 | 331 | 817.05 | 585.35 | 1.516489 | 1.75 | -156.65 | 4/5 | 12/17 | -45.97 |
| liquidity_session | macro_blocked_nonoverlap | tp24_sl15_h12_control | 25 | PASS_STAGE8C_RESEARCH_ONLY | 8.52505 | 331 | 817.05 | 585.35 | 1.516489 | 1.75 | -156.65 | 4/5 | 12/17 | -45.97 |
| liquidity_session | unguarded_nonoverlap | tp24_sl15_h12_control | 20 | PASS_STAGE8C_RESEARCH_ONLY | 8.50599 | 331 | 817.05 | 585.35 | 1.516489 | 1.75 | -161.65 | 4/5 | 12/17 | -48.0 |
| liquidity_session | macro_blocked_nonoverlap | tp24_sl15_h12_control | 20 | PASS_STAGE8C_RESEARCH_ONLY | 8.50599 | 331 | 817.05 | 585.35 | 1.516489 | 1.75 | -161.65 | 4/5 | 12/17 | -48.0 |
| liquidity_session | unguarded_nonoverlap | time_exit_12h | 20 | PASS_STAGE8C_RESEARCH_ONLY | 8.21243 | 262 | 700.92 | 517.52 | 1.54523 | 1.165 | -168.43 | 4/5 | 12/17 | -65.5 |
| liquidity_session | macro_blocked_nonoverlap | time_exit_12h | 20 | PASS_STAGE8C_RESEARCH_ONLY | 8.21243 | 262 | 700.92 | 517.52 | 1.54523 | 1.165 | -168.43 | 4/5 | 12/17 | -65.5 |
| confirmed_session | unguarded_nonoverlap | time_exit_12h | none | PASS_STAGE8C_RESEARCH_ONLY | 7.92275 | 221 | 673.66 | 518.96 | 1.539312 | 1.04 | -189.29 | 4/5 | 12/17 | -92.08 |
| confirmed_session | macro_blocked_nonoverlap | time_exit_12h | none | PASS_STAGE8C_RESEARCH_ONLY | 7.92275 | 221 | 673.66 | 518.96 | 1.539312 | 1.04 | -189.29 | 4/5 | 12/17 | -92.08 |
| confirmed_h1 | unguarded_nonoverlap | time_exit_12h | 30 | WATCHLIST_STAGE8C_RESEARCH_ONLY | 8.81385 | 407 | 1425.82 | 1140.92 | 1.602468 | 0.55 | -237.75 | 4/5 | 12/17 | -94.2 |
| confirmed_h1 | macro_blocked_nonoverlap | time_exit_12h | 30 | WATCHLIST_STAGE8C_RESEARCH_ONLY | 8.81385 | 407 | 1425.82 | 1140.92 | 1.602468 | 0.55 | -237.75 | 4/5 | 12/17 | -94.2 |
| base_h4up_compression_mid_high | unguarded_nonoverlap | time_exit_12h | 20 | WATCHLIST_STAGE8C_RESEARCH_ONLY | 8.64485 | 483 | 1504.49 | 1166.39 | 1.54245 | 1.09 | -227.4 | 4/5 | 11/17 | -102.47 |
| base_h4up_compression_mid_high | macro_blocked_nonoverlap | time_exit_12h | 20 | WATCHLIST_STAGE8C_RESEARCH_ONLY | 8.64485 | 483 | 1504.49 | 1166.39 | 1.54245 | 1.09 | -227.4 | 4/5 | 11/17 | -102.47 |
| confirmed_session | unguarded_nonoverlap | time_exit_12h | 30 | WATCHLIST_STAGE8C_RESEARCH_ONLY | 7.57573 | 221 | 627.2 | 472.5 | 1.535377 | 0.55 | -173.6 | 4/5 | 12/17 | -74.72 |
| confirmed_session | macro_blocked_nonoverlap | time_exit_12h | 30 | WATCHLIST_STAGE8C_RESEARCH_ONLY | 7.57573 | 221 | 627.2 | 472.5 | 1.535377 | 0.55 | -173.6 | 4/5 | 12/17 | -74.72 |
| confirmed_h1 | unguarded_nonoverlap | time_exit_12h | 25 | WATCHLIST_STAGE8C_RESEARCH_ONLY | 6.79677 | 407 | 1083.02 | 798.12 | 1.44583 | 0.22 | -202.75 | 4/5 | 12/17 | -85.15 |
| confirmed_h1 | macro_blocked_nonoverlap | time_exit_12h | 25 | WATCHLIST_STAGE8C_RESEARCH_ONLY | 6.79677 | 407 | 1083.02 | 798.12 | 1.44583 | 0.22 | -202.75 | 4/5 | 12/17 | -85.15 |
| confirmed_h1 | unguarded_nonoverlap | time_exit_12h | 20 | WATCHLIST_STAGE8C_RESEARCH_ONLY | 6.58771 | 407 | 1048.57 | 763.67 | 1.433749 | 0.08 | -183.15 | 4/5 | 11/17 | -72.45 |
| confirmed_h1 | macro_blocked_nonoverlap | time_exit_12h | 20 | WATCHLIST_STAGE8C_RESEARCH_ONLY | 6.58771 | 407 | 1048.57 | 763.67 | 1.433749 | 0.08 | -183.15 | 4/5 | 11/17 | -72.45 |
| confirmed_session | unguarded_nonoverlap | tp24_sl15_h12_control | none | WATCHLIST_STAGE8C_RESEARCH_ONLY | 5.76795 | 264 | 462.28 | 277.48 | 1.355603 | 0.57 | -130.32 | 4/5 | 11/17 | -49.2 |
| confirmed_session | macro_blocked_nonoverlap | tp24_sl15_h12_control | none | WATCHLIST_STAGE8C_RESEARCH_ONLY | 5.76795 | 264 | 462.28 | 277.48 | 1.355603 | 0.57 | -130.32 | 4/5 | 11/17 | -49.2 |
| confirmed_session | unguarded_nonoverlap | tp24_sl15_h12_control | 30 | WATCHLIST_STAGE8C_RESEARCH_ONLY | 5.59831 | 264 | 447.28 | 262.48 | 1.340139 | 0.57 | -130.32 | 4/5 | 11/17 | -49.2 |
| confirmed_session | macro_blocked_nonoverlap | tp24_sl15_h12_control | 30 | WATCHLIST_STAGE8C_RESEARCH_ONLY | 5.59831 | 264 | 447.28 | 262.48 | 1.340139 | 0.57 | -130.32 | 4/5 | 11/17 | -49.2 |
| confirmed_session | unguarded_nonoverlap | tp24_sl15_h12_control | 20 | WATCHLIST_STAGE8C_RESEARCH_ONLY | 5.48717 | 264 | 437.28 | 252.48 | 1.330025 | 0.57 | -130.32 | 4/5 | 11/17 | -49.2 |
| confirmed_session | macro_blocked_nonoverlap | tp24_sl15_h12_control | 20 | WATCHLIST_STAGE8C_RESEARCH_ONLY | 5.48717 | 264 | 437.28 | 252.48 | 1.330025 | 0.57 | -130.32 | 4/5 | 11/17 | -49.2 |
| confirmed_session | unguarded_nonoverlap | tp24_sl15_h12_control | 25 | WATCHLIST_STAGE8C_RESEARCH_ONLY | 5.43217 | 264 | 432.28 | 247.48 | 1.325025 | 0.57 | -130.32 | 4/5 | 11/17 | -49.2 |
| confirmed_session | macro_blocked_nonoverlap | tp24_sl15_h12_control | 25 | WATCHLIST_STAGE8C_RESEARCH_ONLY | 5.43217 | 264 | 432.28 | 247.48 | 1.325025 | 0.57 | -130.32 | 4/5 | 11/17 | -49.2 |
| base_h4up_compression_mid_high | unguarded_nonoverlap | time_exit_12h | 30 | KILL_DRAWDOWN_TOO_HIGH | 9.78185 | 483 | 1805.02 | 1466.92 | 1.642614 | 1.39 | -329.99 | 4/5 | 11/17 | -136.17 |
| base_h4up_compression_mid_high | macro_blocked_nonoverlap | time_exit_12h | 30 | KILL_DRAWDOWN_TOO_HIGH | 9.78185 | 483 | 1805.02 | 1466.92 | 1.642614 | 1.39 | -329.99 | 4/5 | 11/17 | -136.17 |
| base_h4up_compression_mid_high | unguarded_nonoverlap | time_exit_12h | 25 | KILL_DRAWDOWN_TOO_HIGH | 8.76845 | 483 | 1552.18 | 1214.08 | 1.555558 | 1.28 | -274.99 | 4/5 | 11/17 | -125.17 |
| base_h4up_compression_mid_high | macro_blocked_nonoverlap | time_exit_12h | 25 | KILL_DRAWDOWN_TOO_HIGH | 8.76845 | 483 | 1552.18 | 1214.08 | 1.555558 | 1.28 | -274.99 | 4/5 | 11/17 | -125.17 |
| base_h4up_compression_mid_high | unguarded_nonoverlap | time_exit_12h | none | KILL_DRAWDOWN_TOO_HIGH | 8.64918 | 483 | 1638.98 | 1300.88 | 1.531684 | 1.98 | -398.52 | 4/5 | 11/17 | -168.54 |
| base_h4up_compression_mid_high | macro_blocked_nonoverlap | time_exit_12h | none | KILL_DRAWDOWN_TOO_HIGH | 8.64918 | 483 | 1638.98 | 1300.88 | 1.531684 | 1.98 | -398.52 | 4/5 | 11/17 | -168.54 |
| confirmed_h1 | unguarded_nonoverlap | time_exit_12h | none | KILL_DRAWDOWN_TOO_HIGH | 7.38813 | 407 | 1272.44 | 987.54 | 1.496231 | 1.09 | -401.82 | 4/5 | 10/17 | -102.08 |
| confirmed_h1 | macro_blocked_nonoverlap | time_exit_12h | none | KILL_DRAWDOWN_TOO_HIGH | 7.38813 | 407 | 1272.44 | 987.54 | 1.496231 | 1.09 | -401.82 | 4/5 | 10/17 | -102.08 |
| liquidity_session | unguarded_nonoverlap | tp18_sl12_h12 | none | KILL_YEAR_FRAGILE | 6.20454 | 370 | 635.19 | 376.19 | 1.374954 | 1.165 | -125.85 | 3/5 | 11/17 | -54.07 |
| liquidity_session | macro_blocked_nonoverlap | tp18_sl12_h12 | none | KILL_YEAR_FRAGILE | 6.20454 | 370 | 635.19 | 376.19 | 1.374954 | 1.165 | -125.85 | 3/5 | 11/17 | -54.07 |
| liquidity_session | unguarded_nonoverlap | tp18_sl12_h12 | 30 | KILL_YEAR_FRAGILE | 5.98798 | 370 | 617.19 | 358.19 | 1.360498 | 1.165 | -143.85 | 3/5 | 11/17 | -54.07 |
| liquidity_session | macro_blocked_nonoverlap | tp18_sl12_h12 | 30 | KILL_YEAR_FRAGILE | 5.98798 | 370 | 617.19 | 358.19 | 1.360498 | 1.165 | -143.85 | 3/5 | 11/17 | -54.07 |
| liquidity_session | unguarded_nonoverlap | tp18_sl12_h12 | 25 | KILL_YEAR_FRAGILE | 5.90623 | 370 | 609.19 | 350.19 | 1.35417 | 1.165 | -147.34 | 3/5 | 11/17 | -54.07 |
| liquidity_session | macro_blocked_nonoverlap | tp18_sl12_h12 | 25 | KILL_YEAR_FRAGILE | 5.90623 | 370 | 609.19 | 350.19 | 1.35417 | 1.165 | -147.34 | 3/5 | 11/17 | -54.07 |
| base_h4up_compression_mid_high | unguarded_nonoverlap | tp24_sl15_h12_control | none | KILL_DRAWDOWN_TOO_HIGH | 5.90154 | 623 | 1166.67 | 730.57 | 1.334062 | 0.77 | -258.25 | 4/5 | 12/17 | -125.0 |
| base_h4up_compression_mid_high | macro_blocked_nonoverlap | tp24_sl15_h12_control | none | KILL_DRAWDOWN_TOO_HIGH | 5.90154 | 623 | 1166.67 | 730.57 | 1.334062 | 0.77 | -258.25 | 4/5 | 12/17 | -125.0 |
| liquidity_session | unguarded_nonoverlap | tp18_sl12_h12 | 20 | KILL_YEAR_FRAGILE | 5.7249 | 370 | 595.19 | 336.19 | 1.343237 | 1.165 | -161.34 | 3/5 | 11/17 | -62.07 |
| liquidity_session | macro_blocked_nonoverlap | tp18_sl12_h12 | 20 | KILL_YEAR_FRAGILE | 5.7249 | 370 | 595.19 | 336.19 | 1.343237 | 1.165 | -161.34 | 3/5 | 11/17 | -62.07 |
| base_h4up_compression_mid_high | unguarded_nonoverlap | tp24_sl15_h12_control | 30 | KILL_DRAWDOWN_TOO_HIGH | 5.47948 | 623 | 1151.67 | 715.57 | 1.328356 | 0.77 | -258.25 | 3/5 | 12/17 | -125.0 |
| base_h4up_compression_mid_high | macro_blocked_nonoverlap | tp24_sl15_h12_control | 30 | KILL_DRAWDOWN_TOO_HIGH | 5.47948 | 623 | 1151.67 | 715.57 | 1.328356 | 0.77 | -258.25 | 3/5 | 12/17 | -125.0 |
| base_h4up_compression_mid_high | unguarded_nonoverlap | tp24_sl15_h12_control | 25 | KILL_DRAWDOWN_TOO_HIGH | 5.32791 | 623 | 1136.67 | 700.57 | 1.322699 | 0.77 | -278.25 | 3/5 | 12/17 | -135.0 |
| base_h4up_compression_mid_high | macro_blocked_nonoverlap | tp24_sl15_h12_control | 25 | KILL_DRAWDOWN_TOO_HIGH | 5.32791 | 623 | 1136.67 | 700.57 | 1.322699 | 0.77 | -278.25 | 3/5 | 12/17 | -135.0 |
| base_h4up_compression_mid_high | unguarded_nonoverlap | tp24_sl15_h12_control | 20 | KILL_DRAWDOWN_TOO_HIGH | 5.18621 | 623 | 1106.67 | 670.57 | 1.311529 | 0.77 | -278.25 | 3/5 | 12/17 | -135.0 |
| base_h4up_compression_mid_high | macro_blocked_nonoverlap | tp24_sl15_h12_control | 20 | KILL_DRAWDOWN_TOO_HIGH | 5.18621 | 623 | 1106.67 | 670.57 | 1.311529 | 0.77 | -278.25 | 3/5 | 12/17 | -135.0 |
| liquidity_session | unguarded_nonoverlap | tp15_sl12_h12 | none | KILL_YEAR_FRAGILE | 4.66599 | 384 | 413.48 | 144.68 | 1.238165 | 1.465 | -175.9 | 3/5 | 11/17 | -58.47 |
| liquidity_session | macro_blocked_nonoverlap | tp15_sl12_h12 | none | KILL_YEAR_FRAGILE | 4.66599 | 384 | 413.48 | 144.68 | 1.238165 | 1.465 | -175.9 | 3/5 | 11/17 | -58.47 |
| liquidity_session | unguarded_nonoverlap | tp15_sl12_h12 | 30 | KILL_YEAR_FRAGILE | 4.46693 | 384 | 395.48 | 126.68 | 1.225459 | 1.465 | -193.9 | 3/5 | 11/17 | -58.47 |
| liquidity_session | macro_blocked_nonoverlap | tp15_sl12_h12 | 30 | KILL_YEAR_FRAGILE | 4.46693 | 384 | 395.48 | 126.68 | 1.225459 | 1.465 | -193.9 | 3/5 | 11/17 | -58.47 |
| liquidity_session | unguarded_nonoverlap | tp15_sl12_h12 | 25 | KILL_YEAR_FRAGILE | 4.37929 | 384 | 387.48 | 118.68 | 1.219895 | 1.465 | -201.9 | 3/5 | 11/17 | -58.47 |
| liquidity_session | macro_blocked_nonoverlap | tp15_sl12_h12 | 25 | KILL_YEAR_FRAGILE | 4.37929 | 384 | 387.48 | 118.68 | 1.219895 | 1.465 | -201.9 | 3/5 | 11/17 | -58.47 |
| liquidity_session | unguarded_nonoverlap | tp15_sl12_h12 | 20 | KILL_YEAR_FRAGILE | 4.2979 | 384 | 381.48 | 112.68 | 1.215756 | 1.465 | -207.9 | 3/5 | 11/17 | -66.47 |
| liquidity_session | macro_blocked_nonoverlap | tp15_sl12_h12 | 20 | KILL_YEAR_FRAGILE | 4.2979 | 384 | 381.48 | 112.68 | 1.215756 | 1.465 | -207.9 | 3/5 | 11/17 | -66.47 |
| confirmed_session | unguarded_nonoverlap | time_exit_12h | 25 | KILL_YEAR_FRAGILE | 3.94194 | 221 | 323.36 | 168.66 | 1.267782 | 0.13 | -167.6 | 3/5 | 12/17 | -88.72 |
| confirmed_session | macro_blocked_nonoverlap | time_exit_12h | 25 | KILL_YEAR_FRAGILE | 3.94194 | 221 | 323.36 | 168.66 | 1.267782 | 0.13 | -167.6 | 3/5 | 12/17 | -88.72 |
| confirmed_h1 | unguarded_nonoverlap | tp24_sl15_h12_control | none | KILL_NONPOSITIVE_MEDIAN_X4 | 3.45991 | 491 | 591.09 | 247.39 | 1.208857 | -0.16 | -168.85 | 3/5 | 12/17 | -65.6 |
| confirmed_h1 | macro_blocked_nonoverlap | tp24_sl15_h12_control | none | KILL_NONPOSITIVE_MEDIAN_X4 | 3.45991 | 491 | 591.09 | 247.39 | 1.208857 | -0.16 | -168.85 | 3/5 | 12/17 | -65.6 |
| confirmed_h1 | unguarded_nonoverlap | tp24_sl15_h12_control | 30 | KILL_NONPOSITIVE_MEDIAN_X4 | 3.38118 | 491 | 576.09 | 232.39 | 1.202484 | -0.16 | -168.85 | 3/5 | 12/17 | -65.6 |
| confirmed_h1 | macro_blocked_nonoverlap | tp24_sl15_h12_control | 30 | KILL_NONPOSITIVE_MEDIAN_X4 | 3.38118 | 491 | 576.09 | 232.39 | 1.202484 | -0.16 | -168.85 | 3/5 | 12/17 | -65.6 |
| confirmed_h1 | unguarded_nonoverlap | tp24_sl15_h12_control | 25 | KILL_NONPOSITIVE_MEDIAN_X4 | 3.31748 | 491 | 571.09 | 227.39 | 1.200374 | -0.16 | -178.85 | 3/5 | 12/17 | -69.4 |
| confirmed_h1 | macro_blocked_nonoverlap | tp24_sl15_h12_control | 25 | KILL_NONPOSITIVE_MEDIAN_X4 | 3.31748 | 491 | 571.09 | 227.39 | 1.200374 | -0.16 | -178.85 | 3/5 | 12/17 | -69.4 |
| confirmed_h1 | unguarded_nonoverlap | tp24_sl15_h12_control | 20 | KILL_LOW_PF_X4 | 3.21143 | 491 | 551.09 | 207.39 | 1.192009 | -0.16 | -178.85 | 3/5 | 12/17 | -70.6 |
| confirmed_h1 | macro_blocked_nonoverlap | tp24_sl15_h12_control | 20 | KILL_LOW_PF_X4 | 3.21143 | 491 | 551.09 | 207.39 | 1.192009 | -0.16 | -178.85 | 3/5 | 12/17 | -70.6 |
| base_h4up_compression_mid_high | unguarded_nonoverlap | tp18_sl12_h12 | none | KILL_LOW_PF_X4 | 2.91748 | 716 | 709.84 | 208.64 | 1.184629 | -0.175 | -259.25 | 3/5 | 11/17 | -114.2 |
| base_h4up_compression_mid_high | macro_blocked_nonoverlap | tp18_sl12_h12 | none | KILL_LOW_PF_X4 | 2.91748 | 716 | 709.84 | 208.64 | 1.184629 | -0.175 | -259.25 | 3/5 | 11/17 | -114.2 |
| base_h4up_compression_mid_high | unguarded_nonoverlap | tp18_sl12_h12 | 30 | KILL_LOW_PF_X4 | 2.83017 | 716 | 691.84 | 190.64 | 1.179108 | -0.175 | -263.95 | 3/5 | 11/17 | -114.2 |
| base_h4up_compression_mid_high | macro_blocked_nonoverlap | tp18_sl12_h12 | 30 | KILL_LOW_PF_X4 | 2.83017 | 716 | 691.84 | 190.64 | 1.179108 | -0.175 | -263.95 | 3/5 | 11/17 | -114.2 |
| base_h4up_compression_mid_high | unguarded_nonoverlap | tp18_sl12_h12 | 25 | KILL_LOW_PF_X4 | 2.7729 | 716 | 683.84 | 182.64 | 1.176671 | -0.175 | -272.25 | 3/5 | 11/17 | -114.2 |
| base_h4up_compression_mid_high | macro_blocked_nonoverlap | tp18_sl12_h12 | 25 | KILL_LOW_PF_X4 | 2.7729 | 716 | 683.84 | 182.64 | 1.176671 | -0.175 | -272.25 | 3/5 | 11/17 | -114.2 |
| base_h4up_compression_mid_high | unguarded_nonoverlap | tp18_sl12_h12 | 20 | KILL_LOW_PF_X4 | 2.61131 | 716 | 653.84 | 152.64 | 1.167622 | -0.175 | -285.95 | 3/5 | 11/17 | -114.2 |
| base_h4up_compression_mid_high | macro_blocked_nonoverlap | tp18_sl12_h12 | 20 | KILL_LOW_PF_X4 | 2.61131 | 716 | 653.84 | 152.64 | 1.167622 | -0.175 | -285.95 | 3/5 | 11/17 | -114.2 |
| confirmed_session | unguarded_nonoverlap | time_exit_12h | 20 | KILL_LOW_PF_X4 | 2.34709 | 221 | 195.11 | 40.41 | 1.157825 | -0.27 | -174.93 | 3/5 | 10/17 | -81.24 |
| confirmed_session | macro_blocked_nonoverlap | time_exit_12h | 20 | KILL_LOW_PF_X4 | 2.34709 | 221 | 195.11 | 40.41 | 1.157825 | -0.27 | -174.93 | 3/5 | 10/17 | -81.24 |

## Interpretation
- `PASS_STAGE8C_RESEARCH_ONLY`: candidate can move to Stage 8D forward-shadow design, not orders.
- `WATCHLIST_STAGE8C_RESEARCH_ONLY`: promising but needs one focused risk-design revision.
- `KILL_*`: do not rescue by filter mining.
- `emergency_stop_usd=none` for `time_exit_12h` is diagnostic only, not a deployable risk model.

## Decision
- No EA change is allowed from Stage 8C alone.
- Any future locked strategy must use non-overlap execution basis.
- If the best candidate only passes without an emergency stop, Stage 8D must design an operational risk guard before EA changes.
