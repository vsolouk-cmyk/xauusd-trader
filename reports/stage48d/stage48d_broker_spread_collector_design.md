# Stage48D Broker Spread Collector / MT5 Export Design

## Status

`DESIGN_AND_VALIDATOR_READY_NO_PROMOTION`

No trading scan, EA, paper-live, or live action is allowed from this stage.

## Why this stage exists

Stage48C found that a broker/execution-like SQLite schema exists, especially `data/local/xauusd_local_store.sqlite` table `bars`, but row-level numeric spread coverage is insufficient. The best table had long coverage and many filtered rows, but only about 5.5% of scanned rows had numeric spread. That is not enough to build a broker-real cost model.

## Required export target

Create or export a broker/MT5 CSV with row-level spread or bid/ask information into:

```text
data/broker_export/xauusd_m5_spread_export.csv
```

Minimum required columns:

```text
time_utc,symbol,timeframe,open,high,low,close,spread_points,broker,source
```

Optional but strongly preferred columns:

```text
bid_close,ask_close,tick_volume,real_volume,server_time,session_utc
```

## Acceptance thresholds

The validator requires:

```text
min_rows >= 5000
coverage_days >= 20
numeric_spread_coverage_pct >= 80
positive numeric spread rows exist
```

## Operational recommendation

Prefer MT5 broker export from the same broker/server intended for paper/live execution. Reference data such as TwelveData OHLC is not enough for execution-realism studies because it lacks broker-specific spread spikes, rollover behavior, and session-dependent cost.

## Next allowed step after validation

If the validator returns:

```text
BROKER_SPREAD_EXPORT_READY_NO_PROMOTION
```

then the next allowed step is:

```text
STAGE48E_BROKER_REALISM_DECISION_MEMO
```

If it returns:

```text
BROKER_SPREAD_EXPORT_INSUFFICIENT_NO_PROMOTION
```

then more broker/export data is required. Do not start a trading thesis scan.
