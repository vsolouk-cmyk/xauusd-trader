# Stage 2A Baseline Lab

## Purpose

Stage 2A tests simple rule-based baselines before any ML.

A baseline is a simple benchmark strategy. If simple baselines fail after costs, ML is not justified.

## What this stage does

It reads the latest normalized Stage 1 files and tests:

1. Higher-timeframe SMA trend.
2. Session momentum.
3. ATR/range expansion.
4. Asia range breakout.
5. London open breakout.

## Key definitions

- SMA: simple moving average; the average close price over a fixed number of candles.
- ATR/range expansion: a volatility idea; if the candle range is much larger than recent average range, the market may be expanding.
- Asia range breakout: use the high/low from the Asia session and test breakouts during London.
- London open breakout: use the first London hour range and test later breakouts.
- Net USD: raw price movement minus assumed trading cost.
- Drawdown: decline from the previous cumulative peak.

## Strict warning

This is not a trading approval.

With only 500 candles per interval, the result may be statistically weak. The expected first decision may be `need_more_data`.

## Local command

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.xauusd_baseline_lab
```

## Expected outputs

```text
data/reports/stage2a_baseline_summary_*.json
data/reports/stage2a_baseline_summary_*.md
data/reports/baseline_trades/stage2a_baseline_trades_*.csv
```

## Proceed condition

Do not proceed to ML.

Only proceed toward larger baseline data collection if:

- data quality remains OK,
- at least one baseline has enough trades,
- net performance after assumed costs is not obviously poor.
