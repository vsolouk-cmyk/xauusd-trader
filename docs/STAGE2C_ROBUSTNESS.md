# Stage 2C Robustness Diagnostics

## Purpose

Stage 2C tests whether a Stage 2B candidate is robust or just outlier-driven.

## What it checks

- Remove top 1 winning trade.
- Remove top 5 winning trades.
- First half vs second half.
- Remove the best month.
- Stress trading costs.
- Direction breakdown.

## Key definitions

- Outlier: an unusually large result that can dominate totals.
- Cost stress: rerun metrics with higher assumed trading costs.
- Profit factor: gross wins divided by gross losses. Above 1 means wins exceed losses before other judgments.
- Best-month dependency: a strategy that only works because of one unusually good month.

## Local command

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.xauusd_stage2c_robustness
```

This expects Stage 2B output to already exist.

## Full local sequence

```bash
cd ~/Desktop/xauusd-trader
export TWELVEDATA_API_KEY='PASTE_KEY_HERE'
python3 -m app.xauusd_stage1_snapshot --outputsize 5000
python3 -m app.xauusd_stage2b_validate_baselines
python3 -m app.xauusd_stage2c_robustness
```

## GitHub workflow

Run manually:

```text
XAUUSD Stage 2C Robustness Diagnostics
```

## Interpretation

- `stage2c_robust_candidate_found`: candidate deserves deeper baseline refinement and forward-shadow planning later.
- `no_stage2c_robust_candidate`: do not proceed to ML. Fix data/backfill/baseline definitions first.
