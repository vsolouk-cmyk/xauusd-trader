# Stage26C DB-First Failure/Reversal Discovery Patch

Adds `app.stage26c_db_first_failure_reversal_discovery`.

Hard rules:
- Research/shadow discovery only.
- No EA, paper, live, or order authorization.
- DB-first via the validated Stage25C loader.
- CSV fallback is disabled.
- Stage18A, Stage23D, and Stage25D are unchanged.

Run:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage26c_db_first_failure_reversal_discovery
cat data/reports/stage26c_db_first_failure_reversal_discovery/stage26c_db_first_failure_reversal_discovery.md
```
