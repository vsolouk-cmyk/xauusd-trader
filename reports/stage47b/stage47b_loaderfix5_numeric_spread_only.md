# Stage47B LoaderFix5 — Numeric Spread Only

## Problem fixed

LoaderFix4 selected the correct M5 normalized CSV but mapped `spread_available` to the numeric `spread` field. Since `spread_available` contains boolean strings such as `False`, every row failed parsing with:

```text
ValueError("could not convert string to float: 'False'")
```

## Fix

- `spread_available`, `has_spread`, and similar boolean metadata fields are never mapped as numeric spread.
- Numeric spread mapping now prefers `spread_close`, `spread`, `spread_points`, `spread_pips`, and bid/ask-derived spread.
- If no numeric spread exists, candle rows are still accepted and the predefined cost assumption is used.
- CSV diagnostic output now reports whether a numeric spread column was found and whether boolean spread metadata was present.

## Status

Research-only. No promotion, EA, paper-live, or live action is allowed from this patch.
