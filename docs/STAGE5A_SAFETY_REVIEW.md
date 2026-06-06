# Stage 5A Safety Review

## Authorization status

```text
demo_design: allowed
demo_execution: not allowed
paper_order: not allowed
live_trading: not allowed
```

## What Stage 5A may do

- Compile EA.
- Attach to chart.
- Detect closed H1 candles.
- Log signal rows to CSV.
- Print debug messages.

## What Stage 5A may not do

- Send demo orders.
- Send live orders.
- Modify positions.
- Close positions.
- Use trade classes or order functions.

## Manual code audit checklist

Search the EA source for these strings:

```text
OrderSend
CTrade
Buy
Sell
PositionOpen
PositionClose
trade.
```

Expected result:

```text
No real order placement code.
```

A comment may mention these strings for safety documentation, but there must be no executable trading call.
