# Stage80A pandas 3.14 Compatibility Fix

## Decision
- status: `STAGE80A_FIX_READY_NO_PROMOTION`
- decision: `PATCH_STAGE80_PANDAS314_NUMERIC_CONVERSION_NO_ORDER`

## Fix
Stage80 used `pd.to_numeric(..., errors="ignore")`. In newer pandas/Python environments this can raise `ValueError: invalid error value specified`.

The patch replaces that with `errors="coerce"` plus a preservation guard:

- numeric or partially numeric columns are converted deterministically;
- purely non-numeric metadata columns remain unchanged;
- no strategy thresholds, rules, gates, or portfolio decisions are changed.

## Hard blocks
- `NO_AUTOMATED_ORDER`
- `NO_PAPER_ORDER`
- `NO_BROKER_CONNECTION`
- `NO_EA_PROMOTION`
- `NO_LIVE`
- `NO_ORDER_AUTHORIZATION_FROM_STAGE80A`
