# Stage45B3B Scheduled Macro Calendar Acquisition

Stage45B3B is a data-acquisition/repair step for the news blackout calendar. It is introduced after Stage45B3A reduced the mixed calendar too aggressively and left only a few scheduled events with no M15 bar overlap.

This stage builds a scheduled US macro calendar from official/manual sources and keeps numeric shock/backfill labels separate from no-trade blackout windows.

## Scope

Allowed:

- Acquire or build scheduled macro events.
- Write `data/external/news_calendar_scheduled_macro_official.csv`.
- Optionally replace canonical `data/external/news_calendar.csv` when `--apply-canonical` is used.
- Write scheduled blackout windows.
- Report overlap against local M15 bars.

Not allowed:

- Trading signals.
- Candidate shortlist.
- Candidate rescue from Stage41/42/43.
- EA, paper-live, live trading.

## Local command

```bash
python3 scripts/stage45b3b_scheduled_macro_calendar_acquisition.py \
  --years 2022 2023 2024 2025 2026 \
  --apply-canonical \
  --print-summary
```

Then rerun:

```bash
python3 scripts/stage45b3a_news_calendar_semantic_reduction.py --apply-canonical --print-summary
python3 scripts/stage45b2a_external_context_alignment_repair.py --print-summary
python3 scripts/stage45b3_external_context_baseline_design_precheck.py --print-summary
```

## Outputs

```text
data/external/news_calendar_scheduled_macro_official.csv
data/external/news_blackout_windows_scheduled_macro.csv
data/external/news_calendar.csv                         # only with --apply-canonical
data/external/news_blackout_windows.csv                # only with --apply-canonical
reports/stage45b3b/stage45b3b_scheduled_macro_calendar_acquisition_summary.json
reports/stage45b3b/stage45b3b_scheduled_macro_calendar_acquisition.md
reports/stage45b3b/stage45b3b_scheduled_macro_events.csv
reports/stage45b3b/stage45b3b_scheduled_macro_blackout_windows.csv
reports/stage45b3b/stage45b3b_source_fetch_profile.csv
```

## Design note

BLS CPI and Employment Situation releases are treated as scheduled macro events at the published release time. FOMC events are best-effort from the Federal Reserve calendar using a default 14:00 New York statement time when no explicit time is provided. If FOMC parsing is noisy or unavailable, CPI and Employment Situation releases alone should still provide a compact scheduled-macro blackout calendar.

The resulting calendar should be small enough for strategy-design interpretation. Numeric shock/backfill rows remain useful as context features, but not as no-trade blackout windows.
