# Next Step Prompt

Run the broker-real cost-aware diagnostic:

```bash
python3 app/stage48_cost_aware_broker_diagnostic.py \
  --broker-csv ~/Downloads/amarkets_xauusd_5m.csv \
  --cost-model reports/stage48f/stage48f_cost_model.json \
  --timeframe M5 \
  --point-size 0.01 \
  --out reports/stage48_cost_aware
```

Send these outputs:

```text
reports/stage48_cost_aware/stage48_cost_aware_broker_diagnostic_summary.json
reports/stage48_cost_aware/stage48_cost_aware_broker_diagnostic_report.md
reports/stage48_cost_aware/stage48_cost_aware_broker_diagnostic_candidates.csv
```

Do not promote, run EA, paper-live, or live from this stage.
