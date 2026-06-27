# Stage96D COT Rule Warm-up Accounting Fix

Stage96D fixes the remaining COT discovery data-quality accounting issue.

## Problem

COT features are weekly, lagged and rolling. The daily macro panel starts before COT z-score/change features are fully available. Earlier Stage96 outputs still counted these unavoidable pre-coverage and rolling warm-up rows as `MISSING_REQUIRED_FEATURE_ROWS`, which killed otherwise valid COT candidates.

## Fix

For each rule, Stage96D finds the first row where that rule's required feature set is simultaneously complete. Rows before that point are counted as `warmup_missing_rows_ignored`. Missing rows after that point remain hard failures in `missing_required_feature_rows`.

## Scope

Research-only. No threshold tuning, no order authorization, no MT5/EA/observer change.
