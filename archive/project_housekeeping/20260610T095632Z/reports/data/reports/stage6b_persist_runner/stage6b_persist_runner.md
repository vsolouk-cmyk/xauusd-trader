# Stage 6B Local Persist + Evidence Runner

Generated UTC: `2026-06-09T12:01:46+00:00`
Tool version: `v2`

> Hard rule: this runner validates dry-run evidence, updates local SQLite, and produces DB evidence reports. It does not authorize demo, paper, or live orders.

## Inputs
- h1_csv: `/Users/vahid/Downloads/amarkets_xauusd_1h.csv`
- m1_csv: `/Users/vahid/Downloads/amarkets_xauusd_1m.csv`
- signals_csv: `/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/XAUUSD_DryRun_v1_signals.csv`
- db: `data/local/xauusd_local_store.sqlite`
- fetch_twelve: `False`
- run_6c: `True`

## Step summary
| # | Step | Status | Return code |
|---:|---|---|---:|
| 1 | stage_data_file_audit | OK | 0 |
| 2 | stage5b_dryrun_signal_csv_validator | OK | 0 |
| 3 | stage5c_live_outcome_tracker | OK | 0 |
| 4 | stage6a_local_data_store | OK | 0 |
| 5 | stage6c_db_evidence_report | OK | 0 |

## Main reports
- `data/reports/stage_data_file_audit/stage_data_file_audit.md`
- `data/reports/stage5b_dryrun_log_validator.md`
- `data/reports/stage5c_live_outcome_tracker/stage5c_live_outcome_tracker.md`
- `data/reports/stage6a_local_store/stage6a_local_store.md`
- `data/reports/stage6c_db_evidence_report/stage6c_db_evidence_report.md`

## Decision
- Persist + evidence flow completed. Local SQLite evidence store and DB evidence report are updated.
- This does not authorize orders.
