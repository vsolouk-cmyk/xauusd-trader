# Stage25B DB-First Regime Filter Validation — Hotfix 1

This patch replaces `app/stage25b_db_first_regime_filter_validation.py`.

## Purpose

- Keep SQLite as the source of truth for OHLC candles.
- Keep CSV fallback intentionally disabled.
- Fix the previous failure by introspecting SQLite schema instead of assuming one table/column layout.
- If candle discovery still fails, write `stage25b_db_schema_diagnostic.csv` so the actual DB schema can be inspected.

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage25b_db_first_regime_filter_validation
cat data/reports/stage25b_db_first_regime_filter_validation/stage25b_db_first_regime_filter_validation.md
```

## Scope

Research/shadow diagnostic only. No EA, paper, live, or order authorization.
