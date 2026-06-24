# Stage46 External Context Baseline Scan Design

Stage46 is a design-contract stage only. It consumes the clean Stage45B3 precheck and writes a predefined external-context baseline design matrix.

It does not run a scan, does not create signals, does not shortlist candidates, and cannot promote any archived Stage41/42/43 row.

## Inputs

- `reports/stage45b3/stage45b3_external_context_baseline_design_precheck_summary.json`
- `data/local/xauusd_local_store.sqlite`
- `data/external/dxy.csv`
- `data/external/us10y_yield.csv`
- `data/external/real_yield.csv` optional
- `data/reference/cme_gc.csv`
- `data/external/news_calendar.csv`
- `data/external/news_blackout_windows.csv`

## Outputs

- `reports/stage46/stage46_external_context_baseline_scan_design_summary.json`
- `reports/stage46/stage46_external_context_baseline_scan_design.md`
- `reports/stage46/stage46_readiness_matrix.csv`
- `reports/stage46/stage46_baseline_design_matrix.csv`
- `reports/stage46/stage46_guardrail_contract.csv`

## Designed families

1. `EXTCTX_A_DXY_YIELD_TREND_FILTER`
2. `EXTCTX_B_NEWS_BLACKOUT_GUARD`
3. `EXTCTX_C_REFERENCE_FEED_SANITY`
4. `EXTCTX_D_COMPOSITE_CONTEXT_SCORE`

These are prospective designs only. The next stage must implement exactly this design in a cost-aware baseline pass without post-hoc rescue.

## Hard rules

- No Stage41/42/43 candidate rescue.
- No ML.
- No EA/paper/live/live.
- No post-hoc filtering of bad buckets.
- Daily macro context must use safe lag.
- GC reference remains reference-only, not execution-grade.
- News blackout windows must be predefined and materialized before testing.

## Run

```bash
python3 scripts/stage46_external_context_baseline_scan_design.py --print-summary
```
