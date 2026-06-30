# Stage133B CSV delimiter and parser hotfix

Stage133 rule-state telemetry was operational, but the MT5 `FILE_CSV` writer produced tab-separated rows when no delimiter was specified.

Fixes:
- Stage133 injected MQL5 writer now passes explicit comma delimiter to `FileOpen(..., FILE_CSV, ',')`.
- Stage133 Python collector now auto-detects comma vs tab delimiter for `xauusd_stage133_unified_observer_rule_state_latest.csv`.
- This makes `latest_active_rows` reliable even if an old tab-separated file is still present.

No order path, trade class, signal rule, selected-rule logic, broker connection, paper-live, or live path is changed.
