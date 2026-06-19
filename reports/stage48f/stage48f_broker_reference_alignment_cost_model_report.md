# Stage48F Broker Reference Alignment and Cost Model Calibration

- status: `COST_MODEL_INSUFFICIENT_NO_PROMOTION`
- next_allowed_step: `FIX_ALIGNMENT_OR_BROKER_EXPORT_NO_PROMOTION`
- promotion: `NO_GO`
- EA: `NO_GO`
- paper_live: `NO_GO`
- live: `NO_GO`

## Inputs

- broker_csv: `/Users/vahid/Downloads/amarkets_xauusd_5m.csv`
- reference_csv: `/Users/vahid/Desktop/xauusd-trader/data/normalized/normalized_twelvedata_XAU_USD_5min_backfill_20260619T051819Z.csv`
- timeframe: `M5`
- point_size: `0.01`
- selected_broker_time_offset_hours: `4`

## Coverage

- broker_rows: `292435`
- broker_coverage_days: `1509.3299`
- broker_spread_coverage_pct: `5.9647`
- reference_rows: `25905`
- aligned_rows: `17443`
- aligned_coverage_days: `88.3715`

## Spread cost model

- median_spread_points: `37.0000`
- p90_spread_points: `44.0000`
- p95_spread_points: `44.0000`
- p99_spread_points: `45.0000`
- median_spread_cost_bps: `0.8088`
- p90_spread_cost_bps: `0.9501`
- p95_spread_cost_bps: `0.9820`
- p99_spread_cost_bps: `1.0380`
- slippage_buffer_bps: `2.0000`
- recommended_cost_bps: `2.9501`
- stress_cost_bps: `2.9820`
- extreme_cost_bps: `3.0380`

## Broker-reference alignment

- median_basis_bps: `-1.2857`
- median_abs_basis_bps: `17.0967`
- p95_abs_basis_bps: `81.7316`
- p99_abs_basis_bps: `181.1438`

## Decision

ready_failure_reasons: `['broker_spread_coverage_lt_80pct']`

This stage calibrates cost and alignment only. It does not generate trading signals and does not allow EA, paper-live, or live action.
