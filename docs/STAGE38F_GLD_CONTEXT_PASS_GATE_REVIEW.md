# STAGE38F — GLD Context Pass-Candidate Gate Review

## Decision

```text
STAGE38F_GLD_CONTEXT_PASS_GATE = WATCH_ONLY_NO_BASELINE_PROMOTION
GLD_DATA_FOUNDATION = KEEP
GLD_CONTEXT = KEEP_AS_ANNOTATION_OR_RESTRICTED_OVERLAY_INPUT
GLD_BASELINE_PROMOTION = NO-GO
STAGE39 / EA / PAPER-LIVE / LIVE = NO-GO
```

## Inputs reviewed

The gate evaluated GLD/SPDR ETF-flow context using event-clock accounting over 24H, 72H, and 120H horizons.

The prior diagnostic showed several strong subset contexts, especially at 120H:

- `ETF_STRONG_OUTFLOW`
- `ETF_STRONG_INFLOW`
- `FLOW_5D_INFLOW`
- `FLOW_20D_STRONG_OUTFLOW`
- `FLOW_20D_STRONG_INFLOW`
- `FLOW_1D_FLAT`

However, subset trade mean alone is not sufficient. A context must improve event-clock return or materially reduce drawdown after skipped events are counted as zero.

## Gate result

The gate did not produce a promotable baseline.

Key 120H results:

```text
BASELINE_ALWAYS_LONG
event_clock_mean = +37.56 bps
max_drawdown = 10984.34 bps

BLOCK_FLOW_20D_OUTFLOW
event_clock_mean = +44.92 bps
uplift_vs_baseline = +7.37 bps
drawdown_delta = -6063.70 bps
decision = WATCH_RESTRICTED_GLD_CONTEXT_GATE

BLOCK_ETF_OUTFLOW
event_clock_mean = +41.84 bps
uplift_vs_baseline = +4.28 bps
drawdown_delta = -5744.67 bps
decision = WATCH_RESTRICTED_GLD_CONTEXT_GATE

LONG_PERMITTED_EXCLUDE_ETF_OUTFLOW_OR_FLOW20_OUTFLOW
event_clock_mean = +39.74 bps
uplift_vs_baseline = +2.18 bps
drawdown_delta = -6152.76 bps
decision = WATCH_RESTRICTED_GLD_CONTEXT_GATE
```

The closest result is `BLOCK_FLOW_20D_OUTFLOW / 120H`, but it remains below the promotion threshold.

## Interpretation

GLD flow contains useful information, but not enough as a standalone baseline.

The important nuance is:

```text
GLD subset signal = promising
GLD event-clock policy = not yet promotable
```

The GLD features are therefore useful as context and as a possible input to a combined exogenous overlay. They are not sufficient for strategy promotion by themselves.

## Allowed use

Allowed:

- keep GLD daily features
- keep GLD H1 anti-lookahead join
- use GLD flow state as annotation
- use GLD flow in a restricted composite exogenous overlay diagnostic

Not allowed:

- no GLD-only trading rule
- no Stage39
- no EA
- no Telegram trade alerts
- no paper-live
- no live execution

## Next step

Proceed to a read-only composite exogenous overlay gate:

```text
Stage38G = COT + Macro/Risk + GLD composite overlay diagnostic
```

The purpose is not to create a strategy. The purpose is to test whether several independent exogenous contexts together can produce event-clock uplift that none of the individual modules could produce alone.

Promotion remains blocked unless the composite gate demonstrates robust, multi-year, non-concentrated improvement.
