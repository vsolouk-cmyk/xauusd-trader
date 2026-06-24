# STAGE38H — Bull Drift and Tradability Audit Plan

## Status

Read-only diagnostic plan. No strategy promotion, no Stage39, no EA, no paper-live, no live trading.

## Why this stage exists

Stages 38A–38G repeatedly showed positive forward returns in several contexts, especially during 2025/2026. The key risk is that these positives may not be edge; they may simply reflect the broad bull drift of XAUUSD during the sample period.

Stage38H tests that directly.

## Core question

Are the positive 24H/72H/120H forward returns observed in previous diagnostics materially better than a naive always-long gold drift baseline after accounting for:

1. daily event-clock exposure,
2. weekly event-clock exposure,
3. all-H1 overlapping exposure,
4. year and era splits,
5. leave-one-year-out robustness,
6. chronological first-half/second-half stability,
7. adverse excursion and drawdown burden.

## Inputs

SQLite database:

```text
 data/local/xauusd_local_store.sqlite
```

Primary table:

```text
 bars
```

Expected symbol/source/timeframe:

```text
 source = amarkets_mt5
 symbol = XAUUSD
 timeframe aliases = H1,1h
```

The script detects timestamp and OHLC columns flexibly.

## Horizons

Default forward-return horizons:

```text
 24 bars  = 24H
 72 bars  = 72H
 120 bars = 120H
```

## Event families

### 1. DAILY_ANCHOR

First available H1 bar per UTC trading day.

This approximates the event-clock used by macro/GLD daily exogenous features.

### 2. WEEKLY_ANCHOR

First available H1 bar per ISO week.

This reduces overlap and checks whether the same apparent drift survives less-frequent event sampling.

### 3. H1_ALL

Every H1 bar with enough future horizon.

This is intentionally overlapping and is used only as a drift/tradability reference, not a strategy candidate.

## Metrics

For each event family and horizon, the audit computes:

- sample count
- long mean return bps
- long median return bps
- long win rate
- t-stat of mean
- short mean return bps
- net mean after configurable one-trade cost
- MFE and MAE statistics
- event-clock max drawdown
- positive and negative year counts
- max positive-year share
- positive and negative month counts
- max positive-month share
- pre-2025 mean
- exclude-2025 mean
- 2025 mean
- 2026 mean
- first-half mean
- second-half mean
- worst leave-one-year-out mean

## Decision logic

This audit does not promote a strategy. It only classifies the drift regime:

```text
BULL_DRIFT_DOMINANT_NO_EDGE_PROMOTION
BULL_DRIFT_PRESENT_REQUIRES_ALPHA_ABOVE_BASELINE
BULL_DRIFT_WEAK_OR_MIXED_REVIEW
```

Even if always-long drift is positive, it is not a tradable strategy by itself. Promotion requires later evidence that a candidate improves event-clock return and/or drawdown versus this drift baseline.

## Outputs

SQLite tables:

```text
stage38h_bull_drift_forward_returns
stage38h_bull_drift_summary
stage38h_bull_drift_year_summary
stage38h_bull_drift_audit
```

Reports:

```text
data/reports/stage38h_bull_drift_and_tradability_audit/stage38h_bull_drift_and_tradability_audit.json
data/reports/stage38h_bull_drift_and_tradability_audit/stage38h_bull_drift_and_tradability_audit.md
```

## Hard NO-GO rules

Stage38H does not allow:

- Stage39
- EA work
- paper-live
- live execution
- Telegram alerts
- ML training
- parameter optimization

The only allowed next step after Stage38H is a review. If bull drift dominates, previous context diagnostics must be judged relative to this baseline rather than as standalone positives.
