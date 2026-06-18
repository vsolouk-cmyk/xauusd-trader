# Stage45B2_EXTERNAL_CONTEXT_ALIGNMENT_AUDIT

## Decision

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
status = EXTERNAL_CONTEXT_ALIGNMENT_AUDIT_BLOCKED_NO_PROMOTION
recommended_next_stage = Stage45B2A_EXTERNAL_CONTEXT_ALIGNMENT_REPAIR
```

Stage45B2 audits external context alignment only. It does not create signals, shortlist candidates, or promote archived rows.

## P0 schema readiness

| key | status |
| :-- | :-- |
| dxy | READY |
| us10y_yield | READY |
| cme_gc_reference | READY |
| news_calendar | READY |

## Daily context coverage

| key | rows | start | end | same_day_coverage | safe_lag_coverage | staleness_median_days |
| :-- | --: | :-- | :-- | --: | --: | --: |
| dxy | 1025 | 2022-05-02T00:00:00+00:00 | 2026-06-05T00:00:00+00:00 | 79.52% | 99.84% | 0.000 |
| us10y_yield | 1028 | 2022-05-02T00:00:00+00:00 | 2026-06-11T00:00:00+00:00 | 79.91% | 99.84% | 0.000 |
| real_yield_optional | 1028 | 2022-05-02T00:00:00+00:00 | 2026-06-11T00:00:00+00:00 | 79.91% | 99.84% | 0.000 |
| us02y_yield_optional | 0 |  |  |  |  |  |

## CME/GC reference alignment

```json
{
  "schema_ok": true,
  "row_count": 1039,
  "start": "2022-05-02T00:00:00+00:00",
  "end": "2026-06-18T00:00:00+00:00",
  "overlap_rows": 1037,
  "overlap_pct_of_bar_days": 0.807632398753894,
  "return_corr": 0.8445723130581777,
  "return_sign_agreement_pct": 0.8658301158301158,
  "close_diff_bps_profile": {
    "n": 1037,
    "min": 0.0002795289961385089,
    "p10": 3.252637188097828,
    "median": 16.231512465756374,
    "p90": 64.90400615096044,
    "p95": 87.89447505353998,
    "p99": 201.0320794145893,
    "max": 383.2477803684283,
    "mean": 27.405348492700625
  }
}
```

## News calendar blackout alignment

```json
{
  "schema_ok": true,
  "blackout_ready": false,
  "row_count": 515,
  "start": "2022-01-10T13:30:00+00:00",
  "end": "2026-12-09T19:00:00+00:00",
  "macro_semantic_hits": 233,
  "central_bank_gold_only_hits": 10,
  "bars_in_blackout": 0,
  "bars_in_blackout_pct": 0.0,
  "decision_reason": "schema_ok_but_no_bars_in_blackout_window"
}
```

## Blockers and warnings

```json
{
  "blockers": [
    "news_blackout_windows_do_not_cover_any_bars"
  ],
  "warnings": [
    "news_calendar_schema_ok_but_semantic_blackout_review_recommended"
  ]
}
```

## Not allowed

- `candidate_rescue_from_stage41_42_43`
- `post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets`
- `EA_paper_live_live_from_archived_rows`
- `ML_before_robust_cost_aware_baseline`
- `new_candle_only_blind_megascan_before_external_context_alignment_is_audited`

## Anti-overfit note

Do not use this audit to rescue Stage41/42/43 rows. If alignment passes, the next valid action is a predefined external-context baseline design, not a post-hoc candidate rescue pass.
