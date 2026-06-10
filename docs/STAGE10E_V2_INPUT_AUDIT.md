# Stage 10E v2 Input Audit

Stage 10E v1 could silently produce `no_effect` if the Stage 10C numeric shock file was missing.

That happened when a Stage 10B artifact containing only GDELT/scheduled files was copied into local repo after Stage 10C had previously generated numeric events.

v2 adds explicit input audit.

## Critical check

The report now shows:

```text
numeric_events_loaded
gdelt_events_loaded
guard_events_loaded
numeric_guard_events_loaded
```

If:

```text
numeric_guard_events_loaded = 0
```

then yield-guard simulation is invalid and Stage 10C must be rerun before Stage 10E.

## Correct run order after copying Stage 10B artifact

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage10c_numeric_shock_event_backfill
python3 -m app.stage10a_event_impact_lab
python3 -m app.stage10d_event_impact_validation_lab
python3 -m app.stage10e_event_aware_guard_simulation
```

## Run Stage 10E

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage10e_event_aware_guard_simulation
cat data/reports/stage10e_event_aware_guard_simulation/stage10e_event_aware_guard_simulation.md
```

## Outputs

```text
data/reports/stage10e_event_aware_guard_simulation/stage10e_event_aware_guard_simulation.md
data/reports/stage10e_event_aware_guard_simulation/stage10e_input_audit.json
data/reports/stage10e_event_aware_guard_simulation/stage10e_guard_policy_simulation.csv
data/reports/stage10e_event_aware_guard_simulation/stage10e_candidate_trades_event_annotated.csv
data/reports/stage10e_event_aware_guard_simulation/stage10e_recent_event_dashboard.csv
```

## Hard rule

Simulation/report only. No EA change, no automatic news trading.
