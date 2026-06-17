# Stage40 Parallel Thesis Megascan

## Decision scope

```text
scope = RESEARCH_STAGE_ONLY_NO_PROMOTION
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

Stage40 starts after Stage39F concluded that no stable frozen rule survived recency-bias and rule-stability audit. Therefore Stage40 must not extend Stage39 filters. It must start from independent theses and benchmark them in a consolidated way.

## Why this consolidated design exists

The project goal is to reach a robust, commercially usable XAUUSD trading system as fast as possible without wasting time on sequential weak branches. Running each thesis as a full separate A-F pipeline creates too much message latency and too many patch/fix cycles. Stage40 therefore uses a two-layer design:

1. A broad parallel thesis megascan runs multiple independent theses in one command.
2. Only strict survivors, if any, move to a later dedicated audit.

This keeps research breadth high while preventing premature EA/paper-live/live promotion.

## Included thesis families

```text
40A_FALSE_BREAKOUT_SWEEP_REVERSAL
40B_VOLATILITY_COMPRESSION_EXPANSION
40C_SESSION_TRANSITION_IMBALANCE
40D_FAILED_CONTINUATION_AFTER_EXTREME_MOVE
40E_PULLBACK_CONTINUATION_AFTER_TREND
40F_VOLATILITY_SHOCK_REVERSAL
```

## What is intentionally not included

The scan does not include Stage39 extension filters such as:

```text
RANGE_BOTTOM_REV_LONG_W48_Q0.05 + Monday
RANGE_BOTTOM_REV_LONG_W48_Q0.05 + London
RANGE_BOTTOM_REV_LONG_W48_Q0.05 + prior_ret72 bucket
RANGE_BOTTOM_REV_LONG_W48_Q0.05 + trigger severity bucket
```

Those were archived because Stage39F found recency bias and no strict stable frozen survivor.

## Benchmarks and gates

Each candidate is checked against:

- direction-matched H1 all drift,
- direction-matched daily anchor drift,
- event-clock non-overlap,
- round-trip cost stress,
- ex-2025 behavior,
- leave-one-year-out sanity,
- chronological train/OOS split,
- first/second half,
- q1/q2/q3/q4 stability,
- MAE/MFE path risk,
- stop/target touch diagnostics.

## Interpretation

```text
STRICT_PARALLEL_THESIS_WATCH_ONLY_NO_PROMOTION
```

A strict row is worth a later dedicated audit only. It is not tradable.

```text
SOFT_PARALLEL_THESIS_WATCH_ONLY_NO_PROMOTION
```

A soft row has weak residual and should not be promoted.

```text
FAIL_* / INSUFFICIENT_*
```

Do not extend these with filters.

## Next allowed step

If strict rows exist:

```text
Stage40B_DEDICATED_SURVIVOR_AUDIT
```

If no strict rows exist:

```text
Stage40_PARALLEL_THESIS_MEGASCAN = ARCHIVE
```

