# Stage39C Microstructure / Session-Condition Diagnostic

## Scope

```text
stage = Stage39C_MICROSTRUCTURE_SESSION_CONDITION_DIAGNOSTIC
scope = RESEARCH_STAGE_ONLY_NO_PROMOTION
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

Stage39C is allowed only because Stage39B left two rows in:

```text
PATH_DIAGNOSTIC_WATCH_ONLY_NO_PROMOTION
```

It is not a promotion gate. It is a diagnostic to check whether the remaining long mean-reversion rows have any stable session/microstructure condition worth a separate robustness audit.

## Inputs

Default inputs:

```text
data/local/xauusd_local_store.sqlite
reports/stage39b/stage39b_event_path_diagnostic_summary.json
reports/stage39b/stage39b_event_path_event_rows.csv
```

Candidate set:

```text
BB_LOWER_REV_LONG_W120_K2.5
RANGE_BOTTOM_REV_LONG_W48_Q0.05
```

These are the two Stage39B path-diagnostic watch rows. The weak residual/path-risk rows are intentionally excluded.

## Diagnostics

Stage39C evaluates condition buckets around:

```text
UTC session
weekday
UTC hour
spread regime
ATR24 volatility bucket
prior 24H return regime
prior 72H return regime
trigger severity bucket
session x ATR24
session x spread
session x prior-return
```

The diagnostic keeps benchmark discipline:

```text
NO_GO remains fixed
no EA
no paper-live
no live
no Telegram trade alert
no candidate promotion
```

## Output files

```text
reports/stage39c/stage39c_condition_candidate_summary.csv
reports/stage39c/stage39c_condition_bucket_summary.csv
reports/stage39c/stage39c_condition_event_rows.csv
reports/stage39c/stage39c_condition_cross_matrix.csv
reports/stage39c/stage39c_condition_diagnostic_summary.json
reports/stage39c/stage39c_microstructure_session_condition.md
```

## Interpretation

`CONDITION_RESEARCH_WATCH_ONLY_NO_PROMOTION` means the full candidate remains research-observable.

`CONDITION_BUCKET_WATCH_ONLY_NO_PROMOTION` means one condition bucket may deserve Stage39D robustness checking.

`RESIDUAL_TOO_SMALL_VS_PATH_RISK_NO_PROMOTION` means the Stage39B residual is too small relative to adverse excursion.

`ADVERSE_EXCURSION_TOO_HIGH_NO_PROMOTION` means the path remains too risky even if the mean is positive.

`INSUFFICIENT_BUCKET_EVENTS_NO_PROMOTION` means the bucket is too thin.

## Next allowed step

Only if one or more buckets are classified as:

```text
CONDITION_BUCKET_WATCH_ONLY_NO_PROMOTION
```

then the next step is:

```text
Stage39D_CONDITION_ROBUSTNESS_AND_FORWARD_SPLIT_AUDIT
```

Otherwise Stage39A/B/C should be archived and no more filters should be added.
