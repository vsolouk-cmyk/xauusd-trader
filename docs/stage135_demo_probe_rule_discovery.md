# Stage135 Demo Probe Rule Discovery

This stage implements the execution-first loop. If Stage134 is armed but current observer rules are inactive, Stage135 quickly returns to thesis/rule discovery and writes a Stage134-compatible demo-probe KV when a current-active validated candidate exists.

Stage135 itself sends no orders.

Manual Stage134 inputs for a selected probe:

- `InpRuleStateKvFile = xauusd_stage135_demo_probe_rule_state_kv.csv`
- `InpAllowedRules = <selected_rule_id from Stage135 summary>`
- keep `InpRequireDemoAccount=true`
- keep `InpEnableDemoOrders=true` only on demo account

Restore after probe:

- `InpRuleStateKvFile = xauusd_stage133_unified_observer_rule_state_kv.csv`
