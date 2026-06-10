# Stage 4J Shock / Regime Sensitivity Lab

Generated UTC: `2026-06-08T19:40:06+00:00`

> Hard rule: research only. No demo, paper, or live authorization.

## Inputs
- trades_csv: `data/reports/stage4g_v2/stage4g_v2_non_overlap_trades.csv`
- shock_start: `2026-02-28T00:00:00Z`
- recent_start: `2026-06-01T00:00:00Z`

## Group summary
| Group | Trades | Total | PF | Median | Win rate | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| all | 961 | 854.85 | 1.122411 | -3.57 | 0.448491 | -396.42 |
| pre_2026 | 600 | 572.39 | 1.151001 | -1.73 | 0.463333 | -198.21 |
| year_2026 | 361 | 282.46 | 1.088468 | -15.35 | 0.423823 | -396.42 |
| pre_shock | 766 | 846.9 | 1.163258 | -2.3 | 0.460836 | -245.82 |
| shock_or_after | 195 | 7.95 | 1.004427 | -15.35 | 0.4 | -396.42 |
| recent_or_after | 5 | 40.25 | 2.311075 | 23.65 | 0.6 | -30.7 |

## Interpretation
- If `shock_or_after` is much better than `pre_shock`, the rule may be benefiting from conflict/energy-volatility regime.
- If `recent_or_after` has too few trades, do not infer anything from today alone.
- Keep live dry-run running, but do not place orders from this report.
