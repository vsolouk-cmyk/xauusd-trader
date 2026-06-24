# Stage38C Asia Range Targeted Filter Review

**Project:** XAUUSD / Gold Trading System  
**Stage:** Stage38C — Simple Baseline Lab  
**Subject:** C1_ASIA_RANGE_BREAKOUT_24H targeted filter diagnostic  
**Decision date:** 2026-06-16  
**Status:** LOW_CONFIDENCE_RESEARCH_WATCHLIST_ONLY

---

## 1. Executive decision

The targeted filter diagnostic did **not** justify promotion of the H1 Asia range breakout candidate.

Final decision:

```text
C1_ASIA_RANGE_BREAKOUT_24H = LOW_CONFIDENCE_RESEARCH_WATCHLIST_ONLY
TARGETED_FILTER_PROMOTION = NO_GO
RESTRICTED_RETEST = NO_GO
STAGE39 = NO_GO
EA = NO_GO
PAPER_LIVE = NO_GO
LIVE_ORDER = NO_GO
```

The original candidate remains useful as a diagnostic benchmark, but not as a strategy candidate.

---

## 2. Input diagnostic snapshot

Audit result:

```text
status = PASS
decision = REVIEW_MARGINAL_FILTERS_BEFORE_ANY_RETEST
candidate_id = C1_ASIA_RANGE_BREAKOUT_24H
events_loaded = 972
events_written = 972
summary_rows_written = 65
policy_pass_count = 0
policy_watch_count = 1
warning_count = 0
note_count = 0
```

The script ran successfully and produced valid summaries. The rejection is based on economics and robustness, not on a data failure.

---

## 3. Policy-level result

Baseline:

```text
BASELINE_ALL
source_event_count = 972
trade_count = 972
mean_net_bps = +7.63
median_net_bps = +2.37
win_rate_net = 0.507
event_clock_mean_bps = +7.63
event_clock_max_drawdown_bps = 1612.73
positive_year_count = 4
negative_year_count = 1
max_positive_year_share = 0.421
```

Best policy candidate:

```text
LONG_ONLY
source_event_count = 972
trade_count = 533
skipped_count = 439
trade_mean_net_bps = +14.45
trade_median_net_bps = +7.37
win_rate_net = 0.537
event_clock_mean_bps = +7.92
uplift_vs_baseline_event_clock_mean_bps = +0.29
event_clock_max_drawdown_bps = 1430.68
dd_delta_vs_baseline_bps = -182.04
positive_year_count = 4
negative_year_count = 1
max_positive_year_share = 0.489
decision = WATCH_MARGINAL_FILTER
note = LOW_EVENT_CLOCK_UPLIFT_LT_5BPS
```

Interpretation:

```text
LONG_ONLY improves trade-level mean.
LONG_ONLY barely improves event-clock mean.
LONG_ONLY improves drawdown modestly.
The event-clock uplift is too small for promotion.
```

A filter that skips 439 out of 972 events but adds only +0.29 bps event-clock uplift is not strong enough to justify restricted retest.

---

## 4. Short side diagnostic

```text
SHORT_ONLY_DIAGNOSTIC
trade_count = 439
trade_mean_net_bps = -0.65
event_clock_mean_bps = -0.29
uplift_vs_baseline_event_clock_mean_bps = -7.92
event_clock_max_drawdown_bps = 2720.09
note = YEAR_CONCENTRATED_GT_55PCT;LEAVE_ONE_YEAR_OUT_NON_POSITIVE;LOW_EVENT_CLOCK_UPLIFT_LT_5BPS;NO_DRAWDOWN_IMPROVEMENT
```

Decision:

```text
SHORT_SIDE = KILL
```

The short side should not be used as an entry candidate.

---

## 5. COT annotation inside Asia breakout

LONG split by COT:

```text
LONG__MM_NEUTRAL         n=272 mean=+15.30 bps median=+3.74  WR=0.515 note=YEAR_CONCENTRATED_GT_55PCT
LONG__MM_LONG_CROWDED    n=140 mean=+17.84 bps median=+14.81 WR=0.600 note=YEAR_CONCENTRATED_GT_55PCT
LONG__MM_SHORT_CROWDED   n=65  mean=+9.22 bps  median=+6.11  WR=0.538 note=YEAR_CONCENTRATED_GT_55PCT
LONG__MM_EXTREME_LONG    n=31  mean=+7.24 bps  median=+5.32  WR=0.516 note=YEAR_CONCENTRATED_GT_55PCT
LONG__MM_EXTREME_SHORT   n=25  mean=+8.72 bps  median=-9.14  WR=0.440 note=LOW_SAMPLE_LT_30;YEAR_CONCENTRATED_GT_55PCT
```

COT did not produce a promotion-worthy filter. It remains an annotation/context layer only.

---

## 6. Range, ATR, and breakout-hour observations

Some sub-buckets look attractive at trade level, but not enough to justify promotion:

```text
LONG__ATR_LOW       n=181 mean=+15.64 bps median=+14.08 WR=0.564 note=None
LONG__H07           n=177 mean=+17.47 bps median=+7.10  WR=0.565 note=None
LONG__H15_PLUS      n=44  mean=+23.96 bps median=+24.22 WR=0.568 note=None
```

These are observationally useful, but the policy-level event-clock uplift remained marginal. Continuing to combine these filters would become optimization pressure / overfitting.

---

## 7. Methodological concern

The candidate has already passed through several selection stages:

```text
baseline lab -> deep diagnostics -> candidate spec -> targeted filters
```

At this point, further filtering on the same sample without a materially stronger event-clock improvement would be data-mining.

Therefore:

```text
NO additional H1 Asia filter optimization.
NO strategy promotion.
NO restricted retest.
```

---

## 8. Final Stage38C decision

```text
Stage38C baseline lab found weak but real structure.
The only meaningful structure is long-side Asia breakout behavior.
The targeted filters did not turn it into a robust candidate.
The H1 version is too coarse and too marginal for strategy promotion.
```

Final classification:

```text
ASIA_RANGE_BREAKOUT_24H_H1 = LOW_CONFIDENCE_RESEARCH_WATCHLIST_ONLY
```

Allowed future use:

```text
- benchmark diagnostic
- context comparison
- lower-timeframe research reference
```

Forbidden use:

```text
- entry signal
- paper-live trigger
- EA rule
- Stage39 promotion
- live order logic
```

---

## 9. Recommended next phase

The next productive path is not more H1 filtering. The next phase should move to lower-timeframe session construction:

```text
Stage38D — M5/M15 intraday session baseline foundation
```

Reason:

```text
Asia range breakout is intrinsically intraday.
H1 bars are too coarse for breakout timing, stop/target placement, and execution realism.
The project already has large 1m AMarkets history available.
A lower-timeframe baseline can test the same thesis with better event construction.
```

Stage38D must remain read-only:

```text
NO ML
NO Stage39
NO EA
NO paper-live
NO live order
```
