# Stage30A Patch

Adds:

- `app/stage30a_candidate_pool_builder_ml_dataset.py`
- `docs/STAGE30A_CANDIDATE_POOL_BUILDER_ML_DATASET.md`
- updated `tools/archive_inactive_xauusd_artifacts.py`

Run:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage30a_candidate_pool_builder_ml_dataset
cat data/reports/stage30a_candidate_pool_builder_ml_dataset/stage30a_candidate_pool_builder_ml_dataset.md
```

Optional extra artifacts:

```bash
STAGE30A_EXTRA_ARTIFACTS="path/to/a.csv:path/to/b.csv" \
python3 -m app.stage30a_candidate_pool_builder_ml_dataset
```
