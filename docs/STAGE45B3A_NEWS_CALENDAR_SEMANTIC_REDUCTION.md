# Stage45B3A News Calendar Semantic Reduction

## Purpose

Stage45B3A repairs the Stage45B3 design blocker caused by an overly broad news blackout calendar. The observed blocker was `news_blackout_coverage_too_broad`: the selected blackout variant covered more than half of all M15 bars.

The repair separates two concepts that must not be mixed:

- scheduled macro no-trade events, such as FOMC, CPI, PCE, NFP, jobs, rates, inflation, retail sales, ISM/PMI, and GDP events;
- numeric shock/backfill/context labels, such as FRED-derived shock rows, oil-supply shock rows, yield-shock rows, USD-shock rows, and generic GDELT/gold-demand news.

Only the first group is eligible for canonical news blackout windows. The second group is preserved as context, but is not used as a no-trade blackout source.

## Inputs

```text
reports/stage45b3/stage45b3_external_context_baseline_design_precheck_summary.json
data/external/news_calendar.csv
data/local/xauusd_local_store.sqlite
```

## Outputs

```text
reports/stage45b3a/stage45b3a_news_calendar_semantic_reduction_summary.json
reports/stage45b3a/stage45b3a_news_calendar_semantic_reduction.md
reports/stage45b3a/stage45b3a_semantic_reduction_profile.csv
reports/stage45b3a/stage45b3a_category_source_profile.csv
reports/stage45b3a/stage45b3a_selected_scheduled_macro_events.csv
reports/stage45b3a/stage45b3a_excluded_context_events.csv
reports/stage45b3a/stage45b3a_scheduled_macro_blackout_windows.csv
reports/stage45b3a/stage45b3a_blackout_bar_sample.csv
```

With `--apply-canonical`, the stage also writes:

```text
data/external/news_calendar_mixed_pre_stage45b3a.csv
data/external/news_calendar.csv
data/external/news_calendar_scheduled_macro.csv
data/external/news_shock_context_events.csv
data/external/news_blackout_windows.csv
```

## Recommended command

```bash
python3 scripts/stage45b3a_news_calendar_semantic_reduction.py --apply-canonical --print-summary
```

## Window policy

Default windows are event-type aware:

```text
FOMC/rate policy:       -4h / +8h
CPI/PCE/inflation:      -2h / +4h
NFP/jobs/employment:    -2h / +4h
Other scheduled macro:  -1h / +2h
```

These defaults intentionally avoid treating every numeric shock label as a no-trade window.

## Expected decision

A successful repair should produce:

```text
status = NEWS_CALENDAR_SEMANTIC_REDUCTION_READY_NO_PROMOTION
next_allowed_step = Stage45B3_RERUN_EXTERNAL_CONTEXT_BASELINE_DESIGN_PRECHECK
```

If the reduced calendar still covers too many bars, or covers zero bars, Stage45B3A remains blocked.

## Gates

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

## Not allowed

- `candidate_rescue_from_stage41_42_43`
- `post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets`
- `EA_paper_live_live_from_archived_rows`
- `ML_before_robust_cost_aware_baseline`
- `new_blind_megascan_before_news_semantic_reduction_precheck_is_clean`

## Anti-overfit note

This stage must not be used to rescue Stage41/42/43 rows. If the reduced calendar passes design precheck, the next valid step is still a predefined external-context baseline design, not a post-hoc rescue pass.
