# STAGE38I Drift-Adjusted Survivor Audit Review

## Verdict

`STAGE38I_DRIFT_ADJUSTED_SURVIVOR_AUDIT = PASS`

`decision = DRIFT_ADJUSTED_WATCH_ONLY_NO_PROMOTION`

No Stage38 candidate earned promotion after adjusting for the dominant XAUUSD bull drift baseline.

## Audit snapshot

```text
status = PASS
decision = DRIFT_ADJUSTED_WATCH_ONLY_NO_PROMOTION
drift_reference_rows = 3
source_tables_scanned = 5
missing_source_table_count = 0
items_written = 173
strict_pass_count = 0
watch_count = 2
context_only_watch_count = 31
no_promotion_count = 126
warning_count = 0
note_count = 0
```

## Main finding

The dominant observation from Stage38H remains intact: many apparently positive forward-return candidates are largely explained by the underlying long-side drift in gold, especially during 2025.

After subtracting the daily drift reference:

- no candidate achieved `PASS_DRIFT_ADJUSTED_SURVIVOR_WATCH`,
- only two event-clock policies remained as weak watch-only residuals,
- all context-only candidates remain non-promotable because they did not pass event-clock accounting,
- composite overlays did not improve on the strongest GLD-only gate.

## Only event-clock survivors

### 1. Stage38F GLD gate / BLOCK_FLOW_20D_OUTFLOW / 120H

```text
source_stage = Stage38F_GLD_GATE
item_type = EVENT_CLOCK_GATE
horizon = 120H
item = BLOCK_FLOW_20D_OUTFLOW
policy_role = avoid_long_overlay
source_event_count = 1030
trade_count = 833
skipped_count = 197
raw_mean_bps = 55.55
event_clock_mean_bps = 44.92
drift_reference_mean_bps = 38.85
drift_adjusted_bps = +6.07
stage_uplift_bps = +7.37
positive_year_count = 5
negative_year_count = 0
max_positive_year_share = 0.471
worst_loo_mean_bps = 31.35
worst_loo_excluded_year = 2025
survivor_decision = WATCH_DRIFT_ADJUSTED_RESIDUAL_ONLY
note = MARGINAL_DRIFT_ADJUSTED_RESIDUAL_LT_8BPS
```

This is the strongest residual. However, the drift-adjusted residual is only `+6.07 bps`, below the minimum threshold for promotion.

### 2. Stage38F GLD gate / BLOCK_FLOW_20D_OUTFLOW / 72H

```text
source_stage = Stage38F_GLD_GATE
item_type = EVENT_CLOCK_GATE
horizon = 72H
item = BLOCK_FLOW_20D_OUTFLOW
policy_role = avoid_long_overlay
source_event_count = 1032
trade_count = 835
skipped_count = 197
raw_mean_bps = 32.60
event_clock_mean_bps = 26.37
drift_reference_mean_bps = 23.04
drift_adjusted_bps = +3.33
stage_uplift_bps = +4.67
positive_year_count = 5
negative_year_count = 0
max_positive_year_share = 0.472
worst_loo_mean_bps = 18.36
worst_loo_excluded_year = 2025
survivor_decision = WATCH_DRIFT_ADJUSTED_RESIDUAL_ONLY
note = MARGINAL_DRIFT_ADJUSTED_RESIDUAL_LT_8BPS
```

This is weaker than the 120H variant and cannot be promoted.

## Context-only residuals

Several context-only rows show large drift-adjusted values, especially some GLD and macro contexts. These are not promotable because they did not survive event-clock gate accounting. The most important examples:

- macro pressure/risk: `REAL_YIELD_FLAT+USD_UP__RISK_NORMAL / 120H`
- GLD: `ETF_STRONG_OUTFLOW__HOLDING_Z_NEUTRAL / 120H`
- GLD: `FLOW_20D_STRONG_INFLOW / 120H`
- GLD: `ETF_STRONG_OUTFLOW / 120H`
- GLD: `ETF_STRONG_INFLOW / 120H`
- macro: `VIX_5D_UP / 120H`

These are allowed only as annotation/watchlist features, not as trading logic.

## Final Stage38 decision

```text
STAGE38_ACTIVE_RESEARCH = ARCHIVE
STAGE38_TO_STAGE39_PROMOTION = NO-GO
EA = NO-GO
PAPER_LIVE = NO-GO
LIVE = NO-GO
```

## Why Stage38 must be archived

The full Stage38 branch tested:

1. T1 structural filter retest,
2. COT data and feature overlays,
3. H1 simple baselines,
4. M5/M15 session baselines,
5. macro/risk features,
6. GLD ETF holdings/flow features,
7. composite exogenous overlays,
8. bull-drift baseline,
9. drift-adjusted survivor audit.

The final benchmark-corrected result is that no candidate has enough residual edge after accounting for market drift and event-clock opportunity cost.

## What remains useful

The following data foundations are useful and should remain in the repository:

- COT weekly normalized features,
- FRED macro/risk daily features,
- SPDR GLD daily holdings/flow features,
- anti-lookahead H1 joins,
- diagnostic framework and event-clock methodology.

They are useful as context/annotation and for later candidate diagnostics, not as standalone signal logic.

## Recommended next direction

Do not extend Stage38 with more filters. The correct next branch should be benchmark-first and should test whether any candidate can beat:

- daily drift,
- H1 overlapped drift,
- year-split drift,
- cost-stressed returns,
- MAE/MFE tradability constraints.

A clean next-stage candidate is:

`Stage39A_BENCHMARK_FIRST_REVERSAL_OR_MEAN_REVERSION_SCAN`

But Stage39 here must be treated as a new research-stage label, not as EA/paper/live promotion.

## Commit recommendation

Commit this archive state before starting the next branch.
