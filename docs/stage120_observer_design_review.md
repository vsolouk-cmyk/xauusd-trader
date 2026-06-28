# Stage120 Observer Design Review

Stage120 is a review-only stage. It converts Stage119 readiness results into draft observer designs and a Stage121 dry-run preflight queue.

It must not:

- update active observer files,
- write to MT5 `MQL5/Files`,
- change the EA,
- connect to broker surfaces,
- authorize paper, demo, or live orders.

## Inputs

- `reports/stage119_portfolio_observer_readiness_review/stage119_observer_readiness_queue.csv`
- `reports/stage119_portfolio_observer_readiness_review/stage119_feature_coverage_review.csv`
- `reports/stage119_portfolio_observer_readiness_review/stage119_portfolio_overlap_review.csv`
- `reports/stage119_portfolio_observer_readiness_review/stage119_portfolio_observer_readiness_review_summary.json`
- `reports/stage117_segmented_macro_cot_dollar_discovery/stage117_selection_thresholds.csv`

## Outputs

- `reports/stage120_observer_design_review/stage120_observer_design_review_summary.json`
- `reports/stage120_observer_design_review/stage120_observer_design_review_report.md`
- `reports/stage120_observer_design_review/stage120_observer_design_queue.csv`
- `reports/stage120_observer_design_review/stage120_observer_rule_specs_draft.json`
- `reports/stage120_observer_design_review/stage120_observer_feature_contract.csv`
- `reports/stage120_observer_design_review/stage120_stage121_preflight_queue.csv`
- `reports/stage120_observer_design_review/stage120_watchlist_only_rules.csv`
- `reports/stage120_observer_design_review/stage120_governance_gate.csv`

## Run

```bash
cd /Users/vahid/Desktop/xauusd-trader
python3 app/stage120_observer_design_review.py --root /Users/vahid/Desktop/xauusd-trader
```

## Interpretation

If `stage121_preflight_candidate_count > 0`, the next allowed step is Stage121 dry-run observer preflight. Stage121 must still write reports only and must not update active observer/MT5/EA files.
