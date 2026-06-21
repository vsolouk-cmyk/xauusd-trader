# Stage61D2 Fresh Tiny Demo Order Signal

- status: `FRESH_TINY_DEMO_SIGNAL_READY_NO_PROMOTION`
- decision: `COPY_FRESH_SIGNAL_TO_MT5_FILES_AND_USE_ORDER_HARNESS_NOT_TELEMETRY`
- next_allowed_step: `MT5_TINY_DEMO_ORDER_TEST_WITH_STAGE61_DEMOEXECUTIONHARNESS_ALLOWTRADING_TRUE`
- promotion: `NO_GO`
- paper_live: `NO_GO`
- live: `NO_GO`

## Critical separation

For the actual tiny demo order test, attach `Stage61_DemoExecutionHarness`, not `Stage61_DemoExecutionHarness_Telemetry`. The telemetry EA intentionally never sends orders.

## Signal file

- generated: `/Users/vahid/Desktop/xauusd-trader/reports/stage61_demo_tiny_order/mt5_files/stage61_demo_signals.csv`
- destination file name in MT5 `MQL5/Files`: `stage61_demo_signals.csv`
- signal_id: `S61D2_TINY_DEMO_20260621T120220Z`
- expires_utc: `2026-06-21T16:02:20Z`
- lot: `0.01`

## MT5 settings for tiny demo order

- EA: `Stage61_DemoExecutionHarness`
- Account: AMarkets demo only
- `RequireDemoAccount=true`
- `AllowTrading=true` only for this tiny demo order test
- `FixedLot=0.01`
- `MaxOpenPositions=1`
- `MaxOrdersPerDay=1`

Immediately after the test, set `AllowTrading=false` again.
