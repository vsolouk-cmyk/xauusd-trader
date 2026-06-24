# Stage64E - Reduced-Scope P0+VIX Predeclaration

Stage64E is a governance and specification stage. It does not run historical validation.

## Purpose

Stage64D5 showed that P0 plus VIX data are ready while full macro-regime scope is blocked by missing ETF, central-bank, and event-calendar files. Stage64E explicitly predeclares a reduced-scope feasibility track using:

- gold D1 OHLC proxy
- DXY daily
- real yield/proxy daily
- VIX daily

This is a feasibility proxy scope only. It must not be interpreted as full macro-regime thesis validation.

## Important source warning

The gold D1 file is currently a COMEX continuous gold futures reference. It is not broker spot XAUUSD. Any later validation must either:

1. treat it as a reference gold proxy; or
2. replace it with broker/spot D1 history before validation.

## Prohibited actions

Stage64E does not authorize:

- historical validation scan
- paper-order
- paper-live
- live
- EA promotion
- broker connection

## Next stage

`Stage64F_REDUCED_SCOPE_LAG_SAFE_FEATURE_DATASET_PREFLIGHT_NO_VALIDATION`
