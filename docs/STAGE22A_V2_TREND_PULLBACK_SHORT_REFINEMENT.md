# Stage 22A v2 Trend Pullback Short Hybrid Refinement

The original full Stage22A exact grid can run too long.

Stage22A v2 uses a hybrid design:

```text
Phase 1: M15 proxy replay for all variants
Phase 2: exact M1 replay only for top proxy variants
Phase 3: bootstrap only on exact finalists
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage22a_v2_trend_pullback_short_refinement
cat data/reports/stage22a_v2_trend_pullback_short_refinement/stage22a_v2_trend_pullback_short_refinement.md
```

## Optional faster settings

```bash
python3 -m app.stage22a_v2_trend_pullback_short_refinement --exact-top-n 15 --bootstrap-n 50
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

## Hard rule

Research refinement only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to order
```
