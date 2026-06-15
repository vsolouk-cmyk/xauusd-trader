# Stage36B HF2 — Explicit TS Alias Fix

HF1 could still crash with `KeyError: 'ts'` on SQLite schemas where raw selected columns did not normalize cleanly after pandas rename.

HF2 fixes this by selecting OHLC columns with explicit SQL aliases:

- `AS ts`
- `AS open`
- `AS high`
- `AS low`
- `AS close`

It also records an audit error instead of crashing if normalized columns are still missing.

No EA, paper-live, or order behavior is changed.
