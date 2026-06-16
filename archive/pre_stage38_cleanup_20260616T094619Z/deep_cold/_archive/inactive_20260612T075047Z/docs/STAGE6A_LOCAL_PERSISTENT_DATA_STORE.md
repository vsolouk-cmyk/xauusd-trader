# Stage 6A Local Persistent Data Store

This stage persists local broker/reference evidence into SQLite.

## What it imports

- AMarkets/MT5 H1 CSV
- AMarkets/MT5 M1 CSV
- MT5 EA dry-run signal CSV
- Stage 5C live dry-run outcome CSV
- Optional Twelve Data H1/M1 fetch into the same SQLite database

## Default DB

```text
data/local/xauusd_local_store.sqlite
```

## Run without Twelve Data

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage6a_local_data_store
cat data/reports/stage6a_local_store/stage6a_local_store.md
```

## Run with Twelve Data fetch

Requires the environment variable:

```bash
export TWELVE_DATA_API_KEY='YOUR_KEY_HERE'
python3 -m app.stage6a_local_data_store --fetch-twelve
cat data/reports/stage6a_local_store/stage6a_local_store.md
```

## Important architecture rule

- AMarkets/MT5 is the execution source of truth.
- Twelve Data is a reference/secondary source unless later explicitly validated for execution use.
- This stage does not send orders and does not authorize demo, paper, or live trading.
- The SQLite database is local operational evidence and should not be pushed to GitHub.
