# Stage 16C True-Forward Shadow Collector

Stage 16C starts a persistent true-forward shadow journal.

## Why this exists

Stage 16B showed recent-history shadow outcomes were positive, but not forward proof.

Stage 16C fixes that by creating a collector boundary:

```text
collector_start_utc
```

Only signals after that timestamp can count as true-forward.

## Research setup

```text
prev_day_low_sweep_rejection
LONG research direction
sweep_depth >= 1.62
reclaim_above_prev_day_low < 1.55
real_yield_10y_chg5 > 0
entry = next M15 open
exit = 60 minutes after entry
cost = 0.35
```

## Run

First run initializes the collector start boundary:

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage16c_true_forward_shadow_collector
cat data/reports/stage16c_true_forward_shadow_collector/stage16c_true_forward_shadow_collector.md
```

Repeat after refreshing the local store:

```bash
python3 -m app.stage16c_true_forward_shadow_collector
```

## Outputs

```text
data/reports/stage16c_true_forward_shadow_collector/stage16c_collector_state.json
data/reports/stage16c_true_forward_shadow_collector/stage16c_true_forward_shadow_journal.csv
data/reports/stage16c_true_forward_shadow_collector/stage16c_scan_candidates.csv
data/reports/stage16c_true_forward_shadow_collector/stage16c_true_forward_shadow_collector.json
data/reports/stage16c_true_forward_shadow_collector/stage16c_true_forward_shadow_collector.md
```

## Possible decisions

```text
TRUE_FORWARD_STARTED_NO_SIGNALS_YET
NO_VALID_TRUE_FORWARD_SIGNALS_YET
TRUE_FORWARD_COLLECTION_ACTIVE_INSUFFICIENT_CLOSED
TRUE_FORWARD_SHADOW_POSITIVE_EARLY
TRUE_FORWARD_SHADOW_WEAK_OR_NEGATIVE
```

## Hard rule

Research shadow collection only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to order
```
