# Stage108 Unified Observer Second-Order Expansion

Purpose: expand the observer-only unified bridge from the Stage100 six-rule portfolio to a seven-rule portfolio by adding the Stage107-selected second-order COT/macro rule:

`S105_03_COT_DECROWDING_CB_SUPPORT_RY_RELIEF_H120`

Condition:

`cot_mm_net_z_change_4w < 0 AND central_bank_demand_tonnes_3m > 0 AND real_yield_change_20d < 0`

Hard blocks:

- No automated order
- No paper order
- No broker connection
- No order send in EA
- Observer-only EA
- No paper-live
- No live
- No threshold tuning

Daily operational CSV remains:

`data/mt5_bridge/unified_observer_signal.csv`

The EA file is updated only to display the seventh rule. It still contains no order-send path.


## Stage108B loader fix
- Normalizes `date_utc` and COT `available_after_utc` before lookahead comparison.
- Renames any macro-side `available_after_utc` to `macro_available_after_utc` before merge to avoid datetime/Float64 comparison errors.
- Does not change rules, thresholds, MT5 permissions, or observer-only hard blocks.
