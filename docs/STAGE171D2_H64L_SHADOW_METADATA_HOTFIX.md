# Stage171D2 H64L Shadow Metadata Hotfix

Purpose: patch Stage171D shadow logger metadata handling so it correctly recognizes the Stage171E exact locked-rule JSON.

This hotfix does not change H64L signal logic, thresholds, execution behavior, MT5 routing, or demo/live authorization. It only normalizes governance metadata when Stage171D reads:

`reports/stage171e_h64l_exact_rule_lock_from_archive/stage171e_h64l_exact_locked_rule.json`

Expected after patch:

- `exact_rule_locked = True`
- `rule_id = H64L_EXACT_LOCKED_RULE_V2_STAGE66A3`
- `rule_confidence = HIGH_FROM_ARCHIVED_LOCKED_RULE`
- signal remains `NO` unless all four locked H64L conditions pass.

Hard constraints:

- No threshold optimization.
- No MT5 signal file.
- No order routing.
- No demo/live authorization.
- GDELT/news remains guard-only.
