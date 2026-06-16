# Stage 18D Promotion Consolidation and Overlap Audit

Stage18C is an exhaustive refinement lab and can be slow. It should not be rerun routinely.

Stage18D reads the existing Stage18C CSV outputs and selects a small non-duplicate shortlist for later forward-shadow design.

## Inputs

```text
data/reports/stage18c_near_miss_refinement_lab/stage18c_refinement_summary.csv
data/reports/stage18c_near_miss_refinement_lab/stage18c_refinement_trades.csv
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage18d_promotion_consolidation
cat data/reports/stage18d_promotion_consolidation/stage18d_promotion_consolidation.md
```

## What it does

```text
1. Reads Stage18C promoted candidates.
2. Computes trade-time overlap between promoted variants.
3. Keeps only a small representative shortlist.
4. Does not create a new forward collector yet.
```

## Default policy

```text
max_per_family = 1
overlap_threshold = 0.80
```

This avoids adding several almost-identical variants to Stage18A.

## Hard rule

Research consolidation only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to order
```
