# Stage38F — SPDR GLD Loader Review

## Status

```text
STAGE38F_SPDR_GLD_LOADER = PASS
SPDR_GLD_DAILY_ROWS = 5,425
SPDR_GLD_FEATURE_ROWS = 5,425
H1_JOINED_ROWS = 25,643 / 25,643
H1_UNJOINED_ROWS = 0
LOOKAHEAD_VIOLATIONS = 0
```

## Data source retained

The first usable ETF source for Stage38F is the SPDR GLD Historical Archive workbook.

The WGC page was reachable and one WGC XLSX was downloadable, but the current parse audit identified the SPDR GLD workbook as the clear first loader target.

## Loaded feature set

The loader produced daily GLD holdings and derived flow features:

```text
observation_date
available_from_utc
tonnes_gold
gld_tonnes_chg_1d
gld_tonnes_chg_5d
gld_tonnes_chg_20d
gld_tonnes_pct_chg_5d
gld_tonnes_pct_chg_20d
gld_holding_zscore_156d
gld_flow_state
```

The H1 join used an anti-lookahead rule:

```text
For each H1 bar at time T:
use only the latest GLD observation where available_from_utc <= T.
```

The audit found:

```text
lookahead = 0
unjoined = 0
```

## Latest state observed in audit output

The latest rows show sustained GLD outflow/strong outflow into 2026-06-15.

Example:

```text
2026-06-15
GLD tonnes = 1012.210
5d tonnes change = -7.710
20d tonnes change = -25.210
holding z-score 156d = -2.154
flow state = ETF_STRONG_OUTFLOW
```

## Interpretation

This is a successful data foundation step, not evidence of an edge.

GLD/ETF flow should now be tested as an event-level context variable. It must not be used as an entry signal unless it shows robust forward-return separation across years and months.

## Decision

```text
GLD_DATA_FOUNDATION = KEEP
GLD_H1_JOIN = PASS
GLD_FEATURE_DIAGNOSTIC = PROCEED_READ_ONLY
GLD_STRATEGY = NO_GO
STAGE39 = NO_GO
EA = NO_GO
PAPER_LIVE = NO_GO
LIVE_ORDER = NO_GO
```

## Next artifact

```text
app/stage38f_gld_feature_diagnostic.py
```

Purpose:

```text
Check whether GLD flow/holding states separate future XAUUSD returns at event level.
No strategy.
No optimization.
No ML.
No paper/live.
```
