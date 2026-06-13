# Stage31A External/Macro/News Feature Ingestion

Stage31A is a research/shadow-only data engineering stage. It does **not** create signals, orders, EA changes, paper trades, or live authorization.

Purpose:

1. Read the Stage30A ML-ready candidate pool.
2. Look for manually supplied exogenous CSV files under `data/exogenous/`.
3. Create templates when files are missing.
4. Join exogenous features using backward/as-of joins only.
5. Export `stage31a_exogenous_ml_dataset.csv` for Stage31B.

Expected optional files:

- `data/exogenous/dxy.csv`
- `data/exogenous/us10y.csv`
- `data/exogenous/real_yield.csv`
- `data/exogenous/vix.csv`
- `data/exogenous/spx.csv`
- `data/exogenous/oil.csv`
- `data/exogenous/calendar_events.csv`

Numeric source format:

```csv
timestamp,close
2026-01-01T00:00:00Z,100.0
2026-01-02T00:00:00Z,100.5
```

Calendar source format:

```csv
timestamp,event,importance,currency
2026-01-01T13:30:00Z,example_cpi_or_fomc_or_nfp,high,USD
```

Run:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage31a_exogenous_feature_ingestion
cat data/reports/stage31a_exogenous_feature_ingestion/stage31a_exogenous_feature_ingestion.md
```
