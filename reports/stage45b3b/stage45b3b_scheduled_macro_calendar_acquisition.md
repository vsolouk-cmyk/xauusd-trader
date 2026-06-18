# Stage45B3B_SCHEDULED_MACRO_CALENDAR_ACQUISITION

## Decision

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
status = SCHEDULED_MACRO_CALENDAR_BLOCKED_NO_PROMOTION
recommended_next_stage = Stage45B3B_CONTINUE_SCHEDULED_MACRO_CALENDAR_ACQUISITION
```

This stage acquires or builds a scheduled US macro calendar. It does not create trading signals, shortlist candidates, or promote archived rows.

## Acquisition summary

- BLS events: `0`
- FOMC events: `47`
- Manual events: `0`
- Final scheduled event count: `47`

## Blackout overlap

- bars_in_blackout: `0`
- bars_in_blackout_pct: `0.0000%`
- events_with_at_least_one_bar: `0`

## Blockers and warnings

```json
{
  "blockers": [
    "scheduled_macro_blackout_windows_do_not_cover_any_bars"
  ],
  "warnings": [
    "one_or_more_bls_year_pages_failed"
  ]
}
```

## Not allowed

- `candidate_rescue_from_stage41_42_43`
- `post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets`
- `EA_paper_live_live_from_archived_rows`
- `ML_before_robust_cost_aware_baseline`
- `new_blind_megascan_before_scheduled_macro_calendar_is_ready`
