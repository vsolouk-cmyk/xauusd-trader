# Stage31A FRED Downloader Hotfix

Fixes FRED CSV date column compatibility. The downloader now accepts both `DATE` and `observation_date` as the date column.

Install:

```bash
cd ~/Desktop/xauusd-trader
unzip -o ~/Downloads/xauusd_stage31a_fred_downloader_hotfix.zip -d .
```

Run:

```bash
cd ~/Desktop/xauusd-trader
python3 tools/download_fred_exogenous.py
python3 -m app.stage31a_exogenous_feature_ingestion
cat data/reports/stage31a_exogenous_feature_ingestion/stage31a_exogenous_feature_ingestion.md
```
