# Stage 6B v2 Local Persist + Evidence Runner

Stage 6B v2 is the daily/local one-command flow after exporting fresh AMarkets CSV files.

It runs:

1. Stage data file audit
2. Stage 5B dry-run signal validator
3. Stage 5C dry-run outcome tracker
4. Stage 6A local SQLite import
5. Stage 6C DB evidence report

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage6b_persist_runner
cat data/reports/stage6b_persist_runner/stage6b_persist_runner.md
cat data/reports/stage6c_db_evidence_report/stage6c_db_evidence_report.md
```

## Optional Twelve Data attempt

```bash
export TWELVE_DATA_API_KEY='REAL_KEY'
python3 -m app.stage6b_persist_runner --fetch-twelve
```

## Skip Stage 6C if needed

```bash
python3 -m app.stage6b_persist_runner --skip-6c
```

## Important

- This updates only the local SQLite evidence store during Stage 6A.
- It does not place orders.
- It does not authorize demo/paper/live.
- AMarkets/MT5 remains the execution source of truth.
