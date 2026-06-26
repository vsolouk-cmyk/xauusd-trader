# Stage71 Locked Historical Forward Test

## Purpose

Stage71 converts the K06 champion workflow from real-forward waiting into a locked historical proof framework.
It separates the available 2011-present macro dataset into four chronological blocks:

1. `TRAIN_DISCOVERY` — discovery-only window.
2. `VALIDATION_SELECTION` — selection-only window.
3. `LOCKED_HISTORICAL_FORWARD` — pseudo-forward historical window.
4. `FINAL_STATISTICAL_HOLDOUT` — final locked statistical proof window.

The locked windows must not be used for threshold tuning.

## Champion under test

`K06_RESILIENT_GOLD_VS_DXY`, long, 120 trading-day horizon:

- `gold_sma20_over_50 > 0`
- `dxy_ret_20d > 0`
- `real_yield_change_20d < 0`

## Why this stage exists

The project has enough macro history to avoid relying on real-time forward observation as the only statistical proof.
Real forward remains useful for pipeline freshness, latency, data lag, and operational sanity, but the statistical question should be answered using locked historical holdout where possible.

## Index / macro temporal compatibility

Stage71 audits coverage of key columns from the configured target start date, default `2011-01-03`.
If DXY, real yield, VIX, ETF flow, central-bank demand, or gold columns have low coverage, the output marks the specific column as requiring backfill or alignment review.

This stage does not download data. If the existing local macro dataset is not temporally compatible, update or manually download the missing index/source files and rerun the upstream refresh stages.

## Output decision states

- `K06_PASSES_LOCKED_HISTORICAL_FORWARD_NO_ORDER`
- `K06_PASSES_LOCKED_HISTORICAL_FORWARD_WITH_CAUTION_NO_ORDER`
- `K06_FAILS_LOCKED_HISTORICAL_FORWARD_NO_ORDER`

## Hard blocks

Stage71 cannot authorize broker, EA, paper-live, paper-order, or live operation.
