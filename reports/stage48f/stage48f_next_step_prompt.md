# Stage48F LoaderFix1 Next Step

Run the fixed Stage48F script on the AMarkets M5 export:

```bash
python3 app/stage48f_broker_reference_alignment_cost_model.py \
  --broker-csv ~/Downloads/amarkets_xauusd_5m.csv \
  --timeframe M5 \
  --point-size 0.01 \
  --slippage-buffer-bps 2 \
  --out reports/stage48f
```

Send back:

- reports/stage48f/stage48f_broker_reference_alignment_cost_model_summary.json
- reports/stage48f/stage48f_broker_reference_alignment_cost_model_report.md
- reports/stage48f/stage48f_cost_model.json
- reports/stage48f/stage48f_session_cost_profile.csv

No trading scan is authorized by this patch alone.
