# XAUUSD Stage47A Structural Thesis Decision Memo

Generated UTC: 2026-06-18T18:34:23.535449+00:00

## Stage status

```text
stage = Stage47A_STRUCTURAL_THESIS_DECISION
status = DESIGN_DECISION_COMPLETE_SCAN_RECOMMENDED_NO_PROMOTION
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
next_allowed_step = STAGE47B_LIQUIDITY_SWEEP_REVERSAL_SCAN_DESIGN
```

## Inherited state

Stage46 external-context branch is closed. It produced no strict or soft survivors and must not be rescued. The next step must be a structurally new thesis defined before testing, or the project should pause/archive.

Inherited prohibitions:

```text
NO rescue of Stage41/42/43 archived candidates
NO continuation of Stage46 external-context branch
NO post-hoc tuning of bad hours/months/quarters/spread/news buckets
NO ML before robust cost-aware rule baselines survive
NO EA / paper-live / live
```

## Decision standard for Stage47A

A thesis may proceed only if it is:

1. structurally different from Stage41-Stage46,
2. defined before testing,
3. cost-aware at design time,
4. rule-based only,
5. not a filter rescue over previously failed rows,
6. capable of producing larger gross excursion per trade than the cost model,
7. equipped with an explicit kill-switch.

## Thesis candidates reviewed

### STRUCT47_A_LIQUIDITY_SWEEP_REVERSAL — SELECTED FOR STAGE47B DESIGN

Core hypothesis:

XAUUSD frequently probes visible session-range liquidity beyond prior range highs/lows. A subset of these probes fail, close back inside the reference range, and then mean-revert toward the range midpoint or opposite liquidity pool. The intended edge is not continuous trend/context ranking; it is failed breakout reversal after a predefined liquidity sweep.

Why this is structurally new enough:

- It is not a rescue of Stage41/42/43 archived candidates.
- It does not continue Stage46 external context ranking.
- It is not a simple Asia/London breakout; it specifically tests failed breakout/re-entry after a sweep.
- It can be tested using existing candle/session data without ML or external macro feeds.
- It naturally targets fewer trades with larger expected excursion than very short-horizon context filters.

Predefined reference ranges:

```text
Asia reference range: 00:00-06:59 UTC
London active window: 07:00-10:59 UTC
NY active window: 13:00-16:59 UTC
Optional prior-day reference: previous UTC day high/low
```

Signal template:

```text
Long reversal candidate:
1. Price sweeps below a predefined reference low by at least sweep_threshold.
2. A confirmation candle closes back inside the reference range.
3. Entry is evaluated at confirmation close plus cost assumptions.
4. Stop is below the sweep extreme plus buffer.
5. Target is range midpoint, opposite side, or fixed R multiple.

Short reversal candidate:
1. Price sweeps above a predefined reference high by at least sweep_threshold.
2. A confirmation candle closes back inside the reference range.
3. Entry is evaluated at confirmation close plus cost assumptions.
4. Stop is above the sweep extreme plus buffer.
5. Target is range midpoint, opposite side, or fixed R multiple.
```

Predefined scan grid, not optimized after failure:

```text
timeframe = M5 or M15
reference_range = Asia range or prior-day range
active_window = London or NY
sweep_threshold = max(0.10, 0.20, 0.35 ATR_M15)
confirmation = close_back_inside or close_back_inside_plus_0.10_ATR
stop_buffer = max(observed_spread_p75, 0.05 ATR_M15)
target = midpoint, opposite_side, 1R, 1.5R
max_trades = 1 per side per reference range per day
```

Cost model requirements:

```text
Use observed spread if available.
If no bid/ask spread is available, run conservative sensitivity:
- cost_1x = baseline assumed spread/slippage
- cost_2x = double cost
- cost_3x = triple cost
No candidate may be promoted unless it remains positive under at least the defined base cost and is not fragile under sensitivity.
```

Stage47B must report:

```text
candidate_count
strict_survivor_count
soft_survivor_count
mean_net_bps
median_net_bps
oos_mean_net_bps
worst_quarter_net_bps
bootstrap_p10_net_bps
trade_count
trades_per_month
avg_hold_minutes
session_breakdown
cost_sensitivity_1x_2x_3x
benchmark_residual_bps
failure_bucket_counts
```

Stage47B kill-switch:

```text
KILL if strict_survivor_count == 0 and soft_survivor_count == 0
KILL if all candidates have mean_net_bps <= 0 after base cost
KILL if all candidates have oos_mean_net_bps <= 0
KILL if best candidate has bootstrap_p10_net_bps <= 0
KILL if best candidate depends on one narrow quarter/year only
KILL if results require adding/removing bad buckets after seeing failures
KILL if cost_2x flips every candidate negative
```

Decision:

```text
PROCEED_TO_STAGE47B_SCAN_DESIGN
```

This is not a promotion. This only authorizes a predefined scan design/implementation package for the selected thesis.

---

### STRUCT47_B_SCHEDULED_MACRO_POST_SHOCK_REACTION — DEFER

Core hypothesis:

Gold may show tradable post-event continuation or reversal after scheduled high-impact US macro releases once the initial spread/liquidity shock stabilizes.

Reason to defer:

- Potentially structurally valid and higher-excursion.
- Requires reliable event calendar data and event timestamp normalization.
- Must avoid first-spike execution and news-spread traps.
- Not suitable as the immediate next scan unless event data is added first.

Predefined event classes if later revived:

```text
CPI
NFP
FOMC decision / press conference
PCE inflation
ISM PMI
Retail sales
GDP advance/revision
```

Decision:

```text
DEFER_UNTIL_EVENT_CALENDAR_DATA_EXISTS
```

---

### STRUCT47_C_MULTI_DAY_COMPRESSION_BREAKOUT — REJECT FOR NOW

Core hypothesis:

Multi-day compression may precede larger directional expansion in XAUUSD.

Reason to reject now:

- It overlaps too much with ATR/range expansion and higher-timeframe breakout families already conceptually close to the baseline lab.
- Without a stronger structural trigger, it risks repeating cost-overwhelmed range/volatility scans.

Decision:

```text
REJECT_LOW_INCREMENTAL_NOVELTY
```

---

### STRUCT47_D_REFERENCE_FEED_OR_CONTEXT_SANITY_EXTENSION — REJECT

Core hypothesis:

Use reference-feed/context relationships to filter or sanity-check XAUUSD signals.

Reason to reject:

- Too close to the closed Stage46 external-context branch.
- High risk of being an indirect rescue of a failed path.

Decision:

```text
REJECT_STAGE46_OVERLAP
```

## Final Stage47A conclusion

```text
stage47a_decision = START_NEW_STRUCTURAL_SCAN_DESIGN
selected_thesis = STRUCT47_A_LIQUIDITY_SWEEP_REVERSAL
promotion = NO_GO
next_allowed_step = STAGE47B_LIQUIDITY_SWEEP_REVERSAL_SCAN_DESIGN
```

The project should not pause yet. There is one sufficiently distinct, cost-aware, rule-based thesis worth one predefined scan-design pass. If Stage47B also produces no survivors, the project should strongly consider pause/archive rather than inventing more filters.
