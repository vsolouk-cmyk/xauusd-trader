# Stage 1 Data Snapshot

## Purpose

Stage 1 moves from a single smoke-test interval to a multi-interval data snapshot.

It still does **not** create trading signals.

## Stage 1 definition

Stage 1 collects, normalizes, quality-checks, and summarizes multiple XAUUSD intervals.

Current intervals:

- `1min`
- `5min`
- `15min`
- `1h`

## Key definitions

- Snapshot: a saved batch of market data and reports at one point in time.
- Interval/timeframe: the candle duration, such as 1 minute or 1 hour.
- Data quality: checks for missing candles, duplicate timestamps, and basic feed consistency.
- Cost model: assumed trading costs used later when real spread is unavailable.

## Local command

```bash
cd ~/Desktop/xauusd-trader
export TWELVEDATA_API_KEY='PASTE_KEY_HERE'
python3 -m app.xauusd_stage1_snapshot --outputsize 500
```

Optional custom intervals:

```bash
python3 -m app.xauusd_stage1_snapshot --intervals 1min,5min,15min,1h --outputsize 500
```

## Expected outputs

```text
data/raw/*.json
data/normalized/*.csv
data/reports/quality_*.json
data/reports/stage1_snapshot_summary_*.json
data/reports/stage1_snapshot_summary_*.md
```

## Pass condition

Stage 1 passes only if every interval has:

- `ok: true`
- zero duplicate timestamps,
- acceptable missing ratio excluding weekend closure,
- parseable normalized CSV.

## Not a pass/fail issue yet

`spread.available: false` is expected for Twelve Data.

This is not a Stage 1 kill-switch. It becomes critical in baseline testing and execution validation.
