# xauusd-trader

Commercial XAUUSD/gold trading research pipeline.

## Current stage

Stage 3E: forward-shadow scanner for the fixed XAUUSD baseline candidate.

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

## Why Stage 3E exists

GitHub Actions cadence can be irregular. Checking only the latest candle can miss signals.

Stage 3E scans every new candle since the last processed candle.

## Local command

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.xauusd_forward_shadow
```

## GitHub workflow

Run manually:

```text
XAUUSD Stage 3D Forward Shadow
```

The workflow name stays the same, but the module now runs Stage 3E scanning logic.

## Hard rule

Forward shadow only records hypothetical signals and outcomes.

It does not authorize ML, paper-order, or live trading.
