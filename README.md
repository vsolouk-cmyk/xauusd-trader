# xauusd-trader

Commercial XAUUSD/gold trading research pipeline.

## Current stage

Stage 4F: demo-readiness pack for locked XAUUSD candidate.

No ML. No trading bot. No paper order. No live order.

## Locked candidate v1

```text
long-only
TP = 24 USD
SL = 15 USD
blocked session = London 07:00-13:00 UTC
```

## Local commands

Stage 4E:

```bash
python3 -m app.xauusd_stage4e_session_filter_validate
```

Stage 4F:

```bash
python3 -m app.xauusd_stage4f_demo_readiness_pack
```

## Local-only data

Do not commit:

```text
data/second_source/second_source.sqlite
data/second_source/manifest.json
data/reports/
```

## Hard rule

Stage 4F authorizes demo-design only, not demo execution, paper-order, or live trading.
