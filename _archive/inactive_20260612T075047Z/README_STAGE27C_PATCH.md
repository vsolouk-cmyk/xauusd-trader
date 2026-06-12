# Stage27C DB-First H1 ATR Gate Validation Patch

## Install

```bash
cd ~/Desktop/xauusd-trader
unzip -o ~/Downloads/xauusd_stage27c_db_first_h1_atr_gate_validation_patch.zip -d .
```

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage27c_db_first_h1_atr_gate_validation
cat data/reports/stage27c_db_first_h1_atr_gate_validation/stage27c_db_first_h1_atr_gate_validation.md
```

## Optional artifact override

```bash
cd ~/Desktop/xauusd-trader
STAGE27C_TRADE_ARTIFACT=data/reports/stage25c_deduped_filter_validation/stage25c_enriched_canonical_trades.csv \
python3 -m app.stage27c_db_first_h1_atr_gate_validation
```

## Git after success

```bash
cd ~/Desktop/xauusd-trader
git add -A
git commit -m "Add Stage27C DB-first H1 ATR gate validation"
git pull --rebase
git push
```
