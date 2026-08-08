# XAUUSD True-Surprise Data Gate V1

Purpose: validate a point-in-time historical US economic-calendar export before any true-surprise trading scan is built.

Scope is intentionally narrow: headline CPI MoM, core CPI MoM, and Non-Farm Payrolls, 2016-2024 only.

Required source semantics:
- release timestamp in UTC or parseable timezone-aware form
- Actual, Previous, Forecast/consensus from the historical event record
- DateSpan=0 (known release time)
- LastUpdate at or after release
- Forecast must be the survey consensus; TEForecast/model forecast is not an acceptable substitute

The package performs no network calls and contains no credentials. Put one or more provider CSV exports in an inbox folder and run the validator.

Pass requires at least 80 valid rows for each configured group. 2025+ is not read for selection.
