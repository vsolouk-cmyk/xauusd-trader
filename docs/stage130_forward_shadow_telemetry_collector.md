# Stage130 forward shadow telemetry collector

Purpose: collect market-open forward-shadow telemetry snapshots from `MQL5/Files`.

This package does not:
- send orders
- modify EA logic
- modify indicator layout
- connect to broker APIs
- promote Rule8 or Rule9

It reads KV/status CSV files produced by prior observer/indicator/report stages and appends snapshot rows to:

`data/forward_shadow_telemetry/stage130_market_open_shadow_snapshots.csv`

The collector can be run once or in a short polling loop during market hours.
