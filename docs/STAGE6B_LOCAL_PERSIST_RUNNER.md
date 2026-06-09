# Stage 6B Local Persist Runner

This is the daily/local one-command flow after exporting fresh AMarkets CSV files.

It runs:

1. Stage data file audit
2. Stage 5B dry-run signal validator
3. Stage 5C dry-run outcome tracker
4. Stage 6A local SQLite import

## Run without Twelve Data

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage6b_persist_runner
cat data/reports/stage6b_persist_runner/stage6b_persist_runner.md
cat data/reports/stage6a_local_store/stage6a_local_store.md
```

## Run with Twelve Data attempt

```bash
export TWELVE_DATA_API_KEY='REAL_KEY'
python3 -m app.stage6b_persist_runner --fetch-twelve
```

## Important

- This updates only the local SQLite evidence store.
- It does not place orders.
- It does not authorize demo/paper/live.
- AMarkets/MT5 remains the execution source of truth.
