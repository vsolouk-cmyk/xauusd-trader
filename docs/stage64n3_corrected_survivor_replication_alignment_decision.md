# Stage64N3 - Corrected Survivor Replication and Alignment Decision

This stage consumes Stage64N1B and decides whether the reconciled corrected survivor may continue to replication/alignment audit design.

It does not run validation, does not generate signals, does not connect to a broker, and does not authorize paper/live execution.

## Required input

```text
reports/stage64n1b_a2_nonparametric_reconciliation/stage64n1b_a2_nonparametric_reconciliation_summary.json
```

## Outputs

```text
reports/stage64n3_corrected_survivor_replication_alignment_decision/stage64n3_corrected_survivor_replication_alignment_decision_summary.json
reports/stage64n3_corrected_survivor_replication_alignment_decision/stage64n3_corrected_survivor_replication_alignment_decision_report.md
reports/stage64n3_corrected_survivor_replication_alignment_decision/stage64n3_replication_alignment_requirements.csv
reports/stage64n3_corrected_survivor_replication_alignment_decision/stage64n3_decision_matrix.csv
```

## Governance

A reconciled robustness audit does not authorize promotion. Broker/spot alignment and independent replication remain required before any commercialization or broker XAUUSD validation claim.
