# Stage64P Alignment Diagnostic Fastlane

This stage is a no-order broker/spot alignment diagnostic. It is designed to move faster than prior memo-only stages.

It performs the following work in one pass:

- verifies the Stage64O LoaderFix1 context,
- reads the Stage64 gold reference daily close series,
- inspects the AMarkets SQLite broker bar schema,
- scans available broker timeframes and UTC daily session close offsets,
- derives broker D1 closes offline from historical bars,
- compares broker daily returns against the reference gold returns,
- writes alignment candidate metrics and a top-candidate diagnostic report,
- writes an accepted broker D1 raw file only if the declared alignment gates pass.

It does not generate signals, connect to a broker, create orders, run paper-live, or authorize commercialization.

## Gates

- overlap return days >= 500
- return correlation >= 0.95
- sign agreement >= 0.70
- median absolute return difference <= 20 bps
- p90 absolute return difference <= 100 bps

If no candidate passes, the survivor remains research-only and broker XAUUSD claims remain blocked.
