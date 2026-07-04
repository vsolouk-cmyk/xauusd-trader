# Stage146C Demo Frequency Unblocker for Stage134

This patch addresses the current low-frequency blocker.

Observed problem:
- Stage138 can select a new rule ID after refresh.
- Stage134 still has a static `InpAllowedRules` list/input.
- If the selected Stage138 rule is not in the EA input list, Stage134 holds instead of entering demo.

Patch:
- `InpAllowedRules` default becomes `*`.
- `*`, blank, `ANY`, or `ALL` allow the currently selected Stage138 rule.
- `InpMaxSignalAgeSec` default becomes 7200.
- `InpMinSecondsBetweenOrderAttempts` default becomes 60.

Unchanged safety guards:
- demo-account requirement remains.
- no real-account permission is added.
- max open positions remains.
- spread guard remains.
- SL/TP remain.
- duplicate `feature_date|rule_id` guard remains.

Operational use:
- Compile and replace the Stage134 EA.
- On the Stage134 chart, set `InpAllowedRules=*`.
- Keep `InpRuleStateKvFile=xauusd_stage138_technical_rule_state_kv.csv`.
- Keep `InpEnableDemoOrders=true` only on demo.
