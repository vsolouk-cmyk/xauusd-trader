# Stage 10A Event / News Impact Lab

Generated UTC: `2026-06-10T09:34:18+00:00`
Tool version: `v1`

> Hard rule: research only. This does not authorize demo, paper, or live orders.

## Inputs
- db: `data/local/xauusd_local_store.sqlite`
- events_csv: `data/config/stage10a_news_events.csv`
- events_loaded: `515`
- h1_bars: `24225`
- reactions_resolved: `510`
- class_weight_rows: `6`

## Impact buckets
| Bucket | Events |
|---|---:|
| high_impact | 297 |
| low_impact | 66 |
| medium_impact | 102 |
| noisy_or_no_impact | 45 |

## Verdict counts
| Verdict | Events |
|---|---:|
| candidate_relevant | 316 |
| impactful_but_direction_wrong | 83 |
| likely_noise | 45 |
| low_impact_monitor | 66 |

## Adaptive event-class weights
| Event class | Channel | Events | Avg norm impact 12h | Direction acc 12h | Relevant | Noise | Recommended weight |
|---|---|---:|---:|---:|---:|---:|---:|
| oil_supply_shock | oil_inflation_pressure | 217 | 6.550381 |  | 166 | 20 | 1.125 |
| central_bank_gold_demand | central_bank_demand | 10 | 4.155664 | 0.666667 | 4 | 1 | 1.0 |
| usd_shock | usd_pressure | 55 | 8.337094 | 0.6 | 30 | 8 | 0.9 |
| front_end_yield_shock | real_yield_fed_path | 52 | 9.514112 | 0.596154 | 29 | 2 | 0.894231 |
| real_yield_shock | real_yield_fed_path | 143 | 6.375099 | 0.584507 | 70 | 11 | 0.876761 |
| nominal_yield_shock | real_yield_fed_path | 33 | 8.246838 | 0.575758 | 17 | 3 | 0.863636 |

## Interpretation
- `high_impact` and `medium_impact` event classes become candidates for future reporting/guard logic.
- `likely_noise` classes should not be used in trading decisions.
- `impactful_but_direction_wrong` means the event moves gold but our initial direction model is wrong.
- `recommended_weight` is conservative and sample-size capped; small samples cannot create strong weights.

## Commercialization relevance
- This stage can accelerate the project because it does not wait for rare v2 technical signals.
- It turns news evaluation into measured event-reaction data.
- It can later support a semi-discretionary dashboard: technical regime + macro numeric + event risk.

## Decision
- No EA change.
- No automatic news trading.
- Next valid step is filling curated event rows and rerunning this lab.
