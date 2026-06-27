# Stage99 Unified Observer COT Expansion

## Purpose

Stage99 expands the existing unified observer-only bridge from five rules to six rules by adding the Stage98-selected COT positioning rule:

- `C96_07_CB_SUPPORT_NOT_CROWDED_H120`

The stage remains observer-only. It cannot authorize orders, connect to a broker, or promote an EA.

## Inputs

- `data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv`
- `data/external_frontiers/cot_positioning_normalized.csv`
- `reports/stage98_cot_portfolio_increment_review/stage98_cot_portfolio_increment_review_summary.json`

## Output

- `data/mt5_bridge/unified_observer_signal.csv`
- `reports/stage99_unified_observer_cot_expansion/stage99_unified_observer_cot_expansion_summary.json`
- `reports/stage99_unified_observer_cot_expansion/stage99_unified_observer_cot_expansion_report.md`

## Rule set

- `K06_RESILIENT_GOLD_VS_DXY_H120`
- `K03_SAFE_HAVEN_REALYIELD_H120`
- `K07_DXY_TREND_RELIEF_GOLD_TREND_H120`
- `S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120`
- `S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120`
- `C96_07_CB_SUPPORT_NOT_CROWDED_H120`

## COT rule

`C96_07_CB_SUPPORT_NOT_CROWDED_H120` is active when:

- `cot_mm_net_z < 1.0`
- `central_bank_demand_tonnes_3m > 0.0`
- `gold_ret_20d < 0.0`

## COT aliasing

The script accepts the official Stage95 normalized COT column names and maps them to the internal rule aliases:

- `managed_money_net_pct_oi_z_156w -> cot_mm_net_z`
- `managed_money_net_z_156w -> cot_mm_net_z`
- `managed_money_net_pct_oi_change_4w -> cot_mm_net_z_change_4w`
- `managed_money_net_change_4w -> cot_mm_net_z_change_4w`

## Hard blocks

- No automated order
- No paper order
- No broker connection
- No order send in EA
- Observer-only EA
- No paper-live
- No live
- No order authorization from Stage99
- No threshold tuning from unified COT observer expansion
