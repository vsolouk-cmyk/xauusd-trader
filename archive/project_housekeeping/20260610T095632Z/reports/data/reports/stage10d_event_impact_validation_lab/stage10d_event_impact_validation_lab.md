# Stage 10D Event Impact Validation Lab

Generated UTC: `2026-06-10T09:34:21+00:00`
Tool version: `v1`

> Hard rule: validation only. This does not authorize demo, paper, or live orders.

## Inputs
- db: `data/local/xauusd_local_store.sqlite`
- annotated_events_csv: `data/reports/stage10a_event_impact_lab/stage10a_events_annotated.csv`
- raw_events_loaded: `510`
- declustered_events: `351`
- controls_generated: `1404`
- min_gap_hours: `48`
- controls_per_event: `4`

## Verdict counts
| Verdict | Classes |
|---|---:|
| directional_or_guard_candidate | 2 |
| insufficient_sample | 1 |
| reject_or_noise | 3 |

## Event class validation summary
| Event class | Channel | Events | Controls | Avg lift | Median lift | Event high/med | Control high/med | Dir acc | Verdict |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| usd_shock | usd_pressure | 40 | 160 | 1.335575 | 1.107752 | 0.75 | 0.75 | 0.55 | reject_or_noise |
| real_yield_shock | real_yield_fed_path | 102 | 408 | 1.031438 | 0.925693 | 0.784314 | 0.737745 | 0.633663 | reject_or_noise |
| oil_supply_shock | oil_inflation_pressure | 142 | 568 | 0.985541 | 0.969191 | 0.802817 | 0.757042 |  | reject_or_noise |
| central_bank_gold_demand | central_bank_demand | 1 | 4 | 0.362689 | 0.740644 | 0.0 | 0.5 | 1 | insufficient_sample |
| front_end_yield_shock | real_yield_fed_path | 40 | 160 | 1.56094 | 1.47308 | 0.85 | 0.75 | 0.6 | directional_or_guard_candidate |
| nominal_yield_shock | real_yield_fed_path | 26 | 104 | 1.435516 | 1.887377 | 0.884615 | 0.692308 | 0.576923 | directional_or_guard_candidate |

## Interpretation
- Stage 10A measured impact, but Stage 10D asks whether that impact is larger than matched non-event windows.
- De-clustering reduces repeated regime days being counted as independent events.
- `directional_or_guard_candidate` can be tested later as a report/guard layer.
- `risk_volatility_warning_candidate` is not directional; it can support no-trade/event-risk warnings.
- `reject_or_noise` should not be used for trading decisions.

## Decision
- No EA change.
- No automatic news trading.
- If a class passes validation, next step is Stage 10E: event-aware report/guard simulation, not live execution.
