# Stage64F Reduced-Scope Lag-Safe Feature Dataset Preflight

Stage64F is a feature-dataset preflight stage for the predeclared reduced scope:

`P0_PLUS_VIX_NO_ETF_NO_CENTRAL_BANK_NO_EVENT_CALENDAR`

It is not a validation scan. It does not create targets, labels, signals, orders, or promotion evidence.

## Inputs

Stage64F expects these raw files:

- `data/macro_regime/raw/gold_d1_ohlc_2011_present.csv`
- `data/macro_regime/raw/dxy_daily_2011_present.csv`
- `data/macro_regime/raw/real_yield_or_proxy_daily_2011_present.csv`
- `data/macro_regime/raw/vix_daily_2011_present.csv`

The raw files must already have passed Stage64D4 and Stage64D5 readiness checks.

## What it builds

The script builds a lag-safe feature-only dataset:

- `data/macro_regime/normalized/stage64f_reduced_scope_lag_safe_feature_dataset.csv`
- `data/macro_regime/manifests/stage64f_lag_safe_feature_dataset_manifest.json`

For each gold feature date, DXY, real-yield, and VIX observations are joined only if their `available_after_utc` is not later than the gold sample `available_after_utc`.

## What it does not do

Stage64F does not:

- compute forward returns;
- create labels;
- create signal columns;
- run historical validation;
- authorize paper-order, paper-live, live, EA promotion, or broker connection.

## Expected next stage

If Stage64F passes, the next step is Stage64G: walk-forward validation design with fixed hypotheses. Stage64G must still be a design/specification stage unless explicitly implemented later as a separate validation scan stage.

## Source warning

The current gold D1 source may be COMEX continuous futures reference (`GC=F`), not broker spot XAUUSD. Any later validation must keep this as a proxy/reference scope unless a broker/spot D1 backfill is acquired.
