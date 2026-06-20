# Stage49B Next Step

Run the fast importer first:

```bash
python3 app/stage49_amarkets_multitf_importer_fast.py \
  --root . \
  --input-dir ~/Downloads \
  --server-utc-offset-hours 3 \
  --point-size 0.01 \
  --out reports/stage49_broker_multitf
```

Then run hard audit on the Stage49 diagnostic survivors:

```bash
python3 app/stage49_multitf_trend_persistence_hard_audit.py \
  --root . \
  --db data/broker_normalized/amarkets_multitf.sqlite \
  --candidates reports/stage49_broker_multitf/stage49_multitf_trend_persistence_candidates.csv \
  --cost-model reports/stage48f/stage48f_cost_model.json \
  --out reports/stage49_broker_multitf
```

Send these outputs:

```text
reports/stage49_broker_multitf/stage49_fast_import_summary.json
reports/stage49_broker_multitf/stage49_fast_import_report.md
reports/stage49_broker_multitf/stage49_multitf_trend_persistence_hard_audit_summary.json
reports/stage49_broker_multitf/stage49_multitf_trend_persistence_hard_audit_report.md
reports/stage49_broker_multitf/stage49_multitf_trend_persistence_hard_audit_candidates.csv
```
