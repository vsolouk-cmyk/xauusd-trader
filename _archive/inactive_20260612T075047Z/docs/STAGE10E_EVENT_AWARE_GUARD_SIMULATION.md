# Stage 10E Event-Aware Guard / Report Simulation

Stage 10E tests whether event classes validated in Stage 10D can improve the selected technical candidate as a guard/report layer.

It does not modify the EA and does not authorize orders.

## Current default rules

```text
front_end_yield_shock      directional_or_guard_candidate
nominal_yield_shock        directional_or_guard_candidate
central_bank_gold_demand   monitoring_only
```

The first two came from Stage 10D numeric validation.

`central_bank_gold_demand` is kept as monitoring only because GDELT currently has too few independent clusters.

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage10e_event_aware_guard_simulation
cat data/reports/stage10e_event_aware_guard_simulation/stage10e_event_aware_guard_simulation.md
```

## Outputs

```text
data/reports/stage10e_event_aware_guard_simulation/stage10e_event_aware_guard_simulation.md
data/reports/stage10e_event_aware_guard_simulation/stage10e_candidate_trades_event_annotated.csv
data/reports/stage10e_event_aware_guard_simulation/stage10e_guard_policy_simulation.csv
data/reports/stage10e_event_aware_guard_simulation/stage10e_recent_event_dashboard.csv
data/reports/stage10e_event_aware_guard_simulation/stage10e_event_aware_guard_simulation.json
```

## What it simulates

Policy examples:

```text
baseline_all_trades
block_any_validated_yield_event_window
block_hostile_yield_event_window_only
take_only_supportive_yield_event_window
take_only_no_validated_event_window
```

A guard is useful only if it improves PF/drawdown without destroying trade count.

## Hard rule

Simulation/report only. No EA change, no automatic news trading, no paper/live authorization.
