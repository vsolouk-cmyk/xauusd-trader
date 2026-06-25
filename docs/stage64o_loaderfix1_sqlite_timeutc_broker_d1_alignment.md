# Stage64O LoaderFix1 - SQLite `time_utc` Broker D1 Alignment

This patch fixes Stage64O broker/spot alignment derivation when the AMarkets SQLite table uses `time_utc` instead of `utc_time`.

It remains a no-order research/governance stage:

- no broker connection
- no paper order
- no paper-live/live
- no EA promotion
- no new hypothesis scan
- no historical event-calendar filtering

## What changed

LoaderFix1 reads the actual SQLite schema, accepts `time_utc`, selects the highest available timeframe by configured preference, derives D1 close series from broker intraday bars, and computes return alignment versus the Stage64 gold reference file.

## Alignment gates

- minimum overlap days
- return correlation
- sign agreement
- median absolute return difference in bps
- p90 absolute return difference in bps

Passing these gates does not authorize orders. It only permits the next no-order decision stage.
