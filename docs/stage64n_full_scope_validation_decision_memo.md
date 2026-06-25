# Stage64N - Full-Scope Validation Decision Memo

Stage64N reads the Stage64M full-scope validation summary and writes a decision memo. It does not run validation, generate signals, connect to a broker, or authorize any order path.

## Purpose

- Preserve the Stage64M result as a research-only validation result.
- Decide whether a corrected survivor exists.
- If a corrected survivor exists, require a stricter robustness audit before any further claim.
- Preserve event-calendar and broker/spot governance blockers.

## Inputs

- `reports/stage64m_full_scope_walk_forward_validation_run/stage64m_full_scope_walk_forward_validation_run_summary.json`

## Outputs

- `stage64n_full_scope_validation_decision_memo_summary.json`
- `stage64n_full_scope_validation_decision_memo_report.md`
- `stage64n_decision_matrix.csv`
- `stage64n_survivor_audit_plan.csv`

## Hard blocks

Stage64N does not authorize paper-order, EA promotion, paper-live, live, broker connection, event-calendar historical filtering, reduced-scope rescue, or new intraday scanning.
