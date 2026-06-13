# Stage31E Exogenous Forward-Shadow Tracker Patch

Adds a research/shadow-only tracker for the confirmed Stage31D exogenous candidate family.

## Files

- `app/stage31e_exogenous_forward_shadow_tracker.py`

## Inputs

- `data/reports/stage31a_exogenous_feature_ingestion/stage31a_exogenous_ml_dataset.csv`
- `data/reports/stage31d_exogenous_candidate_confirmation/stage31d_candidate_review.csv`

## Outputs

- `data/reports/stage31e_exogenous_forward_shadow_tracker/stage31e_exogenous_forward_shadow_tracker.md`
- `data/reports/stage31e_exogenous_forward_shadow_tracker/stage31e_exogenous_forward_shadow_tracker.json`
- `data/reports/stage31e_exogenous_forward_shadow_tracker/stage31e_tracker_summary.csv`
- `data/reports/stage31e_exogenous_forward_shadow_tracker/stage31e_recent_signals.csv`

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage31e_exogenous_forward_shadow_tracker
cat data/reports/stage31e_exogenous_forward_shadow_tracker/stage31e_exogenous_forward_shadow_tracker.md
```

Optional environment variables:

```bash
export STAGE31E_LOOKBACK_HOURS=336
export STAGE31E_TOP_N=8
export STAGE31E_MIN_PRIOR_ROWS=20
```

## Guardrails

- Research/shadow only.
- No EA changes.
- No automatic trading.
- No paper/live/order authorization.
- No internet fetch.
- Expanding prior-year thresholds only.
