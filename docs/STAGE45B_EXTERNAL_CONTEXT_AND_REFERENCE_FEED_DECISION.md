# Stage45B_EXTERNAL_CONTEXT_AND_REFERENCE_FEED_DECISION

## Purpose

Stage45B is a direction-selection and inventory audit after Stage45C. It does not create signals, does not shortlist candidates, and cannot promote any prior Stage41/42/43 row.

Stage45C found that broker spread alone is not the decisive blocker, while the recent candle-only thesis scans still produced no robust shortlist. Stage45B therefore determines whether external macro/context data and a reference feed exist in the repository with usable schemas.

## Inputs

Default Stage45C input:

```text
reports/stage45c/stage45c_feed_transaction_cost_realism_audit_summary.json
```

Default external context inventory paths are searched under:

```text
data/external/
data/reference/
data/calendar/
```

## Required external context categories

Minimum practical context before a new external-context baseline scan:

```text
DXY or US dollar index proxy
US 10-year yield
CME GC/MGC futures reference feed or equivalent reference market feed
high-impact macro news calendar with UTC timestamps
```

Optional but useful additions:

```text
US 2-year yield
US real yield / TIPS proxy
FOMC calendar
US CPI calendar
NFP / employment calendar
```

## Outputs

```text
reports/stage45b/stage45b_external_context_reference_feed_decision_summary.json
reports/stage45b/stage45b_external_context_reference_feed_decision.md
reports/stage45b/stage45b_external_context_inventory.csv
reports/stage45b/stage45b_required_dataset_spec.csv
```

## Decision logic

```text
If core macro + reference feed + news context are missing:
  next = Stage45B1_EXTERNAL_CONTEXT_DATA_ACQUISITION_PLAN

If macro context exists but reference feed is missing:
  next = Stage45B2_REFERENCE_FEED_ALIGNMENT_AUDIT

If macro context + reference feed + news context exist with acceptable schemas:
  next = Stage46_EXTERNAL_CONTEXT_BASELINE_SCAN_DESIGN
```

## Gates

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

## Not allowed

```text
candidate_rescue_from_stage41_42_43
post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets
EA_paper_live_live_from_archived_rows
ML_before_robust_cost_aware_baseline
new_candle_only_blind_megascan_before_external_context_decision_is_satisfied
```

## Anti-overfit note

This stage only chooses a data/context direction. It must not be used to retrospectively rescue any archived candidate.
