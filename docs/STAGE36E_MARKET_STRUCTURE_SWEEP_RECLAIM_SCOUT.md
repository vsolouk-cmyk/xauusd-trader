# STAGE36E — Market Structure Sweep / Reclaim Scout

Research-only scout for the next Stage36 thesis branch.

Purpose:
- Test prior-day high/low sweep and reclaim/continuation behavior.
- Test rolling 12/24/48-hour swing sweep/reclaim behavior.
- Use H1 XAUUSD OHLC from the local SQLite `bars` table.
- Produce strict review, background, and kill/repair queues.

Execution authorization:
- No EA change.
- No paper-live.
- No order authorization.
- A positive result only authorizes a stricter research review.

Main command:

```bash
python3 -m app.stage36e_market_structure_sweep_reclaim_scout
```

Primary outputs:
- `data/reports/stage36e_market_structure_sweep_reclaim_scout/stage36e_market_structure_sweep_reclaim_scout.md`
- `data/reports/stage36e_market_structure_sweep_reclaim_scout/stage36e_summary.json`
- `data/reports/stage36e_market_structure_sweep_reclaim_scout/stage36e_candidate_summary.csv`
- `data/reports/stage36e_market_structure_sweep_reclaim_scout/stage36e_strict_review_queue.csv`
- `data/reports/stage36e_market_structure_sweep_reclaim_scout/stage36e_background_queue.csv`
- `data/reports/stage36e_market_structure_sweep_reclaim_scout/stage36e_kill_or_repair_queue.csv`
