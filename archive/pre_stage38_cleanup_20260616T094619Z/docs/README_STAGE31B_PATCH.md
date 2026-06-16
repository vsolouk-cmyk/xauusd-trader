# Stage31B Exogenous/Macro Gate Validation Patch

This patch adds:

- `app/stage31b_exogenous_gate_validation.py`

Purpose:

- Consume the Stage31A enriched dataset:
  `data/reports/stage31a_exogenous_feature_ingestion/stage31a_exogenous_ml_dataset.csv`
- Validate exogenous gates for DXY, US10Y, real yield, VIX, SPX, and oil.
- Use expanding prior-year calibration only.
- Produce review-only outputs under:
  `data/reports/stage31b_exogenous_gate_validation/`

Guardrails:

- Research/shadow validation only.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
- No internet fetch.

Run:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage31b_exogenous_gate_validation
cat data/reports/stage31b_exogenous_gate_validation/stage31b_exogenous_gate_validation.md
```

Outputs:

- `stage31b_exogenous_gate_validation.md`
- `stage31b_exogenous_gate_validation.json`
- `stage31b_gate_results.csv`
- `stage31b_candidate_review.csv`

Interpretation:

- `STAGE31B_NO_EXOGENOUS_GATE_PROMOTION_KEEP_RESEARCH_OPEN` means no validated exogenous gate passed review thresholds.
- `STAGE31B_HAS_WEAK_EXOGENOUS_GATE_IMPROVEMENT_REVIEW_ONLY` means diagnostic improvement only.
- `STAGE31B_HAS_STRONG_EXOGENOUS_GATE_CANDIDATE_REVIEW_ONLY` still does not authorize trading; it only justifies a separate forward-shadow tracker.
