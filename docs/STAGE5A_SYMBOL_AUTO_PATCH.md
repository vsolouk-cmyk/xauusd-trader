# Stage 5A Symbol Auto Patch

## Problem

The first EA version forced `InpSymbol = XAUUSD`.

On some MT5/Wine installations, `SymbolSelect("XAUUSD", true)` can fail even when the EA is attached to an XAUUSD chart.

## Fix

The EA now defaults to:

```text
InpSymbol = AUTO
```

When `AUTO` is used, the EA uses the chart symbol:

```text
_Symbol
```

## Expected Experts log

```text
Using chart symbol: XAUUSD
XAUUSD_DryRun_v1 initialized. HARD RULE: no order placement.
Resolved symbol=XAUUSD | chart symbol=XAUUSD | input=AUTO
```

No order placement code was added.
