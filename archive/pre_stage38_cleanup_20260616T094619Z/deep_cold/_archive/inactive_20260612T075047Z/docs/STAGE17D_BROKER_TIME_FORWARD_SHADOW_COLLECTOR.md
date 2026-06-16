# Stage 17D Broker-Time Forward Shadow Collector

Stage 17D starts research-only forward-shadow collection for:

```text
pdh_breakout_continuation_long_h32_cool4
```

## Why broker-time

Stage 17C showed that AMarkets/MT5 bar timestamps are likely broker/server time, not wall-clock UTC.

Therefore Stage 17D uses:

```text
BROKER_BAR_TIME
```

for collector boundaries.

## Setup

```text
side = LONG
signal = completed M15 bar in London/New York breaks above previous-day high and closes above PDH + 0.8
entry = next M15 open
exit = 32 M15 bars later = 8 hours
cooldown = 4 M15 bars
cost = 0.35
```

## First run

The first run initializes the collector boundary:

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage17d_broker_time_forward_shadow_collector
cat data/reports/stage17d_broker_time_forward_shadow_collector/stage17d_broker_time_forward_shadow_collector.md
```

The first run normally gives no signal because it sets:

```text
collector_start_bar_time = latest completed M15 broker-time bar
```

## Repeat after CSV refresh

After updating AMarkets CSV files and running Stage 16E import, run:

```bash
python3 -m app.stage17d_broker_time_forward_shadow_collector
cat data/reports/stage17d_broker_time_forward_shadow_collector/stage17d_broker_time_forward_shadow_collector.md
```

## Important cadence note

The horizon is 8 hours.

If CSV refresh happens only every 24 hours, many signals will be marked:

```text
not_forward_late_detected
```

because the outcome was already visible when the signal was discovered.

For valid forward evidence, refresh cadence should be shorter than the horizon, ideally every 1-4 hours when practical.

## Outputs

```text
data/reports/stage17d_broker_time_forward_shadow_collector/stage17d_collector_state.json
data/reports/stage17d_broker_time_forward_shadow_collector/stage17d_broker_time_forward_shadow_journal.csv
data/reports/stage17d_broker_time_forward_shadow_collector/stage17d_scan_candidates.csv
data/reports/stage17d_broker_time_forward_shadow_collector/stage17d_broker_time_forward_shadow_collector.json
data/reports/stage17d_broker_time_forward_shadow_collector/stage17d_broker_time_forward_shadow_collector.md
```

## Decisions

```text
BROKER_FORWARD_WAITING_FOR_NEW_BAR_DATA
BROKER_FORWARD_ACTIVE_NO_SIGNAL_YET
BROKER_FORWARD_SIGNAL_OPEN
BROKER_FORWARD_OUTCOMES_AVAILABLE_INSUFFICIENT_SAMPLE
BROKER_FORWARD_SHADOW_POSITIVE_EARLY
BROKER_FORWARD_SHADOW_WEAK_OR_NEGATIVE
BROKER_FORWARD_ONLY_LATE_DETECTED_SIGNALS
```

## Hard rule

Research shadow only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to order
```
