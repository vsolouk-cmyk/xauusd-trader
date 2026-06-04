# Stage 2D Runtime Policy

## Problem

The Stage 2D step became slow because the script was creating a full per-trade CSV for every grid variant. That file is useful for debugging, but not for routine evaluation.

## Current policy

Routine Stage 2D runs save:

- summary JSON/MD,
- grid evaluations CSV.

Routine Stage 2D runs do **not** save:

- full per-trade CSV.

This is controlled by:

```yaml
output:
  save_full_trades: false
```

## Debug mode

To create the full trades CSV locally:

```bash
python3 -m app.xauusd_stage2d_grid_lab --data-db data/store/xauusd.sqlite --save-full-trades
```

Do not use debug mode for routine GitHub runs.
