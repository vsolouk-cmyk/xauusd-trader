# Stage51 Broker-Real Volatility Squeeze Breakout Audit

## Thesis

M15 volatility compression may precede short-horizon directional continuation when price breaks out of the compressed range and M30 trend confirmation is aligned.

This is not:

- liquidity-sweep reversal rescue
- H1 range-expansion persistence rescue
- session open-range breakout rescue
- post-hoc long-only/short-only filtering

## Data

Uses the persistent AMarkets multi-timeframe SQLite database:

```text
data/broker_normalized/amarkets_multitf.sqlite
```

Required timeframes:

```text
M5, M15, M30
```

Cost model:

```text
reports/stage48f/stage48f_cost_model.json
```

## Logic

For each grid candidate:

1. Build M15 volatility compression using a rolling prior-window range percentile.
2. Trigger only when the next closed M15 bar breaks above/below the prior compressed range.
3. Confirm direction using M30 close/SMA and SMA slope.
4. Enter at the next M5 close after the signal.
5. Apply broker-real spread gate and Stage48F stress cost.
6. Evaluate 6/12/24 M5-bar horizons.
7. Run hard-audit style checks: IS/OOS, chronological folds, cost x1.5/x2, declustering, year/month concentration, and long/short split diagnostics.

## Promotion policy

This stage can only produce:

- `VOLATILITY_SQUEEZE_HARD_AUDIT_PASS_NEEDS_FORWARD_SHADOW_NO_PROMOTION`
- `VOLATILITY_SQUEEZE_HARD_AUDIT_COMPLETE_NO_PASS_NO_PROMOTION`

It never authorizes EA, paper-live, live trading, or promotion.
