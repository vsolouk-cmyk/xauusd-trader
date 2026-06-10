# Stage 8B Single Regime Thesis Lab

Generated UTC: `2026-06-09T13:38:53+00:00`
Tool version: `v1`

> Hard rule: research only. This does not authorize demo, paper, or live orders.

## Thesis
- thesis_id: `h4_up_compression_long_continuation_v1`
- Rationale: Stage 8A showed favorable long forward distribution in H4 uptrend, mid/high compression, London-NY/New York, and 12h horizon.
- Explicitly not used as rule: `year=2025`.

## Inputs
- db: `data/local/xauusd_local_store.sqlite`
- h1_rows: `24225`
- m1_rows: `1449867`
- macro_windows: `5`
- trades_simulated: `64474`

## Ranking
| Definition | Guard | Geometry | Decision | Score | Signals | Trades | Total x4 | PF x4 | Median x4 | DD x1 | Pos years | Pos sessions |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| liquidity_session | unguarded_overlap | time_exit_12h | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 17.904255 | 1024 | 1017 | 4531.81 | 2.017678 | 0.95 | -394.62 | 4/5 | 2/2 |
| liquidity_session | macro_blocked_overlap | time_exit_12h | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 17.904255 | 1024 | 1017 | 4531.81 | 2.017678 | 0.95 | -394.62 | 4/5 | 2/2 |
| confirmed_session | unguarded_overlap | time_exit_12h | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 14.709275 | 730 | 725 | 3141.55 | 1.899639 | 0.48 | -354.52 | 4/5 | 2/2 |
| confirmed_session | macro_blocked_overlap | time_exit_12h | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 14.709275 | 730 | 725 | 3141.55 | 1.899639 | 0.48 | -354.52 | 4/5 | 2/2 |
| liquidity_session | unguarded_nonoverlap | time_exit_12h | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 12.36974 | 1024 | 262 | 1205.14 | 1.920727 | 2.06 | -193.22 | 4/5 | 2/2 |
| liquidity_session | macro_blocked_nonoverlap | time_exit_12h | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 12.36974 | 1024 | 262 | 1205.14 | 1.920727 | 2.06 | -193.22 | 4/5 | 2/2 |
| liquidity_session | unguarded_overlap | tp24_sl15_h12_control | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 9.298715 | 1024 | 1017 | 2030.77 | 1.515002 | 0.77 | -306.43 | 4/5 | 2/2 |
| liquidity_session | macro_blocked_overlap | tp24_sl15_h12_control | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 9.298715 | 1024 | 1017 | 2030.77 | 1.515002 | 0.77 | -306.43 | 4/5 | 2/2 |
| base_h4up_compression_mid_high | unguarded_nonoverlap | time_exit_12h | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 9.16787 | 2658 | 483 | 1638.98 | 1.531684 | 1.98 | -398.52 | 4/5 | 5/5 |
| base_h4up_compression_mid_high | macro_blocked_nonoverlap | time_exit_12h | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 9.16787 | 2658 | 483 | 1638.98 | 1.531684 | 1.98 | -398.52 | 4/5 | 5/5 |
| liquidity_session | unguarded_nonoverlap | tp24_sl15_h12_control | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 8.265565 | 1024 | 331 | 857.05 | 1.555829 | 1.75 | -156.65 | 4/5 | 2/2 |
| liquidity_session | macro_blocked_nonoverlap | tp24_sl15_h12_control | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 8.265565 | 1024 | 331 | 857.05 | 1.555829 | 1.75 | -156.65 | 4/5 | 2/2 |
| confirmed_h1 | unguarded_nonoverlap | time_exit_12h | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 8.23913 | 1947 | 407 | 1272.44 | 1.496231 | 1.09 | -401.82 | 4/5 | 5/5 |
| confirmed_h1 | macro_blocked_nonoverlap | time_exit_12h | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 8.23913 | 1947 | 407 | 1272.44 | 1.496231 | 1.09 | -401.82 | 4/5 | 5/5 |
| confirmed_session | unguarded_overlap | tp24_sl15_h12_control | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 7.766925 | 730 | 725 | 1289.51 | 1.443884 | 0.36 | -156.69 | 4/5 | 2/2 |
| confirmed_session | macro_blocked_overlap | tp24_sl15_h12_control | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 7.766925 | 730 | 725 | 1289.51 | 1.443884 | 0.36 | -156.69 | 4/5 | 2/2 |
| confirmed_session | unguarded_nonoverlap | time_exit_12h | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 7.74583 | 730 | 221 | 673.66 | 1.539312 | 1.04 | -189.29 | 4/5 | 2/2 |
| confirmed_session | macro_blocked_nonoverlap | time_exit_12h | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 7.74583 | 730 | 221 | 673.66 | 1.539312 | 1.04 | -189.29 | 4/5 | 2/2 |
| liquidity_session | unguarded_overlap | tp18_sl12_h12 | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 7.173185 | 1024 | 1017 | 1490.41 | 1.394207 | 0.49 | -182.15 | 3/5 | 2/2 |
| liquidity_session | macro_blocked_overlap | tp18_sl12_h12 | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 7.173185 | 1024 | 1017 | 1490.41 | 1.394207 | 0.49 | -182.15 | 3/5 | 2/2 |
| base_h4up_compression_mid_high | unguarded_nonoverlap | tp24_sl15_h12_control | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 6.589525 | 2658 | 623 | 1166.67 | 1.334062 | 0.77 | -258.25 | 4/5 | 4/5 |
| base_h4up_compression_mid_high | macro_blocked_nonoverlap | tp24_sl15_h12_control | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 6.589525 | 2658 | 623 | 1166.67 | 1.334062 | 0.77 | -258.25 | 4/5 | 4/5 |
| liquidity_session | unguarded_nonoverlap | tp18_sl12_h12 | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 5.823925 | 1024 | 370 | 635.19 | 1.374954 | 1.165 | -125.85 | 3/5 | 2/2 |
| liquidity_session | macro_blocked_nonoverlap | tp18_sl12_h12 | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 5.823925 | 1024 | 370 | 635.19 | 1.374954 | 1.165 | -125.85 | 3/5 | 2/2 |
| confirmed_session | unguarded_nonoverlap | tp24_sl15_h12_control | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 5.70021 | 730 | 264 | 462.28 | 1.355603 | 0.57 | -130.32 | 4/5 | 2/2 |
| confirmed_session | macro_blocked_nonoverlap | tp24_sl15_h12_control | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 5.70021 | 730 | 264 | 462.28 | 1.355603 | 0.57 | -130.32 | 4/5 | 2/2 |
| liquidity_session | unguarded_overlap | tp15_sl12_h12 | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 5.5717 | 1024 | 1017 | 1118.14 | 1.298317 | 0.62 | -225.54 | 3/5 | 2/2 |
| liquidity_session | macro_blocked_overlap | tp15_sl12_h12 | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 5.5717 | 1024 | 1017 | 1118.14 | 1.298317 | 0.62 | -225.54 | 3/5 | 2/2 |
| confirmed_session | unguarded_overlap | tp18_sl12_h12 | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 4.77643 | 730 | 725 | 741.06 | 1.26141 | 0.08 | -150.43 | 3/5 | 2/2 |
| confirmed_session | macro_blocked_overlap | tp18_sl12_h12 | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 4.77643 | 730 | 725 | 741.06 | 1.26141 | 0.08 | -150.43 | 3/5 | 2/2 |
| confirmed_h1 | unguarded_nonoverlap | tp24_sl15_h12_control | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 4.134305 | 1947 | 491 | 591.09 | 1.208857 | -0.16 | -168.85 | 3/5 | 3/5 |
| confirmed_h1 | macro_blocked_nonoverlap | tp24_sl15_h12_control | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 4.134305 | 1947 | 491 | 591.09 | 1.208857 | -0.16 | -168.85 | 3/5 | 3/5 |
| base_h4up_compression_mid_high | unguarded_nonoverlap | tp18_sl12_h12 | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 4.03905 | 2658 | 716 | 709.84 | 1.184629 | -0.175 | -259.25 | 3/5 | 4/5 |
| base_h4up_compression_mid_high | macro_blocked_nonoverlap | tp18_sl12_h12 | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 4.03905 | 2658 | 716 | 709.84 | 1.184629 | -0.175 | -259.25 | 3/5 | 4/5 |
| liquidity_session | unguarded_nonoverlap | tp15_sl12_h12 | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 4.02937 | 1024 | 384 | 413.48 | 1.238165 | 1.465 | -175.9 | 3/5 | 2/2 |
| liquidity_session | macro_blocked_nonoverlap | tp15_sl12_h12 | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 4.02937 | 1024 | 384 | 413.48 | 1.238165 | 1.465 | -175.9 | 3/5 | 2/2 |
| confirmed_session | unguarded_overlap | tp15_sl12_h12 | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 3.183085 | 730 | 725 | 428.15 | 1.151768 | 0.13 | -164.71 | 3/5 | 2/2 |
| confirmed_session | macro_blocked_overlap | tp15_sl12_h12 | PROMISING_FOR_STAGE8C_RESEARCH_ONLY | 3.183085 | 730 | 725 | 428.15 | 1.151768 | 0.13 | -164.71 | 3/5 | 2/2 |
| confirmed_h1 | unguarded_overlap | tp18_sl12_h12 | WATCHLIST_THESIS_RESEARCH_ONLY | 4.2936 | 1947 | 1927 | 1366.96 | 1.145816 | -0.33 | -429.2 | 3/5 | 4/5 |
| confirmed_h1 | macro_blocked_overlap | tp18_sl12_h12 | WATCHLIST_THESIS_RESEARCH_ONLY | 4.2936 | 1947 | 1927 | 1366.96 | 1.145816 | -0.33 | -429.2 | 3/5 | 4/5 |
| base_h4up_compression_mid_high | unguarded_nonoverlap | tp15_sl12_h12 | WATCHLIST_THESIS_RESEARCH_ONLY | 2.448885 | 2658 | 756 | 338.27 | 1.08515 | 0.135 | -281.36 | 3/5 | 4/5 |
| base_h4up_compression_mid_high | macro_blocked_nonoverlap | tp15_sl12_h12 | WATCHLIST_THESIS_RESEARCH_ONLY | 2.448885 | 2658 | 756 | 338.27 | 1.08515 | 0.135 | -281.36 | 3/5 | 4/5 |
| base_h4up_compression_mid_high | unguarded_overlap | time_exit_12h | KILL_DRAWDOWN_TOO_HIGH | 19.894685 | 2658 | 2631 | 9435.27 | 1.628706 | 1.35 | -1361.14 | 4/5 | 5/5 |
| base_h4up_compression_mid_high | macro_blocked_overlap | time_exit_12h | KILL_DRAWDOWN_TOO_HIGH | 19.894685 | 2658 | 2631 | 9435.27 | 1.628706 | 1.35 | -1361.14 | 4/5 | 5/5 |
| confirmed_h1 | unguarded_overlap | time_exit_12h | KILL_DRAWDOWN_TOO_HIGH | 16.51817 | 1947 | 1927 | 6747.4 | 1.598457 | 0.81 | -876.85 | 4/5 | 5/5 |
| confirmed_h1 | macro_blocked_overlap | time_exit_12h | KILL_DRAWDOWN_TOO_HIGH | 16.51817 | 1947 | 1927 | 6747.4 | 1.598457 | 0.81 | -876.85 | 4/5 | 5/5 |
| base_h4up_compression_mid_high | unguarded_overlap | tp24_sl15_h12_control | KILL_DRAWDOWN_TOO_HIGH | 9.44522 | 2658 | 2631 | 4016.48 | 1.30172 | 0.48 | -703.15 | 3/5 | 5/5 |
| base_h4up_compression_mid_high | macro_blocked_overlap | tp24_sl15_h12_control | KILL_DRAWDOWN_TOO_HIGH | 9.44522 | 2658 | 2631 | 4016.48 | 1.30172 | 0.48 | -703.15 | 3/5 | 5/5 |
| confirmed_h1 | unguarded_overlap | tp24_sl15_h12_control | KILL_DRAWDOWN_TOO_HIGH | 7.411865 | 1947 | 1927 | 2617.15 | 1.261822 | -0.03 | -465.74 | 3/5 | 5/5 |
| confirmed_h1 | macro_blocked_overlap | tp24_sl15_h12_control | KILL_DRAWDOWN_TOO_HIGH | 7.411865 | 1947 | 1927 | 2617.15 | 1.261822 | -0.03 | -465.74 | 3/5 | 5/5 |
| base_h4up_compression_mid_high | unguarded_overlap | tp18_sl12_h12 | KILL_DRAWDOWN_TOO_HIGH | 6.339485 | 2658 | 2631 | 2639.67 | 1.211608 | 0.08 | -693.85 | 3/5 | 4/5 |
| base_h4up_compression_mid_high | macro_blocked_overlap | tp18_sl12_h12 | KILL_DRAWDOWN_TOO_HIGH | 6.339485 | 2658 | 2631 | 2639.67 | 1.211608 | 0.08 | -693.85 | 3/5 | 4/5 |
| base_h4up_compression_mid_high | unguarded_overlap | tp15_sl12_h12 | KILL_DRAWDOWN_TOO_HIGH | 4.4305 | 2658 | 2631 | 1720.5 | 1.141157 | 0.48 | -610.71 | 3/5 | 4/5 |
| base_h4up_compression_mid_high | macro_blocked_overlap | tp15_sl12_h12 | KILL_DRAWDOWN_TOO_HIGH | 4.4305 | 2658 | 2631 | 1720.5 | 1.141157 | 0.48 | -610.71 | 3/5 | 4/5 |
| confirmed_session | unguarded_nonoverlap | tp18_sl12_h12 | KILL_SESSION_CONCENTRATED | 3.05657 | 730 | 292 | 246.92 | 1.175703 | -0.275 | -132.67 | 3/5 | 1/2 |
| confirmed_session | macro_blocked_nonoverlap | tp18_sl12_h12 | KILL_SESSION_CONCENTRATED | 3.05657 | 730 | 292 | 246.92 | 1.175703 | -0.275 | -132.67 | 3/5 | 1/2 |
| confirmed_h1 | unguarded_overlap | tp15_sl12_h12 | KILL_LOW_PF_X4 | 2.33597 | 1947 | 1927 | 695.1 | 1.075874 | -0.03 | -382.41 | 2/5 | 4/5 |
| confirmed_h1 | macro_blocked_overlap | tp15_sl12_h12 | KILL_LOW_PF_X4 | 2.33597 | 1947 | 1927 | 695.1 | 1.075874 | -0.03 | -382.41 | 2/5 | 4/5 |
| confirmed_h1 | unguarded_nonoverlap | tp18_sl12_h12 | KILL_LOW_PF_X4 | 2.031525 | 1947 | 553 | 204.73 | 1.067233 | -0.81 | -215.85 | 3/5 | 3/5 |
| confirmed_h1 | macro_blocked_nonoverlap | tp18_sl12_h12 | KILL_LOW_PF_X4 | 2.031525 | 1947 | 553 | 204.73 | 1.067233 | -0.81 | -215.85 | 3/5 | 3/5 |
| confirmed_session | unguarded_nonoverlap | tp15_sl12_h12 | KILL_LOW_PF_X4 | 1.537285 | 730 | 300 | 83.55 | 1.058708 | -0.215 | -185.41 | 3/5 | 1/2 |
| confirmed_session | macro_blocked_nonoverlap | tp15_sl12_h12 | KILL_LOW_PF_X4 | 1.537285 | 730 | 300 | 83.55 | 1.058708 | -0.215 | -185.41 | 3/5 | 1/2 |
| confirmed_h1 | unguarded_nonoverlap | tp15_sl12_h12 | KILL_LOW_PF_X4 | 1.180315 | 1947 | 584 | 39.01 | 1.012522 | -0.345 | -248.26 | 3/5 | 3/5 |
| confirmed_h1 | macro_blocked_nonoverlap | tp15_sl12_h12 | KILL_LOW_PF_X4 | 1.180315 | 1947 | 584 | 39.01 | 1.012522 | -0.345 | -248.26 | 3/5 | 3/5 |

## Decision rules
- `PROMISING_FOR_STAGE8C_RESEARCH_ONLY`: one thesis definition deserves deeper robustness validation.
- `WATCHLIST_THESIS_RESEARCH_ONLY`: not tradable; can be refined once, not repeatedly filter-mined.
- `KILL_*`: stop this thesis definition.

## Interpretation
- This is the first actual strategy-thesis step after regime discovery.
- If all definitions fail, price-only mechanical development should pause or pivot to macro/discretionary-assisted workflow.
- No EA change is allowed from Stage 8B alone.
