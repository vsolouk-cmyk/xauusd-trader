# Stage43_PARALLEL_CONTEXT_REGIME_MEGASCAN_V4

## Purpose

Stage43 is a new independent XAUUSD/gold research branch after Stage41 and Stage42 were archived. It is not a rescue of failed H1/M15 candidates and it must not filter prior weak rows after seeing their failure buckets.

The goal is to test context/regime theses in a fast parallel scan:

1. scan many predefined context/regime theses at once;
2. create a strict/soft shortlist only if the rules survive benchmark, train/OOS, path-risk, slip, bootstrap, and concentration gates;
3. never promote directly from this scan.

## Research-only state

```text
promotion = NO_GO
EA = NO_GO
paper_live = NO_GO
live = NO_GO
```

Any strict or soft row is watch-only and must pass a separate Stage43B path-stability/promotion audit before operational consideration.

## Default data path

```text
DB: data/local/xauusd_local_store.sqlite
Table: bars
Source: amarkets_mt5
Symbol: XAUUSD
Timeframe: M15
```

The loader is DB-first and supports common aliases:

```text
time column: ts_utc / utc_time / timestamp_utc / timestamp / source_time / time / datetime / date
timeframe aliases: 15m / M15 / 15MIN -> M15; 1h / H1 / 60 / M60 -> H1
source/symbol filters: strip + casefold + compact matching
```

If no bars load after filtering, the script reports available source/symbol/timeframe dimensions and filter diagnostics.

## Thesis families

```text
43A_CONTEXT_TREND_PULLBACK_CONTINUATION
43B_VOL_CONTEXT_IMPULSE_EXHAUSTION_REVERSAL
43C_PRIOR_DAY_CONTEXT_RECLAIM_REJECT
43D_CONTEXT_COMPRESSION_TO_EXPANSION
43E_ASIA_RANGE_REGIME_ACCEPT_REJECT
43F_NEUTRAL_REGIME_VALUE_ROTATION
```

These are intentionally context/regime-based. They use endogenous features only:

```text
HTF trend proxy
volatility state
session context
prior-day high/low/range context
Asia range context
compression/expansion state
```

## Outputs

```text
reports/stage43/stage43_parallel_context_regime_megascan_v4_candidates.csv
reports/stage43/stage43_parallel_context_regime_megascan_v4_events.csv
reports/stage43/stage43_parallel_context_regime_megascan_v4_summary.json
reports/stage43/stage43_parallel_context_regime_megascan_v4.md
```

## Main gates

A candidate is not allowed into strict watch unless it satisfies the predefined gates, including:

```text
minimum event-clock samples
positive cost-stressed mean
positive residual versus same-side intraday benchmark
positive train split
positive OOS split
worst-quarter slip16 floor
bootstrap p10 floor
bootstrap probability of positive mean
quarter positivity
year concentration cap
OOS stop-touch cap
```

## Anti-overfit rule

Do not rescue failed Stage43 rows by removing weak hours, months, years, quarters, volatility states, sessions, or stop-touch buckets after seeing results.

## Command

```bash
python3 scripts/stage43_parallel_context_regime_megascan_v4.py
```

Optional example:

```bash
python3 scripts/stage43_parallel_context_regime_megascan_v4.py --timeframe M15 --min-events 120 --cost-bps 8 --slip-bps 16
```

## Next allowed step

```text
Stage43B_STRICT_SHORTLIST_PATH_STABILITY_AUDIT
```

This is allowed only if:

```text
strict_stage43_context_regime_scan_watch_count > 0
```

If strict count is zero, archive Stage43 or start a genuinely new branch.
