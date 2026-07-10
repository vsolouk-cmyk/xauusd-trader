# Stage171C — H64L Evidence Recovery + Shadow Checklist

This stage is a narrow continuation of the H64L rescue path. It does not scan new rules and does not optimize thresholds.

## Purpose

Stage171B kept `exact_rule_locked=false`. Stage171C tries to recover Stage64/Stage64R evidence from the repo and produces a current manual shadow checklist from the available macro feature dataset.

## Non-goals

- No MT5 order signals.
- No demo/live authorization.
- No threshold re-optimization.
- No new feature family.
- No GDELT/news alpha.

## Outputs

- `stage171c_h64l_evidence_shadow_summary.json`
- `stage171c_decision.md`
- `stage171c_h64l_artifact_deep_inventory.csv`
- `stage171c_h64l_current_shadow_checklist.csv`
- `stage171c_h64l_column_map.csv`
- `stage171c_h64l_targeted_asof_fix_plan_review.csv`
- `stage171c_h64l_signal_ledger_inspection.json`
- `stage171c_h64l_locked_rule_candidate_v1.json`

## Interpretation

A checklist hit is a shadow/logging event only. It is not a trading instruction and must not be routed to MT5. Promotion requires targeted as-of fixes, Stage64R evidence review, and specialist acceptance.
