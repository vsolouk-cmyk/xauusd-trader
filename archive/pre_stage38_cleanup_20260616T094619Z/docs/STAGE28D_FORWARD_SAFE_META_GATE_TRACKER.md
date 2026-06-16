# Stage28D Forward-Safe Meta-Gate Tracker

Research/shadow-only forward tracker for the Stage28C validated meta-gate around the canonical Stage23/25 lineage.

Primary gate:

- `london_range >= prior-event q60(london_range)`
- `prior_day_range >= prior-event q25(prior_day_range)`

Both thresholds are expanding and computed only from earlier canonical candidate events. No full-sample/static threshold is used for forward tracking.

Run:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage28d_forward_safe_meta_gate_tracker
cat data/reports/stage28d_forward_safe_meta_gate_tracker/stage28d_forward_safe_meta_gate_tracker.md
```

This module does not change Stage18A, Stage23D, Stage25D, Stage27D, EA, paper/live mode, or orders.
