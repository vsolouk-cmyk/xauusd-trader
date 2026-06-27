# Stage92B Intraday Loader Fix

Fixes Stage92 intraday CSV loading for AMarkets / MT5 tab-delimited exports with headers like `<DATE>`, `<TIME>`, `<OPEN>`, `<HIGH>`, `<LOW>`, `<CLOSE>`, `<TICKVOL>`, `<VOL>`, `<SPREAD>`.

The discovery logic and gates are unchanged. This is a loader compatibility patch only.

## What changed
- Combine `<DATE>` and `<TIME>` into `utc_time`.
- Accept angle-bracket OHLC headers.
- Accept `<TICKVOL>`, `<VOL>`, and `<SPREAD>`.
- Preserve observer/order hard blocks.

## Expected effect
The command that previously failed with:

```text
FileNotFoundError: No readable intraday CSV found
```

should now read files such as:

```text
~/Downloads/amarkets_xauusd_15m.csv
~/Downloads/amarkets_xauusd_5m.csv
~/Downloads/amarkets_xauusd_1h.csv
```

and continue to Stage92 thesis discovery.
