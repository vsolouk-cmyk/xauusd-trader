# Stage45B1B News Calendar and CME Reference Gap Closure

## Purpose

Stage45B1B is a local diagnostic/helper stage for the two remaining P0 external-context gaps after Stage45B1A:

```text
cme_gc_reference
news_calendar
```

It does not create trading signals, does not shortlist candidates, and cannot promote any Stage41/42/43 row.

## Why this stage exists

Stage45B1A validated that:

```text
dxy = ready
us10y_yield = ready
real_yield = optional ready
cme_gc_reference = missing
news_calendar = missing/not macro-blackout ready
```

A new candle-only scan is still blocked. The next valid work is to close the CME reference and macro-news-calendar data gaps.

## What the script does

The script:

1. Validates canonical external files:

```text
data/external/dxy.csv
data/external/us10y_yield.csv
data/external/real_yield.csv
data/reference/cme_gc.csv
data/external/news_calendar.csv
```

2. Scans likely legacy candidate paths for news/calendar and CME/GC files.
3. Classifies whether a news file is a true high-impact US macro blackout calendar.
4. Rejects generic gold/news/GDELT event lists as insufficient for blackout logic.
5. Produces acquisition tasks for missing P0 inputs.

## Outputs

```text
reports/stage45b1b/stage45b1b_news_calendar_cme_gap_closure_summary.json
reports/stage45b1b/stage45b1b_news_calendar_cme_gap_closure.md
reports/stage45b1b/stage45b1b_news_candidate_inventory.csv
reports/stage45b1b/stage45b1b_cme_candidate_inventory.csv
reports/stage45b1b/stage45b1b_acquisition_tasks.csv
```

## Run command

```bash
python3 scripts/stage45b1b_news_calendar_cme_gap_closure.py --print-summary
```

## Decision logic

If all P0s validate:

```text
recommended_next_stage = Stage45B2_EXTERNAL_CONTEXT_ALIGNMENT_AUDIT
```

If CME or news remains missing:

```text
recommended_next_stage = Stage45B1B_CONTINUE_NEWS_CALENDAR_AND_CME_REFERENCE_ACQUISITION
```

## P0 requirements

### CME GC/MGC reference

Canonical target:

```text
data/reference/cme_gc.csv
```

Required columns:

```text
timestamp,open,high,low,close
```

Optional but useful:

```text
volume,contract,source
```

Daily is the minimum acceptable granularity. Intraday is preferred. If a continuous futures series is used, its roll method must be documented before any alignment audit.

### High-impact macro news calendar

Canonical target:

```text
data/external/news_calendar.csv
```

Recommended columns:

```text
timestamp,event,currency,impact,category,actual,forecast,previous,source
```

The file should include timestamped high-impact US macro events such as:

```text
CPI
FOMC
NFP / Nonfarm Payrolls
PCE
Unemployment Rate
Average Hourly Earnings
Retail Sales
ISM / PMI
GDP
PPI
```

A generic GDELT gold-news file or a one-row example file is not sufficient for blackout logic.

## Not allowed

```text
candidate_rescue_from_stage41_42_43
post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets
EA_paper_live_live_from_archived_rows
ML_before_robust_cost_aware_baseline
new_candle_only_blind_megascan_before_external_context_data_is_available_and_aligned
```

## Next step after this stage

When both `data/reference/cme_gc.csv` and `data/external/news_calendar.csv` validate, move to:

```text
Stage45B2_EXTERNAL_CONTEXT_ALIGNMENT_AUDIT
```
