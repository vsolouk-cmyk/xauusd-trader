# Stage 8C Robustness Validation

Stage 8C validates Stage 8B promising candidates before any locked-strategy or EA proposal.

## What it validates

- Non-overlap execution candidates by default
- Cost x1/x3/x4/x6
- Year-by-year robustness
- Quarter/month robustness
- Drawdown
- Worst losing streak
- Emergency-stop sensitivity for time-exit candidates

## Run

```bash
cd ~/Desktop/xauusd-trader
python3 -m app.stage8c_robustness_validation
cat data/reports/stage8c_robustness_validation/stage8c_robustness_validation.md
```

## Optional: include overlap candidates too

Overlap results are diagnostic only and should not be used as execution basis.

```bash
python3 -m app.stage8c_robustness_validation --include-overlap
```

## Optional: customize emergency stops

```bash
python3 -m app.stage8c_robustness_validation --emergency-stops none,15,20,25,30
```

## Outputs

```text
data/reports/stage8c_robustness_validation/stage8c_robustness_validation.md
data/reports/stage8c_robustness_validation/stage8c_robustness_summaries.csv
data/reports/stage8c_robustness_validation/stage8c_stress_trades.csv
data/reports/stage8c_robustness_validation/stage8c_robustness_validation.json
```

## Important

- `emergency_stop_usd=none` for `time_exit_12h` is diagnostic only, not a deployable risk model.
- No EA change from this report alone.
- No demo/paper/live authorization.
