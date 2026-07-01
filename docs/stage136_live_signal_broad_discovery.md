# Stage136 Live Signal Broad Discovery

Stage135B proved that the historical tail feature date is too old for direct demo selection.
Stage136 fixes the bottleneck by using:

- historical Stage117 dataset for validation/tail metrics
- current MT5 `unified_observer_signal.csv` for live feature activation

It scans:
- single-feature quantile thresholds
- two-feature AND candidates across common live/historical numeric features

Stage136 does not send orders. It only writes a Stage134-compatible KV:

- `xauusd_stage136_broad_discovery_rule_state_kv.csv`

If Stage136 produces `selected_rule_id`, manually set Stage134 inputs:

- `InpRuleStateKvFile = xauusd_stage136_broad_discovery_rule_state_kv.csv`
- `InpAllowedRules = <selected_rule_id>`
- keep `InpRequireDemoAccount=true`
- keep `InpEnableDemoOrders=true` only on demo account

After the demo probe, restore Stage134:

- `InpRuleStateKvFile = xauusd_stage133_unified_observer_rule_state_kv.csv`
