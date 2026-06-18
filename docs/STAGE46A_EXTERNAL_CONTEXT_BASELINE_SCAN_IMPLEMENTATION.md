# Stage46A External Context Baseline Scan Implementation

Stage46A implements the predefined Stage46 external-context baseline design in a fresh, cost-aware research pass.

It does not:

- rescue Stage41/Stage42/Stage43 candidates;
- use post-hoc bad-bucket exclusion;
- create EA, paper-live, or live permissions;
- promote any row;
- use ML.

## Inputs

Required local inputs:

```text
SQLite: data/local/xauusd_local_store.sqlite
Table: bars
Source: amarkets_mt5
Symbol: XAUUSD
Timeframe: M15
```

External context inputs:

```text
data/external/dxy.csv
data/external/us10y_yield.csv
data/external/real_yield.csv
data/reference/cme_gc.csv
data/external/news_blackout_windows.csv
reports/stage46/stage46_external_context_baseline_scan_design_summary.json
```

## Implemented families

```text
EXTCTX_A_DXY_YIELD_TREND_FILTER
EXTCTX_B_NEWS_BLACKOUT_GUARD
EXTCTX_C_REFERENCE_FEED_SANITY
EXTCTX_D_COMPOSITE_CONTEXT_SCORE
```

The news blackout component is implemented as either `exclude` or `tag_only`; it is not treated as an alpha source.

## Guardrails

- DXY/yields/real yield are aligned with one daily lag.
- GC reference feed is used only for reference confirmation, not execution.
- News blackout windows are pre-materialized UTC windows.
- Spread/cost is included through observed bar spread.
- Candidate rows must pass a later Stage46B audit before any promotion discussion.

## Run

```bash
python3 scripts/stage46a_external_context_baseline_scan_implementation.py --print-summary
```

Optional:

```bash
python3 scripts/stage46a_external_context_baseline_scan_implementation.py \
  --hold-bars 4 8 16 \
  --bootstrap-iterations 300 \
  --print-summary
```

## Outputs

```text
reports/stage46a/stage46a_external_context_baseline_scan_implementation_summary.json
reports/stage46a/stage46a_external_context_baseline_scan_implementation.md
reports/stage46a/stage46a_candidate_metrics.csv
reports/stage46a/stage46a_event_audit_sample.csv
reports/stage46a/stage46a_benchmark_metrics.csv
reports/stage46a/stage46a_feature_coverage.csv
```

## Interpretation

If strict or soft candidates appear, the next valid step is a separate Stage46B audit. If no candidate survives, the branch should move to failure analysis or archive rather than relaxing rules.
