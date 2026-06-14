# README — Stage28C Forward-Safe Meta-Gate Validation Patch

## Files added

- `app/stage28c_forward_safe_meta_gate_validation.py`
- `docs/STAGE28C_FORWARD_SAFE_META_GATE_VALIDATION.md`

## Install

```bash
cd ~/Desktop/xauusd-trader
unzip -o ~/Downloads/xauusd_stage28c_forward_safe_meta_gate_validation_patch.zip -d .
```

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage28c_forward_safe_meta_gate_validation
cat data/reports/stage28c_forward_safe_meta_gate_validation/stage28c_forward_safe_meta_gate_validation.md
```

## Optional explicit artifact

```bash
cd ~/Desktop/xauusd-trader
STAGE28C_TRADES_ARTIFACT=data/reports/stage28b_ml_meta_feature_screen/stage28b_normalized_lineage_trades.csv \
python3 -m app.stage28c_forward_safe_meta_gate_validation
```

## Scope

Research/shadow validation only. No EA change, no automatic trading, no paper/live/order authorization.
