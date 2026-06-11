# Stage27A Hotfix 1 — Suppress timezone np.datetime64 warning at source

This hotfix updates `app/stage27a_db_first_outcome_surface_discovery.py`.

## Fix

The M1 replay loop no longer converts timezone-aware pandas timestamps with `np.datetime64(...)`.
Instead, it converts both candle timestamps and event timestamps to UTC nanosecond integers and uses `np.searchsorted` on those integer arrays.

This removes repeated warnings like:

```text
UserWarning: no explicit representation of timezones available for np.
```

## Guardrails

- Research/shadow discovery only.
- No EA change.
- No paper/live/order authorization.
- No market CSV fallback is added.
- Stage18A, Stage23D, and Stage25D are unchanged.

## Checks performed

- `python3 -m py_compile app/stage27a_db_first_outcome_surface_discovery.py`
- Smoke test of `replay_m1(...)` using timezone-aware UTC timestamps with warnings captured; no warnings were emitted.
