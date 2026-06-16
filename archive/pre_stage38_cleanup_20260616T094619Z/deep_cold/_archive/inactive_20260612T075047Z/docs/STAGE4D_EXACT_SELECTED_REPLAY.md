# Stage 4D Exact Selected Scenario Replay

## Purpose

Run exact trade-level replay for the locked Stage 4C candidate:

```text
long-only
TP = 24 USD
SL = 15 USD
```

## What it adds

- exact trade-level CSV,
- exact cost stress from raw trade P/L,
- monthly/yearly/session breakdown,
- reference comparison against long-only time-exit,
- demo-readiness checks.

## Local command

```bash
python3 -m app.xauusd_stage4d_exact_selected_replay
```

## Hard rule

Stage 4D is still diagnostic.

It does not authorize demo, paper-order, or live trading.
