# Stage 2D Baseline Grid Lab

## Purpose

Stage 2C rejected the previous candidate. Stage 2D checks whether nearby simple baseline variants are more stable.

This is not ML. It is parameterized baseline validation.

## What it tests

- SMA trend variants on 1h.
- Session momentum variants on 15min.
- Range expansion variants on 15min.

Each variant is tested with:

- non-overlap filtering,
- chronological train/test split,
- remove top 5 winners,
- cost x2 stress,
- profit factor threshold.

## Key definitions

- Grid lab: testing a controlled set of simple parameter combinations.
- Train/test split: first part of time series is used for initial evaluation, later part is held out for validation.
- Parameter: a fixed strategy setting, such as SMA window or holding horizon.
- Overfit: when a setting works on one sample but fails on new data.

## Local command

```bash
cd ~/Desktop/xauusd-trader
export TWELVEDATA_API_KEY='PASTE_KEY_HERE'
python3 -m app.xauusd_stage1_snapshot --outputsize 5000
python3 -m app.xauusd_stage2d_grid_lab
```

## GitHub workflow

Run manually:

```text
XAUUSD Stage 2D Baseline Grid Lab
```

Inputs:

```text
intervals: 1min,5min,15min,1h
outputsize: 5000
include_run_link: false
```

## Interpretation

- `stage2d_robust_grid_candidate_found`: continue to deeper validation/backfill.
- `no_stage2d_robust_grid_candidate`: do not proceed to ML; change data source/backfill or baseline family.
