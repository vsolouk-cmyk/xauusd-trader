# Stage46_EXTERNAL_CONTEXT_BASELINE_SCAN_DESIGN

## Decision

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
status = EXTERNAL_CONTEXT_BASELINE_SCAN_DESIGN_READY_NO_PROMOTION
recommended_next_stage = Stage46A_EXTERNAL_CONTEXT_BASELINE_SCAN_IMPLEMENTATION
```

Stage46 is a design-contract stage only. It does not run a scan, create trading signals, shortlist candidates, or promote archived rows.

## Readiness

| area          | check                                   |   value | ok   | severity   | note                                                                                                                    |
|:--------------|:----------------------------------------|--------:|:-----|:-----------|:------------------------------------------------------------------------------------------------------------------------|
| stage_chain   | stage45b3_ready_for_stage46             |    True | True | blocker    | status=EXTERNAL_CONTEXT_BASELINE_DESIGN_PRECHECK_READY_NO_PROMOTION; next=Stage46_EXTERNAL_CONTEXT_BASELINE_SCAN_DESIGN |
| bars          | m15_xauusd_bars_loaded                  |  102493 | True | blocker    | start=2022-05-01T23:00:00+00:00; end=2026-06-16T12:15:00+00:00; error=None                                              |
| external_file | data/external/dxy.csv                   |    1025 | True | blocker    | schema_ok=True; start=2022-05-02T00:00:00+00:00; end=2026-06-05T00:00:00+00:00; error=None                              |
| external_file | data/external/us10y_yield.csv           |    1028 | True | blocker    | schema_ok=True; start=2022-05-02T00:00:00+00:00; end=2026-06-11T00:00:00+00:00; error=None                              |
| external_file | data/external/real_yield.csv            |    1028 | True | warning    | schema_ok=True; start=2022-05-02T00:00:00+00:00; end=2026-06-11T00:00:00+00:00; error=None                              |
| external_file | data/reference/cme_gc.csv               |    1039 | True | blocker    | schema_ok=True; start=2022-05-02T00:00:00+00:00; end=2026-06-18T00:00:00+00:00; error=None                              |
| external_file | data/external/news_calendar.csv         |      47 | True | blocker    | schema_ok=True; start=2026-01-08T19:00:00+00:00; end=2026-12-30T19:00:00+00:00; error=None                              |
| external_file | data/external/news_blackout_windows.csv |      47 | True | blocker    | schema_ok=True; start=None; end=None; error=None                                                                        |

## Designed baseline families

| family_id                        | design_role                             | implementation_status    | notes                                                                                                               |
|:---------------------------------|:----------------------------------------|:-------------------------|:--------------------------------------------------------------------------------------------------------------------|
| EXTCTX_A_DXY_YIELD_TREND_FILTER  | directional_context_filter              | DESIGNED_NOT_IMPLEMENTED | Gold-supportive context is falling USD/yields; hostile context is rising USD/yields. No post-hoc filtering allowed. |
| EXTCTX_B_NEWS_BLACKOUT_GUARD     | risk_filter_not_alpha_source            | DESIGNED_NOT_IMPLEMENTED | Blackout is a guard/diagnostic layer. It must not become a post-hoc edge rescue filter.                             |
| EXTCTX_C_REFERENCE_FEED_SANITY   | feed_sanity_and_marketwide_confirmation | DESIGNED_NOT_IMPLEMENTED | Yahoo GC=F is acceptable for reference-feed sanity only, not execution-grade settlement.                            |
| EXTCTX_D_COMPOSITE_CONTEXT_SCORE | predefined_composite_context_bucket     | DESIGNED_NOT_IMPLEMENTED | Composite score must be a transparent rule score, not ML. All weights fixed before test.                            |

## Required guardrails

- `no_archived_candidate_rescue`: Do not evaluate Stage41/42/43 rows with new filters (hard)
- `daily_context_no_lookahead`: DXY/yields/real yield available only with lag1 daily forward-fill (hard)
- `news_blackout_predefined`: Use pre-materialized UTC windows only; no optimizing event windows on outcomes (hard)
- `reference_feed_not_execution`: GC=F/yfinance reference can tag market-wide agreement only; not settlement/execution (hard)
- `cost_aware_first`: Observed spread/cost assumptions remain first-class in every implementation (hard)
- `stability_before_promotion`: Quarter and bootstrap stability required before any promotion discussion (hard)
- `no_ml`: No ML until robust cost-aware rule baselines survive (hard)

## Not allowed

- `candidate_rescue_from_stage41_42_43`
- `post_hoc_filtering_of_bad_hours_months_years_quarters_contexts_or_spread_buckets`
- `EA_paper_live_live_from_archived_rows`
- `ML_before_robust_cost_aware_baseline`
- `running_external_context_scan_before_stage46_design_contract_is_committed`

## Anti-overfit note

This design cannot be used to rescue Stage41/42/43 rows. The next step, if ready, is implementation of this predefined design in a fresh cost-aware baseline pass.
