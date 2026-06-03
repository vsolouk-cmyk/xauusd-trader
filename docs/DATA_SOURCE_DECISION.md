# Data Source Decision

The first technical decision is the data source.

No collector, baseline, ML, paper-order, or live logic should be built before this decision is explicit.

## Option A — REST/cloud feed

Best for fast research and GitHub Actions.

Pros:

- Easier to automate.
- Compatible with GitHub Actions.
- Good for continuous collection.
- Faster to start.

Cons:

- Feed may differ from the future broker/MT5 execution feed.
- Spread quality depends on provider.

Best use:

- Initial research and data-quality pipeline.

## Option B — MT5 broker feed

Best for execution realism.

Pros:

- Closer to future paper/live execution.
- Broker spread and candle behavior are realistic for that broker.

Cons:

- Not ideal for GitHub Actions.
- Usually needs local terminal, VPS, or Windows/MT5 environment.
- More operational overhead.

Best use:

- Later validation before paper-order/live.

## Option C — Futures reference data

Best for institutional benchmark.

Pros:

- Cleaner benchmark for gold futures structure.
- Useful for macro/trend validation.

Cons:

- Data access may be difficult or paid.
- Needs mapping to retail XAUUSD broker feed.

Best use:

- Secondary validation, not the first practical path.

## Recommended initial decision

Start with **REST/cloud feed** if the immediate goal is fast collection and GitHub Actions research.

Keep **MT5 broker feed** as the execution-realistic follow-up.

## Kill-switch for data source

Reject or pause a data source if:

- timestamps are unreliable,
- unexplained gaps are large,
- spread is unavailable or unrealistic,
- symbol pricing is inconsistent,
- collection fails frequently,
- the feed cannot support M1/M5/M15/H1 candles reliably.
