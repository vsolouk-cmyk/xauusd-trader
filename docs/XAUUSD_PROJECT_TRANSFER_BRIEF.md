# XAUUSD Project Transfer Brief

Use this document as the starting context for a new ChatGPT Project and/or a new repository.

## Project name

Suggested: `xauusd-research`

## Strategic goal

Build a commercially usable XAUUSD/gold trading research pipeline, but only after validating market data quality and simple baselines. Do not jump directly to ML or live/paper-order execution.

## Core decision

The crypto strategy path is frozen. Crypto remains a collector/observation project. Active strategy development moves to XAUUSD/gold in a separate project.

## Development philosophy

- Baseline-first, not ML-first.
- Data-quality-first, not signal-first.
- One symbol focus: XAUUSD/gold.
- No bot execution until baselines and forward shadow are validated.
- Every phase has a hard kill-switch.
- Avoid long testing by hope; if baseline/model does not show improvement quickly, stop or pivot.

## Candidate data sources

### Option A: OANDA REST

Best for GitHub Actions and cloud collection. Useful for research cadence and continuous data collection.

Pros:
- REST-friendly.
- GitHub Actions compatible.
- Good for initial research.

Cons:
- Feed may not match future MT5/broker execution.

### Option B: MT5 broker feed

Best for execution realism if future paper/live will use MT5.

Pros:
- Same type of environment used for execution.
- Broker-specific spread/fill realism.

Cons:
- Not suitable for GitHub Actions without a proper Windows/VPS setup.
- Requires MT5 terminal/login.

### Option C: CME GC/MGC futures reference

Best for institutional benchmark/research, not necessarily retail CFD execution.

Pros:
- Cleaner futures market reference.
- Useful for macro/trend validation.

Cons:
- Historical/real-time data access may not be free/easy.
- Needs mapping to XAUUSD CFD feed for execution.

## Suggested initial choice

Start with REST/cloud data if speed matters. Keep MT5 path as the execution-realistic follow-up.

## Phase 1: Data quality only

Collect:

- XAUUSD M1, M5, M15, H1 candles.
- Bid/ask or spread if available.
- Tick volume if available.
- Session tags: Asia, London, New York, London-NY overlap.
- Timestamp quality and gap statistics.

Do not build trading signals yet.

Kill-switch:

- If data has unreliable timestamps, large unexplained gaps, no spread information, or inconsistent symbol pricing, stop before modeling.

## Phase 2: Baseline lab

Before ML, test simple baselines:

- Higher-timeframe trend following.
- Asia range breakout.
- London open breakout.
- NY open continuation/reversal.
- ATR/range expansion.
- Session-only momentum.
- News blackout filter.
- Higher-timeframe bias + intraday entry.

Kill-switch:

- If no baseline is positive after spread/cost assumptions, do not proceed to ML.

## Phase 3: Regime/on-off model

If a baseline works, build a model only to turn that baseline ON/OFF.

Do not train a direct “predict price” model first.

Target:

- Excess return over the selected baseline.
- Improved average return and drawdown versus unconditional baseline.

Kill-switch:

- If the model does not beat the baseline on out-of-sample and forward shadow, stop.

## Phase 4: Forward shadow

Log signals only. No orders.

Resolve with strict timing and spread-aware outcomes.

Kill-switch:

- If strict forward shadow is not positive after enough independent batches, do not proceed.

## Phase 5: Paper-order

Only after forward shadow passes. Paper-order must include:

- Max open positions.
- Max daily loss.
- Spread/slippage guard.
- News blackout.
- Cooldown.
- Fixed small size.

Live remains forbidden until paper-order passes.
