# Stage 5C v3 + Data File Audit

This patch fixes the likely reason behind `missing_m1_data` after a fresh M1 export.

## Key changes

- Stage 5C now supports MT5 CSV exports with separate `<DATE>` and `<TIME>` columns.
- Stage 5C reports M1 parse quality and M1 UTC range.
- Adds `app.stage_data_file_audit`, a read-only file-range audit.
- No SQLite/database update is performed.

## Run

```bash
cd ~/Desktop/xauusd-trader

python3 -m app.stage_data_file_audit
cat data/reports/stage_data_file_audit/stage_data_file_audit.md

python3 -m app.stage5c_live_outcome_tracker
cat data/reports/stage5c_live_outcome_tracker/stage5c_live_outcome_tracker.md
```

No demo/paper/live authorization.
