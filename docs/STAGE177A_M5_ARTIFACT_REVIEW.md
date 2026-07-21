# Stage177A M5 Artifact Review

Reviewed artifact:

`stage177a-dukascopy-m5_full-bid-29779341735.zip`

## Decision

`PASS_FOR_STAGE177B_REFERENCE_INTEGRATION`

This is a research/reference-feed acceptance only. It is not an execution-feed approval.

## Direct artifact verification

- Requested coverage: 2010-01-01 through 2026-07-20
- First actual candle: 2010-01-01 00:00 UTC
- Last actual candle: 2026-07-19 23:55 UTC
- Rows: 1,180,705
- Chunks: 17/17 PASS
- All compressed chunk SHA-256 values matched the manifest
- Duplicate timestamps: 0
- Non-monotonic timestamps: 0
- Null OHLCV fields: 0
- OHLC invariant violations: 0
- Non-positive prices: 0
- Negative volume rows: 0
- Maximum observed gap: 76.5 hours

The dominant non-five-minute gaps were the expected daily maintenance break and weekend closure patterns. No unexplained gap above the Stage177A 96-hour fail threshold was present.

## M5-to-H1 consistency audit

The M5 bars were aggregated to UTC H1 and compared with the independently downloaded direct H1 artifact.

- Shared hours: 98,530
- Exact OHLC hours: 98,476
- Exact OHLC parity: 99.945194%
- OHLC mismatch hours: 54
- Exact volume parity: 99.990866%
- Direct-H1-only hours inside M5 coverage: 443
- M5-derived-only hours: 1

The 443 direct-H1-only observations were concentrated in 2013-2017 and at 21:00/22:00 UTC. Their median range was zero and median reported volume was 370 units, consistent with sparse rollover/session-boundary candles rather than missing active-market M5 history.

The 54 OHLC disagreements are rare but prove that independently downloaded Dukascopy H1 and M5 are not perfectly self-consistent. Therefore Stage177B uses this canonical policy:

- Before M5 coverage: retain direct H1.
- From 2010 onward: treat M5 as primary and derive H1 from M5.
- Do not inject direct-H1-only sparse rollover bars into the canonical overlap.

This policy prevents timeframe-dependent research results caused solely by Dukascopy aggregation differences.
