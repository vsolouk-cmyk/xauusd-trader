# Stage48C Broker Spread Row-Level Audit

- status: `BROKER_SPREAD_ROW_LEVEL_INSUFFICIENT_NO_PROMOTION`
- next_allowed_step: `BROKER_SPREAD_COLLECTOR_OR_MT5_EXPORT_DESIGN`
- promotion: `NO_GO`
- EA: `NO_GO`
- paper_live: `NO_GO`
- live: `NO_GO`

## Decision

- sqlite_files_audited: `1`
- row_level_candidates: `4`
- broker_spread_row_level_ready: `False`
- stop_reason: `row_level_spread_schema_exists_but_coverage_or_quality_threshold_failed`

## Best candidate

- db_path: `/Users/vahid/Desktop/xauusd-trader/data/local/xauusd_local_store.sqlite`
- table: `bars`
- filtered_rows: `307334`
- coverage_days: `1506.5520833333333`
- numeric_spread_rows: `13770`
- numeric_spread_coverage_pct_scanned: `5.508`
- median_spread: `35.0`
- p90_spread: `48.0`
- p95_spread: `51.0`
- inferred_spread_units: `BROKER_POINTS_OR_PRICE_CENTS_LIKELY`

## Interpretation

This stage only audits whether row-level broker/execution spread history is usable. It does not generate signals, does not tune a thesis, and does not allow EA, paper-live, or live promotion.
