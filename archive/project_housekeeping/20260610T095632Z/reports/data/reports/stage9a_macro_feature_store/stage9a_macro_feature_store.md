# Stage 9A Macro/Fundamental Feature Store

Generated UTC: `2026-06-09T19:09:02+00:00`
Tool version: `v1`

> Hard rule: research only. This does not authorize demo, paper, or live orders.

## Inputs
- db: `data/local/xauusd_local_store.sqlite`
- events_csv: `data/config/stage9a_macro_events.csv`
- h1_rows: `24225`
- events_loaded: `0`
- stage8b_trades_annotated: `64474`
- stage8d_signals_annotated: `0`

## Macro regime coverage
| Macro regime | H1 rows |
|---|---:|
| neutral | 24225 |

## Stage 8B × Macro summary
| Macro regime | Trades | Total net x4 | Median net x4 | PF x4 | Win rate x4 |
|---|---:|---:|---:|---:|---:|
| neutral | 62604 | 107072.3 | 0.48 | 1.347556 | 0.515654 |
| unknown | 1870 | 2024.16 | -0.13 | 1.233382 | 0.499465 |

## Scoring model
```text
score = event_gold_bias + safe_haven_score + growth_fear_score + central_bank_demand_score
        - real_yield_pressure - usd_pressure - oil_inflation_pressure
```

## Decision
- Stage 9A only creates the macro feature layer.
- Stage 9B must test technical candidate behavior under supportive/hostile/mixed/event-risk regimes.
- No EA/order workflow change is allowed from Stage 9A.

## Warning
- No real macro events loaded. Copy the template and fill `data/config/stage9a_macro_events.csv`.
