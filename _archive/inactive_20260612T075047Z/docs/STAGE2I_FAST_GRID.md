# Stage 2I Fast Grid Patch

## Purpose

Stage 2D runtime was still high because the grid lab created Python objects and optional trade records while evaluating many variants.

This patch makes Stage 2D vectorized.

## What changed

- Uses NumPy arrays for signal/trade calculations.
- Does not build full trade CSV unless explicitly requested.
- Keeps the same summary/evaluations outputs.
- Adds pip cache to GitHub workflows.
- Removes `pip install --upgrade pip` to reduce workflow overhead.

## Normal command

```bash
python3 -m app.xauusd_stage2d_grid_lab --data-db data/store/xauusd.sqlite
```

## Debug command with full trades

```bash
python3 -m app.xauusd_stage2d_grid_lab --data-db data/store/xauusd.sqlite --save-full-trades
```

## Expected improvement

The `runtime_seconds` inside Stage 2D summary should drop materially.

GitHub total runtime will still include checkout, setup-python, pip install, Telegram, and artifact upload.
