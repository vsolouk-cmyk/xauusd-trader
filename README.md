# XAUUSD Bounded Demo Risk Source Provenance Repair

This overlay repairs the bounded-demo operational preflight failure caused by
requiring `observed_entry_spread_guard_bps` from the real commercial risk
contract, where that field does not exist.

The spread guard remains mandatory and is tied to its actual source:

- `commercial_closure_summary.observed_spread_p95_bps`
- Replay V7 `locked_contract.observed_entry_spread_guard_bps`
- controlled-paper `risk_contract.observed_entry_spread_guard_bps`

All three values must match exactly within numerical tolerance. The commercial
risk contract continues to govern sizing, concurrent-position, daily-cap,
weekly-pause, and hard-drawdown limits.

## Run

```bash
python3 app/xauusd_bounded_demo_design.py design --root .
python3 app/xauusd_bounded_demo_design.py preflight --root .
```

Expected preflight decision:

`PASS_BOUNDED_DEMO_OPERATIONAL_PREFLIGHT_NO_ORDER_PATH`

No order path is enabled by this package.
