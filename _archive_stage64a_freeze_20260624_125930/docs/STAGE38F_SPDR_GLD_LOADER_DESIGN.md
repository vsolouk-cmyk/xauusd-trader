# Stage38F — SPDR GLD Loader Design

## Status

`READ_ONLY_DATA_FOUNDATION`

This step follows the Stage38F source availability and parse audits. The source audit found that the SPDR GLD Historical Archive workbook is directly accessible and the parse audit identified one clean candidate sheet:

```text
file: spdr_historical_archive.xlsx
sheet: US GLD Historical Archive
columns: Date, Closing Price, Ounces of Gold per Share, Total Ounces of Gold in the Trust, Tonnes of Gold, Total Net Asset Value in the Trust, ...
```

## Purpose

Build a normalized daily GLD holdings/flow foundation that can later be used as context, not as an entry signal.

## Loader outputs

SQLite tables:

```text
stage38f_spdr_gld_daily
stage38f_spdr_gld_features
stage38f_spdr_gld_h1_joined
stage38f_spdr_gld_loader_audit
```

Reports:

```text
data/reports/stage38f_spdr_gld_loader/stage38f_spdr_gld_loader.json
data/reports/stage38f_spdr_gld_loader/stage38f_spdr_gld_loader.md
```

## Anti-lookahead rule

For a GLD observation date `D`, the feature is only usable from:

```text
D + 1 day at 00:00:00 UTC
```

For every H1 bar timestamp `T`, the join uses only the latest GLD row with:

```text
gld_available_from_utc <= T
```

## Features

The first feature set is intentionally simple:

```text
tonnes_gold
total_ounces_gold_trust
gld_tonnes_chg_1d
gld_tonnes_chg_5d
gld_tonnes_chg_20d
gld_tonnes_pct_chg_5d
gld_tonnes_pct_chg_20d
gld_holding_zscore_156d
gld_flow_state
```

`gld_flow_state` is a coarse annotation:

```text
ETF_STRONG_INFLOW
ETF_INFLOW
ETF_FLOW_FLAT
ETF_OUTFLOW
ETF_STRONG_OUTFLOW
ETF_FLOW_UNKNOWN
```

## Explicit non-goals

This loader does not create:

```text
strategy
entry signal
optimization
Stage39
EA
paper-live
live order
```

## Next step after PASS

If the loader passes and H1 lookahead count is zero:

```text
Stage38F GLD feature review / diagnostic
```

That diagnostic must still be event-level/read-only before any baseline-context retest.
