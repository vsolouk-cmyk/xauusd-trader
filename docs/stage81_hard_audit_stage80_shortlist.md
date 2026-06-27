# Stage81 Hard Audit - Stage80 Shortlist

Stage81 re-audits the Stage80 discovery shortlist before any observer-portfolio expansion.

## Scope

- Reads the Stage80 shortlist.
- Recomputes rule entries from the macro dataset.
- Applies stricter hard-audit constraints:
  - enough total events
  - positive median return
  - validation / locked-forward / final-holdout support
  - bounded worst loss
  - no missing trigger/date/price rows
  - no lookahead violations
  - controlled overlap with Stage77B selected portfolio
- Produces a small selected list for Stage82 portfolio-review only.

## Non-goals

- No order authorization.
- No paper order.
- No broker connection.
- No EA or MT5 change.
- No threshold tuning.
- No ML.

## Outputs

- `stage81_hard_audit_stage80_shortlist_summary.json`
- `stage81_hard_audit_stage80_shortlist_report.md`
- `stage81_hard_audit_metrics.csv`
- `stage81_selected_for_stage82.csv`
- `stage81_hard_audit_failures.csv`
- `stage81_hard_audit_entry_returns.csv`
