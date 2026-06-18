# Stage45B1B_NEWS_CALENDAR_AND_CME_REFERENCE_GAP_CLOSURE

## Decision

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
recommended_next_stage = Stage45B1B_CONTINUE_NEWS_CALENDAR_AND_CME_REFERENCE_ACQUISITION
```

Stage45B1B is a gap-closure diagnostic for the remaining P0 external-context inputs. It does not create signals, shortlist candidates, or promote archived rows.

## P0 readiness

| key | schema_ok | row_count | start | end | path |
| :-- | :-- | --: | :-- | :-- | :-- |
| dxy | True | 1025 | 2022-05-02T00:00:00+00:00 | 2026-06-05T00:00:00+00:00 | data/external/dxy.csv |
| us10y_yield | True | 1028 | 2022-05-02T00:00:00+00:00 | 2026-06-11T00:00:00+00:00 | data/external/us10y_yield.csv |
| cme_gc_reference | False | 0 |  |  | data/reference/cme_gc.csv |
| news_calendar | False | 0 |  |  | data/external/news_calendar.csv |

## Optional readiness

| key | schema_ok | row_count | path |
| :-- | :-- | --: | :-- |
| real_yield_optional | True | 1028 | data/external/real_yield.csv |

## Candidate scan summary

- CME schema-ready candidate count: `0`
- News blackout-ready candidate count: `2`
- Partial/schema-only news candidate count: `0`

## Acquisition tasks

| key | canonical_path | required_columns | next_action |
| :-- | :-- | :-- | :-- |
| cme_gc_reference | data/reference/cme_gc.csv | timestamp,open,high,low,close[,volume,contract,source] | recover prior GC/MGC file from archive/git or acquire a clean GC/MGC continuous futures reference feed |
| news_calendar | data/external/news_calendar.csv | timestamp,event,currency,impact,category,actual,forecast,previous,source | build/import CPI/FOMC/NFP/PCE/jobs/rate-event calendar; do not use generic GDELT gold news as blackout calendar |

## Rationale

- DXY and US10Y can be treated as macro-core ready only if canonical files validate.
- News must be a high-impact macro blackout calendar, not generic gold news or a one-row example file.
- CME GC/MGC reference remains required before external-context alignment can begin.
- This step does not authorize candidate rescue, candle-only scans, EA, paper-live, or live trading.

## Not allowed

- `candidate_rescue_from_stage41_42_43`
- `post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets`
- `EA_paper_live_live_from_archived_rows`
- `ML_before_robust_cost_aware_baseline`
- `new_candle_only_blind_megascan_before_external_context_data_is_available_and_aligned`

## Anti-overfit note

Do not use this step to rescue Stage41/42/43 rows. After P0 validates, the next valid step is a predefined alignment audit, not a candidate rescue pass.
