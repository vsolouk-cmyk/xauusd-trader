# xauusd-trader

Commercial XAUUSD/gold trading research pipeline.

## Current stage

Stage 4E: session-filter validation for selected long TP/SL scenario.

No ML. No trading bot. No paper order. No live order.

## Selected scenario

```text
long-only
TP = 24 USD
SL = 15 USD
```

## Local commands

Stage 4D:

```bash
python3 -m app.xauusd_stage4d_exact_selected_replay
```

Stage 4E:

```bash
python3 -m app.xauusd_stage4e_session_filter_validate
```

## Local-only data

Do not commit:

```text
data/second_source/second_source.sqlite
data/second_source/manifest.json
data/reports/
```
