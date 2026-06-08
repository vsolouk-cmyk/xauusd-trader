# Stage 5C v2 Live Outcome Tracker

Run:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage5c_live_outcome_tracker
cat data/reports/stage5c_live_outcome_tracker/stage5c_live_outcome_tracker.md
```

Use this after every fresh export of `~/Downloads/amarkets_xauusd_1m.csv`.

Key change:
- The canonical signal time is `signal_closed_h1_time_server` converted by the server UTC offset.
- The misleading `signal_closed_h1_time_gmt_now` field is diagnostic only.
- Multiple signal rows are handled and duplicate rows are skipped by default.

No demo/paper/live authorization.
