# XAUUSD Stage25B Hotfix 1

Copy with:

```bash
cd ~/Desktop/xauusd-trader
unzip -o ~/Downloads/xauusd_stage25b_hotfix1_db_schema_introspection_patch.zip -d .
```

Run with:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage25b_db_first_regime_filter_validation
cat data/reports/stage25b_db_first_regime_filter_validation/stage25b_db_first_regime_filter_validation.md
```

If it still errors, send:

```text
data/reports/stage25b_db_first_regime_filter_validation/stage25b_db_first_regime_filter_validation.md
data/reports/stage25b_db_first_regime_filter_validation/stage25b_db_schema_diagnostic.csv
```
