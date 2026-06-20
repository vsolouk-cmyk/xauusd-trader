# Stage49B Fast Persistent Importer + Hard Audit Design

## Purpose

This package combines the next operational patch into one stage:

1. A fast, persistent AMarkets multi-timeframe importer for repeated updates.
2. A hard audit for Stage49 diagnostic survivors.

It intentionally avoids creating a separate memo stage.

## Importer behavior

`app/stage49_amarkets_multitf_importer_fast.py` reads the permanent AMarkets files:

- `~/Downloads/amarkets_xauusd_1m.csv`
- `~/Downloads/amarkets_xauusd_5m.csv`
- `~/Downloads/amarkets_xauusd_15m.csv`
- `~/Downloads/amarkets_xauusd_30m.csv`
- `~/Downloads/amarkets_xauusd_1h.csv`

It writes persistent data to:

- `data/broker_normalized/amarkets_multitf.sqlite`

The importer uses a manifest table. On later runs:

- unchanged files are skipped;
- safely appended files are parsed from the prior byte offset;
- rewritten or incompatible files trigger a full refresh for that timeframe only.

CSV export is disabled by default for speed. The thesis/audit scripts use SQLite.

## Hard audit behavior

`app/stage49_multitf_trend_persistence_hard_audit.py` reads Stage49 diagnostic survivor candidates and reruns the multi-timeframe trend-persistence rules with stricter checks:

- H1 range expansion threshold is computed from prior H1 bars only.
- Entry occurs after the H1 bar closes.
- M15 and M5 alignment use completed bars before entry.
- Broker-real spread cost gate is applied at entry.
- Stress cost from Stage48F is used.
- Chronological folds, OOS, cost x1.5, cost x2, declustering, yearly concentration, monthly concentration, and direction splits are audited.

Passing hard audit still does not authorize EA, paper-live, live trading, or promotion.

## Expected next decisions

- If no candidate passes hard audit: archive or redesign the thesis.
- If candidates pass hard audit: only a controlled forward-shadow design is allowed.
