# Stage30B — ML-lite Feature Ranker / Scorecard

Stage30B consumes the Stage30A ML-ready candidate pool and evaluates simple, auditable meta-gates under time-aware out-of-sample checks.

It does not create an EA, order, paper trade, live trade, or operational signal.

## Main safeguards

- Uses only Stage30A's exported ML dataset.
- Uses a strict whitelist of forward-safe features.
- Blocks `source_stage`, `source_file`, `family`, `candidate_name`, `year`, and `direction_num` from modeling by default.
- Selects gates only on training years and evaluates them on future years.
- Produces family/source holdout diagnostics.

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage30b_ml_lite_feature_ranker
cat data/reports/stage30b_ml_lite_feature_ranker/stage30b_ml_lite_feature_ranker.md
```

## Output

- `stage30b_ml_lite_feature_ranker.md`
- `stage30b_ml_lite_feature_ranker.json`
- `stage30b_yearly_oos_gate_results.csv`
- `stage30b_selected_train_gates.csv`
- `stage30b_scorecard_ensemble_oos.csv`
- `stage30b_scorecard_predictions.csv`
- `stage30b_family_holdout.csv`
