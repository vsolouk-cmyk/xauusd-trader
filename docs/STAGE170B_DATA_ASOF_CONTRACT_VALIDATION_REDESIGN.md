# Stage170B — Data As-Of Contract and Validation Redesign

## Purpose

Stage170B turns the Stage170A methodology audit into concrete governance artifacts. It is not a trading stage and does not create candidate rules.

## Why this stage exists

Stage170A concluded that new discovery should be frozen until the project has:

- explicit source-level as-of timing contracts,
- loader-level temporal integrity tests,
- purged/embargoed walk-forward validation,
- path-aware labels,
- multiple-testing controls,
- execution/cost realism gates.

## Outputs

- `stage170b_data_asof_contract.csv`
- `stage170b_data_asof_contract_summary.json`
- `stage170b_validation_redesign_matrix.csv`
- `stage170b_multiple_testing_control_plan.csv`
- `stage170b_purged_walk_forward_plan.csv`
- `stage170b_decision.md`

## Operating decision

The expected decision is:

`STAGE170B_DATA_CONTRACT_REQUIRED_BEFORE_NEW_DISCOVERY`

This means Stage170 discovery remains frozen until source contracts are reviewed and enforcement tests are implemented.

## What this stage does not do

- It does not scan new alpha rules.
- It does not write MT5 signal files.
- It does not authorize demo or live trading.
- It does not convert GDELT/news back into alpha.

## Intended next stage

`Stage170C_ASOF_JOIN_ENFORCEMENT_AND_PURGED_WALK_FORWARD_FRAMEWORK`

This should convert the contract into reusable loader assertions and validation mechanics.
