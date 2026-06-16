# Stage35C Minimal Monitor Runner

Purpose: keep only the surviving Stage35C forward-confirmation monitor alive after pre-Stage38 cleanup.

This runner is deliberately minimal:

- runs AMarkets CSV preflight
- runs the existing Stage32F refresh cycle
- runs Stage35C forward-confirmation trigger queue pruner
- does not run Stage36
- does not run Stage37
- does not run discovery
- does not mine variants
- does not authorize EA, paper-live, or orders

Output state file:

`data/reports/stage35c_minimal_monitor/latest_minimal_monitor_state.env`

Log file:

`data/reports/stage35c_minimal_monitor/stage35c_minimal_monitor.log`

Default behavior:

If Stage35C reaches its required new-event threshold, the runner writes `STAGE35C_ACTION_REQUIRED=true` but does not rerun strict gates automatically.

Optional behavior:

Set `XAUUSD_STAGE35C_AUTO_RERUN_GATES=1` only if manual review accepts automatic rerun of:

- Stage33D strict cost-aware pre-paper gate
- Stage33E short confirmation recency filter
- Stage35B strict variant backtest queue evaluator
- Stage35C trigger queue pruner

Launchd template:

`launchd/com.xauusd.stage35c.minimal.monitor.plist.template`

The template runs every 20 minutes. Install manually only after one manual run succeeds.
