# Stage171 H64L Rescue Parallel Track

Stage171 replaces the rejected audit-before-action design with a parallel track:

- Track 1.5: 30-minute triage mapping H64L feature requirements to Stage170C blockers.
- Track 1: timeboxed H64L as-of audit, maximum 3 business days.
- Track 2: manual H64L shadow checklist starts immediately, log-only, no orders.

This stage does not optimize thresholds, does not create MT5 signals, and does not authorize demo/live orders.

## Why

The external specialist feedback accepted the strategic pivot to H64L but rejected a sequential Stage171 audit followed by Stage172 shadow. The correction is to run audit and shadow checklist in parallel, with a hard timebox and explicit fallback.

## Outputs

- `stage171_h64l_rescue_parallel_track_summary.json`
- `stage171_decision.md`
- `stage171_h64l_artifact_inventory.csv`
- `stage171_h64l_feature_blocker_triage.csv`
- `stage171_h64l_manual_shadow_checklist.csv`

## Hard rules

- No threshold re-optimization.
- Mechanical as-of lag fixes only.
- GDELT/news remains guard only.
- Manual shadow can start immediately; orders cannot.
- After 3 business days, incomplete audit is `INCONCLUSIVE`, not open-ended.
