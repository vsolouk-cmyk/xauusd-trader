# Stage171B — H64L Exact Rule Extraction and Shadow Start

Purpose: convert Stage171's parallel-track framework into immediately useful rescue support without falling back into audit-before-action.

This stage is read-only. It does not create MT5 order signals, does not authorize demo/live orders, and does not optimize thresholds.

Outputs:

- `stage171b_h64l_exact_rule_extraction_summary.json`
- `stage171b_decision.md`
- `stage171b_h64l_locked_rule_candidate.json`
- `stage171b_h64l_artifact_inventory.csv`
- `stage171b_h64l_targeted_asof_fix_plan.csv`
- `stage171b_h64l_manual_shadow_log_template.csv`

Rules:

- Manual shadow logging starts immediately.
- Audit is timeboxed to 3 business days.
- Incomplete evidence after the timebox becomes `INCONCLUSIVE`, not an open-ended audit.
- Only mechanical as-of fixes are allowed.
- GDELT/news remains guard only.
- No threshold re-optimization.
