# Stage61D2 Fresh Tiny Demo Order Signal Hotfix

This hotfix separates the telemetry parse-test EA from the actual tiny demo order harness and regenerates a fresh one-row signal with a longer TTL. The telemetry EA intentionally never sends orders, even if `AllowTrading=true`.

Use `Stage61_DemoExecutionHarness` for the tiny demo order test, not `Stage61_DemoExecutionHarness_Telemetry`.

No promotion, paper-live, live trading, or unrestricted order submission is authorized.
