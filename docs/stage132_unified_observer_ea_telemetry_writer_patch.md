# Stage132 Unified Observer EA telemetry writer patch

Stage131 confirmed MT5 runtime is alive, while observer/Rule8/Rule9 files remained stale.
Stage132 adds a telemetry-only writer to the existing Unified Observer EA source.

This package does not:
- add `OrderSend`
- add `CTrade`
- change signal rules
- change trading logic
- change indicator UI
- open paper/live/live paths

The injected MQL5 code writes:
- `xauusd_stage132_unified_observer_ea_heartbeat_kv.csv`
- `xauusd_stage132_unified_observer_ea_heartbeat_history.csv`

Use `--patch-source --write-mt5-ea` to patch the located source and copy it to the configured MT5 Experts directory.
Then compile the patched EA in MetaEditor and reload/reattach it on the XAUUSD,H1 chart.

After reload, run Stage132 again without `--patch-source` to confirm fresh EA heartbeat.
