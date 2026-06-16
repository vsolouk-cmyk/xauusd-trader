# Stage25C — De-duplicated DB-First Filter Validation

Stage25B confirmed that regime/no-trade filters can improve the Stage23B/C candidate family using SQLite candles as the candle source of truth. However, the Stage23C trade artifact contains duplicate and sensitivity variants, so Stage25C validates the filters on one canonical de-duplicated candidate before any forward-shadow tracker is created.

## Hard rules

- Research/shadow diagnostic only.
- No EA change.
- No paper/live/order authorization.
- Stage18A v2 remains unchanged.
- Stage23D remains unchanged.
- SQLite local store is the candle source of truth.
- CSV fallback for candles is intentionally disabled.

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage25c_deduped_filter_validation
cat data/reports/stage25c_deduped_filter_validation/stage25c_deduped_filter_validation.md
```

## Optional environment variables

```bash
STAGE25C_DB_PATH=data/local/xauusd_local_store.sqlite
STAGE25C_STAGE23C_TRADES_PATH=data/reports/stage23c_promotion_candidate_validation/stage23c_exact_trades.csv
STAGE25C_CANONICAL_CANDIDATE=S23B_B_pb0.1_eff0.60_h180_tp0.6_sl0.65
```

## Expected next step

If Stage25C confirms a filter candidate, the next step is a DB-first filtered Stage23D tracker, still research/shadow only.
