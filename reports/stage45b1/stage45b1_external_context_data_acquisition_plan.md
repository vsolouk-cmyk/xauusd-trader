# Stage45B1_EXTERNAL_CONTEXT_DATA_ACQUISITION_PLAN

## Decision

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
recommended_next_stage = Stage45B1_CONTINUE_EXTERNAL_CONTEXT_DATA_ACQUISITION
```

Stage45B1 is a data acquisition and schema-readiness plan only. It does not create trading signals, does not shortlist candidates, and cannot promote archived rows.

## Stage45B reference

```json
{
  "exists": true,
  "stage": "Stage45B_EXTERNAL_CONTEXT_AND_REFERENCE_FEED_DECISION",
  "next_allowed_step": "Stage45B1_EXTERNAL_CONTEXT_DATA_ACQUISITION_PLAN",
  "promotion": "NO_GO",
  "EA": "NO_GO",
  "paper_live": "NO_GO",
  "live": "NO_GO"
}
```

## P0 required datasets

| key | found | schema_ok | selected_path | required_for | accepted first path | required columns |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| dxy | False | False |  | macro_context_core | data/external/dxy.csv | timestamp+close OR date+close OR time+close |
| us10y_yield | False | False |  | macro_context_core | data/external/us10y_yield.csv | timestamp+yield OR date+yield OR timestamp+close OR date+close |
| cme_gc_reference | False | False |  | reference_feed_core | data/external/cme_gc.csv | timestamp+open+high+low+close OR date+open+high+low+close |
| news_calendar | False | False |  | news_blackout_core | data/external/news_calendar.csv | timestamp+event OR datetime+event OR date+event OR timestamp+name |

## Optional datasets

| key | priority | found | schema_ok | use |
| :-- | :-- | :-- | :-- | :-- |
| us02y_yield | P1_OPTIONAL | False | False | Rate-expectation and curve regime. |
| real_yield | P1_OPTIONAL | False | False | Real-yield pressure context for gold. |
| fomc_calendar | P2_OPTIONAL_IF_UNIFIED_NEWS_MISSING_DETAIL | False | False | FOMC blackout and rate-decision event regime. |
| cpi_calendar | P2_OPTIONAL_IF_UNIFIED_NEWS_MISSING_DETAIL | False | False | CPI/inflation blackout and event regime. |
| nfp_calendar | P2_OPTIONAL_IF_UNIFIED_NEWS_MISSING_DETAIL | False | False | NFP/jobs blackout and event regime. |

## Minimal acquisition target

```text
P0_REQUIRED:
1. data/external/dxy.csv
2. data/external/us10y_yield.csv
3. data/external/cme_gc.csv or data/reference/cme_gc.csv
4. data/external/news_calendar.csv
```

## Generated templates

| key | template_path | columns |
| :-- | :-- | :-- |
| dxy | /Users/vahid/Desktop/xauusd-trader/data/external/templates/dxy_template.csv | timestamp, open, high, low, close, volume, source |
| us10y_yield | /Users/vahid/Desktop/xauusd-trader/data/external/templates/us10y_yield_template.csv | timestamp, yield, close, source |
| cme_gc_reference | /Users/vahid/Desktop/xauusd-trader/data/external/templates/cme_gc_reference_template.csv | timestamp, open, high, low, close, volume, contract, source |
| news_calendar | /Users/vahid/Desktop/xauusd-trader/data/external/templates/news_calendar_template.csv | timestamp, event, currency, impact, category, actual, forecast, previous, source |
| us02y_yield | /Users/vahid/Desktop/xauusd-trader/data/external/templates/us02y_yield_template.csv | timestamp, yield, close, source |
| real_yield | /Users/vahid/Desktop/xauusd-trader/data/external/templates/real_yield_template.csv | timestamp, yield, close, source |
| fomc_calendar | /Users/vahid/Desktop/xauusd-trader/data/external/templates/fomc_calendar_template.csv | timestamp, event, impact, source |
| cpi_calendar | /Users/vahid/Desktop/xauusd-trader/data/external/templates/cpi_calendar_template.csv | timestamp, event, impact, source |
| nfp_calendar | /Users/vahid/Desktop/xauusd-trader/data/external/templates/nfp_calendar_template.csv | timestamp, event, impact, source |
| README | /Users/vahid/Desktop/xauusd-trader/data/external/templates/README.md |  |

## Decision rationale

- Stage45B found external context missing; Stage45B1 confirms the acquisition checklist is not yet satisfied.
- New candle-only blind scans remain blocked until external context is acquired and aligned.

## Not allowed

- `candidate_rescue_from_stage41_42_43`
- `post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets`
- `EA_paper_live_live_from_archived_rows`
- `ML_before_robust_cost_aware_baseline`
- `new_candle_only_blind_megascan_before_external_context_data_is_available_and_aligned`

## Anti-overfit note

Do not use this step to rescue Stage41/42/43 rows. Stage45B1 can only define, validate, and track external context data acquisition before any alignment audit or new external-context baseline scan.
