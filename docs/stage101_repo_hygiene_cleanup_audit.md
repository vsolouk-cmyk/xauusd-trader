# Stage101 Repo Hygiene Cleanup Audit

Purpose: clean the XAUUSD repo before further thesis discovery by separating source artifacts from generated runtime outputs.

This stage does not delete local data. It only reports tracked runtime artifacts and prepares safe `git rm --cached` commands.

Runtime outputs that should not be tracked:

- `reports/`
- `_incoming*/`
- patch zip files
- local SQLite/database files
- generated MT5 bridge CSVs
- downloaded/raw COT data
- normalized external-frontier CSVs
- generated macro normalized CSVs

Source artifacts that should remain tracked:

- `app/`
- `configs/`
- `docs/`
- `tests/`
- `mt5/*.mq5`

Recommended workflow:

1. Run Stage101 without applying changes to inspect.
2. Run Stage101 with `--apply-gitignore` to append the guarded ignore block.
3. Run the suggested `git rm --cached` commands from the report.
4. Commit the `.gitignore` and index cleanup.

No orders, MT5 changes, thesis discovery, or local data deletion are performed here.
