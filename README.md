# xauusd-trader

Commercial XAUUSD/gold trading research pipeline.

## Current stage

Stage 2A: simple baseline lab after Stage 1 data quality passed.

No ML. No trading bot. No paper order. No live order.

## First definitions

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

## Current data source decision

Use Twelve Data REST for Stage 0/1/2A because it is faster and cleaner than broker onboarding.

OANDA is paused. MT5/broker feed validation comes later.

## Local Stage 1 snapshot

```bash
cd ~/Desktop/xauusd-trader
export TWELVEDATA_API_KEY='PASTE_KEY_HERE'
python3 -m app.xauusd_stage1_snapshot --outputsize 500
```

## Local Stage 2A baseline lab

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.xauusd_baseline_lab
```

## GitHub Actions

Add repository secret:

```text
TWELVEDATA_API_KEY
```

Then run manually from GitHub UI:

```text
XAUUSD Stage 2A Baseline Lab
```

Inputs:

```text
intervals: 1min,5min,15min,1h
outputsize: 500
```

## Hard rule

If simple baselines are poor after assumed costs, do not proceed to ML.
