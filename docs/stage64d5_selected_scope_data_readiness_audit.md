# Stage64D5 Selected Scope Data Readiness Audit

Purpose: interpret Stage64D4 preflight results after local/source acquisition and decide whether the full macro-regime source set or a reduced P0+VIX source scope is ready for the next governance step.

This stage does **not** run validation, generate signals, authorize paper order, or connect to a broker.

Inputs:

- `reports/stage64d4_source_file_import_preflight/stage64d4_source_file_import_preflight_summary.json`
- `reports/stage64_macro_data_acquisition/stage64_local_macro_data_fetch_summary.json`

Outputs:

- selected-scope readiness report
- selected-scope readiness summary
- readiness CSV

Policy:

- Full scope requires P0, P1, and P2 source files to pass preflight.
- Reduced P0+VIX scope may be considered only for an explicitly predeclared feasibility validation stage.
- If gold is sourced from COMEX continuous futures rather than broker spot XAUUSD, the report flags that as a source-proxy warning.
