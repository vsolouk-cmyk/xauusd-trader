# XAUUSD Stage 5B Preparation Patch

This patch adds preparation tooling only. It does not modify the deployed MT5 EA and does not authorize orders.

## Added files

```text
app/stage5a_ea_safety_audit.py
app/stage5b_dryrun_log_validator.py
configs/locked_strategy_v1.yaml
configs/locked_strategy_v1.json
samples/stage5b_mt5_dryrun_sample.csv
docs/STAGE5A1_EA_SAFETY_AUDIT.md
docs/STAGE5B_DRYRUN_LOG_VALIDATOR.md
docs/STAGE5B_PATCH_README.md
```

## Safe dry-run preparation sequence

Run from repo root:

```bash
python3 -m app.stage5a_ea_safety_audit
python3 -m app.stage5b_dryrun_log_validator --csv samples/stage5b_mt5_dryrun_sample.csv
```

When the market opens and the real MT5 CSV exists:

```bash
python3 -m app.stage5b_dryrun_log_validator --csv "/FULL/PATH/TO/XAUUSD_DryRun_v1_signals.csv"
```

## Commit

Only commit source/config/docs/sample files. Do not commit runtime reports.

```bash
git add app/stage5a_ea_safety_audit.py
git add app/stage5b_dryrun_log_validator.py
git add configs/locked_strategy_v1.yaml
git add configs/locked_strategy_v1.json
git add samples/stage5b_mt5_dryrun_sample.csv
git add docs/STAGE5A1_EA_SAFETY_AUDIT.md
git add docs/STAGE5B_DRYRUN_LOG_VALIDATOR.md
git add docs/STAGE5B_PATCH_README.md

git commit -m "Add Stage 5B dry-run validation tooling"
git pull --rebase
git push
```
