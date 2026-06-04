# xauusd-trader

Commercial XAUUSD/gold trading research pipeline.

## Current stage

Stage 2D: fast vectorized baseline grid lab using a persistent SQLite data store.

Telegram notification is enabled for pipeline reports only.

No ML. No trading bot. No paper order. No live order.

## Key definitions

- XAUUSD: spot gold quoted in US dollars.
- SQLite: a small SQL database stored as a single local file.
- Workflow chain: one GitHub Actions workflow starts after another workflow completes.
- `workflow_run`: GitHub Actions event that runs a workflow after another named workflow completes.
- Baseline: a simple rule-based strategy used as the minimum benchmark before ML.
- Grid lab: controlled testing of simple baseline parameter combinations.
- Vectorized calculation: operating on arrays instead of slow row-by-row Python objects.

## Current data architecture

Persistent database:

```text
data/store/xauusd.sqlite
data/store/manifest.json
```

## Local refresh

```bash
cd ~/Desktop/xauusd-trader
export TWELVEDATA_API_KEY='PASTE_KEY_HERE'
python3 -m app.xauusd_store_refresh
```

## Local fast Stage 2D

```bash
python3 -m app.xauusd_stage2d_grid_lab --data-db data/store/xauusd.sqlite
```

For debug with full trades:

```bash
python3 -m app.xauusd_stage2d_grid_lab --data-db data/store/xauusd.sqlite --save-full-trades
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
