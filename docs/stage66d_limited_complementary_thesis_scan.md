# Stage66D Limited Complementary Thesis Scan

Stage66D is a limited, pre-registered complementary macro-thesis scan for the XAUUSD project.

It exists because Stage66H confirmed that H64L v2 is commercially ready at the design/dry-run level, but the current forward signal is inactive. The project should therefore avoid waiting passively for a low-frequency H64L signal and should test a small number of complementary, shorter-horizon macro theses.

## Scope

Stage66D evaluates only the thesis definitions listed in:

```text
configs/stage66d_limited_complementary_thesis_scan.json
```

No dynamic search, broad megascan, threshold tuning, or event-calendar filtering is allowed.

## Inputs

```text
data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv
data/macro_regime/raw/broker_or_spot_gold_d1_ohlc_2011_present.csv
reports/stage66h_no_broker_dry_run_ticket_generator/stage66h_no_broker_dry_run_ticket_generator_summary.json
```

## Registered thesis families

- D1: gold trend + DXY fall + real-yield fall.
- D2: gold trend + positive ETF flow.
- D3: gold trend + DXY trend relief.
- D4: gold trend + volatility/risk-off + real-yield fall.

Each thesis is evaluated only at the pre-registered horizons, currently 20 and 60 trading days.

## Execution model

The script uses the first external D1 close on or after `sample_available_after_utc`, then exits after the fixed registered horizon. Position-level diagnostics are built with a single-position, non-overlapping engine.

Default costs:

```text
round_trip_execution_cost_bps = 35
feed_mismatch_penalty_bps = 15
total_penalty_bps = 50
```

## Decisions

```text
STAGE66D_PASS_FAST_COMPLEMENTARY_SHORTLIST_NO_ORDER
STAGE66D_WATCH_COMPLEMENTARY_CANDIDATES_NO_ORDER
STAGE66D_NO_COMPLEMENTARY_CANDIDATE_CONTINUE_H64L_BACKGROUND_NO_ORDER
STOP_STAGE66D_STAGE66H_GATE_NOT_READY_NO_ORDER
```

No decision authorizes orders, broker connection, EA promotion, paper-live, or live execution.
