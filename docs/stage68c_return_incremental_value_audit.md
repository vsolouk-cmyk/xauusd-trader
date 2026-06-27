# Stage68C Return / Incremental Value Audit

Diagnostic-only stage for the XAUUSD macro-regime program.

## Purpose

Stage68B proved that the registered rules have material overlap and clustering. Stage68C adds return and incremental value diagnostics so the program does not treat clustered signals as independent opportunities.

## Inputs

- `data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv`
- Registered rules from `configs/stage68c_return_incremental_value_audit.json`

## Outputs

- `stage68c_return_incremental_value_audit_summary.json`
- `stage68c_return_incremental_value_audit_report.md`
- `stage68c_rule_entry_returns.csv`
- `stage68c_entry_clusters.csv`
- `stage68c_incremental_return_contribution.csv`

## Method

- Reconstructs registered active masks.
- Creates no-overlap/cooldown entries using each rule horizon.
- Computes forward gross and net bps return from gold close to horizon exit.
- Applies a total bps cost assumption from config.
- Separates same-day unique and overlapped entries.
- Clusters raw entries within a configurable calendar-day window.

## Governance

Stage68C is diagnostic only.
It does not authorize paper orders, broker connection, EA promotion, paper-live, or live execution.
