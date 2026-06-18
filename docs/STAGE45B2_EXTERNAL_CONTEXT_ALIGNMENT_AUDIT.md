# STAGE45B2_EXTERNAL_CONTEXT_ALIGNMENT_AUDIT

## Purpose

Stage45B2 audits whether the recovered external-context files can be aligned safely to the XAUUSD broker-feed bars before any new external-context baseline is designed.

This is not a signal scan. It does not shortlist, rescue, or promote any Stage41/42/43 candidate.

## Inputs

Default paths:

```text
DB: data/local/xauusd_local_store.sqlite
Table: bars
Source: amarkets_mt5
Symbol: XAUUSD
Timeframe: M15
DXY: data/external/dxy.csv
US10Y: data/external/us10y_yield.csv
CME/GC reference: data/reference/cme_gc.csv
News calendar: data/external/news_calendar.csv
Optional real yield: data/external/real_yield.csv
```

## What the audit checks

1. Loads broker XAUUSD bars using DB-first schema introspection.
2. Aggregates intraday bars to daily OHLC for reference-feed comparison.
3. Validates DXY and US10Y daily coverage.
4. Uses a no-lookahead safe-lag check for daily context: default `bar_date - 1 day`.
5. Compares MT5 XAUUSD daily close/returns against `GC=F`/CME reference close.
6. Checks news-calendar blackout windows around event timestamps.
7. Emits blockers/warnings and selects the next allowed stage.

## Outputs

```text
reports/stage45b2/stage45b2_external_context_alignment_audit_summary.json
reports/stage45b2/stage45b2_external_context_alignment_audit.md
reports/stage45b2/stage45b2_context_coverage.csv
reports/stage45b2/stage45b2_cme_alignment_profile.csv
reports/stage45b2/stage45b2_news_blackout_profile.csv
```

## Run

```bash
python3 scripts/stage45b2_external_context_alignment_audit.py --print-summary
```

## Decision rules

If P0 schema is missing, coverage is poor, CME overlap is too low, or news blackout windows do not cover any bars, the recommended next stage is:

```text
Stage45B2A_EXTERNAL_CONTEXT_ALIGNMENT_REPAIR
```

If alignment is good enough for a first external-context baseline design, the recommended next stage is:

```text
Stage45B3_PREDEFINED_EXTERNAL_CONTEXT_BASELINE_DESIGN
```

## Permanent gates

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

## Not allowed

- Candidate rescue from Stage41/42/43.
- Post-hoc filtering of bad hours/months/years/quarters/context states.
- EA/paper-live/live from archived rows.
- ML before robust cost-aware baseline evidence.
- New candle-only blind megascan before external-context alignment is audited.

## Notes on current P0 sources

The `data/reference/cme_gc.csv` file built from `GC=F`/Yahoo/yfinance is acceptable only as a reference/alignment feed. It is not execution-grade or settlement-grade CME data.

The news calendar may include numeric shock events such as `DGS2` and `DFII10`; Stage45B2 evaluates category/source fields as well as event titles so that these macro events are not incorrectly rejected by title-only keyword checks.
