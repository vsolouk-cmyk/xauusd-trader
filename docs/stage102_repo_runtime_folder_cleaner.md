# Stage102 Repo Runtime Folder Cleaner

Stage102 is a deliberate local cleanup step after Stage101 added `.gitignore` rules. It deletes safe local runtime artifacts only when `--apply` is supplied.

Default cleanup targets:

- `reports/`
- `_incoming*/`
- top-level `*.zip`
- Python caches and macOS `.DS_Store`

It does not delete source directories: `app`, `configs`, `docs`, `tests`, `mt5`, or `.git`.

Generated data under `data/` is preserved by default. Use `--include-generated-data` only after confirming the data can be rebuilt or redownloaded.

No order, broker, MT5, EA, or thesis-discovery behavior is changed.
