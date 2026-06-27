# Stage98C COT Feature Alias Fix

Stage98B fixed pandas 3.14 numeric loading, but portfolio review could still reject all COT additions with `MISSING_COLUMNS:cot_mm_net_z` when the normalized COT dataset came from the official Stage95 builder.

The official Stage95 dataset emits rolling-window COT columns such as:

- `managed_money_net_pct_oi_z_156w`
- `managed_money_net_z_156w`
- `managed_money_net_pct_oi_change_4w`

Stage96 uses the research aliases:

- `cot_mm_net_z`
- `cot_mm_net_z_change_4w`

Stage98C maps the official Stage95 column names to the Stage96 aliases before evaluating COT rule conditions.

No thresholds, thesis rules, MT5 files, observer CSVs, or order permissions are changed.
