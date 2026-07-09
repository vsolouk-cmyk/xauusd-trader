# Stage170A Methodology, Temporal Integrity and Feature Adequacy Audit

## Purpose

Stage170A is a read-only audit gate before any new XAUUSD discovery stage. It exists because Stage166F/167C/168/169 showed that the GDELT/news branch can be used as a current-event guard, but not as a direct alpha with the current feature and rule-space design.

The stage does not create candidates, does not write MT5 signal files, and does not authorize demo or live orders.

## What it audits

- Stage decision inventory from existing reports.
- Timing and as-of risks for broker bars, macro, scheduled events, COT, ETF, GDELT/news and manual events.
- Temporal alignment metadata for key files.
- Validation weaknesses: multiple testing, walk-forward/purged validation, label design, concentration and cost realism.
- Recommendations before the next commercial discovery attempt.

## Why this stage exists

The project has accumulated many stages, features and scans. A new scan without a methodology audit can repeat the same failure loop: broad candidate search, weak edge, low frequency, and then waiting for more samples. Stage170A forces a formal review of whether the data, labels, joins and validation design are adequate before any further promotion path.

## Outputs

- `stage170a_methodology_audit_summary.json`
- `stage170a_decision.md`
- `stage170a_stage_decision_inventory.csv`
- `stage170a_temporal_alignment_audit.csv`
- `stage170a_feature_timing_ledger.csv`
- `stage170a_validation_risk_register.csv`
- `stage170a_methodology_recommendations.csv`

## Expected decision

When Stage169 confirms the news branch kill/guard decision, Stage170A should return:

`STAGE170A_METHOD_AUDIT_REQUIRED_BEFORE_NEW_DISCOVERY`

Recommended action:

`FREEZE_NEW_DISCOVERY; BUILD_ASOF_DATA_CONTRACT_AND_VALIDATION_REDESIGN`

## Next expected stage

The correct next implementation is not another alpha scan. The next stage should be a data-contract and validation redesign stage, for example:

`Stage170B_ASOF_DATA_CONTRACT_AND_VALIDATION_FRAMEWORK`
