# Stage64 external spot/broker D1 data pack - Investing XAU/USD

This pack normalizes the uploaded Investing `XAU_USD Historical Data.csv` into the Stage64 external D1 schema.

## Canonical output

`data/macro_regime/raw/broker_or_spot_gold_d1_ohlc_2011_present.csv`

## Preflight result

- raw_rows: 4030
- canonical_rows: 4030
- first_date: `2011-01-03T00:00:00Z`
- last_date: `2026-06-25T00:00:00Z`
- duplicate_dates: 0
- missing OHLC numeric values: {'open': 0, 'high': 0, 'low': 0, 'close': 0}
- ohlc_bound_adjusted_rows: 21
- bad_ohlc_rows_after_sanitization: 0
- overall_preflight_ok: True

## Notes

The Investing file uses columns `Date, Price, Open, High, Low, Vol., Change %`.
`Price` is mapped to `close`.

A small number of rows had raw OHLC bound inconsistencies where close/open was outside the reported high/low range.
For downstream OHLC safety, this pack adjusts only `high`/`low` bounds to include open and close.
The close series is unchanged, so daily return validation is unaffected by this sanitation.

No order path, broker connection, or live/paper authorization is included.
