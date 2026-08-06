# Stage177C Package Manifest

## Files

- `app/stage177c_amarkets_dst_contract.py`
- `app/stage177b_amarkets_crossfeed.py` (exact repaired loader dependency)
- `configs/stage177c_amarkets_dst_contract.json`
- `tests/test_stage177c_amarkets_dst_contract.py`
- `docs/STAGE177C_AMARKETS_DST_AWARE_UTC_CONTRACT.md`

## Dependency

The exact repaired `app/stage177b_amarkets_crossfeed.py` is included so the package is self-contained.
Stage177B Dukascopy SQLite integration must already exist locally.

## Boundary

Research-only. No signal, paper order, demo order, or live order path exists.
