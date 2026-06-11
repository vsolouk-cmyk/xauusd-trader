# Stage25B — DB-First Regime Filter Validation

## Purpose

Stage25B validates Stage25A-style regime/no-trade filters while using the local SQLite candle store as the source of truth.

The AMarkets CSV files remain raw import inputs only. This module intentionally does not fall back to `~/Downloads/amarkets_xauusd_1m.csv` or `~/Downloads/amarkets_xauusd_1h.csv` for candle data.

## Scope

- Research/shadow diagnostic only.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
- Does not modify Stage18A v2.
- Does not modify Stage23D.

## Inputs

Primary candle source:

```text
Data/local SQLite store:
data/local/xauusd_local_store.sqlite
```

Trade-event source:

```text
data/reports/stage23c_promotion_candidate_validation/stage23c_exact_trades.csv
```

Stage25B still uses Stage23C exact-trade artifacts for event rows. Candle-derived regime features are rebuilt from SQLite.

## Output

```text
data/reports/stage25b_db_first_regime_filter_validation/stage25b_db_first_regime_filter_validation.md
data/reports/stage25b_db_first_regime_filter_validation/stage25b_db_first_regime_filter_validation.json
data/reports/stage25b_db_first_regime_filter_validation/stage25b_filter_candidates.csv
data/reports/stage25b_db_first_regime_filter_validation/stage25b_enriched_stage23c_trades.csv
data/reports/stage25b_db_first_regime_filter_validation/stage25b_stage25a_comparison.csv
```

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage25b_db_first_regime_filter_validation
cat data/reports/stage25b_db_first_regime_filter_validation/stage25b_db_first_regime_filter_validation.md
```

Optional explicit DB path:

```bash
cd ~/Desktop/xauusd-trader
STAGE25B_DB_PATH=data/local/xauusd_local_store.sqlite python3 -m app.stage25b_db_first_regime_filter_validation
cat data/reports/stage25b_db_first_regime_filter_validation/stage25b_db_first_regime_filter_validation.md
```

## Interpretation

If Stage25B confirms Stage25A filters, the next step is not operational promotion. The next step is a separate forward-shadow filter tracker for the Stage23D candidate plus the validated filter.
