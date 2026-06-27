# Stage82 Portfolio Increment Review

Stage82 reviews Stage81B hard-audit survivors for incremental contribution against the existing Stage77B observer portfolio.

It does not authorize orders, change EA behavior, connect to a broker, or tune thresholds.

## Inputs

- `reports/stage77b_corrected_portfolio_candidate_selection_historical_asof/stage77b_corrected_portfolio_candidate_selection_historical_asof_summary.json`
- `reports/stage81b_corrected_hard_audit_stage80_shortlist/stage81b_corrected_hard_audit_stage80_shortlist_summary.json`
- `data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv`

## Outputs

- `stage82_portfolio_increment_review_summary.json`
- `stage82_portfolio_increment_review_report.md`
- `stage82_portfolio_increment_review.csv`
- `stage82_selected_for_stage83.csv`
- `stage82_pairwise_overlap_review.csv`
- `stage82_latest_signal_snapshot.csv`

## Decision use

If Stage82 selects survivors, Stage83 may build an observer-only portfolio expansion bridge. Stage82 itself cannot modify MT5/EA files or authorize orders.
