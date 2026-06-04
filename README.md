# xauusd-trader

Commercial XAUUSD/gold trading research pipeline.

## Current stage

Stage 2D: baseline grid lab using a persistent SQLite data store.

Telegram notification is enabled for pipeline reports only.

No ML. No trading bot. No paper order. No live order.

## Key definitions

- XAUUSD: spot gold quoted in US dollars.
- Candle: one OHLC bar for a fixed time period.
- SQLite: a small SQL database stored as a single local file.
- Primary key: a unique column used to prevent duplicate rows.
- Workflow chain: one GitHub Actions workflow starts after another workflow completes.
- `workflow_run`: GitHub Actions event that runs a workflow after another named workflow completes.
- Baseline: a simple rule-based strategy used as the minimum benchmark before ML.
- Grid lab: controlled testing of simple baseline parameter combinations.

## Current data architecture

Persistent database:

```text
data/store/xauusd.sqlite
data/store/manifest.json
```

Tables:

```text
candles_1min
candles_5min
candles_15min
candles_1h
```

## Local refresh

```bash
cd ~/Desktop/xauusd-trader
export TWELVEDATA_API_KEY='PASTE_KEY_HERE'
python3 -m app.xauusd_store_refresh
```

Run twice. First run should refresh. Second run should usually show `skip_fresh`.

## Local Stage 2D

```bash
python3 -m app.xauusd_stage2d_grid_lab --data-db data/store/xauusd.sqlite
```

## GitHub workflow order

Run manually or let schedule run:

```text
XAUUSD Persistent Data Store Refresh
```

After it completes successfully, GitHub automatically triggers:

```text
XAUUSD Stage 2D Baseline Grid Lab
```

GitHub supports `workflow_run` for running a workflow after another named workflow completes.

## GitHub Actions secrets

```text
TWELVEDATA_API_KEY
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

## Required GitHub setting

```text
Settings → Actions → General → Workflow permissions → Read and write permissions
```

## Hard rule

If no simple baseline variant survives Stage 2D, do not proceed to ML.

Telegram messages are reports only, not signals.
