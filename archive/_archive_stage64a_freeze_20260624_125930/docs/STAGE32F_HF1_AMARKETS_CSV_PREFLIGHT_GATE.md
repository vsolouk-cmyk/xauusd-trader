# Stage32F-HF1 — AMarkets CSV Preflight Gate

## Purpose

This stage prevents wasting 10–15 minutes on the heavy Stage32F wrapper when the newly exported AMarkets CSV files have not advanced enough to create useful forward-shadow samples.

The gate runs **before** import/wrapper execution.

## Command

Use explicit file paths when possible:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage32f_amarkets_csv_preflight \
  --h1-csv ~/Downloads/XAUUSD_H1.csv \
  --m1-csv ~/Downloads/XAUUSD_M1.csv
```

Or let the tool scan Downloads:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage32f_amarkets_csv_preflight --csv-dir ~/Downloads
```

## Decision meanings

```text
RUN_WRAPPER_RECOMMENDED
```

H1 CSV has advanced compared with the DB and crossed at least one tracked signal hour. Run:

```bash
python3 -m app.stage32f_extended_shadow_refresh_cycle --run-active-wrapper
```

```text
SKIP_H1_NOT_ADVANCED
```

The H1 CSV max timestamp is not newer than the DB H1 max timestamp. Do not run the wrapper yet.

```text
RUN_BUT_LOW_SAMPLE_PROBABILITY
```

The H1 CSV advanced, but no tracked signal hour was crossed. Running is allowed, but expected sample gain is low unless pending outcomes resolve.

```text
RUN_WRAPPER_RECOMMENDED_NO_DB_BASELINE
```

The CSV is readable but DB baseline could not be read. Run wrapper once to establish or repair the baseline.

## Default tracked hours

```text
9,12,13,14,15
```

These match the currently active Stage32 focus families: calendar h9/h13, volatility h12, and handoff h13/h14/h15.

Override if needed:

```bash
python3 -m app.stage32f_amarkets_csv_preflight --target-hours 9,12,13,14,15
```

## Output files

```text
data/reports/stage32f_amarkets_csv_preflight/stage32f_preflight.md
data/reports/stage32f_amarkets_csv_preflight/stage32f_preflight.json
```

## Operational policy

Do not run repeated Stage32F wrapper cycles unless this preflight says the wrapper is worth running.

If three real CSV refreshes pass and Stage32F still shows no increase in `ledger_rows` and no decrease in `leading_remaining_to_extended_min`, kill the current Stage32F collection path and return to Stage32B intake expansion / repair.
