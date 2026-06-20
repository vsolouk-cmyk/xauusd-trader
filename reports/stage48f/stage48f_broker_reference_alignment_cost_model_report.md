# Stage48F Broker Reference Alignment and Cost Model Calibration

- status: `COST_MODEL_READY_NO_PROMOTION`
- next_allowed_step: `BROKER_REAL_COST_AWARE_THESIS_DESIGN_OR_RERUN_NO_PROMOTION`
- promotion: `NO_GO`
- EA: `NO_GO`
- paper_live: `NO_GO`
- live: `NO_GO`

## Inputs

- broker_csv: `/Users/vahid/Downloads/amarkets_xauusd_5m.csv`
- reference_csv: `/Users/vahid/Desktop/xauusd-trader/data/normalized/normalized_twelvedata_XAU_USD_5min_backfill_20260619T051819Z.csv`
- timeframe: `M5`
- point_size: `0.01`
- selected_broker_time_offset_hours: `3`

## Coverage

- broker_rows: `292435`
- broker_coverage_days: `1509.3299`
- broker_raw_spread_coverage_pct: `100.0000`
- aligned_spread_coverage_pct: `100.0000`
- reference_rows: `25905`
- aligned_rows: `17435`
- aligned_coverage_days: `88.3438`

## Spread cost model

- median_spread_points: `37.0000`
- p90_spread_points: `44.0000`
- p95_spread_points: `44.0000`
- p99_spread_points: `45.0000`
- median_spread_cost_bps: `0.8087`
- p90_spread_cost_bps: `0.9501`
- p95_spread_cost_bps: `0.9820`
- p99_spread_cost_bps: `1.0380`
- slippage_buffer_bps: `2.0000`
- recommended_cost_bps: `2.9501`
- stress_cost_bps: `2.9820`
- extreme_cost_bps: `3.0380`

## Broker-reference alignment

- median_basis_bps: `-0.6461`
- median_abs_basis_bps: `1.8990`
- p95_abs_basis_bps: `25.0662`
- p99_abs_basis_bps: `110.9022`

## Decision

ready_failure_reasons: `[]`

LoaderFix1 note: broker raw spread coverage is measured on accepted broker rows; aligned spread coverage is measured on aligned rows. Price basis is diagnostic and does not by itself authorize trading.

This stage calibrates cost and alignment only. It does not generate trading signals and does not allow EA, paper-live, or live action.
