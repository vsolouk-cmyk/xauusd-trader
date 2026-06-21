# Stage57A Context Source Precheck and Derived Regime Table

- status: `CONTEXT_SOURCE_PRECHECK_COMPLETE_NO_PROMOTION`
- decision: `CONTEXT_TABLE_READY_FOR_STAGE58_DESIGN_NO_PROMOTION`
- next_allowed_step: `STAGE58_CONTEXT_AWARE_THESIS_DESIGN_NO_PROMOTION_AND_CONTINUE_STAGE52_FORWARD_SHADOW`
- promotion: `NO_GO`
- EA: `NO_GO`
- paper_live: `NO_GO`
- live: `NO_GO`

## Context inventory
- `CTX_SESSION_AND_SPREAD_REGIME` priority=`1` available_now=`True` status=`AVAILABLE_DERIVED_FROM_BROKER_DB`
- `CTX_NEWS_BLACKOUT_CALENDAR` priority=`2` available_now=`False` status=`NEEDS_MANUAL_OR_EXTERNAL_CSV`
- `CTX_USD_RATE_PROXY` priority=`3` available_now=`False` status=`NEEDS_EXTERNAL_CSV_OR_EXISTING_PROXY`
- `CTX_COT_WEEKLY_POSITIONING` priority=`4` available_now=`True` status=`LOCAL_PATH_FOUND_SCHEMA_NOT_ASSUMED`
  - `/Users/vahid/Desktop/xauusd-trader/data/cot/cftc`
  - `/Users/vahid/Desktop/xauusd-trader/data/cot/cftc/artifacts`
- `CTX_REFERENCE_PRICE_BASIS` priority=`5` available_now=`True` status=`LOCAL_REFERENCE_PATH_FOUND_OPTIONAL`
  - `/Users/vahid/Desktop/xauusd-trader/data/normalized/normalized_twelvedata_XAU_USD_5min_backfill_20260619T051819Z.csv`
  - `/Users/vahid/Desktop/xauusd-trader/data/normalized`

## Derived regime tables
- M15: rows=`97573` start=`2022-05-01T22:00:00Z` end=`2026-06-19T16:45:00Z` output=`/Users/vahid/Desktop/xauusd-trader/reports/stage57_context_precheck/stage57a_m15_context_regime_table.csv`
  - spread_cost_bps_quantiles: `{'q50': 1.2397974997417087, 'q75': 1.7479910955277134, 'q90': 2.440651491251248, 'q95': 2.5927014221298474, 'q99': 2.755512623511697}`
  - range_bps_quantiles: `{'q25': 7.255103249496719, 'q50': 10.999601919169354, 'q75': 17.204767210693802, 'q90': 26.81599455331067}`
- M5: rows=`292567` start=`2022-05-01T22:00:00Z` end=`2026-06-19T16:55:00Z` output=`/Users/vahid/Desktop/xauusd-trader/reports/stage57_context_precheck/stage57a_m5_context_regime_table.csv`
  - spread_cost_bps_quantiles: `{'q50': 1.2516010062872092, 'q75': 1.759547485799554, 'q90': 2.4468936685675846, 'q95': 2.652003292870026, 'q99': 2.7640395797389976}`
  - range_bps_quantiles: `{'q25': 3.996476872086699, 'q50': 6.169839857164831, 'q75': 9.708870243748306, 'q90': 15.087331421389157}`

## Checks
- none

## Interpretation
Stage57A is a context-precheck and regime-table generation step only. It does not scan a trading thesis, does not use context as a forward label, and does not authorize promotion, EA, paper-live, live trading, or order submission.
