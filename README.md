# xauusd-trader

Commercial XAUUSD/gold trading research pipeline.

## Current stage

Stage 4C: selected scenario validation.

No ML. No trading bot. No paper order. No live order.

## Selected scenario

```text
long-only
TP = 24 USD
SL = 15 USD
```

## Local commands

Stage 4B:

```bash
python3 -m app.xauusd_stage4b_tpsl_scenario_lab
```

Stage 4C:

```bash
python3 -m app.xauusd_stage4c_selected_scenario_validate
```

## Local-only data

Do not commit:

```text
data/second_source/second_source.sqlite
data/second_source/manifest.json
data/reports/
```

## Hard rule

Stage 4C does not authorize demo, paper-order, or live trading.
