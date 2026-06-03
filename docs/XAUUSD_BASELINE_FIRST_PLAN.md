# XAUUSD Baseline-First Plan

## Objective

Determine whether XAUUSD has a simple, robust, cost-aware baseline worth improving with a model.

## Stage 0: Data source decision

Choose one initial path:

1. REST/cloud feed for fast research.
2. MT5 broker feed for execution realism.
3. Futures reference data if institutional benchmark is needed.

Do not start model development before this decision.

## Stage 1: Collector

Required outputs:

- Raw candles by timeframe.
- Normalized candles.
- Data quality summary.
- Gap report.
- Spread report if bid/ask available.
- Session tags.

Suggested files:

- `app/xauusd_collect.py`
- `app/xauusd_normalize.py`
- `app/xauusd_data_quality.py`
- `.github/workflows/xauusd_research.yml` if REST/cloud feed is used.

## Stage 2: Baseline lab

Test these baselines before ML:

1. Higher-timeframe trend following.
2. Asia range breakout.
3. London open breakout.
4. NY open continuation/reversal.
5. ATR/range expansion.
6. Session-only momentum.
7. News blackout filter.
8. Higher-timeframe bias + intraday entry.

Outputs:

- Per-baseline avg return.
- Win rate.
- Drawdown proxy.
- Trade frequency.
- Session breakdown.
- Spread/cost sensitivity.

## Stage 3: Regime on/off model

Only start if at least one simple baseline is positive after costs.

Model purpose:

- Turn a baseline ON/OFF.
- Improve baseline return and risk.
- Avoid direct price prediction as first objective.

## Stage 4: Forward shadow

No orders. Record signals and strict outcomes.

Required:

- Strict horizon resolve.
- Late diagnostic resolve.
- Batch-level analysis.
- Session-level analysis.

## Stage 5: Paper-order

Only after forward shadow passes.

Guards:

- Max open positions.
- Max daily loss.
- Spread guard.
- News blackout.
- Cooldown.
- Fixed small size.

## Kill-switches

Stop if:

- Data quality is poor.
- No baseline is positive after costs.
- Model does not beat baseline out-of-sample.
- Forward shadow fails.
- Results depend on one narrow session/regime only.
