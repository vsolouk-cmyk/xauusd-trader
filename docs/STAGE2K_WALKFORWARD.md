# Stage 2K Walk-Forward Validation

## Purpose

Stage 2J found stable candidates. Stage 2K checks whether those candidates survive rolling and fold-style validation.

## What it checks

- 5 chronological folds.
- Last fold performance.
- Rolling 25-trade windows.
- Long/short side sanity.
- Last 50 trades.
- Cost x4 stress.

## Key definitions

- Walk-forward validation: testing performance as time moves forward, instead of relying on one aggregate backtest.
- Fold: one chronological segment of trades.
- Rolling window: a moving block of consecutive trades.
- Tail performance: recent trades, such as the last 50 trades.

## Local sequence

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.xauusd_stage2d_grid_lab --data-db data/store/xauusd.sqlite
python3 -m app.xauusd_stage2j_candidate_analysis --data-db data/store/xauusd.sqlite
python3 -m app.xauusd_stage2k_walkforward --data-db data/store/xauusd.sqlite
```

## GitHub workflow

Run manually:

```text
XAUUSD Stage 2K Walk-Forward Validation
```

It also runs after:

```text
XAUUSD Persistent Data Store Refresh
```

## Interpretation

- `stage2k_walkforward_pass_found`: candidate deserves deeper backfill and broker-feed validation.
- `no_stage2k_walkforward_pass`: do not proceed to ML or paper-order.
