# Stage76A MQL Compile Fix

## Purpose
Fix MT5 compile error in `K06_ObserverOnly_EA.mq5`:

`constant variable cannot be passed as reference`

## Cause
In MQL5, `StringToLower()` modifies a string passed by reference. The previous EA passed an expression/const-like input directly through an initializer:

`string v = StringToLower(value);`

Some MT5 builds reject this with the reference error.

## Fix
Copy the input into a mutable local variable first, then call `StringToLower(v);`.

## Safety
The EA remains observer-only. It still contains no order functions and must not include `OrderSend`, `CTrade`, `Buy`, `Sell`, or `PositionOpen` calls.

## Operational note
The EA file only needs to be installed/compiled once unless the EA source changes. Daily operation should update the CSV bridge only.
