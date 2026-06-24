# Stage42_PARALLEL_INTRADAY_EXECUTION_MEGASCAN_V3

## Purpose

Stage42 starts a genuinely new branch after Stage41 archive. It is not a rescue of Stage39, Stage40, or Stage41.

Stage42 changes the research substrate from H1 thesis scanning to intraday execution-feasibility scanning. The default timeframe is `M15`, because the local DB already contains substantially more M15 history than H1. The objective is to test whether intraday structure produces a robust, cost-aware, path-feasible shortlist before any promotion audit.

## Hard operating state

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

The scan itself cannot promote anything. A strict/soft row is only a research watch row. Operational work remains forbidden unless a later Stage42B path-stability/promotion audit passes.

## Default input

```text
db_path: data/local/xauusd_local_store.sqlite
table: bars
source: amarkets_mt5
symbol: XAUUSD
timeframe: M15
```

The loader is DB-first and schema-tolerant:

- timestamp aliases include `utc_time`, `ts_utc`, `timestamp`, `source_time`, and related variants.
- timeframe aliases include `M15`, `15m`, `15MIN`, `15MINUTE`, and related variants.
- source/symbol matching is normalized by strip, casefold, and compact matching.
- zero-row filtering raises a diagnostic JSON with available source/symbol/timeframe values.

## Thesis families scanned

```text
42A_LONDON_ASIA_RANGE_MICRO_RETEST
42B_NY_IMPULSE_PULLBACK_CONTINUATION
42C_PREVDAY_LIQUIDITY_SWEEP_REVERSAL
42D_INTRADAY_COMPRESSION_EXPANSION_CONFIRM
42E_LONDON_RANGE_ACCEPTANCE_REJECTION
42F_MICROTREND_PULLBACK_HOLD
```

These are intraday/execution-feasibility theses. They are not Stage40/41 H1 rescue filters.

## Intraday-specific mechanics

For M15, the default horizons are:

```text
1h = 4 bars
2h = 8 bars
4h = 16 bars
8h = 32 bars
```

The same script can run on M5/M30 by changing `--timeframe`, but the first intended scan is M15.

Path-risk metrics are tighter than H1:

```text
touch_stop_35bps_pct
touch_stop_50bps_pct
median_mae_bps
median_mfe_bps
oos_touch_stop_50bps_pct
```

## Output files

```text
reports/stage42/stage42_parallel_intraday_execution_megascan_v3_candidates.csv
reports/stage42/stage42_parallel_intraday_execution_megascan_v3_events.csv
reports/stage42/stage42_parallel_intraday_execution_megascan_v3_summary.json
reports/stage42/stage42_parallel_intraday_execution_megascan_v3.md
```

## Decision rule

Stage42B is allowed only if:

```text
strict_stage42_intraday_scan_watch_count > 0
```

If strict count is zero, the default action is to archive Stage42 or start a genuinely new thesis branch.

Soft rows are not enough for promotion. They can only inform a future independent thesis design if the rule is not post-hoc rescued.

## Anti-overfit rules

Do not rescue failed Stage42 rows by removing weak buckets after seeing results, including weak hours, weekdays, months, years, quarters, sessions, or stop-touch buckets.

Do not continue any failed Stage39/40/41 survivor under a new name.

## Run command

```bash
python3 scripts/stage42_parallel_intraday_execution_megascan_v3.py
```

Optional M5 exploratory run, only after M15 result is reviewed:

```bash
python3 scripts/stage42_parallel_intraday_execution_megascan_v3.py --timeframe M5 --outdir reports/stage42_m5 --min-events 200
```
