# Stage73 As-Of Validation Bridge

Purpose: validate K06 by pretending the system is standing at an historical as-of date, default `2024-01-01`.

Rules:
- Pre-as-of events define expected behavior.
- Post-as-of and final holdout are compared to realized outcomes.
- No parameter is tuned after seeing post-as-of or final holdout results.
- Future rows are never used to trigger signals; later rows are used only after the horizon has matured to score historical outcomes.
- This is no-order only.

Decision outputs:
- `K06_ASOF_VALIDATION_PASS_NO_ORDER`
- `K06_ASOF_VALIDATION_PASS_WITH_CAUTION_NO_ORDER`
- `K06_ASOF_VALIDATION_FAIL_NO_ORDER`

Outputs:
- `stage73_asof_validation_bridge_summary.json`
- `stage73_asof_validation_bridge_report.md`
- `stage73_k06_asof_entry_returns.csv`
- `stage73_k06_asof_daily_ledger.csv`
- `stage73_k06_asof_validation_errors.csv`
- `stage73_k06_asof_monthly_metrics.csv`
- `stage73_asof_temporal_compatibility.csv`

Hard blocks: no automated order, no broker, no EA, no paper-live, no live, no threshold tuning from Stage73.
