# Stage42 Final Archive After Intraday Megascan V3

Date: 2026-06-17

## Decision

```text
Stage42 = ARCHIVE
Stage42B = NOT_ALLOWED

promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

Stage42 produced no strict or soft shortlist. Therefore there is no valid input set for a Stage42B path-stability / promotion audit.

## Input data

```text
db_path: data/local/xauusd_local_store.sqlite
table: bars
source: amarkets_mt5
symbol: XAUUSD
timeframe: M15
timeframe_normalized: M15
timeframe_minutes: 15
loaded_rows: 102,493
loaded_start: 2022-05-01T23:00:00+00:00
loaded_end: 2026-06-16T12:15:00+00:00
timestamp_column: utc_time
spread_column: spread
```

The loader/filter path was valid for the project schema:

```text
requested_timeframe: M15
requested_timeframe_normalized: M15
timeframe_alias_matches: 102,493
post_filter_rows_after_ohlc_clean: 102,493
```

## Scan settings

```text
cost_bps: 8.0
slip_bps: 16.0
min_events: 120
event_clock: candidate-specific min_gap equals horizon_bars
train_oos_split: chronological 70/30 event-clock split
intraday_path_risk: MAE/MFE plus touch_stop_35bps and touch_stop_50bps
```

## Thesis families scanned

- `42A_LONDON_ASIA_RANGE_MICRO_RETEST`
- `42B_NY_IMPULSE_PULLBACK_CONTINUATION`
- `42C_PREVDAY_LIQUIDITY_SWEEP_REVERSAL`
- `42D_INTRADAY_COMPRESSION_EXPANSION_CONFIRM`
- `42E_LONDON_RANGE_ACCEPTANCE_REJECTION`
- `42F_MICROTREND_PULLBACK_HOLD`

## Result

```text
candidate_rows = 168
events_rows_written = 103371
strict_stage42_intraday_scan_watch_count = 0
soft_stage42_intraday_scan_watch_count = 0
```

Classification counts:

```text
FAIL_BENCHMARK_OR_INTRADAY_STABILITY_RESEARCH_ONLY: 128
INSUFFICIENT_EVENTS_RESEARCH_ONLY: 40
```

## Interpretation

The branch failed at the scan stage. Since both strict and soft watch counts are zero, a follow-up Stage42B audit would be empty and is not allowed.

The top-ranked rows were still classified as `FAIL_BENCHMARK_OR_INTRADAY_STABILITY_RESEARCH_ONLY`. Their failed reasons were dominated by conditions such as:

```text
cost_mean_gt_15
train_gt_0
oos_gt_0
worst_quarter_slip16_gt_minus20
boot_p10_gt_minus5
boot_prob_gt_65
positive_quarter_pct_ge_45
```

This means there is no robust, cost-aware intraday execution candidate in Stage42.

## Anti-overfit constraints

Do not rescue Stage42 by removing weak buckets after seeing results, including:

```text
weak hours
weak months
weak years
stop-touch buckets
specific bad OOS slices
```

No Stage42 row may be promoted, used for EA alerts, paper-live, live, or execution-layer work.

## Next allowed branch

```text
Stage43 = allowed only as a genuinely new thesis branch
Stage42B = not allowed
```

Recommended direction:

```text
Stage43_PARALLEL_CONTEXT_REGIME_MEGASCAN_V4
```

Rationale:

- Stage41 H1 produced zero strict/soft shortlist.
- Stage42 M15 produced zero strict/soft shortlist.
- Moving directly to smaller execution timeframe is unlikely to solve a cost/stability failure unless the thesis itself changes.
- Stage43 should test predeclared context/regime hypotheses rather than post-hoc filters on Stage42 rows.

Suggested Stage43 constraints:

```text
benchmark-first
cost-aware
no promotion at scan stage
no rescue of Stage41/Stage42 candidates
predeclared regime/context gates only
include archive decision if strict/soft shortlist remains zero
```
