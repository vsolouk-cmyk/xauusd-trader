# Stage70B Champion Hard Audit

Purpose: hard-audit exactly one locked champion thesis from Stage70:

`K06_RESILIENT_GOLD_VS_DXY / H120`

This package intentionally does not scan for new candidates, tune thresholds, or create broker/order/EA outputs.

## Champion rule

Long-only thesis:

```text
gold_sma20_over_50 > 0
dxy_ret_20d > 0
real_yield_change_20d < 0
horizon = 120 trading days
cost = 50 bps
```

Interpretation: gold trend remains positive despite dollar strength because real yields are easing.

## Required input

```text
data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv
```

Required columns:

```text
feature_date_utc or date_utc
gold_close
gold_sma20_over_50
dxy_ret_20d
real_yield_change_20d
```

Optional benchmark columns:

```text
dxy_sma20_over_50
gold_sma50_over_200
```

## Outputs

```text
reports/stage70b_champion_hard_audit/stage70b_champion_hard_audit_summary.json
reports/stage70b_champion_hard_audit/stage70b_champion_hard_audit_report.md
reports/stage70b_champion_hard_audit/stage70b_champion_entry_returns.csv
reports/stage70b_champion_hard_audit/stage70b_champion_period_metrics.csv
reports/stage70b_champion_hard_audit/stage70b_champion_yearly_metrics.csv
reports/stage70b_champion_hard_audit/stage70b_champion_leave_one_period_out.csv
reports/stage70b_champion_hard_audit/stage70b_champion_stress_cost.csv
reports/stage70b_champion_hard_audit/stage70b_champion_outlier_sensitivity.csv
reports/stage70b_champion_hard_audit/stage70b_champion_benchmark_overlap.csv
reports/stage70b_champion_hard_audit/stage70b_backlog_register.csv
```

## Valid dispositions

Exactly one of:

```text
PROMOTE_TO_NO_ORDER_SHADOW_CANDIDATE
KILL_CHAMPION_CLOSE_STAGE70
AMBIGUOUS_ONE_DIAGNOSTIC_ONLY
```

If ambiguous, only one diagnostic package is allowed before a final disposition.

## Backlog policy

Backlog is constructive but non-interruptive. It records options without cutting off the current champion path.

Allowed statuses:

```text
BACKLOG_REFERENCE
DATA_BLOCKED_WITH_REQUIREMENTS
```

A backlog item cannot interrupt K06 until K06 is promoted, killed, or parked with reason.

## Hard blocks

```text
NO_AUTOMATED_ORDER
NO_PAPER_ORDER
NO_BROKER_CONNECTION
NO_EA_PROMOTION
NO_PAPER_LIVE
NO_LIVE
NO_ORDER_AUTHORIZATION_FROM_STAGE70B
NO_THRESHOLD_TUNING_FROM_STAGE70B
NO_PROMOTION_FROM_HARD_AUDIT_WITHOUT_FORWARD_SHADOW
```
