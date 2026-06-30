# Stage130B MT5 journal and files telemetry audit

Stage130 showed that the KV/status files exist, but most source files are stale. Stage130B adds a no-change runtime audit by scanning MT5 journal/log files plus Stage130 file-freshness output.

This package does not change EA or indicator source.

It reads:
- `reports/stage130_forward_shadow_telemetry_collector/stage130_latest_shadow_snapshot.csv`
- MT5 log directories derived from the configured `MQL5/Files` path

It writes:
- `reports/stage130b_mt5_journal_and_files_telemetry_audit/stage130b_mt5_journal_runtime_events.csv`
- `reports/stage130b_mt5_journal_and_files_telemetry_audit/stage130b_runtime_health_summary.csv`
- `data/forward_shadow_telemetry/stage130b_mt5_journal_runtime_events.csv`

If logs confirm the Unified Observer EA is active while files remain stale, the next controlled step is a telemetry-only writer inside the existing observer EA.
