# Stage39D_CONDITION_ROBUSTNESS_AND_FORWARD_SPLIT_AUDIT

## Scope

```text
scope = RESEARCH_STAGE_ONLY_NO_PROMOTION
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

Stage39D is allowed only because Stage39C produced condition bucket watch rows. It does not promote any candidate. It audits whether Stage39C condition buckets survive stricter forward robustness checks.

## Inputs

Expected inputs from Stage39C:

```text
reports/stage39c/stage39c_condition_diagnostic_summary.json
reports/stage39c/stage39c_condition_event_rows.csv
reports/stage39c/stage39c_condition_bucket_summary.csv
reports/stage39c/stage39c_condition_cross_matrix.csv
```

The script intentionally avoids a fresh DB load. Stage39C already produced event rows with condition labels. This reduces schema/filtering risk and keeps Stage39D focused on the robustness question.

## What Stage39D audits

For every Stage39C row classified as:

```text
CONDITION_BUCKET_WATCH_ONLY_NO_PROMOTION
```

Stage39D checks:

- event count,
- year coverage,
- ex-2025 mean,
- leave-one-year-out minimum,
- chronological first/second half,
- chronological quarters,
- recent-third split,
- cost plus slippage stress,
- MAE/MFE path risk,
- stop/target touch rates.

It also audits cross-condition watch rows if present in the Stage39C cross matrix.

## Output classifications

```text
STRICT_CONDITION_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION
FORWARD_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION
WEAK_FORWARD_ROBUSTNESS_NO_PROMOTION
FAIL_CONDITION_ROBUSTNESS_NO_PROMOTION
YEAR_SPLIT_WEAK_NO_PROMOTION
ADVERSE_PATH_RISK_TOO_HIGH_NO_PROMOTION
INSUFFICIENT_CONDITION_EVENTS_NO_PROMOTION
```

Only the first two classifications are allowed to continue to a later frozen-rule audit. They still remain research-only and no-go for EA/paper/live/live.

## Default thresholds

```text
min_events = 30
min_years = 4
min_ex2025_events = 20
min_cost_mean_bps = 15
min_recent_cost_mean_bps = 10
max_touch_stop_100_pct = 45
max_median_mae_abs_bps = 100
cost_bps = 8
extra_slippage_bps = 0,4,8,12,16
```

These thresholds are intentionally conservative because Stage39C still showed small residuals relative to path risk.

## Execution

```bash
python3 scripts/stage39d_condition_robustness_forward_split_audit.py \
  --stage39c-summary reports/stage39c/stage39c_condition_diagnostic_summary.json \
  --stage39c-events reports/stage39c/stage39c_condition_event_rows.csv \
  --stage39c-buckets reports/stage39c/stage39c_condition_bucket_summary.csv \
  --stage39c-cross reports/stage39c/stage39c_condition_cross_matrix.csv \
  --cost-bps 8.0 \
  --extra-slippage-bps 0,4,8,12,16 \
  --min-events 30 \
  --output-dir reports/stage39d
```

## Outputs

```text
reports/stage39d/stage39d_condition_robustness_summary.csv
reports/stage39d/stage39d_forward_split_audit.csv
reports/stage39d/stage39d_condition_audited_event_rows.csv
reports/stage39d/stage39d_condition_robustness_summary.json
reports/stage39d/stage39d_condition_robustness_forward_split.md
```

## Next allowed step

Only if one or more rows are:

```text
STRICT_CONDITION_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION
FORWARD_ROBUSTNESS_WATCH_ONLY_NO_PROMOTION
```

the next allowed step is:

```text
Stage39E_FROZEN_RULE_OUT_OF_SAMPLE_AUDIT
```

If no row survives, archive Stage39A-D and do not continue filtering.

## Schema hotfix note: Stage39C event timestamp

Stage39C condition event rows may use `entry_ts` / `exit_ts` instead of the older `entry_utc` / `exit_utc` naming convention. Stage39D now accepts `entry_ts` as a preferred event timestamp column. This keeps the audit DB-first/schema-tolerant and avoids failing when upstream stage outputs use the newer timestamp column names.

This hotfix does not change decision logic, thresholds, promotion status, or the research-only scope.
