# Stage 9B Macro Numeric Update

Generated UTC: `2026-06-10T04:48:21+00:00`
Tool version: `v2_ssl_resilience`

## Status
- status: `db_error`
- start_date: `2022-01-01`
- ssl_mode_requested: `auto`
- allow_insecure_fallback: `False`
- series_requested: `11`
- series_ok: `11`
- observations_fetched: `7188`
- observations_written_sqlite: `0`

## Series status
| Series | Label | Status | SSL mode | Observations | Latest date | Latest value |
|---|---|---|---|---:|---|---:|
| DGS10 | US 10Y Treasury yield | ok | default | 1156 | 2026-06-08 | 4.56 |
| DGS2 | US 2Y Treasury yield | ok | default | 1156 | 2026-06-08 | 4.15 |
| DFII10 | US 10Y TIPS real yield | ok | default | 1156 | 2026-06-08 | 2.21 |
| DTWEXBGS | Nominal Broad US Dollar Index | ok | default | 1155 | 2026-06-05 | 120.0831 |
| DCOILWTICO | WTI crude oil spot price | ok | default | 1151 | 2026-06-01 | 95.96 |
| DCOILBRENTEU | Brent crude oil spot price | ok | default | 1151 | 2026-06-01 | 98.29 |
| CPIAUCSL | CPI All Urban Consumers | ok | default | 52 | 2026-04-01 | 332.407 |
| PPIACO | Producer Price Index All Commodities | ok | default | 52 | 2026-04-01 | 283.764 |
| PAYEMS | Nonfarm Payrolls | ok | default | 53 | 2026-05-01 | 159001.0 |
| UNRATE | Unemployment Rate | ok | default | 53 | 2026-05-01 | 4.3 |
| FEDFUNDS | Effective Federal Funds Rate | ok | default | 53 | 2026-05-01 | 3.63 |

## Errors
- `SQLite write failed: OperationalError: unable to open database file`

## Decision
- This is data collection only.
- No EA/order workflow changes are authorized.
- Prefer default/certifi SSL. Use insecure only as a local fallback when macOS/Python certificate store is broken.
