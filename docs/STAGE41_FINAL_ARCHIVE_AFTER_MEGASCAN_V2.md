# STAGE41 FINAL ARCHIVE AFTER MEGASCAN V2

Date: 2026-06-17  
Source stage: `Stage41_PARALLEL_THESIS_MEGASCAN_V2`

## Final decision

```text
Stage41 = ARCHIVE
Stage41B_STRICT_SHORTLIST_PATH_STABILITY_AUDIT = NOT_ALLOWED
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

## Why Stage41 is closed

Stage41 scanned six new thesis families in a benchmark-first, cost-aware, event-clock scan. The scan produced no strict or soft shortlist rows.

```text
candidate_rows = 180
events_rows_written = 19627
strict_stage41_scan_watch_count = 0
soft_stage41_scan_watch_count = 0
```

Classification counts:

```text
FAIL_BENCHMARK_OR_STABILITY_RESEARCH_ONLY = 136
INSUFFICIENT_EVENTS_RESEARCH_ONLY = 44
```

Because both strict and soft watch counts are zero, there is no valid Stage41B target. Running Stage41B would only audit an empty shortlist or require post-hoc rescue, which is not allowed.

## Data used

```text
db_path = data/local/xauusd_local_store.sqlite
table = bars
source = amarkets_mt5
symbol = XAUUSD
timeframe_requested = H1
timeframe_loaded = ['1h']
loaded_rows = 25643
loaded_start = 2022-05-01T23:00:00+00:00
loaded_end = 2026-06-16T12:00:00+00:00
```

Loader/filter diagnostics confirm that the H1 alias issue was fixed and that `H1` correctly mapped to loaded `1h` bars.

```text
pre_filter_rows = 1971743
timeframe_alias_matches = 25643
post_filter_rows_after_ohlc_clean = 25643
timestamp_column = utc_time
```

## Thesis families scanned

- `41A_MTF_STRUCTURE_BREAK_RETEST`
- `41B_NY_IMPULSE_EXHAUSTION_REVERSAL`
- `41C_SHOCK_COOLDOWN_CONTINUATION`
- `41D_ASIA_RANGE_BREAK_RETEST`
- `41E_PRIOR_DAY_LEVEL_RECLAIM_REJECT`
- `41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION`

## Interpretation

Some individual rows had superficially attractive mean returns, but they were not promotable because the formal scan gates rejected them. The dominant failure mode remained path/stability weakness, especially weak-quarter slippage stress. This is the same type of fragility that previously killed Stage40, so weakening the gates would be the wrong response.

The strongest-looking Stage41 rows must not be rescued by excluding weak buckets after seeing the result. That would create a post-hoc filtered thesis rather than a stable trading rule.

## Closed / forbidden actions

```text
Do not run Stage41B.
Do not promote any Stage41 candidate.
Do not build EA/paper/live/Telegram alerts from Stage41.
Do not rescue Stage41 rows with post-hoc filters.
Do not continue MULTIBAR_VOL_EXPAND_* rows as a special exception.
Do not continue MTF_BREAK_RETEST_* rows as a special exception.
Do not continue ASIA_BREAK_RETEST_* rows as a special exception.
```

## Next allowed branch

The next allowed research path is a genuinely new branch. Recommended:

```text
Stage42_PARALLEL_THESIS_MEGASCAN_V3
```

Stage42 should keep the fast two-step workflow:

```text
1. Parallel scan of independent thesis families.
2. Promotion/path-stability audit only for a real strict/soft shortlist.
```

Potential Stage42 directions should avoid direct rescue of Stage41. Good directions:

1. M5/M15 execution-feasibility thesis scan using already loaded intraday data.
2. Volatility-normalized session thesis with pre-defined news/shock blackout proxy.
3. Cross-timeframe trend/day-type classifier as an on/off filter for simple baselines, not a direct prediction model.
4. Symmetric long/short intraday impulse-retreat thesis with strict early-quarter stability required at scan time.
5. Spread-aware/no-trade-window diagnostics before any new high-frequency thesis.

## Bottom line

```text
Stage41 produced no strict or soft shortlist.
Stage41B is not allowed.
Stage41 is archived.
Next step is a new independent Stage42, not Stage41 rescue.
```
