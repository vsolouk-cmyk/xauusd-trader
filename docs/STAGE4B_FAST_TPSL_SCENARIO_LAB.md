# Stage 4B Fast TP/SL Scenario Lab

## Problem

The first Stage 4B implementation was too slow because it repeatedly filtered the full M1 dataframe for every signal and every scenario.

## Fix

This optimized version:

- precomputes base H1 signals once,
- maps them to M1 entry/exit indexes once,
- precomputes TP/SL hit indexes once per trade,
- evaluates scenarios from precomputed arrays.

## Local command

```bash
python3 -m app.xauusd_stage4b_tpsl_scenario_lab
```

## Expected runtime

On a 2015 MacBook, this should be much faster than the first version. If it still runs for more than a few minutes, stop it and report the last visible output.
