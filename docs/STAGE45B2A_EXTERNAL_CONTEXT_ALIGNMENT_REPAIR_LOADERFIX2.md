# STAGE45B2A_EXTERNAL_CONTEXT_ALIGNMENT_REPAIR_LOADERFIX2

This patch replaces the Stage45B2A repair script with a robust UTC interval-overlap implementation.

## Why this patch exists

The previous Stage45B2A repair still produced zero bars in blackout despite a timestamped news calendar and overlapping M15 bars. Loaderfix2 avoids fragile datetime comparison behavior by:

- parsing all timestamps with `pd.to_datetime(..., utc=True)`;
- converting sorted bar timestamps and window timestamps to int64 nanoseconds;
- using `numpy.searchsorted` to find bars whose `[bar_start, bar_end)` interval overlaps each `[window_start, window_end)` interval;
- writing debug information for bar min/max and window min/max.

## Outputs

```text
data/external/news_blackout_windows.csv
reports/stage45b2a/stage45b2a_external_context_alignment_repair_summary.json
reports/stage45b2a/stage45b2a_external_context_alignment_repair.md
reports/stage45b2a/stage45b2a_blackout_repair_profile.csv
reports/stage45b2a/stage45b2a_blackout_bar_sample.csv
reports/stage45b2a/stage45b2a_news_blackout_windows_all_events.csv
reports/stage45b2a/stage45b2a_news_blackout_windows_macro_semantic_only.csv
reports/stage45b2a/stage45b2a_news_blackout_windows_macro_usd_or_unknown.csv
```

## Gates

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

This stage does not create signals, rescue archived candidates, or authorize trading.
