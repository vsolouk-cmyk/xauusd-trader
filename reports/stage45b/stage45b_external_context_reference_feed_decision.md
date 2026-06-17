# Stage45B_EXTERNAL_CONTEXT_AND_REFERENCE_FEED_DECISION

## Decision

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
recommended_next_stage = Stage45B1_EXTERNAL_CONTEXT_DATA_ACQUISITION_PLAN
```

Stage45B is an external-context and reference-feed decision step only. It does not create trading signals, does not shortlist candidates, and cannot promote archived rows.

## Stage45C reference

```json
{
  "exists": true,
  "error": null,
  "decision_status": "COST_REALISM_AUDITED_NO_PROMOTION",
  "recommended_next_stage": "Stage45B_EXTERNAL_CONTEXT_AND_REFERENCE_FEED_DECISION",
  "next_allowed_step": "Stage45B_EXTERNAL_CONTEXT_AND_REFERENCE_FEED_DECISION",
  "promotion": "NO_GO",
  "EA": "NO_GO",
  "paper_live": "NO_GO",
  "live": "NO_GO"
}
```

## External context inventory

| key | required_for | found | schema_ok | selected_path | row_count_scanned | timestamp_column | start | end |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| dxy | macro_context | False | False |  | 0 |  |  |  |
| us10y_yield | macro_context | False | False |  | 0 |  |  |  |
| us02y_yield | macro_context_optional | False | False |  | 0 |  |  |  |
| real_yield | macro_context_optional | False | False |  | 0 |  |  |  |
| cme_gc_reference | reference_feed | False | False |  | 0 |  |  |  |
| news_calendar | news_blackout_context | False | False |  | 0 |  |  |  |
| fomc_calendar | news_blackout_optional | False | False |  | 0 |  |  |  |
| cpi_calendar | news_blackout_optional | False | False |  | 0 |  |  |  |
| nfp_calendar | news_blackout_optional | False | False |  | 0 |  |  |  |

## Required dataset specification

| key | required_for | acceptable_paths | required_columns_any | notes |
| :-- | :-- | :-- | :-- | :-- |
| dxy | macro_context | data/external/dxy.csv \| data/external/DXY.csv \| data/external/us_dollar_index.csv \| data/external/dxy_daily.csv | timestamp+close OR date+close OR time+close | At least daily DXY proxy aligned to UTC; preferably open/high/low/close if available. |
| us10y_yield | macro_context | data/external/us10y_yield.csv \| data/external/us10y.csv \| data/external/US10Y.csv \| data/external/treasury_10y.csv | timestamp+close OR date+close OR date+yield OR timestamp+yield | Gold is materially sensitive to nominal and real yields; daily is acceptable for first context gate. |
| us02y_yield | macro_context_optional | data/external/us02y_yield.csv \| data/external/us2y.csv \| data/external/US02Y.csv \| data/external/treasury_2y.csv | timestamp+close OR date+close OR date+yield OR timestamp+yield | Useful for rate-expectation regime and curve context; optional for first external-context pass. |
| real_yield | macro_context_optional | data/external/real_yield.csv \| data/external/us10y_real_yield.csv \| data/external/tips_10y.csv | timestamp+close OR date+close OR date+yield OR timestamp+yield | Strong gold context variable, but can be added after DXY + nominal yields. |
| cme_gc_reference | reference_feed | data/external/cme_gc.csv \| data/external/gc_futures.csv \| data/external/GC.csv \| data/external/mgc_futures.csv \| ... | timestamp+open+high+low+close OR date+open+high+low+close | Needed to decide whether MT5 CFD feed behavior is broker-specific or market-wide. |
| news_calendar | news_blackout_context | data/external/news_calendar.csv \| data/external/high_impact_news.csv \| data/external/macro_calendar.csv \| data/cal... | timestamp+event OR datetime+event OR date+event OR timestamp+name | Must support FOMC/CPI/NFP/US jobs/inflation/rate events and UTC timestamps for blackout tagging. |
| fomc_calendar | news_blackout_optional | data/external/fomc_calendar.csv \| data/calendar/fomc_calendar.csv | timestamp+event OR datetime+event OR date+event | Optional if covered by a unified high-impact news calendar. |
| cpi_calendar | news_blackout_optional | data/external/cpi_calendar.csv \| data/calendar/cpi_calendar.csv | timestamp+event OR datetime+event OR date+event | Optional if covered by a unified high-impact news calendar. |
| nfp_calendar | news_blackout_optional | data/external/nfp_calendar.csv \| data/calendar/nfp_calendar.csv | timestamp+event OR datetime+event OR date+event | Optional if covered by a unified high-impact news calendar. |

## Decision rationale

- Stage45C found that spread/cost realism alone is not decisive enough to restart candle-only scans.
- No Stage41/42/43 candidate is promoted; this branch is direction selection only.
- Core external context is absent or schema-invalid: DXY, US 10Y, reference futures, and/or news calendar must be added before external-context baselines.

## Not allowed

- `candidate_rescue_from_stage41_42_43`
- `post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets`
- `EA_paper_live_live_from_archived_rows`
- `ML_before_robust_cost_aware_baseline`
- `new_candle_only_blind_megascan_before_external_context_decision_is_satisfied`

## Anti-overfit note

Do not use this step to rescue Stage41/42/43 rows. Stage45B can only determine whether the next valid branch is data acquisition, reference-feed alignment, or a pre-defined external-context baseline scan.
