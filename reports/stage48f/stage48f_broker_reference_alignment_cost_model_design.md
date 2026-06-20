# Stage48F LoaderFix1: Broker Reference Alignment and Cost Model Calibration

Status: patch/hotfix only. No trading scan, EA, paper-live, or live action.

## Why this hotfix exists

The first Stage48F run parsed the AMarkets MT5 export correctly, but the readiness gate used the wrong denominator for broker spread coverage. It divided the aligned spread rows by all broker rows, causing a false low coverage result even though the broker export itself had almost full numeric spread coverage.

This hotfix separates:

- broker_raw_spread_coverage_pct = numeric spread rows / accepted broker rows
- aligned_spread_coverage_pct = numeric spread rows in aligned subset / aligned rows

It also improves broker server-time offset selection. The earlier rule selected the offset using timestamp match count only. Adjacent offsets can tie when the reference feed has a continuous M5 grid. The new rule keeps offsets within 98% of the best timestamp match count and then selects the offset with the lowest median absolute broker-reference close basis.

## Outputs

- stage48f_broker_reference_alignment_cost_model_summary.json
- stage48f_broker_reference_alignment_cost_model_report.md
- stage48f_cost_model.json
- stage48f_session_cost_profile.csv
- stage48f_alignment_sample.csv

## Gate

A cost model is ready only if:

- broker rows >= 5000
- broker raw spread coverage >= 80%
- aligned rows >= requested minimum
- aligned coverage days >= requested minimum
- aligned spread coverage >= 80%

Price basis remains diagnostic. It is not a trading permission.
