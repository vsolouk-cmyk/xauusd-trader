# Stage23A v2 — Lite Proxy-Then-Exact Discovery Hotfix

## Purpose

Stage23A v2 keeps the Stage23 discovery track independent from Stage18A v2 and fixes the runtime problem observed in the first Stage23A patch.

## Guardrails

- Research/shadow only.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
- Stage18A v2 remains the active operational forward-shadow runner.
- Stage19B/20A/21B/22A watchlist-only candidates are not added to Stage18A.

## Runtime fixes in v2

1. CSV-first loading by default:
   - `~/Downloads/amarkets_xauusd_1m.csv`
   - `~/Downloads/amarkets_xauusd_1h.csv`

   This avoids expensive SQLite table discovery when the local store is large.

2. Smaller deterministic lite grid:
   - candidate cap default: 120
   - exact replay cap default: 18 total / 6 per family

3. Faster replay:
   - numpy `searchsorted` instead of per-event DataFrame slicing.

4. Runtime cap:
   - default `STAGE23A_MAX_RUNTIME_SECONDS=240`
   - if the cap is hit, the report still writes partial results and marks timeout flags in JSON.

5. Lower bootstrap iterations:
   - proxy default: 40
   - exact default: 100

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage23a_lite_proxy_exact_discovery
cat data/reports/stage23a_lite_proxy_exact_discovery/stage23a_lite_proxy_exact_discovery.md
```

## Optional faster run

```bash
cd ~/Desktop/xauusd-trader
STAGE23A_MAX_RUNTIME_SECONDS=180 STAGE23A_MAX_CANDIDATES_TOTAL=90 STAGE23A_MAX_EXACT=12 python3 -m app.stage23a_lite_proxy_exact_discovery
cat data/reports/stage23a_lite_proxy_exact_discovery/stage23a_lite_proxy_exact_discovery.md
```

## If CSV files are missing

The module falls back to SQLite. To force SQLite-first:

```bash
cd ~/Desktop/xauusd-trader
STAGE23A_DATA_LOAD_MODE=sqlite_first python3 -m app.stage23a_lite_proxy_exact_discovery
```

## Outputs

```text
data/reports/stage23a_lite_proxy_exact_discovery/stage23a_lite_proxy_exact_discovery.md
data/reports/stage23a_lite_proxy_exact_discovery/stage23a_lite_proxy_exact_discovery.json
data/reports/stage23a_lite_proxy_exact_discovery/stage23a_proxy_candidates.csv
data/reports/stage23a_lite_proxy_exact_discovery/stage23a_exact_candidates.csv
data/reports/stage23a_lite_proxy_exact_discovery/stage23a_exact_trades.csv
```
