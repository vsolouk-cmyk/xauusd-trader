# Stage45B3A_NEWS_CALENDAR_SEMANTIC_REDUCTION

## Decision

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
status = NEWS_CALENDAR_SEMANTIC_REDUCTION_BLOCKED_NO_PROMOTION
recommended_next_stage = Stage45B3A_CONTINUE_NEWS_CALENDAR_SEMANTIC_REDUCTION
```

Stage45B3A reduces the news calendar semantics only. It does not create trading signals, shortlist candidates, or promote archived rows.

## Semantic reduction

| metric | value |
| :-- | --: |
| input_event_count | 47 |
| scheduled_macro_event_count | 47 |
| excluded_context_event_count | 0 |
| scheduled_macro_blackout_bars | 0 |
| scheduled_macro_blackout_pct | 0.0 |

## Event windows

```json
{
  "fomc_pre_hours": 4.0,
  "fomc_post_hours": 8.0,
  "inflation_pre_hours": 2.0,
  "inflation_post_hours": 4.0,
  "jobs_pre_hours": 2.0,
  "jobs_post_hours": 4.0,
  "default_pre_hours": 1.0,
  "default_post_hours": 2.0
}
```

## Outputs

- `summary_json`: `reports/stage45b3a/stage45b3a_news_calendar_semantic_reduction_summary.json`
- `markdown`: `reports/stage45b3a/stage45b3a_news_calendar_semantic_reduction.md`
- `semantic_reduction_profile_csv`: `reports/stage45b3a/stage45b3a_semantic_reduction_profile.csv`
- `category_source_profile_csv`: `reports/stage45b3a/stage45b3a_category_source_profile.csv`
- `selected_scheduled_macro_events_csv`: `reports/stage45b3a/stage45b3a_selected_scheduled_macro_events.csv`
- `excluded_context_events_csv`: `reports/stage45b3a/stage45b3a_excluded_context_events.csv`
- `scheduled_macro_blackout_windows_csv`: `reports/stage45b3a/stage45b3a_scheduled_macro_blackout_windows.csv`
- `blackout_bar_sample_csv`: `reports/stage45b3a/stage45b3a_blackout_bar_sample.csv`

## Blockers and warnings

```json
{
  "blockers": [
    "scheduled_macro_blackout_windows_do_not_cover_any_bars"
  ],
  "warnings": []
}
```

## Not allowed

- `candidate_rescue_from_stage41_42_43`
- `post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets`
- `EA_paper_live_live_from_archived_rows`
- `ML_before_robust_cost_aware_baseline`
- `new_blind_megascan_before_news_semantic_reduction_precheck_is_clean`

## Anti-overfit note

Do not use this reduction to rescue Stage41/42/43 rows. If the precheck passes after reduction, the next action must still be a predefined external-context baseline design.
