# Stage76B K06 MT5 Observer EA Compile Fix

## Purpose

This patch replaces `mt5/K06_ObserverOnly_EA.mq5` inside the project with the corrected observer-only EA so Stage76 and the MT5 handoff use the same compile-safe file.

## Why

The prior EA could fail on some MQL5 builds with:

```text
constant variable cannot be passed as reference
K06_ObserverOnly_EA.mq5 55 29
```

The fix avoids passing a constant/temporary string into functions that mutate strings by reference. `ParseBool()` now copies the input into a mutable local variable before trimming/lowercasing.

## Scope

- Updates only the observer EA source file.
- Does not change K06 thresholds.
- Does not change Stage76 signal logic.
- Does not authorize orders.

## Daily operating rule

The EA file is installed/compiled only when the EA source changes. Daily updates should only refresh the CSV bridge:

```text
data/mt5_bridge/k06_observer_signal.csv
```

and copy/write it to `MQL5/Files/k06_observer_signal.csv`.

## Hard blocks

- NO_AUTOMATED_ORDER
- NO_PAPER_ORDER
- NO_BROKER_CONNECTION
- NO_ORDER_SEND_IN_EA
- OBSERVER_ONLY_EA
- NO_PAPER_LIVE
- NO_LIVE
