# Stage 9D Macro-Aware Forward Shadow Report

Generated UTC: `2026-06-10T04:57:55+00:00`
Tool version: `v1`

> Hard rule: report only. This does not authorize demo, paper, or live orders.

## Inputs
- db: `data/local/xauusd_local_store.sqlite`
- signals_csv: `/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/XAUUSD_DryRun_v2_regime_shadow_signals.csv`
- outcomes_csv: `data/reports/stage8d_forward_shadow_outcomes/stage8d_forward_shadow_outcomes.csv`
- macro_regime_rows: `1620`
- signals_loaded: `0`
- outcomes_loaded: `0`

## Latest numeric macro snapshot
- obs_date: `2026-06-08`
- macro_regime: `neutral`
- macro_score_long_gold: `0.5`
- reason: `oil=0.5`
- real_yield_10y: `2.21`
- nominal_yield_10y: `4.56`
- nominal_yield_2y: `4.15`
- usd_index: `120.0831`
- wti: `95.96`
- d_real_yield_5d: `0.10000000000000009`
- d_usd_5d_pct: `0.5849153326051585`
- d_oil_5d_pct: `0.0`

## Monitoring warning
- `MACRO_NEUTRAL_CONTEXT_MONITOR`

## Stage 8D live forward-shadow outcomes by macro regime
| Macro regime | Resolved | Total x4 | Median x4 | PF x4 | WR x4 |
|---|---:|---:|---:|---:|---:|
| none | 0 | 0 | 0 | 0 | 0 |

## Recent annotated signals
| Planned entry UTC | Session | Macro regime | Macro score | Reason |
|---|---|---|---:|---|
| none | none | none | 0 | no Stage 8D signal yet |

## Interpretation
- Stage 9C did not justify a macro block/allow rule yet.
- Numeric macro context should be monitored and reported, not used to modify EA entries.
- Hostile numeric regime has too few historical candidate trades and was not bad enough to justify blocking.
- Event/shock windows remain separate from numeric regime and must be handled in the event layer.

## Decision
- No EA change.
- No macro guard yet.
- Continue Stage 8D forward-shadow logging and report macro context alongside each signal/outcome.
