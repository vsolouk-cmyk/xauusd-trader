# Stage 22A Trend Pullback Short Targeted Exact Refinement

Stage21B was positive but not robust enough for forward-shadow design.

Stage22A performs a limited exact-M1 refinement of the same behavior family.

## Why

Stage21B weaknesses:

```text
net_x4 negative / PF below 1
test/2026 median negative
bootstrap lower tail weak
large drawdown
```

## Refinement dimensions

```text
trend_dist: 5.0, 7.5, 10.0, 12.5
pullback: 0.0, 0.5, 1.0, 2.0
slope_min: 0.0, 2.0, 5.0
sma50_dist: 0.0, 5.0, 10.0
horizon_bars: 4, 8, 12, 16
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage22a_trend_pullback_short_refinement
cat data/reports/stage22a_trend_pullback_short_refinement/stage22a_trend_pullback_short_refinement.md
```

For a fast debug run:

```bash
python3 -m app.stage22a_trend_pullback_short_refinement --fast
```

## Decisions

```text
REFINED_TREND_PULLBACK_PROMOTIONS_FOUND
REFINED_TREND_PULLBACK_WATCHLIST_ONLY
REFINED_TREND_PULLBACK_REJECTED
```

Per-variant:

```text
PROMOTE_FORWARD_SHADOW_DESIGN_CANDIDATE
KEEP_REFINED_WATCHLIST
REJECT_REFINED_WEAK
REJECT_TOO_FEW_EVENTS
```

## Important

Stage22A is targeted exact historical refinement, not forward proof.

If no promotion appears, this trend-pullback short family should be frozen as watchlist-only.

## Hard rule

Research refinement only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to order
```
