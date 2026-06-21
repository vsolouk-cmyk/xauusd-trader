# Stage59 Context-Forward Gates — Design

Stage59 evaluates only true-forward evidence produced by Stage58B. It is intentionally a gate/report stage: it does not scan historical data, does not place orders, does not connect to a broker, and does not authorize EA, paper-live, or live trading.

## Inputs

- `data/shadow/stage58b_context_forward_shadow.sqlite`
- `reports/stage58_context_forward_shadow/stage58b_context_forward_shadow_summary.json`
- `reports/stage58_context_aware_stage51/stage58a_context_aware_stage51_regime_audit_candidates.csv`
- `configs/stage59_context_forward_gates.json`

## Gate intent

The gates require minimum true-forward sample size, minimum evaluated evidence, sufficient span, positive stress-adjusted mean and median, acceptable win rate, no backfill contamination, and no excessive concentration by candidate or day.

Historical Stage58A results are not forward evidence. They are used only to identify which context-aware candidates Stage58B is allowed to monitor.
