# Stage119 Portfolio Observer Readiness Review

Stage119 converts Stage118 survivors into a portfolio / observer-readiness review queue.

It is intentionally **review-only**:

- no MT5 bridge write
- no EA change
- no observer CSV update
- no paper/demo/live order
- no candidate promotion

Primary inputs:

- `reports/stage118_macro_cot_spdr_hard_audit/stage118_selected_for_stage119.csv`
- `reports/stage118_macro_cot_spdr_hard_audit/stage118_cost_stress_summary.csv`
- `reports/stage118_macro_cot_spdr_hard_audit/stage118_overlap_matrix.csv`
- `reports/stage116_source_specific_wgc_spdr_dxy_validator/stage116_source_specific_wgc_spdr_dxy_validator_summary.json`

Run:

```bash
cd /Users/vahid/Desktop/xauusd-trader
python3 app/stage119_portfolio_observer_readiness_review.py \
  --root /Users/vahid/Desktop/xauusd-trader
```

Outputs:

- `reports/stage119_portfolio_observer_readiness_review/stage119_portfolio_observer_readiness_review_summary.json`
- `reports/stage119_portfolio_observer_readiness_review/stage119_rule_readiness_scores.csv`
- `reports/stage119_portfolio_observer_readiness_review/stage119_observer_readiness_queue.csv`
- `reports/stage119_portfolio_observer_readiness_review/stage119_portfolio_overlap_review.csv`
- `reports/stage119_portfolio_observer_readiness_review/stage119_governance_gate.csv`

Stage119 can only send rules to Stage120 observer-design review. Stage120 must still be no-update unless explicitly promoted by a separate gate.
