# Stage 10D Event Impact Validation Lab

Stage 10A showed that numeric shock events often coincide with large XAUUSD moves.

That is useful, but not enough. The event set was selected from shock days, so it must be tested against matched non-event control windows.

Stage 10D adds two protections:

```text
1. De-clustering
2. Matched controls
```

## Why de-clustering

Numeric shocks can appear on consecutive days during the same macro regime. Counting every day as a separate independent event exaggerates evidence.

Default:

```text
min_gap_hours = 48
```

per `(event_class, event_channel)`.

## Matched controls

For each de-clustered event, the lab samples same weekday/hour windows from nearby weeks, excluding event dates.

Default:

```text
controls_per_event = 4
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage10d_event_impact_validation_lab
cat data/reports/stage10d_event_impact_validation_lab/stage10d_event_impact_validation_lab.md
```

## Outputs

```text
data/reports/stage10d_event_impact_validation_lab/stage10d_event_impact_validation_lab.md
data/reports/stage10d_event_impact_validation_lab/stage10d_event_class_validation_summary.csv
data/reports/stage10d_event_impact_validation_lab/stage10d_event_controls.csv
data/reports/stage10d_event_impact_validation_lab/stage10d_events_declustered.csv
data/reports/stage10d_event_impact_validation_lab/stage10d_event_impact_validation_lab.json
```

SQLite table:

```text
event_impact_validation_summary
```

## Decision

If an event class survives Stage 10D, it can move to Stage 10E as a report/guard simulation.

No EA change, no automatic news trading, no paper/live authorization.
