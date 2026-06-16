# Stage 16E AMarkets CSV Refresh + True-Forward Cycle

Generated UTC: `2026-06-16T09:32:02+00:00`
Tool version: `v2_imported_utc_fix`

> Hard rule: data refresh + research shadow cycle only. No EA change, no automatic trading, no paper/live authorization.

## Schema compatibility
- bars_has_imported_utc: `True`
- bars_has_ingested_at: `True`

## Bar state
- before_latest_bar_utc: `2026-06-16T12:18:00+00:00`
- after_latest_bar_utc: `2026-06-16T12:18:00+00:00`
- latest_changed: `False`

## Import summary
- files_discovered: `2`
- files_imported: `2`
- files_skipped: `0`
- files_error: `0`
- rows_upserted: `1481006`

## Imported files
| File | Timeframe | Rows clean | Rows upserted | First UTC | Last UTC |
|---|---|---:|---:|---|---|
| `amarkets_xauusd_1h.csv` | `1h` | 24339 | 24339 | `2022-05-02T01:00:00+00:00` | `2026-06-16T12:00:00+00:00` |
| `amarkets_xauusd_1m.csv` | `1m` | 1456667 | 1456667 | `2022-05-02T01:01:00+00:00` | `2026-06-16T12:18:00+00:00` |

## Errors
- none

## Stage16D cycle result
- cycle_status: `skipped`
- cycle_returncode: `None`
- stage16d_final_decision: `None`

## Stage16D bar state
- none

## Stage16D journal counts
- none

## Interpretation
- If files_imported is positive but after_latest_bar_utc is unchanged, the CSVs did not contain newer bars.
- If after_latest_bar_utc is after collector_start_utc and valid_forward_rows is zero, collection is active and waiting.
- Any signal remains research shadow only.
- No paper/live/order escalation is authorized.

## Output files
- import_csv: `data/reports/stage16e_amarkets_csv_refresh_cycle/stage16e_import_results.csv`
- json: `data/reports/stage16e_amarkets_csv_refresh_cycle/stage16e_amarkets_csv_refresh_cycle.json`
- md: `data/reports/stage16e_amarkets_csv_refresh_cycle/stage16e_amarkets_csv_refresh_cycle.md`
