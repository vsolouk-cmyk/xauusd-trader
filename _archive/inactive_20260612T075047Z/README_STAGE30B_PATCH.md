# Stage30B ML-lite Feature Ranker Patch

Adds:

- `app/stage30b_ml_lite_feature_ranker.py`
- `docs/STAGE30B_ML_LITE_FEATURE_RANKER.md`
- updated `tools/archive_inactive_xauusd_artifacts.py`

Install:

```bash
cd ~/Desktop/xauusd-trader
unzip -o ~/Downloads/xauusd_stage30b_ml_lite_feature_ranker_patch.zip -d .
```

Run:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage30b_ml_lite_feature_ranker
cat data/reports/stage30b_ml_lite_feature_ranker/stage30b_ml_lite_feature_ranker.md
```

Optional:

```bash
STAGE30B_DATASET=data/reports/stage30a_candidate_pool_builder_ml_dataset/stage30a_ml_meta_dataset.csv \
python3 -m app.stage30b_ml_lite_feature_ranker
```

Git:

```bash
git add -A
git commit -m "Add Stage30B ML-lite feature ranker"
git pull --rebase
git push
```
