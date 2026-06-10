# Stage 14B Previous-Day Low Sweep Validation

Stage 14B validates the only Stage 14A behavioral candidate:

```text
prev_day_low_sweep_rejection
LONG
horizon_bars = 4
```

This is not a new strategy lab. It is a focused validation.

## Why this stage is necessary

Stage 14A found a candidate:

```text
Events = 377
PF = 1.276455
Median = 0.33
Win rate = 0.522546
```

But the raw average move is small, so cost sensitivity is critical.

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage14b_prev_day_low_sweep_validation
cat data/reports/stage14b_prev_day_low_sweep_validation/stage14b_prev_day_low_sweep_validation.md
```

Optional cost stress:

```bash
python3 -m app.stage14b_prev_day_low_sweep_validation --cost-usd 0.25
python3 -m app.stage14b_prev_day_low_sweep_validation --cost-usd 0.50
```

## Possible decisions

```text
VALIDATION_PASS_FOCUSED_REPLAY_CANDIDATE
FILTER_REQUIRED_COST_SENSITIVE_CANDIDATE
COST_FRAGILE_CANDIDATE
SPLIT_FRAGILE_CANDIDATE
DISTRIBUTION_FRAGILE_CANDIDATE
ROLLING_FRAGILE_CANDIDATE
REJECT_RAW_WEAK
REJECT_TOO_FEW_EVENTS
```

## Hard rule

Research validation only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to signal
```
