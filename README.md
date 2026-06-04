# xauusd-trader

Commercial XAUUSD/gold trading research pipeline.

## Current stage

Stage 2D with a persistent rolling data store.

No ML. No trading bot. No paper order. No live order.

## Key definitions

- XAUUSD: spot gold quoted in US dollars.
- Candle: one OHLC bar for a fixed time period.
- OHLCV: open, high, low, close, volume.
- Spread: ask minus bid; direct trading cost.
- Baseline: a simple rule-based strategy used as the minimum benchmark before ML.
- Data store: persistent CSV files saved in the repo and updated incrementally.
- Incremental refresh: fetching only data after the latest stored candle, with a small overlap and deduplication.
- Snapshot: a saved batch of market data and reports at one point in time.
- Interval/timeframe: candle duration, such as 1 minute or 1 hour.
- SMA: simple moving average.
- Drawdown: decline from the previous cumulative peak.
- Net USD: raw price movement minus assumed trading cost.
- Grid lab: controlled testing of simple baseline parameter combinations.
- Train/test split: first time segment for initial evaluation, later time segment for validation.

## Current data source decision

Use Twelve Data REST for Stage 0/1/2 because it is faster and cleaner than broker onboarding.

OANDA is paused. MT5/broker feed validation comes later.

## Local persistent store refresh

```bash
cd ~/Desktop/xauusd-trader
export TWELVEDATA_API_KEY='PASTE_KEY_HERE'
python3 -m app.xauusd_store_refresh
```

## Local Stage 2D

```bash
python3 -m app.xauusd_stage2d_grid_lab
```

## GitHub Actions secrets

```text
TWELVEDATA_API_KEY
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

Run manually from GitHub UI:

```text
XAUUSD Persistent Data Store Refresh
XAUUSD Stage 2D Baseline Grid Lab
```

Recommended Stage 2D inputs:

```text
refresh_store: true
force_refresh: false
include_run_link: false
```

## Hard rule

If no simple baseline variant survives Stage 2D/next validation, do not proceed to ML.

Telegram messages are reports only, not signals.
