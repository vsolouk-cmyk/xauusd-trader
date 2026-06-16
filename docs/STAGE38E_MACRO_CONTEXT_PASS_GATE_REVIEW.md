# Stage38E Macro Context Pass Gate Review

## Status

```text
STAGE38E_MACRO_DATA_FOUNDATION = PASS
STAGE38E_MACRO_H1_JOIN = PASS
STAGE38E_MACRO_CONTEXT_ERA_RECHECK = PASS
STAGE38E_MACRO_PASS_GATE = WATCH_ONLY / NO_PROMOTION
STAGE38E_ACTIVE_STRATEGY_DEVELOPMENT = STOP
STAGE39 = NO_GO
EA = NO_GO
PAPER_LIVE = NO_GO
LIVE_ORDER = NO_GO
```

## Input reviewed

The macro pass gate compared event-clock policies against an always-long macro-event baseline at 72H and 120H horizons.

Audit result:

```text
status = PASS
decision = MACRO_GATE_WATCH_ONLY_NO_BASELINE_PROMOTION
source_return_rows = 2138
valid_return_rows = 2138
events_written = 12828
summary_rows_written = 12
pass_count = 0
watch_count = 10
no_promotion_count = 0
warning_count = 0
note_count = 1
```

## Key results

### 72H

```text
BASELINE_ALWAYS_LONG:
    event_clock_mean = +21.66 bps
    max_dd = 8317.50 bps

BLOCK_REAL_YIELD_FLAT_USD_DOWN:
    event_clock_mean = +22.80 bps
    uplift = +1.15 bps
    max_dd improvement = 1008.98 bps
    decision = WATCH_RESTRICTED_MACRO_CONTEXT_GATE

LONG_PERMITTED_EXCLUDE_HOSTILE_OR_RISK_ELEVATED:
    event_clock_mean = +23.39 bps
    uplift = +1.74 bps
    max_dd improvement = 4188.51 bps
    decision = WATCH_RESTRICTED_MACRO_CONTEXT_GATE

LONG_ONLY_VIX_5D_UP:
    event_clock_mean = +5.81 bps
    uplift = -15.84 bps
    decision = WATCH only; not a tradable policy

LONG_ONLY_REAL_YIELD_DOWN_USD_FLAT:
    event_clock_mean = +3.36 bps
    uplift = -18.30 bps
    decision = WATCH only; not a tradable policy

LONG_ONLY_REAL_5D_DOWN:
    event_clock_mean = +4.92 bps
    uplift = -16.73 bps
    decision = WATCH only; not a tradable policy
```

### 120H

```text
BASELINE_ALWAYS_LONG:
    event_clock_mean = +38.58 bps
    max_dd = 10561.94 bps

BLOCK_REAL_YIELD_FLAT_USD_DOWN:
    event_clock_mean = +40.34 bps
    uplift = +1.77 bps
    max_dd improvement = 601.06 bps
    decision = WATCH_RESTRICTED_MACRO_CONTEXT_GATE

LONG_PERMITTED_EXCLUDE_HOSTILE_OR_RISK_ELEVATED:
    event_clock_mean = +41.23 bps
    uplift = +2.65 bps
    max_dd improvement = 4907.11 bps
    decision = WATCH_RESTRICTED_MACRO_CONTEXT_GATE

LONG_ONLY_VIX_5D_UP:
    event_clock_mean = +8.21 bps
    uplift = -30.36 bps
    decision = WATCH only; not a tradable policy

LONG_ONLY_REAL_YIELD_DOWN_USD_FLAT:
    event_clock_mean = +8.30 bps
    uplift = -30.28 bps
    decision = WATCH only; not a tradable policy

LONG_ONLY_REAL_5D_DOWN:
    event_clock_mean = +14.55 bps
    uplift = -24.02 bps
    decision = WATCH only; not a tradable policy
```

## Interpretation

The macro context dataset is useful as an explanatory layer, but the event-clock gate does not justify promotion to a baseline or strategy.

The best broad policy is:

```text
LONG_PERMITTED_EXCLUDE_HOSTILE_OR_RISK_ELEVATED
```

But the real event-clock uplift is too small:

```text
72H uplift = +1.74 bps
120H uplift = +2.65 bps
```

This is not enough to justify strategy development.

The supportive-only macro contexts look attractive at trade-level, but collapse when skipped events are counted as zero in event-clock accounting. Therefore they are context annotations, not trade signals.

## Decision

```text
Stage38E macro data foundation = keep
Stage38E macro context = keep as annotation / risk context
Stage38E standalone or overlay strategy = no-go
Stage38E active edge development = stop
```

## Next phase

The main missing institutional gold layer remains ETF holdings/flows.

Recommended next phase:

```text
Stage38F — Free Gold ETF Holdings / Flow Data Foundation
```

This should start as source availability audit only:

```text
app/stage38f_gold_etf_source_availability_audit.py
```

No strategy, no baseline, no Stage39, no EA, no paper-live, no live order.
