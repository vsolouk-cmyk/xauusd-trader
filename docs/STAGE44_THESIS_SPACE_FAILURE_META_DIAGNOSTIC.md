# Stage44_THESIS_SPACE_FAILURE_META_DIAGNOSTIC

## Purpose

Stage44 is not another signal scan. It is a meta-diagnostic over recent failed thesis scans, especially Stage41, Stage42, and Stage43.

The goal is to identify the dominant reason the thesis space is failing before launching another blind megascan.

## Hard decision state

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

Stage44 cannot promote any candidate. It cannot create a trade alert, EA, paper-live layer, or live layer.

## Inputs

Default inputs expected in the repo:

```text
reports/stage41/stage41_parallel_thesis_megascan_v2_summary.json
reports/stage41/stage41_parallel_thesis_megascan_v2_candidates.csv

reports/stage42/stage42_parallel_intraday_execution_megascan_v3_summary.json
reports/stage42/stage42_parallel_intraday_execution_megascan_v3_candidates.csv

reports/stage43/stage43_parallel_context_regime_megascan_v4_summary.json
reports/stage43/stage43_parallel_context_regime_megascan_v4_candidates.csv
```

Missing default inputs are reported but are not fatal if at least one valid stage pair exists.

## What the script measures

- Aggregate candidate count.
- Strict and soft shortlist totals.
- Classification counts.
- Failed reason counts.
- Failed reason buckets:
  - event scarcity
  - cost / mean edge weakness
  - benchmark residual weakness
  - train segment weakness
  - OOS segment weakness
  - quarter stability weakness
  - bootstrap weakness
  - path risk / stop touch weakness
  - concentration risk
- Numeric profiles for cost, residual, train/OOS, worst-quarter, bootstrap and event count metrics.
- Best-looking rows by mean, residual, worst-quarter and bootstrap, only as diagnostic evidence.

## Output files

```text
reports/stage44/stage44_thesis_space_failure_meta_diagnostic_summary.json
reports/stage44/stage44_thesis_space_failure_meta_diagnostic.md
reports/stage44/stage44_thesis_space_failure_reasons_long.csv
```

## Expected interpretation

If Stage41/42/43 all have zero strict and zero soft shortlist, Stage44 should recommend against Stage41B/42B/43B and against another blind thesis scan.

Likely next branch:

```text
Stage45_COST_AWARE_BASELINE_RECALIBRATION_OR_EXTERNAL_CONTEXT_DECISION
```

## Anti-overfit rule

Do not use Stage44 to rescue failed candidates by removing weak hours, months, years, quarters, volatility states, context states, or stop-touch buckets after seeing outputs.

Stage44 is diagnostic only. It exists to decide whether the next effort should be:

1. Cost/spread/slippage recalibration.
2. External-context decision: DXY, yields, macro/news calendar, CME GC/MGC reference.
3. Data-source/feed comparison.
4. A genuinely new pre-defined thesis family.

## Run command

```bash
python3 scripts/stage44_thesis_space_failure_meta_diagnostic.py --print-summary
```
