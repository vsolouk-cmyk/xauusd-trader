# Stage28B Hotfix2 Patch

Files:

- `app/stage28b_ml_meta_feature_screen.py`
- `docs/STAGE28B_HOTFIX2_STRICT_FORWARD_SAFE.md`

Install:

```bash
cd ~/Desktop/xauusd-trader
unzip -o ~/Downloads/xauusd_stage28b_hotfix2_strict_forward_safe_patch.zip -d .
```

Run:

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage28b_ml_meta_feature_screen
cat data/reports/stage28b_ml_meta_feature_screen/stage28b_ml_meta_feature_screen.md
```

Optional explicit artifact:

```bash
STAGE28B_TRADE_ARTIFACT=data/reports/stage25c_deduped_filter_validation/stage25c_enriched_canonical_trades.csv \
python3 -m app.stage28b_ml_meta_feature_screen
```
