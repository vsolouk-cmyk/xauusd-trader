# Stage 18C Near-Miss Refinement Lab

Stage18B found many exact-positive watchlist candidates but no promotions.

Stage18C refines only the strongest near-miss families:

```text
1. pdl_sweep_reclaim_long_controlled
2. asia_high_breakout_long
```

## Why

Stage18B showed:

```text
EXACT_WATCHLIST_POSITIVE_ONLY
promoted_to_stage18c = 0
exact_watchlist_positive = 10
```

The best candidates were positive but mostly failed because of cost x4 fragility or bootstrap lower-tail weakness.

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage18c_near_miss_refinement_lab
cat data/reports/stage18c_near_miss_refinement_lab/stage18c_near_miss_refinement_lab.md
```

For quick debug:

```bash
python3 -m app.stage18c_near_miss_refinement_lab --fast
```

## What it tests

For previous-day low sweep/reclaim:

```text
sweep_min grid
reclaim_max grid
London/New York vs NY-only
horizon 3/4/6/8 M15 bars
cooldown 0/4
```

For Asia high breakout:

```text
close_above_asia_high grid
Asia range min/max grid
London/New York vs London-only vs NY-only
horizon 24/32/48 M15 bars
cooldown 0/4
```

## Checks

```text
exact M1 path
cost x1/x2/x4
70/30 and 80/20 chronological splits
2026 segment
year/quarter breadth
bootstrap lower tail
```

## Decisions

```text
REFINED_PROMOTIONS_FOUND
REFINED_WATCHLIST_ONLY
NO_REFINED_VARIANTS_SURVIVED
```

Per-variant:

```text
PROMOTE_FORWARD_SHADOW_DESIGN_CANDIDATE
KEEP_REFINED_WATCHLIST
REJECT_REFINED_VARIANT
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
