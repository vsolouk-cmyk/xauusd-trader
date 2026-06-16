# Stage32F — Extended Dense Shadow Refresh Cycle

Stage32F is a focused operational cycle for the current fast commercial path.

It should be run after each AMarkets/FRED data refresh when the goal is not broad discovery, but collecting enough forward-observable samples for the current dense leading candidate.

Default command:

```bash
python3 -m app.stage32f_extended_shadow_refresh_cycle
```

If the AMarkets CSV files have just been placed and you want import + observation + Stage32C/D/E in one command:

```bash
python3 -m app.stage32f_extended_shadow_refresh_cycle --run-active-wrapper
```

Outputs:

```text
data/reports/stage32f_extended_shadow_refresh_cycle/stage32f_extended_shadow_refresh_cycle.md
data/reports/stage32f_extended_shadow_refresh_cycle/stage32f_summary.json
data/reports/stage32f_extended_shadow_refresh_cycle/focus_status.csv
data/reports/stage32f_extended_shadow_refresh_cycle/module_runs.csv
```

Safety:

```text
Research/shadow only.
No EA change.
No paper/live.
No order authorization.
```
