# Stage45B1A_EXTERNAL_CONTEXT_IMPORT_VALIDATE

## Decision

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
recommended_next_stage = Stage45B2_EXTERNAL_CONTEXT_ALIGNMENT_AUDIT
```

Stage45B1A only imports, normalizes, and validates external context files. It does not create signals, shortlist candidates, or promote archived rows.

## P0 readiness

| key | schema_ok | row_count | start | end | output_path |
| :-- | :-- | --: | :-- | :-- | :-- |
| dxy | True | 1025 | 2022-05-02T00:00:00+00:00 | 2026-06-05T00:00:00+00:00 | /Users/vahid/Desktop/xauusd-trader/data/external/dxy.csv |
| us10y_yield | True | 1028 | 2022-05-02T00:00:00+00:00 | 2026-06-11T00:00:00+00:00 | /Users/vahid/Desktop/xauusd-trader/data/external/us10y_yield.csv |
| cme_gc_reference | True | 1039 | 2022-05-02T00:00:00+00:00 | 2026-06-18T00:00:00+00:00 | /Users/vahid/Desktop/xauusd-trader/data/reference/cme_gc.csv |
| news_calendar | True | 515 | 2022-01-10T13:30:00+00:00 | 2026-12-09T19:00:00+00:00 | /Users/vahid/Desktop/xauusd-trader/data/external/news_calendar.csv |

## Optional readiness

| key | schema_ok | row_count | output_path |
| :-- | :-- | --: | :-- |
| us02y_yield | False | 0 | /Users/vahid/Desktop/xauusd-trader/data/external/us02y_yield.csv |
| real_yield | True | 1028 | /Users/vahid/Desktop/xauusd-trader/data/external/real_yield.csv |

## Imports performed

| key | import_attempted | written | path | reason |
| :-- | :-- | :-- | :-- | :-- |
| none | False |  |  | validation-only run |

## Decision rationale

- P0 external context files validate successfully; the next step is alignment auditing.
- This step only normalizes and validates external files; it does not authorize candle-only scans or candidate rescue.

## Next command pattern

```bash
python3 scripts/stage45b1a_external_context_import_validate.py \
  --dxy ~/Downloads/xauusd_external_context/dxy.csv \
  --us10y ~/Downloads/xauusd_external_context/us10y_yield.csv \
  --cme-gc ~/Downloads/xauusd_external_context/cme_gc.csv \
  --news-calendar ~/Downloads/xauusd_external_context/news_calendar.csv \
  --overwrite --print-summary
```

## Not allowed

- `candidate_rescue_from_stage41_42_43`
- `post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets`
- `EA_paper_live_live_from_archived_rows`
- `ML_before_robust_cost_aware_baseline`
- `new_candle_only_blind_megascan_before_external_context_data_is_available_and_aligned`

## Anti-overfit note

Do not use imported external data to rescue Stage41/42/43 rows post hoc. After P0 files validate, the only valid next step is a predefined alignment audit.
