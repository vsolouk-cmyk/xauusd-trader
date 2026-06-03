# XAUUSD Stage Plan

## Stage 0 — Data source decision

Deliverable:

- `docs/DATA_SOURCE_DECISION.md`
- selected provider/path
- reason for selection
- known limitations

Kill-switch:

- No reliable candle access.
- No workable automation path.
- No realistic path to later execution validation.

## Stage 1 — Collector and data quality

Deliverables:

- raw candles
- normalized candles
- timestamp/gap report
- spread report if available
- session tags

Kill-switch:

- poor timestamp quality
- large unexplained gaps
- no usable M1/M5 data
- unreliable provider behavior

## Stage 2 — Baseline lab

Baselines to test:

1. Higher-timeframe trend following.
2. Asia range breakout.
3. London open breakout.
4. NY open continuation/reversal.
5. ATR/range expansion.
6. Session-only momentum.
7. News blackout filter.
8. Higher-timeframe bias + intraday entry.

Kill-switch:

- no baseline positive after costs
- result depends on one narrow cherry-picked period
- trade frequency too low to validate
- spread sensitivity destroys edge

## Stage 3 — Regime ON/OFF model

Only allowed if a baseline works.

Objective:

- improve baseline risk-adjusted performance
- reduce bad market periods
- avoid direct price prediction as first model task

Kill-switch:

- model does not beat baseline out-of-sample
- model improvement disappears after costs
- model only works in one narrow period

## Stage 4 — Forward shadow

No orders.

Deliverables:

- signal logs
- strict outcome resolution
- session-level analysis
- batch-level analysis

Kill-switch:

- strict forward results are negative
- results depend on late/loose diagnostics
- live-like costs destroy the signal

## Stage 5 — Paper-order

Only after forward shadow passes.

Required guards:

- max open positions
- max daily loss
- spread guard
- news blackout
- cooldown
- fixed small size

Kill-switch:

- paper results fail strict risk limits
- execution cost differs too much from assumptions
- operational reliability is weak
