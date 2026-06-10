# Stage 7B Strategy Redesign Lab

Generated UTC: `2026-06-09T13:11:50+00:00`
Tool version: `v1`

> Hard rule: research only. This does not authorize demo, paper, or live orders.

## Inputs
- db: `data/local/xauusd_local_store.sqlite`
- h1_rows: `24225`
- m1_rows: `1449867`
- macro_windows: `5`
- base_cost_usd: `0.35`

## Ranking
| Family | Design | Guard | Decision | Score | Trades | Total x1 | Total x4 | PF x4 | Median x4 | DD x1 | Pos years |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| asia_breakout_retest | no_signals | unguarded | KILL_TOO_FEW_TRADES | 0.0 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0/0 |
| asia_breakout_retest | no_signals | macro_blocked | KILL_TOO_FEW_TRADES | 0.0 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0/0 |
| failed_break_reversal | no_signals | unguarded | KILL_TOO_FEW_TRADES | 0.0 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0/0 |
| failed_break_reversal | no_signals | macro_blocked | KILL_TOO_FEW_TRADES | 0.0 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0/0 |
| h4_trend_h1_pullback_continuation | balanced_pullback | macro_blocked | KILL_COST_STRESS_X4_NEGATIVE | -1.673266 | 699 | -55.509464 | -789.459464 | 0.816726 | -3.05 | -531.92357 | 2/5 |
| h4_trend_h1_pullback_continuation | balanced_pullback | unguarded | KILL_COST_STRESS_X4_NEGATIVE | -1.719926 | 701 | -76.739464 | -812.789464 | 0.812326 | -3.05 | -531.92357 | 2/5 |
| baseline_sma_distance_v1_control | control_v1_long | macro_blocked | KILL_COST_STRESS_X4_NEGATIVE | -2.16278 | 1105 | 268.64 | -891.61 | 0.901559 | -6.22 | -658.68 | 2/5 |
| baseline_sma_distance_v1_control | control_v1_long | unguarded | KILL_COST_STRESS_X4_NEGATIVE | -2.26458 | 1108 | 222.59 | -940.81 | 0.896688 | -6.56 | -658.68 | 2/5 |
| compression_expansion_confirmed | range16_pct18_expansion | unguarded | KILL_COST_STRESS_X4_NEGATIVE | -2.9611 | 428 | -395.92705 | -845.32705 | 0.69023 | -6.09 | -604.772725 | 0/5 |
| compression_expansion_confirmed | range16_pct18_expansion | macro_blocked | KILL_COST_STRESS_X4_NEGATIVE | -2.9611 | 428 | -395.92705 | -845.32705 | 0.69023 | -6.09 | -604.772725 | 0/5 |

## Macro windows
- `2026-06-10T10:30:00+00:00` → `2026-06-10T16:30:00+00:00` | US CPI | high | block
- `2026-06-11T11:00:00+00:00` → `2026-06-11T15:30:00+00:00` | US PPI | high | block
- `2026-06-17T15:00:00+00:00` → `2026-06-18T00:00:00+00:00` | FOMC | high | block
- `2026-06-05T10:30:00+00:00` → `2026-06-05T16:30:00+00:00` | US NFP | high | block
- `2026-06-08T00:00:00+00:00` → `2026-06-10T23:59:00+00:00` | iran_israel_shock | shock | block

## Decision rules
- `PROMISING_FOR_STAGE7C_RESEARCH_ONLY`: candidate for deeper validation only, not tradable.
- `WATCHLIST_REDESIGN_NEEDED`: not dead, but thesis or execution logic needs redesign.
- `KILL_*`: do not rescue with filter mining.

## Interpretation
- If all families are killed, the current mechanical-thesis set is insufficient.
- If only macro-blocked improves a family meaningfully, Stage 7C must validate the guard separately.
- No EA change is allowed from this report alone.
