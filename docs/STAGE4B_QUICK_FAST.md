# Stage 4B Quick Fast Patch

## Purpose

The previous Stage 4B version was still slow on a 2015 MacBook.

This patch does two things:

1. Reduces the scenario grid.
2. Removes repeated full-M1 timestamp string conversion inside each scenario.

## Quick grid

```text
sides: long, both
TP: none, 18, 24
SL: none, 12, 15
```

That is 18 scenarios.

## Local command

```bash
python3 -m app.xauusd_stage4b_tpsl_scenario_lab
```

The script now prints progress:

```text
Loading H1/M1 data...
Loaded h1_rows=... m1_rows=...
Built signals=...
Precomputed base_trades=... scenarios=...
```
