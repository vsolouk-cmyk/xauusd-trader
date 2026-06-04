# xauusd-trader

Commercial XAUUSD/gold trading research pipeline.

## Current stage

Stage 0/1: Twelve Data REST collection and data quality.

No ML. No trading bot. No paper order. No live order.

## First definitions

- XAUUSD: spot gold quoted in US dollars.
- Candle: one OHLC bar for a fixed time period.
- OHLCV: open, high, low, close, volume.
- Spread: ask minus bid; direct trading cost.
- Baseline: a simple rule-based strategy used as the minimum benchmark before ML.
- Forward shadow: logging future signals without placing orders.
- Data provider: a service that gives market data but is not necessarily the broker used for execution.

## Current data source decision

Use Twelve Data REST for Stage 0 because it is faster and cleaner than broker onboarding.

OANDA is paused. MT5/broker feed validation comes later.

## Local smoke test

```bash
cd ~/Desktop/xauusd-trader
python3 -m pip install -r requirements.txt
export TWELVEDATA_API_KEY='PASTE_KEY_HERE'
python3 -m app.xauusd_collect --interval 1min --outputsize 100
python3 -m app.xauusd_normalize
python3 -m app.xauusd_data_quality
```

## GitHub Actions

Add repository secret:

```text
TWELVEDATA_API_KEY
```

Then run manually from GitHub UI:

```text
XAUUSD Stage 0 Twelve Data Check
```

## Hard rule

If data quality is poor, stop before baseline testing.
