# Stage64O - External Replication and Broker/Spot Alignment Fastlane

Purpose: compress the next governance steps into one no-order stage.

This stage:

1. Verifies the Stage64N4 fastlane replication result is the valid input.
2. Creates an external replication bundle manifest with hashes of local inputs.
3. Attempts an offline broker/spot alignment audit:
   - Uses `data/macro_regime/raw/broker_or_spot_gold_d1_ohlc_2011_present.csv` if present.
   - Otherwise derives broker D1 from `data/broker_normalized/amarkets_multitf.sqlite` using the preferred timeframe.
4. Compares broker/spot daily returns against `data/macro_regime/raw/gold_d1_ohlc_2011_present.csv`.
5. Emits pass/fail gates without authorizing order, broker connection, paper-live, live, or commercialization.

This is not an order stage, not a broker connection stage, and not a new hypothesis scan.

Run:

```bash
python3 app/stage64o_external_replication_broker_alignment_fastlane.py \
  --root . \
  --config configs/stage64o_external_replication_broker_alignment_fastlane.json \
  --out reports/stage64o_external_replication_broker_alignment_fastlane
```

Required outputs:

- `stage64o_external_replication_broker_alignment_fastlane_summary.json`
- `stage64o_external_replication_broker_alignment_fastlane_report.md`
- `stage64o_external_replication_bundle_manifest.json`
- `stage64o_broker_spot_alignment_metrics.json`
- `stage64o_broker_spot_alignment_gates.csv`
