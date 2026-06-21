# Stage61D3 EA-Compatible Tiny Demo Signal

- status: `EA_COMPATIBLE_TINY_DEMO_SIGNAL_READY_NO_PROMOTION`
- decision: `COPY_EA_COMPATIBLE_SIGNAL_TO_MT5_FILES_AND_RUN_STAGE61_DEMOEXECUTIONHARNESS`
- promotion: `NO_GO`
- paper_live: `NO_GO`
- live: `NO_GO`

## Why this hotfix exists

The previous Stage61D2 CSV used a 13-column exporter schema. The compiled Stage61_DemoExecutionHarness expects a 16-column execution schema, so it read `lot` as `side` and printed `unsupported side ... 0.01`. This hotfix writes the exact 16-column schema consumed by the EA.

## Signal file

- generated: `/Users/vahid/Desktop/xauusd-trader/reports/stage61_demo_tiny_order/mt5_files/stage61_demo_signals.csv`
- destination in MT5 `MQL5/Files`: `stage61_demo_signals.csv`
- signal_id: `S61D3_TINY_DEMO_20260621T123155Z`
- side: `BUY`
- lot: `0.01`
- expiry_utc: `2026-06-21T18:31:55Z`

## MT5 order-test settings

- Detach `Stage61_DemoExecutionHarness_Telemetry`.
- Attach `Stage61_DemoExecutionHarness`.
- `RequireDemoAccount=true`.
- `AllowTrading=true` only for this tiny demo test.
- `FixedLot=0.01`, `MaxOpenPositions=1`, `MaxOrdersPerDay=1`.
- Immediately after the test, set `AllowTrading=false`.
