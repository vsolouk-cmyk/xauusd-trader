# xauusd-trader

Commercial XAUUSD/gold trading research pipeline.

## Current stage

Stage 2D: baseline grid lab with cache-aware data collection and slim artifacts.

Telegram notification is enabled for pipeline reports only.

No ML. No trading bot. No paper order. No live order.

## Key definitions

- XAUUSD: spot gold quoted in US dollars.
- Candle: one OHLC bar for a fixed time period.
- OHLCV: open, high, low, close, volume.
- Spread: ask minus bid; direct trading cost.
- Baseline: a simple rule-based strategy used as the minimum benchmark before ML.
- Forward shadow: logging future signals without placing orders.
- Data provider: a service that gives market data but is not necessarily the broker used for execution.
- Snapshot: a saved batch of market data and reports at one point in time.
- Interval/timeframe: candle duration, such as 1 minute or 1 hour.
- SMA: simple moving average.
- Drawdown: decline from the previous cumulative peak.
- Net USD: raw price movement minus assumed trading cost.
- Overlapping trades: trades whose holding periods overlap.
- Non-overlap filter: accepts a new trade only after the previous trade has exited.
- Outlier: an unusually large result that can dominate totals.
- Profit factor: gross wins divided by gross losses.
- Grid lab: controlled testing of simple baseline parameter combinations.
- Train/test split: first time segment for initial evaluation, later time segment for validation.
- Cache: reuse of saved local/GitHub data files to avoid repeated provider calls.

## Current data source decision

Use Twelve Data REST for Stage 0/1/2 because it is faster and cleaner than broker onboarding.

OANDA is paused. MT5/broker feed validation comes later.

## Local Stage 2D sequence

Reuse cached data if available:

```bash
cd ~/Desktop/xauusd-trader
export TWELVEDATA_API_KEY='PASTE_KEY_HERE'
python3 -m app.xauusd_stage1_snapshot --outputsize 5000
python3 -m app.xauusd_stage2d_grid_lab
```

Force fresh provider data:

```bash
python3 -m app.xauusd_stage1_snapshot --outputsize 5000 --force-refresh
python3 -m app.xauusd_stage2d_grid_lab
```

## GitHub Actions secrets

```text
TWELVEDATA_API_KEY
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

Then run manually from GitHub UI:

```text
XAUUSD Stage 2D Baseline Grid Lab
```

Inputs:

```text
intervals: 1min,5min,15min,1h
outputsize: 5000
force_refresh: false
include_run_link: false
```

## Hard rule

If no simple baseline variant survives Stage 2D, do not proceed to ML.

Telegram messages are reports only, not signals.
