# Stage 5A MT5 Dry-Run EA

## Purpose

Create a MetaTrader 5 Expert Advisor that logs locked strategy signals only.

It does not place orders.

## Locked strategy

```text
strategy_id: xauusd_long_tp24_sl15_no_london_v1
direction: long-only
timeframe: H1
signal: close - SMA10 >= 10 USD
entry model: next H1 open
TP: 24 USD
SL: 15 USD
blocked session: London 07:00-13:00 UTC
```

## File

```text
mql5/Experts/XAUUSD/XAUUSD_DryRun_v1.mq5
```

Copy this file into your MT5 data folder:

```text
MQL5/Experts/XAUUSD/XAUUSD_DryRun_v1.mq5
```

Then compile in MetaEditor.

## Output

The EA writes a CSV file to MT5 common files:

```text
XAUUSD_DryRun_v1_signals.csv
```

## Hard safety rule

This EA contains no order placement code.

It does not use:

```text
OrderSend
CTrade
Buy
Sell
PositionOpen
```

## Important limitation

The session filter uses current UTC time from `TimeGMT()`. For dry-run logging this is acceptable.

Before any demo-order EA, session logic must be hardened against broker server time and tested separately.
