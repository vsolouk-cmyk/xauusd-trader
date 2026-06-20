# Next Step After Stage49

Run the importer every time the AMarkets files are updated:

```bash
python3 app/stage49_amarkets_multitf_importer.py \
  --root . \
  --input-dir ~/Downloads \
  --server-utc-offset-hours 3 \
  --point-size 0.01 \
  --out reports/stage49_broker_multitf
```

Then run the thesis diagnostic:

```bash
python3 app/stage49_multitf_trend_persistence_thesis.py \
  --root . \
  --db data/broker_normalized/amarkets_multitf.sqlite \
  --cost-model reports/stage48f/stage48f_cost_model.json \
  --out reports/stage49_broker_multitf
```

Send back:

```text
reports/stage49_broker_multitf/stage49_amarkets_multitf_import_summary.json
reports/stage49_broker_multitf/stage49_amarkets_multitf_import_report.md
reports/stage49_broker_multitf/stage49_multitf_trend_persistence_summary.json
reports/stage49_broker_multitf/stage49_multitf_trend_persistence_report.md
reports/stage49_broker_multitf/stage49_multitf_trend_persistence_candidates.csv
```
