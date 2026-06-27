# Stage107 Second-Order Portfolio Increment Review

## Purpose
Stage107 reviews Stage106 second-order COT/macro hard-audit survivors before any observer-only expansion. It is a portfolio-increment gate, not a discovery scan and not an MT5/EA change.

## Inputs
- `reports/stage106_second_order_cot_macro_hard_audit/stage106_second_order_cot_macro_hard_audit_summary.json`
- `reports/stage106_second_order_cot_macro_hard_audit/stage106_selected_for_stage107.csv`

## Outputs
- `stage107_second_order_portfolio_increment_review_summary.json`
- `stage107_second_order_portfolio_increment_review_report.md`
- `stage107_second_order_portfolio_increment_review.csv`
- `stage107_selected_for_stage108.csv`

## Hard blocks
- No automated order
- No paper order
- No broker connection
- No EA promotion
- No MT5/EA change
- No paper-live
- No live
- No order authorization
- No threshold tuning

## Interpretation
If Stage107 selects a candidate, Stage108 may expand the unified observer only. Stage107 cannot authorize trading.
