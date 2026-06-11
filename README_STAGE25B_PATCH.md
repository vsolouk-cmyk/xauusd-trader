# Stage25B DB-First Regime Filter Validation Patch

Copy into the repo root:

```bash
cd ~/Desktop/xauusd-trader
unzip -o ~/Downloads/xauusd_stage25b_db_first_regime_filter_validation_patch.zip -d .
```

Run:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage25b_db_first_regime_filter_validation
cat data/reports/stage25b_db_first_regime_filter_validation/stage25b_db_first_regime_filter_validation.md
```

Safe git commands after a successful run:

```bash
cd ~/Desktop/xauusd-trader
git add -A
git commit -m "Add Stage25B DB-first regime filter validation"
git pull --rebase
git push
```
