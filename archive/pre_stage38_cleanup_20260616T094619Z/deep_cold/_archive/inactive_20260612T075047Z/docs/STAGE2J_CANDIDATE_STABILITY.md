# Stage 2J Candidate Stability Analysis

## Purpose

Stage 2D found robust grid candidates. Stage 2J checks whether those candidates are stable over time.

## What it tests

For the top robust Stage 2D candidates:

- monthly performance,
- first/middle/last third performance,
- remove top 10 winners,
- cost x3 stress,
- profit factor threshold,
- drawdown-to-total-net sanity.

## Key definitions

- Candidate stability: a baseline remains positive across time segments, not only in one favorable cluster.
- Positive month ratio: fraction of months with positive net result.
- Time thirds: chronological first, middle, and last third of the candidate's trades.
- Cost x3: rerun result with three times the assumed transaction cost.

## Local sequence

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.xauusd_stage2d_grid_lab --data-db data/store/xauusd.sqlite
python3 -m app.xauusd_stage2j_candidate_analysis --data-db data/store/xauusd.sqlite
```

## GitHub workflow

Run manually:

```text
XAUUSD Stage 2J Candidate Stability Analysis
```

This workflow also runs automatically after:

```text
XAUUSD Persistent Data Store Refresh
```

## Interpretation

- `stage2j_stable_candidate_found`: continue to deeper validation/backfill and later forward-shadow design.
- `no_stage2j_stable_candidate`: do not proceed to ML; improve data horizon or baseline families first.
