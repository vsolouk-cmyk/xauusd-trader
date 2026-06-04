# Data Source Decision

## Current decision

Use Twelve Data REST as the primary Stage 0 data source.

## Why OANDA was paused

OANDA REST v20 is technically suitable, but it is not a reliable dependency for the current operating constraints because country/entity/API access can block the path.

## Why Twelve Data

Twelve Data is a data provider, not a broker. It is simpler for early research and does not require us to solve broker onboarding before we even know whether XAUUSD baselines are promising.

## Critical limitation

Twelve Data Stage 0 data is not final execution data. It should be used for:

- data-collection pipeline testing,
- candle sanity checks,
- initial baseline feasibility,
- rough session/regime behavior.

It should not be used alone for:

- final spread modeling,
- paper-order execution realism,
- live trading decisions.

## Later validation path

After at least one baseline is positive after conservative assumed costs, validate with:

1. Dukascopy or another historical reference source if needed.
2. MT5/broker feed for execution realism.
3. Broker spread/slippage checks before paper-order.
