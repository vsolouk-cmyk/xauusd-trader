# Stage152 Stale Signal Hardening

The 2026-07-06 04:43 server-time order used `feature_date=2026-07-03T19:55:00Z`. That exposed a critical bug: Stage134 freshness was based on rule-state file modification time, so a freshly rewritten Stage151 file could make an old Friday signal look fresh.

Stage152 fixes this in two places:

- Stage134 now applies `InpMaxSignalAgeSec` to `feature_date` parsed as UTC.
- Stage151B now writes `any_signal_active=false` if the latest CSV bar itself is stale, even if the locked rule conditions are true.

No real/live trading is authorized.
