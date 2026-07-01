# Stage134 Demo Executor Pilot

Strategic shift:
- Stop expanding observer-only telemetry.
- Move to demo-live execution to obtain real fill, rejection, spread, slippage, and PnL evidence.
- If demo evidence is negative, return quickly to thesis/rule discovery, fix the rule logic, then move directly back to demo-live execution.

Stage134 is the first order-capable stage, but it is demo-only.

Safety/risk controls:
- `InpRequireDemoAccount=true`
- real account blocked
- `InpEnableDemoOrders=false` by default; must be manually set to true on a demo chart
- max lot default: `0.01`
- max open positions default: `1`
- BUY-only v1
- no martingale
- no averaging
- SL required
- TP required
- time-exit supported
- spread guard
- Stage133 rule-state freshness guard
- duplicate signal guard by `feature_date|selected_rule_id`

Execution rule:
- order can be attempted only if Stage133 says:
  - `any_signal_active=true`
  - `selected_rule_id` is non-empty and allowed
  - rule-state KV is fresh

Outputs in MT5 `MQL5/Files`:
- `xauusd_stage134_demo_executor_status_kv.csv`
- `xauusd_stage134_demo_executor_trade_log.csv`
- `xauusd_stage134_demo_executor_state_kv.csv`
