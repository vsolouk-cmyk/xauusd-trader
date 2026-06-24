# Persistent Data Store

## Why

The old Stage 2 workflow requested 5000 candles for 4 intervals on repeated runs. That wastes Twelve Data credits and increases runtime.

The project now uses a rolling persistent store under:

```text
data/store
```

## Store files

```text
data/store/store_XAU_USD_1min.csv
data/store/store_XAU_USD_5min.csv
data/store/store_XAU_USD_15min.csv
data/store/store_XAU_USD_1h.csv
data/store/manifest.json
```

## Policy

- Bootstrap: fetch latest 5000 rows if a store file does not exist.
- Incremental refresh: fetch rows from a few candles before the last stored timestamp, then deduplicate.
- Refresh only if the latest stored candle is older than 90 minutes.
- Keep at most 20000 rows per interval to avoid repository bloat.

## Local commands

Initial or incremental refresh:

```bash
cd ~/Desktop/xauusd-trader
export TWELVEDATA_API_KEY='PASTE_KEY_HERE'
python3 -m app.xauusd_store_refresh
```

Force refresh:

```bash
python3 -m app.xauusd_store_refresh --force-refresh
```

Run Stage 2D from the persistent store:

```bash
python3 -m app.xauusd_stage2d_grid_lab
```

## GitHub workflows

Manual/scheduled data store refresh:

```text
XAUUSD Persistent Data Store Refresh
```

Baseline evaluation using the persistent store:

```text
XAUUSD Stage 2D Baseline Grid Lab
```

## Important

The data store is research data, not execution data. It still lacks broker bid/ask spread and must later be validated against MT5/broker feed.
