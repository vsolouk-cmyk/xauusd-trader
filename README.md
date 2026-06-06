# xauusd-trader

Commercial XAUUSD/gold trading research pipeline.

## Current stage

Stage 5A: MT5 dry-run EA design.

No demo order. No paper order. No live order.

## Locked candidate v1

```text
long-only
TP = 24 USD
SL = 15 USD
blocked session = London 07:00-13:00 UTC
allowed sessions = Asia, London-NY overlap, New York, Other
```

## Stage 5A EA

```text
mql5/Experts/XAUUSD/XAUUSD_DryRun_v1.mq5
```

This EA logs signals only.

## Hard rule

Stage 5A does not authorize demo execution, paper-order, or live trading.
