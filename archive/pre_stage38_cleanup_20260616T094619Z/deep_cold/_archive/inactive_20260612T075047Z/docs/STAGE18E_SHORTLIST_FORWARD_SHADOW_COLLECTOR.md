# Stage 18E Shortlist Broker-Time Forward Shadow Collector

Stage18E adds only the Stage18D selected shortlist to research-only forward shadow.

## Candidates

```text
C1_PDL_RECLAIM_H6
pdl_sweep_reclaim_long_sweep2.5_reclaim2_london_new_york_h6_cool4

C2_ASIA_HIGH_NY_H48
asia_high_breakout_long_close2_range4-35_new_york_only_h48_cool0
```

## Run standalone

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage18e_shortlist_forward_shadow_collector
cat data/reports/stage18e_shortlist_forward_shadow_collector/stage18e_shortlist_forward_shadow_collector.md
```

## Evidence rule

```text
signal_dt must be after collector_start_bar_time
signal must be detected before exit_target_dt is already available
broker bar time is used for boundaries
```

## Cadence warning

```text
C1 horizon = 90 minutes
C2 horizon = 12 hours
```

Manual daily refresh is too slow for C1 and may be too slow for C2.

## Hard rule

Research shadow only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to order
```
