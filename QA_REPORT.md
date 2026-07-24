# QA Report — Bounded Demo Risk Source Provenance Repair

Program: `XAUUSD_BOUNDED_DEMO_DESIGN_V1_1_RISK_SOURCE_PROVENANCE_REPAIR_NO_ORDER`

## Defect reproduced

The real `commercial_closure_risk_contract.json` does not contain
`observed_entry_spread_guard_bps`. V1 incorrectly required that key and failed:

`commercial risk contract mismatch: ['observed_entry_spread_guard_bps']`

## Source ownership repair

- Commercial risk contract remains authoritative for sizing and loss limits.
- `commercial_closure_summary.observed_spread_p95_bps` is authoritative for the
  observed entry spread guard.
- The same value must also match Replay V7 `locked_contract` and the
  controlled-paper runtime risk contract.
- If a future commercial risk contract includes the optional spread field, it
  must also match; a conflicting value fails closed.
- The legacy risk-contract decision is recorded but is not used as order
  authorization. Authorization remains sourced from the later V7 event-aware
  replay decision. Demo/live orders remain forbidden.

## Tests

- Python compilation: PASS
- Bounded-demo tests: 8/8 PASS
- Exact real risk-contract shape without spread field: PASS
- Commercial-summary spread mismatch fail-closed: PASS
- Optional risk spread mismatch fail-closed: PASS
- Risk file vs embedded commercial-summary risk parity: PASS
- Calendar-horizon fail-closed regression: PASS
- Event-summary hash-link regression: PASS
- Broker/order dependency scan: PASS

## Safety

- `broker_order_allowed = false`
- `demo_order_allowed = false`
- `live_order_allowed = false`
- No broker API, MT5 sender, credential loader, or order adapter added.
