# Stage45B1B News Calendar and CME Gap Closure Loaderfix

## Purpose

This patch fixes a defensive-counting bug in `scripts/stage45b1b_news_calendar_cme_gap_closure.py`.

The original diagnostic can crash in `classify_news_calendar()` when pandas/runtime/object-dtype behavior produces a non-integer value while counting boolean macro-keyword masks. The crash is diagnostic-only and does not invalidate the Stage45B1A result.

## Fix

- Add `_bool_sum()` to count boolean-like masks safely.
- Add `_series_text()` to normalize blank cells before text matching.
- Use robust counting for:
  - `macro_keyword_hits`
  - `central_bank_gold_only_hits`
  - `usd_or_unknown_rows`

## Expected result

If the canonical P0 files are present:

```text
p0_schema_ok_keys = [dxy, us10y_yield, cme_gc_reference, news_calendar]
p0_missing_or_invalid_keys = []
recommended_next_stage = Stage45B2_EXTERNAL_CONTEXT_ALIGNMENT_AUDIT
```

## Gates

This loaderfix does not change project gates:

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

Stage45B1B remains a diagnostic only. It does not create signals, shortlist candidates, rescue archived rows, or authorize any operational layer.
