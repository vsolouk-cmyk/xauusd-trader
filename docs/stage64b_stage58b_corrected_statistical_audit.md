# Stage64B - Stage58B Corrected Statistical Audit

## Purpose

Stage64B converts Stage58B from a promotion-style forward watch into a corrected statistical reference stream. It performs a report-only audit of the existing Stage58B telemetry, estimates the candidate/variant count available from Stage58A artifacts, applies a conservative multiple-testing correction, and assigns a final role to Stage58B.

## Non-negotiable constraints

- No paper-order.
- No paper-live.
- No live.
- No EA promotion.
- No state mutation.
- No rescue filtering or parameter tweaking.
- Stage58B can only remain passive telemetry / secondary research under Stage64 policy.

## Inputs

Default active inputs after Stage64A cleanup:

```text
reports/stage59_context_forward_gates/stage59_context_forward_gate_summary.json
reports/stage58_context_forward_shadow/stage58b_context_forward_shadow_summary.json
reports/stage58_context_aware_stage51/stage58a_context_aware_stage51_regime_audit_candidates.csv
data/shadow/stage58b_context_forward_shadow.sqlite
reports/stage64a_research_freeze_cleanup/stage64a_experiment_ledger_skeleton.csv
```

## Outputs

```text
reports/stage64b_stage58b_corrected_statistical_audit/stage64b_stage58b_corrected_statistical_audit_summary.json
reports/stage64b_stage58b_corrected_statistical_audit/stage64b_stage58b_corrected_statistical_audit_report.md
```

## Statistical logic

The audit uses the current evaluated Stage58B forward outcomes and computes:

- exact one-sided sign-test p-value for win count under p0 = 0.5;
- Bonferroni-corrected sign-test p-value;
- mean-positive one-sided normal approximation when per-signal stress values are available from SQLite;
- Bonferroni correction using an effective test count equal to the maximum of:
  - Stage58A candidate row count;
  - Stage58A pass-like row count;
  - active Stage58B candidate count;
  - configured conservative floor, default 100.

This is intentionally conservative. The goal is not to rescue Stage58B but to prevent mistaking a low-sample, selected context filter for a validated edge.

## Execution

```bash
python3 app/stage64b_stage58b_corrected_statistical_audit.py \
  --root . \
  --config configs/stage64b_stage58b_corrected_statistical_audit.json \
  --out reports/stage64b_stage58b_corrected_statistical_audit
```

## Expected decision pattern

Current Stage58B is expected to remain one of these roles:

```text
PASSIVE_TELEMETRY_SECONDARY_RESEARCH_ONLY_NO_PROMOTION
SECONDARY_RESEARCH_ONLY_MTC_NOT_SIGNIFICANT_NO_PROMOTION
ARCHIVE_OR_PASSIVE_TELEMETRY_ONLY_NO_PROMOTION
```

No output from Stage64B authorizes order placement.
