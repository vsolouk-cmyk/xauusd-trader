# Stage23D DB-First Forward-Shadow Hotfix

This hotfix makes `stage23d_forward_shadow_candidate` use SQLite as the source of truth for candles.

## Scope

- Research/shadow only.
- Stage18A v2 remains unchanged.
- Stage25D remains unchanged.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
- AMarkets CSV fallback is disabled.

## Reason

Stage25D already reads candles from `data/local/xauusd_local_store.sqlite`, while Stage23D was still using the older market-data loader path. This made unfiltered and filtered forward-shadow trackers inconsistent.

## New behavior

- Reads M1/H1 candles from SQLite via schema introspection.
- Uses table `bars` when detected.
- Derives M15 from DB-loaded M1.
- If H1 cannot be loaded from DB, derives H1 from M1 resampling.
- Writes a DB schema diagnostic CSV.

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage23d_forward_shadow_candidate
cat data/reports/stage23d_forward_shadow_candidate/stage23d_forward_shadow_candidate.md
```
