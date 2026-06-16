# Stage 14D Sweep-Depth Filter Robustness

Stage 14D validates the single top Stage 14C filter:

```text
prev_day_low_sweep_rejection
LONG
horizon_bars = 4
filter = sweep_depth_ge_q50
```

## Why

Stage 14C found that this filter passed net-after-cost basic checks. Stage 14D checks whether it is stable enough to justify exact replay.

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage14d_sweep_depth_filter_robustness
cat data/reports/stage14d_sweep_depth_filter_robustness/stage14d_sweep_depth_filter_robustness.md
```

Optional sensitivity:

```bash
python3 -m app.stage14d_sweep_depth_filter_robustness --cost-usd 0.25
python3 -m app.stage14d_sweep_depth_filter_robustness --cost-usd 0.50
```

## Possible decisions

```text
ROBUST_FILTER_CANDIDATE_FOR_EXACT_REPLAY
ROBUST_ENOUGH_FOR_EXACT_REPLAY_BUT_COST_SENSITIVE
REJECT_TOO_FEW_FILTERED_EVENTS
REJECT_NET_EDGE_WEAK
SPLIT_FRAGILE_FILTER
YEAR_DISTRIBUTION_FRAGILE_FILTER
QUARTER_DISTRIBUTION_FRAGILE_FILTER
ROLLING_FRAGILE_FILTER
BOOTSTRAP_FRAGILE_FILTER
```

## Hard rule

Research validation only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to signal
```
