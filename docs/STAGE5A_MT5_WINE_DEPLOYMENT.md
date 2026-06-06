# Stage 5A MT5 on Wine Deployment Notes

## Purpose

Use MT5 on Wine for dry-run signal logging only.

This is acceptable for development and manual dry-run checks, but not for reliable 24/5 automated demo execution.

## Steps

1. Open MT5.
2. Open MetaEditor.
3. Copy `XAUUSD_DryRun_v1.mq5` into:

```text
MQL5/Experts/XAUUSD/
```

4. Compile.
5. Attach the EA to an XAUUSD chart.
6. Enable Algo Trading only if MT5 requires it for EA ticks. The EA still has no order code.
7. Watch the Experts tab and CSV log.

## Broker symbol

Your broker may not use exactly `XAUUSD`.

Possible names:

```text
XAUUSD
XAUUSDm
XAUUSD.
GOLD
```

Set EA input:

```text
InpSymbol
```

to the exact MT5 symbol.

## Not for 24/5 operation

Wine is okay for export, compile, and manual dry-run logging.

For real demo-order testing later, use a Windows VPS or MetaTrader VPS.
