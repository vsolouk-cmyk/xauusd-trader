# Commercial Closure H1-row horizon repair

## Root cause

Stage178's directional target uses:

- entry = `H1.open.shift(-1)`
- exit = `H1.close.shift(-horizon)`

The first Commercial Closure implementation instead used:

- entry timestamp = signal timestamp + 1 clock hour
- exit timestamp = signal timestamp + 24 clock hours

These contracts differ across weekends, holidays, broker maintenance gaps and
missing bars. The mismatch caused artificial M5 coverage loss and could alter
trade P&L, especially in the 2025+ holdout.

## Repair

The sprint now loads the exact ordered AMarkets H1 sequence from the aligned
database and uses row positions:

- entry bucket = H1 row `i + 1`
- exit bucket = H1 row `i + horizon`

Entry and exit M5 buckets must still contain all 12 bars. No gate, threshold,
candidate, cost floor or risk rule was changed.

The previous `KILL_CURRENT_COMMERCIAL_FORMULATION` result must not be used
because it was generated under the wrong horizon contract.
