# Stage157 Global Gate Safe Router

Stage157 hardens the existing Stage155 risk-guarded active router. It preserves the existing Stage134-compatible KV filename:

`xauusd_stage155_m5_active_router_rule_state_kv.csv`

This is deliberate: Stage134 can keep the same `InpRuleStateKvFile`, while Stage156 continues to run the same router command. The behavior changes only when Stage145's aggregate clean-ledger gate says the demo loop has negative expectancy and should freeze/repair.

## Why

Stage155 blocks demo-negative families, but after the latest clean ledger Stage145 reports:

- `gate_decision = STAGE145_FREEZE_REPAIR_RULE_NEGATIVE_EXPECTANCY`
- `recommended_action = FREEZE_CURRENT_RULE_AND_REPAIR_DISCOVERY`
- `severity = HIGH`

Continuing to route into untested families after this aggregate gate risks family-hopping and operational overfit. Stage157 adds a global circuit breaker.

## Behavior

If Stage145 aggregate performance is frozen after at least `--min-global-gate-trades` closed trades, Stage157 writes:

- `any_signal_active=false`
- `active_rule_count=0`
- `decision=STAGE157_GLOBAL_PERFORMANCE_FREEZE_NO_ORDER`
- `global_gate_freeze_active=true`

No orders are sent by this script. Stage134 will also not open a new order because the KV contains no active signal.

If the global gate is not frozen, Stage157 behaves like Stage155:

- reads Stage150/150B cached candidate scores,
- blocks demo-negative families from Stage145,
- selects the best currently active PASS candidate,
- writes the Stage134-compatible KV.

## Operator notes

Keep Stage134 on:

`InpRuleStateKvFile = xauusd_stage155_m5_active_router_rule_state_kv.csv`

Keep:

`InpAllowedRules = all`

Do not disable the global freeze guard unless this is a deliberate diagnostic run. The flag is:

`--disable-global-freeze-guard`

## Repair direction

When the global freeze guard is active, the next commercial step is not to continue demo orders. The next step is discovery repair: re-score the M5/M15 candidate universe with stricter out-of-sample/tail/session/event filters or move the active route to a higher-timeframe/macro-confirmed thesis.
