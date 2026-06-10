# Stage 10C Numeric Shock Event Backfill

Generated UTC: `2026-06-10T09:34:16+00:00`
Tool version: `v1`

> Hard rule: historical event backfill only. This does not authorize demo, paper, or live orders.

## Status
- db: `data/local/xauusd_local_store.sqlite`
- generated_numeric_shocks: `500`
- existing_events_before_merge: `515`
- merged_stage10a_events: `515`
- out_events_csv: `data/config/stage10a_news_events.csv`
- shock_events_csv: `data/macro/events/stage10c_numeric_shock_events.csv`

## Generated shocks by class
| Event class | Events |
|---|---:|
| oil_supply_shock | 217 |
| real_yield_shock | 143 |
| usd_shock | 55 |
| front_end_yield_shock | 52 |
| nominal_yield_shock | 33 |

## Generated shocks by channel
| Channel | Events |
|---|---:|
| real_yield_fed_path | 228 |
| oil_inflation_pressure | 217 |
| usd_pressure | 55 |

## Expected gold direction
| Direction | Meaning | Events |
|---:|---|---:|
| 1 | initially supportive | 109 |
| -1 | initially hostile | 174 |
| 0 | mixed / impact-only | 217 |

## Recent generated shocks preview
| Time UTC | Class | Channel | Expected | Importance | Title |
|---|---|---|---:|---:|---|
| 2026-04-10T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.8 | DCOILWTICO oil_supply_shock mixed on 2026-04-10 |
| 2026-04-14T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.8 | DCOILBRENTEU oil_supply_shock mixed on 2026-04-14 |
| 2026-04-14T13:30:00+00:00 | usd_shock | usd_pressure | 1 | 1.5 | DTWEXBGS usd_shock supportive on 2026-04-14 |
| 2026-04-15T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.2 | DCOILBRENTEU oil_supply_shock mixed on 2026-04-15 |
| 2026-04-17T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.8 | DCOILBRENTEU oil_supply_shock mixed on 2026-04-17 |
| 2026-04-20T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.8 | DCOILBRENTEU oil_supply_shock mixed on 2026-04-20 |
| 2026-04-21T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.8 | DCOILBRENTEU oil_supply_shock mixed on 2026-04-21 |
| 2026-04-22T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.8 | DCOILWTICO oil_supply_shock mixed on 2026-04-22 |
| 2026-04-23T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.2 | DCOILWTICO oil_supply_shock mixed on 2026-04-23 |
| 2026-04-24T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.8 | DCOILBRENTEU oil_supply_shock mixed on 2026-04-24 |
| 2026-04-27T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.8 | DCOILBRENTEU oil_supply_shock mixed on 2026-04-27 |
| 2026-04-28T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.8 | DCOILBRENTEU oil_supply_shock mixed on 2026-04-28 |
| 2026-04-29T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.8 | DCOILWTICO oil_supply_shock mixed on 2026-04-29 |
| 2026-04-30T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.2 | DCOILBRENTEU oil_supply_shock mixed on 2026-04-30 |
| 2026-05-01T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.2 | DCOILBRENTEU oil_supply_shock mixed on 2026-05-01 |
| 2026-05-06T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.8 | DCOILBRENTEU oil_supply_shock mixed on 2026-05-06 |
| 2026-05-07T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.8 | DCOILBRENTEU oil_supply_shock mixed on 2026-05-07 |
| 2026-05-08T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.8 | DCOILBRENTEU oil_supply_shock mixed on 2026-05-08 |
| 2026-05-11T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.8 | DCOILBRENTEU oil_supply_shock mixed on 2026-05-11 |
| 2026-05-12T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.2 | DCOILWTICO oil_supply_shock mixed on 2026-05-12 |
| 2026-05-13T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.2 | DCOILBRENTEU oil_supply_shock mixed on 2026-05-13 |
| 2026-05-14T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.2 | DCOILBRENTEU oil_supply_shock mixed on 2026-05-14 |
| 2026-05-15T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.8 | DCOILBRENTEU oil_supply_shock mixed on 2026-05-15 |
| 2026-05-15T13:30:00+00:00 | real_yield_shock | real_yield_fed_path | -1 | 1.2 | DFII10 real_yield_shock hostile on 2026-05-15 |
| 2026-05-18T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.8 | DCOILBRENTEU oil_supply_shock mixed on 2026-05-18 |
| 2026-05-18T13:30:00+00:00 | real_yield_shock | real_yield_fed_path | -1 | 1.2 | DFII10 real_yield_shock hostile on 2026-05-18 |
| 2026-05-19T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.2 | DCOILWTICO oil_supply_shock mixed on 2026-05-19 |
| 2026-05-19T13:30:00+00:00 | real_yield_shock | real_yield_fed_path | -1 | 1.2 | DFII10 real_yield_shock hostile on 2026-05-19 |
| 2026-05-20T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.2 | DCOILWTICO oil_supply_shock mixed on 2026-05-20 |
| 2026-05-20T13:30:00+00:00 | real_yield_shock | real_yield_fed_path | -1 | 1.2 | DFII10 real_yield_shock hostile on 2026-05-20 |
| 2026-05-21T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.8 | DCOILWTICO oil_supply_shock mixed on 2026-05-21 |
| 2026-05-21T13:30:00+00:00 | real_yield_shock | real_yield_fed_path | -1 | 1.2 | DFII10 real_yield_shock hostile on 2026-05-21 |
| 2026-05-22T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.8 | DCOILWTICO oil_supply_shock mixed on 2026-05-22 |
| 2026-05-26T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.8 | DCOILBRENTEU oil_supply_shock mixed on 2026-05-26 |
| 2026-05-27T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.8 | DCOILBRENTEU oil_supply_shock mixed on 2026-05-27 |
| 2026-05-28T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.8 | DCOILBRENTEU oil_supply_shock mixed on 2026-05-28 |
| 2026-05-29T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.8 | DCOILBRENTEU oil_supply_shock mixed on 2026-05-29 |
| 2026-06-01T13:30:00+00:00 | oil_supply_shock | oil_inflation_pressure | 0 | 1.2 | DCOILBRENTEU oil_supply_shock mixed on 2026-06-01 |
| 2026-06-05T13:30:00+00:00 | real_yield_shock | real_yield_fed_path | -1 | 1.2 | DFII10 real_yield_shock hostile on 2026-06-05 |
| 2026-06-08T13:30:00+00:00 | real_yield_shock | real_yield_fed_path | -1 | 1.2 | DFII10 real_yield_shock hostile on 2026-06-08 |

## Interpretation
- These are numeric shock proxies derived from FRED observations, not original news timestamps.
- They are useful for historical event-reaction testing when news APIs are unavailable.
- Stage 10A must measure actual XAUUSD reaction and decide whether each class is relevant/noisy.

## Decision
- No EA change.
- No automatic news trading.
- Run Stage 10A next on the merged event file.
