# Stage163B Macro-Supported Side Discovery TSV Loader Fix

Stage163B is a hotfix for Stage163. It remains read-only/offline and does not write MT5 KV files or release demo orders.

## Why

The raw AMarkets/MT5 M5 export in the inbox is tab-separated and uses split columns:

- `<DATE>`
- `<TIME>`
- `<OPEN>`
- `<HIGH>`
- `<LOW>`
- `<CLOSE>`

Stage163 could detect `<DATE>` as a date column but did not combine `<DATE>` and `<TIME>`, so it collapsed intraday bars into one row per date after duplicate removal. This caused a tiny `bar_count` around one row per day even though the source file had about 318k rows.

## Fix

Stage163B explicitly combines `<DATE> + <TIME>` for MT5 TSV files and still supports normalized project CSV files with `time_utc`.

The summary now includes loader diagnostics:

- `loader_selected_sep`
- `loader_parse_mode`
- `loader_raw_row_count`
- `loader_raw_columns`

## Execution policy

No orders. No KV. No demo release. Stage157 freeze remains active until a later reviewed execution/governance stage.
