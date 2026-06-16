# STAGE38G Composite Exogenous Overlay Gate Review

## Status

`STAGE38G_COMPOSITE_EXOGENOUS_OVERLAY_GATE = WATCH_ONLY_NO_PROMOTION`

The composite exogenous overlay gate completed successfully from an execution/data-integrity perspective, but it did not produce a promotable baseline or overlay.

## Input foundations used

- COT gold foundation from Stage38B: retained as context only.
- Macro/risk foundation from Stage38E: retained as context only.
- SPDR GLD ETF holdings/flow foundation from Stage38F: retained as context only.

All of these components were previously validated for anti-lookahead joins, but none had passed a strict event-clock promotion gate as standalone overlays.

## Audit result

```text
status = PASS
decision = COMPOSITE_EXOGENOUS_GATE_WATCH_ONLY_NO_PROMOTION
gld_rows_loaded = 25,643
event_count = 1,035
events_written = 30,960
summary_rows_written = 30
pass_count = 0
watch_count = 20
no_promotion_count = 7
warning_count = 0
note_count = 0
```

## Key event-clock findings

### 24H horizon

Baseline always-long event-clock mean:

```text
BASELINE_ALWAYS_LONG = +7.27 bps
```

Best avoid-long overlays did not improve event-clock performance materially:

```text
BLOCK_MACRO_HOSTILE = +7.57 bps, uplift +0.31 bps
LONG_PERMITTED_EXCLUDE_ETF_OUTFLOW_OR_FLOW20_OUTFLOW = +7.77 bps, uplift +0.50 bps
```

Supportive-only policies were worse in event-clock accounting because too many events were skipped.

### 72H horizon

Baseline always-long event-clock mean:

```text
BASELINE_ALWAYS_LONG = +21.71 bps
```

Best avoid-long overlays still failed promotion:

```text
BLOCK_GLD_ETF_OR_FLOW20_OUTFLOW = +23.89 bps, uplift +2.19 bps
BLOCK_MACRO_HOSTILE = +22.69 bps, uplift +0.98 bps
BLOCK_GLD_OR_MACRO_HOSTILE = +21.75 bps, uplift +0.04 bps
```

Supportive-only GLD policies had attractive trade means but worse event-clock means than baseline.

### 120H horizon

Baseline always-long event-clock mean:

```text
BASELINE_ALWAYS_LONG = +37.56 bps
```

The strongest avoid-long overlay was still marginal:

```text
BLOCK_GLD_ETF_OR_FLOW20_OUTFLOW = +41.84 bps, uplift +4.28 bps
BLOCK_MACRO_HOSTILE = +39.53 bps, uplift +1.97 bps
BLOCK_GLD_OR_MACRO_HOSTILE = +38.19 bps, uplift +0.63 bps
```

Supportive-only policies had high trade means but failed event-clock promotion:

```text
LONG_ONLY_GLD_SUPPORTIVE = +24.65 bps, uplift -12.90 bps
LONG_ONLY_GLD_SUPPORTIVE_AND_MACRO_NOT_HOSTILE = +22.85 bps, uplift -14.71 bps
LONG_ONLY_GLD_SUPPORTIVE_AND_MACRO_SUPPORTIVE = +2.63 bps, uplift -34.93 bps
```

## Decision

The composite exogenous overlay is not promotable.

Reasons:

1. No policy achieved promotion-level event-clock uplift.
2. The best 120H uplift was only +4.28 bps, below the minimum practical threshold.
3. Supportive-only policies looked strong on trade-mean but failed after skipped events were accounted for.
4. Combining GLD, macro and COT did not materially outperform the simpler GLD-only or macro-only overlays.
5. The result supports keeping exogenous data for annotation and future diagnostics, not for strategy gating.

## Final Stage38G label

```text
COMPOSITE_EXOGENOUS_GATE_WATCH_ONLY_NO_PROMOTION
```

## What remains valid

The following remain useful as data/context layers:

- COT weekly positioning features.
- Macro/risk daily features from FRED.
- GLD daily holdings/flow features from SPDR.
- Anti-lookahead H1 joins for all above layers.

## What is explicitly not allowed

```text
No Stage39 promotion.
No EA work.
No MT5 trading integration.
No paper-live.
No live trading.
No Telegram trade alerts.
No ML model training based on these weak overlays.
```

## Recommended next action

Stop the exogenous-overlay promotion path and switch to a new session with a transfer pack.

The next research direction should not be another blind overlay combination. The next path should either:

1. pivot to a structurally different thesis with pre-declared economics, or
2. audit whether the current positive baseline drift is mostly a gold bull-market drift that cannot be converted into a tradable edge, or
3. run a small number of thesis-driven diagnostics around reversal/continuation conditional on extreme exogenous disagreement, but only if strict event-clock accounting is retained.
