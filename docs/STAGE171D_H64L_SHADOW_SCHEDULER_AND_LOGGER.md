# Stage171D — H64L Shadow Scheduler and Logger

## Purpose

Stage171D turns the H64L rescue track into a repeatable daily shadow-log routine without creating any MT5 order signal or demo/live authorization.

It is designed after the specialist feedback: shadow observation should start immediately and run in parallel with targeted rule/as-of confirmation. This stage is not a new discovery scan and does not optimize any threshold.

## Inputs

Default inputs:

- `data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv`
- `reports/stage171b_h64l_exact_rule_extraction_and_shadow_start/stage171b_h64l_locked_rule_candidate.json`

The rule candidate is used only for metadata. The evaluated conditions are the fixed H64L checklist:

- `gold_sma20_over_50 > 0`
- `dxy_ret_20d < 0`
- `real_yield_change_20d < 0`
- `etf_flow_tonnes_3m > 0`

## Outputs

- `reports/stage171d_h64l_shadow_scheduler_and_logger/stage171d_h64l_shadow_scheduler_summary.json`
- `reports/stage171d_h64l_shadow_scheduler_and_logger/stage171d_decision.md`
- `reports/stage171d_h64l_shadow_scheduler_and_logger/stage171d_h64l_current_shadow_checklist.csv`
- `reports/stage171d_h64l_shadow_scheduler_and_logger/stage171d_h64l_manual_shadow_log.csv`
- `data/forward_shadow/h64l_manual_shadow_log.csv`

The `data/forward_shadow/h64l_manual_shadow_log.csv` file is the durable manual-shadow ledger.

## Scheduling

The script includes a `write-launchd-plist` command to create a macOS LaunchAgent that runs the daily checklist locally.

Default schedule: 09:15 local machine time.

The LaunchAgent runs only this log-only command and writes stdout/stderr into the Stage171D report folder.

## Hard constraints

- No MT5 signal file is written.
- No order routing is allowed.
- No demo/live authorization is emitted.
- No threshold re-optimization is performed.
- GDELT/news remains guard-only.

## Interpretation

If `h64l_shadow_signal=NO`, do nothing beyond logging.

If `h64l_shadow_signal=YES`, this is still not an order instruction. It means the shadow checklist saw a hit and the team should review exact Stage64R rule evidence and specialist approval before any limited demo bridge.
