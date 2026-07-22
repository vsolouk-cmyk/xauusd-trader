# Stage180 — Frozen-Model Parallel Shadow

## Program decision

Stage179 left exactly one failed gate: the lower 10th percentile of the
48-trade moving-block bootstrap was below zero. All structural, parity,
cost-stress, concentration, drawdown and directional checks passed.

Another retrospective statistical test would create test-shopping risk.
Stage180 therefore activates only a zero-capital, observation-only shadow
ledger while research continues in parallel.

## What the cycle does

1. If AMarkets raw CSV files are newer than the Stage177C aligned database,
   it runs the already-approved Stage177C alignment refresh.
2. It loads the exact frozen Stage178 model and feature contract.
3. It imports the exact Stage178 feature builder.
4. It processes all complete H1 bars after model activation.
5. It records probabilities, no-signals and frozen-threshold signals.
6. It resolves each signal with the exact Stage178 target semantics:
   next-bar open to the close 24 future H1 bars later.
7. It never places an order.

## One-command run

```bash
cd ~/Desktop/xauusd-trader

python3 app/stage180_frozen_model_shadow.py
```

To use the current aligned database without checking raw AMarkets file mtimes:

```bash
python3 app/stage180_frozen_model_shadow.py \
  --skip-alignment-refresh
```

## Outputs

```text
reports/stage180_frozen_model_shadow/stage180_summary.json
reports/stage180_frozen_model_shadow/stage180_decision.md
reports/stage180_frozen_model_shadow/stage180_latest_observation.json
reports/stage180_frozen_model_shadow/stage180_observations.csv
reports/stage180_frozen_model_shadow/stage180_signals.csv
reports/stage180_frozen_model_shadow/stage180_resolved_signals.csv

data/local/stage180_frozen_model_shadow/stage180_shadow.sqlite
```

## Operational boundary

This is not paper trading and does not authorize demo or live execution.
The ledger runs in parallel and does not block continued research.
