# Stage 3D Forward Shadow

## Purpose

Stage 3D starts forward-shadow logging for the fixed candidate.

It does not place orders.

## Fixed candidate

```text
sma10_h12_dist10_cool1
```

## What forward shadow means

The system behaves as if it is trading, but only records:

- entry time,
- direction,
- entry price,
- planned exit time,
- eventual exit price,
- raw/net result.

No real order and no paper order is sent.

## Persistence

Forward shadow database:

```text
data/shadow/forward_shadow.sqlite
```

The GitHub workflow commits this DB so future runs can close previously opened shadow trades.

## Kill-switch

The kill-switch does not stop code execution automatically yet. It reports:

```text
forward_shadow_kill_switch_triggered
```

if closed forward-shadow trades violate configured limits.

## Local command

```bash
python3 -m app.xauusd_forward_shadow
```

## GitHub workflow

```text
XAUUSD Stage 3D Forward Shadow
```

It also runs automatically after:

```text
XAUUSD Persistent Data Store Refresh
```

## Hard rule

Stage 3D is diagnostic only.

No ML. No paper-order. No live trading.
