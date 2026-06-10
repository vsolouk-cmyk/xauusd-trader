# Stage 9B Macro Numeric Artifact Import

Generated UTC: `2026-06-10T04:57:48+00:00`
Tool version: `v2_schema_fix`

## Status
- status: `ok`
- csv_path: `data/macro/macro_numeric_observations.csv`
- db_path: `data/local/xauusd_local_store.sqlite`
- rows_read: `7188`
- rows_written: `7188`
- series_count: `11`
- migrations: `none`

## Series summary
| Source | Series | Observations | First date | Latest date | Latest value |
|---|---|---:|---|---|---:|
| FRED | CPIAUCSL | 104 | 2022-01-01 | 2026-04-01 | 332.407 |
| FRED | DCOILBRENTEU | 1151 | 2022-01-03 | 2026-06-01 | 98.29 |
| FRED | DCOILWTICO | 2302 | 2022-01-03 | 2026-06-01 | 95.96 |
| FRED | DFII10 | 1156 | 2022-01-03 | 2026-06-08 | 2.21 |
| FRED | DGS10 | 1156 | 2022-01-03 | 2026-06-08 | 4.56 |
| FRED | DGS2 | 1156 | 2022-01-03 | 2026-06-08 | 4.15 |
| FRED | DTWEXBGS | 1155 | 2022-01-03 | 2026-06-05 | 120.0831 |
| FRED | FEDFUNDS | 53 | 2022-01-01 | 2026-05-01 | 3.63 |
| FRED | PAYEMS | 53 | 2022-01-01 | 2026-05-01 | 159001.0 |
| FRED | PPIACO | 52 | 2022-01-01 | 2026-04-01 | 283.764 |
| FRED | UNRATE | 106 | 2022-01-01 | 2026-05-01 | 4.3 |

## Decision
- Data imported into local SQLite.
- No EA/order workflow changes are authorized.
