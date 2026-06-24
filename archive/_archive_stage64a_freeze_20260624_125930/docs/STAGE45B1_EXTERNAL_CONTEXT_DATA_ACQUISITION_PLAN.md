# STAGE45B1_EXTERNAL_CONTEXT_DATA_ACQUISITION_PLAN

## Purpose

Stage45B1 converts the Stage45B decision into a concrete external-context data acquisition checklist. It validates whether the required CSV files are present, writes schema templates, and produces a report that decides whether the project can move to external-context alignment.

Stage45B1 is not a trading signal stage. It cannot promote Stage41/42/43 rows, cannot authorize EA/paper/live, and cannot justify post-hoc filtering.

## Why this stage exists

Stage45C showed that broker spread/transaction-cost realism alone does not explain all recent failures. Stage45B then showed that the repository currently lacks the external context needed to build non-candle-only baselines:

- DXY / US Dollar Index proxy
- US 10Y yield
- CME GC/MGC futures reference feed
- high-impact macro news calendar

Before any new external-context baseline scan, these files must be acquired and schema-validated.

## Script

```text
scripts/stage45b1_external_context_data_acquisition_plan.py
```

## Default outputs

```text
reports/stage45b1/stage45b1_external_context_data_acquisition_plan_summary.json
reports/stage45b1/stage45b1_external_context_data_acquisition_plan.md
reports/stage45b1/stage45b1_required_dataset_checklist.csv
reports/stage45b1/stage45b1_templates_written.csv
```

The script also writes schema templates under:

```text
data/external/templates/
```

## Minimal P0 data target

The first external-context pass requires these P0 datasets:

```text
data/external/dxy.csv
data/external/us10y_yield.csv
data/external/cme_gc.csv
or data/reference/cme_gc.csv
data/external/news_calendar.csv
```

Accepted alternatives are listed in the generated checklist and summary JSON.

## Required schema examples

DXY:

```text
timestamp,open,high,low,close,volume,source
```

US 10Y yield:

```text
timestamp,yield,close,source
```

CME GC/MGC reference:

```text
timestamp,open,high,low,close,volume,contract,source
```

News calendar:

```text
timestamp,event,currency,impact,category,actual,forecast,previous,source
```

## Decision rules

If DXY, US10Y, CME/reference feed, and news calendar are all present and schema-valid:

```text
next_allowed_step = Stage45B2_EXTERNAL_CONTEXT_ALIGNMENT_AUDIT
```

If any P0 dataset is missing or schema-invalid:

```text
next_allowed_step = Stage45B1_CONTINUE_EXTERNAL_CONTEXT_DATA_ACQUISITION
```

## Hard NO-GO policy

Stage45B1 always preserves:

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
new_candle_only_blind_megascan_before_external_context_data_is_available_and_aligned
```

## Operational note

This script does not download data. It deliberately creates a reproducible checklist and templates so that external datasets can be added explicitly, committed intentionally, and audited before any baseline scan uses them.
