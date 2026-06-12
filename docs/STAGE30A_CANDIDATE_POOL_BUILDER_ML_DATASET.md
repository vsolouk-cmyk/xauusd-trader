# Stage30A Candidate Pool Builder + ML-ready Meta Dataset

Stage30A builds a normalized, ML-ready research dataset from previous XAUUSD candidate/outcome artifacts.

It does not create entries, trackers, EA changes, paper trades, live trades, or order instructions.

## Outputs

- `data/reports/stage30a_candidate_pool_builder_ml_dataset/stage30a_ml_meta_dataset.csv`
- `data/reports/stage30a_candidate_pool_builder_ml_dataset/stage30a_feature_quality_report.csv`
- `data/reports/stage30a_candidate_pool_builder_ml_dataset/stage30a_candidate_family_contribution.csv`
- `data/reports/stage30a_candidate_pool_builder_ml_dataset/stage30a_artifact_manifest.csv`
- `data/reports/stage30a_candidate_pool_builder_ml_dataset/stage30a_candidate_pool_builder_ml_dataset.md`

## Forward-safe feature policy

Stage30A exports only a controlled whitelist of features intended to be knowable at entry time:

- prior day range
- Asia range and efficiency
- London range and efficiency
- completed-H1 range/ATR features
- day-of-week/month/entry hour
- direction and alignment flags

Leak-prone fields such as full-day range/high/low/close, early-NY fields, exit, TP, SL, outcome-derived fields, and future state fields are not exported as ML features.
