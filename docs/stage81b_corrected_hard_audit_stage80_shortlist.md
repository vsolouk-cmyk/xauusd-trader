# Stage81B Corrected Hard Audit - Stage80 Shortlist

## Purpose

Stage81B corrects the Stage81 hard-audit missing-feature diagnostic. Stage81 counted the natural warm-up window of derived features such as `gold_ret_60d`, `dxy_ret_60d`, `real_yield_change_60d`, and SMA spreads as `MISSING_REQUIRED_FEATURE_ROWS`.

That is too strict for derived features because the first 20/50/60 rows are expected to be unavailable before the feature has enough history. Stage81B ignores only the leading warm-up rows before all required trigger/date/price columns first become available. Any missing values after that first complete required row remain hard failures.

## Non-goals

- No order authorization.
- No broker connection.
- No MT5 or EA change.
- No threshold tuning.
- No relaxation of performance, downside, concentration, or overlap constraints.

## Expected behavior

Stage81B may change candidates that failed only because of natural derived-feature warm-up from fail to pass. Candidates that fail due to excessive downside, excessive overlap, weak split metrics, concentration, lookahead, missing columns, or unexpected post-warm-up missing rows remain failed.

## Outputs

- `stage81b_corrected_hard_audit_stage80_shortlist_summary.json`
- `stage81b_corrected_hard_audit_stage80_shortlist_report.md`
- `stage81b_corrected_hard_audit_metrics.csv`
- `stage81b_selected_for_stage82.csv`
- `stage81b_corrected_hard_audit_failures.csv`
- `stage81b_corrected_hard_audit_entry_returns.csv`
