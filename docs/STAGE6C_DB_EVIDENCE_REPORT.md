# Stage 6C DB Evidence Report

Stage 6C reads the local SQLite evidence store and produces a decision-oriented report.

## What it checks

- DB table counts
- Bars by source/timeframe
- Latest import runs
- Recent dry-run signals
- Recent dry-run outcomes
- Signal/outcome join
- Outcome summary by session and reason
- Live-only `no_asia` counterfactual

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage6c_db_evidence_report
cat data/reports/stage6c_db_evidence_report/stage6c_db_evidence_report.md
```

## Important

- Read-only.
- Does not import CSV.
- Does not send orders.
- Does not authorize demo/paper/live.
- Use this after Stage 6B has updated the local SQLite store.
