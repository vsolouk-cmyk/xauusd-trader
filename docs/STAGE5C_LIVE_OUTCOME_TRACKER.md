# Stage 5C Live Dry-run Outcome Tracker

Resolve Stage 5A live dry-run signals with AMarkets M1 data.

Run:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage5c_live_outcome_tracker
cat data/reports/stage5c_live_outcome_tracker/stage5c_live_outcome_tracker.md
```

If the latest M1 export does not cover the signal plus 12-hour horizon, the signal remains open/unresolved.

Hard rule: dry-run outcome resolution only. No demo/paper/live authorization.
