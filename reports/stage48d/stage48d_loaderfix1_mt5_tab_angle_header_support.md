# Stage48D LoaderFix1 — MT5/AMarkets Tab Export Support

## Problem fixed

AMarkets/MT5 history exports can be tab-separated and use angle-bracket headers such as:

```text
<DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE> <TICKVOL> <VOL> <SPREAD>
```

The previous validator expected conventional comma/header CSV fields such as `time_utc` and `spread_points`, so the file was read as zero valid rows.

## Fix

- Detect tab-separated files.
- Normalize angle-bracket headers such as `<DATE>` to `date`.
- Support separate date and time columns by combining `<DATE>` + `<TIME>`.
- Map `<OPEN>`, `<HIGH>`, `<LOW>`, `<CLOSE>`, and `<SPREAD>`.
- Keep missing symbol/timeframe acceptable when a single file is explicitly supplied with `--timeframe M5`.

## Status

Validation-only. No promotion, EA, paper-live, live trading, or trading-signal scan is allowed from this patch.
