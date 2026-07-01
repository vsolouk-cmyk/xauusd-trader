# Stage138 Broker Technical Demo Discovery

Stage137 proved the current live macro signal file has no numeric live keys usable for broad discovery.
Stage138 switches to broker technical discovery using AMarkets bars.

Purpose:
- keep Stage134 demo executor armed,
- generate a current-active technical candidate if historical validation/tail gates pass,
- write a Stage134-compatible KV file.

Stage138 itself does not send orders.

Default output:
- `xauusd_stage138_technical_rule_state_kv.csv`

If selected:
- `InpRuleStateKvFile = xauusd_stage138_technical_rule_state_kv.csv`
- `InpAllowedRules = <selected_rule_id>`
- keep `InpRequireDemoAccount=true`
- keep `InpEnableDemoOrders=true` only on demo account

After probe:
- restore `InpRuleStateKvFile = xauusd_stage133_unified_observer_rule_state_kv.csv`
