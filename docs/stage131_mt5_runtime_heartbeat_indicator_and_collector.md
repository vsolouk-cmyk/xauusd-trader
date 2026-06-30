# Stage131 MT5 runtime heartbeat indicator and collector

Stage130 showed stale KV/status files. Stage130B found MT5 logs but no relevant runtime journal events. Stage131 adds a minimal, telemetry-only heartbeat indicator to confirm that MT5/chart runtime itself can write fresh files into `MQL5/Files`.

This package does not:
- modify the Unified Observer EA
- send or prepare orders
- connect to any broker API
- change indicator overlay layout
- promote Rule8 or Rule9

The indicator writes:
- `xauusd_stage131_runtime_heartbeat_kv.csv`
- `xauusd_stage131_runtime_heartbeat_history.csv`

If Stage131 heartbeat is fresh but Rule8/Rule9/observer files stay stale, the next controlled patch should add telemetry-only writer instrumentation to the existing observer EA.
