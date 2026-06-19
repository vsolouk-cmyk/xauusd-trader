# Stage48F Broker Reference Alignment and Cost Model Calibration

This patch combines the broker-realism decision and the executable calibration step. It does not generate signals and does not authorize EA, paper-live, or live trading.

## Purpose

Use the validated AMarkets/MT5 M5 spread export as broker-real input, align it with the reference TwelveData M5 feed, and produce a reusable cost model for later cost-aware research.

## Inputs

Default broker input:

```text
~/Downloads/amarkets_xauusd_5m.csv
```

Reference input is autodiscovered from:

```text
data/normalized/normalized_twelvedata_XAU_USD_5min_backfill_*.csv
```

## Outputs

```text
reports/stage48f/stage48f_broker_reference_alignment_cost_model_summary.json
reports/stage48f/stage48f_broker_reference_alignment_cost_model_report.md
reports/stage48f/stage48f_cost_model.json
reports/stage48f/stage48f_session_cost_profile.csv
reports/stage48f/stage48f_alignment_sample.csv
```

## Decision rules

The cost model is marked ready only if:

- broker rows are sufficient,
- broker spread coverage is at least 80%,
- reference alignment has at least 5000 common timestamps,
- aligned coverage is at least 20 days.

Even when ready, promotion, EA, paper-live, and live trading remain NO_GO.
