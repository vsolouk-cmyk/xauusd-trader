# Stage70 Known-Thesis Convergence Runner

This package exists to stop the project from drifting into endless parallel research.
It does not open a new discretionary research lane. It consolidates public gold/XAUUSD thesis families and the existing project thesis surface into one fixed scan and one convergence decision.

## Rules

- Do not audit every pass-fast row.
- Keep Stage68F as daily shadow monitor only.
- Select at most one new champion for a single hard audit.
- If the champion fails, close or deliberately replace it; do not open many parallel paths.
- No order, broker, EA, paper-live, or live path is authorized.

## Outputs

- `stage70_known_thesis_catalog.csv`
- `stage70_known_vs_old_thesis_scan_results.csv`
- `stage70_thesis_entry_returns.csv`
- `stage70_missing_data_requirements.csv`
- `stage70_known_thesis_convergence_runner_summary.json`
- `stage70_known_thesis_convergence_runner_report.md`

## Intended next decision

Only one of:

- `ONE_CHAMPION_HARD_AUDIT_ONLY`
- `NO_TESTABLE_CHAMPION_CLOSE_OR_REQUEST_DATA`

No live or demo EA authorization is possible from this package.
