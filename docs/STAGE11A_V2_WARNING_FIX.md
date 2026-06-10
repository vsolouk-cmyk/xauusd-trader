# Stage 11A v2 Warning Fix

Stage 11A v1 printed repeated pandas warnings:

```text
FutureWarning: Downcasting object dtype arrays on .fillna...
UserWarning: Converting to PeriodArray/Index representation will drop timezone information.
```

These were warnings, not execution errors, but because Stage 11A runs many variants they looked like a loop.

## Fixes

```text
1. Avoid object-dtype fillna(False) on boolean columns.
2. Avoid .dt.to_period("Q") on timezone-aware timestamps.
3. Add progress output every 48 variants.
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage11a_downtrend_short_thesis_lab
cat data/reports/stage11a_downtrend_short_thesis_lab/stage11a_downtrend_short_thesis_lab.md
```

## Optional quieter run

```bash
python3 -m app.stage11a_downtrend_short_thesis_lab --progress-every 0
```

## Hard rule

Research only. No EA change, no paper/live/order authorization.
