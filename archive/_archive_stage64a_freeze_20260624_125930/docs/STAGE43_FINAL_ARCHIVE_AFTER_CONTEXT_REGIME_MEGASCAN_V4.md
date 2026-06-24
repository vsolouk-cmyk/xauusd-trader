# Stage43 Final Archive After Context-Regime Megascan V4

## Decision

```text
Stage43 = ARCHIVE
Stage43B = NOT_ALLOWED
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

Stage43 was a context/regime research scan on M15. It produced no strict or soft shortlist rows, so there is no eligible input for a Stage43B path-stability / promotion audit.

## Input data

```text
db_path: data/local/xauusd_local_store.sqlite
table: bars
source: amarkets_mt5
symbol: XAUUSD
timeframe: M15
timeframe_normalized: M15
timeframe_minutes: 15
loaded_rows: 102493
loaded_start: 2022-05-01T23:00:00+00:00
loaded_end: 2026-06-16T12:15:00+00:00
```

## Families scanned

- `43A_CONTEXT_TREND_PULLBACK_CONTINUATION`
- `43B_VOL_CONTEXT_IMPULSE_EXHAUSTION_REVERSAL`
- `43C_PRIOR_DAY_CONTEXT_RECLAIM_REJECT`
- `43D_CONTEXT_COMPRESSION_TO_EXPANSION`
- `43E_ASIA_RANGE_REGIME_ACCEPT_REJECT`
- `43F_NEUTRAL_REGIME_VALUE_ROTATION`


## Evidence

```text
candidate_rows = 336
events_rows_written = 49079
strict_stage43_context_regime_scan_watch_count = 0
soft_stage43_context_regime_scan_watch_count = 0
```

Classification counts:

```text
INSUFFICIENT_EVENTS_RESEARCH_ONLY = 203
FAIL_BENCHMARK_OR_CONTEXT_STABILITY_RESEARCH_ONLY = 133
```

## Interpretation

The branch failed at the scan/shortlist gate. Since both strict and soft watch counts are zero, Stage43B is not allowed. Rows with superficially positive residuals still failed the predefined gates such as cost mean, train/OOS stability, worst-quarter slip stress, bootstrap floor, or concentration controls.

## Anti-overfit constraints

Do not rescue failed Stage43 rows by removing weak hours, months, years, quarters, volatility states, context states, or stop-touch buckets after seeing this output. That would be post-hoc filtering and is not allowed.

Do not continue these Stage43 rows through any execution layer:

```text
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

## Next allowed step

```text
Stage44 = allowed only as a genuinely new branch
Recommended: Stage44 meta-diagnostic / thesis-space audit before adding another blind megascan
```

Rationale: Stage41, Stage42, and Stage43 all produced zero shortlist rows. The next step should reduce wasted scanning by auditing why thesis families fail and by identifying structural constraints before generating another large candidate grid.
