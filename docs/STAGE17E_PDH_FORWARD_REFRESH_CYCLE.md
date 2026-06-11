# Stage 17E PDH Forward Refresh Cycle

Stage 17E is a one-command research-only cycle for the Stage17D broker-time forward collector.

It does:

```text
1. Import AMarkets CSV files with Stage16E.
2. Run Stage17D broker-time forward shadow collector.
3. Summarize fresh data, open signals, closed outcomes, and late-detected invalid signals.
```

## Default files

```text
~/Downloads/amarkets_xauusd_1h.csv
~/Downloads/amarkets_xauusd_1m.csv
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage17e_pdh_forward_refresh_cycle
cat data/reports/stage17e_pdh_forward_refresh_cycle/stage17e_pdh_forward_refresh_cycle.md
```

## Run with explicit files

```bash
python3 -m app.stage17e_pdh_forward_refresh_cycle \
  --csv-file ~/Downloads/amarkets_xauusd_1h.csv \
  --csv-file ~/Downloads/amarkets_xauusd_1m.csv
```

## Output decisions

```text
REFRESH_CYCLE_WAITING_FOR_NEW_BROKER_BARS
REFRESH_CYCLE_ACTIVE_NO_SIGNAL_YET
REFRESH_CYCLE_FORWARD_SIGNAL_OPEN
REFRESH_CYCLE_FORWARD_OUTCOME_AVAILABLE
REFRESH_CYCLE_LATE_DETECTED_ONLY
REFRESH_CYCLE_IMPORT_FAILED
REFRESH_CYCLE_COLLECTOR_FAILED
REFRESH_CYCLE_REVIEW_STAGE17D
```

## Cadence note

The Stage17D horizon is 8 hours.

A 24-hour refresh cadence can discover signals too late, after the outcome is already visible. Such signals are marked invalid for forward proof.

For valid forward evidence, use a shorter cadence when practical:

```text
1-4 hours preferred
```

## Hard rule

Research shadow cycle only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to order
```
