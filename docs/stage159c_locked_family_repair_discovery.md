# Stage159C Locked-Family Repair Discovery Hotfix

Stage159C fixes a pandas dtype error in the chronological fold assignment.

The failed Stage159B run wrote failure-safe artifacts with:

`TypeError: Invalid value '<ArrowStringArray ... F1_OLD ... F4_RECENT ...>' for dtype 'int64'`

Root cause: the `fold` column was initialized as an integer column and then string fold labels were assigned. Newer pandas/pyarrow-backed dtypes reject this assignment.

Fix: initialize `fold` as an object/string column before assigning labels.

This stage remains read-only/offline. It does not write any execution KV and does not send orders.
