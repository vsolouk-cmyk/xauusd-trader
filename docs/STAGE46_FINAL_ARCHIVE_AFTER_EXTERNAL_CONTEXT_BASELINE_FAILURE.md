# STAGE46_FINAL_ARCHIVE_AFTER_EXTERNAL_CONTEXT_BASELINE_FAILURE

This patch adds the final archive step for Stage46 after the fresh external-context baseline scan failed to produce any strict or soft survivor.

## Purpose

Stage46 final archive preserves the failure evidence from Stage46A and Stage46C, closes the external-context branch, and prevents accidental continuation through post-hoc filters or archived-candidate rescue.

It does not:

- create trading signals,
- scan candidates,
- rescue Stage41/42/43 rows,
- authorize promotion,
- authorize EA/paper-live/live,
- introduce ML.

## Inputs

Default inputs:

```text
reports/stage46c/stage46c_external_context_failure_analysis_or_archive_summary.json
reports/stage46a/stage46a_external_context_baseline_scan_implementation_summary.json
reports/stage46/stage46_external_context_baseline_scan_design_summary.json
reports/stage45b3/stage45b3_external_context_baseline_design_precheck_summary.json
```

## Outputs

```text
reports/stage46_final_archive/stage46_final_archive_after_external_context_baseline_failure_summary.json
reports/stage46_final_archive/stage46_final_archive_after_external_context_baseline_failure.md
reports/stage46_final_archive/stage46_final_archive_register.csv
```

## Run

```bash
python3 scripts/stage46_final_archive_after_external_context_baseline_failure.py --print-summary
```

## Expected decision

If Stage46C is present and archive-recommended:

```text
status = STAGE46_FINAL_ARCHIVE_COMPLETE_NO_PROMOTION
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
next_allowed_step = NEW_SESSION_OR_NEW_STRUCTURAL_THESIS_DECISION
```

## Interpretation

The Stage46 branch is considered closed unless a genuinely new predefined structural thesis is selected. A new thesis must not be a post-hoc filter over Stage41/42/43/46 failures.
