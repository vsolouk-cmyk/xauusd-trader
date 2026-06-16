# Stage Data File Audit

Generated UTC: `2026-06-09T11:57:49+00:00`
Tool version: `v1`

> Hard rule: read-only audit. This does not update SQLite/database and does not authorize orders.

## Files
| Kind | Status | Rows | Start UTC | End UTC | Path |
|---|---|---:|---|---|---|
| h1 | ok | 24225 | 2022-05-01T23:00:00+00:00 | 2026-06-09T11:00:00+00:00 | `/Users/vahid/Downloads/amarkets_xauusd_1h.csv` |
| m1 | ok | 1449867 | 2022-05-01T23:01:00+00:00 | 2026-06-09T11:44:00+00:00 | `/Users/vahid/Downloads/amarkets_xauusd_1m.csv` |
| signals | ok | 1 | 2026-06-09T08:00:00+00:00 | 2026-06-09T08:00:00+00:00 | `/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/XAUUSD_DryRun_v1_signals.csv` |

## Decision
- If M1 end UTC is before signal entry/horizon, Stage 5C must remain open/unresolved.
- If M1 rows are zero but file size is large, the parser/export format is the issue.
