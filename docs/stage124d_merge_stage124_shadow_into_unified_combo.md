# Stage124D merge Stage124 shadow into unified combo

Purpose: merge the Stage124C SPDR-flow macro-relief observer into the unified combo as an 8th **shadow-only** rule.

This patch does not enable trading. It does not use `CTrade`, does not call `OrderSend`, and does not write paper/live/order files.

## Outputs

- `data/shadow_observer/stage124d_unified_combo_plus_stage124_shadow.csv`
- `reports/stage124d_merge_stage124_shadow_into_unified_combo/stage124d_unified_combo_plus_stage124_shadow.csv`
- `reports/stage124d_merge_stage124_shadow_into_unified_combo/stage124d_merge_stage124_shadow_into_unified_combo_summary.json`
- `mql5/Experts/XAUUSD_Stage124D_UnifiedComboShadowOnly.mq5`
- optional MT5 copies when run with `--write-mt5-csv --write-mql5-ea`

## Intended operational state

- Keep previous 7-rule combo running until the old combo EA is intentionally patched/replaced.
- Use Stage124D only as observer-only merged shadow confirmation.
- Do not interpret this as paper/live readiness.
