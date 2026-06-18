# Stage47B LoaderFix1 — path autodiscovery and timeframe normalization

## Status

```text
stage = Stage47B_LOADERFIX1_PATH_AUTODISCOVERY
status = IMPLEMENTATION_READY_NO_PROMOTION
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
next_allowed_step = RUN_STAGE47B_SCAN_ON_REPO_DATA_WITH_AUTODISCOVERY
```

## Why this hotfix exists

The first Stage47B workflow defaulted to `state/xauusd.db`, but the project tree shows the active local SQLite stores are under:

```text
data/local/xauusd_local_store.sqlite
data/store/xauusd.sqlite
```

The project also contains normalized CSV candles under:

```text
data/normalized/normalized_twelvedata_XAU_USD_5min_*.csv
```

Therefore the scanner should not assume a single `state/xauusd.db` database.

## Changes

- Added project source auto-discovery when neither `--db` nor `--csv` is supplied.
- Discovery order:
  1. `data/local/xauusd_local_store.sqlite`
  2. `data/store/xauusd.sqlite`
  3. legacy `state/xauusd.db` / `state/xauusd.sqlite`
  4. fallback to latest matching `data/normalized/*.csv`
- Expanded SQLite/CSV column aliases for timestamp and OHLC fields.
- Fixed timeframe normalization so `M5`, `5min`, `5M`, and `5` map to the same value.
- Updated GitHub Actions inputs: `db_path` and `csv_path` are now optional and empty by default.
- Preserved `NO_DATA_STOP_NO_PROMOTION` behavior instead of crashing.

## Recommended local run

```bash
python3 app/stage47b_liquidity_sweep_reversal_scan.py \
  --timeframe M5 \
  --out reports/stage47b
```

## Explicit local alternatives

```bash
python3 app/stage47b_liquidity_sweep_reversal_scan.py \
  --db data/local/xauusd_local_store.sqlite \
  --timeframe M5 \
  --out reports/stage47b
```

```bash
python3 app/stage47b_liquidity_sweep_reversal_scan.py \
  --db data/store/xauusd.sqlite \
  --timeframe M5 \
  --out reports/stage47b
```

```bash
python3 app/stage47b_liquidity_sweep_reversal_scan.py \
  --csv "$(ls -t data/normalized/normalized_twelvedata_XAU_USD_5min_*.csv | head -1)" \
  --timeframe M5 \
  --out reports/stage47b
```

## GitHub workflow

Run from GitHub UI:

```text
Stage47B Liquidity Sweep Reversal Scan
```

Leave `db_path` and `csv_path` empty first so the workflow uses auto-discovery. If GitHub Actions does not have the local SQLite data committed, run locally instead and commit the generated reports.

## Promotion boundary

This hotfix only repairs loading and source selection. It does not promote Stage47B, does not authorize paper/live, and does not relax any Stage46 archive prohibition.
