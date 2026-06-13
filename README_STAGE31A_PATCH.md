# Stage31A Patch — External/Macro/News Feature Ingestion

Install:

```bash
cd ~/Desktop/xauusd-trader
unzip -o ~/Downloads/xauusd_stage31a_exogenous_feature_ingestion_patch.zip -d .
```

Run:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage31a_exogenous_feature_ingestion
cat data/reports/stage31a_exogenous_feature_ingestion/stage31a_exogenous_feature_ingestion.md
```

Optional explicit Stage30A dataset:

```bash
STAGE31A_DATASET=data/reports/stage30a_candidate_pool_builder_ml_dataset/stage30a_ml_meta_dataset.csv \
python3 -m app.stage31a_exogenous_feature_ingestion
```

The first run creates templates in `data/exogenous/` if the external CSVs are missing.
