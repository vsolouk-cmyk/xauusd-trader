# Stage 9C Macro Regime Interaction Lab

Generated UTC: `2026-06-10T04:57:52+00:00`
Tool version: `v1`

> Hard rule: research only. This does not authorize demo, paper, or live orders.

## Inputs
- db: `data/local/xauusd_local_store.sqlite`
- macro_numeric_rows: `8444`
- daily_regime_rows: `1620`
- stage8b_trades_loaded: `64474`
- stage8b_candidate_trades_loaded: `524`
- stage8d_signals_loaded: `0`

## Daily numeric macro regime coverage
| Macro regime | Days |
|---|---:|
| hostile | 173 |
| mixed | 483 |
| neutral | 853 |
| supportive | 111 |

## Stage 8D candidate family × numeric macro regime
Candidate filter used here:

```text
definition = liquidity_session
guard_variant contains nonoverlap
geometry = time_exit_12h
```

| Definition | Guard | Geometry | Macro regime | Trades | Total x4 | Median x4 | PF x4 | WR x4 | DD x4 |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| liquidity_session | macro_blocked_nonoverlap | time_exit_12h | neutral | 143 | 623.83 | 1.98 | 1.890041 | 0.573427 | -194.1 |
| liquidity_session | macro_blocked_nonoverlap | time_exit_12h | mixed | 83 | 397.05 | 2.72 | 1.737627 | 0.590361 | -124.53 |
| liquidity_session | macro_blocked_nonoverlap | time_exit_12h | supportive | 29 | 111.29 | 0.26 | 2.746822 | 0.517241 | -19.31 |
| liquidity_session | macro_blocked_nonoverlap | time_exit_12h | hostile | 7 | 72.97 | 9.91 | 13.141431 | 0.857143 | -6.01 |
| liquidity_session | unguarded_nonoverlap | time_exit_12h | neutral | 143 | 623.83 | 1.98 | 1.890041 | 0.573427 | -194.1 |
| liquidity_session | unguarded_nonoverlap | time_exit_12h | mixed | 83 | 397.05 | 2.72 | 1.737627 | 0.590361 | -124.53 |
| liquidity_session | unguarded_nonoverlap | time_exit_12h | supportive | 29 | 111.29 | 0.26 | 2.746822 | 0.517241 | -19.31 |
| liquidity_session | unguarded_nonoverlap | time_exit_12h | hostile | 7 | 72.97 | 9.91 | 13.141431 | 0.857143 | -6.01 |

## Scoring model
For long-gold bias:

```text
macro_score = rate_pressure + usd_pressure + oil_inflation_pressure + growth_fear

rising real yield  -> hostile
falling real yield -> supportive
strong USD         -> hostile
weak USD           -> supportive
oil spike          -> mixed/hostile via inflation/Fed pressure
deeply inverted curve -> mild growth-fear support
```

## Interpretation rules
- If supportive/mixed regimes improve PF, median and drawdown without destroying trade count, macro is useful as a guard.
- If macro segmentation only removes trades without improving robustness, it is filter-mining and should be rejected.
- This stage uses numeric macro pressure only. Scheduled event/shock windows remain a separate layer.

## Decision
- No EA/order workflow changes are allowed from Stage 9C alone.
- If a regime interaction is strong, Stage 9D should create a macro-aware forward-shadow report, not order execution.
