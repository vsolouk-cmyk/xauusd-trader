# Stage41 Parallel Thesis Megascan V2

Stage41 starts a new independent XAUUSD/gold research branch after the Stage38, Stage39, and Stage40 archives.

This patch implements:

```text
Stage41_PARALLEL_THESIS_MEGASCAN_V2
```

The stage is deliberately research-only:

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

No candidate produced by this scan may be used for Telegram trade alerts, EA logic, paper-live, paper-order, or live execution. A later Stage41B path-stability audit is required even if this scan produces strict watch rows.

## Why this stage exists

Stage40 showed that the faster workflow is useful: scan many thesis families in parallel first, then audit only a shortlist. Stage41 keeps that two-step structure but starts from genuinely new thesis families.

The Stage41 workflow is:

```text
1. Parallel thesis megascan
2. Promotion/path-stability audit only for strict/soft shortlist
```

This patch covers step 1 only.

## What Stage41 must not do

Stage41 must not rescue or extend:

```text
VOL_COMP_EXP_LONG_L120_Q0.15_M2.0
RANGE_BOTTOM_REV_LONG_W48_Q0.05
BB_LOWER_REV_LONG_W120_K2.5
Stage39 condition buckets
Stage40 soft-watch rows
```

Stage41 must not remove weak buckets after seeing results from Stage40 or Stage41. Post-hoc exclusions are overfit.

## Script

```text
scripts/stage41_parallel_thesis_megascan_v2.py
```

Default input:

```text
DB: data/local/xauusd_local_store.sqlite
Table: bars
Source: amarkets_mt5
Symbol: XAUUSD
Timeframe: H1
```

Default output:

```text
reports/stage41/stage41_parallel_thesis_megascan_v2_candidates.csv
reports/stage41/stage41_parallel_thesis_megascan_v2_events.csv
reports/stage41/stage41_parallel_thesis_megascan_v2_summary.json
reports/stage41/stage41_parallel_thesis_megascan_v2.md
```

## Thesis families scanned

Stage41 uses new families rather than Stage39/40 rescue rules:

```text
41A_MTF_STRUCTURE_BREAK_RETEST
41B_NY_IMPULSE_EXHAUSTION_REVERSAL
41C_SHOCK_COOLDOWN_CONTINUATION
41D_ASIA_RANGE_BREAK_RETEST
41E_PRIOR_DAY_LEVEL_RECLAIM_REJECT
41F_MULTIBAR_VOL_REGIME_EXPANSION_CONFIRMATION
```

### 41A MTF structure break + retest

H1 trigger with H4/D1 proxy context. The candidate requires structure break/retest/hold around prior multi-day levels and trend agreement.

### 41B NY impulse exhaustion reversal

Late New York reversal after a volatility-normalized impulse and rejection wick. This is predefined by clock and impulse conditions, not selected after observing weak buckets.

### 41C Shock cool-down continuation

Continuation only after a shock bar cools down and price holds the shock midpoint. This is not immediate shock reversal.

### 41D Asia range break + retest

London/early-NY break and retest/hold of a completed Asia range. This is not a plain Asia breakout baseline because the retest/hold condition is required.

### 41E Prior-day level reclaim/reject

Liquid-hours reclaim above prior-day high or reject below prior-day low with tolerance control.

### 41F Multi-bar volatility regime expansion confirmation

Compression-to-expansion candidate requiring two-bar confirmation and an explicit trend/volatility gate. This is intentionally different from the failed Stage40 one-bar compression expansion survivor.

## Classification labels

The scanner can produce these labels:

```text
STRICT_STAGE41_SCAN_WATCH_ONLY_NO_PROMOTION
SOFT_STAGE41_SCAN_WATCH_ONLY_NO_PROMOTION
FAIL_BENCHMARK_OR_STABILITY_RESEARCH_ONLY
INSUFFICIENT_EVENTS_RESEARCH_ONLY
ERROR_RESEARCH_ONLY
```

Strict and soft labels are watch-only. They are not promotion.

## Core gates inside the scan

The scan evaluates candidates using:

```text
event-clock thinning
cost-adjusted return
H1 benchmark residual
chronological 70/30 train/OOS split
quarter stability
slip16 stress
bootstrap mean distribution
LOYO-style year concentration checks
ex-2025 check
MAE/MFE path diagnostics
touch_stop_100bps percentage
```

The default stress settings are:

```text
cost_bps = 8
slip_bps = 16
min_events = 40
```

## Run command

From repo root:

```bash
python3 scripts/stage41_parallel_thesis_megascan_v2.py
```

Optional explicit command:

```bash
python3 scripts/stage41_parallel_thesis_megascan_v2.py \
  --db data/local/xauusd_local_store.sqlite \
  --table bars \
  --source amarkets_mt5 \
  --symbol XAUUSD \
  --timeframe H1 \
  --outdir reports/stage41 \
  --cost-bps 8 \
  --slip-bps 16 \
  --min-events 40
```

## Decision logic after running

If strict count is zero:

```text
Stage41A = archive or redesign new thesis families
Stage41B = not allowed
promotion = NO_GO
```

If strict count is greater than zero:

```text
Stage41B_STRICT_SHORTLIST_PATH_STABILITY_AUDIT is allowed
promotion remains NO_GO until Stage41B passes
```

If only soft rows exist:

```text
No promotion
Either archive or run a diagnostic-only audit if the row is conceptually important
```

## GitHub Actions

No workflow file is included in this patch because Stage41 is a local research scan against the local SQLite DB. Workflow behavior is not changed.

## Kill-switch

Stop Stage41 quickly if:

```text
strict_stage41_scan_watch_count = 0
all apparent edges are concentrated in one year or quarter
worst_quarter_slip16_mean_bps is negative for every shortlist row
OOS path risk is worse than the prior failed Stage40 survivor
```


## Loader compatibility fix

This package accepts the current project SQLite schema where the bars timestamp column may be named `utc_time` rather than `timestamp` or `ts_utc`. The loader uses schema introspection and maps the detected time column into internal `ts_utc` before feature generation.

Supported timestamp aliases now include:

```text
ts_utc
utc_time
timestamp_utc
time_utc
datetime_utc
timestamp
source_time
time
datetime
date
```

## Loader/filter compatibility hardening

This revised package also fixes false zero-row loads caused by dimension spelling differences in the SQLite `bars` table.

The loader now:

```text
- detects `utc_time` and other timestamp aliases by schema introspection
- loads detected OHLCV and dimension columns first
- applies normalized pandas-side filters instead of brittle exact SQL-only filters
- matches source/symbol with strip + casefold + compact normalization
- matches timeframe aliases such as `H1`, `1h`, `60`, `60m`, and `M60`
- records available source/symbol/timeframe values in the summary metadata
- emits a detailed diagnostic JSON if filtering still returns zero rows
```

This specifically protects the project schema:

```text
source, symbol, timeframe, utc_time, open, high, low, close, tick_volume, spread, real_volume, source_time, imported_utc, raw_json, volume, ingested_at
```

Smoke checks performed for this revision:

```text
python3 -m py_compile scripts/stage41_parallel_thesis_megascan_v2.py: PASS
synthetic DB with utc_time + exact amarkets_mt5/XAUUSD/H1: PASS
synthetic DB with utc_time + AMarkets MT5/xau-usd/1h alias values: PASS
negative filter diagnostic with wrong source: PASS, detailed available_dimensions_top20 emitted
```
