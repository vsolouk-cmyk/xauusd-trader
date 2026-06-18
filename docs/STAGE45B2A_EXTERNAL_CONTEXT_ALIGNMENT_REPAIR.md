# Stage45B2A External Context Alignment Repair

## Purpose

`Stage45B2A_EXTERNAL_CONTEXT_ALIGNMENT_REPAIR` repairs and diagnoses the remaining Stage45B2 alignment blocker:

```text
news_blackout_windows_do_not_cover_any_bars
```

This is not a signal scan. It does not create candidate rows, does not rescue Stage41/42/43 candidates, and cannot promote anything.

## Why this stage exists

Stage45B2 confirmed that P0 external context files are schema-valid, including:

```text
dxy
us10y_yield
cme_gc_reference
news_calendar
```

However, Stage45B2 reported zero M15 bars inside news blackout windows, despite a timestamped 515-row news calendar and an M15 bar series spanning the same date range. That pattern is more consistent with an alignment/counting implementation issue than with a true absence of overlap.

Stage45B2A recalculates blackout overlap using robust UTC integer timestamp intervals:

```text
window_start = event_timestamp - pre_hours
window_end   = event_timestamp + post_hours
bar is blacked out if window_start <= bar_timestamp <= window_end
```

The default window remains:

```text
pre_hours = 2
post_hours = 2
```

## Inputs

```text
data/local/xauusd_local_store.sqlite
data/external/news_calendar.csv
reports/stage45b2/stage45b2_external_context_alignment_audit_summary.json
```

## Outputs

```text
reports/stage45b2a/stage45b2a_external_context_alignment_repair_summary.json
reports/stage45b2a/stage45b2a_external_context_alignment_repair.md
reports/stage45b2a/stage45b2a_blackout_repair_profile.csv
reports/stage45b2a/stage45b2a_blackout_bar_sample.csv
reports/stage45b2a/stage45b2a_news_blackout_windows_all_events.csv
reports/stage45b2a/stage45b2a_news_blackout_windows_macro_semantic_only.csv
reports/stage45b2a/stage45b2a_news_blackout_windows_macro_usd_or_unknown.csv
data/external/news_blackout_windows.csv
```

## Decision logic

If repaired blackout windows cover at least one bar, the next allowed stage becomes:

```text
Stage45B3_EXTERNAL_CONTEXT_BASELINE_DESIGN_PRECHECK
```

If they still cover zero bars, the next allowed stage remains:

```text
Stage45B2A_CONTINUE_EXTERNAL_CONTEXT_ALIGNMENT_REPAIR
```

In all cases:

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

## Run

```bash
python3 scripts/stage45b2a_external_context_alignment_repair.py --print-summary
```

Optional window parameters:

```bash
python3 scripts/stage45b2a_external_context_alignment_repair.py \
  --news-pre-hours 2 \
  --news-post-hours 2 \
  --print-summary
```

## Not allowed

- Candidate rescue from Stage41/42/43.
- Post-hoc filtering of bad hours/months/years/quarters/context buckets.
- EA, paper-live, or live trading from archived rows.
- ML before a robust cost-aware baseline exists.
- A new blind megascan before external-context alignment repair is clean.

## Anti-overfit note

This repair is infrastructure-only. If it succeeds, the next valid step is a predefined external-context baseline design precheck, not a pass over archived candidates.
