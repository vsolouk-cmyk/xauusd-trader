# Stage137 Fuzzy Live Schema Bridge Discovery

Stage136 failed because exact shared numeric features between live `unified_observer_signal.csv` and the historical Stage117 dataset were zero.

Stage137 fixes that by:
- reading the current live MT5 signal file,
- extracting numeric live keys,
- fuzzy-mapping live keys to historical numeric feature columns,
- running broad threshold and pair-condition discovery,
- validating on historical validation/tail segments,
- writing a Stage134-compatible rule-state KV only if a current-active candidate passes.

Stage137 itself does not send orders.

If selected:
- `InpRuleStateKvFile = xauusd_stage137_fuzzy_bridge_rule_state_kv.csv`
- `InpAllowedRules = <selected_rule_id>`

After demo probe:
- restore `InpRuleStateKvFile = xauusd_stage133_unified_observer_rule_state_kv.csv`
