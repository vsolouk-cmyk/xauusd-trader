# xauusd-trader

Commercial XAUUSD/gold trading research pipeline.

## Current stage

Stage 3D: forward shadow for the fixed XAUUSD baseline candidate.

No ML. No trading bot. No paper order. No live order.

## Fixed candidate

```text
sma10_h12_dist10_cool1
```

## Current stores

Primary market data:

```text
data/store/xauusd.sqlite
```

Forward shadow log:

```text
data/shadow/forward_shadow.sqlite
```

## Local Stage 3D

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.xauusd_forward_shadow
```

## GitHub workflow

Run manually:

```text
XAUUSD Stage 3D Forward Shadow
```

It also runs after:

```text
XAUUSD Persistent Data Store Refresh
```

## Hard rule

Forward shadow only records hypothetical signals and outcomes.

It does not authorize ML, paper-order, or live trading.
