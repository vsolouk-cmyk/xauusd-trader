# Stage46A external context baseline scan implementation loaderfix

## Purpose

This loaderfix repairs a runtime-specific NumPy/Pandas boolean mask issue in `evaluate_candidate`.

## Error repaired

```text
ValueError: output array is read-only
```

The error occurred at the candidate-exit mask update step when a boolean mask returned from Pandas/NumPy was backed by a read-only view.

## Fix

Boolean masks are now materialized as writable NumPy arrays before combination with the valid-exit mask. The implementation also avoids the in-place `&=` operation at that point.

## Scope

This is a loader/runtime fix only.

It does not change:

- Stage46 design contract
- candidate families
- thresholds
- evaluation gates
- cost assumptions
- promotion logic
- project gates

All gates remain:

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```
