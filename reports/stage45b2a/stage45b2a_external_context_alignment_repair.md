# Stage45B2A_EXTERNAL_CONTEXT_ALIGNMENT_REPAIR

## Decision

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
status = EXTERNAL_CONTEXT_ALIGNMENT_REPAIR_READY_NO_PROMOTION
recommended_next_stage = Stage45B3_EXTERNAL_CONTEXT_BASELINE_DESIGN_PRECHECK
```

Stage45B2A repairs only external-context/news-blackout alignment diagnostics. It does not create trading signals, shortlist candidates, or promote archived rows.

## News calendar meta

```json
{
  "exists": true,
  "schema_ok": true,
  "row_count": 47,
  "start": "2026-01-08T19:00:00+00:00",
  "end": "2026-12-30T19:00:00+00:00",
  "macro_semantic_hits": 47,
  "central_bank_gold_only_hits": 0,
  "usd_or_unknown_rows": 47
}
```

## Blackout repair profiles

| variant | event_count | bars_in_blackout | bars_in_blackout_pct | events_with_bar | median_bars_per_event |
| :-- | --: | --: | --: | --: | --: |
| all_events | 47 | 8122 | 7.924% | 25 | 610.0 |
| macro_semantic_only | 47 | 8122 | 7.924% | 25 | 610.0 |
| macro_usd_or_unknown | 47 | 8122 | 7.924% | 25 | 610.0 |

## Selected repaired blackout windows

```text
selected_blackout_variant = macro_usd_or_unknown
selected_bars_in_blackout = 8122
canonical_blackout_windows_path = data/external/news_blackout_windows.csv
```

## Blockers and warnings

```json
{
  "blockers": [],
  "warnings": []
}
```

## Not allowed

- `candidate_rescue_from_stage41_42_43`
- `post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets`
- `EA_paper_live_live_from_archived_rows`
- `ML_before_robust_cost_aware_baseline`
- `new_blind_megascan_before_external_context_alignment_repair_is_clean`

## Anti-overfit note

Do not use this repair step to rescue Stage41/42/43 rows. If alignment repair is clean, the next valid step is a predefined external-context baseline design precheck, not a post-hoc candidate rescue pass.
