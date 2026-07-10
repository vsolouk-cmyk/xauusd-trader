# Stage170C — As-Of Join Enforcement and Validation Framework

Stage170C converts the Stage170B design contract into machine-readable checks and creates the validation scaffolding required before any new alpha discovery.

## Purpose

This is a read-only governance/enforcement stage. It creates no candidates, writes no MT5 files, and does not authorize demo/live orders.

It produces:

- `stage170c_asof_enforcement_summary.json`
- `stage170c_decision.md`
- `stage170c_data_contract_enforcement_report.csv`
- `stage170c_temporal_join_test_report.csv`
- `stage170c_purged_walk_forward_folds.csv`
- `stage170c_multiple_testing_adjustment_template.csv`
- `stage170c_path_label_framework.csv`

## Interpretation

If the decision is `STAGE170C_ASOF_ENFORCEMENT_BLOCKS_NEW_DISCOVERY`, do not run new discovery. Fix the source contract and implement loader-level temporal join tests.

If the decision is `STAGE170C_ASOF_FRAMEWORK_READY_FOR_READONLY_DISCOVERY_ONLY`, read-only discovery may resume, but commercial promotion and demo release remain blocked until purged walk-forward, multiple-testing control and path-aware labels are implemented.

## Why this stage exists

Stage170A/170B found that implementation discipline has improved, but historical timing integrity and validation design are not yet strong enough for new candidate promotion. This stage prevents the project from falling back into broad scans before the data contract becomes enforceable.

## Safety

- `order_routing_allowed = False`
- `demo_release_allowed = False`
- No MT5 signal files are written.
