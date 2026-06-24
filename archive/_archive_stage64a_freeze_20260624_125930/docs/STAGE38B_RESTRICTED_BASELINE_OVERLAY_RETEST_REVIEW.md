# Stage38B — Restricted Baseline Overlay Retest Review

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38B / T3 COT Data Foundation  
**Status:** Review after restricted baseline-overlay retest  
**Decision:** T3 COT overlay is marginal; do not promote to strategy/backtest  
**Trading mode:** Read-only research only  

---

## 1. Executive Decision

```text
T3_COT_OVERLAY_RETEST_STATUS = MARGINAL_VALUE
T3_STANDALONE_SIGNAL = NO_GO
T3_STRATEGY_BACKTEST = NO_GO
T3_STAGE39_PROMOTION = NO_GO
EA = NO_GO
PAPER_LIVE = NO_GO
LIVE_ORDER = NO_GO
T3_ALLOWED_USE = CONTEXT_OR_RISK_ANNOTATION_ONLY
```

The restricted overlay retest confirms that COT has some descriptive value, but the actual event-clock improvement is too small to justify strategy/backtest promotion.

The correct decision is to stop active T3 strategy development here and retain COT as a weekly macro/positioning context layer only.

---

## 2. Input Audit

User-provided retest audit:

```text
audit = ('PASS', 'MARGINAL_OVERLAY_VALUE_REVIEW_BEFORE_ANY_BACKTEST', 429, 2145, 10, 0, 3)
```

Interpretation:

```text
status = PASS
source_event_rows = 429
events_written = 2145
summary_rows_written = 10
warning_count = 0
note_count = 3
```

The tool ran successfully. The issue is not data quality or code failure; the issue is weak economic value.

---

## 3. Primary Result — 120H Horizon

```text
BASELINE_ALWAYS_LONG:
    source_event_count = 215
    trade_count = 215
    skipped_count = 0
    trade_mean_bps = 36.97
    event_clock_mean_bps = 36.97
    event_clock_max_drawdown_bps = 2043.19

OVERLAY_LONG_PERMITTED_ONLY:
    source_event_count = 215
    trade_count = 191
    skipped_count = 24
    trade_mean_bps = 43.22
    event_clock_mean_bps = 38.40
    uplift_vs_baseline_event_clock_mean_bps = +1.43
    event_clock_max_drawdown_bps = 2043.19
    dd_delta_vs_baseline_bps = 0.00
```

Assessment:

```text
120H overlay uplift is only +1.43 bps.
Drawdown is unchanged.
This is not enough to justify strategy promotion.
```

---

## 4. Primary Result — 240H Horizon

```text
BASELINE_ALWAYS_LONG:
    source_event_count = 214
    trade_count = 214
    skipped_count = 0
    trade_mean_bps = 82.52
    event_clock_mean_bps = 82.52
    event_clock_max_drawdown_bps = 3598.80

OVERLAY_LONG_PERMITTED_ONLY:
    source_event_count = 214
    trade_count = 190
    skipped_count = 24
    trade_mean_bps = 96.88
    event_clock_mean_bps = 86.02
    uplift_vs_baseline_event_clock_mean_bps = +3.49
    event_clock_max_drawdown_bps = 3598.80
    dd_delta_vs_baseline_bps = 0.00
```

Assessment:

```text
240H overlay uplift is only +3.49 bps.
Drawdown is unchanged.
The overlay improves average return slightly, but not enough for active development.
```

---

## 5. Component Policies

### 5.1 Avoid-long hostile block

```text
120H uplift = +1.09 bps
240H uplift = +2.55 bps
Drawdown improvement = 0.00 bps
```

This is directionally sensible but too weak.

### 5.2 Low-conviction block

```text
120H uplift = +0.34 bps
240H uplift = +0.95 bps
Drawdown improvement = 0.00 bps
```

This does not justify a gate.

### 5.3 Squeeze diagnostic long-only

```text
120H trade_mean_bps = +147.48
120H event_clock_mean_bps = +6.86
120H uplift_vs_baseline = -30.11

240H trade_mean_bps = +256.22
240H event_clock_mean_bps = +11.97
240H uplift_vs_baseline = -70.55
```

Although the selected events are strong, the sample is too small and year-concentrated. As an always-on event-clock policy, it underperforms the baseline.

Conclusion:

```text
SQUEEZE_DO_NOT_SHORT remains useful as a risk warning.
It is not a long-entry strategy.
```

---

## 6. Methodological Interpretation

The overlay looks better when measuring only selected trades, but the correct event-clock comparison shows weak marginal value.

This matters because a filter can appear strong by removing unattractive events, but if the skipped periods are counted as zero exposure, the true portfolio-level uplift may be small.

The event-clock retest is therefore the correct decision layer.

---

## 7. Final T3 Decision

```text
T3_ACTIVE_STRATEGY_DEVELOPMENT = STOP
T3_BACKTEST = NO_GO
T3_FORWARD_SHADOW = NO_GO
T3_PAPER_ORDER = NO_GO
T3_LIVE = NO_GO
```

Allowed future use:

```text
T3_COT_CONTEXT_LAYER = YES
T3_COT_RISK_ANNOTATION = YES
T3_COT_DO_NOT_SHORT_WARNING_FOR_EXTREME_SHORT = OPTIONAL
T3_COT_AVOID_LONG_WARNING_FOR_SHORT_CROWDED_ATR_EXPANSION = OPTIONAL
```

Not allowed:

```text
Do not use T3 as a standalone entry signal.
Do not build a COT-only strategy.
Do not promote COT overlay to Stage39.
Do not connect this to EA, paper-live, or live order.
```

---

## 8. Recommended Next Step

Since T3/COT does not provide enough standalone or overlay edge, the next productive step is not another COT optimization.

Recommended next phase:

```text
Stage38C — Return to simple baseline lab with COT retained as context only
```

Candidate baseline direction:

```text
Session-aware, cost-aware baseline diagnostics:
    1. London open continuation/reversal
    2. NY open continuation/reversal
    3. Asia range breakout
    4. ATR/range expansion
    5. Higher-timeframe bias + intraday entry
```

COT should only be attached as a reporting dimension, not used as the primary entry or filter in the first pass.

---

## 9. Commit Recommendation

Commit the Stage38B artifacts after this review because the data foundation is valuable even though T3 is not promotable.

Suggested commit:

```bash
cd ~/Desktop/xauusd-trader
git status --short
git add -A
git commit -m "Review Stage38B restricted COT overlay retest"
git pull --rebase origin main
git push
```

