# XAUUSD bounded demo design runbook

## Boundary

This package freezes and preflights a demo design. It contains no MT5 API, broker API, order sender, EA, arming switch, credential loader, or live path.

## Commands

```bash
python3 app/xauusd_bounded_demo_design.py design --root .
python3 app/xauusd_bounded_demo_design.py preflight --root .
```

## Pass decisions

- `PASS_BOUNDED_DEMO_DESIGN_NO_ORDER_PATH`
- `PASS_BOUNDED_DEMO_OPERATIONAL_PREFLIGHT_NO_ORDER_PATH`

Both decisions keep `demo_order_allowed=false`.

## Frozen design

- Bidirectional probability tails: LONG >= 0.60, SHORT <= 0.40.
- Entry at aligned H1 row i+1 open.
- Exit at aligned H1 row i+24 close.
- Stage115 official scheduled USD event calendar, ±60 minutes.
- One concurrent position and one new position per day.
- Initial demo exposure is 25% of the validated notional/equity ceiling.
- Weekly pause 2%; hard drawdown kill 8%.
- The bounded window is 30 calendar days or 10 resolved positions, whichever occurs first.
- This window tests execution plumbing and guards, not model reselection.

## Failure handling

Any evidence hash mismatch, incomplete event calendar through the exit horizon, risk-contract mismatch, or stale/incorrect program version fails closed. Do not weaken thresholds to make preflight pass.

## V1.1 spread-guard provenance

The real Commercial Closure risk-contract JSON does not contain
`observed_entry_spread_guard_bps`. Operational preflight validates that value
against `commercial_closure_summary.observed_spread_p95_bps`, Replay V7, and
the controlled-paper runtime contract. Absence from the risk-contract JSON is
valid; disagreement across authoritative sources is blocking.
