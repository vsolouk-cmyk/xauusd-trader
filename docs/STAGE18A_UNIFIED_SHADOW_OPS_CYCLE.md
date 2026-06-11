# Stage 18A Unified Shadow Ops Cycle

Stage 18A is the preferred manual loop for active shadow candidates.

It does:

```text
1. Import AMarkets CSVs once.
2. Run Stage16C macro pressure/reversal sweep collector.
3. Run Stage17D broker-time PDH breakout continuation collector.
4. Produce one consolidated dashboard report.
```

## Default files

```text
~/Downloads/amarkets_xauusd_1h.csv
~/Downloads/amarkets_xauusd_1m.csv
```

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage18a_unified_shadow_ops_cycle
cat data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.md
```

## Explicit files

```bash
python3 -m app.stage18a_unified_shadow_ops_cycle \
  --csv-file ~/Downloads/amarkets_xauusd_1h.csv \
  --csv-file ~/Downloads/amarkets_xauusd_1m.csv
```

## Outputs

```text
data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.md
data/reports/stage18a_unified_shadow_ops_cycle/stage18a_unified_shadow_ops_cycle.json

data/reports/stage16c_true_forward_shadow_collector/stage16c_true_forward_shadow_collector.md
data/reports/stage17d_broker_time_forward_shadow_collector/stage17d_broker_time_forward_shadow_collector.md
data/reports/stage16e_amarkets_csv_refresh_cycle/stage16e_amarkets_csv_refresh_cycle.md
```

## Decisions

```text
UNIFIED_ACTIVE_NO_SIGNAL_YET
UNIFIED_FORWARD_SIGNAL_OPEN
UNIFIED_FORWARD_OUTCOME_AVAILABLE
UNIFIED_LATE_DETECTED_REVIEW_CADENCE
UNIFIED_CYCLE_IMPORT_FAILED
UNIFIED_CYCLE_BOTH_COLLECTORS_FAILED
```

## V2/EA signal note

If an external V2/EA dry-run logs a signal, compare it against the Stage16C/Stage17D journals.

Do not treat it as an order signal.

## Hard rule

Research shadow operations only:

```text
No EA change
No automatic trading
No paper/live authorization
No direct conversion to order
```
