# Stage147 P0 Execution Hardening and Stage145B Family Gate

This package implements the first agile corrections extracted from the external review.

## External review points addressed

P0-1: Stage134 must not let retcode `10018` market-closed rejections become a successful duplicate blocker.

P0-2: `InpMaxHoldMinutes=60` is inconsistent with H1 signal logic. The default is moved to 240 minutes.

P1-1: Stage145 aggregate metrics are not sufficient. Stage145B adds per-family metrics and a clustering alert.

## Files changed

- `mql5/Experts/Advisors/XAUUSD/XAUUSD_Stage134_DemoExecutorPilot_EA.mq5`
- `app/stage145_clean_ledger_performance_gate.py`
- `configs/stage147_p0_execution_hardening_and_family_gate.json`
- `docs/stage147_p0_execution_hardening_and_family_gate.md`
- tests under `tests/`

## Operational stance

This is not a real/live promotion. It only hardens the demo execution stack.

Stage134 remains demo-only and still requires:

- `InpRequireDemoAccount=true`
- `InpEnableDemoOrders=true` only on demo
- fixed small lot
- max open positions guard

## Next implementation after this package

The next agile package should address Stage138 contamination testing and/or ATR-based SL/TP, depending on the first market-open replacement order result.
