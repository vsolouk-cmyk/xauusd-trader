# Stage 4F Demo-Readiness Pack

## Purpose

Stage 4F converts Stage 4E into a locked candidate specification for demo-design.

It does not authorize demo execution.

## Locked candidate

```text
Direction: long-only
TP: 24 USD
SL: 15 USD
Blocked session: London 07:00-13:00 UTC
Allowed: Asia, London-NY overlap, New York, Other
```

## Local command

```bash
python3 -m app.xauusd_stage4f_demo_readiness_pack
```

## Meaning of pass

A pass means:

```text
Ready to design MT5 demo EA / dry-run logging.
Not ready to send demo orders.
Not ready for paper-order.
Not ready for live trading.
```
