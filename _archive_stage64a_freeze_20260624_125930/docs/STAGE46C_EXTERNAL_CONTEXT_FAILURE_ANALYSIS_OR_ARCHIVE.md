# Stage46C External Context Failure Analysis / Archive

Stage46C is a diagnostic and decision stage after the fresh Stage46A external-context baseline scan.

It reads:

```text
reports/stage46a/stage46a_external_context_baseline_scan_implementation_summary.json
reports/stage46a/stage46a_candidate_metrics.csv
```

It writes:

```text
reports/stage46c/stage46c_external_context_failure_analysis_or_archive_summary.json
reports/stage46c/stage46c_external_context_failure_analysis_or_archive.md
reports/stage46c/stage46c_failure_bucket_matrix.csv
reports/stage46c/stage46c_family_failure_summary.csv
reports/stage46c/stage46c_top_candidate_diagnostic.csv
reports/stage46c/stage46c_recommendation_contract.csv
```

## Scope

This stage does not create signals, does not shortlist candidates, does not rescue Stage41/42/43 rows, and does not authorize EA, paper-live, or live trading.

## Intended interpretation

If Stage46A has zero strict and zero soft survivors, Stage46C should explain the failure drivers and recommend final archive of the branch unless a genuinely new predefined thesis is selected.

Typical failure buckets:

```text
no_survivors
no_positive_net_edge
cost_overwhelms_gross_edge
oos_negative
quarter_stability_negative
bootstrap_floor_negative
benchmark_residual_too_small
```

## Run

```bash
python3 scripts/stage46c_external_context_failure_analysis_or_archive.py --print-summary
```

## Gates

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```
